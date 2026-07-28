#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# morning_brief.sh — the "time trigger" of a work loop.
#
# INWARD-ONLY. It collects, takes stock, writes ONE board, and pings you.
# It must NEVER perform an outward operation (send / publish / mutate the SSOT).
# Anything outward the agent notices goes into the approval queue, not out the door.
#
# Run it by hand once, then put it on cron (or Windows Task Scheduler, or just a
# daily calendar reminder to run it by hand — see docs/windows.md). Cron is only
# the example scheduler; any way of starting it on a schedule is equivalent, and a
# CLI is needed only if you want it fully hands-off. Reads config from config.env
# (copy config.env.example first).
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

# cron's default PATH omits ~/.local/bin, so AGENT_CMD (claude / codex / gemini,
# installed there by most native installers) is not found and the run dies instantly.
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME}/.local/bin:${PATH}"

# ─── locate & load config ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${LOOP_CONFIG:-$SCRIPT_DIR/../config.env}"
if [[ ! -f "$CONFIG" ]]; then
  echo "config not found: $CONFIG" >&2
  echo "  copy config.env.example → config.env and edit it (or set LOOP_CONFIG)." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG"

: "${PROJECT_ROOT:?set PROJECT_ROOT in config.env}"
: "${SSOT_DIR:?set SSOT_DIR in config.env}"
: "${BRIEF_DIR:?set BRIEF_DIR in config.env}"
: "${LOG_DIR:?set LOG_DIR in config.env}"
: "${AGENT_CMD:?set AGENT_CMD in config.env}"

TODAY="$(date +%F)"
DOW="$(date +%A)"
OUT="${BRIEF_DIR}/${TODAY}.md"
NOTIFY_FILE="${BRIEF_DIR}/${TODAY}.notify.txt"   # the agent writes a 1-line summary here
mkdir -p "$BRIEF_DIR" "$LOG_DIR"
rm -f "$NOTIFY_FILE"

# ─── the prompt: an inward-only stock-take. Edit freely for your own context. ─
# The prompt does the reasoning; it must not run any send/publish/push command.
read -r -d '' PROMPT <<PROMPT_EOF || true
Run a morning stock-take and write "today's board" to ${OUT}.
This is an automated INWARD task. Outward operations are STRICTLY FORBIDDEN:
do not send email/chat, do not publish, do not push, do not deploy, and do not
edit the SSOT files. Read-only except for writing the two output files named below.

Today is ${TODAY} (${DOW}).

Do this:
1. Read the SSOT under ${SSOT_DIR}: decisions.md (list undecided / recently-changed
   topics), tasks.md (open promises with deadlines), glossary.md, people.md.
2. Read the approval queue at ${QUEUE_FILE}: list every unprocessed entry, one line
   each, with your one-line recommendation (approve / edit / reject).
3. Deadline radar: from tasks.md, compute days-remaining for each open item and make
   a small table sorted by urgency. Verify each weekday against the calendar.
4. Compose the board with these sections:
   (1) What happened overnight (only if you have a read-only source for it)
   (2) Today's deadlines and promises
   (3) Waiting on the human — the approval queue, one recommended line each
   (4) Work in progress
   (5) Anything you could NOT read from this automated run (say so plainly)
5. Write the board to ${OUT}.
6. Write ONE line (count of items waiting on the human + the single most urgent
   deadline) to ${NOTIFY_FILE}. Do not send any network notification yourself —
   the wrapper script sends the push. Finish read-only within a few minutes.
PROMPT_EOF

# ─── run the agent (headless) ──────────────────────────────────────────────
# CLI-SWAP POINT ▼  Replace this ONE invocation to use a different CLI.
#   Claude : "$AGENT_CMD" -p "$PROMPT" ${AGENT_MODEL:+--model "$AGENT_MODEL"} $AGENT_FLAGS
#   Codex  : "$AGENT_CMD" exec "$PROMPT" $AGENT_FLAGS         # (codex CLI)
#   Gemini : "$AGENT_CMD" -p "$PROMPT" ${AGENT_MODEL:+-m "$AGENT_MODEL"} $AGENT_FLAGS
#   Any CLI that takes a prompt on argv and runs non-interactively works.
# shellcheck disable=SC2086
timeout "${AGENT_TIMEOUT:-1500}" "$AGENT_CMD" -p "$PROMPT" \
  ${AGENT_MODEL:+--model "$AGENT_MODEL"} $AGENT_FLAGS \
  >> "${LOG_DIR}/morning_brief_${TODAY}.log" 2>&1
status=$?

# ─── notify (self-ping; still inward) ──────────────────────────────────────
if [[ "${NTFY_ENABLED:-1}" != "0" && -n "${NTFY_TOPIC:-}" && -s "$NOTIFY_FILE" ]]; then
  auth=()
  [[ -n "${NTFY_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer ${NTFY_TOKEN}")
  curl -s "${auth[@]}" -H "Title: morning board ${TODAY}" \
    -d "$(cat "$NOTIFY_FILE")" "${NTFY_SERVER:-https://ntfy.sh}/${NTFY_TOPIC}" > /dev/null || true
fi

echo "[$(date '+%F %T')] morning_brief exit=${status} out=${OUT}" >> "${LOG_DIR}/morning_brief_cron.log"
exit "$status"
