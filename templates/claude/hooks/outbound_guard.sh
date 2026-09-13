#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# outbound_guard.sh (Claude Code) — the PreToolUse hook that stops a send.
#
# WHY THIS FILE EXISTS. This is the Claude Code half of the pair whose Codex
# half is templates/codex/hooks/outbound_guard.sh. The Codex half was written
# after a measured incident: with "outward = ask first" in the instructions
# file and the strictest sandbox set, the agent called gmail's send tool
# unasked and, when the approval policy refused it, CREATED A DRAFT to the real
# customer instead. A blocked path is not a closed door — the model finds the
# neighbouring verb, because nothing in the machine says no.
#
# Claude Code had no such control. Its unattended lane is protected only by the
# CLI's own default (an MCP tool that is not named in `--allowedTools` is
# refused), and its interactive lane only by the permission prompt — both are
# defaults, not designed controls, and a future cron line that writes
# `--allowedTools "mcp__…__*"` opens the door again in silence. So the "no"
# moves into the machine here too.
#
# ─── the wire format, from the published specification ─────────────────────
# https://code.claude.com/docs/en/hooks
#
# stdin  — one JSON object. The documented PreToolUse example is:
#            {"session_id":"abc123","prompt_id":"…","transcript_path":"…",
#             "cwd":"/home/user/my-project","scratchpad_dir":"…",
#             "permission_mode":"default","hook_event_name":"PreToolUse",
#             "tool_name":"Bash","tool_input":{…},"tool_use_id":"toolu_01ABC…"}
#          `tool_name` is "Name of the tool being called"; `tool_input` is
#          "The tool's arguments".
#
# stdout — the documented deny is exactly:
#            {"hookSpecificOutput":{"hookEventName":"PreToolUse",
#             "permissionDecision":"deny",
#             "permissionDecisionReason":"Destructive command blocked by hook"}}
#          `permissionDecision` takes "allow" (approve the tool call), "deny"
#          (block it) or "ask" (request user confirmation).
#
# ⚠️ WE NEVER PRINT "allow", AND THAT IS THE ONE PLACE THIS FILE DIFFERS FROM
# ITS CODEX TWIN BY CHOICE RATHER THAN BY DIALECT. Codex has no way to say yes,
# so its pass path prints `{}` because that is all it can do. Claude Code DOES
# accept "allow" — and "allow" here is an ELEVATION: it approves the call and
# skips the permission prompt that is currently the only thing guarding the
# interactive lane. A guard that answered "allow" on every read would hand the
# agent a standing pass to every connector in the session. So the pass path
# prints the same empty document. The docs describe the no-decision case like
# this: "Exit code 0 with no output means the hook has no decision to report,
# so the tool call continues through the normal permission flow. The hook can
# deny the call, but staying silent doesn't approve it."
#
# `{}` is that same silence written as valid JSON — an object carrying no
# `hookSpecificOutput`, so there is no decision to report. It is spelled as a
# document rather than as literally nothing so that this file and its Codex
# twin have ONE pass path, and so the tests can parse every branch's output.
# The difference is not load-bearing: rejected hook output is itself
# non-blocking, which is the same outcome as the pass. The permit path below
# prints `{}` too — a permit LIFTS THE DENY, it does not grant permission; the
# CLI's own permission layer still applies underneath.
#
# ⚠️ "ask" IS DELIBERATELY UNUSED. It looks like the friendlier answer and it
# is the wrong one for this loop: an unattended cron run has nobody to ask, so
# "ask" there is a hang, not a question. Deny plus a one-shot permit is the
# same shape on both lanes.
#
# ⚠️ THE HOST FAILS OPEN, exactly as Codex's does. From the same page: "When
# the script path doesn't exist or isn't executable, the shell exits with a
# code like 127 and you see the same notice … For most hook events, the action
# proceeds." Unparseable stdout is the same non-blocking error. A broken guard
# and an absent guard look identical from outside — which is why
# tests/test_o_claude_guard.sh runs this file against synthetic payloads and
# validates its stdout, rather than reading it.
#
# ⚠️ EXIT CODE. We always exit 0 and let the JSON carry the decision, which is
# the shape the documented example uses. Exit 2 also blocks ("On events that
# can block, exit 2 blocks whether or not you print JSON") but takes its reason
# from stderr, so a deny raised that way would lose the queue instruction that
# is the whole point of the reason string.
#
# ⚠️ A LIMITATION INHERITED FROM THE TWIN, STATED OUT LOUD. The classifier
# reads `tool_name` with a regex over the raw payload, so it takes the FIRST
# occurrence. Every payload observed and every published example puts
# `tool_name` ahead of `tool_input`, but JSON object order is the producer's
# choice — if a host ever serialized them the other way, an argument value
# containing the text `"tool_name":"Bash"` would shadow the real one. The SEND
# path is not exposed to this: outbound_permit.py parses the whole envelope
# with a strict JSON parser before it will claim anything. Only the classifier
# is, and it is the same property the Codex twin ships with. Fixing it costs a
# python3 start on every tool call; raise it with the operator before paying
# that, rather than changing it here by reflex.
#
# ─── how a name is judged ──────────────────────────────────────────────────
# Claude Code's tool names carry THREE segments: mcp__<server>__<operation>,
# where <server> is itself compound (`claude_ai_Google_Calendar`). Matching the
# operation segment alone — what the Codex twin does — is not enough here,
# because one server's `update_page` is outward speech into a workspace shared
# with a customer while another's `update_file` is a file edit. So the rules
# below are ANCHORED, FULL-NAME regexes, and only the last-resort fallback
# looks at the operation segment.
#
# ORDER IS THE POLICY, and tests assert it:
#   1. no tool_name                  → deny  (fail closed on a moved schema)
#   2. not an mcp__ tool             → pass  (Bash is never matched: `git push`
#                                             and `rm` are reversible-by-history
#                                             and this loop runs them unattended)
#   3. an exact permit target        → claim a one-shot permit, else deny
#   4. the explicit outward list     → deny
#   5. the Slack namespaces          → closed read allowlist, else deny
#   6. reversible-by-history git     → pass
#   7. a read (get/list/search/read) → pass
#   8. the outward-verb fallback     → deny
#   9. anything else                 → pass
# Step 7 must come before step 8 and after step 4: `notion-get-comments` is a
# READ whose name contains an outward verb, and `trash_message` is outward
# while `untrash_message` is the recovery from it.
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

