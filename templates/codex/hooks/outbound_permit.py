#!/usr/bin/env python3
"""Issue and atomically claim one-shot permits for an approved Gmail send.

A permit records approval; it never creates approval.  Run ``review`` first,
then ``issue`` only when an operator can cite the user's explicit assent.  The
boundary assumes agents cannot modify this project or invoke this operator
helper without authorization; an adversary with workspace-write access is out
of scope.
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


TOOL_NAME = "mcp__codex_apps__gmail__send_email"
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


def review_record(tool_input) -> dict:
    canonical = canonical_input(tool_input)
    return {
        "tool_name": TOOL_NAME,
        "canonical_tool_input": strict_loads(canonical),
        "canonical_json": canonical,
        "sha256": digest(canonical),
    }


def print_review(tool_input) -> str:
    record = review_record(tool_input)
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

    tool_input = load_tool_input(args.tool_input)
    actual_hash = print_review(tool_input)
    if actual_hash != args.expected_sha256.lower():
        raise PermitError("reviewed SHA-256 does not match the current tool-input file")

    project = resolved_project(args.project_root)
    permit_root = project / ".codex" / "outbound-permits"
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
        "tool_name": TOOL_NAME,
        "tool_input_sha256": actual_hash,
        "tool_input_canonical": canonical_input(tool_input),
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


def validate_permit(record: object, now: int) -> None:
    if not isinstance(record, dict) or set(record) != PERMIT_KEYS:
        raise PermitError("invalid permit schema")
    string_keys = {
        "permit_id", "tool_name", "tool_input_sha256", "tool_input_canonical",
        "project_root", "session_id", "approval_ref", "approval_quote",
    }
    if any(not isinstance(record[key], str) or not record[key] for key in string_keys):
        raise PermitError("invalid permit string field")
    if type(record["version"]) is not int or record["version"] != VERSION:
        raise PermitError("unsupported permit version")
    if type(record["created_at"]) is not int or type(record["expires_at"]) is not int:
        raise PermitError("invalid permit timestamp")
    lifetime = record["expires_at"] - record["created_at"]
    if record["created_at"] > now or lifetime < 1 or lifetime > MAX_TTL:
        raise PermitError("invalid permit lifetime")
    canonical = canonical_input(strict_loads(record["tool_input_canonical"]))
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
    if envelope.get("tool_name") != TOOL_NAME:
        raise PermitError("permit is only valid for Gmail send_email")
    session_id = envelope.get("session_id")
    cwd = envelope.get("cwd")
    if not isinstance(session_id, str) or not session_id or not isinstance(cwd, str):
        raise PermitError("hook input lacks session_id or cwd")
    project = resolved_project(args.project_root)
    if not cwd_belongs_to_project(cwd, project):
        raise PermitError("hook cwd is outside the permitted project")
    canonical = canonical_input(envelope.get("tool_input"))
    tool_hash = digest(canonical)

    permit_root = project / ".codex" / "outbound-permits"
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
        validate_permit(record, now)
        if (
            record["tool_name"] == TOOL_NAME
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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Review, issue, or claim a one-shot Gmail send permit. A permit "
            "does not substitute for user approval."
        )
    )
    sub = result.add_subparsers(dest="command", required=True)
    review_cmd = sub.add_parser("review", help="show canonical payload and SHA-256; write nothing")
    review_cmd.add_argument("--tool-input", type=Path, required=True)

    issue_cmd = sub.add_parser("issue", help="write a short-lived one-shot permit")
    issue_cmd.add_argument("--tool-input", type=Path, required=True)
    issue_cmd.add_argument("--expected-sha256", required=True)
    issue_cmd.add_argument("--project-root", required=True)
    issue_cmd.add_argument("--session-id", required=True)
    issue_cmd.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL)
    issue_cmd.add_argument("--approval-ref", required=True)
    issue_cmd.add_argument("--approval-quote", required=True)
    issue_cmd.add_argument("--confirm-user-approved", action="store_true")

    claim_cmd = sub.add_parser("claim", help=argparse.SUPPRESS)
    claim_cmd.add_argument("--project-root", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "review":
            print_review(load_tool_input(args.tool_input))
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
