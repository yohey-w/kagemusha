#!/usr/bin/env python3
"""correction_scan.py — harvest CORRECTION CANDIDATES from AI-CLI session logs, daily, for free.

The highest-value line in your logs is the one where you overruled the agent
("no, not like that", "I didn't ask for that", "you assumed X"). It is the delta
between the model and you, and it is also the line nobody ever collects: the
correction happens in the middle of a chat, gets acted on, and scrolls away.

This script is the cheap half of the distillation courier: it runs every day,
uses NO LLM, and does exactly three things — walk the last N days of session
logs, append the turns that LOOK LIKE corrections to an append-only material
file, and count how many EVENTS have not been distilled yet. The expensive half
(scripts/distill.sh) reads that count and decides whether there is enough
material to be worth firing a model at. Design: docs/distillation-loop.md.

  ┌──────────────────────────────────────────────────────────────────────┐
  │ THIS SCRIPT DOES NOT JUDGE, and it does not promote anything. It     │
  │ matches regexes and quotes text. A hit is a CANDIDATE. Deciding      │
  │ which candidate is a real correction — and which correction is worth │
  │ becoming a rule — happens later, and the last step of it is a human. │
  └──────────────────────────────────────────────────────────────────────┘

**Events, not lines.** One thing you said four different ways in ninety seconds
is ONE correction. Counted as four it would clear the firing threshold on its
own and then arrive at the reviewer looking like four independent witnesses —
pseudo-repetition inflating confidence, which the journal spec bans by name
(cluster-one-vote). So candidates are grouped, coarsely and mechanically, by
session + time bucket, and it is the number of GROUPS that the threshold sees.
The grouping is deliberately dumb: two unrelated corrections three minutes apart
become one event, and one event straddling a bucket edge becomes two. It is a
damper on volume, not a semantic parser — see --cluster-window.

Three things it deliberately does NOT collect:
  · subagent turns (`isSidechain`). In a sidechain the "user" role is another
    agent's prompt, not you. Harvesting those would fill the material file with
    the agent correcting itself and pass it off as your judgment.
  · tool results and harness plumbing (they carry the `user` role too).
  · anything older than the window, or already harvested (dedup by content
    hash, so running it twice a day is harmless).

It also grabs the tail of the assistant turn immediately before each hit. A
correction without the thing it corrected is not evidence of anything — the
reason a call was overruled is only recoverable while the rejected artifact is
still in view (docs/judgment-distillation.md, "reasons are collected at the
scene"). That one line of context is what keeps the later review honest.

**Where the text goes.** Everything here stays on this machine: it reads local
logs and writes the two local files you name. Quoted fragments are TRUNCATED on
purpose (--snippet / --lead) — the material file is an index into your logs, not
a second copy of them, and it is the file that later gets pasted into a model
prompt. The only thing that ever leaves the machine is that one distillation
call, made by scripts/distill.sh, carrying the truncated material.

Usage:
  scripts/correction_scan.py --patterns FILE --material FILE --state FILE
                             [--since 1d] [--dir DIR ...]
                             [--snippet 300] [--lead 160] [--cluster-window 20]
  scripts/correction_scan.py --state FILE --status
  scripts/correction_scan.py --state FILE --material FILE --mark-distilled

  --patterns  your correction patterns, one regex per line ('#' comments).
              REQUIRED — there is no built-in list. Start from
              templates/correction_patterns.example.txt and cut it down: the
              phrases you use when you overrule someone are yours, and a
              vocabulary shipped in the script would quietly become everyone's.
  --material  the append-only material file candidates are added to
  --state     small JSON file: events harvested, events distilled, when
  --dir       a directory of *.jsonl session logs; repeatable.
              Default: ~/.claude/projects/<slug of the current directory>
  --status    print pending / harvested / days-since-distill and exit
  --mark-distilled  advance the ratchet: everything harvested so far counts as
              distilled, and a marker line is appended to the material file.
              scripts/distill.sh calls this ONLY after a successful run.

Exit codes: 0 ok · 2 bad usage / no log directory at all.
A quiet day (log dirs exist, nothing recent in them) is exit 0 and one line on
stderr — not an error. A missing log directory IS an error: "you did no work"
and "the harvester has been pointed at nothing for a month" must not look alike.

Stdlib only. Reads logs; writes the two files you name. Nothing leaves the machine.
"""
import datetime
import glob
import hashlib
import json
import os
import re
import sys

