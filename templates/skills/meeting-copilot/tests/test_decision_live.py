#!/usr/bin/env python3
"""判定層を会議中に効かせる配線 (copilot.py) の回帰テスト。

**外へは1バイトも出さない。** 判定器は差し替えた偽物で、答えは試験が決める。

ここで見ているのは「出るべきときに出て、**足りないときは何も出ない**」——
外れたカードは、無いカードより悪い。会議の最中に読む人は、出たものを信じる。

  · 約束(Q8) … 境目以上で3行カード1枚・同じ発話で2枚出さない・境目未満は出ない
  · 探し物(Q4) … 合図の語が無くても判定で起動する(既存の規則と OR)
  · 段(Q1) … 画面に添えるだけ。**段は動かさない**・出すのは show_decision_cards のときだけ
  · 種類(Q3) … 雑談のあとは催促を見送る
  · 局面(Q2) … 「終わった」が続いたら予鈴だけ。**畳むには無音が要る**
  · 会議中は撃ち直さない(retry_busy_sec=0)
  · 判定層が落ちても番人は生き続ける

実行:
    python3 -m unittest discover -s templates/skills/meeting-copilot/tests -v
書き込みは tempfile の中だけ。
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
EXAMPLE_MEETING = SKILL / "config" / "example_meeting"

sys.path.insert(0, str(SCRIPTS))

import decision_engine as de  # noqa: E402

TS_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def iso(dt: datetime) -> str:
    return dt.strftime(TS_FMT)


def load_copilot(meeting, state):
    """会議フォルダと状態ディレクトリを差し替えて copilot を読み直す。"""
    for k in ("MEETLIVE_AGENDA", "MEETLIVE_SCRIPT", "MEETLIVE_STAGE",
              "MEETLIVE_CREDS_FILE", "MEETLIVE_PHRASEBOOK", "MEETLIVE_QUICK_FACTS"):
        os.environ.pop(k, None)
    os.environ["MEETLIVE_MEETING"] = str(meeting)
    os.environ["MEETLIVE_DIR"] = str(state)
    for name in ("meetlive_config", "lookup_assist", "decision_engine", "copilot"):
        sys.modules.pop(name, None)
    return importlib.import_module("copilot")


class FakeEngine:
    """答えを試験が決める判定器。外へは出ない。"""

    name = "fake"

    def __init__(self):
        self.answers = {}
        self.calls = 0
        self.raise_next = None
        self.delay = 0.0

    def set(self, **kw):
        """``q8=0.9`` のように「問い=確信度」で置く。"""
        self.answers = dict(kw)

    def evaluate(self, state, questions):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.raise_next:
            e, self.raise_next = self.raise_next, None
            raise e
        by = {}
        a = self.answers
        if "q8" in a and "q8_commitment" in questions:
            p = a["q8"]
            by["q8_commitment"] = de.Answer(
                qid="q8_commitment", qtype="noul", value="yes" if p >= 0.5 else "no",
                confidence=max(p, 1 - p), p_yes=p)
        if "q4" in a and "q4_lookup" in questions:
            p = a["q4"]
            by["q4_lookup"] = de.Answer(
                qid="q4_lookup", qtype="noul", value="yes" if p >= 0.5 else "no",
                confidence=max(p, 1 - p), p_yes=p)
        if "q1" in a and "q1_step" in questions:
            key, c = a["q1"]
            by["q1_step"] = de.Answer(qid="q1_step", qtype="choice", value=key,
                                      confidence=c)
        if "q3" in a and "q3_kind" in questions:
            key, c = a["q3"]
            by["q3_kind"] = de.Answer(qid="q3_kind", qtype="choice", value=key,
                                      confidence=c)
        if "q2" in a and "q2_phase" in questions:
            key, c = a["q2"]
            by["q2_phase"] = de.Answer(qid="q2_phase", qtype="score", value=key,
                                       confidence=c)
        return de.Answers(by_id=by, backend=self.name)


class LiveBase(unittest.TestCase):
    """会議フォルダの複製で番人を1体作る。判定器は偽物に差し替える。"""

    show_cards = True
    backend = "jev"

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dlive_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.meeting = self.tmp / "meeting"
        shutil.copytree(EXAMPLE_MEETING, self.meeting)
        self.state = self.tmp / "state"
        self.state.mkdir()
        # 会議フォルダ側で判定層を入にする（既定は rules・カードなし）
        mj = json.loads((self.meeting / "meeting.json").read_text(encoding="utf-8"))
        mj["decision_backend"] = self.backend
        mj["show_decision_cards"] = self.show_cards
        (self.meeting / "meeting.json").write_text(
            json.dumps(mj, ensure_ascii=False), encoding="utf-8")
        # 宛先を空にしておく（万一この設定が使われても外へ出ない）
        self._saved = {k: os.environ.get(k) for k in ("MEETLIVE_MEETING", "MEETLIVE_DIR")}
        self.addCleanup(self._restore)
        self.c = load_copilot(self.meeting, self.state)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for name in ("copilot", "viewer2", "meetlive_config", "lookup_assist",
                     "decision_engine"):
            sys.modules.pop(name, None)

    def make(self):
        c = self.c
        kb = c.Knowledge()
        kb.load()
        cop = c.Copilot(kb, datetime.now() - timedelta(minutes=1))
        cop.call_answerer = lambda *a, **k: None
        cop.call_premise_watch = lambda *a, **k: None
        cop.started = True
        self.fake = FakeEngine()
        # 本物の鎖は差し替える前に控えておく（どの段が組み立てられたかを見る試験用）
        self.real_engine = cop.decision["engine"] if cop.decision else None
        if cop.decision:
            cop.decision["engine"] = self.fake
        return cop

    def stage_names(self) -> list:
        """組み立てられた退避の鎖の段の名前。"""
        eng = self.real_engine
        if eng is None:
            return []
        return [e.name for e in eng.engines] if hasattr(eng, "engines") else [eng.name]

    def say(self, cop, speaker, text, at=None):
        cop.feed({"ts": iso(at or datetime.now()), "speaker": speaker, "text": text})
        cop.wait_decisions(5)

    def cards(self, kind=None):
        p = self.state / "cards.jsonl"
        if not p.exists():
            return []
        out = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        return [c for c in out if kind is None or c["kind"] == kind]


class WiringTest(LiveBase):
    """配線そのもの。"""

    def test_the_layer_is_built_and_never_retries_during_a_meeting(self):
        cop = self.make()
        self.assertIsNotNone(cop.decision, "判定層が組み立てられていない")
        # 番人が読み込んだのと同じモジュールを使う（読み直すと別クラスになる）
        dec = sys.modules["decision_engine"]
        eng = dec.make_engine("rules", cop.decision["bundle"], cop.decision["meeting"])
        self.assertTrue(hasattr(eng, "evaluate"))
        # 🔴 会議中に混雑で待つと、そのカードは会話が次へ行ったあとに出る
        real = dec.make_engine("jev", dec.bundle_from_dict({
            "jev": {"base_url": "x", "key_env": "K"},
            "fallback_chain": ["jev", "rules"], "questions": []}),
            cop.decision["meeting"], note=lambda m: None)
        self.assertEqual(real.retry_busy_sec, 0.0)

    def test_the_shipped_chain_fits_inside_the_pool(self):
        """③ 警告は「4秒/発話 × 班の本数」を超える鎖のときだけ。"""
        b = cop_bundle = self.make().decision["bundle"]
        budget = 0.0
        for st in cop_bundle.fallback_chain:
            if st.name == "jev" and b.jev.base_url:
                budget += st.timeout_sec or b.jev.timeout_sec
            elif st.name == "llm" and b.llm.base_url:
                budget += st.timeout_sec or b.llm.timeout_sec
        room = self.c.SEC_PER_UTTERANCE * self.c.MAX_DECISION_WORKERS
        self.assertLessEqual(budget, room,
                             f"同梱の鎖({budget}秒)が班で捌ける上限({room}秒)を超えている")
        self.assertAlmostEqual(budget, 3.5, places=2, msg=f"鎖の上限は3.5秒のはず: {budget}")

    def test_the_worker_never_blocks_the_main_loop(self):
        cop = self.make()
        self.fake.delay = 0.6
        self.fake.set(q8=0.95)
        t0 = time.monotonic()
        cop.feed({"ts": iso(datetime.now()), "speaker": "host",
                  "text": "明日までに資料をお送りします。"})
        spent = time.monotonic() - t0
        self.assertLess(spent, 0.3, f"本線が判定を待っている({spent:.2f}s)")
        cop.wait_decisions(5)
        self.assertEqual(len(self.cards("commit")), 1)

    def test_utterances_are_not_dropped_while_one_is_in_flight(self):
        # 🔴 1本ずつだと、鎖が遅い日は見送りだらけでカードが出ない。
        #    本数ぶんは重ねて走らせて、発話を取り落とさない。
        cop = self.make()
        self.fake.delay = 0.4
        self.fake.set(q8=0.95)
        for i in range(self.c.MAX_DECISION_WORKERS):
            cop.feed({"ts": iso(datetime.now() + timedelta(seconds=i)),
                      "speaker": "host", "text": f"{i}番目の約束をします。"})
        cop.wait_decisions(10)
        self.assertEqual(self.fake.calls, self.c.MAX_DECISION_WORKERS,
                         "重ねて走らせていない（発話を取り落としている）")
        self.assertEqual(len(self.cards("commit")), self.c.MAX_DECISION_WORKERS)

    def test_the_oldest_in_flight_is_abandoned_when_the_pool_is_full(self):
        cop = self.make()
        self.fake.delay = 0.5
        self.fake.set(q8=0.95)
        n = self.c.MAX_DECISION_WORKERS
        for i in range(n + 1):           # 1本ぶん溢れさせる
            cop.feed({"ts": iso(datetime.now() + timedelta(seconds=i)),
                      "speaker": "host", "text": f"{i}番目の約束をします。"})
        cop.wait_decisions(10)
        time.sleep(0.6)                  # 諦めた班が返ってくるのを待つ
        # 判定は全部走る（通信は止められない）が、**画面に出るのは諦めなかった分だけ**
        self.assertEqual(self.fake.calls, n + 1)
        self.assertEqual(len(self.cards("commit")), n,
                         "諦めたはずの判定がカードになっている")
        recs = [json.loads(x) for x in
                (self.state / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(1 for r in recs if r.get("abandoned")), 1,
                         "諦めた印が記録に残っていない")
        self.assertEqual(len(recs), n + 1, "記録は全部残すこと（採点の材料）")

    def test_an_exception_in_the_worker_does_not_kill_the_watchdog(self):
        cop = self.make()
        self.fake.raise_next = RuntimeError("判定器が壊れた")
        self.say(cop, "host", "明日までにお送りします。")
        self.assertEqual(self.cards("commit"), [])
        # 番人は生きていて、次の発話は普通に処理される
        self.fake.set(q8=0.95)
        self.say(cop, "host", "来週までに見積をお送りします。")
        self.assertEqual(len(self.cards("commit")), 1)

    def test_every_judgement_is_written_to_the_log(self):
        cop = self.make()
        self.fake.set(q8=0.1)
        self.say(cop, "host", "そうですね、わかりました。")
        recs = [json.loads(x) for x in
                (self.state / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(recs), 1)
        self.assertIn("q8_commitment", recs[0]["answers"])
        self.assertEqual(recs[0]["backend"], "fake")


class RosterGateTest(LiveBase):
    """🔴 名簿が無ければ、外へ出す段は会議中も起動しない。

    いちばん起きやすいのは「roster.txt を作り忘れたが meeting.json に相手の
    呼び方は書いてある」。保険で関門が開くと、**警告なしに実名が外へ出る**
    （2026-09-20 の独立レビューが、ライブ経路だけこの穴を持っていると指摘）。
    """

    def test_no_roster_file_means_no_outward_stage_even_with_a_counterpart(self):
        (self.meeting / "roster.txt").unlink()
        mj = json.loads((self.meeting / "meeting.json").read_text(encoding="utf-8"))
        self.assertTrue(mj.get("counterpart"), "この試験は counterpart 前提")
        cop = self.make()
        # 判定は動く（ルールだけ）が、外へ出る実装は1つも組み立てられていない
        self.assertIsNotNone(cop.decision)
        names = self.stage_names()
        self.assertEqual(names, ["rules"], f"外へ出る段が残っている: {names}")
        # 保険（counterpart）は名簿に入っているが、関門は開けていない
        self.assertTrue(cop.decision["meeting"].roster, "保険そのものは効いている")

    def test_an_empty_roster_file_is_the_same_as_none(self):
        (self.meeting / "roster.txt").write_text(
            "# 名前をまだ書いていない\n\n", encoding="utf-8")
        self.make()
        self.assertEqual(self.stage_names(), ["rules"])

    def test_a_real_roster_lets_the_outward_stage_through(self):
        self.make()                # デモの roster.txt はそのまま
        names = self.stage_names()
        self.assertIn("jev", names, f"名簿があるのに止めている: {names}")

    def test_the_gate_is_the_same_function_the_replay_uses(self):
        dec = sys.modules["decision_engine"]
        ok, why = dec.roster_gate(self.meeting, dec.Privacy())
        self.assertTrue(ok, why)
        (self.meeting / "roster.txt").unlink()
        ok, why = dec.roster_gate(self.meeting, dec.Privacy())
        self.assertFalse(ok)
        self.assertIn("roster.txt", why)


class DecisionLogConcurrencyTest(LiveBase):
    """`decisions.jsonl` は班3本から同時に書かれる。1行が割れないこと。"""

    def test_three_threads_never_break_a_line(self):
        import threading
        dec = sys.modules["decision_engine"]
        logf = dec.DecisionLog(self.state / "concurrent.jsonl")
        # 会議中に伸びうる大きさ（窓8発話＋候補30件）に近い行を書く
        big = "あ" * 3000
        ans = dec.Answers(by_id={}, backend="t")
        n = 40

        def run(k):
            for i in range(n):
                logf.write(utterance_id=f"{k}-{i}", ts="t", speaker="host",
                           state={"recent_utterances": [{"text": big}]},
                           questions={"q": {"instructions": big}},
                           answers=ans, latency_ms=1.0)

        ths = [threading.Thread(target=run, args=(k,)) for k in range(3)]
        for th in ths:
            th.start()
        for th in ths:
            th.join(30)
        lines = (self.state / "concurrent.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3 * n, "行が落ちている/増えている")
        ids = set()
        for ln in lines:
            ids.add(json.loads(ln)["utterance_id"])   # 壊れていれば例外
        self.assertEqual(len(ids), 3 * n, "同じ行が二重に書かれている")


class CommitCardTest(LiveBase):
    """① 約束(Q8)。9/19 に1件も記録に残らなかった穴。"""

    SAY = "そこはこちらで持ち帰って、水曜までにお送りします。"

    def test_a_confident_promise_draws_one_three_line_card(self):
        cop = self.make()
        self.fake.set(q8=0.85)
        self.say(cop, "host", self.SAY)
        cards = self.cards("commit")
        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertEqual(c["to"], "進行役へ")
        self.assertTrue(c["target"], "【対象】が空")
        self.assertIn("進行役がいま約束した", c["status"])
        self.assertIn("水曜までに", c["status"], "逐語が【状況】に入っていない")
        self.assertIn("台帳", c["say"])
        for k in ("target", "status", "say"):
            self.assertTrue(c[k].strip(), k)

    def test_below_the_threshold_nothing_is_drawn(self):
        cop = self.make()
        self.fake.set(q8=0.7)          # 既定の境目は 0.8
        self.say(cop, "host", self.SAY)
        self.assertEqual(self.cards("commit"), [])

    def test_the_same_utterance_never_draws_twice(self):
        cop = self.make()
        self.fake.set(q8=0.9)
        at = datetime.now()
        self.say(cop, "host", self.SAY, at=at)
        cop.decision_seen.discard("x")          # 別経路で消えないことの確認用
        self.say(cop, "host", self.SAY, at=at)  # 同じ ts = 同じ発話
        self.assertEqual(len(self.cards("commit")), 1)

    def test_the_threshold_comes_from_decisions_yaml(self):
        cop = self.make()
        q = cop.decision["bundle"].question("q8_commitment")
        q.thresholds["act"] = 0.6
        self.fake.set(q8=0.7)                    # 既定なら出ない値
        self.say(cop, "host", self.SAY)
        self.assertEqual(len(self.cards("commit")), 1, "設定した境目が効いていない")


class LookupTest(LiveBase):
    """② 探し物(Q4)。合図の語と **OR**。"""

    def test_the_judgement_starts_a_lookup_without_a_cue_word(self):
        cop = self.make()
        self.fake.set(q4=0.6)
        # 合図の語（「お待ちください」等）を1つも含まない言い方
        self.say(cop, "host", "検証環境の入口、いまアカウントの一覧を見ています。")
        self.assertTrue(self.cards("lookup"), "判定層から探し物が起動していない")

    def test_below_the_threshold_it_does_not_fire(self):
        cop = self.make()
        self.fake.set(q4=0.3)
        self.say(cop, "host", "検証環境の入口、アカウントの一覧です。")
        self.assertEqual(self.cards("lookup"), [])

    def test_the_cue_word_still_works_on_its_own(self):
        """既存の規則は判定層に置き換えられていない（足しただけ）。"""
        cop = self.make()
        self.fake.set(q4=0.0)
        self.say(cop, "guest", "検証環境の入口はどこでしたっけ。")
        self.say(cop, "host", "ちょっとお待ちください。検証環境の入口を確認します。")
        self.assertTrue(self.cards("lookup"), "合図の語だけで出なくなっている")

    def test_the_same_find_is_not_repeated(self):
        cop = self.make()
        self.fake.set(q4=0.9)
        self.say(cop, "host", "検証環境の入口のアカウント一覧です。")
        n = len(self.cards("lookup"))
        self.say(cop, "host", "検証環境の入口のアカウント一覧です。")
        self.assertEqual(len(self.cards("lookup")), n, "同じ探し物を撃ち直している")


class StepHintTest(LiveBase):
    """③ 段(Q1)。画面に添えるだけで、段は動かさない。"""

    def test_a_confident_step_is_written_as_a_hint(self):
        cop = self.make()
        self.fake.set(q1=("s3", 0.9))
        before = cop.cur
        self.say(cop, "host", "現状の確認に入らせてください。")
        hint = json.loads((self.state / "decision_hint.json").read_text(encoding="utf-8"))
        self.assertEqual(hint["step"], "s3")
        self.assertTrue(hint["title"])
        # 🔴 段そのものは規則の側でしか動かない
        self.assertEqual(cop.cur, cop.calc_cur())
        self.assertEqual(cop.auto_hi, cop.auto_step(),
                         "判定層が段の高水位を動かしている")
        del before

    def test_below_the_threshold_or_none_writes_nothing(self):
        cop = self.make()
        self.fake.set(q1=("s3", 0.6))
        self.say(cop, "host", "そのあたりを見ていきましょう。")
        self.assertFalse((self.state / "decision_hint.json").exists())
        self.fake.set(q1=("none", 0.99))
        self.say(cop, "host", "ところで今日は暑いですね。")
        self.assertFalse((self.state / "decision_hint.json").exists())

    def test_the_viewer_ignores_a_stale_hint(self):
        cop = self.make()
        self.fake.set(q1=("s3", 0.95))
        self.say(cop, "host", "現状の確認に入らせてください。")
        v = importlib.import_module("viewer2")
        self.assertIsNotNone(v.decision_hint(self.state))
        old = time.time() - (v.DECISION_HINT_MAX_AGE + 30)
        os.utime(self.state / "decision_hint.json", (old, old))
        self.assertIsNone(v.decision_hint(self.state),
                          "古い推定を画面に出し続けている")


class HintOffTest(LiveBase):
    """show_decision_cards が false なら画面は変わらない（記録だけ）。"""

    show_cards = False

    def test_nothing_reaches_the_screen_but_the_log_still_grows(self):
        cop = self.make()
        self.assertIsNotNone(cop.decision, "記録のための判定層まで止まっている")
        self.fake.set(q1=("s3", 0.95))
        self.say(cop, "host", "現状の確認に入らせてください。")
        self.assertFalse((self.state / "decision_hint.json").exists())
        self.assertTrue((self.state / "decisions.jsonl").exists())


class OffTest(LiveBase):
    """既定（rules・カードなし）では判定層そのものを組み立てない。"""

    show_cards = False
    backend = "rules"

    def test_the_layer_is_not_built_at_all(self):
        cop = self.make()
        self.assertIsNone(cop.decision)
        cop.feed({"ts": iso(datetime.now()), "speaker": "host", "text": "お送りします。"})
        self.assertIsNone(cop.decision_thread)
        self.assertEqual(cop._jobs, [])
        self.assertFalse((self.state / "decisions.jsonl").exists())


class KindAndPhaseTest(LiveBase):
    """④ 種類(Q3) と ⑤ 局面(Q2)。"""

    def test_small_talk_holds_back_the_next_nudge(self):
        cop = self.make()
        self.fake.set(q3=("small_talk", 0.9))
        self.say(cop, "host", "いい天気ですね。")
        self.assertGreater(cop.suppress_nudge_until, time.time())
        cop.last_line_ts = datetime.now() - timedelta(seconds=60)
        cop.cur = 1
        n = len(self.cards())
        cop.tick()
        self.assertEqual(len(self.cards()), n, "雑談の直後に催促が出ている")

    def test_a_confident_fact_does_not_hold_anything_back(self):
        cop = self.make()
        self.fake.set(q3=("fact", 0.95))
        self.say(cop, "host", "登録は12事業所まで進んでいます。")
        self.assertLessEqual(cop.suppress_nudge_until, time.time())

    # 🔴 別れの言葉そのものは**既存のキーワード規則**でも予鈴を鳴らす。
    #    ここで測りたいのは判定層の側なので、その語を1つも含まない文を使う
    #    (でないと、鳴ったのがどちらの仕掛けか分からない)。
    QUIET = ("本日はこれで終わりということで。", "はい、以上になります。",
             "そういうことで、大丈夫です。", "承知しました、そのように。")

    def test_ended_three_times_rings_the_bell_but_does_not_stop(self):
        cop = self.make()
        self.fake.set(q2=("ended", 0.9))
        for s in self.QUIET[:2]:
            self.say(cop, "host", s)
        self.assertIsNone(cop.farewell_at, "2発話で予鈴が鳴っている")
        self.say(cop, "host", self.QUIET[2])
        self.assertIsNotNone(cop.farewell_at, "3発話続いても予鈴が鳴らない")
        # 🔴 予鈴は停止ではない。無音が続くまで畳まない
        cop.last_line_ts = datetime.now()
        cop.check_end(time.time(), 0.0)
        self.assertFalse(cop.stopping, "無音なしで畳もうとしている")
        self.assertFalse(cop.stop_file_written() if hasattr(cop, "stop_file_written")
                         else (self.state / "meetlive.stop").exists())

    def test_a_body_answer_resets_the_streak(self):
        cop = self.make()
        self.fake.set(q2=("ended", 0.9))
        for s in self.QUIET[:2]:
            self.say(cop, "host", s)
        self.fake.set(q2=("body", 0.9))
        self.say(cop, "host", "あ、もう1件だけよろしいですか。")
        self.assertEqual(cop.ended_streak, 0)
        self.fake.set(q2=("ended", 0.9))
        self.say(cop, "host", self.QUIET[3])
        self.assertIsNone(cop.farewell_at, "数え直しになっていない")

    def test_a_low_confidence_ended_does_not_count(self):
        cop = self.make()
        self.fake.set(q2=("ended", 0.5))
        for s in self.QUIET:
            self.say(cop, "host", s)
        self.assertIsNone(cop.farewell_at)


if __name__ == "__main__":
    unittest.main()
