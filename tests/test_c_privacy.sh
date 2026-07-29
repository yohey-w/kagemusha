#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# C. leak guard — no personal / machine-specific identifier in a tracked file.
#
# The kit is written by dogfooding inside a live clone, so the failure mode is
# not "someone commits secrets on purpose", it is "a path or a client name
# rides along in a copy-pasted example". This scans every tracked file.
#
# The guard is itself tested: every pattern in tests/forbidden_patterns.txt is
# turned into a positive sample and must be caught, plus a negative sample of
# lookalikes that must NOT be. A detector nobody has seen detect anything is
# not evidence.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "C. personal-data leak guard"

C_PATTERNS="$TESTS_DIR/forbidden_patterns.txt"
assert_file "C: pattern file exists" "$C_PATTERNS"

# active (non-comment, non-blank) patterns
C_ERE="$TEST_TMP/c_ere.txt"
grep -vE '^[[:space:]]*(#|$)' "$C_PATTERNS" > "$C_ERE"
c_n="$(wc -l < "$C_ERE" | tr -d ' ')"
# a floor, so that emptying the pattern file cannot buy a green run
assert_ge "C: pattern file carries its patterns ($c_n found)" "$c_n" 9

# c_scan FILE... — print every offending "file:line:text"; empty output = clean
c_scan() { grep -InHE -f "$C_ERE" -- "$@" 2>/dev/null; }

# ── the real scan: every git-tracked file in the repo ──────────────────────
C_TRACKED=()
while IFS= read -r f; do C_TRACKED+=("$REPO_ROOT/$f"); done < <(git -C "$REPO_ROOT" ls-files)
assert_ge "C: tracked files to scan" "${#C_TRACKED[@]}" 20
assert_empty_str "C: no tracked file contains a forbidden identifier" "$(c_scan "${C_TRACKED[@]}")"

# ── does the detector detect? one positive sample per pattern ──────────────
# The sample is DERIVED from the pattern by deleting [ ] and \ — so a pattern
# and its own test case can never drift apart, and no forbidden literal is
# ever written into a tracked file (which would fail the scan above).
c_missed=""
while IFS= read -r ere; do
  sample="$(printf '%s' "$ere" | tr -d '[]\\')"
  probe="$TEST_TMP/c_probe.txt"
  { echo "harmless line"; echo "prefix ${sample} suffix"; echo "trailing line"; } > "$probe"
  if [[ -z "$(c_scan "$probe")" ]]; then c_missed="${c_missed}${ere} (sample: ${sample})"$'\n'; fi
done < "$C_ERE"
assert_empty_str "C: every pattern actually catches its own sample" "$c_missed"

# ── and does it stay quiet on the lookalikes? ──────────────────────────────
# yohey-w is the author's public GitHub handle: it is load-bearing in the clone
# URL and the LICENSE, and a guard that flags it would be turned off on day one.
C_NEG="$TEST_TMP/c_negative.txt"
cat > "$C_NEG" <<'NEG'
git clone https://github.com/yohey-w/kagemusha.git
Copyright (c) 2026 yohey-w
https://github.com/yohey-w/multi-agent-shogun
NTFY_TOPIC="change-me-to-something-unguessable"
PROJECT_ROOT="$HOME/work-loop"
a scary movie, a scarf, a tone-deaf take, home tools
alice@example.com|2026-12-31|client A
NEG
assert_empty_str "C: allowed lookalikes (yohey-w, example.com, …) are not flagged" "$(c_scan "$C_NEG")"

# ── end-to-end: a file that would really leak is really caught ─────────────
# Built by concatenation so this source file itself stays clean.
C_POS="$TEST_TMP/c_positive.txt"
{
  echo "LOG_DIR=/home/to""no/kagemusha/logs"
  echo "NTFY_TOPIC=\"sho-y0uh""ey\""
  echo "INBW_SLACK_CHANNELS=\"C0A2ASZD2U""R\""
  echo "board: https://claude.ai/code/arti""fact/deadbeef"
  echo "contact: yoheinab""e777@gmail.com"
} > "$C_POS"
c_hits="$(c_scan "$C_POS" | wc -l | tr -d ' ')"
assert_eq "C: a genuinely leaking file is caught on all 5 lines" "5" "$c_hits"
