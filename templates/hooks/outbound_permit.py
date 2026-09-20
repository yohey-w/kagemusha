#!/usr/bin/env python3
"""Issue and atomically claim one-shot permits for an approved exact send.

A permit records approval; it never creates approval.  Run ``review`` first,
then ``issue`` only when an operator can cite the user's explicit assent.  The
boundary assumes agents cannot modify this project or invoke this operator
helper without authorization; an adversary with workspace-write access is out
of scope.

ONE HELPER, TWO CLIs.  ``--cli codex`` (the default, so an existing Codex
install keeps working unchanged) and ``--cli claude`` select which pair of
exact wire tool names a permit may name, and which directory the permit store
lives in: ``<project>/.codex/outbound-permits`` or
``<project>/.claude/outbound-permits``.  Everything else — canonicalization,
the SHA-256 binding over the complete argument set, the project/session/expiry
binding, and the atomic single claim — is shared, because it is the part that
must not drift between the two.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time


GMAIL_TOOL_NAME = "mcp__codex_apps__gmail__send_email"
SLACK_TOOL_NAME = "mcp__codex_apps__slack__slack_send_message"
CLAUDE_GMAIL_TOOL_NAME = "mcp__claude_ai_Gmail__send_message"
CLAUDE_SLACK_TOOL_NAME = "mcp__slack__slack_post_message"
# Notion, Claude side only: the operator's own workspace is where this system
# keeps its 正本 (ledgers, logs), so an approved write to ONE page is a real
# act the operator asks for, not a broadcast.  Two acts, mirroring the email
# and channel pair: edit one existing page, or create one new page.  The other
# Notion writes named in the guard's OUTBOUND_EXACT — comments, session
# messages, duplicate/move — keep no permit path, because the guard's own
# record says a list that opens one verb invites the neighbouring one.
CLAUDE_NOTION_UPDATE_TOOL_NAME = "mcp__claude_ai_Notion__notion-update-page"
CLAUDE_NOTION_CREATE_TOOL_NAME = "mcp__claude_ai_Notion__notion-create-pages"

# The exact wire names a permit may open, per CLI.  Deliberately narrow: one
# email and one channel message on each side, plus — Claude only — one page
# edit and one page creation.  Replies, drafts, forwards and edits have no
# permit path and go through the approval queue.  Codex has no entry for
# Notion: its guard names no Notion tool, so there is nothing to open there.
CLI_TOOL_NAMES = {
    "codex": {"gmail": GMAIL_TOOL_NAME, "slack": SLACK_TOOL_NAME},
    "claude": {
        "gmail": CLAUDE_GMAIL_TOOL_NAME,
        "slack": CLAUDE_SLACK_TOOL_NAME,
        "notion-update": CLAUDE_NOTION_UPDATE_TOOL_NAME,
        "notion-create": CLAUDE_NOTION_CREATE_TOOL_NAME,
    },
}
# Where each CLI's guard looks for the store.  The guard derives the project
# root from its own location, never from caller input.
CLI_STORE_DIR = {"codex": ".codex", "claude": ".claude"}
DEFAULT_CLI = "codex"
# Backwards compatibility: the module-level name the Codex guard and the
# original tests knew.  Selecting a CLI narrows this, it never widens it.
TOOL_NAMES = CLI_TOOL_NAMES[DEFAULT_CLI]
# The `--tool` selector is one flag for every CLI, so its argparse choices must
# be the UNION; the per-CLI table is what actually decides, and asking for a
# selector this CLI does not have is refused as a usage error (exit 2) rather
# than silently resolved to some other CLI's wire name.
ALL_TOOL_SELECTORS = frozenset(
    selector for table in CLI_TOOL_NAMES.values() for selector in table
)
ALL_TOOL_NAMES = frozenset(
    name for table in CLI_TOOL_NAMES.values() for name in table.values()
)
VERSION = 1


def _tool_name_for(args):
    """The wire name this (cli, tool) pair selects, or a usage error."""
    try:
        return CLI_TOOL_NAMES[args.cli][args.tool]
    except KeyError:
        # exit 2 = usage error, the same code argparse uses for a bad choice.
        # A selector that exists for another CLI must fail the same way as one
        # that exists nowhere, or the caller learns to retry against the wrong
        # CLI and the store directories stop meaning what they say.
        print(
            f"usage error: --tool {args.tool} is not available for --cli {args.cli} "
            f"(available: {', '.join(sorted(CLI_TOOL_NAMES[args.cli]))})",
            file=sys.stderr,
        )
        raise SystemExit(2)
def _namespace_and_operation(name: str):
    """Split `mcp__<server>__<operation>` into its two halves, or (None, None).

    The `mcp__<server>__` prefix is a wire convention and is stable; what
    varies between the two observed spellings of the SAME connector call is
    only the operation segment.
    """
    if not isinstance(name, str):
        return None, None
    head, sep, rest = name.partition("__")
    if not sep or not head:
        return None, None
    server, sep, operation = rest.partition("__")
    if not sep or not server or not operation:
        return None, None
    return head + "__" + server + "__", operation


def canonical_tool_name(name, allowed_tools=ALL_TOOL_NAMES):
    """Return the canonical permit tool name `name` refers to, else None.

    ONE CONNECTOR, TWO SPELLINGS.  Measured 2026-09-13/14 on the ChatGPT
    desktop app: the JavaScript wrapper inside `exec` is
    `tools.mcp__codex_apps__gmail_create_draft` (one `_`), while the
    PreToolUse envelope for that same call carries
    `mcp__codex_apps__gmail__create_draft` (two).  The desktop tool catalogue
    lists `mcp__codex_apps__gmail_send_email` with one.  Both forms are in
    circulation on one machine on one day, so an exact string comparison
    recognises one of them and silently fails to recognise its twin.

    That gap never leaked a send — the guard's verb rule matches either
    spelling and denies both.  What it broke is the other direction: a send
    the operator reviewed, approved and issued a permit for is refused, for a
    reason no log states.  A control that fails shut for an approved act is
    still a control that has to be repaired, or the next repair will be
    someone widening the verb list.

    ONLY the `__`/`_` difference inside the operation segment is absorbed.
    The namespace prefix must match exactly, and every other difference — a
    hyphen, a missing separator, another verb, another connector — resolves to
    None and is treated as the different tool it is.
    """
    if name in allowed_tools:
        return name
    prefix, operation = _namespace_and_operation(name)
    if prefix is None:
        return None
    flattened = operation.replace("__", "_")
    for candidate in allowed_tools:
        c_prefix, c_operation = _namespace_and_operation(candidate)
        if c_prefix == prefix and c_operation.replace("__", "_") == flattened:
            return candidate
    return None

DEFAULT_TTL = 300
MAX_TTL = 900
PERMIT_KEYS = {
    "version", "permit_id", "tool_name", "tool_input_sha256",
    "tool_input_canonical", "project_root", "session_id", "created_at",
    "expires_at", "approval_ref", "approval_quote",
}


class PermitError(Exception):
    pass


def _object_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PermitError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _bad_constant(value):
    raise PermitError(f"non-finite JSON number: {value}")


def strict_loads(text: str):
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_bad_constant,
        )
    except PermitError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PermitError("invalid JSON") from exc


def without_object_nulls(value):
    if isinstance(value, dict):
        return {
            key: without_object_nulls(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [without_object_nulls(item) for item in value]
    return value


def canonical_input(value) -> str:
    if not isinstance(value, dict):
        raise PermitError("tool_input must be a JSON object")
    try:
        return json.dumps(
            without_object_nulls(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PermitError("tool_input is not canonicalizable JSON") from exc


def digest(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_tool_input(path: Path):
    try:
        return strict_loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PermitError(f"cannot read tool input: {path}") from exc


def resolved_project(path_text: str) -> Path:
    try:
        path = Path(path_text).resolve(strict=True)
    except OSError as exc:
        raise PermitError("project root does not exist") from exc
    if not path.is_dir():
        raise PermitError("project root is not a directory")
    return path


def _require_text(tool_input, key: str, label: str) -> str:
    value = tool_input.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PermitError(f"{label} {key} must be a non-empty string")
    return value


def _validate_codex_slack(tool_input) -> None:
    if not tool_input:
        raise PermitError("Slack tool_input must not be empty")
    if tool_input.get("draft_id") is not None:
        raise PermitError("draft_id is not valid for a new Slack send")
    for key in ("channel_id", "message"):
        _require_text(tool_input, key, "Slack")
    if len(tool_input["message"]) > 5000:
        raise PermitError("Slack message must be at most 5000 characters")
    thread_ts = tool_input.get("thread_ts")
    if thread_ts is not None and (
        not isinstance(thread_ts, str) or not thread_ts.strip()
    ):
        raise PermitError("Slack thread_ts must be a non-empty string")
    reply_broadcast = tool_input.get("reply_broadcast")
    if reply_broadcast is not None and type(reply_broadcast) is not bool:
        raise PermitError("Slack reply_broadcast must be a boolean")
    if reply_broadcast is True and thread_ts is None:
        raise PermitError("Slack reply_broadcast=true requires thread_ts")


def _validate_claude_slack(tool_input) -> None:
    # mcp__slack__slack_post_message takes exactly channel_id and text; a
    # threaded reply is a different tool and has no permit path.
    if not tool_input:
        raise PermitError("Slack tool_input must not be empty")
    for key in ("channel_id", "text"):
        _require_text(tool_input, key, "Slack")
    if len(tool_input["text"]) > 5000:
        raise PermitError("Slack text must be at most 5000 characters")


def _validate_claude_gmail(tool_input) -> None:
    # mcp__claude_ai_Gmail__send_message takes recipients as ARRAYS and carries
    # a draftId escape hatch: the connector documents that when draftId is
    # present "the other fields are ignored, and the specified draft is sent as
    # is".  A permit whose hash covers to/subject/body would then bind nothing
    # that is actually sent, so a permit may not name one.
    if not tool_input:
        raise PermitError("Gmail tool_input must not be empty")
    if tool_input.get("draftId") is not None:
        raise PermitError("draftId is not valid for a permitted new send")
    for key in ("to", "cc", "bcc"):
        value = tool_input.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            raise PermitError(f"Gmail {key} must be an array of addresses")
        for address in value:
            if not isinstance(address, str) or not address.strip():
                raise PermitError(f"Gmail {key} must contain non-empty addresses")
    if not tool_input.get("to"):
        raise PermitError("Gmail to must name at least one recipient")
    subject = tool_input.get("subject")
    if subject is not None and not isinstance(subject, str):
        raise PermitError("Gmail subject must be a string")
    bodies = [tool_input.get("body"), tool_input.get("htmlBody")]
    if not any(isinstance(part, str) and part.strip() for part in bodies):
        raise PermitError("Gmail body or htmlBody must be a non-empty string")


# Notion-flavored markdown can reach OTHER pages from inside a body string:
# `<page url=…>` moves a page, `<database data-source-url=…>` creates a linked
# view, `<folder …>` attaches one.  A permit that hashed only the body would
# bind the text and not the act, so a permitted write may not carry them.
# (Found 2026-09-18 by an independent review of the first version of this file.)
# Matched as a PATTERN, not as fixed substrings: `<page\turl=`, `<page\nurl=`
# and `< page url=` all reached another page while a substring check for
# "<page " let them through (found 2026-09-18 in review).
_NOTION_REACHING_NOTATION = re.compile(
    r"<\s*/?\s*(?:page|database|folder)\b", re.IGNORECASE
)
# The commands a permit may open.  `replace_content` and `apply_template` are
# NOT here: the first deletes child pages and databases that the arguments
# never name, and the second writes whatever the template says TODAY, so the
# hash binds an id instead of the content that lands.
_NOTION_PERMITTED_COMMANDS = frozenset(
    {"update_properties", "update_content", "insert_content"}
)


def _reject_reaching_notation(value, where: str) -> None:
    """Refuse any string in the payload that can act on a DIFFERENT page."""
    if isinstance(value, str):
        found = _NOTION_REACHING_NOTATION.search(value)
        if found:
            raise PermitError(
                f"Notion {where} may not carry `{found.group(0).strip()}` notation "
                "(it acts on another page or database)"
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_reaching_notation(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_reaching_notation(item, f"{where}[{index}]")


def _validate_claude_notion_update(tool_input) -> None:
    # notion-update-page edits ONE existing page, named by page_id, under one
    # command.  The hash already binds the whole argument set; these checks keep
    # a permit from being issued for a call whose EFFECT is not in that set.
    if not tool_input:
        raise PermitError("Notion tool_input must not be empty")
    _require_text(tool_input, "page_id", "Notion")
    _require_text(tool_input, "command", "Notion")
    command = tool_input["command"]
    if command not in _NOTION_PERMITTED_COMMANDS:
        raise PermitError(
            f"Notion command {command} has no permit path "
            f"(permitted: {', '.join(sorted(_NOTION_PERMITTED_COMMANDS))})"
        )
    if tool_input.get("allow_async") is True:
        # a backgrounded write answers before the page is written, so the
        # approval would cover an outcome nobody has seen.
        raise PermitError("allow_async is not valid for a permitted Notion write")
    if tool_input.get("template_id") is not None:
        raise PermitError("template_id binds an id, not the content that lands")
    if tool_input.get("is_skill") is not None:
        # marking a page as a skill turns it into instructions another agent
        # loads; that is the `convert-page-to-skill` act, which has no path.
        raise PermitError("is_skill is not valid for a permitted Notion write")
    if tool_input.get("allow_deleting_content") is True:
        raise PermitError(
            "allow_deleting_content deletes child pages the arguments never name"
        )
    updates = tool_input.get("content_updates")
    if updates is not None:
        if not isinstance(updates, list) or len(updates) != 1:
            raise PermitError("a Notion permit may name exactly one content update")
        if updates[0].get("replace_all_matches") is True:
            raise PermitError("replace_all_matches makes one permit many edits")
    _reject_reaching_notation(tool_input, "update")


def _validate_claude_notion_create(tool_input) -> None:
    # notion-create-pages takes a LIST.  One permit opens one act, so a permit
    # may name exactly one page.  A parent is required: without it the call
    # creates a workspace-level private page, and the operator would be
    # approving a destination that the arguments never state.
    if not tool_input:
        raise PermitError("Notion tool_input must not be empty")
    pages = tool_input.get("pages")
    if not isinstance(pages, list) or len(pages) != 1:
        raise PermitError("a Notion permit may name exactly one page")
    if not isinstance(pages[0], dict) or not pages[0]:
        raise PermitError("Notion page must be a non-empty object")
    parent = tool_input.get("parent")
    if not isinstance(parent, dict) or not parent:
        raise PermitError("Notion create needs an explicit parent")
    if tool_input.get("creation_mode") is not None:
        raise PermitError("creation_mode is not valid alongside an explicit parent")
    if tool_input.get("allow_async") is True:
        raise PermitError("allow_async is not valid for a permitted Notion write")
    if pages[0].get("template_id") is not None:
        raise PermitError("template_id binds an id, not the content that lands")
    if pages[0].get("is_skill") is not None:
        raise PermitError("is_skill is not valid for a permitted Notion write")
    _reject_reaching_notation(tool_input, "create")


# Keyed by the exact wire tool name, which is unique across both CLIs, so the
# right shape check is selected without the caller having to say which CLI it
# came from.  A tool with no entry is bound by its hash alone.
INPUT_VALIDATORS = {
    SLACK_TOOL_NAME: _validate_codex_slack,
    CLAUDE_SLACK_TOOL_NAME: _validate_claude_slack,
    CLAUDE_GMAIL_TOOL_NAME: _validate_claude_gmail,
    CLAUDE_NOTION_UPDATE_TOOL_NAME: _validate_claude_notion_update,
    CLAUDE_NOTION_CREATE_TOOL_NAME: _validate_claude_notion_create,
}


def validated_canonical_input(tool_name: str, tool_input) -> str:
    canonical = canonical_input(tool_input)
    validator = INPUT_VALIDATORS.get(tool_name)
    if validator is not None:
        validator(tool_input)
    return canonical


def review_record(tool_name: str, tool_input) -> dict:
    canonical = validated_canonical_input(tool_name, tool_input)
    return {
        "tool_name": tool_name,
        "canonical_tool_input": strict_loads(canonical),
        "canonical_json": canonical,
        "sha256": digest(canonical),
    }


def print_review(tool_name: str, tool_input) -> str:
    record = review_record(tool_name, tool_input)
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
    return record["sha256"]


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def issue(args) -> None:
    if not args.confirm_user_approved:
        raise PermitError(
            "refusing to issue: --confirm-user-approved is required and must "
            "be backed by the user's explicit assent"
        )
    if not args.session_id.strip() or not args.approval_ref.strip() or not args.approval_quote.strip():
        raise PermitError("session-id, approval-ref, and approval-quote must be non-empty")
    if args.ttl_seconds < 1 or args.ttl_seconds > MAX_TTL:
        raise PermitError(f"ttl-seconds must be between 1 and {MAX_TTL}")

    tool_name = _tool_name_for(args)
    tool_input = load_tool_input(args.tool_input)
    actual_hash = print_review(tool_name, tool_input)
    if actual_hash != args.expected_sha256.lower():
        raise PermitError("reviewed SHA-256 does not match the current tool-input file")

    project = resolved_project(args.project_root)
    permit_root = project / CLI_STORE_DIR[args.cli] / "outbound-permits"
    pending = permit_root / "pending"
    claimed = permit_root / "claimed"
    pending.mkdir(parents=True, exist_ok=True, mode=0o700)
    claimed.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(permit_root, 0o700)
    os.chmod(pending, 0o700)
    os.chmod(claimed, 0o700)

    now = int(time.time())
    permit_id = secrets.token_hex(16)
    record = {
        "version": VERSION,
        "permit_id": permit_id,
        "tool_name": tool_name,
        "tool_input_sha256": actual_hash,
        "tool_input_canonical": validated_canonical_input(tool_name, tool_input),
        "project_root": str(project),
        "session_id": args.session_id,
        "created_at": now,
        "expires_at": now + args.ttl_seconds,
        "approval_ref": args.approval_ref,
        "approval_quote": args.approval_quote,
    }
    target = pending / f"{permit_id}.json"
    temporary = pending / f".{permit_id}.tmp"
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        fsync_dir(pending)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    print(json.dumps({
        "permit_file": str(target),
        "expires_at": record["expires_at"],
        "project_root": record["project_root"],
        "session_id": record["session_id"],
        "approval_ref": record["approval_ref"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


def validate_permit(record: object, now: int, allowed_tools=ALL_TOOL_NAMES) -> None:
    if not isinstance(record, dict) or set(record) != PERMIT_KEYS:
        raise PermitError("invalid permit schema")
    string_keys = {
        "permit_id", "tool_name", "tool_input_sha256", "tool_input_canonical",
        "project_root", "session_id", "approval_ref", "approval_quote",
    }
    if any(not isinstance(record[key], str) or not record[key] for key in string_keys):
        raise PermitError("invalid permit string field")
    if record["tool_name"] not in allowed_tools:
        raise PermitError("permit tool is not allowlisted")
    if type(record["version"]) is not int or record["version"] != VERSION:
        raise PermitError("unsupported permit version")
    if type(record["created_at"]) is not int or type(record["expires_at"]) is not int:
        raise PermitError("invalid permit timestamp")
    lifetime = record["expires_at"] - record["created_at"]
    if record["created_at"] > now or lifetime < 1 or lifetime > MAX_TTL:
        raise PermitError("invalid permit lifetime")
    canonical = validated_canonical_input(
        record["tool_name"], strict_loads(record["tool_input_canonical"])
    )
    if canonical != record["tool_input_canonical"] or digest(canonical) != record["tool_input_sha256"]:
        raise PermitError("corrupt permit payload binding")


def cwd_belongs_to_project(cwd_text: str, project: Path) -> bool:
    try:
        cwd = Path(cwd_text).resolve(strict=True)
        cwd.relative_to(project)
        return True
    except (OSError, ValueError):
        return False


def claim(args) -> None:
    envelope = strict_loads(sys.stdin.read())
    if not isinstance(envelope, dict):
        raise PermitError("hook input must be an object")
    allowed_tools = frozenset(CLI_TOOL_NAMES[args.cli].values())
    # The wire name is canonicalised before anything else uses it, so the rest
    # of this function — the validator lookup, the record comparison, the
    # permit store — only ever sees the one spelling a permit is written
    # under.  A name that does not resolve is a different tool and is refused.
    tool_name = canonical_tool_name(envelope.get("tool_name"), allowed_tools)
    if tool_name is None:
        raise PermitError("permit is only valid for an allowlisted exact send tool")
    session_id = envelope.get("session_id")
    cwd = envelope.get("cwd")
    if not isinstance(session_id, str) or not session_id or not isinstance(cwd, str):
        raise PermitError("hook input lacks session_id or cwd")
    project = resolved_project(args.project_root)
    if not cwd_belongs_to_project(cwd, project):
        raise PermitError("hook cwd is outside the permitted project")
    canonical = validated_canonical_input(tool_name, envelope.get("tool_input"))
    tool_hash = digest(canonical)

    permit_root = project / CLI_STORE_DIR[args.cli] / "outbound-permits"
    pending = permit_root / "pending"
    claimed = permit_root / "claimed"
    if not pending.is_dir() or not claimed.is_dir():
        raise PermitError("permit store is absent")

    now = int(time.time())
    candidates = sorted(pending.glob("*.json"))
    for path in candidates:
        try:
            record = strict_loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PermitError("cannot read permit") from exc
        validate_permit(record, now, allowed_tools)
        if (
            record["tool_name"] == tool_name
            and record["tool_input_sha256"] == tool_hash
            and record["tool_input_canonical"] == canonical
            and record["project_root"] == str(project)
            and record["session_id"] == session_id
            and record["expires_at"] > now
        ):
            target = claimed / path.name
            try:
                os.rename(path, target)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise PermitError("atomic permit claim failed") from exc
            fsync_dir(pending)
            fsync_dir(claimed)
            return
    raise PermitError("no unexpired matching one-shot permit")


def add_cli_flag(command: argparse.ArgumentParser) -> None:
    """Which CLI's wire names and permit store this invocation means.

    Defaults to codex so an installed Codex guard that predates the shared
    helper keeps working with the argument list it already passes.
    """
    command.add_argument(
        "--cli", choices=sorted(CLI_TOOL_NAMES), default=DEFAULT_CLI
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Review, issue, or claim a one-shot exact send permit. A permit "
            "does not substitute for user approval."
        )
    )
    sub = result.add_subparsers(dest="command", required=True)
    review_cmd = sub.add_parser("review", help="show canonical payload and SHA-256; write nothing")
    review_cmd.add_argument("--tool-input", type=Path, required=True)
    review_cmd.add_argument(
        "--tool", choices=sorted(ALL_TOOL_SELECTORS), default="gmail"
    )
    add_cli_flag(review_cmd)

    issue_cmd = sub.add_parser("issue", help="write a short-lived one-shot permit")
    issue_cmd.add_argument("--tool-input", type=Path, required=True)
    issue_cmd.add_argument(
        "--tool", choices=sorted(ALL_TOOL_SELECTORS), default="gmail"
    )
    issue_cmd.add_argument("--expected-sha256", required=True)
    issue_cmd.add_argument("--project-root", required=True)
    issue_cmd.add_argument("--session-id", required=True)
    issue_cmd.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL)
    issue_cmd.add_argument("--approval-ref", required=True)
    issue_cmd.add_argument("--approval-quote", required=True)
    issue_cmd.add_argument("--confirm-user-approved", action="store_true")
    add_cli_flag(issue_cmd)

    claim_cmd = sub.add_parser("claim", help=argparse.SUPPRESS)
    claim_cmd.add_argument("--project-root", required=True)
    add_cli_flag(claim_cmd)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "review":
            print_review(_tool_name_for(args),
                         load_tool_input(args.tool_input))
        elif args.command == "issue":
            issue(args)
        else:
            claim(args)
        return 0
    except PermitError as exc:
        print(f"outbound permit: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("outbound permit: unexpected failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
