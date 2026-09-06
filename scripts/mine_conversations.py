#!/usr/bin/env python3
"""Mine an approver's own utterances out of AI-CLI conversation logs.

The judgment-distillation loop (see docs/judgment-distillation.md) needs one
input the approval queue does not capture by itself: the moments where the human
*rejected*, *corrected*, or *overruled* the agent in the flow of a conversation.
Those live in the raw chat transcript, not in the queue. This script pulls the
human-authored turns out of those transcripts so a later pass can bucket them
(see filter_judgments.py) and feed them to the weekly distillation.

It reads both supported CLIs — Claude Code (`~/.claude/projects/<slug>/*.jsonl`)
and Codex CLI (`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`) — and keeps only
genuine human turns, dropping tool output, system reminders, harness-injected
context, meta records, and sub-agent traffic. `--source` picks a CLI; the
default reads whichever ones exist on this machine. Claude Code's CLI and
desktop app both write to the same local `~/.claude/projects` path, so mining
works the same whichever one you drove the conversation from.

The file-format knowledge lives in scripts/lib/log_sources.py, not here; see
that module to add a third harness.

Privacy: this reads YOUR OWN local logs and writes an extract to a directory you
choose. Nothing leaves the machine. Point --out at a private, git-ignored path;
never commit the extract into a public repo.

Usage
-----
  # Full extract (writes corpus.jsonl + sessions.json under --out):
  python3 mine_conversations.py --out ~/judgment/mining

  # Last-7-days window (writes corpus_recent.jsonl only, leaves the full
  # corpus untouched — this is what the weekly cron calls):
  python3 mine_conversations.py --out ~/judgment/mining --since 7d

  # One CLI only, or an absolute start date, or a count with no writes:
  python3 mine_conversations.py --source codex --since 2026-09-01 --dry-run

  # Point at specific project log dirs (default: all of ~/.claude/projects/*):
  python3 mine_conversations.py --dirs ~/.claude/projects/-home-me-work --out ~/judgment/mining
  CONV_DIRS=/path/a:/path/b python3 mine_conversations.py --out ~/judgment/mining

  # Codex keeps every project in one tree, so scope it by working directory:
  python3 mine_conversations.py --source codex --codex-cwd ~/work --out ~/judgment/mining

Extending to other harnesses
----------------------------
Add a `LogSource` subclass in scripts/lib/log_sources.py; nothing in this file
needs to change. A source yields records with a fixed set of fields, and this
script's own judgment about which of them are the human's voice is:

  1. `kind`/`msg_role` are both "user" — the transcript's own idea of who spoke.
  2. Not `is_sidechain` (a sub-agent's prompt is your agent's voice, not yours)
     and not `is_meta` (harness bookkeeping wearing a conversational role).
  3. Not one of the SKIP_* shapes below — slash commands, hook output, nudges.
  4. `prompt_source` says a human typed it. Claude Code tags turns "typed" /
     "queued" / tool-injected; Codex has no such field, so every Codex turn
     that got this far is kept and `--dry-run` prints the breakdown by source
     so you can see what you are keeping. `--any-source` drops the test.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import log_sources  # noqa: E402
from log_sources import CLAUDE, CODEX  # noqa: E402

# promptSource values that mean "a human actually authored this turn".
# Claude Code uses "typed" (interactive) and "queued" (multi-line paste / -p).
# Empty string covers older logs that predate the field.
TYPED_SOURCES = {"typed", "queued", ""}

# Human turns that are actually machine wake-ups, not judgments. Extend for your
# own automation (e.g. a mailbox poller that injects "you have N unread").
import re  # noqa: E402
NUDGE_RE = re.compile(r"^(You have \d+ unread|\d+ new messages?)\b", re.I)

# System/tooling turns that arrive on the "user" channel but are not the human.
SKIP_PREFIX = ("<command-name>", "<local-command", "Caveat: The messages below",
               "[Request interrupted")
SKIP_CONTAIN = ("<command-message>", "session_start_hook", "SessionStart:")
INTERRUPT_PREFIX = "[Request interrupted"


def parse_since(value):
    """'7d' / '7' / '2026-09-01' -> int days. None if not given."""
    try:
        return log_sources.parse_since(value, default=None)
    except ValueError:
        sys.exit("invalid --since value: %r (use e.g. 7d, 7, or 2026-09-01)" % value)


def ts_dt(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def text_of(content):
    """Content is either a string or a list of typed blocks.

    Deliberately stricter than log_sources.text_of: only blocks that say they
    are text. An extract that quietly absorbed an image or tool_use block would
    put non-speech in the corpus the distiller reads as the human's words.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def trunc(t, lim=1800):
    """Keep long turns bounded but preserve head and tail (the ask + the P.S.)."""
    if len(t) <= lim:
        return t
    return t[:1200] + "\n...[%d chars elided]...\n" % (len(t) - 1600) + t[-400:]


