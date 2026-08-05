#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# F. discipline scanner — scripts/discipline_scan.py + the shipped catalog.
#
# The scanner exists to tell you whether a discipline you adopted is doing
# anything. Two failure modes would make it worse than nothing, so both are
# pinned here:
#   · a false dead letter (it missed evidence that was in the log). The
#     reference implementation really did this: it prefiltered on '"text"',
#     which silently dropped every user turn whose content is a bare string.
#   · a prohibition reported as a dead letter (compliance with a prohibition
#     is unobservable, so zero hits is not a signal).
# Fixtures are synthetic JSONL written here from fixed strings — no real log
# is read by the suite.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "F. discipline scanner"

F_SCAN="$REPO_ROOT/scripts/discipline_scan.py"
# The catalog the scan is EXERCISED with is a fixture, not the shipped example:
# core ships the catalog FORMAT with zero entries (a shipped list would audit
# somebody else's disciplines), so the entries with real regexes live next to
# the synthetic logs they match. The shipped example is asserted separately,
# below, to be empty and to fail loudly rather than scan nothing.
F_CAT="$REPO_ROOT/tests/fixtures/discipline_catalog.yaml"
F_SHIPPED="$REPO_ROOT/templates/discipline_catalog.example.yaml"
F_LOGS="$TEST_TMP/f_logs"
F_EMPTY="$TEST_TMP/f_empty"
F_OUT="$TEST_TMP/f_report.md"

assert_file "F: scripts/discipline_scan.py ships" "$F_SCAN"
assert_file "F: tests/fixtures/discipline_catalog.yaml (the exercise fixture) ships" "$F_CAT"
assert_file "F: templates/discipline_catalog.example.yaml ships" "$F_SHIPPED"
assert_file "F: docs/discipline-audit.md ships" "$REPO_ROOT/docs/discipline-audit.md"
assert_file "F: templates/discipline-audit-prompt.md ships" \
  "$REPO_ROOT/templates/discipline-audit-prompt.md"

mkdir -p "$F_LOGS" "$F_EMPTY"
f_now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# One transcript, four turns, all fixed strings:
#   1 assistant, block-list content   → A6 fire   (swept-shelves report)
#   2 user,      BARE STRING content  → A2 breach (approver asks for the board)
#   3 assistant, block-list content   → A6-P breach ("exhaustive")
#   4 assistant, harness noise        → must be ignored
{
  printf '{"type":"assistant","timestamp":"%s","message":{"content":[{"type":"text","text":"%s"}]}}\n' \
    "$f_now" '掃いた棚: A, B。未掃: C。'
  printf '{"type":"user","timestamp":"%s","message":{"content":"%s"}}\n' \
    "$f_now" 'いま何が進んでるんだっけ'
  printf '{"type":"assistant","timestamp":"%s","message":{"content":[{"type":"text","text":"%s"}]}}\n' \
    "$f_now" '三つの棚を網羅したので問題ありません'
  printf '{"type":"assistant","timestamp":"%s","message":{"content":[{"type":"text","text":"%s"}]}}\n' \
    "$f_now" '<command-name>noise</command-name>'
} > "$F_LOGS/deadbeef-session.jsonl"

assert_ok "F: scan runs against the fixture catalog" \
  python3 "$F_SCAN" --catalog "$F_CAT" --dir "$F_LOGS" --since 7d --out "$F_OUT"

assert_grep "F: report says candidates, not findings" "candidates, not findings" "$F_OUT"
assert_grep "F: report warns firings are unobservable for prohibitions" \
  "Zero hits on a prohibition means nothing" "$F_OUT"
assert_grep "F: trace firing detected (assistant, block content)" \
  "[FIRE] $(date -u +%Y-%m-%d)" "$F_OUT"
assert_grep "F: trace firing is the swept-shelves passage" '掃いた棚' "$F_OUT"
assert_grep "F: prohibition breach detected" '網羅した' "$F_OUT"
# the regression: a user turn whose content is a bare string must be scanned
assert_grep "F: bare-string user turn is scanned (not dropped)" \
  'いま何が進んでるんだっけ' "$F_OUT"
assert_no_grep "F: harness noise is skipped" "<command-name>" "$F_OUT"
# a prohibition is never listed as a dead letter — the tail line is trace-only
f_tail="$(grep '^Trace disciplines with zero firing candidates:' "$F_OUT")"
assert_nonempty_str "F: report ends with the trace-only dead-letter line" "$f_tail"
case "$f_tail" in
  *A6-P*|*A3-P*) fail "F: prohibitions absent from dead-letter line" "got: $f_tail" ;;
  *) pass "F: prohibitions absent from dead-letter line" ;;
