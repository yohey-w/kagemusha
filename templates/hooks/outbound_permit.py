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
import secrets
import sys
import time


GMAIL_TOOL_NAME = "mcp__codex_apps__gmail__send_email"
SLACK_TOOL_NAME = "mcp__codex_apps__slack__slack_send_message"
CLAUDE_GMAIL_TOOL_NAME = "mcp__claude_ai_Gmail__send_message"
CLAUDE_SLACK_TOOL_NAME = "mcp__slack__slack_post_message"

# The exact wire names a permit may open, per CLI.  Deliberately two acts on
# each side — one email, one channel message.  Replies, drafts, forwards and
# edits have no permit path and go through the approval queue.
CLI_TOOL_NAMES = {
    "codex": {"gmail": GMAIL_TOOL_NAME, "slack": SLACK_TOOL_NAME},
    "claude": {"gmail": CLAUDE_GMAIL_TOOL_NAME, "slack": CLAUDE_SLACK_TOOL_NAME},
}
# Where each CLI's guard looks for the store.  The guard derives the project
# root from its own location, never from caller input.
CLI_STORE_DIR = {"codex": ".codex", "claude": ".claude"}
DEFAULT_CLI = "codex"
# Backwards compatibility: the module-level name the Codex guard and the
# original tests knew.  Selecting a CLI narrows this, it never widens it.
TOOL_NAMES = CLI_TOOL_NAMES[DEFAULT_CLI]
ALL_TOOL_NAMES = frozenset(
    name for table in CLI_TOOL_NAMES.values() for name in table.values()
)
VERSION = 1
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


# Keyed by the exact wire tool name, which is unique across both CLIs, so the
# right shape check is selected without the caller having to say which CLI it
# came from.  A tool with no entry is bound by its hash alone.
INPUT_VALIDATORS = {
    SLACK_TOOL_NAME: _validate_codex_slack,
    CLAUDE_SLACK_TOOL_NAME: _validate_claude_slack,
    CLAUDE_GMAIL_TOOL_NAME: _validate_claude_gmail,
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

    tool_name = CLI_TOOL_NAMES[args.cli][args.tool]
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
    tool_name = envelope.get("tool_name")
    if tool_name not in allowed_tools:
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
    review_cmd.add_argument("--tool", choices=sorted(TOOL_NAMES), default="gmail")
    add_cli_flag(review_cmd)

    issue_cmd = sub.add_parser("issue", help="write a short-lived one-shot permit")
    issue_cmd.add_argument("--tool-input", type=Path, required=True)
    issue_cmd.add_argument("--tool", choices=sorted(TOOL_NAMES), default="gmail")
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
            print_review(CLI_TOOL_NAMES[args.cli][args.tool],
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