def typed_by_a_human(rec, keep_all_sources):
    """Did a person type this, as far as the log can tell?

    Only Claude Code records the answer. Codex writes the session's own origin
    ("exec" / "cli" / "vscode") in the same slot, which says how the session
    started and nothing about who wrote this turn — so Codex turns are kept and
    the breakdown is printed instead of a silent guess dressed as a filter.
    """
    if keep_all_sources or rec["source"] != CLAUDE:
        return True
    return rec["prompt_source"] in TYPED_SOURCES


def human_turns(session_file, keep_all_sources):
    """Yield (timestamp, prompt_source, after_interrupt, text) for human turns."""
    pending_interrupt = False
    for rec in session_file.records():
        if rec["is_sidechain"]:           # sub-agent traffic, not the human
            continue
        if rec["kind"] != "user":
            continue
        if rec["msg_role"] != "user":
            continue
        if rec["is_meta"]:
            continue
        txt = text_of(rec["raw_content"]).strip()
        if not txt:
            continue
        # An interrupt is the human hitting Esc mid-generation: a strong
        # "you're going wrong" signal. Flag the NEXT human turn as following one.
        if txt.startswith(INTERRUPT_PREFIX):
            pending_interrupt = True
            continue
        if any(txt.startswith(p) for p in SKIP_PREFIX):
            continue
        if any(s in txt[:300] for s in SKIP_CONTAIN):
            continue
        if txt.startswith("<system-reminder>"):
            continue
        if NUDGE_RE.match(txt):
            continue
        if not typed_by_a_human(rec, keep_all_sources):
            continue
        after = pending_interrupt
        pending_interrupt = False
        yield (rec["ts"], rec["prompt_source"], after, trunc(txt))


def build_sources(args):
    claude_dirs = None
    if args.dirs:
        claude_dirs = args.dirs
    elif os.environ.get("CONV_DIRS"):
        claude_dirs = os.environ["CONV_DIRS"].split(":")
    # Naming a directory for one CLI scopes the run to that CLI. Otherwise
    # `auto` reads whichever CLIs have logs on this machine.
    source = log_sources.resolve_source_name(
        args.source, claude_named=claude_dirs is not None,
        codex_named=bool(args.codex_dir or args.codex_cwd))
    try:
        sources = log_sources.build_sources(
            source, claude_dirs=claude_dirs,
            codex_dirs=args.codex_dir or None, codex_cwd=args.codex_cwd or None)
    except ValueError as e:
        sys.exit(str(e))
    live = [s for s in sources if s.existing_dirs()]
    if not live:
        looked = "; ".join(s.describe() for s in sources) or "nothing configured"
        sys.exit("no conversation logs found (looked in: %s).\n"
                 "  Pass --dirs / --codex-dir, or set CONV_DIRS / CODEX_SESSIONS_DIR."
                 % looked)
    # Keep only the directories that exist, so the walk does not re-stat a path
    # that was never there — but report on the ones that were asked for.
    for s in live:
        s.dirs = s.existing_dirs()
    return live


