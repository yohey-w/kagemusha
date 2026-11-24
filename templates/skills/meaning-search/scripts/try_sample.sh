#!/usr/bin/env bash
# Run both fictional topics through the configured real model and score each result.
set -euo pipefail

script="$(realpath -- "${BASH_SOURCE[0]}")"
scripts="$(dirname -- "$script")"
sample="$scripts/../sample"
key="$sample/answer_key.json"
topics="$(python3 -c 'import json, sys; print(*json.load(open(sys.argv[1], encoding="utf-8"))["topics"], sep="\n")' "$key")"
output="$(mktemp -d "${TMPDIR:-/tmp}/meaning-search-sample.XXXXXX")"

printf 'Sample results: %s\n' "$output"
status=0
index=0
while IFS= read -r topic; do
    index=$((index + 1))
    result="$output/topic-$index"
    if python3 "$scripts/meaning_search.py" \
        --case "example-co の架空の倉庫業務" --topic "$topic" \
        --ledger "$sample/ledger.yaml" --journal "$sample/decisions_journal.md" \
        --glossary "$sample/glossary.md" --mishearings "$sample/mishearings.md" \
        --transcripts "$sample/transcripts" --source-root "$sample" --out "$result"; then
        :
    else
        code=$?
        [[ "$code" -eq 3 ]] || exit "$code"
        status="$code"
        printf 'Sample run was partial: %s\n' "$topic" >&2
    fi
    python3 "$scripts/score.py" "$result/result.json" "$key"
done <<< "$topics"
exit "$status"
