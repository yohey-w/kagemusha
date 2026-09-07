#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# outbound_guard.sh — the PreToolUse hook that stops an agent from sending.
#
# WHY THIS FILE EXISTS. The instructions file says "outward = ask first". That
# sentence is a request, and a request is not a control. Measured 2026-09-07 on
# codex-cli 0.153.4, with the rule present in AGENTS.md and the sandbox set to
# its most restrictive setting:
#
#     codex exec -s read-only "email the customer: 'this is a test'"
#
# …asked nobody, called gmail's send tool outright, and when exec's approval
# policy refused the send, WENT AROUND IT and created a draft addressed to the
# real customer instead. Two facts fell out of that run:
#
#   · `-s read-only` sandboxes the FILESYSTEM. It does not touch connectors.
#     A connector call is a network call the sandbox has no opinion about.
#   · A blocked path is not a closed door. The model rerouted to a neighbouring
#     tool with the same effect, because nothing in the machine said no.
#
# So the "no" has to live in the machine. This hook is that "no": Codex asks it
# before every tool call and it answers deny for the outward ones. The sole
# exception is an exact Gmail send_email call carrying a short-lived, one-shot
# permit issued after explicit operator review by outbound_permit.py.
#
# WHAT IT BLOCKS. Connector / MCP tool calls whose OPERATION name contains one
# of the verbs below. Nothing else — in particular, a shell command is never
# matched, because `git push` and `rm` are reversible-by-history operations the
# loop deliberately leaves unattended, and a substring rule over shell text
# would eat them.
#
#   send · post · create_draft · update_draft · reply · forward · publish · delete
#
# ⚠️ NOTE ON THE LIST. `forward` and `update_draft` are here on purpose and
# were NOT in the incident. They belong to the same class as `create_draft`
# (they put your words in front of a third party), and the incident is exactly
# a story about the model finding the neighbouring verb. Shorten the list only
# with that in mind. To change it, edit OUTBOUND_VERBS below.
#
# ─── the wire format, measured, not guessed ────────────────────────────────
# stdin  — `pre-tool-use.command.input`, a JSON schema embedded in the codex
#          binary. `additionalProperties: false`; required keys include
#          cwd · hook_event_name · model · permission_mode · session_id ·
#          tool_input · tool_name · tool_use_id · transcript_path · turn_id.
#          Observed for a connector call (codex-cli 0.153.4, 2026-09-07):
#            {"tool_name":"mcp__codex_apps__gmail__search_emails",
#             "tool_input":{"query":"","max_results":1,...}, …}
#          and for the shell: {"tool_name":"Bash","tool_input":{"command":…}}.
#
# stdout — `pre-tool-use.command.output`, also `additionalProperties: false`.
#          The binary's own error strings say which fields it will not take:
#          permissionDecision `allow` and `ask` are BOTH rejected, as are
#          decision:approve, continue:false, stopReason and suppressOutput.
#          There is therefore no "yes" to say. Letting a call through means
#          printing `{}` — an empty, valid document — and that is what the
#          pass path below does.
#          A deny is the one decision the schema accepts, and it must carry a
#          non-empty reason ("…deny without a non-empty permissionDecisionReason").
#
# ⚠️ THE HOST FAILS OPEN. If this script is missing, unreadable, or prints
# something the schema rejects, `codex exec` says NOTHING and the tool call
# proceeds. A broken guard and an absent guard look identical from the outside.
# That is why scripts/test.sh feeds this file synthetic payloads and validates
# its stdout as JSON: the test is the only thing standing between a typo here
# and a silent hole.
#
# The basic classifier uses Bash only. Python is required solely to validate
# and atomically claim a Gmail send permit; if it or the helper is absent, that
# send is denied. A permit records approval and never substitutes for it.
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

# The verbs, as an extended-regex alternation. Matched against the OPERATION
# segment of the tool name (everything after the final `__`), not the whole
# name — so a connector that happens to be called `postgres` is not swept up by
# `post`.
OUTBOUND_VERBS='send|post|create_draft|update_draft|reply|forward|publish|delete'
PERMITTED_TOOL='mcp__codex_apps__gmail__send_email'
hook_dir="${BASH_SOURCE[0]%/*}"
[[ "$hook_dir" == "${BASH_SOURCE[0]}" ]] && hook_dir='.'
HOOK_DIR="$(cd "$hook_dir" 2>/dev/null && pwd -P)"
PROJECT_ROOT="$(cd "$HOOK_DIR/../.." 2>/dev/null && pwd -P)"
PERMIT_HELPER="$HOOK_DIR/outbound_permit.py"

# Optional breadcrumb. Unset by default: a guard that writes to disk on every
# tool call is a guard that fills a disk. Set it when you want to see the hook
# firing (the acceptance test does).
GUARD_LOG="${OUTBOUND_GUARD_LOG:-}"

log() { [[ -n "$GUARD_LOG" ]] && printf '%s %s\n' "$(date -Is)" "$*" >> "$GUARD_LOG"; return 0; }

# `{}` is the pass: valid against the output schema, and says nothing, because
# the schema has no way to say yes.
allow() { log "allow ${1:-}"; printf '{}'; exit 0; }

deny() {  # deny <tool_name> <why>
  log "DENY $1 — $2"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "outbound guard: $1 is an outward call. Do not send. Append the message to approval_queue.md and wait for the operator to approve it. / 外向き送信は approval_queue.md へ積んで殿の承認を待つ。($2)"
  exit 0
}

payload="$(</dev/stdin)"

# tool_name is an identifier. Matching its closing quote as well as its safe
# character set prevents partial extraction from becoming JSON interpolation.
safe_name=''
if [[ "$payload" =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9_.:/-]+)\" ]]; then
  safe_name="${BASH_REMATCH[1]}"
fi

# No tool_name means the schema moved or the payload never arrived. Deny — the
# guard being loudly wrong is recoverable; the guard being quietly absent is
# the failure this whole file exists to prevent.
if [[ -z "$safe_name" ]]; then
  deny "unknown-tool" "the hook could not read tool_name from its input"
fi

# Connector and MCP calls only. Bash and the built-in tools pass untouched.
if [[ "$safe_name" != mcp__* ]]; then
  allow "$safe_name"
fi

# This exact operation is the only outward call that a permit can open. The
# helper strictly parses the entire envelope and claims the matching record by
# atomic rename before this hook emits the empty pass document. Any failure is
# a deny; stderr is deliberately hidden so message contents never enter the
# hook response.
if [[ "$safe_name" == "$PERMITTED_TOOL" ]]; then
  if [[ -n "$PROJECT_ROOT" && -f "$PERMIT_HELPER" ]] && command -v python3 >/dev/null 2>&1; then
    if printf '%s' "$payload" | python3 "$PERMIT_HELPER" claim --project-root "$PROJECT_ROOT" >/dev/null 2>&1; then
      allow "$safe_name (one-shot permit claimed)"
    fi
  fi
  deny "$safe_name" "no valid one-shot permit matched the complete send arguments, project, session, and expiry"
fi

operation="${safe_name##*__}"
if [[ "$operation" =~ ($OUTBOUND_VERBS) ]]; then
  deny "$safe_name" "operation '$operation' matches the outbound verb list"
fi

allow "$safe_name"