def main():
    ap = argparse.ArgumentParser(description="Mine approver utterances from AI-CLI logs.")
    ap.add_argument("--out", default=os.environ.get("JUDGMENT_MINING_OUT", "."),
                    help="output directory (default: $JUDGMENT_MINING_OUT or cwd). "
                         "Keep this private / git-ignored.")
    ap.add_argument("--source", default=None,
                    help="which CLI's logs to read: claude | codex | auto "
                         "(default: $LOG_SOURCE, else auto = every one present).")
    ap.add_argument("--dirs", nargs="*", default=None,
                    help="Claude Code conversation log dirs (default: $CONV_DIRS, "
                         "else ~/.claude/projects/*).")
    ap.add_argument("--codex-dir", action="append", default=[],
                    help="Codex sessions root; repeatable "
                         "(default: $CODEX_SESSIONS_DIR, else ~/.codex/sessions).")
    ap.add_argument("--codex-cwd", action="append", default=[],
                    help="keep only Codex sessions whose working directory is "
                         "this path or below it; repeatable. Codex keeps every "
                         "project in one tree, so without this you get all of them.")
    ap.add_argument("--since", default=None,
                    help="window mode: keep only turns since N days ago (7d) or "
                         "since a date (2026-09-01). Writes corpus_recent.jsonl, "
                         "leaves the full corpus alone.")
    ap.add_argument("--any-source", action="store_true",
                    help="keep every human turn regardless of promptSource "
                         "(use if your CLI has no promptSource field).")
    ap.add_argument("--dry-run", action="store_true",
                    help="read and count, write nothing. Prints what each log "
                         "source contributed.")
    args = ap.parse_args()

    sources = build_sources(args)

    out_dir = os.path.expanduser(args.out)
    if not args.dry_run:
        os.makedirs(out_dir, exist_ok=True)
    since_days = parse_since(args.since)
    cutoff = None
    if since_days is not None:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=since_days)

    seen = {}          # md5(head) -> count, for cross-session de-duplication
    recs = []
    sessions = []
    files_by_cli = Counter()
    # No mtime pre-filter, even with --since: dedup is built over EVERY file and
    # first-seen wins, so skipping old files would change which copy of a
    # repeated paste survives into the window.
    for src in sources:
        for sf in src.iter_files(None):
            files_by_cli[src.name] += 1
            n_turns = n_uniq = n_interrupt = 0
            first_ts = last_ts = None
            for ts, prompt_src, after, txt in human_turns(sf, args.any_source):
                if after:
                    n_interrupt += 1
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
                n_turns += 1
                key = hashlib.md5(txt[:400].encode()).hexdigest()
                if key in seen:            # same paste re-sent in another session
                    seen[key] += 1
                    continue
                seen[key] = 1
                n_uniq += 1
                rec = {"session": sf.session_id[:8], "ts": ts, "src": prompt_src,
                       "interrupt": after, "n": len(txt), "text": txt}
                if src.name != CLAUDE:
                    # Provenance only where it is not the historical default, so
                    # a Claude-only extract stays byte-identical to older runs.
                    rec["cli"] = src.name
                recs.append(rec)
            if n_turns:
                s = {"session": sf.session_id[:8], "turns": n_turns, "uniq": n_uniq,
                     "interrupts": n_interrupt,
                     "first": (first_ts or "")[:10], "last": (last_ts or "")[:10]}
                if src.name != CLAUDE:
                    s["cli"] = src.name
                sessions.append(s)

    recs.sort(key=lambda r: r["ts"])
    read_line = "read: " + ", ".join("%s %d file(s)" % (k, v)
                                     for k, v in sorted(files_by_cli.items()))

    if cutoff is not None:
        recent = [r for r in recs if ts_dt(r["ts"]) is not None and ts_dt(r["ts"]) >= cutoff]
        print(read_line)
        print("since %dd cutoff: %s" % (since_days, cutoff.isoformat()))
        print("recent human turns:", len(recent), "(of %d total)" % len(recs))
        print("by source:", Counter(r["src"] for r in recent).most_common())
        print("by cli:", Counter(r.get("cli", CLAUDE) for r in recent).most_common())
        if args.dry_run:
            print("dry run: nothing written")
            return
        outp = os.path.join(out_dir, "corpus_recent.jsonl")
        with open(outp, "w") as f:
            for r in recent:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("written:", outp)
        return

    print(read_line)
    print("human turns:", len(recs),
          " de-duplicated:", sum(v - 1 for v in seen.values() if v > 1))
    print("sessions:", len(sessions))
    print("by source:", Counter(r["src"] for r in recs).most_common())
    print("by cli:", Counter(r.get("cli", CLAUDE) for r in recs).most_common())
    if args.dry_run:
        print("dry run: nothing written")
        return
    corpus = os.path.join(out_dir, "corpus.jsonl")
    with open(corpus, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "sessions.json"), "w") as f:
        json.dump(sorted(sessions, key=lambda s: -s["uniq"]), f, ensure_ascii=False, indent=1)
    print("written:", corpus)


if __name__ == "__main__":
    main()
