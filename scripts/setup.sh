#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# setup.sh — scaffold a work-loop.
#
# Default target is the repo root itself: you live INSIDE the clone, and the
# allowlist .gitignore guarantees your instance data can never be committed
# (and `git pull` updates the kit under you). An explicit path still works
# if you prefer a separate directory.
#
#   ./scripts/setup.sh              # scaffold into the clone (recommended)
#   ./scripts/setup.sh ~/work-loop  # …or into a separate directory
#
# WHAT IT COPIES IS DATA, NOT CODE. Every source->dest pair lives in
# manifests/scaffold.tsv and this script only executes that list. A rule that
# lives inside a script is a rule nobody can see being broken — one added `cp`
# line and a sample shelf has quietly become everybody's default. As a manifest
# it shows up in the diff, and the acceptance gate (test group H) asserts on it
# directly. See docs/layers.md.
#
# WHAT IT SCAFFOLDS IS SHAPE, NEVER CONTENT. Every template it copies is an
# EMPTY form — column definitions, state transitions, the evidence contract.
# No principle, no verifier, no correction vocabulary, no sample judgment. The
# first line in any of these files has to be one you earned.
#
# NEVER CLOBBERS existing files, so it is safe to re-run: your filled-in files
# are never overwritten.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="${SCAFFOLD_MANIFEST:-$REPO_ROOT/manifests/scaffold.tsv}"

TARGET="${1:-$REPO_ROOT}"

# The sample-shelf directory name, spelled in two pieces on purpose — the same
# reason manifests/scaffold.tsv spells it with a separator. This scaffolder must
# not contain that path as a literal string anywhere, not even inside a check
# for it, so that "does setup.sh name it at all?" stays a question a plain grep
# can answer with yes/no and no argument about which occurrences are "real".
# What the boundary IS lives in docs/layers.md; this is only its machine form.
SHELF="cook""book"

die() { printf 'setup.sh: %s\n' "$1" >&2; exit 2; }

[[ -f "$MANIFEST" ]] || die "scaffold manifest not found: $MANIFEST"

# ─── the manifest, validated before a single byte is copied ────────────────
# Rules 1-7 are written out in the manifest's own header. A row that breaks one
# is a hard stop (exit 2), never a skipped line: a scaffolder that silently
# ignores what it cannot parse is a scaffolder that silently stops scaffolding.
if grep -qF -- "$SHELF/" "$MANIFEST"; then
  die "$MANIFEST names the sample shelf. Core must not copy from it (docs/layers.md)."
fi

