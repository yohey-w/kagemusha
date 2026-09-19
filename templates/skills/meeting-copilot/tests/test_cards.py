#!/usr/bin/env python3
"""カードの3要素・催促の重複抑制・終話検知・探し物アシストの回帰テスト。

2026-09-19 の実走で焼けた3つを、そのまま検査項目にしてある:

  実測① カード1013件のうち3要素（対象/状況/言うこと）がそろっていたのは14件（1.4%）
        → 番人が出す**全種別**に3要素があること
  実測② 同一文言の催促カードが960件（45秒に1回×12時間）
        → 同じ対象の催促は初回だけフルカード、以後はバッジ
  実測③ 会議後も3プロセスが12時間近く残った
        → 終話を検知したら自分で停止ファイルを置くこと。
          そして**会議の最中には置かないこと**（こちらのほうが害が大きい）

加えて、Q3（カンペの粒度）とQ4（探し物アシスト）の表示・秘密の扱いを見る。

⚠ このテストは LLM を呼ばない。answerer / premise_watch の起動は無効化してある
  （有効なままだと、検査のたびに本物のモデルへ発注が飛ぶ）。

実行: python3 -m unittest discover -s templates/skills/meeting-copilot/tests
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
EXAMPLE_MEETING = SKILL / "config" / "example_meeting"
sys.path.insert(0, str(SCRIPTS))

# 番人が出すカードの種別（＝3要素がそろっていなければならない全部）
ALL_KINDS = ("call", "topic", "warn", "wrap", "lookup")


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def load_copilot(meeting: pathlib.Path, state: pathlib.Path):
    for k in ("MEETLIVE_AGENDA", "MEETLIVE_SCRIPT", "MEETLIVE_STAGE",
              "MEETLIVE_PHRASEBOOK", "MEETLIVE_CREDS_FILE", "MEETLIVE_LEDGER",
              "MEETLIVE_QUICK_FACTS", "MEETLIVE_SCRIPT_MODE"):
        os.environ.pop(k, None)
    os.environ["MEETLIVE_MEETING"] = str(meeting)
    os.environ["MEETLIVE_DIR"] = str(state)
    for name in ("copilot", "viewer2", "meetlive_config", "lookup_assist", "step_detect"):
        sys.modules.pop(name, None)
    return importlib.import_module("copilot")


class CopilotCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cards_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.meeting = self.tmp / "meeting"
        shutil.copytree(EXAMPLE_MEETING, self.meeting)
        self.state = self.tmp / "state"
        self.state.mkdir()
        self._saved = {k: os.environ.get(k)
                       for k in ("MEETLIVE_MEETING", "MEETLIVE_DIR")}
        self.addCleanup(self._restore)
        self.c = load_copilot(self.meeting, self.state)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for name in ("copilot", "viewer2", "meetlive_config", "lookup_assist"):
            sys.modules.pop(name, None)

    def make(self, start=None, end=None):
        """番人を1体作る。🔴 外部モデルを呼ぶ2経路はここで塞ぐ。"""
        c = self.c
        kb = c.Knowledge()
        kb.load()
        cop = c.Copilot(kb, start or datetime.now() - timedelta(minutes=1), end=end)
        cop.call_answerer = lambda *a, **k: None       # LLM を呼ばせない
        cop.call_premise_watch = lambda *a, **k: None  # 同上（子プロセス）
        cop.started = True
        return cop

    def cards(self):
        p = self.state / "cards.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

    def say(self, cop, speaker, text, at=None):
        cop.feed({"ts": iso(at or datetime.now()), "speaker": speaker, "text": text})

    # ================================================ 実測① 3要素
    def test_every_card_has_the_three_elements(self):
        cop = self.make()
        step2_kw = cop.kb.steps[1]["kw"][0]
        # call（呼びかけへの回答）
        self.say(cop, "host", f"{self.c.CALL_WORDS[0]}、いま何分たってる？")
        # warn（約束の境界）
        self.say(cop, "guest", "ところで、お値段はいくらになりますか")
        # topic（進行）
        self.say(cop, "guest", "はい、お願いします")
        self.say(cop, "host", f"では、{step2_kw}についてお話しさせてください")
        # lookup（探し物）
        self.say(cop, "guest", "検証環境のログイン画面を見せてもらえますか")
        self.say(cop, "host", "ちょっとお待ちください、検証環境のアドレスどこだっけ")
        # wrap（中止条件）— 語彙は会議フォルダの phrasebook から取る
        self.say(cop, "host", f"そこは{self.c.HANDOVER_WORDS[0]}ので、あらためてご連絡します")

        got = self.cards()
        self.assertTrue(got, "カードが1枚も出ていない")
        kinds = {c["kind"] for c in got}
        for k in ("call", "warn", "topic", "lookup", "wrap"):
            self.assertIn(k, kinds, f"{k} カードが出ていない: {kinds}")
        for c in got:
            for field in ("target", "status", "say", "to"):
                self.assertTrue(str(c.get(field, "")).strip(),
                                f"{c['kind']} カードに {field} が無い: {c}")
            self.assertIn(c["to"], ("進行役へ", "記録のみ"))
            self.assertTrue(c.get("lines"), "lines（後方互換）が空")
            self.assertNotEqual(c["lines"], ["手元にありません。"],
                                f"3要素から lines を作れていない: {c}")

    def test_internal_ids_do_not_become_the_card_subject(self):
        """premise_ok の【対象】は台帳の事実文。"F-011" のような内部IDは小さく添えるだけ。"""
        sys.modules.pop("premise_watch", None)
        try:
            pw = importlib.import_module("premise_watch")
        except SystemExit as e:               # PyYAML が無い環境ではこの層を飛ばす
            self.skipTest(f"premise_watch を読み込めない: {e}")
        pid = pw.PREMISES[0]["id"]
        title = pw.PREMISES[0]["title"]
        card = pw.to_card({"ts": iso(datetime.now()), "type": "既知",
                           "source": pid, "reply": "はい、そのとおりです。",
                           "utterance": "動いてますね"})
        self.assertEqual(card["target"], title)
        self.assertEqual(card["ref"], pid)
        self.assertNotIn(pid, card["target"], "内部IDが本文の対象になっている")
        self.assertEqual(card["say"], "はい、そのとおりです。")
        self.assertEqual(card["to"], "進行役へ")

    def test_nudge_card_says_what_to_ask_not_just_what_is_missing(self):
        """「○○を聞くと進みます」で終わらせない。読み上げられる問いを出す。"""
        cop = self.make()
        must = next(m for s in cop.kb.steps for m in s["must"] if m.get("ask"))
        cop.nudge("k", must["name"], "まだ取れていません", cop.ask_for(must, 0), "検査")
        c = self.cards()[-1]
        self.assertEqual(c["target"], must["name"])
        self.assertEqual(c["say"], must["ask"][:58] if len(must["ask"]) <= 58
                         else must["ask"][:57] + "…")
        self.assertNotIn("聞くと進みます", c["say"])

    # ================================================ 実測② 催促の重複抑制
    def test_repeated_nudge_becomes_a_badge_not_a_new_full_card(self):
        cop = self.make()
        for _ in range(60):
            cop.nudge("m:1", "鍵の名義", "まだ取れていません",
                      "鍵の名義はどちら様でしょうか", "検査")
        got = [c for c in self.cards() if c["target"] == "鍵の名義"]
        # 初回1枚 + 節目(2,4,8,16,32)のバッジ5枚 = 6枚。960件の反復は起きない
        self.assertLessEqual(len(got), 8, f"催促が {len(got)} 枚出た（反復の再発）")
        self.assertGreaterEqual(len(got), 2, "件数のバッジが1枚も出ていない")
        self.assertFalse(got[0].get("badge"), "初回はフルカード")
        self.assertTrue(got[-1].get("badge"), "2枚目以降はバッジ")
        self.assertEqual(got[-1]["count"], 32)
        self.assertEqual(cop.nudged["m:1"], 60, "数え落としがある")

    def test_different_targets_each_get_their_own_full_card(self):
        cop = self.make()
        cop.nudge("a", "鍵の名義", "まだ", "名義はどちらですか", "検査")
        cop.nudge("b", "請求の宛名", "まだ", "宛名はどちらですか", "検査")
        got = self.cards()
        self.assertEqual(len(got), 2)
        self.assertFalse(any(c.get("badge") for c in got))

    def test_viewer_folds_the_same_target_into_one_card(self):
        """画面側でも畳む（番人が撃ち直しても、右列に同じカードが積み上がらない）。"""
        sys.modules.pop("viewer2", None)
        v = importlib.import_module("viewer2")
        cop = self.make()
        for _ in range(20):
            cop.nudge("m:1", "鍵の名義", "まだ", "名義はどちらですか", "検査")
        (self.state / "transcript.jsonl").write_text(
            json.dumps({"ts": iso(datetime.now() - timedelta(minutes=2)),
                        "type": "mode", "mode": "start"}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        st = v.build_state(self.state, v.load_agenda(v.AGENDA_PATH),
                           (datetime.now() - timedelta(minutes=2)).timestamp(), None)
        same = [c for c in st["cards"] if c.get("target") == "鍵の名義"]
        self.assertEqual(len(same), 1, f"同じ対象が {len(same)} 枚並んでいる")
        self.assertEqual(same[0]["unresolved"], 16, "未解決の件数が出ていない")
        self.assertTrue(same[0]["say"], "畳んだ結果、言うことが消えている")

    # ================================================ 実測③ 終話検知
    def test_no_stop_while_the_meeting_is_still_running(self):
        """🔴 会議の最中に畳むほうが害が大きい。予定超過だけでは絶対に止めない。

        実走の会議は60分の予定に対して133分かかった。
        """
        start = datetime.now() - timedelta(minutes=133)
        cop = self.make(start=start, end=start + timedelta(minutes=60))
        cop.last_line_ts = datetime.now() - timedelta(seconds=20)   # いま喋っている
        cop.tick()
        self.assertFalse(self.c.STOP_FILE.exists(),
                         "予定を73分超えていても、喋っている間は止めてはいけない")
        self.assertFalse(cop.stopping)

    def test_farewell_alone_does_not_stop(self):
        cop = self.make(start=datetime.now() - timedelta(minutes=30))
        self.say(cop, "host", "本日はこれで失礼します")
        self.assertIsNotNone(cop.farewell_at, "別れの言葉を拾えていない")
        cop.last_line_ts = datetime.now()
        cop.tick()
        self.assertFalse(self.c.STOP_FILE.exists(), "別れの言葉だけでは止めない")

    def test_farewell_then_silence_stops(self):
        cop = self.make(start=datetime.now() - timedelta(minutes=30))
        self.say(cop, "host", "本日はこれで失礼します")
        cop.last_line_ts = datetime.now() - timedelta(minutes=9)
        cop.tick()
        self.assertTrue(self.c.STOP_FILE.exists(), "別れの言葉＋無音でも止まらない")
        why = json.loads(self.c.STOP_FILE.read_text(encoding="utf-8"))
        self.assertEqual(why["by"], "copilot")
        self.assertIn("別れの挨拶", why["why"])
        last = self.cards()[-1]
        self.assertEqual(last["to"], "記録のみ")
        self.assertIn("同席", last["target"])

    def test_long_silence_stops(self):
        cop = self.make(start=datetime.now() - timedelta(minutes=90))
        cop.last_line_ts = datetime.now() - timedelta(minutes=30)
        cop.tick()
        self.assertTrue(self.c.STOP_FILE.exists())
        self.assertIn("無音", json.loads(
            self.c.STOP_FILE.read_text(encoding="utf-8"))["why"])

    def test_a_restored_rehearsal_transcript_does_not_stop_the_meeting(self):
        """リハの逐語を復元しただけ（本番の発話がまだ0）では止めない。"""
        start = datetime.now() + timedelta(minutes=5)      # 会議はこれから
        cop = self.make(start=start)
        cop.last_line_ts = start - timedelta(hours=12)     # 前夜の試験発話
        cop.start = datetime.now() - timedelta(minutes=1)  # 開始直後に見立てる
        cop.tick()
        self.assertFalse(self.c.STOP_FILE.exists(),
                         "前夜の逐語の古さで、始まった直後に畳んではいけない")

    def test_stop_is_written_only_once(self):
        cop = self.make(start=datetime.now() - timedelta(minutes=90))
        cop.last_line_ts = datetime.now() - timedelta(minutes=30)
        cop.tick()
        n = len(self.cards())
        cop.tick()
        cop.tick()
        self.assertEqual(len(self.cards()), n, "終話カードが繰り返し出ている")

    # ================================================ 段の検知
    def test_step_advances_on_the_second_host_segment_after_the_guest(self):
        """音声認識はこちらの発話を細切れにする。相手の直後の1発話だけを見ると、
        相槌で枠を使い切って本題を取りこぼす（実測の失敗の裏返し）。"""
        cop = self.make()
        kw = cop.kb.steps[1]["kw"][0]
        self.say(cop, "guest", "そうですね、お願いします")
        self.say(cop, "host", "はい、ありがとうございます。")           # 相槌
        self.say(cop, "host", f"では、{kw}についてお話しさせてください")  # 本題
        self.assertEqual(cop.auto_step(), 1, "2発話目の本題で段が進むはず")

    def test_a_keyword_deep_inside_our_own_monologue_does_not_jump_steps(self):
        """こちらが長く喋り続けている途中の偶然一致では飛ばない（実測の誤検知の対策）。"""
        cop = self.make()
        kw = cop.kb.steps[3]["kw"][0]
        self.say(cop, "guest", "なるほど、わかりました")
        for i in range(6):
            self.say(cop, "host", f"ええ、そのあたりは追って整理しますね（{i}）")
        self.say(cop, "host", f"ちなみに{kw}の話も前に出ていましたね")
        self.assertEqual(cop.auto_step(), 0, "独話の奥での一致で段が飛んでいる")

    def test_backchannel_never_advances(self):
        cop = self.make()
        kw = cop.kb.steps[1]["kw"][0]
        self.say(cop, "guest", "どうぞ")
        self.say(cop, "host", kw[:3])          # 短い断片
        self.assertEqual(cop.auto_step(), 0)


class QuickFactsCase(CopilotCase):
    """Q4 探し物アシスト。"""

    def test_trigger_words_fire_and_others_do_not(self):
        import lookup_assist as la
        for t in ("ちょっとお待ちください、資料を出します",
                  "確認しますね",
                  "えーっと、どこだっけ"):
            self.assertTrue(la.is_lookup(t, la.DEFAULT_TRIGGERS), t)
        for t in ("それでいきましょう",
                  "はい、そのとおりです",
                  "では次の話に move しましょう"):
            self.assertFalse(la.is_lookup(t, la.DEFAULT_TRIGGERS), t)

    def test_quick_facts_hit_produces_a_three_line_card(self):
        cop = self.make()
        self.say(cop, "guest", "検証環境のログイン画面を見せてもらえますか")
        self.say(cop, "host", "ちょっとお待ちください、検証環境のアドレスどこだっけ")
        got = [c for c in self.cards() if c["kind"] == "lookup"]
        self.assertEqual(len(got), 1, self.cards())
        c = got[0]
        self.assertIn("検証環境", c["target"])
        self.assertIn("即答表", c["status"])
        self.assertTrue(c["say"])
        self.assertEqual(c["to"], "進行役へ")

    def test_ledger_facts_are_searched_too(self):
        import lookup_assist as la
        idx = la.Index(ledger=self.meeting / "ledger.yaml")
        if not len(idx):
            self.skipTest("台帳を読めない環境（PyYAML 無し）")
        fact = idx.entries[0]
        probe = " ".join(sorted(fact["bag"], key=len, reverse=True)[:3])
        hit = idx.find(f"確認します、{probe}は", "")
        self.assertIsNotNone(hit, f"台帳の事実に当たらない: {probe}")
        self.assertTrue(hit["ref"], "台帳の項目なのに内部IDが付いていない")

    def test_a_secret_is_never_put_on_the_card(self):
        """🔴 合言葉・鍵・トークンの値は出さない（画面共有に映る事故の元）。"""
        import lookup_assist as la
        qf = self.tmp / "qf.md"
        qf.write_text("## 管理画面のパスワード\n"
                      "値: hunter2-SUPERSECRET-9999\n", encoding="utf-8")
        idx = la.Index(quick_facts=qf)
        hit = idx.find("えーっと、管理画面のパスワードは", "パスワードを教えてください")
        self.assertIsNotNone(hit)
        self.assertNotIn("hunter2-SUPERSECRET-9999", hit["say"])
        self.assertNotIn("hunter2-SUPERSECRET-9999", hit["status"])
        self.assertIn("鍵パネル", hit["say"])

    def test_nothing_value_shaped_survives_rendering_of_a_secret_entry(self):
        """同梱の即答表をぜんぶ描いてみて、秘密の項目から値が漏れないことを見る。"""
        import lookup_assist as la
        entries = la.parse_quick_facts(
            (EXAMPLE_MEETING / "quick_facts.md").read_text(encoding="utf-8"))
        self.assertTrue(entries, "同梱の即答表が読めていない")
        secret = [e for e in entries if e["secret"]]
        self.assertTrue(secret, "秘密の扱いを見せる項目が同梱の即答表に無い")
        for e in entries:
            out = la.Index.render({**e, "target": e["title"], "status": "s",
                                   "say": e["body"], "ref": ""})
            if e["secret"]:
                self.assertNotRegex(out["say"], la.VALUE_RE,
                                    f"秘密の項目から値らしい文字列が出ている: {e['title']}")
                self.assertIn("鍵パネル", out["say"])

    def test_a_miss_is_recorded_for_later(self):
        cop = self.make()
        self.say(cop, "guest", "むかしの話ですが")
        self.say(cop, "host", "ちょっとお待ちください、ええと、あれの件どこだっけ")
        p = self.state / "lookup_misses.jsonl"
        self.assertTrue(p.exists(), "当たらなかった探し物が記録されていない")
        rec = json.loads(p.read_text(encoding="utf-8").splitlines()[-1])
        self.assertIn("host", rec)
        self.assertIn("guest", rec)
        self.assertIn("むかしの話", rec["guest"])

    def test_the_same_thing_is_not_offered_twice(self):
        cop = self.make()
        for _ in range(4):
            self.say(cop, "guest", "検証環境のログイン画面を見せてもらえますか")
            self.say(cop, "host", "ちょっとお待ちください、検証環境のアドレスどこだっけ")
        got = [c for c in self.cards() if c["kind"] == "lookup"]
        self.assertEqual(len(got), 1, "同じ探し物を繰り返し出している")

    def test_lookup_does_not_swallow_the_rest_of_the_utterance(self):
        """探し物は**足すだけ**。同じ発話の警報や進行を消してはいけない。"""
        cop = self.make()
        self.say(cop, "guest", "それ、追加の費用はいくらになりますか")
        self.say(cop, "host", "ちょっとお待ちください、お見積りの金額を確認します")
        kinds = {c["kind"] for c in self.cards()}
        self.assertIn("warn", kinds, f"金額の警報が消えている: {kinds}")


class ScriptModeCase(CopilotCase):
    """Q3 カンペの粒度（answers_only で言い方の例を隠す）。"""

    def blocks(self, mode: str):
        raw = json.loads((self.meeting / "meeting.json").read_text(encoding="utf-8"))
        raw["script_mode"] = mode
        (self.meeting / "meeting.json").write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        for name in ("viewer2", "meetlive_config"):
            sys.modules.pop(name, None)
        v = importlib.import_module("viewer2")
        return v, v.build_blocks(v.load_agenda(v.AGENDA_PATH), v.parse_script(v.SCRIPT_PATH))

    def test_with_lines_shows_all_three_rows(self):
        _v, blocks = self.blocks("with_lines")
        for b in blocks:
            roles = [x.get("role") for x in b["items"]]
            self.assertIn("line", roles, f"【{b['n']}】に言い方の例が無い")
            self.assertIn("answer", roles)
            self.assertIn("ask", roles)

    def test_answers_only_hides_the_line_to_say(self):
        _v, blocks = self.blocks("answers_only")
        for b in blocks:
            roles = [x.get("role") for x in b["items"]]
            self.assertNotIn("line", roles, f"【{b['n']}】で言い方の例が隠れていない")
            self.assertIn("answer", roles, "取る答えまで消えている")
            self.assertIn("ask", roles, "抜けたら出す問いまで消えている")

    def test_the_setting_is_read_through_meetlive_config(self):
        v, _ = self.blocks("answers_only")
        self.assertEqual(v.cfgmod.script_mode(), "answers_only")
        v2, _ = self.blocks("nonsense")
        self.assertEqual(v2.cfgmod.script_mode(), "with_lines", "知らない値は既定へ")


if __name__ == "__main__":
    unittest.main()
