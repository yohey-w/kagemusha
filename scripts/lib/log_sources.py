#!/usr/bin/env python3
"""One reader for the conversation logs of every AI CLI this kit supports.

Three scripts mine the same raw material — `mine_conversations.py` (the
approver's own turns), `correction_scan.py` (the moments he overruled the
agent), `discipline_scan.py` (whether the disciplines fire at all). Each of them
used to open `~/.claude/projects/*/*.jsonl` by hand. That was fine while there
was one CLI. There are now two, they write different shapes to different places,
and a copy of the parsing in each script is three places for the shapes to drift
apart.

So the walk lives here, once, behind a `LogSource`. The scripts keep their own
judgment about which turns matter — that is the interesting part and it differs
per script — and lose only the file-format knowledge.

The record
----------
`iter_records()` yields plain dicts. Every field is present on every record;
fields a CLI does not have are empty, never missing:

    source        "claude" | "codex" — which CLI wrote this line
    kind          "user" | "assistant" — the transcript's own record type
    role          alias of kind (what the scanners match `role` against)
    msg_role      the role inside the message envelope, when there is one
    ts            ISO-8601 timestamp string, as the log wrote it
    text          the turn's text, joined
    raw_content   the untouched content value, for a caller with a stricter
                  idea of what counts as text than `text_of()` here
    session_id    identity of THIS transcript file (full, never a prefix)
    parent_id     the parent thread, for a sub-agent transcript; else ""
    path          absolute path of the file the line came from
    line          1-based PHYSICAL line number in that file
    cwd           working directory the session ran in ("" if unrecorded)
    is_sidechain  True for sub-agent traffic (its "user" is another agent)
    is_meta       harness bookkeeping wearing a conversational role
    is_tool_result  tool output wearing the user role
    prompt_source how the turn arrived ("typed"/"queued"/… on Claude Code; the
                  session's own `source` on Codex, e.g. "exec"/"cli"/"vscode")
    originator    the client that wrote the session ("" if unrecorded)

`line` counts every physical line of the file, including the ones skipped
before parsing. It is half of correction_scan's event identity and that
identity is persisted: renumbering would re-fire every event already retired.

The two shapes
--------------
**Claude Code** — one `<session-uuid>.jsonl` per session under a per-project
directory (`~/.claude/projects/<slug>/`). One JSON object per line; the ones
worth reading have `type` of "user" or "assistant" and the text under
`message.content`. Sub-agent traffic is flagged inline (`isSidechain`) inside
the same file as its parent.

**Codex CLI** — one `rollout-<ISO>-<uuid>.jsonl` per session under a
date-partitioned tree (`~/.codex/sessions/YYYY/MM/DD/`). The first line is a
`session_meta` header (session id, cwd, originator, and — for a sub-agent —
`thread_source: "subagent"` plus `parent_thread_id`). Conversation turns are
`{"type": "response_item", "payload": {"type": "message", "role": …,
"content": [{"type": "input_text"|"output_text", "text": …}]}}`.

Three Codex-specific things this adapter absorbs, so the scanners never see
them:

  1. **Every turn is on the wire twice.** `event_msg` re-emits user and
     assistant messages (as `user_message`/`agent_message` on older builds,
     inside `item_completed` on newer ones) alongside the `response_item` that
     already carries them. Only `response_item` is read; counting both would
     double every hit.
  2. **The harness speaks in the user's voice.** `<environment_context>` rides
     along on 1 user message in 8 — usually as a SECOND part of the same
     message whose first part is the human's actual prompt. So injected parts
     are dropped per part, not per message; dropping the message would delete
     the prompt bundled with it. `developer` turns (the base instructions) are
     dropped whole.
  2b. **Another agent's session is not yours either.** Codex records who opened
     the session in `originator`; when that is another agent (`"Claude Code"`),
     the "user" turns in it were written by a machine. Same treatment as a
     sub-agent: `is_sidechain`, harvested by nobody.
  3. **Sub-agents get their own files.** Where Claude Code flags a sidechain
     line inside the parent's transcript, Codex writes the sub-agent a separate
     rollout whose header says `thread_source: "subagent"`. Every record from
     such a file is `is_sidechain`.

Verified against codex-cli 0.149.0 on 2026-09-06: rollout JSONL is still what a
live session writes (a `codex exec` run created
`~/.codex/sessions/2026/09/06/rollout-*.jsonl` with the full text in it). Newer
builds ALSO project the same session into `~/.codex/thread_history_*.sqlite`
(`history_mode: "paginated"` in the header says so). This reader uses the JSONL
only; see docs/distillation-loop.md for what happens if that changes.

Privacy: this reads YOUR OWN local logs and returns their text to the caller.
Nothing here leaves the machine.

Stdlib only.
"""
import datetime
import glob
import json
import os
import re

