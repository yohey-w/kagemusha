#!/usr/bin/env python3
"""discipline_scan.py — pull EVIDENCE CANDIDATES for your disciplines out of AI-CLI session logs.

You adopted some disciplines. Are they doing anything in your loop?
This script answers the only part of that question a machine can answer: it
walks your session logs for the last N days and, for every discipline in your
catalog, prints the passages that *look like* the discipline firing or being
broken — each with the original fragment and where it came from.

  ┌──────────────────────────────────────────────────────────────────────┐
  │ THIS SCRIPT DOES NOT JUDGE. It matches regexes and quotes text.       │
  │ A hit is a CANDIDATE, not a firing. Sorting candidates into fired /   │
  │ broken / can't-tell is the reviewer's job (a human, or an LLM given   │
  │ templates/discipline-audit-prompt.md). Candidates that the quoted     │
  │ text does not actually support must be thrown away, not counted.      │
  │ Keeping the matching dumb and the judging separate is the point: a    │
  │ scanner that scored itself would just be grading its own regexes.     │
  └──────────────────────────────────────────────────────────────────────┘

Two kinds of discipline, and the difference decides what the numbers mean:

  trace       — a discipline that COMMANDS AN ACTION ("write the scope before
                you write a negation", "read the write back"). Obeying it
                leaves a trace in the log, so firings are countable and a
                trace discipline with zero firings this week is a legitimate
                DEAD-LETTER CANDIDATE (a rule you carry but never use).
  prohibition — a discipline that COMMANDS RESTRAINT ("don't assert what you
                haven't checked", "never write 'exhaustive'"). Obeying it
                produces the sentence you did NOT write, which no log
                contains. Firings are UNOBSERVABLE. Only breaches show up.
                Zero hits on a prohibition is not evidence of anything, and
                this script will never call one a dead letter.

Usage:
  scripts/discipline_scan.py --catalog judgment/discipline_catalog.yaml \\
      [--since 7d] [--dir DIR ...] [--out FILE] [--max-samples 4] [--snippet 150]

  --catalog   your discipline catalog (start from
              templates/discipline_catalog.example.yaml)
  --dir       a directory of *.jsonl session logs; repeatable.
              Default: ~/.claude/projects/<slug of the current directory>,
              which is where Claude Code keeps this project's transcripts.
  --out       write the Markdown digest here ("-" = stdout, the default)

Exit codes: 0 ok · 2 bad usage / bad catalog / nothing to scan.
Scanning zero files is an ERROR, not an empty report: a report saying "no
evidence for any discipline" would read exactly like "every discipline is
dead", and those two must never be confusable.

Stdlib only. Reads logs; writes one file. Nothing leaves the machine.
"""
import datetime
import glob
import hashlib
import json
import os
import re
import sys

VALID_TYPES = ("trace", "prohibition")
VALID_ROLES = ("assistant", "user", "any")
CATALOG_KEYS = ("id", "type", "name", "origin", "role", "breach_role",
                "fire", "breach", "note")

# Session-log lines that are harness plumbing rather than anything anyone said.
SKIP_PREFIX = ("<command-name>", "<local-command", "<bash-stdout",
               "Caveat: The messages below", "[Request interrupted")


class CatalogError(Exception):
    pass


# ── catalog ────────────────────────────────────────────────────────────────
# A deliberately tiny YAML subset, parsed here so the kit stays stdlib-only
# (no PyYAML to install before you can audit anything). Supported:
#
#   disciplines:
#     - id: A6
#       type: trace
#       fire: 'regex|with|pipes'          # quote regexes: ' ' is literal
#
# · one `disciplines:` list of `- key: value` blocks, scalars only
# · 'single-quoted' (literal; '' means one quote) — use this for regexes
# · "double-quoted" (only \\ and \" are escapes)
# · bare values are taken literally to end of line, so a bare value CANNOT
#   carry a trailing # comment (a regex may legitimately contain '#')
# Anything richer is rejected loudly rather than half-understood.