# ─── 3. the only two calls a permit can open ───────────────────────────────
# Deliberately the same two acts as the Codex twin: one email, one channel
# message. NOT `Gmail reply`, NOT `slack_reply_to_thread` — a threaded reply
# has no permit path today and must go through the queue. Gmail's send_message
# can thread by itself (`replyThreadId`), so the email side loses nothing.
GMAIL_PERMITTED_TOOL='mcp__claude_ai_Gmail__send_message'
SLACK_PERMITTED_TOOL='mcp__slack__slack_post_message'

# ─── 4. outward by name. Each entry is anchored against the WHOLE name. ────
# The operator's ruling, item by item:
#   Gmail      — speech to a third party, plus the two irreversible mailbox
#                acts (trash, spam). `untrash_*` / `unmark_*_spam` are the
#                recoveries and stay open.
#   Slack      — the send pair, named here as well as caught by step 5.
#   Notion     — the workspace is shared with customers; pages, comments and
#                session messages are outward speech.
#   Calendar   — an invitation and an RSVP are speech to the other attendees.
#   Drive      — sharing publishes; trashing is not reversible from here.
#   GitHub     — issue and review COMMENTS are speech. The code-moving half of
#                GitHub is deliberately NOT here; see step 6. Creating or
#                forking a REPOSITORY is not code-moving: a repository is a
#                publication, and this guard denies the delete that would undo
#                it, so allowing the create would satisfy the operator's
#                reversibility test in one direction only.
#   Vercel     — a deploy is production, a purchase spends money, a pause takes
#                production down.
OUTBOUND_EXACT='^mcp__claude_ai_Gmail__(send_message|reply|forward|create_draft|update_draft)$
^mcp__claude_ai_Gmail__(trash_message|trash_thread|mark_message_spam|mark_thread_spam)$
^mcp__slack__slack_(post_message|reply_to_thread)$
^mcp__claude_ai_Notion__notion-(create-pages|update-page|create-comment|send-message-to-session)$
^mcp__claude_ai_Google_Calendar__(create_event|update_event|delete_event|respond_to_event)$
^mcp__claude_ai_Google_Drive__(share_file|trash_file)$
^mcp__github__(issue_write|add_issue_comment|pull_request_review_write)$
^mcp__plugin_vercel_vercel__(deploy_to_vercel|buy_[a-z_]+|pause_project)$'

