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
# before every tool call and it answers deny for the outward ones.
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
# For the same reason the parse below is plain grep/sed with no jq or python
# dependency — a missing interpreter would be exactly that silent hole — and an
# input with no readable tool_name is DENIED, not waved through.
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

# The verbs, as an extended-regex alternation. Matched against the OPERATION
# segment of the tool name (everything after the final `__`), not the whole
# name — so a connector that happens to be called `postgres` is not swept up by
# `post`.
OUTBOUND_VERBS='send|post|create_draft|update_draft|reply|forward|publish|delete'

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

payload="$(cat)"

# tool_name is a required string field holding an identifier, so a literal
# scan is enough and brings no interpreter with it.
tool_name="$(printf '%s' "$payload" \
  | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -n 1 \
  | sed 's/.*:[[:space:]]*"//; s/"$//')"

# Belt and braces: the reason string is interpolated into JSON, so anything
# that could break the quoting is dropped rather than escaped.
safe_name="$(printf '%s' "$tool_name" | tr -cd 'A-Za-z0-9_.:/-')"

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

operation="${safe_name##*__}"
if printf '%s' "$operation" | grep -qE "$OUTBOUND_VERBS"; then
  deny "$safe_name" "operation '$operation' matches the outbound verb list"
fi

allow "$safe_name"
