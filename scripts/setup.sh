#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# setup.sh — scaffold a work-loop.
#
# Default target is the repo root itself: you live INSIDE the clone, and the
# allowlist .gitignore guarantees your instance data can never be committed
# (and `git pull` updates the kit under you). An explicit path still works
# if you prefer a separate directory.
#
# Creates the SSOT + approval queue + verifiers from templates/, the
# judgment-distillation layer, the project-context layer (system_map.md,
# projects/ with the charter template), an agent-instructions file
# (CLAUDE.md), and briefs/ logs/ local/ directories. NEVER clobbers
# existing files, so it is safe to re-run: your filled-in files are
# never overwritten.
#
#   ./scripts/setup.sh              # scaffold into the clone (recommended)
#   ./scripts/setup.sh ~/work-loop  # …or into a separate directory
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATES="$REPO_ROOT/templates"

TARGET="${1:-$REPO_ROOT}"

mkdir -p "$TARGET/ssot" "$TARGET/briefs" "$TARGET/logs" "$TARGET/local" \
         "$TARGET/projects/_archive" \
         "$TARGET/judgment/mining" "$TARGET/judgment/reports" "$TARGET/judgment/logs"

copy() {  # copy() <src> <dst> — never clobber existing files
  local src="$1" dst="$2"
  if [[ -e "$dst" ]]; then
    echo "  skip (exists): $dst"
  else
    cp "$src" "$dst"
    echo "  create:        $dst"
  fi
}

echo "scaffolding work-loop into: $TARGET"

# SSOT files live under ssot/
for f in decisions tasks glossary people; do
  copy "$TEMPLATES/$f.md" "$TARGET/ssot/$f.md"
done

# approval queue, verifiers, and the system map live at the work-dir root
# (the hottest file gets the shortest path)
copy "$TEMPLATES/approval_queue.md" "$TARGET/approval_queue.md"
copy "$TEMPLATES/verifiers.md"      "$TARGET/verifiers.md"
copy "$TEMPLATES/system_map.md"     "$TARGET/system_map.md"

# judgment-distillation layer (the feedback side — see docs/judgment-distillation.md)
copy "$TEMPLATES/decisions_journal.md" "$TARGET/judgment/decisions_journal.md"
copy "$TEMPLATES/judgment_model.md"    "$TARGET/judgment/judgment_model.md"

# project-context layer: copy the charter template into each new project
# folder as projects/<name>/charter.md (card = folder = charter, 1:1:1)
copy "$TEMPLATES/charter.md" "$TARGET/projects/_charter_template.md"

# agent instructions — saved under the filename your AI CLI reads.
# Claude Code reads CLAUDE.md (created here if absent); Codex reads AGENTS.md
# (if you already have one, we leave things alone — copy it yourself).
if [[ -e "$TARGET/CLAUDE.md" || -e "$TARGET/AGENTS.md" ]]; then
  echo "  skip (exists): $TARGET/CLAUDE.md or AGENTS.md (agent instructions)"
else
  copy "$TEMPLATES/agent_instructions.md" "$TARGET/CLAUDE.md"
  echo "  → Codex user? rename it: mv $TARGET/CLAUDE.md $TARGET/AGENTS.md"
fi

# a starter config next to the scripts (edit before running morning_brief.sh)
if [[ ! -f "$REPO_ROOT/config.env" ]]; then
  copy "$REPO_ROOT/config.env.example" "$REPO_ROOT/config.env"
  echo "  → edit $REPO_ROOT/config.env : set PROJECT_ROOT=\"$TARGET\", AGENT_CMD, NTFY_TOPIC"
fi

cat <<DONE

done. next:
  1. fill in $TARGET/ssot/*.md   (decisions, tasks, glossary, people)
  2. edit  $TARGET/CLAUDE.md     (agent instructions — or rename to AGENTS.md for Codex)
  3. per project: mkdir $TARGET/projects/<name> and copy
           $TARGET/projects/_charter_template.md -> projects/<name>/charter.md
           then add one card for it in $TARGET/system_map.md
  4. edit  $REPO_ROOT/config.env (PROJECT_ROOT="$TARGET", AGENT_CMD, NTFY_TOPIC)
  5. test  $SCRIPT_DIR/morning_brief.sh
  6. cron  53 6 * * *  $SCRIPT_DIR/morning_brief.sh   (Windows: see docs/windows.md)

  judgment distillation (the feedback side — optional, add once the loop runs):
  7. edit  $TARGET/judgment/judgment_model.md  (seed a few of your own principles)
  8. copy  $SCRIPT_DIR/weekly_distill.sh.example -> weekly_distill.sh, edit its CONFIG
  9. cron  17 21 * * 0  $SCRIPT_DIR/weekly_distill.sh   (once a week — see docs/judgment-distillation.md)
DONE
