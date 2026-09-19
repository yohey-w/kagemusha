#!/usr/bin/env python3
"""「同席開始」合図の回帰テスト（標準ライブラリだけ・外へは出ない）。

背景（実際に焼けた事故・T-0019）: ある日の会議で、進行役が「同席開始」と言っても画面の段が
自動で切り替わらず、手で切り替える実害が出た。原因は **書く側 (receiver.py) が完全一致で
しか検知しておらず、読む側 (viewer2.py / copilot.py) だけが聞き取り揺れを吸収していた非対称**。
音声の開始合図は、全会議を通じて1度も効いていなかった。

なので、このテストの中心は「拾える/拾えない」ではなく **書く側と読む側が同じ入力集合を
受理すること** に置いてある。片方だけ賢くする改修が入ったら、ここが赤くなる。

3段:
  1. 述語 mode_signal.is_start_signal — 実際に音声認識が化けた綴りだけで検査する
  2. 対称性 — 同じ入力集合を、書く側 (receiver.Writer) と読む側 (viewer2.build_nav) に
     流し、受理する集合が一致することを確かめる
  3. ボタン (/mode/start) — 音声より確実な主手段。transcript に1行書かれ、画面が①へ戻る

⚠ 想像の例文を足さないこと。足すのは実際に化けたものだけ（増やすと誤爆側が育つ）。
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timedelta

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
EXAMPLE_MEETING = SKILL / "config" / "example_meeting"
sys.path.insert(0, str(SCRIPTS))

# デモ会議フォルダが持っている語彙で検査する（設定から取れることの確認も兼ねる）。
CALL_WORDS = ("コパイロット", "こぱいろっと", "秘書", "ひしょ")
START_WORD = "同席開始"
HOMOPHONES = ("透析", "同時")
VOCAB = {"call_words": CALL_WORDS, "start_word": START_WORD, "homophones": HOMOPHONES}

# (発話, 出典) — 出典は「実データで観測した誤変換」か「合成(自己確認)」
POSITIVE_CASES = [
    ("同席開始。", "合成: 正しい合図そのもの(完全一致の自己確認)"),
    ("透析開始。", "実観測: 『同席開始』が『透析開始』に化けた"),
    ("秘書開始。", "実観測: 呼びかけ語+開始 に化けた"),
    ("秘書開始してほしいな。", "実観測: 語尾がついた形"),
    ("コパイロット、スタート", "合成: アンカー語がスタート側"),
]

NEGATIVE_CASES = [
    ("今動作機会して喋ったけど。", "実観測: 誤変換の連鎖・アンカー語なし"),
    ("今同席返しって喋ったけど。", "実観測: 『同席』はあるが開始/スタートが無い"),
    ("今非常開始って喋ってんだけどね。", "実観測: 『開始』はあるが語彙に無い"),
    ("同時にこれを確認する前に", "実観測: 『同時』だけでアンカー語無し"),
    ("同時に一つの入力で三つできるという認識で", "実観測: 通常会話"),
    ("例のごとくうちのAIを同席させてまして、これが", "実観測: 『同席』はあるが同上"),
    ("席始めます。紹介して", "実観測: 『開始』を含まない誤変換"),
    ("秘書さん、これいくらですか", "合成: 呼びかけ語だけでは発火しない確認"),
    ("", "合成: 空文字"),
]

ALL_CASES = [t for t, _ in POSITIVE_CASES] + [t for t, _ in NEGATIVE_CASES]
EXPECTED = {t: True for t, _ in POSITIVE_CASES}
EXPECTED.update({t: False for t, _ in NEGATIVE_CASES})


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def load_modules(meeting: pathlib.Path, state: pathlib.Path):
    for k in ("MEETLIVE_MEETING", "MEETLIVE_DIR", "MEETLIVE_AGENDA", "MEETLIVE_SCRIPT",
              "MEETLIVE_STAGE", "MEETLIVE_CREDS_FILE", "MEETLIVE_CALL_WORDS",
              "MEETLIVE_START_HOMOPHONES", "MEETLIVE_LAYOUT"):
        os.environ.pop(k, None)
    os.environ["MEETLIVE_MEETING"] = str(meeting)
    os.environ["MEETLIVE_DIR"] = str(state)
    for name in ("viewer2", "receiver", "mode_signal", "meetlive_config"):
        sys.modules.pop(name, None)
    return (importlib.import_module("mode_signal"),
            importlib.import_module("receiver"),
            importlib.import_module("viewer2"))


class ModeSignalCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="mode_signal_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.meeting = self.tmp / "meeting"
        shutil.copytree(EXAMPLE_MEETING, self.meeting)
        self.state = self.tmp / "state"
        self.state.mkdir()
        self._saved = {k: os.environ.get(k) for k in
                       ("MEETLIVE_MEETING", "MEETLIVE_DIR")}
        self.addCleanup(self._restore)
        self.mode_signal, self.receiver, self.viewer2 = load_modules(self.meeting, self.state)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def step2_utterance(self) -> str:
        """段②へ進ませる発話を**デモ会議フォルダの段取りから作る**。

        ここに文字列を直書きすると、デモの段取りを組み替えただけでこのテストが
        赤くなる（このテストが見ているのは合図の対称性であって、デモの文言ではない）。
        段②の検知キーワードをそのまま含む、十分な長さの発話を作る。
        """
        v = self.viewer2
        steps = (v.load_agenda(v.AGENDA_PATH) or {})["steps"]
        kw = next((k for k in steps[1]["kw"] if k), "")
        self.assertTrue(kw, "デモ会議フォルダの段②に検知キーワードがありません")
        return f"では、{kw}についてお話しさせてください"


# ---------------------------------------------------------------- 1. 述語


class TestPredicate(ModeSignalCase):
    def test_positive_cases(self):
        for text, src in POSITIVE_CASES:
            with self.subTest(text=text):
                self.assertTrue(self.mode_signal.is_start_signal(text, **VOCAB),
                                f"拾えなかった: 「{text}」 ({src})")

    def test_negative_cases(self):
        for text, src in NEGATIVE_CASES:
            with self.subTest(text=text):
                self.assertFalse(self.mode_signal.is_start_signal(text, **VOCAB),
                                 f"誤爆した: 「{text}」 ({src})")

    def test_vocabulary_comes_from_the_meeting_folder(self):
        """語彙はコードでなく会議フォルダから来る（デモ会議は透析/同時を宣言している）。"""
        start_word, fuzzy = self.mode_signal.vocabulary()
        self.assertEqual(start_word, START_WORD)
        for w in ("秘書", "透析", "同席"):
            self.assertIn(w, fuzzy, "呼びかけ語・化けた綴り・開始語の語幹が入る")

    def test_homophones_are_not_hardcoded(self):
        """化けた綴りを宣言していない会議では、その綴りは拾わない（既定は狭い）。"""
        raw = json.loads((self.meeting / "meeting.json").read_text(encoding="utf-8"))
        raw["start_homophones"] = []
        (self.meeting / "meeting.json").write_text(json.dumps(raw, ensure_ascii=False),
                                                   encoding="utf-8")
        ms, _rcv, _v = load_modules(self.meeting, self.state)
        self.assertFalse(ms.is_start_signal("透析開始。"))
        self.assertTrue(ms.is_start_signal("同席開始。"), "開始語そのものは常に拾う")
        self.assertTrue(ms.is_start_signal("秘書開始。"), "呼びかけ語+開始も拾う")


# ---------------------------------------------------------------- 2. 対称性


class TestWriterReaderSymmetry(ModeSignalCase):
    """🔴 このテストが本体。書く側と読む側が、同じ入力集合を受理すること。"""

    def writer_accepts(self, text: str) -> bool:
        """書く側 (receiver.Writer): この発話1本で transcript に mode:start が書かれるか。"""
        d = pathlib.Path(tempfile.mkdtemp(prefix="w_", dir=self.tmp))
        w = self.receiver.Writer(d, quiet=True)
        w.emit("host", text, True, capture_ts=0.0)
        rows = [json.loads(x) for x in
                (d / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        return any(r.get("type") == "mode" and r.get("mode") == "start" for r in rows)

    def reader_accepts(self, text: str) -> bool:
        """読む側 (viewer2.build_nav): この発話を「同席開始」の起点として扱うか。

        観測の仕方: 合図より**前**に段2の検知キーワードを置いておく。起点として扱われれば
        その前の発話は集計から外れて段は①のまま、扱われなければ段②へ進む。
        """
        v = self.viewer2
        agenda = v.load_agenda(v.AGENDA_PATH)
        t0 = datetime.now() - timedelta(minutes=5)
        lines = [
            {"ts": iso(t0), "speaker": "host", "text": self.step2_utterance()},
            {"ts": iso(t0 + timedelta(seconds=30)), "speaker": "host", "text": text},
        ]
        nav = v.build_nav(agenda, lines, "start", t0.timestamp())
        return nav["cur"] == 0

    def test_same_inputs_are_accepted_by_both_sides(self):
        mismatches = []
        for text in ALL_CASES:
            if not text:
                continue                      # 空文字は emit しない経路
            w, r = self.writer_accepts(text), self.reader_accepts(text)
            if w != r:
                mismatches.append(f"「{text}」 書く側={w} 読む側={r}")
        self.assertEqual(mismatches, [],
                         "書く側と読む側で受理が食い違っている（T-0019 の再発）:\n"
                         + "\n".join(mismatches))

    def test_both_sides_match_the_predicate(self):
        for text in ALL_CASES:
            if not text:
                continue
            with self.subTest(text=text):
                want = EXPECTED[text]
                self.assertEqual(self.writer_accepts(text), want, "書く側")
                self.assertEqual(self.reader_accepts(text), want, "読む側")

    def test_fuzzy_match_fires_only_once_before_start(self):
        """あいまい判定は開始前の1回きり（開始後に通常会話で増殖しない）。"""
        d = pathlib.Path(tempfile.mkdtemp(prefix="w_once_", dir=self.tmp))
        w = self.receiver.Writer(d, quiet=True)
        for i, text in enumerate(["透析開始。", "同時にスタートしましょう",
                                  "秘書開始って言ってた"]):
            w.emit("host", text, True, capture_ts=float(i))
        rows = [json.loads(x) for x in
                (d / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        starts = [r for r in rows if r.get("type") == "mode" and r.get("mode") == "start"]
        self.assertEqual(len(starts), 1, f"あいまい判定は1回だけのはず: {starts}")

    def test_exact_start_word_always_fires(self):
        """完全一致は常時発火（言い直せば何度でも効く）。"""
        d = pathlib.Path(tempfile.mkdtemp(prefix="w_exact_", dir=self.tmp))
        w = self.receiver.Writer(d, quiet=True)
        for i in range(3):
            w.emit("host", "同席開始", True, capture_ts=float(i))
        rows = [json.loads(x) for x in
                (d / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        starts = [r for r in rows if r.get("type") == "mode" and r.get("mode") == "start"]
        self.assertEqual(len(starts), 3)

    def test_guest_utterance_never_starts(self):
        """相手の発話では始まらない（回り込みで相手の声が host に入る事故の保険）。"""
        d = pathlib.Path(tempfile.mkdtemp(prefix="w_guest_", dir=self.tmp))
        w = self.receiver.Writer(d, quiet=True)
        w.emit("guest", "同席開始", True, capture_ts=0.0)
        rows = [json.loads(x) for x in
                (d / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertFalse([r for r in rows if r.get("type") == "mode"])


# ---------------------------------------------------------------- 3. ボタン


class TestStartButton(ModeSignalCase):
    def test_button_writes_one_line_and_resets_to_first_step(self):
        v = self.viewer2
        agenda = v.load_agenda(v.AGENDA_PATH)
        blocks = v.build_blocks(agenda, v.parse_script(v.SCRIPT_PATH))
        start_epoch = (datetime.now() - timedelta(minutes=5)).timestamp()
        # 押す前に段2のキーワードを喋っておく = ボタンで①へ戻ることが観測できる
        (self.state / "transcript.jsonl").write_text(
            json.dumps({"ts": iso(datetime.now() - timedelta(minutes=4)),
                        "speaker": "host", "text": self.step2_utterance()},
                       ensure_ascii=False) + "\n", encoding="utf-8")
        handler = v.make_handler(self.state, agenda, blocks, start_epoch)

        class S(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        srv = S(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_address[1]

        with urllib.request.urlopen(base + "/state", timeout=10) as r:
            before = json.loads(r.read().decode())
        self.assertEqual(before["nav"]["cur"], 1, "押す前は段②に進んでいる")

        with urllib.request.urlopen(base + "/mode/start", timeout=10) as r:
            body = json.loads(r.read().decode())
        self.assertTrue(body["ok"])

        rows = [json.loads(x) for x in
                (self.state / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
                if x.strip()]
        starts = [r for r in rows if r.get("type") == "mode" and r.get("mode") == "start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0].get("src"), "button")

        with urllib.request.urlopen(base + "/state", timeout=10) as r:
            after = json.loads(r.read().decode())
        self.assertEqual(after["nav"]["cur"], 0, "ボタンの後は段①へ戻る")
        self.assertTrue(after["nav"]["live"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
