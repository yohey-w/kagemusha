#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# distill.sh — the MATERIAL trigger of the distillation courier.
#
# Runs daily, next to correction_scan.py, and almost always does nothing. Its
# whole job is the decision: is there enough new material to be worth firing a
# model at? Below the threshold it stays silent (one log line) and costs you
# nothing. See docs/distillation-loop.md.
#
# WHY NOT JUST RUN IT EVERY DAY. A model asked to distill principles from two
# thin corrections will produce principles from two thin corrections — it will
# not say "not enough". Firing on a schedule regardless of material is how a
# rule book fills up with rules nobody's practice actually earned. The threshold
# is not a cost saving; it is the thing that keeps the output honest.
#
# THREE STATES, NEVER TWO (docs/fixed-point-sweep.md):
#   FIRED   — the model ran; the ratchet advances only now
#   SKIPPED — not enough material; silence, one log line
#   FAILED  — the run died, or produced no write. The ratchet does NOT advance,
#             so the material is still pending tomorrow. A failure that quietly
#             counted as "distilled" would drop the evidence on the floor and
#             leave the board looking healthy.
#
# IT PROPOSES; IT NEVER PROMOTES. The only file the model may write is the
# promotion queue, appended. It is forbidden from editing your agent
# instructions, your principles, or any source of truth — because *promoting a
# correction into a rule is a review, and a review is a person*. Moving text
# needs no gate. Promotion does.
#
# INWARD-ONLY, like morning_brief.sh: no send, no publish, no push, no deploy.
# Verify: DISTILL_DRYRUN=1 scripts/distill.sh   (decides, prints, fires nothing)
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

# cron's default PATH omits ~/.local/bin, so AGENT_CMD (claude / codex / gemini,
# installed there by most native installers) is not found and the run dies instantly.
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME}/.local/bin:${PATH}"
# If your agent CLI uses MCP servers or hooks, it may also need `node` on PATH.

# ─── locate & load config ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${LOOP_CONFIG:-$REPO_ROOT/config.env}"
if [[ ! -f "$CONFIG" ]]; then
  echo "config not found: $CONFIG" >&2
  echo "  copy config.env.example → config.env and edit it (or set LOOP_CONFIG)." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG"

: "${AGENT_CMD:?set AGENT_CMD in config.env}"

MATERIAL="${DISTILL_MATERIAL_FILE:?set DISTILL_MATERIAL_FILE in config.env}"
STATE="${DISTILL_STATE_FILE:?set DISTILL_STATE_FILE in config.env}"
QUEUE="${DISTILL_QUEUE_FILE:?set DISTILL_QUEUE_FILE in config.env}"
PROMPT_TPL="${DISTILL_PROMPT_FILE:-$REPO_ROOT/templates/distill-prompt.md}"
THRESHOLD="${DISTILL_THRESHOLD:-5}"
FALLBACK_DAYS="${DISTILL_FALLBACK_DAYS:-7}"
RULES_FILE="${DISTILL_RULES_FILE:-}"         # named so the prompt can forbid it
PRINCIPLES_FILE="${DISTILL_PRINCIPLES_FILE:-}"  # optional: conflict guard
MAX_MATERIAL_LINES="${DISTILL_MAX_MATERIAL_LINES:-400}"
LOGD="${LOG_DIR:-$REPO_ROOT/logs}"
TODAY="$(date +%F)"
mkdir -p "$LOGD"
LOG="${LOGD}/distill_${TODAY}.log"
CRONLOG="${LOGD}/distill_cron.log"

log_state() {  # log_state <STATE> <detail>
  printf '[%s] distill %s %s\n' "$(date '+%F %T')" "$1" "$2" >> "$CRONLOG"
}

[[ -f "$PROMPT_TPL" ]] || { echo "prompt template not found: $PROMPT_TPL" >&2
  log_state FAILED "prompt template missing: $PROMPT_TPL"; exit 1; }

