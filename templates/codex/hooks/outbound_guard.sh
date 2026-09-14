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
# ⚠️ THE FIRST VERSION OF THIS RULE WAS BROKEN BY ONE LINE. It listed the bad
# shapes — `tools["…"]`, `"…" + "…"`, `${…}`, `Object.values(tools)` — and an
# adversarial review (2026-09-13) walked straight past it with
#
#     const t = tools; t[name](…)
#
# and eleven more: Reflect.get, `tools?.[n]`, destructuring, fromCharCode,
# atob, .replace, .join(""), a prefix variable, a template literal that does
# not start with `${`, new Function, and an ALL_TOOLS alias. All of them
# reached the real send tools. The lesson generalises: the ways to hide a NAME
# are unbounded, so enumerating them is always one line behind. The ways to
# REACH the tool object are a small closed set, and all but one are dynamic.
# The rule below is therefore inverted — one good shape is allowed and every
# other contact with `tools` is denied — and an obfuscated name becomes inert,
# because there is no longer a dispatch to hand it to.
#
# THE SHELL IS STILL OUT OF SCOPE. `exec_command` and `Bash` carry shell text,
# a shell cannot reach a connector, and a substring rule over command text would
# eat `git push`. Only tools that execute CODE are scanned — measured, that is
# `exec`; `node_repl` rides along because T7 found exec's implementation to be
# the MCP server node_repl.exe, and a renamed door should not reopen this.
#
# WHAT IT COSTS, REPLAYED RATHER THAN ESTIMATED. Every distinct `exec` call in
# ~/.codex/sessions/2026/09/ — 8,635 of them, real work — was fed to this file.
# 8,541 passed; 94 were denied (1.09%), and the breakdown is the point:
#
#     79  ALL_TOOLS — listing the tool table. Refused on purpose, see below
#      8  apply_patch text editing THIS KIT, which quotes send tools verbatim
#      5  a real write or send, actually called from inside exec
#      2  prose and shell text that happens to read as JavaScript
#
# ⚠️ LISTING THE TOOL TABLE NOW COSTS SOMETHING, AND THAT IS A DELIBERATE
# TRADE. `ALL_TOOLS` is how an agent asks "what connectors do I have?", and it
# is also the one object that hands out a callable without anyone writing its
# name — `const AT = ALL_TOOLS; AT.find(…)(…)` was a working bypass. It cannot
# be both. Enumerate the tools somewhere other than `exec`: write the list into
# the instructions file, or keep it in a skill. An indirect READ is refused for
# the same reason, so reads must be written as direct calls.
#
# The `.replace` / `.join("")` pair that the review found in bypasses is NOT
# matched here. Measured, those two appear in 4.5% of real calls (385 of 8,635)
# doing ordinary string work, and once dynamic dispatch is closed an obfuscated
# name has nothing to dispatch to — so matching them would buy nothing and cost
# seventeen times the current false-positive rate.
#
# ⚠️ A PERMIT NEVER OPENS A SEND INSIDE exec. The one-shot permit binds an
# approved send to its exact arguments; inside a code string there are no
# arguments to bind, only source text that can build them at run time. An
# approved send must therefore travel as a direct connector call.
#
# ⚠️ AND THE DESKTOP APP DOES OFFER ONE — measured 2026-09-14, correcting what
# this comment said before. When the JavaScript wrapper dispatches, the inner
# call reaches PreToolUse in its own right: the hook was handed tool_name
# `mcp__codex_apps__gmail__create_draft` and denied it there, not at `exec`.
# The wrapper's own spelling has one `_` and the envelope's has two, so ONE
# connector answers to two names. `same_permit_tool` below absorbs exactly
# that difference and nothing else.
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