# ─── 4b. NEIGHBOURS — not in the operator's list, added on the incident's
# lesson: the model that is refused one verb reaches for the one beside it.
# Every entry here is the same CLASS as something above (outward speech, or an
# irreversible act). Prune this block, not the one above, if it bites.
#
# The Notion rows are here because running this guard over the whole connector
# roster found the incident's own shape: `notion-create-pages` was denied while
# `notion-duplicate-page` and `notion-move-pages` — which put content in the
# same shared workspace — went straight through. A list that denies one verb
# and leaves its synonym open is not a control.
OUTBOUND_NEIGHBOURS='^mcp__github__(add_reply_to_pull_request_comment|add_comment_to_pending_review|sub_issue_write|request_copilot_review)$
^mcp__github__(create_repository|delete_repository|fork_repository)$
^mcp__plugin_vercel_vercel__(unpause_project|create_git_project|update_project_deployment_protection)$
^mcp__plugin_vercel_vercel__(reply_to_toolbar_thread|edit_toolbar_message|add_toolbar_reaction|change_toolbar_thread_resolve_status)$
^mcp__claude_ai_Notion__notion-(duplicate-page|move-pages|create-attachment)$
^mcp__claude_ai_Notion__notion-(create-database|create-view|create-folder|update-view|update-folder|update-data-source)$
^mcp__claude_ai_Notion__notion-(spawn-session|stop-session)$'

# ─── 5. Slack fails closed, in both of its namespaces ──────────────────────
# Same reasoning as the Codex twin: the Slack connector's write operations are
# not all spelled with an outward verb (add_reaction, join, upload …), and a
# reaction in a customer's channel is still something the customer sees. So the
# READ side is a closed enumerated list and everything else in the namespace is
# denied — including operations that do not exist yet. `mcp__claude_ai_Slack__`
# currently exposes only its authentication pair; it is listed for the day it
# exposes more.
SLACK_READ_EXACT='^mcp__slack__slack_(get_channel_history|get_thread_replies|get_user_profile|get_users|list_channels)$
^mcp__claude_ai_Slack__(authenticate|complete_authentication)$'
SLACK_NAMESPACES='^mcp__(slack|claude_ai_Slack)__'

# ─── 6. reversible by history — the operator's standing ruling ─────────────
# "The test is not whether it is outward, it is whether it can be undone."
# git keeps history and revert exists, so the code-moving operations run
# unattended. Their names are here rather than left to fall through, because
# `delete_file` would otherwise be swept up by the fallback's `delete`.
GIT_REVERSIBLE='^mcp__github__(push_files|create_or_update_file|delete_file|create_branch)$
^mcp__github__(create_pull_request|merge_pull_request|update_pull_request|update_pull_request_branch)$'

# ─── 7. a read, by token, anywhere in the operation segment ────────────────
# Written as tokens rather than prefixes because the three connector families
# spell reads three ways: `search_threads`, `notion-get-comments`,
# `slack_list_channels`. A token match keeps `notion-get-comments` — a read
# whose name contains `comment` — out of the fallback below.
READ_TOKENS='(^|[_-])(get|list|search|read|fetch|query|download)([_-]|$)'

# ─── 8. the last resort, on the operation segment only ─────────────────────
# Matched against everything after the final `__`, so a server merely NAMED
# after a verb (`mcp__postgres__query`) is not swept up by `post`.
# `delete` is here on the reversibility test, not the outwardness one.
OUTBOUND_VERBS='send|post|publish|share|invite|forward|reply|comment|deploy|purchase|buy_|create_draft|update_draft|delete'

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

# The pass. `{}` is a valid, decision-free document — NOT `permissionDecision:
# "allow"`, which would bypass the permission prompt. See the header.
allow() { log "allow ${1:-}"; printf '{}'; exit 0; }

deny() {  # deny <tool_name> <why>
  log "DENY $1 — $2"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "outbound guard: $1 is an outward call. Do not send, and do not reach for a neighbouring tool. Append the message to approval_queue.md and wait for the operator to approve it. / 外向き送信は approval_queue.md へ積んで殿の承認を待つ。別のツールへ迂回するな。($2) session_id=${SAFE_SESSION:-unknown} — an approved exact send is opened with .claude/hooks/outbound_permit.py issue --cli claude (see docs/outbound-permits.md)."
  exit 0
}

# ⚠️ READ fd 0 DIRECTLY. NOT `$(</dev/stdin)`, WHICH READS NOTHING HERE.
# MEASURED 2026-09-13 on this host: Claude Code hands the hook its payload on a
# SOCKET, not a pipe —
#     fd0 -> socket:[95691964]   (readlink /proc/self/fd/0, from inside the hook)
# `$(</dev/stdin)` does not read fd 0; it OPENS THE PATH /dev/stdin, which is a
# symlink to /proc/self/fd/0, and a socket cannot be opened by path. The
# redirect therefore fails, the substitution yields the empty string, and —
# because nothing here is fatal — the guard sails on with no payload. It then
# cannot find tool_name and denies everything as "unknown-tool": loud, and
# useless, and the fix is one word.
#
# This is invisible to a test that pipes stdin, because a PIPE *can* be
# reopened through /proc. The socket case is what tests/test_o_claude_guard.sh
# reproduces with a real socketpair, and it is the only assertion in this
# repository that would have caught it.
payload="$(cat)"

