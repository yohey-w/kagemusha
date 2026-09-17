#!/usr/bin/env python3
"""ssot/ledger.yaml（正本）→ ssot/*.md（人が読む用のビュー）を生成する。

殿裁定 2026-08-22「SSOTは物理的にひとつにしないと事故る」の生成側。
**MD は生成物**。直接編集しても次回生成で消える。編集するのは ssot/ledger.yaml だけ。

流儀は projects/sugawara-donow/ledgers/render.py に合わせてある
（BANNER / esc / 不変条件の assert / 件数の印字）。

使い方: python3 scripts/render_ssot.py [ledger.yaml のパス]

同時に走る不変条件のチェック（assert）:
  - ID の重複が無い（tasks / facts / holes / forks / open_questions を横断）
  - status が enum のいずれか
  - due が YYYY-MM-DD か null。due_note は due が null のときだけ
  - project が projects[].path のいずれか（か null）
  - holes.blocks / forks.depends_on / tasks.depends_on の ID 参照先が実在する

🔴 節名を変えるときの制約（**まだ生きている**）:
  - 締切レーダー（local/scripts/goal_scan/scan.py:src_tasks・朝の便 6:53 cron→ntfy）は、
    **節名に「進行中」または「未着手」を含む節だけ**を読む。チェックリスト節は読まない。
    節名を変えると、その節のタスクは殿の携帯から静かに消える。
  - 2026-08-23 まで、同 src_tasks は **この生成物 ssot/tasks.md を列の位置**
    （cells[0..3] = 担当|内容|期日|状態）で読んでいた。いまは正本 ssot/ledger.yaml を
    直接読むので、**列順を変えても締切レーダーは壊れない**（読者は人間だけ）。
    等価性は local/scripts/test_ssot_readers.py が実データで突き合わせている。
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]          # ~/kagemusha
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "ssot/ledger.yaml"
OUT = ROOT / "ssot"

BANNER = "<!-- 自動生成。ssot/ledger.yaml を編集すること -->\n\n"

STATUS_OK = ("未着手", "進行中", "待ち", "完了", "消滅")
# 節の並びは ledger の tasks に現れた順（固定リストにすると、節名が1文字変わった
# だけで丸ごと描かれず消える——2026-08-22 に実際に13件落とした）
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^(T-|F-|H-|K-|OPEN-|A\d)")


def esc(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


# ── 不変条件 ─────────────────────────────────────────────────
def check(d):
    ids = {}
    for bucket in ("tasks", "facts", "holes", "forks", "open_questions"):
        for row in d.get(bucket, []):
            assert row["id"] not in ids, f"ID重複: {row['id']}"
            ids[row["id"]] = bucket

    paths = {p["path"] for p in d["projects"]}
    for t in d["tasks"]:
        assert t["status"] in STATUS_OK, f"{t['id']}: 状態が不正 {t['status']!r}"
        assert t["project"] is None or t["project"] in paths, \
            f"{t['id']}: project が projects に無い {t['project']!r}"
        if t["due"] is not None:
            assert DATE_RE.match(str(t["due"])), f"{t['id']}: due が YYYY-MM-DD でない"
            assert not t.get("due_note"), f"{t['id']}: due があるのに due_note が入っている"
        for ref in t.get("depends_on") or []:
            if ID_RE.match(str(ref)):
                assert str(ref).startswith("A") or ref in ids, \
                    f"{t['id']}.depends_on の参照先が無い: {ref}"

    for row in d["holes"]:
        for ref in row.get("blocks") or []:
            assert ref in ids, f"{row['id']}.blocks の参照先が無い: {ref}"
    for row in d["forks"]:
        for ref in row.get("depends_on") or []:
            assert ref in ids, f"{row['id']}.depends_on の参照先が無い: {ref}"
    return ids


# ── tasks.md ────────────────────────────────────────────────
def due_cell(t):
    if t["due"]:
        return t["due"]
    note = t.get("due_note") or ""
    m = re.search(r"「(.+?)」", note)
    return m.group(1) if m else "—"


def render_tasks(d, proj_id):
    blocks = d["meta"]["doc_blocks"]["tasks"]
    out = [BANNER, blocks["header"], "\n\n"]
    sections = []
    for t in d["tasks"]:
        if t.get("section") not in sections:
            sections.append(t.get("section"))
    drawn = 0
    for sec in sections:
        rows = [t for t in d["tasks"] if t.get("section") == sec]
        if not rows:
            continue
        drawn += len(rows)
        out.append(f"## {sec}（{len(rows)}件）\n\n")
        if str(sec).startswith("チェックリスト"):
            for t in rows:
                mark = "x" if t["status"] == "完了" else " "
                out.append(f"- [{mark}] `{t['id']}` {t['what']}\n")
            out.append("\n")
        else:
            # 先頭4列 担当|内容|期日|状態 は人が読む並び。
            # （2026-08-23 まではここを src_tasks が位置で読んでいた。いまは
            #   ssot/ledger.yaml 直読みなので、機械の都合で縛られてはいない）
            out.append("| 担当 | 内容 | 期日 | 状態 | 出典 | 案件 | ID |\n")
            out.append("|---|---|---|---|---|---|---|\n")
            for t in rows:
                out.append(
                    f"| {esc(t['who'])} | {esc(t['what'])} | {due_cell(t)} | {t['status']} | "
                    f"{esc(t.get('source') or '')} | {proj_id(t['project'])} | {t['id']} |\n")
            out.append("\n")

    assert drawn == len(d["tasks"]), f"タスクを描き落とした: {drawn}/{len(d['tasks'])}"

    notes = []
    for t in d["tasks"]:
        lines = []
        for key, label in (("critical", "🔴 落とせない"), ("blocker", "止めているもの"),
                           ("depends_on", "依存"), ("evidence", "証拠"),
                           ("due_note", "期日の注記"), ("schedule", "日程"),
                           ("impact", "効いてくるところ"), ("escalation", "催促の線"),
                           ("spawned", "ここから生まれた"), ("outcome", "結果"),
                           ("evidence_required", "完了に要る証拠"), ("note", "注記"),
                           ("verified_at", "最後に現物確認した日")):
            v = t.get(key)
            if v in (None, "", [], False):
                continue
            if isinstance(v, list):
                v = " / ".join(str(x) for x in v)
            lines.append(f"  - {label}: {' '.join(str(v).split())}")
        if lines:
            notes.append(f"- **{t['id']}** {t['what'][:40]}…\n" + "\n".join(lines))
    if notes:
        out.append("\n## 注記（期日・証拠・依存・止まっているもの）\n\n")
        out.append("\n".join(notes) + "\n")

    out.append("\n" + blocks["footer"] + "\n")
    return "".join(out)


# ── people.md ───────────────────────────────────────────────
def render_people(d):
    blocks = d["meta"]["doc_blocks"]["people"]
    out = [BANNER, blocks["header"], "\n\n",
           "| 表示名 | 読み | 役割 | 連絡手段 |\n|---|---|---|---|\n"]
    for p in d["people"]:
        out.append(f"| {esc(p['display'])} | {esc(p['reading'])} | "
                   f"{esc(p['role'])} | {esc(p['contact'])} |\n")
    out.append("\n" + blocks["footer"] + "\n")
    return "".join(out)


# ── glossary.md ─────────────────────────────────────────────
def render_glossary(d):
    blocks = d["meta"]["doc_blocks"]["glossary"]
    out = [BANNER, blocks["header"], "\n\n"]
    groups = []
    for g in d["glossary"]:
        if g["group"] not in groups:
            groups.append(g["group"])
    for group in groups:
        rows = [g for g in d["glossary"] if g["group"] == group]
        if rows[0]["kind"] == "用語（節）":
            continue                      # CHS は末尾へ（原文の並び）
        out.append(f"## {group}\n\n")
        if rows[0]["kind"] == "禁止語":
            out.append("| 使ってはいけない語 | 正しい書き方 | 理由 |\n|---|---|---|\n")
            for r in rows:
                out.append(f"| {esc(r['term'])} | {esc(r['correct'])} | {esc(r['reason'])} |\n")
        else:
            out.append("| 正式表記 | 別名・表記ゆれ | 意味 |\n|---|---|---|\n")
            for r in rows:
                out.append(f"| {esc(r['term'])} | {esc(r['aliases'])} | {esc(r['meaning'])} |\n")
        out.append("\n")
    out.append("---\n\n" + blocks["footer"] + "\n")
    for g in d["glossary"]:
        if g["kind"] == "用語（節）":
            out.append("\n" + g["body"] + "\n")
    return "".join(out)


# ── decisions.md ────────────────────────────────────────────
def render_decisions(d):
    blocks = d["meta"]["doc_blocks"]["decisions"]
    out = [BANNER, blocks["header_pre_index"], "\n\n",
           "| topic | 最新 | 要約 |\n|---|---|---|\n"]
    indexed = sorted((x for x in d["decisions"] if x.get("index_order")),
                     key=lambda x: x["index_order"])
    for r in indexed:
        out.append(f"| {esc(r['topic'])} | {r['id']} | {esc(r['index_summary'])} |\n")
    out.append("\n" + blocks["header_post_index"] + "\n\n")

    for r in d["decisions"]:
        if r.get("kind") == "未記帳":
            continue
        head = f"### {r['id']} [topic: {r['topic']}]"
        if r.get("replaces"):
            head += f" ✅ 置換元: {r['replaces']}"
        if r.get("replaced_by"):
            head += f" ⚠️ 置換先: {r['replaced_by']}"
        out.append(head + "\n")
        for key, label in (("decision", "決定"), ("source", "出典"), ("background", "背景")):
            if r.get(key):
                out.append(f"- {label}: {r[key]}\n")
        out.append("\n")

    out.append(blocks["unrecorded_header"] + "\n\n")
    for r in d["decisions"]:
        if r.get("kind") == "未記帳":
            out.append(f"- {r['body']}\n")
    out.append("\n" + blocks["footer"] + "\n")
    return "".join(out)


def main():
    d = yaml.safe_load(SRC.read_text(encoding="utf-8"))
    check(d)

    by_path = {p["path"]: p["id"] for p in d["projects"]}

    def proj_id(path):
        return by_path.get(path, "—") if path else "—"

    files = {
        "tasks.md": render_tasks(d, proj_id),
        "people.md": render_people(d),
        "glossary.md": render_glossary(d),
        "decisions.md": render_decisions(d),
    }
    for name, body in files.items():
        (OUT / name).write_text(body, encoding="utf-8")

    print(f"正本: {SRC}")
    print(f"人 {len(d['people'])} / 用語 {len(d['glossary'])} / 規約 {len(d['norms'])} / "
          f"決定 {len(d['decisions'])} / タスク {len(d['tasks'])} / "
          f"事実 {len(d['facts'])} / 穴 {len(d['holes'])} / 分岐 {len(d['forks'])} / "
          f"未決の問い {len(d['open_questions'])}")
    per = {}
    for t in d["tasks"]:
        per[proj_id(t["project"])] = per.get(proj_id(t["project"]), 0) + 1
    print("タスクの案件別:", " / ".join(f"{k} {v}" for k, v in sorted(per.items())))
    print("verified_at が null:", sum(1 for t in d["tasks"] if t.get("verified_at") is None))
    print("生成:", " ".join(f"ssot/{n}" for n in files))


if __name__ == "__main__":
    main()