# ─── the read allowlist, for connector calls made from inside code ─────────
# Derived from the tool catalogue, not invented: 275 distinct
# mcp__codex_apps__* names appear across the 83 rollouts in
# ~/.codex/sessions/2026/09/, and `codex plugin list` names the installed
# connectors (gmail · slack · notion · github · google-drive · google-calendar).
# A name is a read when it carries a read token AND carries no write token,
# both as whole `_`-delimited words — `ready_for_review` is not a `read`, and
# `postgres` is not a `post`. Checked against all 275: 137 allow, 138 deny,
# no outbound name in the allow set and no measured read in the deny set.
# Every token below hits at least one real name; `describe` and `count` hit
# none and are therefore not shipped. To widen the allowlist, add a token here.
READ_TOKENS='search|get|list|read|fetch|export|query|find'
WRITE_TOKENS='send|post|create|update|delete|draft|reply|forward|publish|upload|import|archive|label|modify|move|copy|duplicate|invite|join|leave|schedule|edit|add|remove|complete|set|rename|restore|trash|star|pin|react|write|share|clear|append|insert|mark|merge|execute|run|rerun|enable|disable|lock|unlock|resolve|dismiss|convert|request|assign|download|bulk|apply|revoke|install|uninstall|deploy|transfer'
RE_READ_TOKEN="(^|_)($READ_TOKENS)(_|$)"
RE_WRITE_TOKEN="(^|_)($WRITE_TOKENS)(_|$)"

