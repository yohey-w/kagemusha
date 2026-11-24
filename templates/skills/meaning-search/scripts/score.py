#!/usr/bin/env python3
"""Compare the records and quoted source lines in a result with an answer key."""

import argparse
import json
from pathlib import Path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def print_recall(label, expected, missed):
    found = len(expected) - len(missed)
    if expected:
        print(f"{label} recall: {found}/{len(expected)} ({found / len(expected):.1%})")
    else:
        print(f"{label} recall: 0/0 (n/a)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path, help="result.json from meaning_search.py")
    parser.add_argument("answer_key", type=Path, help="expected IDs and quotes by topic")
    args = parser.parse_args()

    try:
        result = read_json(args.result)
        topic = result["topic"]
        key = read_json(args.answer_key)["topics"]
        if topic not in key:
            parser.error(f"topic {topic!r} is missing from {args.answer_key}")
        expected_records = key[topic]["records"]
        expected_quotes = key[topic]["quotes"]
        key_root = args.answer_key.resolve().parent
        found_ids = {record["id"] for record in result["records"]}
        found_quotes = set()
        for excerpt in result["excerpts"]:
            file = Path(excerpt["file"]).resolve()
            found_quotes.update((file, quote["line"]) for quote in excerpt["quotes"])
        missed_ids = [record_id for record_id in expected_records if record_id not in found_ids]
        missed_quotes = [quote for quote in expected_quotes
                         if ((key_root / quote["file"]).resolve(), quote["line"]) not in found_quotes]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.error(f"cannot score result and answer key: {exc}")

    print(f"topic: {topic}")
    print_recall("records", expected_records, missed_ids)
    print("missed ids: " + (", ".join(missed_ids) or "none"))
    print_recall("quotes", expected_quotes, missed_quotes)
    print("missed quotes: " + (", ".join(f"{q['file']}:{q['line']}" for q in missed_quotes) or "none"))


if __name__ == "__main__":
    main()
