#!/usr/bin/env python3
"""build_agenda.py の回帰テスト（標準ライブラリだけ・外へは出ない）。

見ているのは「進行表1枚から、番人と画面が読める2ファイルが出るか」と、
**出来上がりが会議で機能する形かどうか**（2026-09-19 実走で壊れていたのがそこ）:

  1. アジェンダ節のチェックリスト → 段。分・題・取る答えを拾う
  2. 「確認したいこと」→ 段へ割り付け、必須取得物と「抜けたら出す問い」になる
  3. 検知キーワードが「言い方の例」に**文字どおり**含まれる（読めば段が進む）
  4. 注記 <!-- kw / say / ask / must --> が効く（Notion に貼っても表示されない）
  5. 埋まらなかった欄は（要記入）で出る＝文章を発明しない
  6. 生成した talk_script.md を viewer2.parse_script が読め、段の役割が付く
  7. 同じ入力からは同じ出力（作り直しても並びが動かない）

実行: python3 -m unittest discover -s templates/skills/meeting-copilot/tests
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
DEMO_SHEET = SKILL / "config" / "example_meeting" / "agenda_sheet.md"
sys.path.insert(0, str(SCRIPTS))

import build_agenda as ba  # noqa: E402

# 架空の会議の進行表。実在の案件・人名・URL は1つも入っていない。
SHEET = """# ひばり商店さま 定例（架空）

## 🎯 今回のゴール

> 棚卸しのやり方を決めて、次に動く人と日付を確定する。

## 📋 アジェンダ（40分）

- [ ] **1. 今日決めたいこと（5分）** — ①棚卸しのやり方 ②担当 ③次回の日付
      <!-- say: 今日決めたいことは3つです。 -->
      <!-- must: 3つを提示した | 決めたいことは3つ -->
- [ ] **2. いまの棚卸しの様子（10分）** — 何人で、何日かけているか
- [ ] **3. 新しいやり方の確定（20分）** — 週1回に寄せるか、日次のままか
- [ ] **4. 次回のご相談（5分）** — 次に話す日を押さえる
      <!-- ask: 次にお話しするのは、いつがよろしいですか -->
      <!-- must: 次回の日付 | 来週|再来週 -->

## ❓ 確認したいこと

**今日ぜひお答えいただきたいもの**

- [ ] いまの棚卸しは、何人で担当されていますか
- [ ] 週1回に寄せる形で、ご不便はありませんか

**時間があれば**

- [ ] 在庫の記録は、何年分残しておきたいですか
"""

# 節の見出しが違う書き方でも読めること（アジェンダ/進行/次第、確認したいこと/質問）
SHEET_ALT = """## 進行（30分）

- [ ] **1. 現状のすり合わせ** — 5行で読み上げる
- [ ] **2. 見積りの前提** — どこまでを範囲にするか

## 質問

