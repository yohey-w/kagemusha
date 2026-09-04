#!/usr/bin/env python3
"""返し役 (responder.py) の回帰テスト（標準ライブラリだけ・LLM は呼ばない）。

ここで見るのは、9/3〜9/4 の実走で焼けた4つの仕様。どれも「壊れても会議の朝までは
気づけない」たぐいのもの:

  1. 材料は **全量・切り詰めゼロ**で連結される
     (切り詰めは沈黙ではなく捏造を生む ── 答えが後半にある問いで、台本と逆のことを
      自信をもって言い出す。9/3 実測)
  2. 呼びかけ語は meeting.json のものが効き、相手 (guest) の発話では暴発しない
  3. 心拍は viewer2 が読める書式で書かれる (稼働ラインの「心拍なし」が誤報にならない)
  4. 先読み (bank) が当たったときは LLM を**呼ばない** (音声の遅延に間に合わせる仕掛け)

実行:
    python3 -m unittest discover -s templates/skills/meeting-copilot/tests -v
書き込みは tempfile の中だけ・外へは一切出ない (LLM 経路はスタブに差し替える)。
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"

sys.path.insert(0, str(SCRIPTS))

MEETLIVE_ENV = ("MEETLIVE_MEETING", "MEETLIVE_DIR", "MEETLIVE_KNOWLEDGE_DIR",
                "MEETLIVE_SCRIPT_NAME", "MEETLIVE_BANK", "MEETLIVE_CALL_WORDS",
                "MEETLIVE_MODEL_ANSWER", "MEETLIVE_EFFORT_ANSWER")

# viewer2 が心拍・カードの時刻を読む書式。ここがズレると「心拍なし」と誤報する。
VIEWER_TS_FMT = "%Y-%m-%dT%H:%M:%S.%f"

SCRIPT_MD = """# 台本

## 【1】冒頭
> 本日はお時間をいただきありがとうございます。まずは前回の宿題からご説明します。

