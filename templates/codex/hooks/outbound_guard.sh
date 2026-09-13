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
# before every tool call and it answers deny for the outward ones. The only
# exceptions are the exact Gmail and Slack send operations named below, each
# carrying a short-lived, one-shot permit issued after explicit operator review
# by outbound_permit.py.
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
# ─── the same verb, one level down: a send hidden inside `exec` ────────────
# MEASURED 2026-09-13 (local/state/codex_desktop_test_20260913/, test_matrix.md
# §再測 and T7_rootcause.txt; the desktop app on GPT-5.6 Sol). The app shows the
# model exactly three tools — `exec` · `spawn_agent` · `wait_agent` — and a
# connector is reached from JavaScript INSIDE exec:
#
#     tools.mcp__codex_apps__gmail_create_draft({to:"…", subject:"…", …})
#
# So PreToolUse is handed tool_name `exec`, the "connector and MCP calls only"
# line below waved it through, and the draft to the address in the prompt was
# created — with the hook installed, trusted, and its trusted_hash written to
# the user config. The CLI is the same shape: across 83 rollouts under
# ~/.codex/sessions/2026/09/, every one of 9,222 code-executing calls is `exec`
# (`custom_tool_call`, name `exec`), several carrying
# `tools.mcp__codex_apps__gmail_search_emails(…)` — e.g.
# rollout-2026-09-07T13-46-52-01a07a30-*.jsonl. The A7 re-test of 2026-09-07
# denied its send because that one WAS a direct MCP call
# (`mcp__codex_apps__gmail__create_draft`); both spellings still deny.
#
# The verb list was never the hole. The hole was that on this path the outward
# call never appears in tool_name at all.
#
# WHAT IS SCANNED, AND WHY THE WHOLE DOCUMENT. For a code-executing tool the
# classifier reads the ENTIRE payload text rather than one field, because the
# key the code string arrives under is [未計測] — the rollout records it as
# `custom_tool_call.input`, but no PreToolUse payload for `exec` has been
# captured, so `code` / `cmd` / `command` / `input` are all guesses. Reading the
# raw document removes the guess and costs nothing: an `mcp__…` identifier
# contains no character that JSON escapes, so it survives `\"` and `\n`
# untouched, and no other field in the envelope (cwd · session_id · model ·
# permission_mode · transcript_path) can hold one.
#
# THE SHELL IS STILL OUT OF SCOPE. `exec_command` and `Bash` carry shell text,
# a shell cannot reach a connector, and a substring rule over command text would
# eat `git push`. Only tools that execute CODE are scanned — measured, that is
# `exec`; `node_repl` rides along because T7 found exec's implementation to be
# the MCP server node_repl.exe, and a renamed door should not reopen this.
#
# WHAT IT COSTS, REPLAYED RATHER THAN ESTIMATED. Every distinct `exec` call in
# ~/.codex/sessions/2026/09/ — 8,635 of them, real work — was fed to this file.
# 8,610 passed. Of the 25 denied: 4 really were a send issued from inside exec;
# 3 were the tool table being searched for the send tool by name; and 18 were
# the agent EDITING THIS KIT — apply_patch text carrying outbound_guard.sh or
# test_m_codex.sh, an `rg` for one of the literals, a probe building a fake hook
# envelope. That is the whole false-positive class, and it is worth knowing the
# shape of it: patching the lines below that name a send tool, from inside exec,
# will be refused by the rule those lines install. Outside this repository's own
# maintenance the replay denied nothing. None of the 25 came from the run-time
# rules in part 2 — they cost zero false positives across all 8,635.
#
# ⚠️ A PERMIT NEVER OPENS A SEND INSIDE exec. The one-shot permit binds an
# approved send to its exact arguments; inside a code string there are no
# arguments to bind, only source text that can build them at run time. An
# approved send must therefore travel as a direct connector call — which on the
# desktop app is currently not offered at all (exec is the only tool it shows,
# and its namespace has one `_` where the permit keys below have two). That is
# a real limit of this control, recorded here rather than papered over.
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
# and atomically claim an exact send permit; if it or the helper is absent,
# that send is denied. A permit records approval and never substitutes for it.
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

