#!/usr/bin/env python3
"""viewer2 の状態計算と HTTP 経路の回帰テスト（標準ライブラリだけ・外へは出ない）。

会議の道具は「会議の日にしか動かせない」ことになりがちで、そうなると壊れたことに
本番まで気づけない。ここで見るのは、実際に会議で焼けた仕様そのもの:

  1. 「済」は再読込しても復活しない (サーバ側 dismissed.jsonl に残る)
  2. 呼びかけへの回答 (call) はカード列の先頭に固定される
  3. mode=start より前のカードは出ない (リハの発話が本番に積み上がらない)
  4. 自動で消えるのは card_policy.auto_dismiss_kinds に挙げた種別だけ
  5. 資料棚の一覧が出る / `..%2f` の遡上は 404
  6. 合言葉は共有窓 (/stage/*) にも手元画面の HTML にも出ない (叩いたときだけ読む)
  7. 舞台のボタンは meeting.json の stage.order の順・その分だけ
  8. layout (columns / rows / auto) が HTML に効く
  9. 設定の解決順 = 会議フォルダ → 個別env → 同梱の例

実行:
    python3 -m unittest discover -s templates/skills/meeting-copilot/tests -v
ネットワークは 127.0.0.1 のみ・書き込みは tempfile の中だけ。
"""
from __future__ import annotations

import http.server
import importlib
import json
import os
import pathlib
import shutil
import socketserver
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime, timedelta

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
CONFIG = SKILL / "config"
EXAMPLE_MEETING = CONFIG / "example_meeting"

sys.path.insert(0, str(SCRIPTS))

MEETLIVE_ENV = ("MEETLIVE_MEETING", "MEETLIVE_DIR", "MEETLIVE_CREDS_FILE", "MEETLIVE_DOCS",
                "MEETLIVE_AGENDA", "MEETLIVE_SCRIPT", "MEETLIVE_STAGE", "MEETLIVE_PHRASEBOOK",
                "MEETLIVE_LAYOUT", "MEETLIVE_CALL_WORDS", "MEETLIVE_KNOWLEDGE_DIR")

SECRET = "kaiwai-no-aikotoba-999"          # この文字列が画面に漏れないことを見る
CREDS_MD = f"""# 合言葉（テスト用の架空）

| 用途 | URL | 合言葉 |
|---|---|---|
| 管理画面 | https://example.com/admin | `{SECRET}` |
"""


def load_viewer(meeting: pathlib.Path, state: pathlib.Path, **env):
    """環境を差し替えて viewer2 を読み直す (設定は import 時に解決されるため)。"""
    for k in MEETLIVE_ENV:
        os.environ.pop(k, None)
    os.environ["MEETLIVE_MEETING"] = str(meeting)
    os.environ["MEETLIVE_DIR"] = str(state)
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(v)
    for name in ("viewer2", "mode_signal", "meetlive_config"):
        sys.modules.pop(name, None)
    return importlib.import_module("viewer2")