# ─── what the code may do with the `tools` object ──────────────────────────
# The ONLY permitted shape is a static member access, `tools.<name>`. Every
# other way of touching the object is a way of reaching a name the scanner
# cannot read, so every other way is denied.
#
# A1 — the reference ENDS: `tools[`, `tools)`, `tools;`, `tools,`, `tools ||`,
#      `tools :`, or end of code. `.` is absent (that is the allowed form) and
#      so are `/` and `-`, or every `local/tools/…` path and `--tools` flag in
#      a shell string would be read as JavaScript.
RE_TOOLS_LOOSE='(^|[^A-Za-z0-9_$])tools[[:space:]]*($|[][?),;}=|&+:<>*%^~!])'
# A2 — the reference is STORED or PASSED: `= tools`, `(tools`, `, tools`. The
#      preceding punctuator is what separates code from prose — "filesystem
#      tools to open" is preceded by a letter and is left alone. A following
#      identifier means a line break stood there (`const t = tools` ⏎ `t[n]`),
#      which is JavaScript's semicolon insertion and an alias all the same.
RE_TOOLS_ALIAS='[=(\[{,;:?!&|][[:space:]]*tools[[:space:]]*($|[^.])'
# B — a static connector call: tools.<identifier>, captured for the allowlist.
RE_TOOLS_DOT='(^|[^A-Za-z0-9_$])tools[[:space:]]*\.[[:space:]]*([A-Za-z_$][A-Za-z0-9_$]*)'
# A3 — the same object reached through the global scope instead of by name:
#      `globalThis["tools"]`, `this.tools`, `self`/`window`/`global`. Rules A1
#      and A2 both read the text around the identifier `tools`, and in
#      `globalThis["tools"]` that identifier sits inside a string, with a quote
#      on each side — neither rule fires. Found by review, 2026-09-13. Whether
#      the sandbox actually resolves it is NOT VERIFIED [未確認]; it is closed
#      because a door whose lock is untested is still a door.
JS_QUOTES=$'"\'\x60'
RE_GLOBAL_TOOLS="(^|[^A-Za-z0-9_.\$])(globalThis|this|self|window|global)[[:space:]]*([.]|\\[[[:space:]]*[${JS_QUOTES}])[[:space:]]*tools([^A-Za-z0-9_\$]|\$)"
# C — the tool table itself. Listing it is an ordinary inbound move, but it is
#     also the one object that hands out a callable without naming it, and an
#     alias (`const AT = ALL_TOOLS`) puts it back out of reach. Denied whole.
RE_ALL_TOOLS='(^|[^A-Za-z0-9_$])ALL_TOOLS'
# D — constructs that MAKE code or resolve a property without writing its name.
#     These defeat any scanner by construction, so they are refused outright.
#     `import` is deliberately NOT here. Measured over the 8,635 real calls it
#     fires 15 times and every one is source being WRITTEN to a file — Python's
#     `from x import (` and a TypeScript `import(url)` inside a patch — never
#     JavaScript the sandbox evaluates. It also buys nothing: a module cannot
#     be dispatched onto a hidden name once A has closed that door, and a
#     data: URL carrying a literal `tools.<name>` is read by rule B anyway.
RE_CODE_FROM_DATA='(^|[^A-Za-z0-9_$.])(eval|Function)[[:space:]]*\(|new[[:space:]]+Function|Reflect[[:space:]]*\.[[:space:]]*get|[.[:space:]]atob[[:space:]]*\(|fromCharCode'

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
# embedded_outbound <payload text> → prints the offending name, or a short
# label for a shape that hides the name, and returns 0; prints nothing and
# returns 1 when the code is clean.
#
# THIS RULE IS INVERTED, AND THAT IS THE WHOLE POINT. The first version of it
# listed bad shapes and denied those. An adversarial review (2026-09-13) broke
# it in one line — `const t = tools; t[name](…)` — and then eleven more ways:
# Reflect.get, optional chaining, destructuring, String.fromCharCode, atob,
# .replace, .join(""), a prefix variable, a template literal, new Function.
# Every one of them reached the real Gmail and Slack send tools. The lesson is
# structural, not a missing pattern: the ways to hide a NAME are unbounded, so
# a list of them is always one line behind. The ways to REACH the tool object
# are not — JavaScript has a small, closed set, and all but one of them are
# dynamic. So the rule now names the one good shape and refuses the rest:
#
#   ALLOWED   tools.<name>(…)   written out, called on the spot, and <name>
#             on the read allowlist when it is a connector
#   DENIED    everything else that touches `tools` or `ALL_TOOLS`
#
# An obfuscated name is then inert: you cannot dispatch on it without one of
# the dynamic forms, and those are gone. That is why there is no rule here for
# .replace or .join — they were measured in 4.5% of real calls, and denying
# them buys nothing once the dispatch is closed.
#
# Bash only, deliberately: a guard that needs grep, sed or python to decide is
# a guard that fails OPEN on a machine missing one of them, and fails open in
# silence.
#
# WHAT IT STILL CANNOT SEE, written down rather than pretended away:
#   · a code tool that Codex ships under a name not in CODE_EXEC_TOOLS. The
#     measured set is exactly `exec` (9,222 of 9,222 code-executing calls); a
#     future `run_code` would be unguarded until added here.
#   · `spawn_agent`: a child's own tool calls are not this payload. Whether
#     the hook fires for the child is NOT VERIFIED [未確認] — it needs a live
#     Codex to answer, and nothing in the repository states it either way.
#   · homoglyphs and zero-width characters inside a name. Measured on node:
#     they either fail to parse or address a key that does not exist, so they
#     cannot call anything — detection is unnecessary, not missing.
#   · the shell can still run `outbound_permit.py issue`, whose only gate is
#     the `--confirm-user-approved` flag it is asked to pass. A permit records
#     approval; it was never a proof of one. Unchanged by this rule.
embedded_outbound() {
  local text="$1" code rest name op
  local bs='\' dq='"'

  # Undo JSON's escaping so the text reads as the model wrote it. The doubled
  # backslash goes first, or `\\"` is misread as an escaped quote. A line break
  # arrives as the two characters \ and n, which are NOT whitespace, so
  # `[[:space:]]*` would stop dead at one; restoring it as a single space is
  # exactly what the source said, and a space cannot glue two identifiers.
  code="${text//"${bs}${bs}"/ }"
  code="${code//"${bs}${dq}"/"$dq"}"
  code="${code//"${bs}n"/ }"
  code="${code//"${bs}t"/ }"
  code="${code//"${bs}r"/ }"

  # D — code made out of data, and property lookup that never spells the name.
  [[ "$code" =~ $RE_CODE_FROM_DATA ]] && { printf 'code built at run time - eval/Function/Reflect.get/atob/fromCharCode'; return 0; }
  # C — the tool table as an object: hands out a callable without naming it.
  [[ "$code" =~ $RE_ALL_TOOLS ]] && { printf 'ALL_TOOLS'; return 0; }
  # A — every reference to `tools` that is not a static member access.
  [[ "$code" =~ $RE_TOOLS_LOOSE  ]] && { printf 'a dynamic reference to the tools object'; return 0; }
  [[ "$code" =~ $RE_TOOLS_ALIAS  ]] && { printf 'the tools object stored or passed on'; return 0; }
  [[ "$code" =~ $RE_GLOBAL_TOOLS ]] && { printf 'the tools object reached through the global scope'; return 0; }

  # B — what is left is `tools.<name>`. A connector among them must be called
  # on the spot and must be a read. Anything else — a write, an unknown name,
  # or a bare reference being kept for later — is refused.
  rest="$code"
  while [[ "$rest" =~ $RE_TOOLS_DOT ]]; do
    name="${BASH_REMATCH[2]}"
    rest="${rest#*"${BASH_REMATCH[0]}"}"
    [[ "$name" == mcp__* ]] || continue        # exec_command, web__run, …
    [[ "$rest" =~ ^[[:space:]]*\( ]] || { printf '%s' "$name"; return 0; }
    op="${name#mcp__}"; op="${op#*__}"         # mcp__codex_apps__gmail_x → gmail_x
    [[ "$op" =~ $RE_READ_TOKEN ]] && ! [[ "$op" =~ $RE_WRITE_TOKEN ]] && continue
    printf '%s' "$name"; return 0
  done
  return 1
}

# ─── one connector, two spellings ──────────────────────────────────────────
# same_permit_tool <wire name> <canonical permit name> → 0 when the two name
# the SAME connector call.
#
# MEASURED 2026-09-13/14 on the ChatGPT desktop app. The JavaScript wrapper
# inside `exec` is `tools.mcp__codex_apps__gmail_create_draft` — one `_` — and
# the PreToolUse envelope for that same call carries
# `mcp__codex_apps__gmail__create_draft` — two. The desktop tool catalogue in
# the rollout lists `mcp__codex_apps__gmail_send_email` with one. So both
# spellings are in circulation on one machine on one day.
#
# The DENY side never depended on this: the verb rule below matches the
# operation segment either way, and both spellings deny. What broke is the
# other direction — the permit keys are exact strings, so an approved,
# reviewed, operator-signed send arriving under the twin spelling is refused
# with no way to tell why. A control that fails shut on an approved act still
# has to be repaired, or the next repair is somebody widening the verb list.
#
# Only the `__`/`_` difference INSIDE the operation segment is absorbed. The
# `mcp__<server>__` prefix must match exactly, so another connector, another
# verb, a hyphen or a missing separator all stay different tools.
same_permit_tool() {
  local raw="$1" canon="$2" rest raw_ns raw_op canon_ns canon_op
  [[ "$raw" == "$canon" ]] && return 0
  [[ "$raw" == *__*__* ]] || return 1
  rest="${raw#*__}";   raw_ns="${raw%%__*}__${rest%%__*}__";     raw_op="${raw#"$raw_ns"}"
  rest="${canon#*__}"; canon_ns="${canon%%__*}__${rest%%__*}__"; canon_op="${canon#"$canon_ns"}"
  [[ -n "$raw_op" && "$raw_ns" == "$canon_ns" && "${raw_op//__/_}" == "${canon_op//__/_}" ]]
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
    deny "$safe_name" "inside $operation only a written-out read is allowed — tools.<read tool>(…) — and this code has something else: $embedded. Do not reach a connector any other way and do not send from here; an approved send must be a direct connector call that a one-shot permit can bind / exec の中で許されるのは直書きの読み取り呼び出しだけ。外向きは exec の中で行わず、承認済みなら直接ツールで許可票を使え"
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
permit_canonical=''
if same_permit_tool "$safe_name" "$GMAIL_PERMITTED_TOOL"; then
  permit_canonical="$GMAIL_PERMITTED_TOOL"
elif same_permit_tool "$safe_name" "$SLACK_PERMITTED_TOOL"; then
  permit_canonical="$SLACK_PERMITTED_TOOL"
fi
if [[ -n "$permit_canonical" ]]; then
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
# operation. This branch is still scoped to the exact wire namespace
# `mcp__codex_apps__slack__`, so a one-underscore Slack name does NOT reach it
# and falls through to the verb rule below — which catches every measured
# Slack WRITE that carries a verb, but not the verbless ones (add_reaction,
# join_conversation, …). Recorded as a known gap rather than widened here,
# because widening it would also change which one-underscore Slack READS stay
# available, and no such call has been measured. [未検証]
# The approved Slack SEND is unaffected: it is handled above, where
# `same_permit_tool` accepts either spelling.
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