# ─── the decision ──────────────────────────────────────────────────────────
STATUS="$(python3 "$SCRIPT_DIR/correction_scan.py" --state "$STATE" --status 2>>"$LOG")"
if [[ -z "$STATUS" ]]; then
  echo "could not read state: $STATE" >&2
  log_state FAILED "state unreadable: $STATE"
  exit 1
fi
PENDING="$(printf '%s\n' "$STATUS" | sed -n 's/^pending=//p')"
DAYS="$(printf '%s\n' "$STATUS" | sed -n 's/^days_since_distill=//p')"
PENDING="${PENDING:-0}"; DAYS="${DAYS:--1}"

# Fire when the material is thick enough — or when the fallback is due, so that
# a light week still gets distilled instead of piling up forever. Two guards on
# the fallback: it needs pending > 0 (a week with nothing to say is a week with
# nothing to distill, and burning a model on an empty file is the exact failure
# the threshold exists to prevent), and DAYS < 0 means "no clock yet", which is
# not the same as overdue — a fresh install has waited zero days.
REASON=""
if [[ "$PENDING" -ge "$THRESHOLD" ]]; then
  REASON="threshold (${PENDING} >= ${THRESHOLD})"
elif [[ "$PENDING" -gt 0 && "$DAYS" -ge "$FALLBACK_DAYS" ]]; then
  REASON="fallback (${PENDING} pending, ${DAYS}d since last distillation)"
else
  log_state SKIPPED "pending=${PENDING} threshold=${THRESHOLD} days=${DAYS}"
  echo "distill: SKIPPED — pending=${PENDING} (threshold ${THRESHOLD}), ${DAYS}d since last run"
  exit 0
fi

# ─── build the prompt ──────────────────────────────────────────────────────
# The material is the tail of the file after the last "distilled through"
# marker: everything harvested since the previous successful run.
MATERIAL_TEXT="$(awk '/^<!-- distilled through /{buf=""; next} {buf = buf $0 "\n"} END{printf "%s", buf}' \
  "$MATERIAL" 2>/dev/null | tail -n "$MAX_MATERIAL_LINES")"
[[ -n "$MATERIAL_TEXT" ]] || MATERIAL_TEXT="(material file empty or unreadable: ${MATERIAL} — say so in the report rather than inventing candidates)"

PRINCIPLES_BLOCK="(no existing-principles file is configured; skip the conflict check and say so in the report)"
if [[ -n "$PRINCIPLES_FILE" && -f "$PRINCIPLES_FILE" ]]; then
  PRINCIPLES_BLOCK="$(cat "$PRINCIPLES_FILE")"
elif [[ -n "$PRINCIPLES_FILE" ]]; then
  PRINCIPLES_BLOCK="(DISTILL_PRINCIPLES_FILE is set to ${PRINCIPLES_FILE} but that file does not exist — report this as a broken configuration, do not proceed as if there were no principles)"
fi

RULES_NAME="${RULES_FILE:-your agent-instructions file (CLAUDE.md / AGENTS.md)}"

PROMPT="$(cat "$PROMPT_TPL")"
PROMPT="${PROMPT//\{\{TODAY\}\}/$TODAY}"
PROMPT="${PROMPT//\{\{PENDING\}\}/$PENDING}"
PROMPT="${PROMPT//\{\{THRESHOLD\}\}/$THRESHOLD}"
PROMPT="${PROMPT//\{\{MATERIAL_FILE\}\}/$MATERIAL}"
PROMPT="${PROMPT//\{\{QUEUE_FILE\}\}/$QUEUE}"
PROMPT="${PROMPT//\{\{RULES_FILE\}\}/$RULES_NAME}"
PROMPT="${PROMPT//\{\{PRINCIPLES_BLOCK\}\}/$PRINCIPLES_BLOCK}"
PROMPT="${PROMPT//\{\{MATERIAL\}\}/$MATERIAL_TEXT}"

