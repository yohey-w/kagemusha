#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# A. syntax & lint — every tracked shell / python file, no exemptions.
#
# Lint severity is pinned at "warning" (which still includes SC2259-class
# errors). Not lower: at --severity=style the suite reports 80+ SC2317
# "command appears unreachable" notes against the lane-dispatch style in
# inbound_watch.sh — false positives that would train everyone to ignore the
# output, which is worse than not running the linter at all.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "A. syntax & lint"

A_SH=()
while IFS= read -r f; do A_SH+=("$f"); done < <(git -C "$REPO_ROOT" ls-files '*.sh' '*.sh.example')
A_PY=()
while IFS= read -r f; do A_PY+=("$f"); done < <(git -C "$REPO_ROOT" ls-files '*.py')

assert_ge "A: tracked shell files found" "${#A_SH[@]}" 5
assert_ge "A: tracked python files found" "${#A_PY[@]}" 2

for f in "${A_SH[@]}"; do
  assert_ok "A: bash -n $f" bash -n "$REPO_ROOT/$f"
  head -n 1 "$REPO_ROOT/$f" | grep -q '^#!' \
    && pass "A: shebang present $f" \
    || fail "A: shebang present $f" "first line is not a #! line"
done

if command -v shellcheck >/dev/null 2>&1; then
  for f in "${A_SH[@]}"; do
    assert_ok "A: shellcheck -S warning $f" \
      shellcheck --severity=warning --format=gcc --external-sources "$REPO_ROOT/$f"
  done
else
  fail "A: shellcheck available on PATH" \
"shellcheck is not installed, so no shell file in this repo has been linted.
This counts as a FAILURE, not a skip — see tests/lib.sh.
  Debian/Ubuntu : sudo apt-get install -y shellcheck
  macOS         : brew install shellcheck
  static binary : https://github.com/koalaman/shellcheck/releases"
fi

for f in "${A_PY[@]}"; do
  assert_ok "A: py_compile $f" python3 -m py_compile "$REPO_ROOT/$f"
done

# Everything under scripts/ is something the docs tell you to run or to cron,
# including the .example wirings you copy. They ship executable.
while IFS= read -r line; do
  mode="${line%% *}"; path="${line#* }"
  assert_eq "A: exec bit in git index: $path" "100755" "$mode"
done < <(git -C "$REPO_ROOT" ls-files -s -- scripts | awk '{print $1, $4}')