# The verbs, as an extended-regex alternation. Matched against the OPERATION
# segment of the tool name (everything after the final `__`), not the whole
# name — so a connector that happens to be called `postgres` is not swept up by
# `post`.
OUTBOUND_VERBS='send|post|create_draft|update_draft|reply|forward|publish|delete'
GMAIL_PERMITTED_TOOL='mcp__codex_apps__gmail__send_email'
SLACK_PERMITTED_TOOL='mcp__codex_apps__slack__slack_send_message'
SLACK_READ_OPERATIONS='slack_get_reactions|slack_list_channel_members|slack_list_starred_items|slack_list_user_channels|slack_list_user_conversations|slack_list_user_groups|slack_list_workspaces|slack_read_canvas|slack_read_channel|slack_read_file|slack_read_thread|slack_read_user_profile|slack_search_channels|slack_search_emojis|slack_search_public|slack_search_public_and_private|slack_search_users'

# Tools that run CODE, and can therefore reach a connector from inside their
# argument. Matched against the operation segment, so a namespaced spelling
# (mcp__codex_apps__node_repl__exec) lands here too.
CODE_EXEC_TOOLS='exec|node_repl'

# The three JavaScript quote characters, written this way so the file itself
# stays free of a stray backtick.
JS_QUOTES=$'"\'\x60'
# A name split across a concatenation: "mcp__codex_apps__gmail_" + "send_email".
RE_CONCAT_GLUE="[${JS_QUOTES}][[:space:]]*[+][[:space:]]*[${JS_QUOTES}]"
# A name assembled at run time instead of written down: `mcp__${app}_send`.
RE_TEMPLATE_NAME='mcp__[A-Za-z0-9_]*\$\{'
# tools[…] indexed by anything that is not a quoted literal — tools[name].
RE_COMPUTED_INDEX="tools\\[[[:space:]]*[^${JS_QUOTES}[:space:]]"
# The whole table walked as data: Object.keys(tools), Object.entries(tools).
RE_TOOLS_ENUM='Object\.(keys|values|entries)\([[:space:]]*tools'
# A tool resolved out of ALL_TOOLS and immediately CALLED. Listing the table is
# the normal inbound move and stays allowed; invoking the result is not.
RE_RESOLVED_CALL='ALL_TOOLS[^;]*[])][[:space:]]*\('

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