- [ ] 範囲はどこまでにしますか
"""


class BuildAgendaCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="build_agenda_test_"))
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)

    def build(self, text=SHEET, total=0.0):
        return ba.build(text, total, "架空の定例")

    # ---- 1. 段 --------------------------------------------------------
    def test_checklist_becomes_steps_with_minutes_and_answers(self):
        b = self.build()
        self.assertEqual(len(b["steps"]), 4)
        self.assertEqual([s["目安分"] for s in b["steps"]], [5.0, 10.0, 20.0, 5.0])
        self.assertEqual(b["total_min"], 40.0, "見出しの（40分）が会議の長さになる")
        self.assertIn("棚卸しのやり方", b["steps"][0]["取る答え"])
        self.assertIn("いまの棚卸しの様子", b["steps"][1]["title"])
        self.assertNotIn("2.", b["steps"][1]["title"], "頭の番号は丸数字に置き換わる")

    def test_headings_can_be_written_several_ways(self):
        b = ba.build(SHEET_ALT, 0.0, "別の書き方")
        self.assertEqual(len(b["steps"]), 2)
        self.assertEqual(b["total_min"], 30.0)
        self.assertEqual(len(b["asks"]), 1)

    def test_missing_agenda_section_is_a_clear_error(self):
        with self.assertRaises(SystemExit) as cm:
            ba.build("# ただの覚え書き\n\n本文だけ。\n")
        self.assertIn("アジェンダ", str(cm.exception))

    def test_minutes_are_spread_when_not_written(self):
        b = ba.build("## アジェンダ（30分）\n\n- [ ] **1. あ** — x\n- [ ] **2. い** — y\n")
        self.assertEqual([s["目安分"] for s in b["steps"]], [15.0, 15.0])

    # ---- 2. 確認したいこと の割り付け ----------------------------------
    def test_asks_land_on_the_step_that_shares_words(self):
        b = self.build()
        by_title = {s["title"]: s for s in b["steps"]}
        step2 = next(s for t, s in by_title.items() if "棚卸しの様子" in t)
        names = [m["名前"] for m in step2["必須取得物"]]
        self.assertTrue(any("何人で担当" in n for n in names),
                        f"「何人で担当」は棚卸しの段に付くはず: {names}")

    def test_every_ask_lands_somewhere(self):
        b = self.build()
        placed = sum(len(s["必須取得物"]) for s in b["steps"])
        # 注記で書いた must 2件 + 確認したいこと3件
        self.assertEqual(placed, 5, "確認したいことが1つも落ちない")
        for a in b["asks"]:
            self.assertIn("step", a, "割り付け先が決まっていない問いがある")

    def test_musts_carry_the_question_to_read_aloud(self):
        """取り漏れカードの【言うこと】の出どころ。ここが空だと1要素カードに戻る。"""
        b = self.build()
        asked = [m for s in b["steps"] for m in s["必須取得物"] if m.get("問い")]
        self.assertTrue(asked)
        for m in asked:
            self.assertTrue(m["問い"].strip())

    # ---- 3. 読めば段が進む --------------------------------------------
    def test_keywords_appear_literally_in_the_line_to_say(self):
        b = self.build()
        for s in b["steps"]:
            self.assertTrue(s["検知キーワード"], f"{s['title']}: 検知キーワードが空")
            hit = [k for k in s["検知キーワード"] if k in s["言い方の例"]]
            self.assertTrue(hit, f"{s['title']}: キメ台詞を読んでも段が進まない "
                                 f"{s['検知キーワード']} / {s['言い方の例']}")

    def test_generated_keywords_actually_advance_the_step(self):
        """段取りJSONを step_detect に食わせて、キメ台詞で段が進むことを見る。"""
        import re

        import step_detect
        b = self.build()
        steps = [{"kw": s["検知キーワード"]} for s in b["steps"]]

        def kw_hit(kw, blob):
            try:
                return bool(re.search(kw, blob))
            except re.error:
                return kw in blob

        recs = []
        for s in b["steps"]:
            recs.append({"speaker": "guest", "text": "はい、お願いします。"})
            recs.append({"speaker": "host", "text": s["言い方の例"]})
        self.assertEqual(step_detect.scan(steps, recs, kw_hit), len(steps) - 1,
                         "台本を順に読み上げたら最後の段まで進むはず")

    # ---- 4. 注記 ------------------------------------------------------
    def test_html_comments_override_the_generated_text(self):
        b = self.build()
        self.assertEqual(b["steps"][0]["言い方の例"], "今日決めたいことは3つです。")
        self.assertEqual(b["steps"][3]["抜けたら出す問い"],
                         "次にお話しするのは、いつがよろしいですか")
        names = [m["名前"] for m in b["steps"][3]["必須取得物"]]
        self.assertIn("次回の日付", names)

    def test_comments_do_not_leak_into_titles(self):
        b = self.build()
        for s in b["steps"]:
            self.assertNotIn("<!--", s["title"] + s["取る答え"] + s["言い方の例"])

    # ---- 5. 発明しない -------------------------------------------------
    def test_unfillable_fields_are_marked_not_invented(self):
        b = ba.build("## アジェンダ（10分）\n\n- [ ] **1. 雑談（10分）** — とくに無し\n")
        self.assertEqual(b["steps"][0]["抜けたら出す問い"], ba.TODO)
        bad = ba.check(b)
        self.assertTrue(any("抜けたら出す問い" in x for x in bad))
        self.assertTrue(any("必須取得物" in x for x in bad))

    def test_check_flag_fails_when_something_is_blank(self):
        sheet = self.tmp / "sheet.md"
        sheet.write_text("## アジェンダ（10分）\n\n- [ ] **1. 雑談（10分）** — とくに無し\n",
                         encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_agenda.py"), str(sheet),
                            "--out", str(self.tmp / "out"), "--check"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("埋まらなかった", r.stdout)

    # ---- 6. 出力が読めるか ---------------------------------------------
    def test_files_are_written_and_readable_by_the_copilot_and_viewer(self):
        sheet = self.tmp / "sheet.md"
        sheet.write_text(SHEET, encoding="utf-8")
        out = self.tmp / "meeting"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_agenda.py"), str(sheet),
                            "--out", str(out)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        raw = json.loads((out / "agenda_steps.json").read_text(encoding="utf-8"))
        self.assertEqual(len(raw["steps"]), 4)
        self.assertEqual(raw["会議分"], 40.0)

        # viewer2 の台本パーサが読めること（段の3行に役割が付く）
        import importlib
        import os
        os.environ["MEETLIVE_MEETING"] = str(out)
        os.environ["MEETLIVE_DIR"] = str(self.tmp / "state")
        for name in ("viewer2", "meetlive_config"):
            sys.modules.pop(name, None)
        v = importlib.import_module("viewer2")
        try:
            blocks = v.parse_script(out / "talk_script.md")
            self.assertEqual(sorted(blocks, key=int), ["1", "2", "3", "4"])
            for n, items in blocks.items():
                roles = [x.get("role") for x in items]
                self.assertIn("answer", roles, f"【{n}】に取る答えが無い")
                self.assertIn("line", roles, f"【{n}】に言い方の例が無い")
                self.assertIn("ask", roles, f"【{n}】に抜けたら出す問いが無い")
                self.assertEqual(len([r for r in roles if r]), 3,
                                 f"【{n}】は3行だけのはず: {items}")
        finally:
            for k in ("MEETLIVE_MEETING", "MEETLIVE_DIR"):
                os.environ.pop(k, None)
            for name in ("viewer2", "meetlive_config"):
                sys.modules.pop(name, None)

    def test_labels_are_stripped_from_the_displayed_text(self):
        """画面には「取る答え:」「抜けたら:」の札は出さず、中身だけを出す。"""
        import importlib
        import os
        sheet = self.tmp / "s2.md"
        sheet.write_text(SHEET, encoding="utf-8")
        out = self.tmp / "m2"
        subprocess.run([sys.executable, str(SCRIPTS / "build_agenda.py"), str(sheet),
                        "--out", str(out)], capture_output=True, text=True, timeout=60)
        os.environ["MEETLIVE_MEETING"] = str(out)
        os.environ["MEETLIVE_DIR"] = str(self.tmp / "state2")
        for name in ("viewer2", "meetlive_config"):
            sys.modules.pop(name, None)
        v = importlib.import_module("viewer2")
        try:
            items = v.parse_script(out / "talk_script.md")["4"]
            ask = next(x for x in items if x.get("role") == "ask")
            self.assertFalse(ask["s"].startswith("抜けたら"), ask["s"])
            self.assertEqual(ask["s"], "次にお話しするのは、いつがよろしいですか")
        finally:
            for k in ("MEETLIVE_MEETING", "MEETLIVE_DIR"):
                os.environ.pop(k, None)
            for name in ("viewer2", "meetlive_config"):
                sys.modules.pop(name, None)

    # ---- 7. 同じ入力 → 同じ出力 ----------------------------------------
    def test_output_is_stable(self):
        a = ba.to_agenda_json(self.build(), "sheet.md")
        b = ba.to_agenda_json(self.build(), "sheet.md")
        self.assertEqual(json.dumps(a, ensure_ascii=False, sort_keys=True),
                         json.dumps(b, ensure_ascii=False, sort_keys=True))

    # ---- 同梱のデモが本当にこの手順で作られているか -----------------------
    def test_shipped_demo_folder_regenerates_identically(self):
        """デモ会議フォルダの2ファイルは agenda_sheet.md から作ったものであること。

        ここが食い違うと、同梱の例が「手で直した版」になり、新しい利用者が
        この手順を踏んでも同じものが出てこない。
        """
        self.assertTrue(DEMO_SHEET.exists(), DEMO_SHEET)
        out = self.tmp / "regen"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_agenda.py"),
                            str(DEMO_SHEET), "--out", str(out), "--check",
                            "--title", "Acme社 移行の打合せ（デモ・架空）"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in ("agenda_steps.json", "talk_script.md"):
            self.assertEqual(
                (out / name).read_text(encoding="utf-8"),
                (DEMO_SHEET.parent / name).read_text(encoding="utf-8"),
                f"{name} が進行表から作り直したものと違う "
                f"(build_agenda.py を直したら同梱のデモも作り直すこと)")


if __name__ == "__main__":
    unittest.main()
