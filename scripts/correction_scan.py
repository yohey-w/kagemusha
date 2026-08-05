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

**Every harvested turn keeps a way back to the log line it came from.** A quote
truncated to 300 characters, attributed to "session a1b2c3d4" at minute
resolution, is not something you can open again — and the review step is exactly
where you need the surrounding turns to decide whether a correction meant what
it looks like it meant. So each candidate records the FULL session id, the byte
line number, the full timestamp and a SHA-256 of the untruncated text, in a
sidecar index next to the material file, and `--show-event` reopens it.

That same record identity is what dedup keys on. Keying on "session prefix +
first 120 characters" looks fine until you say "違う" twice in one long-running
session on different days: the second one hashes identically to the first and is
dropped as already-seen. A correction you made is not a duplicate of a different
correction that happens to be worded the same.

**The pending counter is a set of event ids, not an integer.** A count cannot
say WHICH events a distillation actually read, so advancing it wholesale marks
material as processed that never rode in the prompt — everything the line cap
cut off, plus anything the scanner appended while the model was running. Instead
`--emit-batch` freezes an explicit batch (id, event ids, sha256 of the exact
text), and `--mark-distilled --batch` retires only the ids in that manifest.

Usage:
  scripts/correction_scan.py --patterns FILE --material FILE --state FILE
                             [--since 1d] [--dir DIR ...]
                             [--snippet 300] [--lead 160] [--cluster-window 20]
  scripts/correction_scan.py --state FILE --status
  scripts/correction_scan.py --state FILE --material FILE --emit-batch
                             --batch-dir DIR [--max-lines 400]
  scripts/correction_scan.py --batch FILE --check-output FILE
  scripts/correction_scan.py --state FILE --material FILE --mark-distilled
                             --batch FILE
  scripts/correction_scan.py --material FILE --show-event E-xxxxxxxxxx [--context 3]

  --patterns  your correction patterns, one regex per line ('#' comments).
              REQUIRED — there is no built-in list. Start from
              templates/correction_patterns.example.txt and cut it down: the
              phrases you use when you overrule someone are yours, and a
              vocabulary shipped in the script would quietly become everyone's.
  --material  the append-only material file candidates are added to
  --state     small JSON file: events harvested, events distilled, when
  --dir       a directory of *.jsonl session logs; repeatable.
              If omitted, DISTILL_LOG_DIRS (from config.env, whitespace- or
              colon-separated) is used. Only if that is unset too does the
              path get GUESSED from the current directory — which under cron
              is $HOME, i.e. the wrong project. That guess now says so, loudly,
              on stderr: a scheduler running with the wrong CWD used to harvest
              a different project's logs, or nothing at all, in silence.
  --status    print pending / harvested / days-since-distill and exit
  --emit-batch  freeze the next batch: write <batch-dir>/<id>.txt (the exact
              material the model will see, whole events only, oldest first, up
              to --max-lines) and <batch-dir>/<id>.json (the manifest: batch id,
              the event ids in it, and the sha256 of that text). Prints the two
              paths. Events that did not fit stay pending for the next run.
  --check-output  validate a model's stdout against a manifest: every event id
              in the batch must be accounted for as processed / no_reason /
              rejected, and no id may be invented. Prints the queue section to
              stdout on success; exits 3 with a reason on failure.
  --mark-distilled --batch FILE  retire exactly the event ids in that manifest
              and append a marker line to the material file. scripts/distill.sh
              calls this ONLY after a validated run.
  --show-event  reopen one event: the full original text of every turn in it,
              plus the surrounding turns, from the log file it came from.

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
STATE_VERSION = 2
INDEX_SUFFIX = ".index.jsonl"