# ─── the classifier for the code-executing tools ───────────────────────────
# embedded_outbound <payload text> → prints the offending identifier, or a
# short label for a name the code never spells out, and returns 0; prints
# nothing and returns 1 when the code is clean.
#
# Bash only, deliberately: the same reason the rest of the classifier is. A
# guard that needs grep, sed or python to decide is a guard that fails OPEN on
# a machine that is missing one of them, and fails open in silence.
#
# KNOWN BLIND SPOTS, written down rather than pretended away. A name spelled
# with character escapes (`gmail_send_email`), or one that arrives from
# outside the code — read from a file, returned by an earlier tool call — is
# not visible here. This rule raises the cost of the accidental send that
# actually happened; it is not a sandbox.
embedded_outbound() {
  local text="$1" unescaped joined rest id op prev iter=0
  local bs='\' dq='"'

  # Undo JSON's escaping so the text reads as the model wrote it. The doubled
  # backslash goes first, or `\\"` is misread as an escaped quote.
  unescaped="${text//"${bs}${bs}"/ }"
  unescaped="${unescaped//"${bs}${dq}"/"$dq"}"
  # A line break arrives as the two characters \ and n, which are not
  # whitespace — so `[[:space:]]*` steps over a space but NOT over a newline,
  # and a name split across two lines walks past the rules below. Measured
  # before the fix: `"…gmail_" +⏎"send_email"` and a find(…) invoked on the
  # next line both passed. Restoring the break as one space is exactly what
  # the source said, and a space cannot glue two identifiers into one.
  unescaped="${unescaped//"${bs}n"/ }"
  unescaped="${unescaped//"${bs}t"/ }"
  unescaped="${unescaped//"${bs}r"/ }"

  # Re-join a name split across a concatenation: "…gmail_" + "send_email".
  joined="$unescaped"
  while [[ "$joined" =~ $RE_CONCAT_GLUE ]]; do
    prev="$joined"
    joined="${joined/"${BASH_REMATCH[0]}"/}"
    [[ "$joined" == "$prev" ]] && break      # never spin on a pattern that
    (( ++iter > 500 )) && break              # refuses to shrink
  done

  # 1) the name is there, literally — `tools.mcp__…`, `tools["mcp__…"]`,
  #    `ALL_TOOLS.find(t => t.name === "mcp__…")`, or the glued form above.
  rest="$joined"
  while [[ "$rest" =~ mcp__[A-Za-z0-9_]+ ]]; do
    id="${BASH_REMATCH[0]}"
    rest="${rest#*"$id"}"
    op="${id##*__}"
    if [[ "$id" == *slack* ]]; then
      # The desktop spelling doubles the app prefix (slack_slack_read_thread),
      # so the read allowlist is matched with that prefix optional. Anything
      # the list does not name fails closed, exactly as the direct path does.
      [[ "$op" =~ ^(slack_)?($SLACK_READ_OPERATIONS)$ ]] || { printf '%s' "$id"; return 0; }
      continue
    fi
    [[ "$op" =~ ($OUTBOUND_VERBS) ]] && { printf '%s' "$id"; return 0; }
  done

  # 2) the name is never written down, so rule 1 cannot see it. Reading does
  #    not need any of these forms; reaching a verb past the guard does.
  [[ "$unescaped" =~ $RE_TEMPLATE_NAME  ]] && { printf 'a tool name built by interpolation'; return 0; }
  [[ "$unescaped" =~ $RE_COMPUTED_INDEX ]] && { printf 'tools[] indexed by a computed name'; return 0; }
  [[ "$unescaped" =~ $RE_TOOLS_ENUM     ]] && { printf 'the tool table enumerated as data'; return 0; }
  [[ "$unescaped" =~ $RE_RESOLVED_CALL  ]] && { printf 'a tool resolved from ALL_TOOLS and then called'; return 0; }
  return 1
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

operation="${safe_name##*__}"

# A tool that runs CODE can reach a connector from inside its argument, where
# tool_name never mentions it. Scan the code before the classifier below waves
# `exec` through as "not an MCP call". Clean code falls through to the ordinary
# path; it is not allowed early, so a namespaced exec still meets every rule.
#
# The pass stays fail-OPEN by design and by symmetry with the rest of the file:
# nothing here parses JSON, so there is no parse to fail, and code the scanner
# does not recognise prints the empty document exactly as before. On the
# desktop app `exec` is the ONLY tool the model has, so a rule that denied
# whatever it could not read would not be a guard — it would be an off switch.
if [[ "$operation" =~ ^($CODE_EXEC_TOOLS)$ ]]; then
  embedded="$(embedded_outbound "$payload")"
  if [[ -n "$embedded" ]]; then
    deny "$safe_name" "the code carries an outward connector call ($embedded). Do not make outward calls from inside $operation; an approved send must be a direct connector call that a one-shot permit can bind / 外向き呼び出しは exec の中で行わず、承認済みなら直接ツールで許可票を使え"
  fi
fi

# Connector and MCP calls only. Bash and the built-in tools pass untouched.
if [[ "$safe_name" != mcp__* ]]; then
  allow "$safe_name"
fi

# These exact operations are the only outward calls that a permit can open. The
# helper strictly parses the entire envelope and claims the matching record by
# atomic rename before this hook emits the empty pass document. Any failure is
# a deny; stderr is deliberately hidden so message contents never enter the
# hook response.
if [[ "$safe_name" == "$GMAIL_PERMITTED_TOOL" || "$safe_name" == "$SLACK_PERMITTED_TOOL" ]]; then
  if [[ -n "$PROJECT_ROOT" && -f "$PERMIT_HELPER" ]] && command -v python3 >/dev/null 2>&1; then
    if printf '%s' "$payload" | python3 "$PERMIT_HELPER" claim --project-root "$PROJECT_ROOT" >/dev/null 2>&1; then
      allow "$safe_name (one-shot permit claimed)"
    fi
  fi
  deny "$safe_name" "no valid one-shot permit matched the complete send arguments, project, session, and expiry"
fi

# The Slack connector includes write operations whose names do not contain one
# of the generic outbound verbs (add_reaction, join_conversation, upload, …).
# Keep its read side as a closed allowlist and fail closed on every other Slack
# operation. This is deliberately scoped to the measured wire namespace; the
# JavaScript wrapper spelling has one fewer `__` and is not a permit target.
if [[ "$safe_name" == mcp__codex_apps__slack__* ]]; then
  if [[ "$operation" =~ ^($SLACK_READ_OPERATIONS)$ ]]; then
    allow "$safe_name"
  fi
  deny "$safe_name" "Slack operation '$operation' is not on the read-only allowlist"
fi

if [[ "$operation" =~ ($OUTBOUND_VERBS) ]]; then
  deny "$safe_name" "operation '$operation' matches the outbound verb list"
fi

allow "$safe_name"
