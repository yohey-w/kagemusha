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
# IT PROPOSES; IT NEVER PROMOTES. Promoting a correction into a rule is a
# review, and a review is a person. Moving text needs no gate. Promotion does.
#
# THE MODEL WRITES NOTHING. Not the rules file, not the queue — nothing. It is
# invoked WITHOUT the permission-skipping flags the other scripts use, so its
# file tools are denied by the CLI itself; it prints its report to stdout, this
# script validates that report against a frozen batch manifest, and THIS SCRIPT
# does the appending. "Only write the queue" as a sentence in a prompt is a
# request, not a boundary — and the material it is reading is your own past
# input, i.e. text this script did not write and cannot vouch for. A prompt
# cannot be the thing that stops text in the prompt.
#
# ONLY WHAT THE MODEL ACTUALLY READ IS RETIRED. The batch is frozen before the
# call (fixed event ids + a sha256 of the exact text), the model must account
# for every id in it, and only those ids advance. Otherwise the line cap silently
# retires the oldest events it trimmed, and so does anything the daily harvest
# appends while the model is still running.
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
# The weekly fallback is OFF by default (0). A fallback that fires on a single
# pending correction is the exact failure the threshold exists to prevent, on a
# timer. A slow week gets a REMINDER in the skip line instead — see below.
FALLBACK_DAYS="${DISTILL_FALLBACK_DAYS:-0}"
STALE_DAYS="${DISTILL_STALE_DAYS:-7}"
RULES_FILE="${DISTILL_RULES_FILE:-}"         # named so the prompt can forbid it
PRINCIPLES_FILE="${DISTILL_PRINCIPLES_FILE:-}"  # optional: conflict guard
MAX_MATERIAL_LINES="${DISTILL_MAX_MATERIAL_LINES:-400}"
BATCH_DIR="${DISTILL_BATCH_DIR:-$(dirname "$MATERIAL")/batches}"
# Deliberately NOT $AGENT_FLAGS. That key carries --dangerously-skip-permissions
# for the scripts that need an agent with hands; this run must not have hands.
# Empty = the CLI's own default, which in headless mode is "deny" (verified: a
# `claude -p` asked to write a file with no flags reports the denial and exits 0
# without creating it). Override only if your CLI needs a flag to be read-only.
DISTILL_FLAGS="${DISTILL_AGENT_FLAGS-}"
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

# Fire when the material is thick enough. The fallback fires on time instead of
# on material, so it is OFF unless you turned it on (DISTILL_FALLBACK_DAYS > 0);
# when on it still needs pending > 0, and DAYS < 0 ("no clock yet") is not
# overdue — a fresh install has waited zero days, and treating that as overdue
# made the fallback fire on day one and cancel the threshold.
#
# With the fallback off, a slow week is not silently forgotten: material older
# than DISTILL_STALE_DAYS is NAMED in the skip line and the cron log. A reminder
# is what a thin week needs. A distillation is not.
REASON=""
if [[ "$PENDING" -ge "$THRESHOLD" ]]; then
  REASON="threshold (${PENDING} >= ${THRESHOLD})"
elif [[ "$FALLBACK_DAYS" -gt 0 && "$PENDING" -gt 0 && "$DAYS" -ge "$FALLBACK_DAYS" ]]; then
  REASON="fallback (${PENDING} pending, ${DAYS}d since last distillation)"
else
  STALE=""
  if [[ "$PENDING" -gt 0 && "$DAYS" -ge "$STALE_DAYS" ]]; then
    STALE=" — ${PENDING} event(s) have been waiting ${DAYS}d; raise DISTILL_THRESHOLD's bar or set DISTILL_FALLBACK_DAYS to distil them anyway"
  fi
  log_state SKIPPED "pending=${PENDING} threshold=${THRESHOLD} days=${DAYS}${STALE:+ STALE}"
  echo "distill: SKIPPED — pending=${PENDING} (threshold ${THRESHOLD}), ${DAYS}d since last run${STALE}"
  exit 0
fi

# ─── freeze the batch ──────────────────────────────────────────────────────
# Before anything is sent: which events go in, written down. The batch takes the
# OLDEST pending events first and only whole ones; anything past the line cap
# stays pending instead of being trimmed off the front and then marked done.
BATCH_OUT="$(python3 "$SCRIPT_DIR/correction_scan.py" --state "$STATE" --material "$MATERIAL" \
  --emit-batch --batch-dir "$BATCH_DIR" --max-lines "$MAX_MATERIAL_LINES" 2>>"$LOG")"
BATCH_ID="$(printf '%s\n' "$BATCH_OUT" | sed -n 's/^batch_id=//p')"
BATCH_TXT="$(printf '%s\n' "$BATCH_OUT" | sed -n 's/^text=//p')"
BATCH_JSON="$(printf '%s\n' "$BATCH_OUT" | sed -n 's/^manifest=//p')"
BATCH_N="$(printf '%s\n' "$BATCH_OUT" | sed -n 's/^events=//p')"
BATCH_DEFER="$(printf '%s\n' "$BATCH_OUT" | sed -n 's/^deferred=//p')"
if [[ -z "$BATCH_ID" || ! -f "$BATCH_TXT" || ! -f "$BATCH_JSON" ]]; then
  log_state FAILED "could not freeze a batch (state=${STATE}); ratchet NOT advanced"
  echo "distill: FAILED — could not freeze a batch; see ${LOG}" >&2
  exit 1