# The fences the distilling model must print around its two blocks. Free prose
# either side is fine and ignored; what is NOT fine is a run whose output cannot
# be told apart from a run that produced nothing, which is why the wrapper
# refuses anything it cannot find these in.
Q_OPEN, Q_CLOSE = "<<<QUEUE-SECTION>>>", "<<<END-QUEUE-SECTION>>>"
D_OPEN, D_CLOSE = "<<<EVENT-DISPOSITION>>>", "<<<END-EVENT-DISPOSITION>>>"
DISPOSITIONS = ("processed", "no_reason", "rejected")


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
    """Log directories when --dir was not given.

    Order matters. DISTILL_LOG_DIRS is a stated answer; the CWD-derived path is
    a GUESS, and under cron it is reliably the wrong one (cron's working
    directory is $HOME, not your project). The guess stays — it is what makes
    the tool pleasant to run by hand — but it announces itself, because a
    harvester quietly pointed at the wrong project looks exactly like a quiet
    week for as long as nobody checks.
    """
    env = os.environ.get("DISTILL_LOG_DIRS", "").strip()
    if env:
        parts = [p for p in re.split(r"[:\s]+", env) if p]
        return [os.path.expanduser(p) for p in parts]
    guess = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                         project_slug(os.getcwd()))
    sys.stderr.write(
        "correction_scan: no --dir and no DISTILL_LOG_DIRS; GUESSING from the\n"
        "  current directory (%s) -> %s\n"
        "  Under cron the current directory is $HOME, so this guess is wrong there.\n"
        "  Pass --dir explicitly in the cron line, or set DISTILL_LOG_DIRS.\n"
        % (os.getcwd(), guess))
    return [guess]


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
    if st and int(st.get("version", 1)) < STATE_VERSION:
        # v1 counted pending as an integer, which cannot say WHICH events a run
        # actually distilled. There is no way to reconstruct the ids after the
        # fact, and guessing them is the very failure the version bump fixes, so
        # this stops instead of migrating silently.
        die("state file %s is version %s; this script needs version %d.\n"
            "  v1 tracked pending work as a bare count, which cannot name the events a\n"
            "  distillation actually read. The ids cannot be recovered from a count.\n"
            "  Delete the state file to restart the counter (your material file and its\n"
            "  index are untouched; only the not-yet-distilled bookkeeping resets)."
            % (path, st.get("version", 1), STATE_VERSION))
    st.setdefault("version", STATE_VERSION)
    st.setdefault("harvested", 0)        # EVENTS, not candidate lines
    st.setdefault("distilled", 0)
    st.setdefault("first_scan", None)    # when this loop's clock started
    st.setdefault("last_scan", None)
    st.setdefault("last_distill", None)
    st.setdefault("seen", [])            # candidate record identities
    st.setdefault("events", [])          # event ids ever counted
    st.setdefault("pending_ids", [])     # event ids harvested but not distilled
    return st


def pending_of(st):
    """Pending is the SIZE OF A SET, never a subtraction. Two counters that are
    supposed to differ by the outstanding work drift the moment anything is
    retired out of order; a set of ids cannot drift, and it can also say which."""
    return len(st["pending_ids"])


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
            # The FULL session id, not a prefix. A prefix is fine for display and
            # fatal for identity: it is half of the dedup key, and two sessions
            # sharing eight hex characters would silently share a namespace.
            session = os.path.basename(path)
            if session.endswith(".jsonl"):
                session = session[:-len(".jsonl")]
            prior = ""                     # last assistant turn seen in this file
            lineno = 0
            with open(path, errors="replace") as fh:
                for line in fh:
                    lineno += 1
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
                    # Identity is the LOG RECORD, not the words in it. Keying on
                    # the text would make "違う", said twice in one long session
                    # on different days, one event — the second one dropped as
                    # already seen. Two identical sentences are two corrections
                    # when they sit on two different lines of the transcript.
                    sha = hashlib.sha256(txt.encode("utf-8")).hexdigest()
                    ident = "%s|%d|%s|%s" % (session, lineno, ts, sha)
                    found.append({
                        "ts": ts[:16].replace("T", " "),
                        "raw_ts": ts,
                        "session": session,
                        "src": session[:8],          # display only
                        "file": os.path.abspath(path),
                        "line": lineno,
                        "sha256": sha,
                        "pat": hit[:24],
                        "text": body,
                        "prior": ctx,
                        "key": hashlib.sha256(ident.encode("utf-8")).hexdigest()[:32],
                    })
    found.sort(key=lambda c: (c["raw_ts"], c["session"], c["line"]))
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
        # Prefixed and short enough to retype: an event id is something a human
        # pastes into --show-event, and something the distilling model must echo
        # back per event, so it has to survive being read off a screen.
        ckey = "E-" + hashlib.sha256(("%s|%s" % (c["session"], bucket))
                                     .encode("utf-8")).hexdigest()[:10]
        if ckey not in groups:
            groups[ckey] = []
            order.append(ckey)
        groups[ckey].append(c)
    return [(k, groups[k]) for k in order]