__all__ = [
    "CLAUDE", "CODEX", "SOURCE_CHOICES",
    "LogSource", "ClaudeProjectsSource", "CodexSessionsSource", "SessionFile",
    "build_sources", "text_of", "record_from_line", "source_of_path",
    "default_codex_roots", "default_claude_dirs", "split_dirs",
]

CLAUDE = "claude"
CODEX = "codex"
SOURCE_CHOICES = ("claude", "codex", "auto")

# Codex injects these in the user's voice. They are the harness talking, and on
# most turns they arrive bundled with the human's real prompt in the same
# message — which is why they are filtered per content part.
CODEX_INJECTED_PREFIXES = ("<environment_context>", "<recommended_plugins>")

# The uuid at the end of rollout-<ISO>-<uuid>.jsonl, used only as a fallback
# identity when a rollout has no readable header.
_ROLLOUT_UUID_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.jsonl$")

# How far into a rollout to look for the session_meta header before giving up.
_HEADER_SCAN_LINES = 8


def split_dirs(value):
    """Split a colon- or whitespace-separated directory list from the env."""
    if not value:
        return []
    return [p for p in re.split(r"[:\s]+", value.strip()) if p]


def default_claude_dirs():
    """Every project directory Claude Code has written, oldest name first."""
    return sorted(glob.glob(os.path.expanduser("~/.claude/projects/*")))


def default_codex_roots():
    """$CODEX_SESSIONS_DIR (colon-separated) if set, else ~/.codex/sessions."""
    env = split_dirs(os.environ.get("CODEX_SESSIONS_DIR", ""))
    return env or [os.path.expanduser("~/.codex/sessions")]


def default_codex_cwd():
    """$CODEX_CWD_FILTER — the project scope Codex's single tree does not give.

    Claude Code hands you one directory per project, so pointing a scan at a
    project is pointing it at a path. Codex files everything into one tree, so
    the equivalent has to be a filter, and a scheduled job needs somewhere to
    say it once.
    """
    return split_dirs(os.environ.get("CODEX_CWD_FILTER", ""))