# Deliberately duplicated from discipline_scan.py rather than shared: every
# script in scripts/ has to stay runnable on its own, copied anywhere, stdlib only.
SKIP_PREFIX = ("<command-name>", "<local-command", "<bash-stdout",
               "Caveat: The messages below", "[Request interrupted")

MARKER = "<!-- distilled through "
SEEN_CAP = 5000          # keep the state file small; older hashes age out
STATE_VERSION = 1


def die(msg):
    sys.stderr.write("correction_scan: %s\n" % msg)
    sys.exit(2)


# ── argv ───────────────────────────────────────────────────────────────────
def opts(argv, name, multi=False):
    vals = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == name and i + 1 < len(argv):
            vals.append(argv[i + 1])
            i += 2
            continue
        if a.startswith(name + "="):
            vals.append(a.split("=", 1)[1])
        i += 1
    return vals if multi else (vals[-1] if vals else None)


def project_slug(path):
    """Claude Code's directory name for a project: every non-alphanumeric
    character of the absolute path becomes '-' (so /a/b-c -> -a-b-c)."""
    return "".join(c if c.isalnum() and c.isascii() else "-" for c in os.path.abspath(path))


def default_dirs():
    return [os.path.join(os.path.expanduser("~"), ".claude", "projects",
                         project_slug(os.getcwd()))]


# ── state ──────────────────────────────────────────────────────────────────
def load_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
    except FileNotFoundError:
        st = {}
    except (OSError, ValueError) as e:
        # A corrupt state file must stop the run. Silently starting from zero
        # would re-harvest everything and, worse, reset the pending count that
        # decides whether the expensive half fires.
        die("cannot read state file %s: %s\n"
            "  Fix or delete it deliberately; this script will not guess." % (path, e))
    st.setdefault("version", STATE_VERSION)
    st.setdefault("harvested", 0)        # EVENTS, not candidate lines
    st.setdefault("distilled", 0)
    st.setdefault("first_scan", None)    # when this loop's clock started
    st.setdefault("last_scan", None)
    st.setdefault("last_distill", None)
    st.setdefault("seen", [])            # candidate content hashes
    st.setdefault("events", [])          # cluster keys already counted
    return st


def save_state(path, st):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def days_since(iso):
    if not iso:
        return -1
    try:
        then = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return -1
    if then.tzinfo is None:
        then = then.replace(tzinfo=datetime.timezone.utc)
    delta = datetime.datetime.now(datetime.timezone.utc) - then
    return max(0, delta.days)