def shown_ts(rec):
    """'YYYY-MM-DD HH:MM' from either shape of record.

    Fresh candidates carry a pre-formatted "ts"; index records carry the full
    ISO timestamp under the same key, because the index's job is to be exact.
    Normalising here keeps the material file and the batch text byte-identical
    for the same event — which matters, because the batch is hashed.
    """
    return str(rec.get("ts", ""))[:16].replace("T", " ")


def render_event(ckey, members):
    """One event, in the shape both the material file and the batch use."""
    head = members[0]
    L = ["- event %s — [%s] session %s, %d turn(s) (pat: %s)"
         % (ckey, shown_ts(head), head["session"], len(members), head["pat"])]
    if head["prior"]:
        L.append("  - in reply to: ...%s" % head["prior"])
    for m in members:
        # The provenance rides WITH the quote, not in a footnote. A reviewer who
        # has to go looking for the source of a truncated line does not go.
        L.append("  - you [%s] (%s:%d): %s"
                 % (shown_ts(m)[11:], m["session"], m["line"], m["text"]))
    return L


def render(events, days, dirs, window):
    stamp = datetime.datetime.now().strftime("%F %T")
    L = ["", "## %s — %d event(s), window %dd" % (stamp, len(events), days),
         "<!-- machine-extracted, UNJUDGED. dirs: %s / grouping: session + %dmin bucket -->"
         % (", ".join(dirs), window),
         "<!-- reopen any of these in full: correction_scan.py --material FILE --show-event E-xxxxxxxxxx -->",
         ""]
    for ckey, members in events:
        L.extend(render_event(ckey, members))
    return "\n".join(L) + "\n"


# ── provenance index ───────────────────────────────────────────────────────
def index_path(material):
    return material + INDEX_SUFFIX


def index_append(material, events):
    """One JSONL record per harvested turn, next to the material file.

    The material file is for a human to read, so its quotes are truncated and
    its attribution is short. This is the other half: everything needed to open
    the original line again — full session, absolute path, line number, full
    timestamp, sha256 of the untruncated text — kept out of the reading path so
    that neither file has to compromise for the other.
    """
    path = index_path(material)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for ckey, members in events:
            for m in members:
                fh.write(json.dumps({
                    "event": ckey, "key": m["key"], "session": m["session"],
                    "file": m["file"], "line": m["line"], "ts": m["raw_ts"],
                    "sha256": m["sha256"], "pat": m["pat"],
                    "text": m["text"], "prior": m["prior"],
                }, ensure_ascii=False) + "\n")


def index_load(material):
    """[(event_id, [records...])] in first-seen order."""
    path = index_path(material)
    groups = {}
    order = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ev = rec.get("event")
                if not ev:
                    continue
                if ev not in groups:
                    groups[ev] = []
                    order.append(ev)
                groups[ev].append(rec)
    except FileNotFoundError:
        return []
    except OSError as e:
        die("cannot read the material index %s: %s" % (path, e))
    return [(ev, groups[ev]) for ev in order]


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
    pending = pending_of(st)
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