class Serving:
    """viewer2 のハンドラを 127.0.0.1 の空きポートで動かす (プロセスを起こさない)。"""

    def __init__(self, viewer2, outdir, start_epoch, total_min=None):
        agenda = viewer2.load_agenda(viewer2.AGENDA_PATH)
        blocks = viewer2.build_blocks(agenda, viewer2.parse_script(viewer2.SCRIPT_PATH))
        handler = viewer2.make_handler(outdir, agenda, blocks, start_epoch, total_min)

        class S(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.srv = S(("127.0.0.1", 0), handler)
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def get(self, path, timeout=10):
        with urllib.request.urlopen(self.base + path, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")

    def status(self, path, timeout=10):
        try:
            code, _ = self.get(path, timeout)
            return code
        except urllib.error.HTTPError as e:      # noqa: F821 — urllib.error は下で import
            return e.code

    def json(self, path):
        return json.loads(self.get(path)[1])

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(timeout=5)


import urllib.error  # noqa: E402 — Serving.status が使う


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


class ViewerCase(unittest.TestCase):
    """会議フォルダ・状態Dirを毎回作り直す土台。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="meetlive_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.meeting = self.tmp / "meeting"
        shutil.copytree(EXAMPLE_MEETING, self.meeting)
        self.state = self.tmp / "state"
        self.state.mkdir()
        self.creds = self.tmp / "creds.md"
        self.creds.write_text(CREDS_MD, encoding="utf-8")
        self.now = datetime.now()
        self.start_epoch = (self.now - timedelta(minutes=5)).timestamp()
        self._saved_env = {k: os.environ.get(k) for k in MEETLIVE_ENV}
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # ---- 材料を書く ----------------------------------------------------
    def write_meeting_json(self, **patch):
        p = self.meeting / "meeting.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw.update(patch)
        p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_transcript(self, rows):
        with (self.state / "transcript.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def write_cards(self, cards):
        with (self.state / "cards.jsonl").open("w", encoding="utf-8") as f:
            for c in cards:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    def six_cards(self, start: datetime):
        """会議で出る6枚 (call を1枚含む)。すべて mode=start より後。"""
        kinds = [("topic", "いまは【1】現状の確認です。"),
                 ("call", "手元の数字では12,000件です。正式にはお見積りに載せます。"),
                 ("premise_ok", "既知: 相手の担当は1名。"),
                 ("premise_new", "新情報: 切替日は翌月2営業日を希望。"),
                 ("reply", "「本番だけ先に動かして、次の弾で広げます」"),
                 ("topic", "【2】へ移りました。")]
        out = []
        for i, (kind, line) in enumerate(kinds):
            out.append({"ts": iso(start + timedelta(seconds=10 + i * 10)),
                        "kind": kind, "lines": [line], "confidence": "high"})
        return out

    def viewer(self, **env):
        return load_viewer(self.meeting, self.state, MEETLIVE_CREDS_FILE=self.creds, **env)

    def serve(self, viewer2, total_min=None):
        s = Serving(viewer2, self.state, self.start_epoch, total_min)
        self.addCleanup(s.close)
        return s


# ---------------------------------------------------------------- 1・2・3


class TestCardStack(ViewerCase):
    def test_stack_pins_call_and_hides_pre_start_cards(self):
        """カード列: 6枚出る・call が先頭・mode=start より前のカードは出ない。"""
        start = self.now - timedelta(minutes=3)
        rehearsal = {"ts": iso(start - timedelta(minutes=30)), "kind": "topic",
                     "lines": ["リハの残骸。本番に出てはいけない。"], "confidence": "high"}
        self.write_cards([rehearsal] + self.six_cards(start))
        self.write_transcript([
            {"ts": iso(start - timedelta(minutes=31)), "speaker": "host",
             "text": "リハをします"},
            {"ts": iso(start), "type": "mode", "mode": "start", "src": "button"},
            {"ts": iso(start + timedelta(seconds=5)), "speaker": "host",
             "text": "まず現状を確認させてください"},
        ])
        v = self.viewer()
        st = v.build_state(self.state, v.load_agenda(v.AGENDA_PATH), self.start_epoch)

        self.assertEqual(len(st["cards"]), 6, "6枚そのまま出る(自動で消えない)")
        self.assertEqual(st["cards"][0]["kind"], "call", "call は先頭に固定される")
        self.assertTrue(st["cards"][0]["pin"])
        texts = " ".join(l for c in st["cards"] for l in c["lines"])
        self.assertNotIn("リハの残骸", texts, "mode=start より前のカードは出ない")

    def test_dismiss_is_persistent_and_undoable(self):
        """「済」はサーバ側に残る = 再読込で復活しない。「戻す」で履歴から戻る。"""
        start = self.now - timedelta(minutes=3)
        cards = self.six_cards(start)
        self.write_cards(cards)
        self.write_transcript([{"ts": iso(start), "type": "mode", "mode": "start"}])
        v = self.viewer()
        s = self.serve(v)

        key = cards[0]["ts"]
        body = s.json("/card/dismiss?key=" + urllib.request.quote(key))
        self.assertTrue(body["ok"])

        st = s.json("/state")
        self.assertEqual(len(st["cards"]), 5, "消したぶんだけ減る")
        self.assertNotIn(key, [c["key"] for c in st["cards"]])
        self.assertIn(key, [c["key"] for c in st["history"]], "履歴には残る")

        # 状態を作り直しても(=再読込しても)復活しない
        st2 = v.build_state(self.state, v.load_agenda(v.AGENDA_PATH), self.start_epoch)
        self.assertNotIn(key, [c["key"] for c in st2["cards"]])
        self.assertTrue((self.state / "dismissed.jsonl").exists())

        s.json("/card/undismiss?key=" + urllib.request.quote(key))
        st3 = s.json("/state")
        self.assertIn(key, [c["key"] for c in st3["cards"]], "「戻す」で戻る")


# ---------------------------------------------------------------- 4


class TestAutoDismissKinds(ViewerCase):
    def _state_with_old_cards(self, kinds):
        """十分に古い(ttlを超えた)カードを種別ぶん並べた状態を作る。"""
        start = self.now - timedelta(hours=2)
        cards = [{"ts": iso(start + timedelta(seconds=i)), "kind": k,
                  "lines": [f"{k} のカード"], "confidence": "high"}
                 for i, k in enumerate(kinds)]
        self.write_cards(cards)
        self.write_transcript([{"ts": iso(start), "type": "mode", "mode": "start"}]
                              + [{"ts": iso(start + timedelta(minutes=1 + i)),
                                  "speaker": "host", "text": f"発話{i}"} for i in range(20)])
        return cards

    def test_only_listed_kinds_disappear(self):
        """既定 (warn / premise_warn) だけが自動で消え、他は残る。"""
        self._state_with_old_cards(["warn", "premise_warn", "topic", "reply"])
        v = self.viewer()
        st = v.build_state(self.state, v.load_agenda(v.AGENDA_PATH), self.start_epoch)
        kinds = [c["kind"] for c in st["cards"] if not c.get("auto")]
        self.assertNotIn("warn", kinds)
        self.assertNotIn("premise_warn", kinds)
        self.assertIn("topic", kinds)
        self.assertIn("reply", kinds)

    def test_policy_is_configurable(self):
        """auto_dismiss_kinds を meeting.json で変えると、消える種別が変わる。"""
        self._state_with_old_cards(["warn", "topic", "reply"])
        self.write_meeting_json(card_policy={"auto_dismiss_kinds": ["reply"]})
        v = self.viewer()
        st = v.build_state(self.state, v.load_agenda(v.AGENDA_PATH), self.start_epoch)
        kinds = [c["kind"] for c in st["cards"] if not c.get("auto")]
        self.assertIn("warn", kinds, "警報も、挙げなければ手で消すまで残る")
        self.assertNotIn("reply", kinds, "挙げた種別だけが自動で消える")


# ---------------------------------------------------------------- 5


class TestDocShelf(ViewerCase):
    def test_docs_are_listed_from_the_meeting_folder(self):
        v = self.viewer()
        s = self.serve(v)
        docs = s.json("/docs")
        names = sorted(d["name"] for d in docs)
        self.assertEqual(len(docs), 2, f"デモ会議の docs/ は2件のはず: {names}")
        code, html = s.get("/doc/" + urllib.request.quote(names[0]))
        self.assertEqual(code, 200)
        self.assertIn("<html", html)

    def test_path_traversal_is_404(self):
        v = self.viewer()
        s = self.serve(v)
        for evil in ("/doc/..%2fmeeting.json",
                     "/doc/..%2f..%2f..%2fetc%2fpasswd",
                     "/doc/%2Fetc%2Fpasswd",
                     "/doc/sub%2fnested.md"):
            self.assertEqual(s.status(evil), 404, f"棚の外へ出られてはいけない: {evil}")

    def test_only_allowed_suffixes(self):
        (self.meeting / "docs" / "secret.env").write_text("TOKEN=x", encoding="utf-8")
        v = self.viewer()
        s = self.serve(v)
        self.assertNotIn("secret.env", [d["name"] for d in s.json("/docs")])
        self.assertEqual(s.status("/doc/secret.env"), 404)


# ---------------------------------------------------------------- 6


class TestCredsNeverLeak(ViewerCase):
    def test_secret_is_absent_from_page_and_stage(self):
        """合言葉は /creds を叩いたときだけ読む。HTML にも共有窓にも出ない。"""
        v = self.viewer()
        s = self.serve(v)

        _, page = s.get("/")
        self.assertNotIn(SECRET, page, "手元画面の HTML に埋め込んではいけない")
        self.assertIn("🔑", page, "鍵パネルのボタンは出る")

        for path in ("/stage", "/stage/blank", "/stage/state"):
            _, body = s.get(path)
            self.assertNotIn(SECRET, body, f"共有窓に出てはいけない: {path}")

        creds = s.json("/creds")
        self.assertTrue(creds["ok"])
        self.assertEqual(creds["rows"][0]["secret"], SECRET, "叩いたときだけ返る")

    def test_no_creds_file_does_not_break(self):
        v = load_viewer(self.meeting, self.state)      # MEETLIVE_CREDS_FILE 無し
        s = self.serve(v)
        creds = s.json("/creds")
        self.assertFalse(creds["ok"])
        self.assertIn("error", creds)
        self.assertEqual(s.status("/state"), 200, "鍵パネル無しでも画面は動く")


# ---------------------------------------------------------------- 7


class TestStageOrder(ViewerCase):
    def test_order_comes_from_meeting_json(self):
        v = self.viewer()
        s = self.serve(v)
        st = s.json("/state")
        self.assertEqual(st["stage_set"]["order"], ["blank", "agenda", "slides", "free"])
        self.assertEqual(st["stage_set"]["label"], "デモ（架空）")
        _, page = s.get("/")
        self.assertNotIn('"res": "demo"', page, "order に無いボタンは画面に出ない")

    def test_urls_come_from_stage_urls_json(self):
        """個々の URL は走行中に差し込める stage_urls.json が勝つ (order は meeting.json)。"""
        (self.state / "stage_urls.json").write_text(
            json.dumps({"agenda": "https://example.com/changed",
                        "set_label": "これは負ける", "order": ["blank"]}),
            encoding="utf-8")
        v = self.viewer()
        s = self.serve(v)
        st = s.json("/state")
        self.assertEqual(st["stage_set"]["order"], ["blank", "agenda", "slides", "free"],
                         "order は meeting.json が勝つ")
        self.assertEqual(st["stage_set"]["label"], "デモ（架空）")
        self.assertEqual(v.res_url("agenda"), "https://example.com/changed",
                         "URL は stage_urls.json が勝つ")

    def test_stage_set_switches_resource(self):
        v = self.viewer()
        s = self.serve(v)
        body = s.json("/stage/set?res=slides")
        self.assertTrue(body["ok"])
        self.assertEqual(body["res"], "slides")
        self.assertFalse(s.json("/stage/set?res=nonexistent")["ok"])


# ---------------------------------------------------------------- 8


class TestLayout(ViewerCase):
    def test_columns_and_rows(self):
        v = self.viewer()                     # デモ会議は layout: columns
        s = self.serve(v)
        _, page = s.get("/")
        self.assertIn('<body data-layout="columns">', page)
        self.assertEqual(s.json("/state")["layout"], "columns")
        # ?layout= はその1枚だけの一時切替
        self.assertIn('<body data-layout="rows">', s.get("/?layout=rows")[1])
        self.assertIn('<body data-layout="columns">', s.get("/?layout=nonsense")[1])

    def test_layout_from_meeting_json(self):
        self.write_meeting_json(layout="rows")
        v = self.viewer()
        s = self.serve(v)
        self.assertIn('<body data-layout="rows">', s.get("/")[1])
        self.assertEqual(s.json("/state")["layout"], "rows")

    def test_auto_keeps_the_portrait_fallback(self):
        self.write_meeting_json(layout="auto")
        v = self.viewer()
        s = self.serve(v)
        _, page = s.get("/")
        self.assertIn('<body data-layout="auto">', page)
        self.assertIn('body[data-layout="auto"] #main{flex-direction:column}', page,
                      "auto のときだけ縦置きで縦積みへ退避する規則が要る")


# ---------------------------------------------------------------- 9


class TestConfigResolution(ViewerCase):
    """解決順 = 会議フォルダ → 個別env(後方互換) → 同梱の例。"""

    def test_meeting_folder_wins_over_env(self):
        other = self.tmp / "old_agenda.json"
        other.write_text(json.dumps({"steps": [{"id": "x", "title": "前の案件の段"}]}),
                         encoding="utf-8")
        v = self.viewer(MEETLIVE_AGENDA=other)
        self.assertEqual(v.AGENDA_PATH, self.meeting / "agenda_steps.json",
                         "古い個別env が残っていても会議フォルダが勝つ")

    def test_env_used_when_meeting_folder_lacks_the_file(self):
        (self.meeting / "agenda_steps.json").unlink()
        other = self.tmp / "env_agenda.json"
        shutil.copy(EXAMPLE_MEETING / "agenda_steps.json", other)
        v = self.viewer(MEETLIVE_AGENDA=other)
        self.assertEqual(v.AGENDA_PATH, other)

    def test_falls_back_to_bundled_example_not_to_real_data(self):
        for k in MEETLIVE_ENV:
            os.environ.pop(k, None)
        os.environ["MEETLIVE_DIR"] = str(self.state)
        for name in ("viewer2", "mode_signal", "meetlive_config"):
            sys.modules.pop(name, None)
        v = importlib.import_module("viewer2")
        self.assertEqual(v.AGENDA_PATH, CONFIG / "agenda_steps.example.json")
        self.assertEqual(v.SCRIPT_PATH, CONFIG / "talk_script.example.md")

    def test_missing_meeting_folder_stops_instead_of_falling_back(self):
        os.environ["MEETLIVE_MEETING"] = str(self.tmp / "does_not_exist")
        os.environ["MEETLIVE_DIR"] = str(self.state)
        for name in ("viewer2", "mode_signal", "meetlive_config"):
            sys.modules.pop(name, None)
        with self.assertRaises(SystemExit):
            importlib.import_module("viewer2")

    def test_missing_env_file_stops_instead_of_falling_back(self):
        (self.meeting / "agenda_steps.json").unlink()
        with self.assertRaises(SystemExit):
            self.viewer(MEETLIVE_AGENDA=self.tmp / "nope.json")


# ---------------------------------------------------------------- 稼働ライン


class TestHealthLine(ViewerCase):
    def test_silence_is_reported_without_crashing(self):
        """心拍ファイルが無くても落ちない。「心拍なし」と言い切る。"""
        v = self.viewer()
        s = self.serve(v)
        h = s.json("/state")["health"]
        self.assertFalse(h["heartbeat"]["ok"])
        self.assertIn("心拍なし", h["heartbeat_text"])
        self.assertIn("材料が無ければカードは出ません", h["note"])
        self.assertIn("材料が無ければカードは出ません", s.get("/")[1])

    def test_fresh_heartbeat_is_alive(self):
        (self.state / "heartbeat.json").write_text(
            json.dumps({"ts": iso(datetime.now()), "role": "responder",
                        "model": "example-model", "note": "待機中"}, ensure_ascii=False),
            encoding="utf-8")
        v = self.viewer()
        st = v.build_state(self.state, v.load_agenda(v.AGENDA_PATH), self.start_epoch)
        self.assertTrue(st["health"]["heartbeat"]["ok"])
        self.assertEqual(st["health"]["heartbeat"]["role"], "responder")

    def test_stale_heartbeat_is_reported_as_dead(self):
        old = datetime.now() - timedelta(seconds=300)
        (self.state / "heartbeat.json").write_text(
            json.dumps({"ts": iso(old), "role": "responder"}, ensure_ascii=False),
            encoding="utf-8")
        v = self.viewer()
        st = v.build_state(self.state, v.load_agenda(v.AGENDA_PATH), self.start_epoch)
        self.assertFalse(st["health"]["heartbeat"]["ok"])
        self.assertIn("心拍なし", st["health"]["heartbeat_text"])

    def test_broken_heartbeat_file_does_not_crash(self):
        (self.state / "heartbeat.json").write_text("{ this is not json", encoding="utf-8")
        v = self.viewer()
        s = self.serve(v)
        self.assertEqual(s.status("/state"), 200)
        self.assertIn("心拍なし", s.json("/state")["health"]["heartbeat_text"])

    def test_last_audio_and_line_times_are_shown(self):
        start = self.now - timedelta(minutes=2)
        self.write_transcript([
            {"ts": iso(start), "type": "mode", "mode": "start"},
            {"ts": iso(start + timedelta(seconds=30)), "speaker": "guest",
             "text": "担当は1名でやっています"},
        ])
        (self.state / "latency.jsonl").write_text("{}\n", encoding="utf-8")
        v = self.viewer()
        st = v.build_state(self.state, v.load_agenda(v.AGENDA_PATH), self.start_epoch)
        self.assertNotEqual(st["health"]["line_at"], "—")
        self.assertNotEqual(st["health"]["audio_at"], "—")
        self.assertIn("受信", st["health"]["text"])




# ---------------------------------------------------------------- 追補


class TestCredsIdRow(ViewerCase):
    def test_id_line_is_picked_up(self):
        """表とは別に「ID: xxxx」の行があれば拾う(ログイン名が表に入らない書き方)。"""
        self.creds.write_text(CREDS_MD + "\n- ID: acme-admin\n", encoding="utf-8")
        v = self.viewer()
        s = self.serve(v)
        creds = s.json("/creds")
        self.assertEqual(creds["id"], "acme-admin")
        self.assertNotIn("acme-admin", s.get("/")[1], "ID も HTML には埋め込まない")


class TestHeartbeatFollowsOutdir(ViewerCase):
    def test_heartbeat_is_read_from_the_served_outdir(self):
        """--outdir が MEETLIVE_DIR と違っても、心拍はそのDirから読む。"""
        other = self.tmp / "other_state"
        other.mkdir()
        (other / "heartbeat.json").write_text(
            json.dumps({"ts": iso(datetime.now()), "role": "copilot"}, ensure_ascii=False),
            encoding="utf-8")
        v = self.viewer()
        st = v.build_state(other, v.load_agenda(v.AGENDA_PATH), self.start_epoch)
        self.assertTrue(st["health"]["heartbeat"]["ok"])
        self.assertEqual(st["health"]["heartbeat"]["role"], "copilot")


if __name__ == "__main__":
    unittest.main(verbosity=2)