## 【2】費用の話
> 比較レポートは想定8〜12時間・上限10万円でお見積りします、と一度お伝えください。
🚫 その場で値引きを約束しない
"""

LONG_DOC = "# 長い資料\n" + "".join(f"{i:04d}行目の本文である。\n" for i in range(1200))

MEETING_JSON = {
    "title": "テスト会議（架空）",
    "host_label": "進行役",
    "counterpart": "先方",
    "call_words": ["コパイロット", "こぱいろっと", "秘書"],
}


def load_responder(meeting: pathlib.Path, state: pathlib.Path, **env):
    """環境を差し替えて responder を読み直す。"""
    for k in MEETLIVE_ENV:
        os.environ.pop(k, None)
    os.environ["MEETLIVE_MEETING"] = str(meeting)
    os.environ["MEETLIVE_DIR"] = str(state)
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(v)
    for name in ("responder", "meetlive_config"):
        sys.modules.pop(name, None)
    mod = importlib.import_module("responder")
    mod.reset_config()
    return mod


class ResponderCase(unittest.TestCase):
    """会議フォルダを1つ作り、その中で返し役を動かす。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.meeting = root / "meeting"
        self.state = root / "state"
        (self.meeting / "kb").mkdir(parents=True)
        self.state.mkdir(parents=True)
        (self.meeting / "meeting.json").write_text(
            json.dumps(MEETING_JSON, ensure_ascii=False), encoding="utf-8")
        (self.meeting / "kb" / "talk_script.md").write_text(SCRIPT_MD, encoding="utf-8")
        (self.meeting / "kb" / "long_doc.md").write_text(LONG_DOC, encoding="utf-8")
        self.r = load_responder(self.meeting, self.state)
        self.llm_calls = []

    def tearDown(self):
        self.tmp.cleanup()
        for k in MEETLIVE_ENV:
            os.environ.pop(k, None)

    def stub_llm(self, reply: str = ""):
        """LLM 経路を差し替える。呼ばれた回数と引数を記録する。"""
        def _fake(text, recent, pack, timeout=90.0):
            self.llm_calls.append({"text": text, "pack": pack})
            return reply
        self.r.call_llm = _fake

    def write_bank(self, cards: list):
        (self.meeting / "bank.json").write_text(
            json.dumps(cards, ensure_ascii=False), encoding="utf-8")

    # ── 1. 材料は全量 ──────────────────────────────────────────────────
    def test_pack_contains_every_material_in_full(self):
        """kb/ の中身が1つ残らず、しかも**全文**で入る。"""
        pack = self.r.build_pack()
        self.assertIn(SCRIPT_MD, pack, "台本が全文で入っていない")
        self.assertIn(LONG_DOC, pack, "長い資料が全文で入っていない（切り詰められた）")
        self.assertIn("0000行目", pack)
        self.assertIn("1199行目", pack, "末尾が落ちている＝切り詰めが復活している")
        self.assertGreaterEqual(len(pack), len(SCRIPT_MD) + len(LONG_DOC))

    def test_pack_ignores_the_configured_character_limits(self):
        """切り詰めの上限を絞っても、返し役の材料は縮まない。

        answerer は上限に従うが、返し役は従わない ── ここが 9/3 の事故の芯。
        「上限を渡したら効いてしまった」を機械で止める。
        """
        r = load_responder(self.meeting, self.state,
                           MEETLIVE_KNOWLEDGE_PER_FILE=200, MEETLIVE_KNOWLEDGE_TOTAL=400)
        self.assertIn(LONG_DOC, r.build_pack())

    def test_new_material_needs_no_code_change(self):
        """棚に置いたファイルがそのまま材料になる（コード側の一覧を持たない）。"""
        (self.meeting / "kb" / "zz_added_later.md").write_text(
            "後から足した資料。これも読まれること。", encoding="utf-8")
        self.assertIn("後から足した資料", self.r.build_pack())

    def test_script_leads_the_pack(self):
        """接地の基準になる台本は先頭に置く（後ろにあると読み飛ばされやすい）。"""
        pack = self.r.build_pack()
        self.assertLess(pack.index("talk_script.md"), pack.index("long_doc.md"))

    def test_pack_is_rebuilt_when_material_changes(self):
        """前夜に台本を直しても、古いパックのまま会議に入らない。"""
        first = self.r.load_pack()
        self.assertIn("上限10万円", first)
        p = self.meeting / "kb" / "talk_script.md"
        p.write_text(SCRIPT_MD + "\n## 【3】追記された節\n> 追記された文言です。\n",
                     encoding="utf-8")
        os.utime(p, (p.stat().st_atime + 10, p.stat().st_mtime + 10))
        self.assertIn("追記された節", self.r.load_pack())

    # ── 2. 呼びかけ語 ──────────────────────────────────────────────────
    def test_call_words_come_from_meeting_json(self):
        self.assertEqual(self.r.cfgmod.call_words(),
                         ("コパイロット", "こぱいろっと", "秘書"))

    def test_call_detected_for_host_by_word(self):
        """receiver の call フラグが無くても、呼びかけ語だけで拾う。"""
        self.assertTrue(self.r.is_call({"speaker": "host", "text": "コパイロット、いまの件は?"}))
        self.assertTrue(self.r.is_call({"speaker": "host", "text": "秘書、費用は?"}))

    def test_call_detected_for_host_by_flag(self):
        self.assertTrue(self.r.is_call({"speaker": "host", "text": "いまの件", "call": True}))

    def test_no_call_without_a_call_word(self):
        self.assertFalse(self.r.is_call({"speaker": "host", "text": "では次の話に移ります"}))

    def test_guest_never_triggers_a_call(self):
        """相手が呼びかけ語を口にしても撃たない（話者が土台・9/4 の host/guest 規律）。"""
        self.assertFalse(self.r.is_call({"speaker": "guest", "text": "コパイロットって何ですか"}))
        self.assertFalse(self.r.is_call({"speaker": "guest", "text": "秘書", "call": True}))

    def test_call_words_follow_the_meeting_folder(self):
        """別の会議フォルダなら別の呼びかけ語（コードに焼かない）。"""
        (self.meeting / "meeting.json").write_text(
            json.dumps({**MEETING_JSON, "call_words": ["モニタ"]}, ensure_ascii=False),
            encoding="utf-8")
        r = load_responder(self.meeting, self.state)
        self.assertTrue(r.is_call({"speaker": "host", "text": "モニタ、いまの数字は?"}))
        self.assertFalse(r.is_call({"speaker": "host", "text": "コパイロット、いまの数字は?"}))

    # ── 3. 心拍 ────────────────────────────────────────────────────────
    def test_heartbeat_shape(self):
        """{"ts","role","model","note"} が状態Dir直下に出る。"""
        p = self.r.write_heartbeat("待機")
        self.assertEqual(p, self.state / "heartbeat.json")
        hb = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(set(hb), {"ts", "role", "model", "note"})
        self.assertEqual(hb["role"], "responder")
        self.assertEqual(hb["note"], "待機")
        self.assertTrue(hb["model"], "モデル名が空だと稼働ラインで何が動いているか分からない")

    def test_heartbeat_timestamp_parses_the_way_the_viewer_parses_it(self):
        """viewer2 の _ts と同じ書式。ここがズレると常に「心拍なし」と誤報する。"""
        hb = json.loads(self.r.write_heartbeat().read_text(encoding="utf-8"))
        parsed = datetime.strptime(hb["ts"], VIEWER_TS_FMT)
        self.assertLess(abs((datetime.now() - parsed).total_seconds()), 120)

    def test_heartbeat_leaves_no_half_written_file(self):
        """置き換えで書く（読み手が書き途中を掴んで「壊れている」に見えない）。"""
        for _ in range(3):
            self.r.write_heartbeat("連打")
        left = [p.name for p in self.state.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(left, [], f"一時ファイルが残っている: {left}")
        json.loads((self.state / "heartbeat.json").read_text(encoding="utf-8"))

    # ── 4. 先読みが当たったら LLM を呼ばない ────────────────────────────
    def test_bank_hit_skips_the_llm(self):
        self.write_bank([{
            "key": "hikaku", "uniq": ["比較レポート"], "kw": ["いくら", "費用"],
            "sec": "【2】費用の話",
            "reply": "比較レポートは想定8〜12時間・上限10万円でお見積りします、と一度お伝えください。",
            "nums": "想定8〜12時間・上限10万円", "forbid": "その場で値引きを約束しない",
        }])
        r = load_responder(self.meeting, self.state)
        self.r = r
        self.stub_llm("節: 呼ばれてはいけない\n返し: 呼ばれてはいけない\n数字: なし\n禁: なし")
        rec = r.answer("比較レポートはいくらですか")
        self.assertEqual(self.llm_calls, [], "先読みが当たったのに LLM を呼んでいる")
        self.assertTrue(rec["src"].startswith("bank/hikaku"), rec["src"])
        self.assertEqual(rec["sec"], "【2】費用の話")
        self.assertEqual(rec["bad_numbers"], [], "台本にある数字を「無い数字」と誤検出した")

    def test_bank_miss_falls_through_to_the_llm(self):
        self.write_bank([{"key": "hikaku", "uniq": ["比較レポート"], "kw": [],
                          "sec": "【2】費用の話", "reply": "x", "nums": "", "forbid": ""}])
        r = load_responder(self.meeting, self.state)
        self.r = r
        self.stub_llm("節: 【1】冒頭\n返し: 本日はお時間をいただきありがとうございます。まずは前回の宿題からご説明します。\n数字: なし\n禁: 値引きの約束")
        rec = r.answer("まったく別の話題について伺えますか", gate_context="まったく別の話題")
        self.assertEqual(len(self.llm_calls), 1, "未知の発話なのに LLM を呼んでいない")
        self.assertIn(SCRIPT_MD, self.llm_calls[0]["pack"], "LLM へ渡した材料が全文でない")

    def test_a_single_weak_word_does_not_fire_the_bank(self):
        """普通語1つだけの弱い一致で撃たない（議題外の発話に金額つきカードが出る事故）。"""
        bank = [{"key": "hikaku", "uniq": [], "kw": ["いくら", "費用"],
                 "sec": "【2】費用の話", "reply": "…", "nums": "", "forbid": ""}]
        self.assertIsNone(self.r.bank_hit("費用のことはまた今度で", bank)[0])
        self.assertIsNotNone(self.r.bank_hit("費用はいくらですか", bank)[0])

    # ── 出力の読み取り ─────────────────────────────────────────────────
    def test_reason_words_do_not_contaminate_the_forbid_line(self):
        """根拠語はラベルとして受ける。受けないと「🚫 …」の末尾にぶら下がる（9/4 実測）。"""
        d = self.r.parse_out("節: 【2】費用の話\n返し: あああ\n数字: なし\n"
                             "禁: 値引きを約束しない\n根拠語: 比較レポート")
        self.assertEqual(d["forbid"], "値引きを約束しない")
        self.assertEqual(d["why"], "比較レポート")

    def test_reason_words_never_reach_the_card(self):
        """根拠語は判断の跡であって、読み上げる文ではないので画面には出さない。"""
        rec = {"ts": datetime.now().strftime(self.r.TS_FMT), "kind": "reply", "q": "q",
               "src": "llm", "latency_s": 0.1, "sec": "【2】費用の話", "reply": "あああ",
               "nums": "なし", "forbid": "値引きを約束しない", "why": "比較レポート",
               "bad_numbers": [], "gated": []}
        self.assertNotIn("比較レポート", " ".join(self.r.to_card(rec)["lines"]))

    # ── ついで: カードの書式（viewer2 が読む形） ────────────────────────
    def test_emitted_card_has_the_fields_the_viewer_reads(self):
        rec = {"ts": datetime.now().strftime(self.r.TS_FMT), "kind": "reply",
               "q": "比較レポートはいくらですか", "src": "bank/x", "latency_s": 0.1,
               "sec": "【2】費用の話", "reply": "上限10万円でお見積りします",
               "nums": "上限10万円", "forbid": "値引きの約束", "bad_numbers": [], "gated": []}
        self.r.emit(rec)
        card = json.loads((self.state / "cards.jsonl").read_text(encoding="utf-8").strip())
        self.assertEqual(card["kind"], "reply")
        self.assertEqual(card["confidence"], "high")
        self.assertEqual(card["q"], "比較レポートはいくらですか")
        self.assertTrue(card["lines"][0].startswith("§"))
        datetime.strptime(card["ts"], VIEWER_TS_FMT)

    def test_no_material_is_logged_but_not_shown_unless_called(self):
        """「材料になし」で画面を塗り替えない。ただし呼ばれたときは必ず出す。"""
        base = {"ts": datetime.now().strftime(self.r.TS_FMT), "q": "雑談", "src": "llm",
                "latency_s": 0.1, "bad_numbers": [], "gated": [], **self.r.FALLBACK}
        self.r.emit({**base, "kind": "reply"})
        self.assertFalse((self.state / "cards.jsonl").exists(), "材料になしがカードになった")
        self.assertTrue((self.state / self.r.LOG_NAME).exists(), "ログには残すこと")
        self.r.emit({**base, "kind": "call"})
        card = json.loads((self.state / "cards.jsonl").read_text(encoding="utf-8").strip())
        self.assertEqual(card["kind"], "call")
        self.assertEqual(card["confidence"], "none")


if __name__ == "__main__":
    unittest.main()
