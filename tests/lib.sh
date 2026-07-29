#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# tests/lib.sh — assertions and fixtures for scripts/test.sh.
#
# DESIGN NOTE (this kit sells acceptance gates; its own gate has to hold up):
# there is deliberately NO skip primitive here. A check either runs and passes
# or runs and fails. A missing tool is a FAILURE, not a skip — an unverified
# file is not a green file. "skipped=0" in the summary is therefore structural,
# not a claim someone has to trust.
#
# Sourced by scripts/test.sh; not meant to be run directly.
# ═══════════════════════════════════════════════════════════════════════════

TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_NAMES=""

_c_pass=''; _c_fail=''; _c_dim=''; _c_rst=''
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  _c_pass=$'\033[32m'; _c_fail=$'\033[31m'; _c_dim=$'\033[2m'; _c_rst=$'\033[0m'
fi

group() { printf '\n%s── %s%s\n' "$_c_dim" "$1" "$_c_rst"; }

pass() {
  TESTS_TOTAL=$((TESTS_TOTAL + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
  printf '  %sok%s   %s\n' "$_c_pass" "$_c_rst" "$1"
}

fail() {
  TESTS_TOTAL=$((TESTS_TOTAL + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
  FAILED_NAMES="${FAILED_NAMES}${1}"$'\n'
  printf '  %sFAIL%s %s\n' "$_c_fail" "$_c_rst" "$1"
  if [[ -n "${2:-}" ]]; then printf '%s\n' "$2" | sed 's/^/       | /'; fi
}

# ─── assertions ────────────────────────────────────────────────────────────

# assert_ok NAME CMD...      — command exits 0
assert_ok() {
  local name="$1"; shift
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -eq 0 ]]; then pass "$name"
  else fail "$name" "exit=$rc
$(printf '%s' "$out" | tail -n 20)"; fi
}

# assert_exit NAME WANT CMD... — command exits with WANT
assert_exit() {
  local name="$1" want="$2"; shift 2
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -eq "$want" ]]; then pass "$name"
  else fail "$name" "want exit=$want got exit=$rc
$(printf '%s' "$out" | tail -n 20)"; fi
}

assert_eq() {  # assert_eq NAME WANT GOT
  if [[ "$2" == "$3" ]]; then pass "$1"; else fail "$1" "want: $2
got : $3"; fi
}

assert_ne() {  # assert_ne NAME NOT_WANT GOT
  if [[ "$2" != "$3" ]]; then pass "$1"; else fail "$1" "must differ from: $2"; fi
}

assert_ge() {  # assert_ge NAME GOT MIN
  if [[ "$2" -ge "$3" ]]; then pass "$1"; else fail "$1" "got $2, want >= $3"; fi
}

assert_file() { if [[ -f "$2" ]]; then pass "$1"; else fail "$1" "not a file: $2"; fi; }
assert_dir()  { if [[ -d "$2" ]]; then pass "$1"; else fail "$1" "not a directory: $2"; fi; }
assert_absent() { if [[ ! -e "$2" ]]; then pass "$1"; else fail "$1" "should not exist: $2"; fi; }

assert_same() {  # assert_same NAME FILE_A FILE_B — byte-identical
  if cmp -s "$2" "$3"; then pass "$1"; else fail "$1" "files differ: $2 vs $3
$(diff "$2" "$3" 2>&1 | head -n 10)"; fi
}

# assert_grep NAME PATTERN FILE — fixed-string. A missing file FAILS both this
# and assert_no_grep: "the file wasn't there" must never read as a pass.
assert_grep() {
  local name="$1" pat="$2" file="$3"
  if [[ ! -f "$file" ]]; then fail "$name" "file does not exist: $file"; return; fi
  if grep -qF -- "$pat" "$file"; then pass "$name"
  else fail "$name" "not found in $file: $pat
$(tail -n 20 "$file")"; fi
}

assert_no_grep() {
  local name="$1" pat="$2" file="$3"
  if [[ ! -f "$file" ]]; then fail "$name" "file does not exist: $file"; return; fi
  if grep -qF -- "$pat" "$file"; then
    fail "$name" "MUST NOT appear in $file: $pat
$(grep -nF -- "$pat" "$file" | head -n 5)"
  else pass "$name"; fi
}

assert_empty_str() {  # assert_empty_str NAME VALUE  — VALUE must be empty
  if [[ -z "$2" ]]; then pass "$1"; else fail "$1" "expected empty, got:
$(printf '%s' "$2" | head -n 20)"; fi
}

assert_nonempty_str() {
  if [[ -n "$2" ]]; then pass "$1"; else fail "$1" "expected non-empty output"; fi
}

# ─── fixtures ──────────────────────────────────────────────────────────────

# kit_copy DEST — materialize ONLY the git-tracked files (working-tree content,
# so uncommitted edits are what gets tested) into DEST. This is the "fresh
# clone" a user gets; instance data is structurally absent.
kit_copy() {
  local dest="$1"
  mkdir -p "$dest"
  git -C "$REPO_ROOT" ls-files -z \
    | tar -C "$REPO_ROOT" --null -T - -cf - \
    | tar -C "$dest" -xf -
}

# kit_git_init DEST — make DEST a hermetic git repo with the kit committed.
# Global/system git config is neutralized so a user's core.excludesFile or
# init.templateDir cannot change the answer.
kit_git_init() {
  local dest="$1"
  git -C "$dest" -c init.defaultBranch=main init -q
  git -C "$dest" add -A
  git -C "$dest" -c user.name=test -c user.email=test@example.invalid \
      commit -qm "kit" >/dev/null
}

# mtime PATH — seconds since epoch (GNU stat, BSD stat fallback)
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null; }

# tree_hashes DIR — "sha256  relpath" for every regular file, sorted.
tree_hashes() {
  ( cd "$1" && find . -type f ! -path './.git/*' -print0 | sort -z \
      | xargs -0 sha256sum 2>/dev/null )
}

# tree_mtimes DIR — "mtime relpath" for every regular file, sorted.
tree_mtimes() {
  ( cd "$1" && find . -type f ! -path './.git/*' -printf '%T@ %p\n' 2>/dev/null | sort )
}