def _scalar(raw, lineno):
    raw = raw.strip()
    if not raw:
        raise CatalogError("line %d: empty value" % lineno)
    q = raw[0]
    if q not in "'\"":
        return raw
    out, i, n = [], 1, len(raw)
    while i < n:
        c = raw[i]
        if c == q:
            if q == "'" and i + 1 < n and raw[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            rest = raw[i + 1:].strip()
            if rest and not rest.startswith("#"):
                raise CatalogError("line %d: trailing junk after quoted value: %r"
                                   % (lineno, rest))
            return "".join(out)
        if c == "\\" and q == '"' and i + 1 < n and raw[i + 1] in '"\\':
            out.append(raw[i + 1])
            i += 2
            continue
        out.append(c)
        i += 1
    raise CatalogError("line %d: unterminated %s-quoted value" % (lineno, q))


def parse_catalog(path):
    """Return a list of validated discipline dicts, or raise CatalogError."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as e:
        raise CatalogError("cannot read catalog: %s" % e)

    items, cur, in_list = [], None, False
    for lineno, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t", "-")):
            key = line.split(":", 1)[0].strip()
            if key != "disciplines":
                raise CatalogError("line %d: unknown top-level key %r "
                                   "(only 'disciplines:' is supported)" % (lineno, key))
            in_list = True
            continue
        if not in_list:
            raise CatalogError("line %d: content before 'disciplines:'" % lineno)
        body = line.strip()
        if body.startswith("- "):
            cur = {}
            items.append((cur, lineno))
            body = body[2:].strip()
        elif body.startswith("-"):
            raise CatalogError("line %d: '-' must be followed by a space" % lineno)
        if cur is None:
            raise CatalogError("line %d: key outside any list item" % lineno)
        if ":" not in body:
            raise CatalogError("line %d: expected 'key: value', got %r" % (lineno, body))
        key, raw = body.split(":", 1)
        key = key.strip()
        if key not in CATALOG_KEYS:
            raise CatalogError("line %d: unknown key %r (allowed: %s)"
                               % (lineno, key, ", ".join(CATALOG_KEYS)))
        if key in cur:
            raise CatalogError("line %d: duplicate key %r in one discipline" % (lineno, key))
        cur[key] = _scalar(raw, lineno)

    if not items:
        raise CatalogError("no disciplines found in %s" % path)

    out, seen = [], set()
    for d, lineno in items:
        where = "%s (item starting line %d)" % (d.get("id", "<no id>"), lineno)
        for req in ("id", "type", "name"):
            if req not in d:
                raise CatalogError("%s: missing required key %r" % (where, req))
        if d["id"] in seen:
            raise CatalogError("%s: duplicate id" % where)
        seen.add(d["id"])
        if d["type"] not in VALID_TYPES:
            raise CatalogError("%s: type must be one of %s" % (where, "/".join(VALID_TYPES)))
        for rk in ("role", "breach_role"):
            if d.get(rk, "assistant") not in VALID_ROLES:
                raise CatalogError("%s: %s must be one of %s"
                                   % (where, rk, "/".join(VALID_ROLES)))
        if d["type"] == "prohibition" and d.get("fire"):
            raise CatalogError(
                "%s: a prohibition cannot have a 'fire' pattern. Obeying a "
                "prohibition is the sentence you did not write; no log holds it. "
                "Give it a 'breach' pattern only — or, if you really can observe "
                "the compliance, the discipline is a trace and should say so."
                % where)
        if d["type"] == "trace" and not d.get("fire"):
            raise CatalogError("%s: a trace discipline needs a 'fire' pattern "
                               "(that is what makes it auditable)" % where)
        rec = dict(d)
        rec.setdefault("role", "assistant")
        rec.setdefault("breach_role", rec["role"])
        rec.setdefault("origin", "")
        try:
            rec["_fire"] = re.compile(d["fire"], re.I) if d.get("fire") else None
            rec["_breach"] = re.compile(d["breach"], re.I) if d.get("breach") else None
        except re.error as e:
            raise CatalogError("%s: bad regex: %s" % (where, e))
        out.append(rec)
    return out


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
    character of the absolute path becomes '-' (so /a/b-c → -a-b-c)."""
    return "".join(c if c.isalnum() and c.isascii() else "-" for c in os.path.abspath(path))


def default_dirs():
    return [os.path.join(os.path.expanduser("~"), ".claude", "projects",
                         project_slug(os.getcwd()))]


def die(msg):
    sys.stderr.write("discipline_scan: %s\n" % msg)
    sys.exit(2)


# ── log walk ───────────────────────────────────────────────────────────────
def text_of(content):
    """Message text, whichever shape the transcript uses.

    A user turn's `content` is often a BARE STRING while an assistant turn is a
    list of typed blocks. Handling only the list shape silently drops every
    human turn — which is most of the breach evidence — so both shapes are
    handled here and a regression test pins it.
    """
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


def scan(dirs, disciplines, cutoff, max_samples, snippet):
    hits = {d["id"]: {"fire": [], "breach": [], "fire_n": 0, "breach_n": 0}
            for d in disciplines}
    seen = set()
    files = msgs = 0
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
            with open(path, errors="replace") as fh:
                for line in fh:
                    # cheap prefilter — note it keys on the ROLE, never on
                    # '"text"', which would drop bare-string user turns
                    if '"assistant"' not in line and '"user"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    kind = obj.get("type")
                    if kind not in ("assistant", "user"):
                        continue
                    ts = obj.get("timestamp", "")
                    if not ts or ts < cut_s:
                        continue
                    txt = text_of((obj.get("message") or {}).get("content")).strip()
                    if not txt or txt.startswith(SKIP_PREFIX):
                        continue
                    if "<system-reminder>" in txt[:80]:
                        continue
                    role = "assistant" if kind == "assistant" else "user"
                    sub = bool(obj.get("isSidechain"))
                    msgs += 1
                    for d_ in disciplines:
                        for rex, slot, want in ((d_["_fire"], "fire", d_["role"]),
                                                (d_["_breach"], "breach", d_["breach_role"])):
                            if rex is None or (want != "any" and want != role):
                                continue
                            m = rex.search(txt)
                            if not m:
                                continue
                            start = max(0, m.start() - 40)
                            frag = txt[start:start + snippet].replace("\n", " ").strip()
                            key = hashlib.md5(
                                (d_["id"] + slot + frag[:80]).encode("utf-8")).hexdigest()
                            if key in seen:
                                continue
                            seen.add(key)
                            h = hits[d_["id"]]
                            h[slot + "_n"] += 1
                            if len(h[slot]) < max_samples:
                                h[slot].append({"ts": ts[:16].replace("T", " "),
                                                "src": src, "sub": sub, "frag": frag})
    return hits, files, msgs


def render(disciplines, hits, files, msgs, days, dirs, cutoff):
    L = ["# Discipline evidence candidates — last %d days (machine-extracted, UNJUDGED)" % days,
         "",
         "Scanned: %d session-log file(s), %d message(s), since %s"
         % (files, msgs, cutoff.isoformat()[:16]),
         "Log dirs: %s" % ", ".join(dirs),
         "",
         "**These are candidates, not findings.** Every line below is a regex hit with the",
         "original text attached. Read the fragment: if it does not actually support the",
         "discipline, drop it — do not count it. Counting regex hits is not measuring a",
         "discipline.",
         "",
         "- **trace** disciplines command an action, so firings leave a trace and are",
         "  countable. Zero firings this week = dead-letter candidate.",
         "- **prohibition** disciplines command restraint. Obeying one produces a sentence",
         "  that was never written, so firings are **unobservable** — only breaches show.",
         "  **Zero hits on a prohibition means nothing. Never call it a dead letter.**",
         "- `sub=1` marks a subagent's turn rather than the main thread's.",
         ""]
    dead = []
    for d in disciplines:
        h = hits[d["id"]]
        label = "trace" if d["type"] == "trace" else "prohibition"
        L.append("## %s [%s] %s" % (d["id"], label, d["name"]))
        if d["type"] == "trace":
            L.append("- source: %s / fire candidates: %d, breach candidates: %d"
                     % (d["origin"] or "—", h["fire_n"], h["breach_n"]))
        else:
            L.append("- source: %s / breach candidates: %d (firings unobservable by design)"
                     % (d["origin"] or "—", h["breach_n"]))
        if d.get("note"):
            L.append("- note: %s" % d["note"])
        for slot, name in (("fire", "FIRE"), ("breach", "BREACH")):
            for s in h[slot]:
                L.append("  - [%s] %s %s sub=%d: %s"
                         % (name, s["ts"], s["src"], 1 if s["sub"] else 0, s["frag"]))
        if h["fire_n"] == 0 and h["breach_n"] == 0:
            if d["type"] == "trace":
                dead.append(d["id"])
                L.append("  - (no evidence) → dead-letter candidate")
            else:
                L.append("  - (no breach found) → says nothing about compliance; "
                         "not a dead-letter candidate")
        L.append("")
    L.append("Trace disciplines with zero firing candidates: %s"
             % (", ".join(dead) if dead else "none"))
    return "\n".join(L) + "\n", dead


def main():
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        sys.stdout.write(__doc__)
        return 0

    catalog = opts(argv, "--catalog")
    if not catalog:
        die("--catalog is required (start from templates/discipline_catalog.example.yaml)")
    try:
        disciplines = parse_catalog(catalog)
    except CatalogError as e:
        die(str(e))

    raw_since = (opts(argv, "--since") or "7").strip().lower().rstrip("d")
    try:
        days = int(raw_since)
        if days <= 0:
            raise ValueError
    except ValueError:
        die("--since wants a positive number of days, e.g. 7 or 7d")
    try:
        max_samples = int(opts(argv, "--max-samples") or "4")
        snippet = int(opts(argv, "--snippet") or "150")
    except ValueError:
        die("--max-samples and --snippet want integers")

    dirs = [os.path.expanduser(p) for p in opts(argv, "--dir", multi=True)] or default_dirs()
    missing = [d for d in dirs if not os.path.isdir(d)]
    if len(missing) == len(dirs):
        die("no session-log directory found: %s\n"
            "  Pass --dir explicitly. (The default is derived from the current\n"
            "  directory; it only exists if this project has transcripts.)"
            % ", ".join(missing))

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    hits, files, msgs = scan(dirs, disciplines, cutoff, max_samples, snippet)
    if files == 0:
        # An empty report and "every discipline is dead" must never look alike.
        die("no session log from the last %d day(s) under: %s\n"
            "  Nothing was scanned, so no report is written." % (days, ", ".join(dirs)))

    body, dead = render(disciplines, hits, files, msgs, days, dirs, cutoff)
    out = opts(argv, "--out") or "-"
    if out == "-":
        sys.stdout.write(body)
    else:
        d = os.path.dirname(out)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(body)
        sys.stderr.write("scanned files=%d messages=%d -> %s\ntrace dead-letter candidates: %s\n"
                         % (files, msgs, out, ", ".join(dead) if dead else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