def do_emit_batch(state_path, material, batch_dir, max_lines):
    """Freeze exactly what the next distillation will see, and name it.

    Two silent losses live in the alternative ("take the tail of the material
    file and afterwards mark everything as done"):
      · the LINE CAP cuts from the head, so the oldest events — the ones that
        have waited longest — are the first to be dropped, and then retired as
        though they had been read;
      · the daily harvest keeps appending WHILE the model runs, so anything that
        lands mid-flight is retired without ever having been in a prompt.
    Both disappear once the batch is a fixed list of event ids: whole events
    only, oldest first, and whatever did not fit is simply still pending.
    """
    st = load_state(state_path)
    pending_ids = list(st["pending_ids"])
    if not pending_ids:
        die("nothing pending: no batch to emit")
    by_event = dict(index_load(material))

    chosen, lines = [], []
    for ev in pending_ids:                      # oldest first — harvest order
        recs = by_event.get(ev)
        if not recs:
            continue                            # index pruned or moved; skip it
        block = render_event(ev, recs)
        if lines and len(lines) + len(block) > max_lines:
            break                               # whole events only, never half
        chosen.append(ev)
        lines.extend(block)
    if not chosen:
        die("no pending event could be rendered from the index %s\n"
            "  (the state says %d pending; the index knows none of them)"
            % (index_path(material), len(pending_ids)))

    text = "\n".join(lines) + "\n"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    bid = "B-%s-%s" % (datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), sha[:8])
    os.makedirs(batch_dir, exist_ok=True)
    txt_path = os.path.join(batch_dir, bid + ".txt")
    json_path = os.path.join(batch_dir, bid + ".json")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"batch_id": bid,
                   "created": datetime.datetime.now(datetime.timezone.utc)
                              .isoformat(timespec="seconds"),
                   "material_file": material,
                   "text_file": txt_path,
                   "text_sha256": sha,
                   "line_count": len(lines),
                   "event_ids": chosen,
                   "deferred_event_ids": [e for e in pending_ids if e not in chosen]},
                  fh, ensure_ascii=False, indent=1)
    sys.stdout.write("batch_id=%s\ntext=%s\nmanifest=%s\nevents=%d\ndeferred=%d\n"
                     % (bid, txt_path, json_path, len(chosen),
                        len(pending_ids) - len(chosen)))
    return 0


def load_batch(path):
    try:
        with open(path, encoding="utf-8") as fh:
            man = json.load(fh)
    except (OSError, ValueError) as e:
        die("cannot read the batch manifest %s: %s" % (path, e))
    if not man.get("event_ids"):
        die("batch manifest %s names no events" % path)
    return man


def between(text, open_tag, close_tag):
    i = text.find(open_tag)
    if i < 0:
        return None
    j = text.find(close_tag, i + len(open_tag))
    if j < 0:
        return None
    return text[i + len(open_tag):j].strip("\n")