fi
MATERIAL_TEXT="$(cat "$BATCH_TXT")"

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
PROMPT="${PROMPT//\{\{BATCH_ID\}\}/$BATCH_ID}"
PROMPT="${PROMPT//\{\{EVENT_COUNT\}\}/$BATCH_N}"
PROMPT="${PROMPT//\{\{MATERIAL\}\}/$MATERIAL_TEXT}"

# ─── DRY RUN: decide and print, fire nothing (no cost) ──────────────────────
if [[ "${DISTILL_DRYRUN:-0}" = "1" ]]; then
  echo "=== DRY RUN: agent NOT invoked ==="
  echo "decision : FIRE — ${REASON}"
  echo "command  : ${AGENT_CMD} -p <prompt> ${AGENT_MODEL:+--model ${AGENT_MODEL}} ${DISTILL_FLAGS}"
  echo "batch    : ${BATCH_ID} — ${BATCH_N} event(s) in, ${BATCH_DEFER} deferred to the next run"
  echo "manifest : ${BATCH_JSON}"
  echo "queue    : ${QUEUE}  (written by THIS script, not by the model)"
  echo "--- PROMPT ---"; printf '%s\n' "$PROMPT"; echo "--- /PROMPT ---"
  exit 0
fi

# ─── fire (no hands: stdout only) ──────────────────────────────────────────
{ echo "[$(date '+%F %T')] === distill ${TODAY} — FIRE: ${REASON} (batch ${BATCH_ID}) ==="; } >> "$LOG"
MODEL_OUT="${BATCH_TXT%.txt}.out"

# CLI-SWAP POINT ▼  (same as morning_brief.sh, minus the permissions)
#   Claude : "$AGENT_CMD" -p "$PROMPT" ${AGENT_MODEL:+--model "$AGENT_MODEL"} $DISTILL_FLAGS
#   Codex  : "$AGENT_CMD" exec "$PROMPT" $DISTILL_FLAGS
#   Gemini : "$AGENT_CMD" -p "$PROMPT" ${AGENT_MODEL:+-m "$AGENT_MODEL"} $DISTILL_FLAGS
# Whatever you put here, do NOT put the permission-skipping flag in it: this run
# is supposed to be unable to touch a file, and the report comes back on stdout.
# shellcheck disable=SC2086
timeout "${AGENT_TIMEOUT:-1200}" "$AGENT_CMD" -p "$PROMPT" \
  ${AGENT_MODEL:+--model "$AGENT_MODEL"} ${DISTILL_FLAGS} > "$MODEL_OUT" 2>>"$LOG"
RC=$?
cat "$MODEL_OUT" >> "$LOG" 2>/dev/null || true

# ─── validate, THEN write, THEN advance the ratchet ────────────────────────
# The order is the whole point. Nothing reaches the review queue that has not
# been checked against the manifest, and nothing is retired that has not reached
# the queue. An exit code of 0 proves only that a process ended.
if [[ "$RC" -ne 0 ]]; then
  log_state FAILED "exit=${RC} batch=${BATCH_ID} pending=${PENDING} (ratchet NOT advanced; material stays pending)"
  echo "distill: FAILED exit=${RC} — see ${LOG}" >&2
else
  SECTION="$(python3 "$SCRIPT_DIR/correction_scan.py" --batch "$BATCH_JSON" \
    --check-output "$MODEL_OUT" 2>>"$LOG")"
  VRC=$?
  if [[ "$VRC" -ne 0 || -z "$SECTION" ]]; then
    log_state FAILED "exit=0 but the output failed validation against batch ${BATCH_ID}; ratchet NOT advanced"
    echo "distill: FAILED — the run exited 0 but its output did not account for the batch; see ${LOG}" >&2
    RC=1
  else
    QUEUE_BEFORE=0
    [[ -f "$QUEUE" ]] && QUEUE_BEFORE="$(wc -c < "$QUEUE" | tr -d ' ')"
    mkdir -p "$(dirname "$QUEUE")"
    { printf '\n<!-- distill %s · batch %s · %s event(s) · source: %s -->\n' \
        "$TODAY" "$BATCH_ID" "$BATCH_N" "$BATCH_JSON"
      printf '%s\n' "$SECTION"; } >> "$QUEUE"
    QUEUE_AFTER=0
    [[ -f "$QUEUE" ]] && QUEUE_AFTER="$(wc -c < "$QUEUE" | tr -d ' ')"
    if [[ "$QUEUE_AFTER" -le "$QUEUE_BEFORE" ]]; then
      # Our own write, read back. The kit's "read back what you wrote" verifier
      # applies to the kit, and now the writer being checked is this script.
      log_state FAILED "the queue append did not land (${QUEUE_BEFORE}->${QUEUE_AFTER}); ratchet NOT advanced"
      echo "distill: FAILED — could not append to ${QUEUE}" >&2
      RC=1
    else
      python3 "$SCRIPT_DIR/correction_scan.py" --state "$STATE" --material "$MATERIAL" \
        --mark-distilled --batch "$BATCH_JSON" >> "$LOG" 2>&1
      log_state FIRED "${REASON}; batch ${BATCH_ID} (${BATCH_N} event(s), ${BATCH_DEFER} deferred); queue ${QUEUE_BEFORE}->${QUEUE_AFTER} bytes"
      echo "distill: FIRED — ${REASON}; ${BATCH_N} event(s) distilled, ${BATCH_DEFER} deferred; review ${QUEUE}"
    fi
  fi
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
