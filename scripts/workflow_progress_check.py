#!/usr/bin/env python3
"""Read-only workflow advice; never grants permission or changes goal/job state.

Input is a small nonsecret JSON object. Review keys include purpose, source,
dependency/configuration identity and adoption conditions, not just a filename.
"""
import argparse
import json
import sys
from pathlib import Path

MAX_INPUT_BYTES = 65536
# Depth is checked on the raw bytes before parsing, so the answer does not depend on
# which Python runs it: older parsers raise RecursionError on deep nesting, newer ones
# parse it. A small current-state record never needs more than a few levels.
MAX_NESTING = 64


def nesting_exceeds(text, limit=MAX_NESTING):
    """True if brackets/braces outside JSON strings nest deeper than `limit`.

    Takes the decoded text (the same characters the parser will see), so the
    count cannot disagree with the parse over the input's encoding.
    """
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > limit:
                return True
        elif char in "]}":
            depth -= 1
    return False


def decode_input(raw):
    """Accept UTF-8 only (a leading BOM is tolerated); refuse anything else.

    json.loads() on bytes would also guess UTF-16/32, which the nesting check
    above would then read differently from the parser.
    """
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("input must be UTF-8 JSON") from None


def integer(data, key, default=0):
    value = data.get(key, default)
    if type(value) is not int or value < 0:
        raise ValueError(f"{key} must be a nonnegative integer")
    return value


def boolean(data, key, default=False):
    value = data.get(key, default)
    if type(value) is not bool:
        raise ValueError(f"{key} must be boolean")
    return value


def assess(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    action = data.get("action")
    if action not in ("review", "work"):
        raise ValueError("action must be review or work")
    findings = []

    if action == "review":
        key = data.get("review_key")
        accepted = data.get("accepted_review_keys", [])
        if not isinstance(key, str) or not key.strip():
            raise ValueError("review_key must identify purpose/version/deps/conditions")
        if not isinstance(accepted, list) or any(not isinstance(k, str) for k in accepted):
            raise ValueError("accepted_review_keys must be strings")
        changed = any([boolean(data, k) for k in (
            "new_evidence", "new_issue", "constraints_changed", "user_requested_repeat"
        )])
        if key in accepted and not changed:
            findings.append("REUSE_ACCEPTED_REVIEW")
        packet_chars = integer(data, "packet_chars")
        justified = boolean(data, "packet_justified")
        duplicates = boolean(data, "duplicate_background_confirmed")
        if packet_chars > 12000 and not justified:
            findings.append("TRIM_DUPLICATE_BACKGROUND_KEEP_DECISIVE_RAW" if duplicates
                            else "VERIFY_PACKET_RELEVANCE_KEEP_DECISIVE_RAW")

    threat = data.get("added_threat_model")
    if threat is not None:
        if not isinstance(threat, str) or not threat.strip():
            raise ValueError("added_threat_model must be a nonempty string")
        origin = data.get("threat_model_origin")
        if origin not in ("contract", "user", "confirmed_failure", "review_suggestion", "unknown"):
            raise ValueError("threat_model_origin must be explicit")
        if origin in {"review_suggestion", "unknown"}:
            findings.append("RESOLVE_THREAT_SCOPE_BEFORE_ADDING_GATE")

    if action == "work":
        for key in ("unchanged_goal_turns", "safe_next_action", "live_handle_verified"):
            if key not in data:
                raise ValueError(f"work requires {key}")
        unchanged = integer(data, "unchanged_goal_turns")
        safe = boolean(data, "safe_next_action")
        live = boolean(data, "live_handle_verified")
        if live:
            handle = data.get("live_handle_id")
            if not isinstance(handle, str) or not handle.strip():
                raise ValueError("verified live wait requires a handle ID observed now")
        if unchanged >= 3 and not safe and not live:
            findings.append("MARK_BLOCKED_IF_SAME_IMPEDIMENT_CONSECUTIVE")
        elif live and not safe:
            findings.append("WAIT_SAME_VERIFIED_LIVE_HANDLE")
        if integer(data, "minutes_without_progress") >= 20 and not live:
            findings.append("REASSESS_CRITICAL_PATH_NO_NEW_PAPERWORK")

    return {"advisory_only": True, "findings": findings,
            "permission_granted": False, "state_or_jobs_changed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="nonsecret JSON; otherwise stdin")
    args = parser.parse_args(argv)
    try:
        if args.input:
            with args.input.open("rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input exceeds 64KiB; use a small current-state record")
        text = decode_input(raw)
        if nesting_exceeds(text):
            raise RecursionError
        result = assess(json.loads(text))
    except RecursionError:
        print(json.dumps({"error": "JSON nesting exceeds parser capacity",
                          "permission_granted": False}))
        return 2
    except (OSError, ValueError) as error:
        # Do not echo the input body or file contents.
        print(json.dumps({"error": str(error), "permission_granted": False}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