esac
assert_grep "F: prohibition with no hits is explicitly excluded" \
  "not a dead-letter candidate" "$F_OUT"

# ── failure modes: every one of these must be loud, never a quiet empty run ──
assert_exit "F: missing --catalog is an error" 2 python3 "$F_SCAN" --dir "$F_LOGS"
assert_exit "F: unreadable catalog is an error" 2 \
  python3 "$F_SCAN" --catalog "$TEST_TMP/nope.yaml" --dir "$F_LOGS"
assert_exit "F: nonexistent log dir is an error" 2 \
  python3 "$F_SCAN" --catalog "$F_CAT" --dir "$TEST_TMP/f_no_such_dir"
assert_exit "F: zero files scanned is an error, not an empty report" 2 \
  python3 "$F_SCAN" --catalog "$F_CAT" --dir "$F_EMPTY"

# ── the SHIPPED catalog carries the format and no disciplines ──────────────
# A catalog is a list of the disciplines its owner adopted. Shipping one would
# audit somebody else's, report dead letters for rules nobody took, and read as
# a starting set. So the example ships with `disciplines: []` and the scanner
# refuses it loudly — the refusal is the forcing function, and a silent empty
# report would be the failure.
f_shipped_entries="$(grep -cE '^[[:space:]]*-[[:space:]]+id:' "$F_SHIPPED" || true)"
assert_eq "F: the shipped catalog has zero active entries" "0" "$f_shipped_entries"
assert_grep "F: …and still carries the field documentation" "type: prohibition" "$F_SHIPPED"
assert_grep "F: …and shows one entry as a comment, not as data" "#  - id: X1" "$F_SHIPPED"
assert_exit "F: an empty catalog is a loud error, not a quiet empty report" 2 \
  python3 "$F_SCAN" --catalog "$F_SHIPPED" --dir "$F_LOGS"

# ── catalog validation ─────────────────────────────────────────────────────
f_cat() { printf '%s\n' "$@" > "$TEST_TMP/f_cat.yaml"; }

f_cat "disciplines:" \
      "  - id: T1" "    type: trace" "    name: writes the scope first" \
      "    fire: '掃いた棚'" \
      "  - id: P1" "    type: prohibition" "    name: never claims exhaustive" \
      "    breach: 'this string appears nowhere'"
assert_ok "F: minimal hand-written catalog parses" \
  python3 "$F_SCAN" --catalog "$TEST_TMP/f_cat.yaml" --dir "$F_LOGS" --out "$TEST_TMP/f2.md"
assert_grep "F: unfired prohibition is not called a dead letter" \
  "Trace disciplines with zero firing candidates: none" "$TEST_TMP/f2.md"

f_cat "disciplines:" \
      "  - id: P2" "    type: prohibition" "    name: unobservable compliance" \
      "    fire: 'anything'"
assert_exit "F: a prohibition with a fire pattern is rejected" 2 \
  python3 "$F_SCAN" --catalog "$TEST_TMP/f_cat.yaml" --dir "$F_LOGS"

f_cat "disciplines:" "  - id: T2" "    type: trace" "    name: no fire pattern"
assert_exit "F: a trace with no fire pattern is rejected" 2 \
  python3 "$F_SCAN" --catalog "$TEST_TMP/f_cat.yaml" --dir "$F_LOGS"

f_cat "disciplines:" "  - id: T3" "    type: rumour" "    name: bad type" \
      "    fire: 'x'"
assert_exit "F: an unknown type is rejected" 2 \
  python3 "$F_SCAN" --catalog "$TEST_TMP/f_cat.yaml" --dir "$F_LOGS"

f_cat "disciplines:" "  - id: T4" "    type: trace" "    name: bad key" \
      "    fire: 'x'" "    scoring: 10"
assert_exit "F: an unknown key is rejected (no silent typos)" 2 \
  python3 "$F_SCAN" --catalog "$TEST_TMP/f_cat.yaml" --dir "$F_LOGS"

f_cat "disciplines:" "  - id: T5" "    type: trace" "    name: bad regex" \
      "    fire: '(unclosed'"
assert_exit "F: a broken regex is rejected" 2 \
  python3 "$F_SCAN" --catalog "$TEST_TMP/f_cat.yaml" --dir "$F_LOGS"