# tool_name is an identifier. Matching its closing quote as well as its safe
# character set prevents partial extraction from becoming JSON interpolation.
safe_name=''
if [[ "$payload" =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9_.:/-]+)\" ]]; then
  safe_name="${BASH_REMATCH[1]}"
fi

# The session id travels in the deny reason so the operator knows which value
# to bind a permit to; `issue` refuses without it. Same safe charset, same
# reason. transcript_path is deliberately NOT quoted back — it spells out the
# project slug.
SAFE_SESSION=''
if [[ "$payload" =~ \"session_id\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9_.:/-]+)\" ]]; then
  SAFE_SESSION="${BASH_REMATCH[1]}"
fi

# ─── 1. no tool_name means the schema moved or the payload never arrived ───
# Deny: the guard being loudly wrong is recoverable; the guard being quietly
# absent is the failure this whole file exists to prevent.
if [[ -z "$safe_name" ]]; then
  deny "unknown-tool" "the hook could not read tool_name from its input"
fi

# ─── 2. connector and MCP calls only ───────────────────────────────────────
if [[ "$safe_name" != mcp__* ]]; then
  allow "$safe_name"
fi

# ─── 3. the exact permit targets ───────────────────────────────────────────
# The helper strictly parses the entire envelope and claims the matching record
# by atomic rename before this hook emits the pass document. Any failure is a
# deny; stderr is hidden so message contents never enter the hook response.
if [[ "$safe_name" == "$GMAIL_PERMITTED_TOOL" || "$safe_name" == "$SLACK_PERMITTED_TOOL" ]]; then
  if [[ -n "$PROJECT_ROOT" && -f "$PERMIT_HELPER" ]] && command -v python3 >/dev/null 2>&1; then
    if printf '%s' "$payload" | python3 "$PERMIT_HELPER" claim --cli claude --project-root "$PROJECT_ROOT" >/dev/null 2>&1; then
      allow "$safe_name (one-shot permit claimed)"
    fi
  fi
  deny "$safe_name" "no valid one-shot permit matched the complete send arguments, project, session, and expiry"
fi

# ─── 4. the explicit outward list, and its neighbours ──────────────────────
while IFS= read -r rule; do
  [[ -n "$rule" ]] || continue
  if [[ "$safe_name" =~ $rule ]]; then
    deny "$safe_name" "the tool is on the outward list"
  fi
done <<< "$OUTBOUND_EXACT"

while IFS= read -r rule; do
  [[ -n "$rule" ]] || continue
  if [[ "$safe_name" =~ $rule ]]; then
    deny "$safe_name" "the tool is of the same class as one on the outward list"
  fi
done <<< "$OUTBOUND_NEIGHBOURS"

# ─── 5. the Slack namespaces, fail closed ──────────────────────────────────
if [[ "$safe_name" =~ $SLACK_NAMESPACES ]]; then
  while IFS= read -r rule; do
    [[ -n "$rule" ]] || continue
    if [[ "$safe_name" =~ $rule ]]; then
      allow "$safe_name"
    fi
  done <<< "$SLACK_READ_EXACT"
  deny "$safe_name" "the Slack namespace is closed: only the enumerated read operations pass"
fi

# ─── 6. reversible by history ──────────────────────────────────────────────
while IFS= read -r rule; do
  [[ -n "$rule" ]] || continue
  if [[ "$safe_name" =~ $rule ]]; then
    allow "$safe_name (reversible by history)"
  fi
done <<< "$GIT_REVERSIBLE"

operation="${safe_name##*__}"

# ─── 7. reading is not sending ─────────────────────────────────────────────
# A guard that also blocks the inbound sweep gets switched off, and a guard
# that is switched off protects nothing.
if [[ "$operation" =~ $READ_TOKENS ]]; then
  allow "$safe_name"
fi

# ─── 8. the fallback ───────────────────────────────────────────────────────
if [[ "$operation" =~ ($OUTBOUND_VERBS) ]]; then
  deny "$safe_name" "operation '$operation' matches the outbound verb list"
fi

# ─── 9. ────────────────────────────────────────────────────────────────────
allow "$safe_name"
