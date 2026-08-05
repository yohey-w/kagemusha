#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# test.sh — the acceptance gate for this kit. The SAME command runs locally
# and in CI (.github/workflows/ci.yml just calls this file), so a green run on
# your machine and a green run on the badge mean the same thing.
#
#   ./scripts/test.sh          # everything (this is what CI runs)
#   ./scripts/test.sh b e      # only groups B and E — prints a PARTIAL banner
#                                and can never be mistaken for a full pass
#
# Design rules, since this kit is about acceptance gates:
#   · no skip primitive. A missing tool is a failure, not a skip. skipped=0
#     is structural, not a promise (see tests/lib.sh).
#   · nothing outward: no AI CLI is invoked, no host but 127.0.0.1 is
#     contacted, and the repo you are sitting in is never written to — every
#     test runs against a throwaway copy of the tracked files under $TMPDIR.
#   · a floor on the number of assertions, so deleting a test group turns the
#     run red instead of making it faster.
#
# Groups: A syntax/lint · B setup.sh · C leak guard · D .gitignore · E cron
#         F discipline scanner · G distillation courier · H layer boundary
#         I community lane
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TESTS_DIR="$REPO_ROOT/tests"

ALL_GROUPS=(a_lint b_setup c_privacy d_gitignore e_cron f_discipline g_distill h_layers
            i_community_lane)
MIN_ASSERTIONS=520   # floor for a full run (currently 528); raise it as you add tests

# ─── preflight ─────────────────────────────────────────────────────────────
die() { printf 'test.sh: %s\n' "$1" >&2; exit 2; }

git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "not a git work tree: $REPO_ROOT (the suite tests the TRACKED files)"
[[ -d "$TESTS_DIR" ]] || die "missing tests/ directory"
# node is required, not optional: group I evaluates the community workflows'
# own path gate in the engine actions/github-script runs it in. Re-implementing
# that gate in another language would test the re-implementation.
for t in git bash python3 node tar find grep sed awk sha256sum cmp comm timeout curl; do
  command -v "$t" >/dev/null 2>&1 || die "required tool not found: $t"
done

# keep __pycache__ out of the working tree when we byte-compile
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/kagemusha-pycache"

TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/kagemusha-test.XXXXXX")"
cleanup() {
  case "$TEST_TMP" in
    */kagemusha-test.??????) rm -rf "$TEST_TMP" ;;   # only ever our own mktemp dir
  esac
}
trap cleanup EXIT

# shellcheck source=tests/lib.sh
source "$TESTS_DIR/lib.sh"

# ─── which groups ──────────────────────────────────────────────────────────
SELECTED=()
if [[ $# -gt 0 ]]; then
  for want in "$@"; do
    hit=""
    for g in "${ALL_GROUPS[@]}"; do
      [[ "$g" == "$want" || "${g%%_*}" == "$want" ]] && { SELECTED+=("$g"); hit=1; }
    done
    [[ -n "$hit" ]] || die "unknown group: $want (have: ${ALL_GROUPS[*]})"
  done
else
  SELECTED=("${ALL_GROUPS[@]}")
fi
PARTIAL=$([[ ${#SELECTED[@]} -eq ${#ALL_GROUPS[@]} ]] && echo "" || echo "1")

printf 'kagemusha test suite\n'
printf '  repo    : %s\n' "$REPO_ROOT"
printf '  tracked : %s files\n' "$(git -C "$REPO_ROOT" ls-files | wc -l | tr -d ' ')"
printf '  sandbox : %s\n' "$TEST_TMP"
printf '  groups  : %s\n' "${SELECTED[*]}"

for g in "${SELECTED[@]}"; do
  f="$TESTS_DIR/test_$g.sh"
  [[ -f "$f" ]] || { fail "group $g present" "missing file: $f"; continue; }
  # shellcheck source=/dev/null
  source "$f"
done

# ─── summary ───────────────────────────────────────────────────────────────
if [[ -z "$PARTIAL" && "$TESTS_TOTAL" -lt "$MIN_ASSERTIONS" ]]; then
  fail "suite completeness (>= $MIN_ASSERTIONS assertions on a full run)" \
"only $TESTS_TOTAL assertions ran. Either a group died early or tests were
removed. A shrinking suite is a regression, not an improvement."
fi

printf '\n'
if [[ "$TESTS_FAILED" -gt 0 ]]; then
  printf 'failed:\n'
  printf '%s' "$FAILED_NAMES" | sed 's/^/  · /'
  printf '\n'
fi
[[ -n "$PARTIAL" ]] && printf '*** PARTIAL RUN (%s) — not an acceptance pass ***\n' "${SELECTED[*]}"

printf 'total=%d passed=%d failed=%d skipped=0\n' \
  "$TESTS_TOTAL" "$TESTS_PASSED" "$TESTS_FAILED"

[[ "$TESTS_FAILED" -eq 0 ]] || exit 1
[[ -z "$PARTIAL" ]] || exit 0
printf 'OK\n'
