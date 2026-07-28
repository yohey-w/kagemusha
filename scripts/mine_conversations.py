#!/usr/bin/env python3
"""Mine an approver's own utterances out of AI-CLI conversation logs.

The judgment-distillation loop (see docs/judgment-distillation.md) needs one
input the approval queue does not capture by itself: the moments where the human
*rejected*, *corrected*, or *overruled* the agent in the flow of a conversation.
Those live in the raw chat transcript, not in the queue. This script pulls the
human-authored turns out of those transcripts so a later pass can bucket them
(see filter_judgments.py) and feed them to the weekly distillation.

It reads Claude Code session logs by default — newline-delimited JSON, one file
per session, under ~/.claude/projects/<slugified-project>/*.jsonl — and keeps
only genuine human turns (typed / queued), dropping tool output, system
reminders, meta records, and sidechain (sub-agent) traffic. Claude Code's CLI and
desktop app both write to this same local ~/.claude/projects path, so mining works
the same whichever one you drove the conversation from. For a different harness,
see "Extending to other harnesses" below.

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

  # Point at specific project log dirs (default: all of ~/.claude/projects/*):
  python3 mine_conversations.py --dirs ~/.claude/projects/-home-me-work --out ~/judgment/mining
  CONV_DIRS=/path/a:/path/b python3 mine_conversations.py --out ~/judgment/mining

Extending to other harnesses
----------------------------
Only three things are Claude-Code-specific; adapt `iter_records()` for a
different CLI and the rest is portable:
  1. On-disk shape: one JSONL file per session under a per-project directory.
     Change `session_files()` for a different layout (e.g. a single log file, or
     a SQLite store — yield (session_id, [record, ...]) instead).
  2. The "is this a human turn?" test: here, type=="user" & message.role=="user"
     & not sidechain/meta. Rewrite `human_turns()` for your record schema.
  3. `promptSource`: Claude Code tags typed vs. queued vs. tool-injected user
     records. TYPED_SOURCES lists the ones that mean "the human actually said
     this". If your CLI lacks the field, set --any-source to keep every human
     turn (you lose the tool-injected-vs-typed distinction).
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter

# promptSource values that mean "a human actually authored this turn".
# Claude Code uses "typed" (interactive) and "queued" (multi-line paste / -p).
# Empty string covers older logs that predate the field.
TYPED_SOURCES = {"typed", "queued", ""}

# Human turns that are actually machine wake-ups, not judgments. Extend for your
# own automation (e.g. a mailbox poller that injects "you have N unread").
NUDGE_RE = re.compile(r"^(You have \d+ unread|\d+ new messages?)\b", re.I)

# System/tooling turns that arrive on the "user" channel but are not the human.
SKIP_PREFIX = ("<command-name>", "<local-command", "Caveat: The messages below",
               "[Request interrupted")
SKIP_CONTAIN = ("<command-message>", "session_start_hook", "SessionStart:")
INTERRUPT_PREFIX = "[Request interrupted"


def parse_since(value):
    """'7d' / '7' / '14d' -> int days. None if not given."""
    if value is None:
        return None
    v = value.strip().lower().rstrip("d")
    try:
        return int(v)
    except ValueError:
        sys.exit("invalid --since value: %r (use e.g. 7d or 7)" % value)


def ts_dt(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def text_of(content):
    """Claude Code content is either a string or a list of typed blocks."""
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


def session_files(dirs):
    """Yield every session log path. Claude Code = one *.jsonl per session."""
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
            yield path


def human_turns(path, keep_all_sources):
    """Yield (timestamp, promptSource, after_interrupt, text) for human turns.

    Rewrite this function to port to a non-Claude-Code harness; everything
    downstream operates on these four fields.
    """
    pending_interrupt = False
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("isSidechain"):          # sub-agent traffic, not the human
                continue
            if o.get("type") != "user":
                continue
            m = o.get("message") or {}
            if m.get("role") != "user":
                continue
            if o.get("isMeta") or o.get("isCompactSummary"):
                continue
            txt = text_of(m.get("content")).strip()
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
            src = o.get("promptSource", "")
            if not keep_all_sources and src not in TYPED_SOURCES:
                continue
            after = pending_interrupt
            pending_interrupt = False
            yield (o.get("timestamp", ""), src, after, trunc(txt))


def main():
    ap = argparse.ArgumentParser(description="Mine approver utterances from AI-CLI logs.")
    ap.add_argument("--out", default=os.environ.get("JUDGMENT_MINING_OUT", "."),
                    help="output directory (default: $JUDGMENT_MINING_OUT or cwd). "
                         "Keep this private / git-ignored.")
    ap.add_argument("--dirs", nargs="*", default=None,
                    help="conversation log dirs (default: $CONV_DIRS, else "
                         "~/.claude/projects/*).")
    ap.add_argument("--since", default=None,
                    help="window mode: keep only the last N days (e.g. 7d). "
                         "Writes corpus_recent.jsonl, leaves the full corpus alone.")
    ap.add_argument("--any-source", action="store_true",
                    help="keep every human turn regardless of promptSource "
                         "(use if your CLI has no promptSource field).")
    args = ap.parse_args()

    if args.dirs:
        dirs = args.dirs
    elif os.environ.get("CONV_DIRS"):
        dirs = os.environ["CONV_DIRS"].split(":")
    else:
        dirs = sorted(glob.glob(os.path.expanduser("~/.claude/projects/*")))
    dirs = [os.path.expanduser(d) for d in dirs if os.path.isdir(os.path.expanduser(d))]
    if not dirs:
        sys.exit("no conversation dirs found (pass --dirs or set CONV_DIRS).")

    out_dir = os.path.expanduser(args.out)
    os.makedirs(out_dir, exist_ok=True)
    since_days = parse_since(args.since)
    cutoff = None
    if since_days is not None:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=since_days)

    seen = {}          # md5(head) -> count, for cross-session de-duplication
    recs = []
    sessions = []
    for path in session_files(dirs):
        base = os.path.basename(path)
        n_turns = n_uniq = n_interrupt = 0
        first_ts = last_ts = None
        for ts, src, after, txt in human_turns(path, args.any_source):
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
            recs.append({"session": base[:8], "ts": ts, "src": src,
                         "interrupt": after, "n": len(txt), "text": txt})
        if n_turns:
            sessions.append({"session": base[:8], "turns": n_turns, "uniq": n_uniq,
                             "interrupts": n_interrupt,
                             "first": (first_ts or "")[:10], "last": (last_ts or "")[:10]})

    recs.sort(key=lambda r: r["ts"])

    if cutoff is not None:
        recent = [r for r in recs if ts_dt(r["ts"]) is not None and ts_dt(r["ts"]) >= cutoff]
        outp = os.path.join(out_dir, "corpus_recent.jsonl")
        with open(outp, "w") as f:
            for r in recent:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("since %dd cutoff: %s" % (since_days, cutoff.isoformat()))
        print("recent human turns:", len(recent), "(of %d total)" % len(recs))
        print("by source:", Counter(r["src"] for r in recent).most_common())
        print("written:", outp)
        return

    corpus = os.path.join(out_dir, "corpus.jsonl")
    with open(corpus, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "sessions.json"), "w") as f:
        json.dump(sorted(sessions, key=lambda s: -s["uniq"]), f, ensure_ascii=False, indent=1)
    print("human turns:", len(recs),
          " de-duplicated:", sum(v - 1 for v in seen.values() if v > 1))
    print("sessions:", len(sessions))
    print("by source:", Counter(r["src"] for r in recs).most_common())
    print("written:", corpus)


if __name__ == "__main__":
    main()