def do_check_output(batch_path, out_path):
    """Gate between the model's stdout and the review queue.

    The model is not trusted to write the queue (it has no file tools), and it
    is not trusted to have READ what it was sent either. The manifest says which
    events went in; the output has to account for every one of them — as a
    candidate, as "no reason on record", or as rejected — and may not name an
    event that was not in the batch. Anything short of that is a FAILED run, and
    the material stays pending. Partial credit here is how a batch gets marked
    distilled on the strength of the two events the model happened to notice.
    """
    man = load_batch(batch_path)
    try:
        with open(out_path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError as e:
        die("cannot read the model output %s: %s" % (out_path, e))

    def reject(msg):
        sys.stderr.write("correction_scan: batch %s REJECTED: %s\n" % (man["batch_id"], msg))
        sys.exit(3)

    section = between(raw, Q_OPEN, Q_CLOSE)
    if section is None:
        reject("no %s ... %s block in the output (%d bytes read)"
               % (Q_OPEN, Q_CLOSE, len(raw)))
    if not section.strip():
        reject("the queue section is empty; a run that says nothing is "
               "indistinguishable from a run that never happened")
    disp = between(raw, D_OPEN, D_CLOSE)
    if disp is None:
        reject("no %s ... %s block; the run cannot say which events it read" % (D_OPEN, D_CLOSE))

    seen, dup = {}, []
    for line in disp.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        label, rest = line.split(":", 1)
        label = label.strip().lower()
        if label not in DISPOSITIONS:
            continue
        for ev in re.split(r"[,\s]+", rest.strip()):
            if not ev:
                continue
            if ev in seen:
                dup.append(ev)
            seen[ev] = label

    want = set(man["event_ids"])
    got = set(seen)
    if dup:
        reject("event(s) filed under two dispositions at once: %s" % ", ".join(sorted(set(dup))))
    missing = sorted(want - got)
    extra = sorted(got - want)
    if missing:
        reject("%d event(s) in the batch are unaccounted for: %s"
               % (len(missing), ", ".join(missing)))
    if extra:
        reject("%d event id(s) not in this batch were reported: %s "
               "(invented ids mean the output is about material it did not receive)"
               % (len(extra), ", ".join(extra)))
    sys.stdout.write(section.rstrip("\n") + "\n")
    sys.stderr.write("batch %s ok: %d event(s) accounted for (%s)\n"
                     % (man["batch_id"], len(want),
                        ", ".join("%s=%d" % (d, sum(1 for v in seen.values() if v == d))
                                  for d in DISPOSITIONS)))
    return 0


def do_mark(state_path, material, batch_path):
    st = load_state(state_path)
    man = load_batch(batch_path)
    ids = [e for e in man["event_ids"]]
    unknown = [e for e in ids if e not in st["pending_ids"]]
    st["pending_ids"] = [e for e in st["pending_ids"] if e not in set(ids)]
    st["distilled"] += len(ids) - len(unknown)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    st["last_distill"] = now
    save_state(state_path, st)
    if material:
        append(material, "\n%s%s (batch %s, %d event(s): %s) -->\n"
               % (MARKER, now, man["batch_id"], len(ids), " ".join(ids)))
    sys.stderr.write("marked %d event(s) as distilled (batch %s); %d still pending%s\n"
                     % (len(ids), man["batch_id"], pending_of(st),
                        "" if not unknown else
                        "; %d id(s) were not pending and were ignored" % len(unknown)))
    return 0


def do_show_event(material, event_id, context):
    """Reopen an event: full original text, plus the turns around it.

    A truncated quote is enough to notice a correction and never enough to judge
    one — "you were told to stop" is equally explained by several principles, and
    which one it was is in the turns either side. Provenance that cannot be
    followed is decoration.
    """
    hits = [(ev, recs) for ev, recs in index_load(material) if ev == event_id]
    if not hits:
        die("no such event in %s: %s\n"
            "  (event ids look like E-1a2b3c4d5e and appear in the material file)"
            % (index_path(material), event_id))
    out = sys.stdout
    for ev, recs in hits:
        out.write("event %s — %d turn(s)\n" % (ev, len(recs)))
        for rec in recs:
            out.write("\n%s\n  %s:%s  %s  (pattern: %s)\n"
                      % ("-" * 70, rec["file"], rec["line"], rec["ts"], rec.get("pat", "?")))
            lines = []
            try:
                with open(rec["file"], errors="replace") as fh:
                    lines = fh.readlines()
            except OSError as e:
                out.write("  [the log file is gone or unreadable: %s]\n" % e)
                out.write("  harvested text (truncated at harvest): %s\n" % rec["text"])
                continue
            idx = rec["line"] - 1
            if not (0 <= idx < len(lines)):
                out.write("  [line %d no longer exists in this file]\n" % rec["line"])
                continue
            obj = None
            try:
                obj = json.loads(lines[idx])
            except ValueError:
                pass
            got = usable(obj) if isinstance(obj, dict) else None
            if not got:
                out.write("  [line %d is no longer the record it was]\n" % rec["line"])
                continue
            full = got[1]
            # A log that has been rewritten under you is a fact worth printing,
            # not a detail to smooth over: the quote you are about to weigh may
            # not be the text that was harvested.
            if hashlib.sha256(full.encode("utf-8")).hexdigest() != rec["sha256"]:
                out.write("  ⚠ CONTENT CHANGED since harvest (sha256 mismatch) —\n"
                          "    what follows is the log as it reads NOW.\n")
            out.write("\n  >>> the correction, in full:\n")
            for ln in full.splitlines() or [""]:
                out.write("  | %s\n" % ln)
            before, after = [], []
            i = idx - 1
            while i >= 0 and len(before) < context:
                try:
                    o = json.loads(lines[i])
                except ValueError:
                    i -= 1
                    continue
                g = usable(o)
                if g:
                    before.append((i + 1, g))
                i -= 1
            i = idx + 1
            while i < len(lines) and len(after) < context:
                try:
                    o = json.loads(lines[i])
                except ValueError:
                    i += 1
                    continue
                g = usable(o)
                if g:
                    after.append((i + 1, g))
                i += 1
            for label, seq in (("before", list(reversed(before))), ("after", after)):
                if not seq:
                    continue
                out.write("\n  --- %s ---\n" % label)
                for lno, (role, txt) in seq:
                    out.write("  [%s L%d] %s\n" % (role, lno, " ".join(txt.split())[:400]))
    return 0


def main():
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        sys.stdout.write(__doc__)
        return 0

    # Two modes read nothing and advance nothing, so they need no state file:
    # validating a model's output against a manifest, and reopening one event.
    if "--check-output" in argv:
        batch = opts(argv, "--batch")
        if not batch:
            die("--check-output requires --batch FILE (the manifest it is checked against)")
        return do_check_output(os.path.expanduser(batch),
                               os.path.expanduser(opts(argv, "--check-output")))
    if "--show-event" in argv:
        mat = opts(argv, "--material")
        if not mat:
            die("--show-event requires --material FILE (its index holds the provenance)")
        try:
            ctx = int(opts(argv, "--context") or "3")
        except ValueError:
            die("--context wants an integer number of surrounding turns")
        return do_show_event(os.path.expanduser(mat), opts(argv, "--show-event"), ctx)

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
        batch = opts(argv, "--batch")
        if not batch:
            die("--mark-distilled now requires --batch FILE.\n"
                "  Retiring 'everything harvested so far' silently discards whatever the\n"
                "  line cap cut off and whatever the harvester appended while the model was\n"
                "  running. Only the events named in a batch manifest may be retired.")
        if not material:
            die("--material is required with --mark-distilled (the marker is appended to it)")
        return do_mark(state_path, material, os.path.expanduser(batch))
    if "--emit-batch" in argv:
        if not material:
            die("--material is required with --emit-batch (the index lives beside it)")
        batch_dir = opts(argv, "--batch-dir")
        if not batch_dir:
            die("--emit-batch requires --batch-dir DIR (where the frozen batch is written)")
        try:
            max_lines = int(opts(argv, "--max-lines") or "400")
            if max_lines <= 0:
                raise ValueError
        except ValueError:
            die("--max-lines wants a positive integer")
        return do_emit_batch(state_path, material, os.path.expanduser(batch_dir), max_lines)

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
        index_append(material, events)
        st["seen"] = (st["seen"] + [c["key"] for c in fresh])[-SEEN_CAP:]
        # Only clusters never counted before move the pending needle. A late turn
        # joining an event that already fired must not fire it a second time.
        st["harvested"] += len(new_events)
        st["events"] = (st["events"] + [k for k, _ in new_events])[-SEEN_CAP:]
        # Pending is a queue of ids, in harvest order, so a batch can take the
        # OLDEST first. The tail-of-file cap used to drop exactly these.
        st["pending_ids"] = st["pending_ids"] + [k for k, _ in new_events]
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    st["last_scan"] = now_iso
    if not st["first_scan"]:
        st["first_scan"] = now_iso
    save_state(state_path, st)

    pending = pending_of(st)
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
