#!/usr/bin/env python3
"""判定層 (decision_engine.py / replay_eval.py) の回帰テスト。

標準ライブラリだけ・**外へは1バイトも出さない**（Jev の経路は 127.0.0.1 に
立てた偽の判定器へ向ける）・鍵が1つも無い機体で全部通る。

ここで見ているのは、要求定義の受入条件そのもの:

  A3 Jev を止めてもルール判定で再生が最後まで通る（退避）
  A4 送った物に名簿の名前が平文で残らない（マスク・**送信の現物**で確認）
  A5 usage から費用が出る（再生の集計）
  ＋ 問いの束の組み立て（host 限定の問いを相手の発話で送らない／候補が
     0件の問いは送らない）と、宛先を内蔵しないこと

実行:
    python3 -m unittest discover -s templates/skills/meeting-copilot/tests -v
書き込みは tempfile の中だけ。
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
DEMO = SKILL / "config" / "example_meeting"
EXAMPLE_BUNDLE = SKILL / "config" / "decisions.example.yaml"

sys.path.insert(0, str(SCRIPTS))

import decision_engine as de  # noqa: E402

# 試験用の鍵の置き場。本物の名前 (AI_GATEWAY_API_KEY 等) は使わない——
# 機体に本物が入っていると、試験が黙って本物を掴んでしまう。
TEST_KEY_ENV = "MEETLIVE_TEST_DECISION_KEY"

# 偽の判定器が返す答え。公式の応答の形（型名・probabilities・usage）に合わせる。
CANNED = {
    "model": "stub-1",
    "answers": {
        "q1_step": {"type": "choice", "choice": "s2",
                    "probabilities": {"s1": 0.1, "s2": 0.8, "none": 0.1},
                    "confidence": 0.72},
        "q2_phase": {"type": "score", "score": 1.4,
                     "legend": {"0": "opening", "1": "body", "2": "closing",
                                "3": "ended"},
                     "confidence": 0.61},
        "q4_lookup": {"type": "noul", "noul": 0.93},
    },
    "usage": {"input_tokens": 1000, "output_tokens": 20},
}

# 偽の小型 LLM が返す本文（JSON の文字列として message.content に入る）
LLM_ANSWER = {
    "q1_step": {"value": "s3", "confidence": 0.7},
    "q2_phase": {"value": "closing", "confidence": 0.6},
    "q4_lookup": {"value": "yes", "confidence": 0.9},
    "q5_quick_fact": {"value": "none", "confidence": 0.55},
    "q8_commitment": {"value": "no", "confidence": 0.8},
}

BUNDLE_DICT = {
    "window": {"utterances": 4, "max_chars": 400},
    "privacy": {"roster": "roster.txt"},
    "jev": {"base_url": "", "path": "/v1/systemone", "model": "stub",
            "key_env": TEST_KEY_ENV, "timeout_sec": 2.0},
    "llm": {"base_url": "", "path": "/v1/chat/completions", "model": "stub-llm",
            "key_env": TEST_KEY_ENV, "timeout_sec": 3.0},
    "fallback_chain": ["jev", "llm", "rules"],
    "pricing": {"input_per_mtok": 2.0, "output_per_mtok": 0.0, "currency": "USD"},
    "questions": [
        {"id": "q1_step", "type": "choice", "ask": "any",
         "candidates": "agenda_steps", "include_none": True,
         "instructions": "Which step?"},
        {"id": "q2_phase", "type": "score", "ask": "any",
         "levels": [{"key": "opening"}, {"key": "body"}, {"key": "closing"},
                    {"key": "ended"}],
         "instructions": "Which phase?"},
        {"id": "q4_lookup", "type": "noul", "ask": "host",
         "instructions": "Is the host looking something up?"},
        {"id": "q5_quick_fact", "type": "choice", "ask": "any",
         "candidates": "quick_facts", "include_none": True,
         "instructions": "Which entry?"},
        {"id": "q8_commitment", "type": "noul", "ask": "host",
         "instructions": "Did the host promise something?"},
    ],
}


class _Handler(BaseHTTPRequestHandler):
    """偽の判定器。受け取った本文を全部ためておく（送信の現物を試験が読む）。"""

    def _json(self, code, obj):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):                                    # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        self.server.received.append({
            "path": self.path, "body": body.decode("utf-8"),
            "auth": self.headers.get("Authorization") or ""})
        # OpenAI 互換のほうは別の道。1台の偽サーバで両方を受ける。
        if self.path.endswith("/chat/completions"):
            mode = self.server.llm_mode
            if mode == "down":
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"boom")
                return
            text = (self.server.llm_text if mode == "custom"
                    else json.dumps(LLM_ANSWER, ensure_ascii=False))
            self._json(200, {"model": "stub-llm",
                             "choices": [{"message": {"content": text}}],
                             "usage": {"prompt_tokens": 700, "completion_tokens": 40}})
            return
        mode = self.server.mode
        if mode == "500":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
            return
        if mode == "429" or (mode == "429once" and not self.server.served_one):
            self.server.served_one = True
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b"slow down")
            return
        if mode == "wrongtype":
            bad = {"model": "stub-1", "usage": {"input_tokens": 1},
                   "answers": {"q4_lookup": {"type": "noul", "noul": "n/a"}}}
            payload = json.dumps(bad).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if mode == "garbage":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"not json at all")
            return
        payload = json.dumps(CANNED).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):                            # 試験の出力を汚さない
        return


class StubServer:
    """127.0.0.1 の空きポートに立てる偽の判定器。"""

    def __init__(self, mode="ok", llm_mode="ok", llm_text=""):
        self.httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.received = []
        self.httpd.mode = mode
        self.httpd.llm_mode = llm_mode
        self.httpd.llm_text = llm_text
        self.httpd.served_one = False
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address[0], self.httpd.server_address[1]
        return "http" + "://" + f"{host}:{port}"

    @property
    def received(self) -> list:
        return self.httpd.received

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def demo_bundle(llm=None, chain=None, **jev) -> de.Bundle:
    d = json.loads(json.dumps(BUNDLE_DICT))
    d["jev"].update(jev)
    if llm:
        d["llm"].update(llm)
    if chain is not None:
        d["fallback_chain"] = chain
    return de.bundle_from_dict(d)


def window(*pairs) -> list:
    return [{"speaker": s, "text": t} for s, t in pairs]


class BundleTest(unittest.TestCase):
    """設定の読み込み。同梱の例と、デモ会議フォルダの分が食い違わないこと。"""

    def test_example_declares_the_six_questions(self):
        # PyYAML の無い機体でも中身は確かめる（拡張子だけ見て通すことはしない）。
        want = ("q1_step", "q2_phase", "q3_kind", "q4_lookup", "q5_quick_fact",
                "q8_commitment")
        for path in (EXAMPLE_BUNDLE, DEMO / "decisions.yaml"):
            text = path.read_text(encoding="utf-8")
            for qid in want:
                self.assertIn(f"id: {qid}", text, f"{path.name} に {qid} が無い")

    def test_example_parses_when_yaml_is_available(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            # yaml が無い機体では、読み手が**黙って空を返さない**ことを確かめる。
            with self.assertRaises(SystemExit):
                de.load_bundle(EXAMPLE_BUNDLE)
            return
        b = de.load_bundle(EXAMPLE_BUNDLE)
        self.assertEqual(len(b.questions), 6)
        self.assertEqual(b.question("q4_lookup").ask, "host")
        self.assertEqual(b.question("q8_commitment").ask, "host")
        self.assertEqual(b.question("q1_step").candidates, "agenda_steps")
        self.assertEqual(b.question("q5_quick_fact").candidates, "quick_facts")
        self.assertEqual([k for k, _ in b.question("q2_phase").levels],
                         ["opening", "body", "closing", "ended"])
        self.assertTrue(b.jev.key_env, "鍵を入れる環境変数の名前が空")

    def test_bundle_path_falls_back_to_the_shipped_example(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(de.resolve_bundle_path(td), de.DECISIONS_EXAMPLE)
        self.assertEqual(de.resolve_bundle_path(DEMO), DEMO / "decisions.yaml")


class QuestionShapeTest(unittest.TestCase):
    """問いの束の組み立て。"""

    def setUp(self):
        self.bundle = demo_bundle()
        self.meeting = de.load_meeting_data(DEMO, self.bundle.privacy)
        self.masker = de.Masker(self.meeting.roster)

    def test_candidates_come_from_the_meeting_folder(self):
        qs = de.build_questions(self.bundle, self.meeting, "host", self.masker)
        crit = qs["q1_step"]["criteria"]
        self.assertIn("none", crit)
        self.assertEqual(len([k for k in crit if k != "none"]), len(self.meeting.steps))
        self.assertGreater(len(self.meeting.steps), 1, "デモに段が無い")
        self.assertGreater(len(qs["q5_quick_fact"]["criteria"]), 1)

    def test_host_only_questions_are_not_sent_for_the_other_party(self):
        host = de.build_questions(self.bundle, self.meeting, "host", self.masker)
        guest = de.build_questions(self.bundle, self.meeting, "guest", self.masker)
        self.assertIn("q4_lookup", host)
        self.assertIn("q8_commitment", host)
        self.assertNotIn("q4_lookup", guest)
        self.assertNotIn("q8_commitment", guest)
        self.assertIn("q1_step", guest)

    def test_a_question_with_no_candidates_is_dropped(self):
        # 会議フォルダに即答表も段取りも無いとき、「該当なし」しか選べない問いを
        # 送っても料金が掛かるだけで何も判らない。
        with tempfile.TemporaryDirectory() as td:
            empty = de.load_meeting_data(td, self.bundle.privacy)
            qs = de.build_questions(self.bundle, empty, "host", self.masker)
        self.assertNotIn("q1_step", qs)
        self.assertNotIn("q5_quick_fact", qs)
        self.assertIn("q4_lookup", qs)

    def test_score_criteria_is_an_ordered_list(self):
        qs = de.build_questions(self.bundle, self.meeting, "host", self.masker)
        self.assertIsInstance(qs["q2_phase"]["criteria"], list)
        self.assertGreaterEqual(len(qs["q2_phase"]["criteria"]), 2)

    def test_the_window_keeps_only_the_recent_utterances(self):
        hist = window(*[("host", f"はつわ{i}" * 20) for i in range(20)])
        win = de.window_of(hist, self.bundle.window, self.bundle.window_chars)
        self.assertLessEqual(len(win), self.bundle.window)
        self.assertLessEqual(sum(len(r["text"]) for r in win),
                             self.bundle.window_chars + len(win[0]["text"]))
        self.assertEqual(win[-1], hist[-1], "いまの発話が窓から落ちている")


class MaskTest(unittest.TestCase):
    """A4: 送った物に名簿の名前が平文で残らない。"""

    def setUp(self):
        self.bundle = demo_bundle()
        self.meeting = de.load_meeting_data(DEMO, self.bundle.privacy)
        self.masker = de.Masker(self.meeting.roster)

    def test_roster_is_loaded_from_the_meeting_folder(self):
        names = [n for n, _ in self.meeting.roster]
        self.assertIn("山田 太郎", names)
        self.assertIn("Acme", names)

    def test_a_family_name_alone_is_masked_too(self):
        # 会議では姓だけで呼ばれる。名簿に姓名で書いてあっても伏せること。
        self.assertNotIn("山田", self.masker.text("山田です、よろしくお願いします"))
        self.assertNotIn("太郎", self.masker.text("太郎さんにお伝えします"))

    def test_the_whole_payload_is_masked_not_only_the_state(self):
        # 段の見出しや即答表の見出しにも相手の名前が入りうるので、**送る物の
        # 全体**（state + questions）で確かめる。
        meeting = de.MeetingData(
            steps=(de.Step("s1", "Acme社への移行の範囲", (), "山田 太郎さんの承認"),),
            quick_facts=(("qf_1", "山田 太郎さんの連絡先"),),
            roster=self.meeting.roster, lookup_triggers=(), farewell_words=(),
            ask_marks=())
        win = window(("guest", "山田です。"), ("host", "Acmeさん、ありがとうございます。"))
        payload = json.dumps(
            {"state": de.build_state(win, self.masker),
             "questions": de.build_questions(self.bundle, meeting, "host", self.masker)},
            ensure_ascii=False)
        for name in ("山田", "太郎", "Acme", "鈴木"):
            self.assertNotIn(name, payload, f"送る物に {name} が残っている")
        self.assertIn("〈相手〉", payload)

    def test_the_counterpart_in_meeting_json_is_masked_without_a_roster(self):
        # roster.txt を作り忘れても、meeting.json に書いてある相手の呼び方は伏せる。
        # 「名簿が無い」がそのまま「名前が素通り」にならないように。
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            (d / "meeting.json").write_text(
                json.dumps({"counterpart": "テスト商事さん", "host_label": "進行役"},
                           ensure_ascii=False), encoding="utf-8")
            meeting = de.load_meeting_data(d)
            names = [n for n, _ in meeting.roster]
            self.assertIn("テスト商事", names, "敬称を落として名簿へ入っていない")
            self.assertNotIn("進行役", names, "既定の呼び方を名前として扱っている")
            masked = de.Masker(meeting.roster).text("テスト商事さんにお送りします")
            self.assertNotIn("テスト商事", masked)

    def test_speaker_labels_are_role_names(self):
        st = de.build_state(window(("host", "あ"), ("guest", "い")), self.masker)
        self.assertEqual([r["speaker"] for r in st["recent_utterances"]],
                         ["〈進行役〉", "〈相手〉"])


class RulesBackendTest(unittest.TestCase):
    """いまの判定を同じ問いの形に包めているか。"""

    def setUp(self):
        self.bundle = demo_bundle()
        self.meeting = de.load_meeting_data(DEMO, self.bundle.privacy)
        self.masker = de.Masker(self.meeting.roster)
        self.engine = de.RulesBackend(self.meeting, self.bundle)

    def _ask(self, win):
        state = de.build_state(win, self.masker)
        qs = de.build_questions(self.bundle, self.meeting, win[-1]["speaker"], self.masker)
        return self.engine.evaluate(state, qs)

    def test_lookup_cue_turns_the_noul_to_yes(self):
        yes = self._ask(window(("guest", "URLはどこでしたっけ"),
                               ("host", "ちょっとお待ちください。確認します。")))
        self.assertEqual(yes.by_id["q4_lookup"].value, "yes")
        no = self._ask(window(("guest", "はい"), ("host", "承知しました。")))
        self.assertEqual(no.by_id["q4_lookup"].value, "no")

    def test_a_step_keyword_in_an_opening_turn_moves_the_step(self):
        a = self._ask(window(("guest", "よろしくお願いします"),
                             ("host", "今日決めたいことは3つあります。")))
        self.assertNotEqual(a.by_id["q1_step"].value, "none")
        # 相槌では動かない（step_detect の min_chars）
        b = self._ask(window(("guest", "よろしくお願いします"), ("host", "はい")))
        self.assertEqual(b.by_id["q1_step"].value, "none")

    def test_questions_it_has_no_rule_for_answer_with_zero_confidence(self):
        # 約束の検知はルールを持っていない。**外すのではなく持っていない**ことが
        # 記録から読めるように、確信度 0 で返す。
        a = self._ask(window(("guest", "お願いします"), ("host", "明日お送りします。")))
        self.assertEqual(a.by_id["q8_commitment"].value, "no")
        self.assertEqual(a.by_id["q8_commitment"].confidence, 0.0)

    def test_every_asked_question_gets_an_answer(self):
        a = self._ask(window(("guest", "はい"), ("host", "ではそのように進めます。")))
        qs = de.build_questions(self.bundle, self.meeting, "host", self.masker)
        self.assertEqual(set(a.by_id), set(qs))
        self.assertEqual(a.backend, "rules")


class CriteriaDetailTest(unittest.TestCase):
    """④ 段の見出しだけでは判定材料が薄いので、「取る答え」を添えられるようにした。"""

    def setUp(self):
        self.meeting = de.load_meeting_data(DEMO)
        self.masker = de.Masker(self.meeting.roster)

    def test_the_detail_line_is_read_from_the_agenda(self):
        self.assertTrue(any(s.detail for s in self.meeting.steps),
                        "デモの段取りに「取る答え」が1つも無い")

    def test_off_by_default_on_and_the_description_grows(self):
        def crit(detail):
            d = json.loads(json.dumps(BUNDLE_DICT))
            for q in d["questions"]:
                if q["id"] == "q1_step":
                    q["criteria_detail"] = detail
            b = de.bundle_from_dict(d)
            return de.build_questions(b, self.meeting, "host",
                                      self.masker)["q1_step"]["criteria"]
        plain, rich = crit(False), crit(True)
        self.assertEqual(set(plain), set(rich), "鍵が変わってはいけない")
        grew = [k for k in plain if k != "none" and len(rich[k]) > len(plain[k])]
        self.assertTrue(grew, "criteria_detail を立てても説明が伸びていない")
        # 既定は off（黙って送る量が増えない）
        self.assertFalse(de.bundle_from_dict(BUNDLE_DICT).question("q1_step").criteria_detail)

    def test_the_detail_is_masked_like_everything_else(self):
        meeting = de.MeetingData(
            steps=(de.Step("s1", "移行の範囲", (), "山田 太郎さんの承認を取る"),),
            roster=self.meeting.roster)
        d = json.loads(json.dumps(BUNDLE_DICT))
        for q in d["questions"]:
            if q["id"] == "q1_step":
                q["criteria_detail"] = True
        qs = de.build_questions(de.bundle_from_dict(d), meeting, "host", self.masker)
        self.assertNotIn("山田", json.dumps(qs, ensure_ascii=False))


class BusyRetryTest(unittest.TestCase):
    """③ 混雑(429/503)のときだけ、退避の前に1回だけ待って撃ち直す。"""

    def setUp(self):
        self.meeting = de.load_meeting_data(DEMO)
        os.environ[TEST_KEY_ENV] = "test-key-not-a-real-one"
        self.addCleanup(lambda: os.environ.pop(TEST_KEY_ENV, None))

    def test_the_http_status_survives_as_a_number(self):
        srv = StubServer(mode="429")
        self.addCleanup(srv.close)
        b = demo_bundle(base_url=srv.base_url)
        with self.assertRaises(de.DecisionError) as cm:
            de.JevBackend(b.jev, bundle=b).evaluate({"recent_utterances": []},
                                                    {"q4_lookup": {"type": "noul"}})
        self.assertEqual(cm.exception.status, 429)

    def test_a_busy_signal_is_retried_once_and_then_succeeds(self):
        # 1回目だけ 429、2回目から通る偽の判定器
        srv = StubServer(mode="429once")
        self.addCleanup(srv.close)
        b = demo_bundle(base_url=srv.base_url)
        eng = de.make_engine("jev", b, self.meeting, retry_busy_sec=0.01)
        ans = eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})
        self.assertEqual(ans.backend, "jev", "撃ち直して通ったのに退避している")
        self.assertIn("撃ち直して通った", ans.error)
        self.assertEqual(len(srv.received), 2, "撃ち直していない")

    def test_a_retry_that_also_fails_falls_back(self):
        srv = StubServer(mode="429")
        self.addCleanup(srv.close)
        b = demo_bundle(base_url=srv.base_url)
        eng = de.make_engine("jev", b, self.meeting, retry_busy_sec=0.01)
        ans = eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})
        self.assertEqual(ans.backend, "rules(fallback)")
        self.assertEqual(len(srv.received), 2)

    def test_without_the_option_a_busy_signal_falls_back_at_once(self):
        # 🔴 会議中の既定。待たずに退避する（待つとカードが遅れる）
        srv = StubServer(mode="429")
        self.addCleanup(srv.close)
        b = demo_bundle(base_url=srv.base_url)
        eng = de.make_engine("jev", b, self.meeting)
        ans = eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})
        self.assertEqual(ans.backend, "rules(fallback)")
        self.assertEqual(len(srv.received), 1, "既定なのに撃ち直している")

    def test_a_non_busy_failure_is_not_retried(self):
        srv = StubServer(mode="500")
        self.addCleanup(srv.close)
        b = demo_bundle(base_url=srv.base_url)
        eng = de.make_engine("jev", b, self.meeting, retry_busy_sec=0.01)
        ans = eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})
        self.assertEqual(ans.backend, "rules(fallback)")
        self.assertEqual(len(srv.received), 1, "待っても無駄な失敗で撃ち直している")


class JevBackendTest(unittest.TestCase):
    """外の判定器との往復。**偽の判定器**が相手で、鍵は試験用の環境変数。"""

    def setUp(self):
        self.meeting = de.load_meeting_data(DEMO)
        self.masker = de.Masker(self.meeting.roster)
        self.prev = os.environ.get(TEST_KEY_ENV)
        os.environ[TEST_KEY_ENV] = "test-key-not-a-real-one"

    def tearDown(self):
        if self.prev is None:
            os.environ.pop(TEST_KEY_ENV, None)
        else:
            os.environ[TEST_KEY_ENV] = self.prev

    def test_it_refuses_to_run_without_a_destination(self):
        # 🔴 宛先は道具の中に無い。設定に無ければ起動しない（既定で外へ出ない）。
        with self.assertRaises(SystemExit):
            de.JevBackend(de.JevSettings(key_env=TEST_KEY_ENV))

    def test_a_missing_key_is_a_recoverable_error_not_a_crash(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        os.environ.pop(TEST_KEY_ENV, None)
        b = demo_bundle(base_url=srv.base_url)
        eng = de.JevBackend(b.jev, bundle=b)
        with self.assertRaises(de.DecisionError):
            eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})

    def test_the_three_answer_types_are_normalised(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        bundle = demo_bundle(base_url=srv.base_url)
        eng = de.JevBackend(bundle.jev, bundle=bundle)
        win = window(("guest", "URLは"), ("host", "お待ちください。確認します。"))
        state = de.build_state(win, self.masker)
        qs = de.build_questions(bundle, self.meeting, "host", self.masker)
        ans = eng.evaluate(state, qs)
        self.assertEqual(ans.backend, "jev")
        self.assertEqual(ans.by_id["q1_step"].value, "s2")
        self.assertAlmostEqual(ans.by_id["q1_step"].confidence, 0.72)
        # score 1.4 → 四捨五入して 1 番目のレベル = body
        self.assertEqual(ans.by_id["q2_phase"].value, "body")
        # noul には confidence が無い。校正用の確信度は max(p, 1-p) と決めてある
        self.assertEqual(ans.by_id["q4_lookup"].value, "yes")
        self.assertAlmostEqual(ans.by_id["q4_lookup"].confidence, 0.93)
        self.assertEqual(ans.usage["input_tokens"], 1000)

    def test_the_request_carries_the_key_and_the_masked_payload(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        bundle = demo_bundle(base_url=srv.base_url)
        eng = de.JevBackend(bundle.jev, bundle=bundle)
        win = window(("guest", "山田です。"), ("host", "Acmeさん、確認します。"))
        eng.evaluate(de.build_state(win, self.masker),
                     de.build_questions(bundle, self.meeting, "host", self.masker))
        sent = srv.received[0]
        self.assertEqual(sent["path"], "/v1/systemone")
        self.assertTrue(sent["auth"].startswith("Bearer "))
        for name in ("山田", "Acme"):
            self.assertNotIn(name, sent["body"], "送信の現物に名前が残っている")

    def test_a_dead_backend_raises_so_the_caller_can_fall_back(self):
        for mode in ("500", "garbage", "wrongtype"):
            srv = StubServer(mode=mode)
            self.addCleanup(srv.close)
            b = demo_bundle(base_url=srv.base_url)
            eng = de.JevBackend(b.jev, bundle=b)
            with self.assertRaises(de.DecisionError, msg=mode):
                eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})


class FallbackTest(unittest.TestCase):
    """A3: Jev を止めてもルール判定で最後まで通る。"""

    def setUp(self):
        self.meeting = de.load_meeting_data(DEMO)
        self.masker = de.Masker(self.meeting.roster)
        os.environ[TEST_KEY_ENV] = "test-key-not-a-real-one"
        self.addCleanup(lambda: os.environ.pop(TEST_KEY_ENV, None))

    def test_the_fallback_answers_and_says_who_answered(self):
        srv = StubServer(mode="500")
        self.addCleanup(srv.close)
        bundle = demo_bundle(base_url=srv.base_url)
        eng = de.make_engine("jev", bundle, self.meeting)
        win = window(("guest", "URLは"), ("host", "お待ちください。確認します。"))
        ans = eng.evaluate(de.build_state(win, self.masker),
                           de.build_questions(bundle, self.meeting, "host", self.masker))
        self.assertEqual(ans.backend, "rules(fallback)")
        self.assertIn("jev", ans.error)
        self.assertEqual(ans.by_id["q4_lookup"].value, "yes")

    def test_a_live_backend_is_not_tagged_as_a_fallback(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        bundle = demo_bundle(base_url=srv.base_url)
        eng = de.make_engine("jev", bundle, self.meeting)
        ans = eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})
        self.assertEqual(ans.backend, "jev")
        self.assertEqual(ans.error, "")


class LLMBackendTest(unittest.TestCase):
    """Jev が使えないときの中段。同じ問いの束を JSON で答えさせる。"""

    def setUp(self):
        self.meeting = de.load_meeting_data(DEMO)
        self.masker = de.Masker(self.meeting.roster)
        os.environ[TEST_KEY_ENV] = "test-key-not-a-real-one"
        self.addCleanup(lambda: os.environ.pop(TEST_KEY_ENV, None))

    def _engine(self, srv, **kw):
        b = demo_bundle(llm={"base_url": srv.base_url}, **kw)
        return de.LLMBackend(b.llm, bundle=b), b

    def _ask(self, eng, bundle, speaker="host"):
        win = window(("guest", "URLは"), ("host", "お待ちください。確認します。"))
        return eng.evaluate(de.build_state(win, self.masker),
                            de.build_questions(bundle, self.meeting, speaker, self.masker))

    def test_it_refuses_to_run_without_a_destination(self):
        with self.assertRaises(SystemExit):
            de.LLMBackend(de.LLMSettings(key_env=TEST_KEY_ENV))

    def test_the_three_types_come_back_in_the_same_shape_as_jev(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        eng, b = self._engine(srv)
        ans = self._ask(eng, b)
        self.assertEqual(ans.backend, "llm")
        self.assertEqual(ans.by_id["q1_step"].value, "s3")
        self.assertAlmostEqual(ans.by_id["q1_step"].confidence, 0.7)
        self.assertEqual(ans.by_id["q2_phase"].value, "closing")
        self.assertEqual(ans.by_id["q2_phase"].score, 2.0)       # levels の3番目
        self.assertEqual(ans.by_id["q4_lookup"].value, "yes")
        self.assertAlmostEqual(ans.by_id["q4_lookup"].p_yes, 0.9)
        self.assertEqual(ans.usage["input_tokens"], 700)

    def test_the_approximated_distribution_is_marked_as_such(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        eng, b = self._engine(srv)
        a = self._ask(eng, b).by_id["q1_step"]
        self.assertTrue(a.approx, "近似なのに印が無い")
        self.assertIn("approx", a.as_dict())
        self.assertAlmostEqual(sum(a.probabilities.values()), 1.0, places=2)
        self.assertTrue(all(v > 0 for v in a.probabilities.values()),
                        "0 を配ると「起こりえない」と読めてしまう")
        # Jev の本物の分布には印が付かない（混ぜて読まないための区別）
        self.assertNotIn("approx", de.parse_answer(
            "q", {"type": "choice", "choice": "a",
                  "probabilities": {"a": 1.0}, "confidence": 1.0}, None).as_dict())

    def test_the_prompt_carries_the_allowed_values_and_the_masked_state(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        eng, b = self._engine(srv)
        win = window(("guest", "山田です。"), ("host", "Acmeさん、確認します。"))
        eng.evaluate(de.build_state(win, self.masker),
                     de.build_questions(b, self.meeting, "host", self.masker))
        sent = srv.received[0]
        self.assertTrue(sent["path"].endswith("/chat/completions"))
        self.assertTrue(sent["auth"].startswith("Bearer "))
        self.assertIn("allowed values", sent["body"])
        self.assertIn("q8_commitment", sent["body"])
        for name in ("山田", "Acme"):
            self.assertNotIn(name, sent["body"], "送信の現物に名前が残っている")

    def test_a_value_outside_the_allowed_list_is_dropped_not_rounded(self):
        srv = StubServer(llm_mode="custom", llm_text=json.dumps(
            {"q1_step": {"value": "まったく別の段", "confidence": 0.9},
             "q4_lookup": {"value": "yes", "confidence": 0.8}}))
        self.addCleanup(srv.close)
        eng, b = self._engine(srv)
        ans = self._ask(eng, b)
        self.assertNotIn("q1_step", ans.by_id, "選択肢に無い値を丸めて採用している")
        self.assertEqual(ans.by_id["q4_lookup"].value, "yes")

    def test_broken_json_raises_so_the_chain_moves_on(self):
        for text in ("これは JSON ではありません", "{\"q1_step\": ", "[1,2,3]",
                     json.dumps({"q1_step": {"value": "ありえない"}})):
            srv = StubServer(llm_mode="custom", llm_text=text)
            self.addCleanup(srv.close)
            eng, b = self._engine(srv)
            with self.assertRaises(de.DecisionError, msg=text[:20]):
                self._ask(eng, b)

    def test_a_fenced_json_block_is_still_read(self):
        srv = StubServer(llm_mode="custom",
                         llm_text="```json\n" + json.dumps(LLM_ANSWER) + "\n```")
        self.addCleanup(srv.close)
        eng, b = self._engine(srv)
        self.assertEqual(self._ask(eng, b).by_id["q1_step"].value, "s3")


class ChainTest(unittest.TestCase):
    """退避の鎖: jev → llm → rules。どれが答えたかが記録に残ること。"""

    def setUp(self):
        self.meeting = de.load_meeting_data(DEMO)
        self.masker = de.Masker(self.meeting.roster)
        os.environ[TEST_KEY_ENV] = "test-key-not-a-real-one"
        self.addCleanup(lambda: os.environ.pop(TEST_KEY_ENV, None))
        self.quiet = lambda m: None

    def _run(self, srv, kind="jev", **kw):
        b = demo_bundle(base_url=srv.base_url, llm={"base_url": srv.base_url}, **kw)
        eng = de.make_engine(kind, b, self.meeting, note=self.quiet)
        win = window(("guest", "URLは"), ("host", "お待ちください。確認します。"))
        return eng.evaluate(de.build_state(win, self.masker),
                            de.build_questions(b, self.meeting, "host", self.masker))

    def test_jev_429_hands_over_to_the_llm(self):
        srv = StubServer(mode="429")
        self.addCleanup(srv.close)
        ans = self._run(srv)
        # 段はモデル名まで名乗る（同じ鎖に別のモデルを何段も置けるので、
        # どのモデルが答えたのかが分からないと記録の意味が無い）
        self.assertTrue(ans.backend.startswith("llm"), ans.backend)
        self.assertIn("stub-llm", ans.backend)
        self.assertTrue(ans.backend.endswith("(fallback)"), ans.backend)
        self.assertIn("429", ans.error)
        self.assertEqual(ans.by_id["q1_step"].value, "s3")

    def test_when_the_llm_is_down_too_it_lands_on_rules(self):
        srv = StubServer(mode="429", llm_mode="down")
        self.addCleanup(srv.close)
        ans = self._run(srv)
        self.assertEqual(ans.backend, "rules(fallback)")
        self.assertIn("jev", ans.error)
        self.assertIn("llm", ans.error)
        self.assertEqual(ans.by_id["q4_lookup"].value, "yes")   # ルールでも答えは出る

    def test_broken_json_from_the_llm_lands_on_rules(self):
        srv = StubServer(mode="429", llm_mode="custom", llm_text="申し訳ありませんが")
        self.addCleanup(srv.close)
        ans = self._run(srv)
        self.assertEqual(ans.backend, "rules(fallback)")
        self.assertIn("llm", ans.error)

    def test_a_healthy_jev_never_reaches_the_llm(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        ans = self._run(srv)
        self.assertEqual(ans.backend, "jev")
        self.assertEqual(ans.error, "")
        self.assertFalse([r for r in srv.received
                          if r["path"].endswith("/chat/completions")])

    def test_backend_llm_starts_the_chain_at_the_llm(self):
        # LLM 単独の成績を Jev と並べて測るための入口
        srv = StubServer()
        self.addCleanup(srv.close)
        ans = self._run(srv, kind="llm")
        self.assertTrue(ans.backend.startswith("llm"), ans.backend)
        self.assertFalse(ans.backend.endswith("(fallback)"), ans.backend)
        self.assertFalse([r for r in srv.received
                          if r["path"].endswith("/systemone")], "jev を叩いている")

    def test_an_unconfigured_middle_link_is_dropped_but_the_asked_one_is_not(self):
        srv = StubServer(mode="429")
        self.addCleanup(srv.close)
        b = demo_bundle(base_url=srv.base_url)          # llm は base_url 空のまま
        eng = de.make_engine("jev", b, self.meeting, note=self.quiet)
        win = window(("guest", "はい"), ("host", "確認します。"))
        ans = eng.evaluate(de.build_state(win, self.masker),
                           de.build_questions(b, self.meeting, "host", self.masker))
        self.assertEqual(ans.backend, "rules(fallback)")
        # 頼まれた実装が未設定なら、黙って代わりを立てずに止まる
        with self.assertRaises(SystemExit):
            de.make_engine("llm", demo_bundle(), self.meeting, note=self.quiet)

    def test_two_llm_stages_are_tried_in_order(self):
        # 退避先の LLM は複数書ける。1つ目が落ちたら2つ目へ。
        srv = StubServer(mode="429", llm_mode="down")      # jev も llm も落ちる
        self.addCleanup(srv.close)
        b = demo_bundle(base_url=srv.base_url, llm={"base_url": srv.base_url},
                        chain=["jev", "llm:model-a", "llm:model-b", "rules"])
        self.assertEqual([s.name for s in b.fallback_chain],
                         ["jev", "llm", "llm", "rules"])
        self.assertEqual(b.fallback_chain[1].model, "model-a")
        self.assertEqual(b.fallback_chain[2].model, "model-b")
        eng = de.make_engine("jev", b, self.meeting, note=self.quiet)
        self.assertEqual([e.name for e in eng.engines],
                         ["jev", "llm:model-a", "llm:model-b", "rules"])
        ans = eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})
        self.assertEqual(ans.backend, "rules(fallback)")
        # 両方のモデルを試した跡が残る（どちらで落ちたか分かること）
        self.assertIn("model-a", ans.error)
        self.assertIn("model-b", ans.error)

    def test_the_second_llm_answers_when_the_first_is_down(self):
        srv = StubServer(mode="429")
        self.addCleanup(srv.close)
        # 1段目は宛先を持たない（＝設定されていないので外れる）
        b = demo_bundle(base_url=srv.base_url, llm={"base_url": srv.base_url},
                        chain=["jev", "llm:model-a", "rules"])
        eng = de.make_engine("jev", b, self.meeting, note=self.quiet)
        ans = eng.evaluate({"recent_utterances": []}, {"q4_lookup": {"type": "noul"}})
        self.assertEqual(ans.backend, "llm:model-a(fallback)")
        body = json.loads([r for r in srv.received
                           if r["path"].endswith("/chat/completions")][0]["body"])
        self.assertEqual(body["model"], "model-a", "段のモデルが送られていない")

    def test_a_stage_can_carry_its_own_timeout(self):
        b = demo_bundle(chain=["jev", {"llm": "model-a", "timeout_sec": 1.5}, "rules"])
        self.assertEqual(b.fallback_chain[1].timeout_sec, 1.5)
        self.assertIn("1.5秒", b.chain_label)

    def test_llm_model_override_names_the_model_being_measured(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        b = demo_bundle(base_url=srv.base_url, llm={"base_url": srv.base_url},
                        chain=["jev", "llm:model-a", "llm:model-b", "rules"])
        eng = de.make_engine("llm", b, self.meeting, note=self.quiet,
                             llm_model="model-z")
        # 測ると名指ししたモデル1つ + rules。途中で入れ替わらない
        self.assertEqual([e.name for e in eng.engines], ["llm:model-z", "rules"])

    def test_the_shipped_default_chain_is_jev_haiku_rules(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest_not_used = True
            b = None
        else:
            b = de.load_bundle(EXAMPLE_BUNDLE)
        if b is None:
            # yaml が無い機体でも、既定は**コードの側**にあるので確かめられる
            b = de.bundle_from_dict({"questions": []})
        names = [s.name for s in b.fallback_chain]
        self.assertEqual(names, ["jev", "llm", "rules"])
        self.assertEqual(b.fallback_chain[1].model, "anthropic/claude-haiku-4.5")

    def test_the_chain_always_ends_at_rules(self):
        b = de.bundle_from_dict({"fallback_chain": ["jev"], "questions": []})
        self.assertEqual(b.fallback_chain[-1].name, "rules")
        with self.assertRaises(SystemExit):
            de.bundle_from_dict({"fallback_chain": ["jev", "haiku"], "questions": []})


class ReplayTest(unittest.TestCase):
    """再生ハーネスを丸ごと1回。記録・集計・費用・送信なしを確かめる。"""

    TRANSCRIPT = [
        {"ts": "2026-01-01T10:00:00", "speaker": "guest", "text": "山田です。よろしくお願いします。"},
        {"ts": "2026-01-01T10:00:10", "speaker": "host",
         "text": "今日決めたいことは3つです。順にまいります。"},
        {"ts": "2026-01-01T10:01:00", "speaker": "guest", "text": "検証環境の入口はどこでしたか。"},
        {"ts": "2026-01-01T10:01:10", "speaker": "host",
         "text": "ちょっとお待ちください。確認します。"},
        {"ts": "2026-01-01T10:40:00", "speaker": "host", "text": "では失礼します。ありがとうございました。"},
    ]

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.dir = pathlib.Path(self.td.name)
        self.tr = self.dir / "transcript.jsonl"
        self.tr.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in self.TRANSCRIPT) + "\n",
            encoding="utf-8")
        self.out = self.dir / "decisions.jsonl"

    def run_replay(self, *extra):
        cmd = [sys.executable, str(SCRIPTS / "replay_eval.py"),
               "--transcript", str(self.tr), "--meeting", str(DEMO),
               "--out", str(self.out), *extra]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           cwd=self.td.name)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        return p.stdout

    def test_every_utterance_lands_in_the_log_with_its_line_number(self):
        self.run_replay("--backend", "rules")
        recs = [json.loads(x) for x in self.out.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["utterance_id"] for r in recs], [1, 2, 3, 4, 5])
        self.assertTrue(all(r["backend"] == "rules" for r in recs))
        self.assertTrue(all(r["state"]["recent_utterances"] for r in recs))
        self.assertTrue(all(r["answers"] for r in recs))
        # 名簿の名前は記録にも残らない（記録はそのまま「送った物」なので）
        self.assertNotIn("山田", self.out.read_text(encoding="utf-8"))

    def test_the_summary_reports_accuracy_from_a_label_file(self):
        labels = self.dir / "labels.csv"
        labels.write_text(
            "utterance_id,q,gold\n2,q1_step,s1\n4,q4_lookup,yes\n5,q4_lookup,no\n",
            encoding="utf-8")
        out = self.run_replay("--backend", "rules", "--labels", str(labels))
        self.assertIn("的中率", out)
        self.assertIn("q4_lookup", out)
        self.assertIn("再現率", out)
        self.assertIn("確信度ごとの的中率", out)
        self.assertIn("p50", out)

    def test_dry_run_sends_nothing_and_shows_the_key_map(self):
        out = self.run_replay("--backend", "jev", "--dry-run")
        self.assertIn("1件も送信しません", out)
        self.assertIn("q1_step", out)
        self.assertFalse(self.out.exists(), "--dry-run が記録を書いている")

    def test_sending_without_a_roster_is_refused(self):
        # A4 の裏側。名簿が空のまま外へ送るのは、手違いでは通らないようにする。
        with tempfile.TemporaryDirectory() as td:
            bare = pathlib.Path(td)
            # meeting.json に相手の呼び方はある（＝保険は効く）が roster.txt は無い。
            # 保険が効いたぶんで関門が黙って開かないことを、ここで確かめる。
            (bare / "meeting.json").write_text(
                json.dumps({"counterpart": "テスト商事さん"}, ensure_ascii=False),
                encoding="utf-8")
            cmd = [sys.executable, str(SCRIPTS / "replay_eval.py"),
                   "--transcript", str(self.tr), "--meeting", str(bare),
                   "--out", str(self.out), "--backend", "jev"]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                               cwd=self.td.name)
            self.assertNotEqual(p.returncode, 0, "名簿なしで送ろうとしたのに通った")
            self.assertIn("roster.txt がありません", p.stdout + p.stderr)
            self.assertFalse(self.out.exists())
            # ...そして --dry-run は名簿が無くても通る（1件も送らないため）
            p2 = subprocess.run(cmd + ["--dry-run"], capture_output=True, text=True,
                                timeout=120, cwd=self.td.name)
            self.assertEqual(p2.returncode, 0, p2.stderr[-800:])

    def test_ids_thins_the_calls_but_not_the_context(self):
        # ① 呼び出しは減らすが、窓の文脈は逐語全体から取る。
        ids = self.dir / "ids.txt"
        ids.write_text("4\n5  # 注記は無視\n999\n", encoding="utf-8")
        out = self.run_replay("--backend", "rules", "--ids", str(ids))
        recs = [json.loads(x) for x in self.out.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["utterance_id"] for r in recs], [4, 5])
        self.assertIn("逐語に無い", out, "--ids の余りを黙って捨てている")
        # 4番の窓には、判定していない1〜3番が文脈として入っている
        w = recs[0]["state"]["recent_utterances"]
        self.assertGreater(len(w), 1, "間引いたら窓まで痩せている")
        self.assertIn("今日決めたいことは3つです。順にまいります。",
                      [u["text"] for u in w])

    def test_pace_spaces_the_calls_out(self):
        # ② 間隔。無料枠のレート制限を避けるため
        import time as _t
        t0 = _t.monotonic()
        self.run_replay("--backend", "rules", "--pace", "0.2")
        spent = _t.monotonic() - t0
        # 5発話 → 間隔は4回ぶん ≒ 0.8秒
        self.assertGreater(spent, 0.6, f"間隔が効いていない({spent:.2f}s)")

    def test_retry_on_429_needs_a_pace_to_wait_for(self):
        cmd = [sys.executable, str(SCRIPTS / "replay_eval.py"),
               "--transcript", str(self.tr), "--meeting", str(DEMO),
               "--out", str(self.out), "--backend", "rules", "--retry-on-429"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           cwd=self.td.name)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--pace", p.stdout + p.stderr)

    def test_a_label_for_a_question_never_asked_is_out_of_scope(self):
        # ⑤ q4/q8 は進行役の発話にしか聞かない。相手の発話に付いた正解は
        #    不正解ではなく「対象外」——分母に入れず、件数を画面に出す。
        labels = self.dir / "labels.csv"
        # 1番と3番は相手の発話（q4 は聞いていない）、4番は進行役
        labels.write_text(
            "utterance_id,q,gold\n1,q4_lookup,no\n3,q4_lookup,no\n4,q4_lookup,yes\n",
            encoding="utf-8")
        out = self.run_replay("--backend", "rules", "--labels", str(labels))
        self.assertIn("対象外", out)
        row = next(l for l in out.splitlines() if l.startswith("q4_lookup"))
        # 正解付き=1（進行役の4番だけ）／対象外=2（相手の1番と3番）
        self.assertRegex(row, r"q4_lookup\s+\d+\s+1\s+2\s")
        self.assertIn("100.0%", row, "聞いた1件は当たっているはず")

    def test_backend_llm_runs_through_the_cli_and_is_recorded(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        d = json.loads(json.dumps(BUNDLE_DICT))
        d["llm"]["base_url"] = srv.base_url
        d["fallback_chain"] = ["llm", "rules"]
        bp = self.dir / "decisions.json"
        bp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.environ[TEST_KEY_ENV] = "test-key-not-a-real-one"
        self.addCleanup(lambda: os.environ.pop(TEST_KEY_ENV, None))
        out = self.run_replay("--backend", "llm",
                              "--decisions", str(bp.with_suffix(".yaml")))
        self.assertIn("llm:stub-llm=5", out, out[-600:])
        recs = [json.loads(x) for x in self.out.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all(r["backend"].startswith("llm") for r in recs))
        self.assertTrue(recs[0]["answers"]["q1_step"]["approx"])

    def test_the_roster_gate_covers_the_llm_too(self):
        # rules 以外はどれも外へ出る。jev だけ見張ると llm を足した日に穴が開く。
        with tempfile.TemporaryDirectory() as td:
            bare = pathlib.Path(td)
            (bare / "meeting.json").write_text("{}", encoding="utf-8")
            for backend in ("jev", "llm"):
                p = subprocess.run(
                    [sys.executable, str(SCRIPTS / "replay_eval.py"),
                     "--transcript", str(self.tr), "--meeting", str(bare),
                     "--out", str(self.out), "--backend", backend],
                    capture_output=True, text=True, timeout=120, cwd=self.td.name)
                self.assertNotEqual(p.returncode, 0, backend)
                self.assertIn("roster.txt がありません", p.stdout + p.stderr, backend)

    def test_the_cost_comes_out_of_usage(self):
        srv = StubServer()
        self.addCleanup(srv.close)
        bundle_path = self.dir / "decisions.json"   # yaml が無くても読める形で渡す
        d = json.loads(json.dumps(BUNDLE_DICT))
        d["jev"]["base_url"] = srv.base_url
        bundle_path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        env_line = f"{TEST_KEY_ENV}=test-key-not-a-real-one"
        os.environ[TEST_KEY_ENV] = "test-key-not-a-real-one"
        self.addCleanup(lambda: os.environ.pop(TEST_KEY_ENV, None))
        out = self.run_replay("--backend", "jev",
                              "--decisions", str(bundle_path.with_suffix(".yaml")))
        self.assertIn("入力 5,000 トークン", out, env_line)   # 5発話 × 1000
        self.assertIn("概算 0.0100 USD", out)               # 5000/1e6 × 2.0
        self.assertIn("jev=5", out)


if __name__ == "__main__":
    unittest.main()
