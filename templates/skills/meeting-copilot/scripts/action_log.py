#!/usr/bin/env python3
"""action_log.py — 同席モニタが「いつ・何をしたか」を1本の年表に統合する。

会議が終わったあと、**モニタが実際に何をしたか**を突き合わせるための道具。
「鳴りっぱなしだった催促は誤検知だったのか、それとも本当に未達だったのか」を
逐語(transcript.jsonl)と並べて確かめられる。新しい記録は増やさず、既存のログを読むだけ。

材料:
  cards.jsonl        画面に出したカード(内容)
  display_log.jsonl  カード+進行状態のスナップショット(nav/mode)
  stage_cmd.jsonl    舞台の切り替え操作(voice/manual)
  premise_watch.jsonl 前提監視の判定(⚠矛盾/✔既知/＋新規)
  transcript.jsonl   生の発話(call=true の行が呼びかけ)

出力: 時刻順の1行1イベント。種別ごとに絞り込み可能。

Usage:
    MEETLIVE_DIR=./meetlive_state/2026-01-20-acme \\
      python3 action_log.py --date 2026-01-20                  # その日の全イベント
    python3 action_log.py --date 2026-01-20 --kind card        # カード発火だけ
    python3 action_log.py --date 2026-01-20 --kind stage       # 舞台切替だけ
    python3 action_log.py --date 2026-01-20 --md out.md        # Markdown年表として保存
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import meetlive_config as cfgmod  # noqa: E402

MEETLIVE_DIR = cfgmod.state_dir(create=False)

KIND_LABELS = {
    "card": "カード発火",
    "stage": "舞台切替",
    "premise": "前提監視",
    "nav": "段の進行",
}


def load_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def iso_of(row):
    for key in ("iso", "ts"):
        v = row.get(key)
        if isinstance(v, str) and "T" in v:
            return v
    return None


def on_date(iso, date):
    return bool(iso) and iso[:10] == date


def build_events(date):
    events = []

    for row in load_jsonl(MEETLIVE_DIR / "cards.jsonl"):
        iso = iso_of(row)
        if not on_date(iso, date):
            continue
        events.append({
            "ts": iso, "kind": "card",
            "detail": " / ".join(row.get("lines", []))[:120],
            "conf": row.get("confidence"),
        })

    prev_title = None
    for row in load_jsonl(MEETLIVE_DIR / "display_log.jsonl"):
        iso = iso_of(row)
        if not on_date(iso, date):
            continue
        nav = row.get("nav") or {}
        title = nav.get("title")
        if title and title != prev_title:
            events.append({
                "ts": iso, "kind": "nav",
                "detail": f"段が切り替わり: {title}",
                "conf": None,
            })
            prev_title = title

    for row in load_jsonl(MEETLIVE_DIR / "stage_cmd.jsonl"):
        iso = row.get("iso")
        if not on_date(iso, date):
            continue
        events.append({
            "ts": iso, "kind": "stage",
            "detail": f"舞台→{row.get('res')} (src={row.get('src')}) 「{row.get('text','')[:40]}」",
            "conf": None,
        })

    for row in load_jsonl(MEETLIVE_DIR / "premise_watch.jsonl"):
        iso = row.get("ts")
        if not on_date(iso, date):
            continue
        t = row.get("type", "なし")
        if t == "なし":
            continue
        events.append({
            "ts": iso, "kind": "premise",
            "detail": f"[{t}] {row.get('utterance','')[:60]}",
            "conf": None,
        })

    events.sort(key=lambda e: e["ts"] or "")
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--kind", choices=list(KIND_LABELS), default=None)
    ap.add_argument("--md", help="この年表をMarkdownファイルへ保存")
    ap.add_argument("--from-time", help="この時刻(HH:MM:SS)以降だけ(実開始で絞る用)")
    ap.add_argument("--to-time", help="この時刻(HH:MM:SS)以前だけ")
    args = ap.parse_args()

    events = build_events(args.date)
    if args.kind:
        events = [e for e in events if e["kind"] == args.kind]
    if args.from_time:
        events = [e for e in events if e["ts"] and e["ts"][11:19] >= args.from_time]
    if args.to_time:
        events = [e for e in events if e["ts"] and e["ts"][11:19] <= args.to_time]

    lines = [f"# 同席モニタ 行動年表 — {args.date}", "",
             f"状態ディレクトリ: {MEETLIVE_DIR}", "",
             f"総イベント数: {len(events)}", ""]
    lines.append("| 時刻 | 種別 | 内容 |")
    lines.append("|---|---|---|")
    for e in events:
        t = e["ts"][11:19] if e["ts"] else "?"
        lines.append(f"| {t} | {KIND_LABELS.get(e['kind'], e['kind'])} | {e['detail']} |")
    out = "\n".join(lines)

    if args.md:
        pathlib.Path(args.md).write_text(out + "\n", encoding="utf-8")
        print(f"saved: {args.md} ({len(events)}件)")
    else:
        print(out)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stderr.close()