def epoch_minutes(ts):
    """Minutes since the epoch for an ISO timestamp, or None if unparseable."""
    try:
        t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return int(t.timestamp() // 60)


# ── patterns ───────────────────────────────────────────────────────────────
def load_patterns(path):
    try:
        with open(path, encoding="utf-8") as fh:
            raw = [ln.strip() for ln in fh]
    except OSError as e:
        die("cannot read patterns file: %s\n"
            "  Start from templates/correction_patterns.example.txt." % e)
    raw = [ln for ln in raw if ln and not ln.startswith("#")]
    if not raw:
        die("patterns file %s has no patterns (only comments/blank lines).\n"
            "  An empty pattern list harvests nothing and looks exactly like a quiet week."
            % path)
    out = []
    for p in raw:
        try:
            out.append((p, re.compile(p, re.I)))
        except re.error as e:
            die("bad regex %r: %s" % (p, e))
    return out


# ── log walk ───────────────────────────────────────────────────────────────
def text_of(content):
    """Message text, whichever shape the transcript uses. A user turn's
    `content` is often a BARE STRING while an assistant turn is a list of typed
    blocks; handling only the list shape silently drops every human turn."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                parts.append(c["text"])
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(parts)
    return ""


def usable(obj):
    """(role, text) for a turn worth looking at, else None."""
    kind = obj.get("type")
    if kind not in ("assistant", "user"):
        return None
    if obj.get("isSidechain"):
        return None                      # a subagent's prompt is not your voice
    if obj.get("toolUseResult") is not None:
        return None                      # tool output wearing the user role
    txt = text_of((obj.get("message") or {}).get("content")).strip()
    if not txt or txt.startswith(SKIP_PREFIX):
        return None
    if "<system-reminder>" in txt[:80]:
        return None
    return kind, txt


def harvest(dirs, patterns, cutoff, snippet, lead):
    """Return (candidates, files_seen). Each candidate is a dict."""
    found = []
    files = 0
    cut_s = cutoff.isoformat()

    for d in dirs:
        if not os.path.isdir(d):
            continue
        for path in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
            try:
                if os.path.getmtime(path) < cutoff.timestamp():
                    continue
            except OSError:
                continue
            files += 1
            src = os.path.basename(path)[:8]
            prior = ""                     # last assistant turn seen in this file
            with open(path, errors="replace") as fh:
                for line in fh:
                    if '"assistant"' not in line and '"user"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    got = usable(obj)
                    if not got:
                        continue
                    role, txt = got
                    if role == "assistant":
                        prior = txt
                        continue
                    ts = obj.get("timestamp", "")
                    if not ts or ts < cut_s:
                        continue
                    hit = None
                    for src_pat, rex in patterns:
                        if rex.search(txt):
                            hit = src_pat
                            break
                    if hit is None:
                        continue
                    body = " ".join(txt.split())[:snippet]
                    ctx = " ".join(prior.split())
                    ctx = ctx[-lead:] if len(ctx) > lead else ctx
                    found.append({
                        "ts": ts[:16].replace("T", " "),
                        "raw_ts": ts,
                        "src": src,
                        "pat": hit[:24],
                        "text": body,
                        "prior": ctx,
                        "key": hashlib.md5(("%s|%s" % (src, body[:120]))
                                           .encode("utf-8")).hexdigest(),
                    })
    found.sort(key=lambda c: c["ts"])
    return found, files


def cluster(cands, window):
    """Group candidates into EVENTS: same session, same fixed time bucket.

    Fixed buckets (not a chain from the previous hit) so the grouping is stable
    across runs: a turn harvested tomorrow lands in the same bucket it would
    have landed in today, and an event already counted is not counted twice.
    """
    groups = {}
    order = []
    for c in cands:
        em = epoch_minutes(c["raw_ts"])
        bucket = (em // window) if em is not None else c["raw_ts"][:16]
        ckey = hashlib.md5(("%s|%s" % (c["src"], bucket)).encode("utf-8")).hexdigest()[:12]
        if ckey not in groups:
            groups[ckey] = []
            order.append(ckey)
        groups[ckey].append(c)
    return [(k, groups[k]) for k in order]


def render(events, days, dirs, window):
    stamp = datetime.datetime.now().strftime("%F %T")
    L = ["", "## %s — %d event(s), window %dd" % (stamp, len(events), days),
         "<!-- machine-extracted, UNJUDGED. dirs: %s / grouping: session + %dmin bucket -->"
         % (", ".join(dirs), window), ""]
    for ckey, members in events:
        head = members[0]
        L.append("- event %s — [%s] session %s, %d turn(s) (pat: %s)"
                 % (ckey, head["ts"], head["src"], len(members), head["pat"]))
        if head["prior"]:
            L.append("  - in reply to: ...%s" % head["prior"])
        for m in members:
            L.append("  - you [%s]: %s" % (m["ts"][11:], m["text"]))
    return "\n".join(L) + "\n"


def append(path, body):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new:
            fh.write("# correction material — append-only, machine-harvested, UNJUDGED\n"
                     "#\n"
                     "# Candidates only: a line here is a regex hit, not a correction, and a\n"
                     "# correction is not yet a rule. Nothing in this file governs anything\n"
                     "# until a human promotes it. Quotes are truncated on purpose — this is\n"
                     "# an index into your logs, not a copy of them. See docs/distillation-loop.md.\n")
        fh.write(body)


# ── modes ──────────────────────────────────────────────────────────────────
def do_status(state_path):
    st = load_state(state_path)
    pending = max(0, st["harvested"] - st["distilled"])
    # Before the first distillation the clock runs from the first scan, not from
    # nothing: a brand-new install has waited zero days, not forever. Reporting
    # "never" as overdue would make the weekly fallback fire on day one and
    # quietly cancel the threshold it is supposed to back up.
    ref = st["last_distill"] or st["first_scan"]
    sys.stdout.write("pending=%d\nharvested=%d\ndistilled=%d\n"
                     "days_since_distill=%d\nlast_scan=%s\n"
                     % (pending, st["harvested"], st["distilled"],
                        days_since(ref), st["last_scan"] or "never"))
    return 0


def do_mark(state_path, material):
    st = load_state(state_path)
    pending = max(0, st["harvested"] - st["distilled"])
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    st["distilled"] = st["harvested"]
    st["last_distill"] = now
    save_state(state_path, st)
    if material:
        append(material, "\n%s%s (%d event(s)) -->\n" % (MARKER, now, pending))
    sys.stderr.write("marked %d event(s) as distilled\n" % pending)
    return 0


def main():
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        sys.stdout.write(__doc__)
        return 0

    state_path = opts(argv, "--state")
    if not state_path:
        die("--state is required (a small JSON file; it holds the pending count)")
    state_path = os.path.expanduser(state_path)
    material = opts(argv, "--material")
    if material:
        material = os.path.expanduser(material)

    if "--status" in argv:
        return do_status(state_path)
    if "--mark-distilled" in argv:
        return do_mark(state_path, material)

    if not material:
        die("--material is required (the append-only file candidates land in)")
    pat_file = opts(argv, "--patterns")
    if not pat_file:
        die("--patterns is required (start from templates/correction_patterns.example.txt).\n"
            "  There is no built-in vocabulary: the words you use to overrule an agent\n"
            "  are yours, and a list baked into this script would become everyone's.")

    raw_since = (opts(argv, "--since") or "1").strip().lower().rstrip("d")
    try:
        days = int(raw_since)
        if days <= 0:
            raise ValueError
    except ValueError:
        die("--since wants a positive number of days, e.g. 1 or 7d")
    try:
        snippet = int(opts(argv, "--snippet") or "300")
        lead = int(opts(argv, "--lead") or "160")
        window = int(opts(argv, "--cluster-window") or "20")
        if window <= 0:
            raise ValueError
    except ValueError:
        die("--snippet / --lead want integers; --cluster-window wants a positive integer")

    patterns = load_patterns(os.path.expanduser(pat_file))
    dirs = [os.path.expanduser(p) for p in opts(argv, "--dir", multi=True)] or default_dirs()
    if not [d for d in dirs if os.path.isdir(d)]:
        die("no session-log directory found: %s\n"
            "  Pass --dir explicitly. (The default is derived from the current\n"
            "  directory; it only exists if this project has transcripts.)"
            % ", ".join(dirs))

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    cands, files = harvest(dirs, patterns, cutoff, snippet, lead)

    st = load_state(state_path)
    seen = set(st["seen"])
    fresh = [c for c in cands if c["key"] not in seen]
    events = cluster(fresh, window)

    known = set(st["events"])
    new_events = [(k, m) for k, m in events if k not in known]

    if events:
        append(material, render(events, days, dirs, window))
        st["seen"] = (st["seen"] + [c["key"] for c in fresh])[-SEEN_CAP:]
        # Only clusters never counted before move the pending needle. A late turn
        # joining an event that already fired must not fire it a second time.
        st["harvested"] += len(new_events)
        st["events"] = (st["events"] + [k for k, _ in new_events])[-SEEN_CAP:]
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    st["last_scan"] = now_iso
    if not st["first_scan"]:
        st["first_scan"] = now_iso
    save_state(state_path, st)

    pending = max(0, st["harvested"] - st["distilled"])
    if files == 0:
        # A quiet day is not a failure. It is also not silence: the line below is
        # how you tell "I did no work" apart from "the harvester died in March".
        sys.stderr.write("no session log touched in the last %dd under: %s "
                         "(quiet day; nothing harvested)\n" % (days, ", ".join(dirs)))
    sys.stderr.write("files=%d hits=%d new_turns=%d new_events=%d pending=%d -> %s\n"
                     % (files, len(cands), len(fresh), len(new_events), pending, material))
    return 0


if __name__ == "__main__":
    sys.exit(main())