# ─── DRY RUN: decide and print, fire nothing (no cost) ──────────────────────
if [[ "${DISTILL_DRYRUN:-0}" = "1" ]]; then
  echo "=== DRY RUN: agent NOT invoked ==="
  echo "decision : FIRE — ${REASON}"
  echo "command  : ${AGENT_CMD} -p <prompt> ${AGENT_MODEL:+--model ${AGENT_MODEL}} ${AGENT_FLAGS:-}"
  echo "queue    : ${QUEUE}"
  echo "--- PROMPT ---"; printf '%s\n' "$PROMPT"; echo "--- /PROMPT ---"
  exit 0
fi

# ─── fire ──────────────────────────────────────────────────────────────────
{ echo "[$(date '+%F %T')] === distill ${TODAY} — FIRE: ${REASON} ==="; } >> "$LOG"
QUEUE_BEFORE=0
[[ -f "$QUEUE" ]] && QUEUE_BEFORE="$(wc -c < "$QUEUE" | tr -d ' ')"

# CLI-SWAP POINT ▼  (same as morning_brief.sh)
#   Claude : "$AGENT_CMD" -p "$PROMPT" ${AGENT_MODEL:+--model "$AGENT_MODEL"} $AGENT_FLAGS
#   Codex  : "$AGENT_CMD" exec "$PROMPT" $AGENT_FLAGS
#   Gemini : "$AGENT_CMD" -p "$PROMPT" ${AGENT_MODEL:+-m "$AGENT_MODEL"} $AGENT_FLAGS
# shellcheck disable=SC2086
timeout "${AGENT_TIMEOUT:-1200}" "$AGENT_CMD" -p "$PROMPT" \
  ${AGENT_MODEL:+--model "$AGENT_MODEL"} ${AGENT_FLAGS:-} >> "$LOG" 2>&1
RC=$?

# ─── read back, then (and only then) advance the ratchet ───────────────────
# A success exit code is not proof the write happened — the kit's own verifier
# ("read back what you wrote") applies to its own scripts first.
QUEUE_AFTER=0
[[ -f "$QUEUE" ]] && QUEUE_AFTER="$(wc -c < "$QUEUE" | tr -d ' ')"

if [[ "$RC" -ne 0 ]]; then
  log_state FAILED "exit=${RC} pending=${PENDING} (ratchet NOT advanced; material stays pending)"
  echo "distill: FAILED exit=${RC} — see ${LOG}" >&2
elif [[ "$QUEUE_AFTER" -le "$QUEUE_BEFORE" ]]; then
  log_state FAILED "exit=0 but ${QUEUE} did not grow (${QUEUE_BEFORE}->${QUEUE_AFTER}); ratchet NOT advanced"
  echo "distill: FAILED — the run exited 0 but wrote nothing to ${QUEUE}" >&2
  RC=1
else
  python3 "$SCRIPT_DIR/correction_scan.py" --state "$STATE" --material "$MATERIAL" \
    --mark-distilled >> "$LOG" 2>&1
  log_state FIRED "${REASON}; queue ${QUEUE_BEFORE}->${QUEUE_AFTER} bytes"
  echo "distill: FIRED — ${REASON}; review ${QUEUE}"
fi

# ─── ntfy self-ping (inward). FAILED must not read like FIRED. ─────────────
if [[ "${NTFY_ENABLED:-1}" != "0" && -n "${NTFY_TOPIC:-}" ]]; then
  auth=()
  [[ -n "${NTFY_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer ${NTFY_TOKEN}")
  if [[ "$RC" -eq 0 ]]; then
    body="${PENDING} correction(s) distilled into promotion candidates. Review the queue when you have a minute; nothing was applied."
    title="distillation ${TODAY}"
  else
    body="The distillation run did not complete (exit ${RC}). Nothing was distilled and nothing was lost - the material is still waiting for the next run."
    title="distillation FAILED ${TODAY}"
  fi
  curl -s "${auth[@]}" -H "Title: ${title}" -d "$body" \
    "${NTFY_SERVER:-https://ntfy.sh}/${NTFY_TOPIC}" > /dev/null || true
fi

exit "$RC"
