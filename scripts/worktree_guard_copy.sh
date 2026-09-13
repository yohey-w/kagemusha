#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# worktree_guard_copy.sh — put the outward guard into a git worktree.
#
#   ./scripts/worktree_guard_copy.sh <worktree-path>
#   ./scripts/worktree_guard_copy.sh --dry-run <worktree-path>
#
# WHY THIS EXISTS. A git worktree gets the TRACKED files and nothing else. The
# two files that arm the outward guard are deliberately NOT tracked — they hold
# machine-local absolute paths, so the allowlist .gitignore keeps them out of
# the repository:
#
#     .claude/settings.json    (the PreToolUse registration)
#     .codex/config.toml       (the same, for the other CLI)
#
# So `git worktree add` copies neither, and an agent started inside a worktree
# runs with NO BRAKE ON OUTWARD CALLS AT ALL — while the main checkout beside
# it is guarded. Nothing announces this. The hook host fails open, which here
# means it never even looks: there is no hook to fail.
#
# MEASURED 2026-09-13 on the author's machine: six worktrees existed and NOT
# ONE had a .claude/ or a .codex/ directory. An independent review reproduced
# it in the worktree it was itself reviewing from, and confirmed there is no
# rescue path at the user level either — so the exposure was total, and silent.
#
# This matters more than it looks, because the instructions file recommends
# worktree isolation as the normal way to run parallel work. The safest lane in
# the loop was the unguarded one.
#
# WHAT THIS DOES. Copies the guard's four pieces into the worktree, NEVER over
# anything already there, and rewrites the absolute project path inside the
# copied Codex config so its hook points at the worktree instead of back at the
# checkout it came from. Claude Code needs no rewrite: its registration uses
# ${CLAUDE_PROJECT_DIR}, which the CLI expands per worktree.
#
# WHAT IT IS NOT. It is not a substitute for the rule. A worktree that has not
# been armed must not be used for outward work, and `--dry-run` is there so you
# can see what is missing before you trust it.
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

DRY_RUN=""
TARGET=""

usage() {
  cat <<'USAGE'
worktree_guard_copy.sh — put the outward guard into a git worktree.

  ./scripts/worktree_guard_copy.sh [--dry-run] <worktree-path>

A worktree receives only TRACKED files. The outward guard is armed by
.claude/settings.json and .codex/config.toml, which are instance data and are
git-ignored on purpose — so a fresh worktree has no guard, and says nothing
about it. This copies them in.

  --dry-run   report what would be copied; write nothing
  --help      this text

Nothing is ever overwritten: an entry that already exists is reported as
"skip (exists)" and left alone. Run it from the checkout you want to copy FROM.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    -*)        printf 'worktree_guard_copy.sh: unknown flag: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *)
      if [[ -n "$TARGET" ]]; then
        printf 'worktree_guard_copy.sh: more than one worktree given\n' >&2; exit 2
      fi
      TARGET="$1"; shift ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  printf 'worktree_guard_copy.sh: no worktree path given\n' >&2
  usage >&2
  exit 2
fi

if [[ ! -d "$TARGET" ]]; then
  printf 'worktree_guard_copy.sh: not a directory: %s\n' "$TARGET" >&2
  exit 2
fi

TARGET_ABS="$(cd "$TARGET" && pwd -P)"

if [[ "$TARGET_ABS" == "$SOURCE_ROOT" ]]; then
  printf 'worktree_guard_copy.sh: that is the checkout we would copy FROM: %s\n' "$TARGET_ABS" >&2
  exit 2
fi

printf 'worktree guard copy\n'
printf '  from : %s\n' "$SOURCE_ROOT"
printf '  to   : %s\n' "$TARGET_ABS"
[[ -n "$DRY_RUN" ]] && printf '  mode : DRY RUN (nothing is written)\n'

COPIED=0
SKIPPED=0
MISSING=0

# copy_entry RELATIVE_PATH — a file or a directory, relative to both roots.
copy_entry() {
  local rel="$1" src="$SOURCE_ROOT/$1" dst="$TARGET_ABS/$1"
  if [[ ! -e "$src" ]]; then
    printf '  absent (source): %s\n' "$rel"
    MISSING=$((MISSING + 1))
    return 0
  fi
  if [[ -e "$dst" ]]; then
    printf '  skip (exists):   %s\n' "$rel"
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi
  if [[ -n "$DRY_RUN" ]]; then
    printf '  would copy:      %s\n' "$rel"
    COPIED=$((COPIED + 1))
    return 0
  fi
  mkdir -p "$(dirname "$dst")" || return 1
  cp -R "$src" "$dst" || return 1
  printf '  copy:            %s\n' "$rel"
  COPIED=$((COPIED + 1))
}

copy_entry ".claude/settings.json"
copy_entry ".claude/hooks"
copy_entry ".codex/config.toml"
copy_entry ".codex/hooks"

# The Codex hook command is an ABSOLUTE path — a relative one would resolve
# against wherever the CLI was started, so the template spells it out in full.
# Copied verbatim into a worktree it still points at the checkout it came from,
# which means the worktree's agent would run the OTHER tree's hook and write
# its permits there. Repoint it. Claude Code needs no equivalent: its command
# uses ${CLAUDE_PROJECT_DIR}, which the CLI expands per worktree.
CODEX_COPY="$TARGET_ABS/.codex/config.toml"
if [[ -z "$DRY_RUN" && -f "$CODEX_COPY" ]] && grep -qF -- "$SOURCE_ROOT" "$CODEX_COPY" 2>/dev/null; then
  if TMP_CFG="$(mktemp "$TARGET_ABS/.codex/.config.toml.XXXXXX")"; then
    if sed "s|$SOURCE_ROOT|$TARGET_ABS|g" "$CODEX_COPY" > "$TMP_CFG" && mv "$TMP_CFG" "$CODEX_COPY"; then
      printf '  repoint:         .codex/config.toml (hook path now names this worktree)\n'
    else
      rm -f "$TMP_CFG"
      printf '  WARNING: could not repoint .codex/config.toml — check its hook path by hand\n' >&2
    fi
  fi
fi

printf '  ── copied=%d skipped=%d absent=%d\n' "$COPIED" "$SKIPPED" "$MISSING"

if [[ "$MISSING" -gt 0 ]]; then
  printf '  → an absent source is not armed in the checkout you copied FROM either.\n'
  printf '    Arm it there first (templates/claude/settings.json.example,\n'
  printf '    ./scripts/setup.sh --codex), then run this again.\n'
fi

if [[ -n "$DRY_RUN" ]]; then
  printf '  → dry run: nothing written\n'
elif [[ "$COPIED" -gt 0 ]]; then
  printf '  → Codex also needs the project marked trusted in its USER config, and\n'
  printf '    approves a hook once per hook file. A worktree is a new path, so that\n'
  printf '    approval is asked again. Until it is given, the hook is skipped SILENTLY.\n'
fi