def text_of(content):
    """Message text, whichever shape the transcript uses.

    A user turn's `content` is often a BARE STRING while an assistant turn is a
    list of typed blocks; a reader that handles only the list shape silently
    drops every human turn. Bare strings inside the list are kept too — an
    older Claude Code wrote them that way.
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


def _record(**kw):
    """A record with every field present. Missing is worse than empty: a caller
    that has to test for absence will forget on the one field that matters."""
    rec = {
        "source": "", "kind": "", "role": "", "msg_role": "",
        "ts": "", "text": "", "raw_content": None,
        "session_id": "", "parent_id": "", "path": "", "line": 0, "cwd": "",
        "is_sidechain": False, "is_meta": False, "is_tool_result": False,
        "prompt_source": "", "originator": "",
    }
    rec.update(kw)
    rec["role"] = rec["kind"]
    return rec


# ── one raw line -> one record ─────────────────────────────────────────────
def _claude_record(obj, path, lineno, session_id):
    if not isinstance(obj, dict):
        return None
    kind = obj.get("type")
    if kind not in ("user", "assistant"):
        return None
    msg = obj.get("message") or {}
    content = msg.get("content")
    return _record(
        source=CLAUDE, kind=kind, msg_role=msg.get("role") or "",
        ts=obj.get("timestamp", "") or "",
        text=text_of(content), raw_content=content,
        session_id=session_id, path=path, line=lineno,
        is_sidechain=bool(obj.get("isSidechain")),
        is_meta=bool(obj.get("isMeta") or obj.get("isCompactSummary")),
        is_tool_result=obj.get("toolUseResult") is not None,
        prompt_source=obj.get("promptSource", "") or "",
    )


def _codex_parts(content):
    """Drop the harness's own parts; return [{"type": "text", "text": …}].

    Normalising to Claude Code's block shape is not cosmetic: it means a caller
    with its own stricter `text_of` (mine_conversations keeps one) reads both
    CLIs through the same code path instead of growing a second branch.
    """
    if isinstance(content, str):
        content = [{"type": "input_text", "text": content}]
    if not isinstance(content, list):
        return []
    out = []
    for part in content:
        if isinstance(part, str):
            txt = part
        elif isinstance(part, dict):
            txt = part.get("text") or ""
        else:
            continue
        if not txt:
            continue
        if txt.lstrip().startswith(CODEX_INJECTED_PREFIXES):
            continue
        out.append({"type": "text", "text": txt})
    return out


def _codex_record(obj, path, lineno, header):
    if not isinstance(obj, dict):
        return None
    # response_item only. event_msg carries the SAME user and assistant turns a
    # second time (user_message/agent_message, or item_completed on 0.149+);
    # reading both would double every count downstream.
    if obj.get("type") != "response_item":
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    role = payload.get("role")
    if role not in ("user", "assistant"):
        return None                      # "developer" = the base instructions
    parts = _codex_parts(payload.get("content"))
    if not parts:
        return None                      # nothing left once the harness is cut
    return _record(
        source=CODEX, kind=role, msg_role=role,
        ts=obj.get("timestamp", "") or "",
        text=text_of(parts), raw_content=parts,
        session_id=header["session_id"], parent_id=header["parent_id"],
        path=path, line=lineno, cwd=header["cwd"],
        is_sidechain=header["is_sidechain"],
        prompt_source=header["prompt_source"],
        originator=header["originator"],
    )


def source_of_path(path):
    """Which CLI wrote this log file, by its name.

    Used to reopen one line long after the harvest (correction_scan's
    --show-event), where all that survives is the path.
    """
    return CODEX if os.path.basename(path).startswith("rollout-") else CLAUDE


def header_for(path, source=None):
    """The per-file header a later `record_from_line` on this path will need.

    Claude Code needs none — every line carries its own flags. A Codex rollout
    keeps cwd and the sub-agent marking in one header line at the top, so
    reopening a line months later means reading that header again.
    """
    source = source or source_of_path(path)
    return _codex_header(path) if source == CODEX else None


def record_from_line(line, path, lineno, source=None, header=None):
    """Parse one raw log line into a record, or None. Never raises."""
    source = source or source_of_path(path)
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    if source == CODEX:
        return _codex_record(obj, path, lineno, header or _empty_codex_header(path))
    return _claude_record(obj, path, lineno, _claude_session_id(path))


def _claude_session_id(path):
    """Claude Code names the file after the session. The FULL id, not a prefix:
    a prefix is fine for display and fatal for identity."""
    base = os.path.basename(path)
    return base[:-len(".jsonl")] if base.endswith(".jsonl") else base


def _empty_codex_header(path):
    m = _ROLLOUT_UUID_RE.search(os.path.basename(path))
    return {"session_id": m.group(1) if m else os.path.basename(path),
            "parent_id": "", "cwd": "", "is_sidechain": False,
            "prompt_source": "", "originator": ""}


def _codex_header(path):
    """Read the session_meta line at the top of a rollout.

    `id` is this transcript; `session_id` in the header is the ROOT thread,
    which for a sub-agent is its parent. Identity has to be per file, so `id`
    wins — two sub-agents of one parent must not share a namespace.
    """
    head = _empty_codex_header(path)
    try:
        with open(path, errors="replace") as fh:
            for _ in range(_HEADER_SCAN_LINES):
                line = fh.readline()
                if not line:
                    break
                if '"session_meta"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") != "session_meta":
                    continue
                pl = obj.get("payload")
                if not isinstance(pl, dict):
                    continue
                src = pl.get("source")
                originator = pl.get("originator") or ""
                # A sub-agent says so three ways; any one of them is enough,
                # because which ones a given build writes has changed before.
                #
                # The FOURTH way is the originator, and it is the one that
                # matters most here: a session Codex opened because another
                # agent asked it to (`originator: "Claude Code"` — 53 such
                # lines in this machine's own tree) is not you talking. Harvest
                # it as yours and the distillation lane learns from an agent's
                # instructions to an agent, which is exactly the corruption
                # `is_sidechain` exists to prevent. Whoever wrote that prompt,
                # it was not a human overruling anybody.
                sidechain = (pl.get("thread_source") == "subagent"
                             or bool(pl.get("parent_thread_id"))
                             or (isinstance(src, dict) and "subagent" in src)
                             or originator.startswith("Claude Code"))
                head.update({
                    "session_id": pl.get("id") or pl.get("session_id") or head["session_id"],
                    "parent_id": pl.get("parent_thread_id") or "",
                    "cwd": pl.get("cwd") or "",
                    "is_sidechain": sidechain,
                    # `source` is a plain string on a user session and a nested
                    # object on a sub-agent's; only the string is a source name.
                    "prompt_source": src if isinstance(src, str) else "subagent",
                    "originator": originator,
                })
                break
    except OSError:
        pass
    return head


# ── files and sources ──────────────────────────────────────────────────────
class SessionFile(object):
    """One transcript file, its header already read.

    The header is separate from the records because callers filter on it —
    by cwd, by sidechain — and opening every rollout in a year of sessions to
    find out which project it belonged to is the slow way to answer that.
    """

    def __init__(self, source, path, session_id, cwd="", parent_id="",
                 is_sidechain=False, header=None):
        self.source = source
        self.path = path
        self.session_id = session_id
        self.cwd = cwd
        self.parent_id = parent_id
        self.is_sidechain = is_sidechain
        self._header = header

    def records(self):
        """Yield every conversational record in the file, in file order."""
        try:
            fh = open(self.path, errors="replace")
        except OSError:
            return
        with fh:
            lineno = 0
            for line in fh:
                lineno += 1                      # every physical line, always
                if self.source == CLAUDE:
                    # Cheap prefilter: a record whose type is "user" or
                    # "assistant" always contains that word literally. Keyed on
                    # the ROLE and never on '"text"', which would drop the
                    # bare-string user turns.
                    if '"user"' not in line and '"assistant"' not in line:
                        continue
                    rec = record_from_line(line, self.path, lineno, CLAUDE)
                else:
                    if '"message"' not in line:
                        continue
                    rec = record_from_line(line, self.path, lineno, CODEX,
                                           self._header)
                if rec is not None:
                    yield rec


class LogSource(object):
    """A place conversation logs live, and the walk over it."""

    name = ""

    def __init__(self, dirs):
        self.dirs = [os.path.expanduser(d) for d in dirs]

    def existing_dirs(self):
        return [d for d in self.dirs if os.path.isdir(d)]

    def describe(self):
        return "%s: %s" % (self.name, ", ".join(self.dirs) or "(none)")

    def iter_files(self, since=None):
        raise NotImplementedError

    def iter_records(self, since=None):
        for sf in self.iter_files(since):
            for rec in sf.records():
                yield rec

    @staticmethod
    def _too_old(path, since):
        if since is None:
            return False
        try:
            return os.path.getmtime(path) < since.timestamp()
        except OSError:
            return True


class ClaudeProjectsSource(LogSource):
    """~/.claude/projects/<slug>/<session-uuid>.jsonl — one file per session."""

    name = CLAUDE

    def iter_files(self, since=None):
        for d in self.dirs:
            if not os.path.isdir(d):
                continue
            for path in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
                if self._too_old(path, since):
                    continue
                yield SessionFile(CLAUDE, path, _claude_session_id(path))


class CodexSessionsSource(LogSource):
    """~/.codex/sessions/YYYY/MM/DD/rollout-<ISO>-<uuid>.jsonl.

    One tree for every project, so `cwd_filter` is how you get back the
    per-project scope that Claude Code gives you by directory. Without it, a
    scan run inside one repo reports on all of them.
    """

    name = CODEX

    def __init__(self, dirs, cwd_filter=None):
        LogSource.__init__(self, dirs)
        self.cwd_filter = [os.path.abspath(os.path.expanduser(c))
                           for c in (cwd_filter or [])]

    def _wanted_cwd(self, cwd):
        if not self.cwd_filter:
            return True
        if not cwd:
            return False
        cwd = os.path.abspath(os.path.expanduser(cwd))
        return any(cwd == c or cwd.startswith(c + os.sep) for c in self.cwd_filter)

    def iter_files(self, since=None):
        for root in self.dirs:
            if not os.path.isdir(root):
                continue
            paths = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames.sort()
                for fn in filenames:
                    if fn.startswith("rollout-") and fn.endswith(".jsonl"):
                        paths.append(os.path.join(dirpath, fn))
            for path in sorted(paths):
                if self._too_old(path, since):
                    continue
                header = _codex_header(path)
                if not self._wanted_cwd(header["cwd"]):
                    continue
                yield SessionFile(CODEX, path, header["session_id"],
                                  cwd=header["cwd"], parent_id=header["parent_id"],
                                  is_sidechain=header["is_sidechain"],
                                  header=header)


def resolve_source_name(source=None, claude_named=False, codex_named=False):
    """Which CLI to read, when the caller did not say outright.

    Naming a log directory for one CLI is itself a statement of scope. A run
    told exactly where the Claude Code transcripts are must not ALSO swallow a
    year of Codex sessions out of the default tree — the caller who typed
    `--dir` was drawing a boundary, and a default that walks around it is the
    kind of help nobody asked for. Only when neither side was named does `auto`
    mean "every CLI present on this machine".
    """
    if source:
        return source
    env = (os.environ.get("LOG_SOURCE") or "").strip()
    if env:
        return env
    if claude_named and not codex_named:
        return CLAUDE
    if codex_named and not claude_named:
        return CODEX
    return "auto"


def build_sources(source=None, claude_dirs=None, codex_dirs=None, codex_cwd=None):
    """Return the LogSources to read, in reading order (Claude first).

    `source` is "claude", "codex", or "auto" (default, or $LOG_SOURCE). Under
    "auto" a CLI is included only if its log tree actually exists on this
    machine, so a one-CLI box needs no configuration. Naming a CLI explicitly
    always returns it, present or not — "you asked for Codex and there are no
    Codex logs" is the caller's error to report, not a silent empty scan.
    """
    source = (source or os.environ.get("LOG_SOURCE") or "auto").strip().lower()
    if source == "both":                 # a natural way to say it; accept it
        source = "auto"
    if source not in SOURCE_CHOICES:
        raise ValueError("unknown log source %r (want one of: %s)"
                         % (source, ", ".join(SOURCE_CHOICES)))
    out = []
    if source in (CLAUDE, "auto"):
        dirs = list(claude_dirs) if claude_dirs else default_claude_dirs()
        src = ClaudeProjectsSource(dirs)
        if source == CLAUDE or src.existing_dirs():
            out.append(src)
    if source in (CODEX, "auto"):
        roots = list(codex_dirs) if codex_dirs else default_codex_roots()
        src = CodexSessionsSource(roots, cwd_filter=codex_cwd or default_codex_cwd())
        if source == CODEX or src.existing_dirs():
            out.append(src)
    return out


def iter_all_files(sources, since=None):
    for src in sources:
        for sf in src.iter_files(since):
            yield sf


def parse_since(value, default=None):
    """'7d' / '7' / '2026-09-01' -> a number of days (int), or `default`.

    An absolute date is accepted because that is how a human says "since the
    release", and converting it here means every script takes both spellings.
    """
    if value is None:
        return default
    v = str(value).strip().lower()
    if not v:
        return default
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        day = datetime.datetime.strptime(v, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        days = (now - day).days + 1
        return max(days, 1)
    v = v.rstrip("d")
    return int(v)                        # ValueError is the caller's to report