ROWS=()
lineno=0
while IFS= read -r line || [[ -n "$line" ]]; do
  lineno=$((lineno + 1))
  case "$line" in ''|[[:space:]]*'#'*|'#'*) continue ;; esac
  [[ -n "${line//[[:space:]]/}" ]] || continue

  n_fields="$(printf '%s' "$line" | awk -F'\t' '{print NF}')"
  [[ "$n_fields" == "3" ]] || die "$MANIFEST:$lineno: expected 3 tab-separated fields, got $n_fields"

  src="$(printf '%s' "$line" | cut -f1)"
  dst="$(printf '%s' "$line" | cut -f2)"
  grd="$(printf '%s' "$line" | cut -f3)"

  for fld in "$src" "$dst" "$grd"; do
    [[ -n "$fld" ]] || die "$MANIFEST:$lineno: empty field"
    case "$fld" in
      " "*|*" "|$'\t'*|*$'\t') die "$MANIFEST:$lineno: padded field: '$fld'" ;;
    esac
  done

  case "$src" in
    /*)          die "$MANIFEST:$lineno: source must be relative: $src" ;;
    templates/*) : ;;
    *)           die "$MANIFEST:$lineno: source must be rooted at templates/: $src" ;;
  esac
  case "$dst" in /*) die "$MANIFEST:$lineno: dest must be relative: $dst" ;; esac
  case "/$src/$dst/$grd/" in */../*) die "$MANIFEST:$lineno: '..' is not allowed: $line" ;; esac
  [[ -f "$REPO_ROOT/$src" ]] || die "$MANIFEST:$lineno: source does not exist: $src"

  for seen in ${ROWS[@]+"${ROWS[@]}"}; do
    [[ "$(printf '%s' "$seen" | cut -f2)" != "$dst" ]] || die "$MANIFEST:$lineno: duplicate dest: $dst"
  done
  ROWS+=("$line")
done < "$MANIFEST"

[[ ${#ROWS[@]} -gt 0 ]] || die "$MANIFEST has no rows — nothing would be scaffolded"

# ─── directories (mkdir only, no content — see the manifest's own header) ───
mkdir -p "$TARGET/ssot" "$TARGET/briefs" "$TARGET/logs" "$TARGET/local" \
         "$TARGET/projects/_archive" \
         "$TARGET/judgment/mining" "$TARGET/judgment/reports" "$TARGET/judgment/logs"

echo "scaffolding work-loop into: $TARGET"

copy() {  # copy() <src> <dst> — never clobber existing files
  local src="$1" dst="$2"
  if [[ -e "$dst" ]]; then
    echo "  skip (exists): $dst"
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "  create:        $dst"
  fi
}

AGENT_FILE_CREATED=""
for row in "${ROWS[@]}"; do
  src="$(printf '%s' "$row" | cut -f1)"
  dst="$(printf '%s' "$row" | cut -f2)"
  grd="$(printf '%s' "$row" | cut -f3)"

  case "$grd" in
    skip-if-exists)
      copy "$REPO_ROOT/$src" "$TARGET/$dst"
      ;;
    skip-if-any-exists:*)
      # never clobber an agent-instructions file, whatever the CLI calls it
      blocked=""
      IFS=',' read -r -a others <<< "${grd#skip-if-any-exists:}"
      for o in "${others[@]}"; do
        [[ -e "$TARGET/$o" ]] && blocked="$o"
      done
      if [[ -n "$blocked" ]]; then
        echo "  skip (exists): $TARGET/$blocked (agent instructions)"
      else
        copy "$REPO_ROOT/$src" "$TARGET/$dst"
        [[ "$dst" == "CLAUDE.md" ]] && AGENT_FILE_CREATED=1
      fi
      ;;
    *) die "unknown guard '$grd' for $dst" ;;
  esac
done

if [[ -n "$AGENT_FILE_CREATED" ]]; then
  echo "  → Codex user? rename it: mv $TARGET/CLAUDE.md $TARGET/AGENTS.md"
fi

# ─── the correction vocabulary: a file, with nothing in it ─────────────────
# This is NOT a manifest row, because there is no template to copy: the phrases
# you use when you overrule an agent are the one part of this kit that cannot be
# shipped. A list baked in here would quietly become everybody's, and every
# user's material file would then be shaped by words they never say. So the file
# is created EMPTY OF PATTERNS — the scanner refuses to run until you write your
# own, which is the intended forcing function, not a bug.
CORR="$TARGET/judgment/correction_patterns.txt"
if [[ -e "$CORR" ]]; then
  echo "  skip (exists): $CORR"
else
  cat > "$CORR" <<'CORRPAT'
# correction_patterns.txt — YOUR correction vocabulary. One Python regex per
# line, matched case-insensitively against your side of the transcript. Blank
# lines and lines starting with '#' are ignored.
#
# THIS FILE SHIPS WITH NO PATTERNS, on purpose. scripts/correction_scan.py has
# no built-in list and refuses to run on an empty one: the words you type when
# an agent has gone the wrong way are the one thing nobody else can write for
# you. A shipped list would harvest on phrases you never use, and the material
# file would fill up with somebody else's arguments.
#
# HOW TO FILL IT: read a week of your own transcripts and look for what you
# actually type when you overrule the agent. It is usually shorter and blunter
# than you expect, and it repeats — three or four phrases cover most of it.
#
# TUNING, in one rule: start broad, narrow later. Too broad costs you one line
# to skim in review; too narrow costs you the signal entirely, silently, and you
# never learn what you missed. Aim at VOCABULARY, not meaning — "the user
# disagreed" is not a regex; "that's not what I asked" is.
#
# Format notes: see templates/correction_patterns.example.txt.
# Write your patterns below this line.
CORRPAT
  echo "  create:        $CORR (no patterns — write your own before the scanner runs)"
fi

# a starter config next to the scripts (edit before running morning_brief.sh)
if [[ ! -f "$REPO_ROOT/config.env" ]]; then
  copy "$REPO_ROOT/config.env.example" "$REPO_ROOT/config.env"
  echo "  → edit $REPO_ROOT/config.env : set PROJECT_ROOT=\"$TARGET\", AGENT_CMD, NTFY_TOPIC"
fi

# The session-log directory for THIS target, spelled out. The scanner can guess
# it from the current directory, but cron's current directory is $HOME, so a
# cron line without --dir harvests the wrong project (or nothing) in silence.
# Same slug rule the scanner uses: every non-alphanumeric character becomes '-'.
TARGET_ABS="$(cd "$TARGET" && pwd)"
LOG_SLUG="$(printf '%s' "$TARGET_ABS" | sed 's/[^A-Za-z0-9]/-/g')"
LOG_DIRS="$HOME/.claude/projects/$LOG_SLUG"

cat <<DONE

Core scaffolded. No file from ${SHELF}/ was copied or activated.
Everything above is an EMPTY form: no principle, no verifier, no correction
vocabulary, no sample judgment. That is the design — see docs/layers.md.

next, in three steps:
  1. edit  $TARGET/CLAUDE.md — the delegation boundary and your own disciplines
           (or rename it to AGENTS.md for Codex). Nothing else runs until an
           agent knows what it may do without asking.
  2. fill  $TARGET/ssot/*.md (decisions, tasks, glossary, people) and add one
           project card in $TARGET/system_map.md, with
           $TARGET/projects/_charter_template.md copied to
           projects/<name>/charter.md. Card = folder = charter, 1:1:1.
  3. wire  the cron lines below, one at a time, checking each one runs by hand
           first. Start with the morning brief; add the distillation lane once
           the loop has actually been running.

  morning brief:
    edit  $REPO_ROOT/config.env (PROJECT_ROOT="$TARGET", AGENT_CMD, NTFY_TOPIC)
    test  $SCRIPT_DIR/morning_brief.sh
    cron  53 6 * * *  $SCRIPT_DIR/morning_brief.sh   (Windows: see docs/windows.md)

  judgment distillation (the feedback side — add once the loop runs):
    seed  $TARGET/judgment/judgment_model.md is empty; principles arrive by
          distilling your own journal, not by copying somebody's list
    copy  $SCRIPT_DIR/weekly_distill.sh.example -> weekly_distill.sh, edit CONFIG
    cron  17 21 * * 0  $SCRIPT_DIR/weekly_distill.sh   (docs/judgment-distillation.md)

  distillation courier (harvest daily, distil only when material piles up):
    write $CORR — your own correction phrases. It was created with none, and
          the scanner refuses to run until it has some (docs/distillation-loop.md).
    cron  7 6 * * *  $SCRIPT_DIR/correction_scan.py --patterns $CORR \\
                        --material $TARGET/judgment/correction_material.md \\
                        --state $TARGET/judgment/distill_state.json --since 1d \\
                        --dir $LOG_DIRS
      The --dir is not optional in a cron line: cron's working directory is \$HOME,
      and without it the scanner guesses a log path from there — i.e. the wrong one.
      (Check the guess above matches your CLI's transcript directory; if you work in
      more than one project, repeat --dir, or set DISTILL_LOG_DIRS in config.env.)
    cron  23 6 * * *  $SCRIPT_DIR/distill.sh   (fires only past the threshold)
      then review $TARGET/judgment/promotion_queue.md by hand: promotion is the one
      step that stays manual, because a rule nobody reviewed would govern every run
      after it.
DONE
