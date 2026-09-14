#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# O. the Claude Code outward guard — the second half of the pair whose Codex
#    half group M asserts.
#
# THE FAILURE THIS GROUP EXISTS FOR IS SILENCE, exactly as in M9, and the
# published specification says so in as many words: "When the script path
# doesn't exist or isn't executable, the shell exits with a code like 127 …
# For most hook events, the action proceeds." A hook that is missing, or that
# prints something unparseable, is indistinguishable from a hook that decided
# to allow. So these assertions RUN the script against synthetic payloads and
# read its stdout; none of them read the source.
#
#   O1  the pair ships, compiles, and is executable
#   O2  the wire format is the documented one — and never says "allow"
#   O3  the outward list denies, verb by verb and connector by connector
#   O4  reading is not sending, including reads NAMED after an outward verb
#   O5  anchored, not substring: trash denies while untrash passes
#   O6  reversible-by-history git passes while GitHub speech denies
#   O7  both Slack namespaces fail closed
#   O8  the shell and the built-ins are never matched
#   O9  an unreadable payload fails CLOSED, and every branch prints valid JSON
#   O10 the one-shot permit: exact binding, single claim, per-CLI isolation
#   O11 the settings example registers the hook the way the docs specify
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "O. the outward guard (Claude Code)"

# ─── O1. the pair ships ────────────────────────────────────────────────────
O_GUARD_TEMPLATE="$REPO_ROOT/templates/claude/hooks/outbound_guard.sh"
O_PERMIT_TEMPLATE="$REPO_ROOT/templates/hooks/outbound_permit.py"
assert_file "O1: the Claude outward guard ships in the kit" "$O_GUARD_TEMPLATE"
assert_ok "O1: …and is syntactically valid bash" bash -n "$O_GUARD_TEMPLATE"
assert_ok "O1: …and is executable in the tree" test -x "$O_GUARD_TEMPLATE"
assert_file "O1: the permit helper is SHARED, not a second copy" "$O_PERMIT_TEMPLATE"
assert_absent "O1: …so no per-CLI duplicate survives under templates/codex/" \
  "$REPO_ROOT/templates/codex/hooks/outbound_permit.py"
assert_absent "O1: …nor under templates/claude/" \
  "$REPO_ROOT/templates/claude/hooks/outbound_permit.py"
assert_ok "O1: …and its Python is syntactically valid" \
  env PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile "$O_PERMIT_TEMPLATE"

# Run the hook from the same .claude/hooks layout a real project has. Its
# project binding is derived from that location, never from caller input.
O_ROOT="$TEST_TMP/o_claude_project"
mkdir -p "$O_ROOT/.claude/hooks"
cp "$O_GUARD_TEMPLATE" "$O_PERMIT_TEMPLATE" "$O_ROOT/.claude/hooks/"
chmod +x "$O_ROOT/.claude/hooks/outbound_guard.sh" "$O_ROOT/.claude/hooks/outbound_permit.py"
O_GUARD="$O_ROOT/.claude/hooks/outbound_guard.sh"
O_PERMIT="$O_ROOT/.claude/hooks/outbound_permit.py"

# o_guard PAYLOAD → the hook's stdout for that PreToolUse input
o_guard() { printf '%s' "$1" | bash "$O_GUARD" 2>/dev/null; }
o_output_decision() {  # hook stdout → allow | deny | INVALID
  O_G_OUT="$1" O_G_PY='
import json, os, sys
try: d = json.loads(os.environ["O_G_OUT"])
except Exception: print("INVALID"); sys.exit()
h = d.get("hookSpecificOutput") or {}
print(h.get("permissionDecision") or ("pass" if not h else "INVALID"))
' python3 -c 'import os;exec(os.environ["O_G_PY"])'
}
# o_decide TOOL → pass | deny | INVALID, for a bare call with empty arguments
o_decide() {
  o_output_decision "$(o_guard "{\"session_id\":\"s-test\",\"cwd\":\"$O_ROOT\",\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"$1\",\"tool_input\":{}}")"
}

# ─── O2. the wire format, against the published specification ──────────────
# https://code.claude.com/docs/en/hooks — the documented deny is
#   {"hookSpecificOutput":{"hookEventName":"PreToolUse",
#    "permissionDecision":"deny","permissionDecisionReason":"…"}}
O_DENY_OUT="$(o_guard "{\"session_id\":\"s-wire\",\"cwd\":\"$O_ROOT\",\"tool_name\":\"mcp__claude_ai_Google_Drive__share_file\",\"tool_input\":{}}")"
assert_grep_str "O2: the deny names the event, as the schema requires" \
  '"hookEventName":"PreToolUse"' "$O_DENY_OUT"
assert_grep_str "O2: …and carries permissionDecision deny" '"permissionDecision":"deny"' "$O_DENY_OUT"
O_DENY_REASON="$(O_G_OUT="$O_DENY_OUT" python3 -c 'import json,os;print(json.loads(os.environ["O_G_OUT"])["hookSpecificOutput"]["permissionDecisionReason"],end="")')"
assert_nonempty_str "O2: the deny carries a reason (it is what the user is shown)" "$O_DENY_REASON"
assert_grep_str "O2: …and the reason names where the message goes instead" \
  "approval_queue.md" "$O_DENY_REASON"
assert_grep_str "O2: …and tells the agent not to reach for a neighbour" \
  "neighbouring tool" "$O_DENY_REASON"
# The operator cannot issue a permit without the session id, and the hook is
# the only place it is on screen at the moment of the refusal.
assert_grep_str "O2: …and hands back the session id a permit must bind to" \
  "session_id=s-wire" "$O_DENY_REASON"
assert_no_grep_str "O2: …while NOT quoting transcript_path back (it spells the project)" \
  "transcript_path" "$O_DENY_REASON"

# THE PASS IS THE EMPTY DOCUMENT, NOT "allow". Claude Code accepts
# permissionDecision "allow" — and "allow" APPROVES the call, skipping the
# permission prompt that is the interactive lane's only other guard. A guard
# that answered "allow" on reads would hand out a standing pass to every
# connector in the session. The docs' no-decision case is what we want:
# "Exit code 0 with no output means the hook has no decision to report, so the
# tool call continues through the normal permission flow. The hook can deny the
# call, but staying silent doesn't approve it." `{}` is that silence written as
# valid JSON, so every branch stays parseable by these assertions.
assert_eq "O2: the pass is the empty document" "{}" \
  "$(o_guard '{"tool_name":"Bash","tool_input":{"command":"ls"}}')"
assert_eq "O2: …and the hook exits 0 so the JSON carries the decision" "0" \
  "$(printf '{"tool_name":"mcp__claude_ai_Gmail__send_message"}' | bash "$O_GUARD" >/dev/null 2>&1; echo $?)"

# ─── O3. the outward list ──────────────────────────────────────────────────
for o_gmail in send_message reply forward create_draft update_draft; do
  assert_eq "O3: Gmail $o_gmail is denied" "deny" "$(o_decide "mcp__claude_ai_Gmail__$o_gmail")"
done
for o_notion in create-pages update-page create-comment send-message-to-session; do
  assert_eq "O3: Notion $o_notion is denied" "deny" "$(o_decide "mcp__claude_ai_Notion__notion-$o_notion")"
done
# the neighbours the roster sweep found: one verb denied and its synonym open
# is not a control.
for o_notion_near in duplicate-page move-pages create-database create-view \
                     create-folder create-attachment update-view update-folder \
                     update-data-source spawn-session stop-session; do
  assert_eq "O3: Notion $o_notion_near is denied as the same class" "deny" \
    "$(o_decide "mcp__claude_ai_Notion__notion-$o_notion_near")"
done
# Found by an independent adversarial review of this guard (2026-09-13), by
# sweeping a WIDER roster than the author's: both slipped through while
# `notion-create-attachment`, which is the same act, was denied. An enumerated
# blocklist is structurally weak against the entry nobody thought to list —
# which is the argument for sweeping the whole roster rather than re-reading
# the list.
assert_eq "O3: Notion create-file-upload is denied (same class as create-attachment)" "deny" \
  "$(o_decide 'mcp__claude_ai_Notion__notion-create-file-upload')"
assert_eq "O3: Notion convert-page-to-skill is denied (it takes a page out of the workspace)" "deny" \
  "$(o_decide 'mcp__claude_ai_Notion__notion-convert-page-to-skill')"
for o_cal in create_event update_event delete_event respond_to_event; do
  assert_eq "O3: Calendar $o_cal is denied" "deny" "$(o_decide "mcp__claude_ai_Google_Calendar__$o_cal")"
done
for o_drive in share_file trash_file; do
  assert_eq "O3: Drive $o_drive is denied" "deny" "$(o_decide "mcp__claude_ai_Google_Drive__$o_drive")"
done
for o_vercel in deploy_to_vercel buy_pro buy_domain buy_credits buy_addon pause_project \
                unpause_project create_git_project update_project_deployment_protection \
                reply_to_toolbar_thread edit_toolbar_message add_toolbar_reaction \
                change_toolbar_thread_resolve_status; do
  assert_eq "O3: Vercel $o_vercel is denied" "deny" "$(o_decide "mcp__plugin_vercel_vercel__$o_vercel")"
done
# an unlisted connector that says what it does still gets caught by the fallback
assert_eq "O3: an unknown connector's publish operation is denied" "deny" \
  "$(o_decide 'mcp__example__publish_page')"
assert_eq "O3: …and an unknown connector's send operation" "deny" \
  "$(o_decide 'mcp__some_new_vendor__send_invoice')"

# ONE UNDERSCORE AFTER `mcp` IS STILL A CONNECTOR (issue #21).
# The prefix gate asked for `mcp__` and passed everything else, so a name whose
# first separator is a single underscore never reached a rule at all — the
# header said "not an mcp__ tool → pass", meaning Bash and the built-ins, and a
# connector spelled `mcp_…` is neither. The gate now asks for `mcp`.
# NOTE the asymmetry with the Codex twin: the anchored `^mcp__…` lists (steps
# 4-6) still miss a one-underscore name, so what closes here is exactly the
# verb-carrying subset that step 8 catches. Verbless writes under that spelling
# remain open, as they were before. [未検証 — no such call has been measured]
assert_eq "O3: a one-underscore connector send is denied (issue #21)" "deny" \
  "$(o_decide 'mcp_claude_ai_Gmail__send_message')"
assert_eq "O3: …and one whose namespace carries no separator at all" "deny" \
  "$(o_decide 'mcpslack__slack_post_message')"
assert_eq "O3: …while the one-underscore READ stays available" "pass" \
  "$(o_decide 'mcp_claude_ai_Gmail__search_threads')"

# ─── O4. reading is not sending ────────────────────────────────────────────
# A guard that also blocks the inbound sweep gets switched off, and a guard
# that is switched off protects nothing.
for o_read in mcp__claude_ai_Gmail__search_threads mcp__claude_ai_Gmail__get_thread \
              mcp__claude_ai_Gmail__get_message mcp__claude_ai_Gmail__list_labels \
              mcp__claude_ai_Google_Calendar__list_events \
              mcp__claude_ai_Google_Calendar__search_events \
              mcp__claude_ai_Google_Drive__search_files \
              mcp__claude_ai_Google_Drive__read_file_content \
              mcp__claude_ai_Google_Drive__download_file_content \
              mcp__claude_ai_Google_Drive__get_file_permissions \
              mcp__claude_ai_Notion__notion-search mcp__claude_ai_Notion__notion-fetch \
              mcp__claude_ai_Notion__notion-query-data-sources \
              mcp__github__get_file_contents mcp__github__list_commits \
              mcp__github__search_code mcp__github__pull_request_read \
              mcp__github__issue_read; do
  assert_eq "O4: $o_read remains available for inbound reads" "pass" "$(o_decide "$o_read")"
done
# THE REGRESSION THE ORDER EXISTS FOR: reads whose NAMES contain an outward
# verb. Put the fallback before the read check and every one of these breaks.
assert_eq "O4: notion-get-comments is a READ, though its name says comment" "pass" \
  "$(o_decide 'mcp__claude_ai_Notion__notion-get-comments')"
assert_eq "O4: …and list_drafts, though its name says draft" "pass" \
  "$(o_decide 'mcp__claude_ai_Gmail__list_drafts')"
assert_eq "O4: …and get_draft" "pass" "$(o_decide 'mcp__claude_ai_Gmail__get_draft')"

# ─── O5. anchored, not substring ───────────────────────────────────────────
# The destructive act is denied; the RECOVERY from it stays open. A substring
# rule over `trash` or `spam` would close both, which would leave an operator
# unable to undo the very thing the guard is here to prevent.
assert_eq "O5: trash_message is denied" "deny" "$(o_decide 'mcp__claude_ai_Gmail__trash_message')"
assert_eq "O5: …while untrash_message passes" "pass" "$(o_decide 'mcp__claude_ai_Gmail__untrash_message')"
assert_eq "O5: trash_thread is denied" "deny" "$(o_decide 'mcp__claude_ai_Gmail__trash_thread')"
assert_eq "O5: …while untrash_thread passes" "pass" "$(o_decide 'mcp__claude_ai_Gmail__untrash_thread')"
assert_eq "O5: mark_message_spam is denied" "deny" "$(o_decide 'mcp__claude_ai_Gmail__mark_message_spam')"
assert_eq "O5: …while unmark_message_spam passes" "pass" "$(o_decide 'mcp__claude_ai_Gmail__unmark_message_spam')"
assert_eq "O5: mark_thread_spam is denied" "deny" "$(o_decide 'mcp__claude_ai_Gmail__mark_thread_spam')"
assert_eq "O5: …while unmark_thread_spam passes" "pass" "$(o_decide 'mcp__claude_ai_Gmail__unmark_thread_spam')"

# ─── O6. reversible by history ─────────────────────────────────────────────
# The operator's standing ruling: "the test is not whether it is outward, it is
# whether it can be undone." git keeps history and revert exists, so the
# code-moving half of GitHub runs unattended — while SPEECH on GitHub does not.
for o_git in push_files create_or_update_file delete_file create_branch \
             create_pull_request merge_pull_request update_pull_request \
             update_pull_request_branch; do
  assert_eq "O6: github $o_git passes (reversible by history)" "pass" \
    "$(o_decide "mcp__github__$o_git")"
done
for o_speech in issue_write add_issue_comment pull_request_review_write \
                add_reply_to_pull_request_comment add_comment_to_pending_review \
                sub_issue_write request_copilot_review; do
  assert_eq "O6: github $o_speech is denied (it is speech, not code)" "deny" \
    "$(o_decide "mcp__github__$o_speech")"
done
assert_eq "O6: github delete_repository is denied (history is what is lost)" "deny" \
  "$(o_decide 'mcp__github__delete_repository')"
# A repository is a publication, and this guard denies the delete that would
# undo it — so allowing the create would pass the reversibility test in one
# direction only.
assert_eq "O6: …and create_repository too: publishing, with no undo left open" "deny" \
  "$(o_decide 'mcp__github__create_repository')"
assert_eq "O6: …and fork_repository, which publishes someone else's code" "deny" \
  "$(o_decide 'mcp__github__fork_repository')"
# the pair that proves the ordering: both contain `delete`, and they differ.
assert_eq "O6: delete_file passes while delete_event does not — same verb, different act" \
  "pass|deny" "$(o_decide 'mcp__github__delete_file')|$(o_decide 'mcp__claude_ai_Google_Calendar__delete_event')"

# ─── O7. both Slack namespaces fail closed ─────────────────────────────────
for o_slack_read in slack_get_channel_history slack_get_thread_replies \
                    slack_get_user_profile slack_get_users slack_list_channels; do
  assert_eq "O7: Slack $o_slack_read remains available" "pass" "$(o_decide "mcp__slack__$o_slack_read")"
done
assert_eq "O7: slack_post_message is denied without a permit" "deny" \
  "$(o_decide 'mcp__slack__slack_post_message')"
assert_eq "O7: slack_reply_to_thread is denied and has NO permit path" "deny" \
  "$(o_decide 'mcp__slack__slack_reply_to_thread')"
# a reaction in a customer's channel is still something the customer sees
assert_eq "O7: slack_add_reaction is denied by the closed namespace" "deny" \
  "$(o_decide 'mcp__slack__slack_add_reaction')"
assert_eq "O7: an operation that does not exist yet fails closed" "deny" \
  "$(o_decide 'mcp__slack__slack_future_operation')"
assert_eq "O7: …in the second Slack namespace too" "deny" \
  "$(o_decide 'mcp__claude_ai_Slack__post_anything')"
assert_eq "O7: …whose authentication pair is the only thing open there" "pass" \
  "$(o_decide 'mcp__claude_ai_Slack__authenticate')"
assert_eq "O7: …both halves of it" "pass" \
  "$(o_decide 'mcp__claude_ai_Slack__complete_authentication')"

# ─── O8. the shell and the built-ins are never matched ─────────────────────
# ON PURPOSE: `git push` and `rm` are reversible-by-history operations this
# loop deliberately leaves unattended, and a substring rule over command text
# would eat them.
assert_eq "O8: the shell is never matched, whatever the command says" "pass" \
  "$(o_output_decision "$(o_guard '{"tool_name":"Bash","tool_input":{"command":"git push && rm -rf ./tmp && echo post && mail -s send x"}}')")"
for o_builtin in Read Write Edit WebFetch WebSearch Task Artifact; do
  assert_eq "O8: the built-in $o_builtin is never matched" "pass" "$(o_decide "$o_builtin")"
done
assert_eq "O8: …nor is a connector merely NAMED after a verb (postgres)" "pass" \
  "$(o_decide 'mcp__postgres__query')"

# ─── O9. fail closed on an unreadable payload ──────────────────────────────
# Loudly wrong is recoverable; quietly absent is the failure this file prevents.
assert_eq "O9: an input with no tool_name is denied, not waved through" "deny" \
  "$(o_output_decision "$(o_guard '{"hook_event_name":"PreToolUse"}')")"
assert_eq "O9: …and so is empty input" "deny" "$(o_output_decision "$(o_guard '')")"
assert_eq "O9: …and so is a payload that is not JSON at all" "deny" \
  "$(o_output_decision "$(o_guard 'not json')")"

# every branch must be valid JSON, or the host drops it and the call proceeds
O_BAD=""
for o_p in '{"tool_name":"mcp__claude_ai_Gmail__send_message"}' \
           '{"tool_name":"mcp__claude_ai_Gmail__search_threads"}' \
           '{"tool_name":"mcp__slack__slack_post_message","tool_input":{"channel_id":"C1","text":"x"}}' \
           '{"tool_name":"mcp__github__push_files","tool_input":{}}' \
           '{"tool_name":"Bash","tool_input":{"command":"ls"}}' \
           'not json' \
           '' ; do
  O_G_OUT="$(o_guard "$o_p")" python3 -c 'import json,os;json.loads(os.environ["O_G_OUT"])' 2>/dev/null \
    || O_BAD="${O_BAD}${o_p:-<empty>}"$'\n'
done
assert_empty_str "O9: every branch prints valid JSON (the host drops anything else, in silence)" "$O_BAD"

# THE ELEVATION GUARD. Sweeping every payload above, the string "allow" must
# never appear in any decision this hook emits — it would approve the call and
# skip the permission prompt.
O_ELEVATED=""
for o_p in mcp__claude_ai_Gmail__send_message mcp__claude_ai_Gmail__search_threads \
           mcp__github__push_files mcp__slack__slack_get_users Bash mcp__postgres__query \
           mcp__claude_ai_Notion__notion-get-comments mcp__claude_ai_Google_Drive__share_file; do
  case "$(o_decide "$o_p")" in
    allow) O_ELEVATED="${O_ELEVATED}${o_p}"$'\n' ;;
  esac
done
assert_empty_str "O9: no branch ever answers \"allow\" — that would skip the permission prompt" "$O_ELEVATED"

# ─── O9b. the payload arrives on a SOCKET, not a pipe ──────────────────────
# THE BUG THIS EXISTS FOR WAS FOUND BY RUNNING THE HOOK FOR REAL, AFTER 185
# synthetic assertions had passed. Measured 2026-09-13 from inside the live
# hook: `readlink /proc/self/fd/0` answers `socket:[95691964]`. Claude Code
# hands the payload over a socket.
#
# `$(</dev/stdin)` — the idiom the Codex twin uses, and the one this file was
# written with — does not read fd 0. It OPENS THE PATH /dev/stdin, a symlink to
# /proc/self/fd/0, and a socket cannot be opened by path. So the read yields
# nothing, the guard finds no tool_name, and every single call is denied as
# "unknown-tool". Loud rather than silent, so it fails safe — but the guard is
# useless in exactly the state that looks like it is working hardest.
#
# Every other assertion in this group pipes stdin, and a PIPE can be reopened
# through /proc. That is why they all passed while the real thing was broken.
# This one hands the hook a genuine socketpair, which is the only shape that
# tells the two apart.
O_SOCK_PY="$TEST_TMP/o_socket_probe.py"
cat > "$O_SOCK_PY" <<'PYEOF'
import json, socket, subprocess, sys

guard, payload = sys.argv[1], sys.argv[2]
parent, child = socket.socketpair()
try:
    proc = subprocess.Popen([guard], stdin=child.fileno(),
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    child.close()
    parent.sendall(payload.encode("utf-8"))
    parent.shutdown(socket.SHUT_WR)
    out, _ = proc.communicate(timeout=30)
finally:
    parent.close()
try:
    decision = (json.loads(out or b"{}").get("hookSpecificOutput") or {})
except Exception:
    print("INVALID"); raise SystemExit
print(json.dumps({
    "decision": decision.get("permissionDecision", "pass"),
    "reason": decision.get("permissionDecisionReason", ""),
}))
PYEOF
o_socket() {  # o_socket TOOL → the hook's verdict when stdin is a socket
  python3 "$O_SOCK_PY" "$O_GUARD" \
    "{\"session_id\":\"s-sock\",\"cwd\":\"$O_ROOT\",\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"$1\",\"tool_input\":{}}"
}
O_SOCK_DENY="$(o_socket 'mcp__claude_ai_Gmail__send_message')"
assert_grep_str "O9b: over a socket, an outward call is still denied" \
  '"decision": "deny"' "$O_SOCK_DENY"
# the discriminator: with $(</dev/stdin) the payload is empty, so the reason is
# the fail-closed one and the tool name never appears.
assert_grep_str "O9b: …and the hook actually READ the name (not a blind fail-closed deny)" \
  'mcp__claude_ai_Gmail__send_message' "$O_SOCK_DENY"
assert_no_grep_str "O9b: …so it never says it could not read its input" \
  'could not read tool_name' "$O_SOCK_DENY"
assert_grep_str "O9b: …and the session id survives the socket too" \
  'session_id=s-sock' "$O_SOCK_DENY"
O_SOCK_PASS="$(o_socket 'mcp__claude_ai_Gmail__search_threads')"
assert_grep_str "O9b: over a socket, a read still passes" '"decision": "pass"' "$O_SOCK_PASS"
O_SOCK_SHELL="$(o_socket 'Bash')"
assert_grep_str "O9b: …and the shell is still never matched" '"decision": "pass"' "$O_SOCK_SHELL"

# ─── O10. the one-shot permit ──────────────────────────────────────────────
O_SEND="$O_ROOT/send-input.json"
cat > "$O_SEND" <<'JSON'
{"to":["to@example.invalid"],"cc":["cc@example.invalid"],"subject":"Approved subject","body":"Approved body","htmlBody":null}
JSON
o_review() { python3 "$O_PERMIT" review --cli claude --tool "${2:-gmail}" --tool-input "$1"; }
o_hash() { o_review "$1" "${2:-gmail}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["sha256"])'; }
o_issue() {  # input session [ttl] [tool]
  local input="$1" session="$2" ttl="${3:-300}" tool="${4:-gmail}" hash
  hash="$(o_hash "$input" "$tool")"
  python3 "$O_PERMIT" issue --cli claude --tool "$tool" --tool-input "$input" \
    --expected-sha256 "$hash" --project-root "$O_ROOT" --session-id "$session" \
    --ttl-seconds "$ttl" --approval-ref "TEST-$session" \
    --approval-quote "synthetic explicit approval" --confirm-user-approved >/dev/null
}
o_envelope() {  # input session cwd [tool]
  O_INPUT="$1" O_SESSION="$2" O_CWD="$3" \
  O_TOOL="${4:-mcp__claude_ai_Gmail__send_message}" python3 -c '
import json, os
with open(os.environ["O_INPUT"], encoding="utf-8") as f: tool_input=json.load(f)
print(json.dumps({"tool_name":os.environ["O_TOOL"], "tool_input":tool_input,
                  "session_id":os.environ["O_SESSION"], "cwd":os.environ["O_CWD"]}))'
}
o_claim() { o_output_decision "$(o_guard "$1")"; }

O_REVIEW="$(o_review "$O_SEND")"
assert_grep_str "O10: review exposes the complete canonical payload" "Approved body" "$O_REVIEW"
assert_grep_str "O10: …and its SHA-256" '"sha256"' "$O_REVIEW"
assert_grep_str "O10: …bound to the Claude wire name, not the Codex one" \
  'mcp__claude_ai_Gmail__send_message' "$O_REVIEW"
assert_no_grep_str "O10: …and never the Codex spelling" \
  'mcp__codex_apps__gmail__send_email' "$O_REVIEW"
assert_absent "O10: review alone writes no permit" "$O_ROOT/.claude/outbound-permits"
assert_exit "O10: the tool selector is a closed allowlist" 2 \
  python3 "$O_PERMIT" review --cli claude --tool arbitrary --tool-input "$O_SEND"
assert_exit "O10: the CLI selector is a closed allowlist too" 2 \
  python3 "$O_PERMIT" review --cli notacli --tool gmail --tool-input "$O_SEND"
assert_exit "O10: issue refuses to treat a permit as approval" 1 \
  python3 "$O_PERMIT" issue --cli claude --tool gmail --tool-input "$O_SEND" \
    --expected-sha256 "$(o_hash "$O_SEND")" --project-root "$O_ROOT" \
    --session-id no-confirm --approval-ref TEST --approval-quote approved

# the draft escape hatch: with draftId set, the connector sends the draft and
# IGNORES every field the permit hashed. A permit must not be able to name one.
O_DRAFT="$O_ROOT/draft-input.json"
printf '%s\n' '{"to":["to@example.invalid"],"body":"x","draftId":"draft-1"}' > "$O_DRAFT"
assert_exit "O10: a permit cannot name draftId (it would bind nothing that is sent)" 1 \
  python3 "$O_PERMIT" review --cli claude --tool gmail --tool-input "$O_DRAFT"
O_NORECIP="$O_ROOT/norecip-input.json"
printf '%s\n' '{"to":[],"body":"x"}' > "$O_NORECIP"
assert_exit "O10: …nor an empty recipient list" 1 \
  python3 "$O_PERMIT" review --cli claude --tool gmail --tool-input "$O_NORECIP"
O_NOBODY="$O_ROOT/nobody-input.json"
printf '%s\n' '{"to":["to@example.invalid"],"subject":"s"}' > "$O_NOBODY"
assert_exit "O10: …nor a send with no body at all" 1 \
  python3 "$O_PERMIT" review --cli claude --tool gmail --tool-input "$O_NOBODY"

assert_eq "O10: Gmail send without a permit stays denied" "deny" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-none "$O_ROOT")")"
o_issue "$O_SEND" sess-exact
O_EXACT="$(o_envelope "$O_SEND" sess-exact "$O_ROOT")"
assert_eq "O10: an exact approved Gmail send passes once" "pass" "$(o_claim "$O_EXACT")"
assert_eq "O10: the claimed permit cannot be reused" "deny" "$(o_claim "$O_EXACT")"
assert_dir "O10: the store lives under .claude/, not .codex/" \
  "$O_ROOT/.claude/outbound-permits/claimed"
assert_absent "O10: …and the Codex store is never created by a Claude permit" \
  "$O_ROOT/.codex"

# every send field is inside the canonical hash, and a failed match must not
# consume the ticket.
O_MUT="$O_ROOT/mutations"; mkdir -p "$O_MUT"
O_BASE="$O_SEND" O_MUT_DIR="$O_MUT" python3 -c '
import copy, json, os
with open(os.environ["O_BASE"], encoding="utf-8") as f: base=json.load(f)
changes = {
 "to": lambda d: d.__setitem__("to", ["other@example.invalid"]),
 "to_extra": lambda d: d["to"].append("second@example.invalid"),
 "cc": lambda d: d.__setitem__("cc", ["other-cc@example.invalid"]),
 "bcc": lambda d: d.__setitem__("bcc", ["hidden@example.invalid"]),
 "subject": lambda d: d.__setitem__("subject", d["subject"] + "!"),
 "body": lambda d: d.__setitem__("body", d["body"] + "!"),
 "extra": lambda d: d.__setitem__("replyThreadId", "thread-1"),
}
for name, change in changes.items():
    value=copy.deepcopy(base); change(value)
    with open(os.path.join(os.environ["O_MUT_DIR"], name+".json"), "w", encoding="utf-8") as f:
        json.dump(value, f)
'
for o_field in to to_extra cc bcc subject body extra; do
  o_session="sess-mutate-$o_field"
  o_issue "$O_SEND" "$o_session"
  assert_eq "O10: changing $o_field is denied" "deny" \
    "$(o_claim "$(o_envelope "$O_MUT/$o_field.json" "$o_session" "$O_ROOT")")"
  assert_eq "O10: …without consuming the exact permit ($o_field)" "pass" \
    "$(o_claim "$(o_envelope "$O_SEND" "$o_session" "$O_ROOT")")"
done

# omitted and null object fields are the one declared equivalence
O_OMIT="$O_MUT/omitted.json"
O_BASE="$O_SEND" O_OUT="$O_OMIT" python3 -c '
import json,os
d=json.load(open(os.environ["O_BASE"])); d.pop("htmlBody")
json.dump(d,open(os.environ["O_OUT"],"w"))'
o_issue "$O_SEND" sess-null
assert_eq "O10: omitted and null object fields are equivalent" "pass" \
  "$(o_claim "$(o_envelope "$O_OMIT" sess-null "$O_ROOT")")"

o_issue "$O_SEND" sess-bound
assert_eq "O10: a permit is denied in another session" "deny" \
  "$(o_claim "$(o_envelope "$O_SEND" wrong-session "$O_ROOT")")"
assert_eq "O10: …and remains usable in its bound session" "pass" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-bound "$O_ROOT")")"

o_issue "$O_SEND" sess-project
assert_eq "O10: a permit is denied outside its bound project" "deny" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-project /tmp)")"
assert_eq "O10: …and remains usable in its bound project" "pass" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-project "$O_ROOT")")"

o_issue "$O_SEND" sess-tool
assert_eq "O10: no permit opens a neighbouring outward tool" "deny" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-tool "$O_ROOT" mcp__claude_ai_Gmail__create_draft)")"
assert_eq "O10: …not even the reply beside it" "deny" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-tool "$O_ROOT" mcp__claude_ai_Gmail__reply)")"
assert_eq "O10: …and only the exact Gmail send can claim it" "pass" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-tool "$O_ROOT")")"

# ── expiry, WITHOUT asking this machine what time it is ──────────────────
# THIS TEST USED TO ISSUE A 1-SECOND PERMIT AND `sleep 2`. It failed about once
# in 25 runs, and an independent review found out why: on this host (WSL2)
# `sleep 2` sometimes returns after ~0.37s — measured 3 times in 40 — so the
# permit had not expired when the claim arrived and the claim rightly
# succeeded. The test was asserting the clock, not the code.
#
# So: issue a NORMAL permit, then move its timestamps into the past by
# rewriting the record. `created_at`/`expires_at` are the only things changed,
# the lifetime stays inside the helper's accepted range, and no test anywhere
# has to wait for a second to go by. A sleeping test on a machine whose sleep
# is unreliable is a coin toss wearing a lab coat.
o_repoint() {  # o_repoint SESSION CREATED_DELTA EXPIRES_DELTA — seconds from now
  O_R="$O_ROOT" O_S="$1" O_C="$2" O_E="$3" python3 -c '
import json, os, time, pathlib
root = pathlib.Path(os.environ["O_R"]) / ".claude" / "outbound-permits" / "pending"
now = int(time.time())
hits = 0
for path in root.glob("*.json"):
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["session_id"] != os.environ["O_S"]:
        continue
    record["created_at"] = now + int(os.environ["O_C"])
    record["expires_at"] = now + int(os.environ["O_E"])
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    hits += 1
print(hits)'
}
o_issue "$O_SEND" sess-expiry 300
assert_eq "O10: the permit to age is on disk before it is aged" "1" \
  "$(o_repoint sess-expiry -1000 -700)"
assert_eq "O10: an expired permit is refused (no sleep, no clock dependency)" "deny" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-expiry "$O_ROOT")")"
# the control: same shape, same code path, still in date → still passes. Without
# this, a guard that denied everything would also make the line above green.
o_issue "$O_SEND" sess-fresh 300
assert_eq "O10: …while an unexpired permit of the same shape still passes" "pass" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-fresh "$O_ROOT")")"

# ── the flake's mechanism, pinned so a fix is a DELIBERATE change ─────────
# DOCUMENTS CURRENT BEHAVIOUR, and current behaviour is a known weakness.
# `validate_permit` RAISES from inside the scan loop, so one unusable permit in
# `pending/` aborts the whole scan and denies every permit the scan had not
# reached yet — including a perfectly good one. A backwards step of the system
# clock makes `created_at > now` true and produces exactly that.
#
# AND THIS IS WHY THE FLAKE WAS INTERMITTENT RATHER THAN CONSTANT: the scan is
# `sorted(pending.glob("*.json"))`, and the filename is a RANDOM permit id. A
# bad permit only harms a good one when its name happens to sort FIRST. Writing
# this test the obvious way produced a test that passed or failed by coin toss
# — so the bad permit is renamed here to sort first, which is the only way to
# assert the mechanism deterministically.
#
# The direction is safe (deny), which is why this was never urgent. If the
# helper is ever changed to skip a bad permit and continue, THIS ASSERTION
# SHOULD FLIP — that is the point of pinning it.
o_issue "$O_SEND" sess-poison 300
assert_eq "O10: a permit dated in the future is on disk" "1" \
  "$(o_repoint sess-poison 600 900)"
assert_eq "O10: …and is renamed to sort first (the scan is ordered by filename)" "1" \
  "$(O_R="$O_ROOT" python3 -c '
import json, os, pathlib
root = pathlib.Path(os.environ["O_R"]) / ".claude" / "outbound-permits" / "pending"
moved = 0
for path in sorted(root.glob("*.json")):
    if json.loads(path.read_text(encoding="utf-8"))["session_id"] == "sess-poison":
        path.rename(root / ("0" * 32 + ".json")); moved += 1
print(moved)')"
o_issue "$O_SEND" sess-victim 300
assert_eq "O10: [known weakness] an unusable permit scanned first denies a good one" "deny" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-victim "$O_ROOT")")"
# clear the poisoned record so the rest of the group is unaffected
assert_eq "O10: …and the poisoned record can be removed" "1" \
  "$(O_R="$O_ROOT" python3 -c '
import json, os, pathlib
root = pathlib.Path(os.environ["O_R"]) / ".claude" / "outbound-permits" / "pending"
gone = 0
for path in list(root.glob("*.json")):
    if json.loads(path.read_text(encoding="utf-8"))["session_id"] == "sess-poison":
        path.unlink(); gone += 1
print(gone)')"
assert_eq "O10: …after which the good permit claims normally" "pass" \
  "$(o_claim "$(o_envelope "$O_SEND" sess-victim "$O_ROOT")")"

# Slack: the exact wire name, the exact argument set
O_SLACK="$O_ROOT/slack-input.json"
printf '%s\n' '{"channel_id":"C0ABC12345","text":"Approved Slack body"}' > "$O_SLACK"
O_SLACK_REVIEW="$(o_review "$O_SLACK" slack)"
assert_grep_str "O10: Slack review names the Claude wire tool" \
  'mcp__slack__slack_post_message' "$O_SLACK_REVIEW"
assert_no_grep_str "O10: …not the Codex one" \
  'mcp__codex_apps__slack__slack_send_message' "$O_SLACK_REVIEW"
assert_eq "O10: Slack send without a permit stays denied" "deny" \
  "$(o_claim "$(o_envelope "$O_SLACK" slack-none "$O_ROOT" mcp__slack__slack_post_message)")"
o_issue "$O_SLACK" slack-exact 300 slack
O_SLACK_EXACT="$(o_envelope "$O_SLACK" slack-exact "$O_ROOT" mcp__slack__slack_post_message)"
assert_eq "O10: an exact approved Slack post passes once" "pass" "$(o_claim "$O_SLACK_EXACT")"
assert_eq "O10: the claimed Slack permit cannot be reused" "deny" "$(o_claim "$O_SLACK_EXACT")"
o_issue "$O_SLACK" slack-thread 300 slack
assert_eq "O10: a post permit does not open the threaded reply beside it" "deny" \
  "$(o_claim "$(o_envelope "$O_SLACK" slack-thread "$O_ROOT" mcp__slack__slack_reply_to_thread)")"

# the two CLIs share the binding and nothing else: a Codex-named tool cannot
# claim through the Claude selector, and vice versa.
assert_exit "O10: a Codex wire name cannot claim through --cli claude" 1 \
  env O_P="$O_PERMIT" O_R="$O_ROOT" bash -c \
  'printf "%s" "{\"tool_name\":\"mcp__codex_apps__gmail__send_email\",\"tool_input\":{},\"session_id\":\"x\",\"cwd\":\"$O_R\"}" | python3 "$O_P" claim --cli claude --project-root "$O_R" 2>/dev/null'
assert_exit "O10: …and a Claude wire name cannot claim through --cli codex" 1 \
  env O_P="$O_PERMIT" O_R="$O_ROOT" bash -c \
  'printf "%s" "{\"tool_name\":\"mcp__claude_ai_Gmail__send_message\",\"tool_input\":{},\"session_id\":\"x\",\"cwd\":\"$O_R\"}" | python3 "$O_P" claim --cli codex --project-root "$O_R" 2>/dev/null'

# ─── O11. the settings example registers the hook as the docs specify ──────
# "To match every tool from a server, append `.*` to the server prefix. The
# `.*` is required: a matcher like `mcp__memory` … is compared as an exact
# string and matches no tool."
O_SETTINGS="$REPO_ROOT/templates/claude/settings.json.example"
assert_file "O11: the Claude settings template ships" "$O_SETTINGS"
assert_ok "O11: …and is valid JSON" \
  env O_S="$O_SETTINGS" python3 -c 'import json,os;json.load(open(os.environ["O_S"]))'
O_HOOKS="$(O_S="$O_SETTINGS" python3 -c '
import json, os
d = json.load(open(os.environ["O_S"]))
pre = d.get("hooks", {}).get("PreToolUse", [])
print(json.dumps(pre))')"
assert_grep_str "O11: PreToolUse is registered" '"matcher"' "$O_HOOKS"
assert_grep_str "O11: …with a matcher that is a regex over the MCP namespace" \
  '"mcp__.*"' "$O_HOOKS"
assert_grep_str "O11: …pointing at the guard" 'outbound_guard.sh' "$O_HOOKS"
# a relative path resolves against wherever the CLI was started, which is not
# the project root under cron. The documented placeholder is the fix, and it
# also keeps an absolute machine path out of a tracked file.
assert_grep_str "O11: …by the documented project-dir placeholder, not a relative path" \
  'CLAUDE_PROJECT_DIR' "$O_HOOKS"
assert_grep "O11: the template says the pass is never \"allow\"" \
  "permissionDecision" "$O_SETTINGS"

# ─── O12. the guard reaches a worktree, or it does not exist there ─────────
# A git worktree receives only TRACKED files, and the two files that ARM the
# guard (.claude/settings.json, .codex/config.toml) are instance data, kept out
# of the repository on purpose. So `git worktree add` arms nothing, and the
# agent in that worktree has no brake — while the checkout beside it does.
# Measured 2026-09-13: six worktrees existed on the author's machine and not
# one had a .claude/ or .codex/ directory. An independent review reproduced it
# from inside the worktree it was reviewing in.
O_WT_SCRIPT="$REPO_ROOT/scripts/worktree_guard_copy.sh"
assert_file "O12: the worktree arming script ships" "$O_WT_SCRIPT"
assert_ok "O12: …and is syntactically valid bash" bash -n "$O_WT_SCRIPT"
assert_ok "O12: …and is executable in the tree" test -x "$O_WT_SCRIPT"
assert_exit "O12: …and prints its own help" 0 bash "$O_WT_SCRIPT" --help

# a synthetic checkout, armed, and an empty worktree beside it. The script
# derives the source from its OWN location, so it has to live in the fixture.
O_WT_SRC="$TEST_TMP/o_wt_src"
O_WT_DST="$TEST_TMP/o_wt_dst"
mkdir -p "$O_WT_SRC/scripts" "$O_WT_SRC/.claude/hooks" "$O_WT_SRC/.codex/hooks" "$O_WT_DST"
cp "$O_WT_SCRIPT" "$O_WT_SRC/scripts/"
chmod +x "$O_WT_SRC/scripts/worktree_guard_copy.sh"
printf '{"hooks":{"PreToolUse":[{"matcher":"mcp__.*"}]}}\n' > "$O_WT_SRC/.claude/settings.json"
printf '#!/usr/bin/env bash\nprintf "{}"\n' > "$O_WT_SRC/.claude/hooks/outbound_guard.sh"
printf 'command = "%s/.codex/hooks/outbound_guard.sh"\n' "$O_WT_SRC" > "$O_WT_SRC/.codex/config.toml"
printf '#!/usr/bin/env bash\nprintf "{}"\n' > "$O_WT_SRC/.codex/hooks/outbound_guard.sh"
O_WT_RUN="$O_WT_SRC/scripts/worktree_guard_copy.sh"

# --dry-run must write NOTHING. A dry run that creates the directory it is
# only supposed to describe would leave a half-armed worktree looking armed.
O_WT_DRY="$(bash "$O_WT_RUN" --dry-run "$O_WT_DST" 2>&1)"
assert_grep_str "O12: --dry-run says what it would copy" "would copy" "$O_WT_DRY"
assert_grep_str "O12: …and says it wrote nothing" "nothing written" "$O_WT_DRY"
assert_absent "O12: …and really did not write .claude/" "$O_WT_DST/.claude"
assert_absent "O12: …nor .codex/" "$O_WT_DST/.codex"

assert_exit "O12: the real run exits 0" 0 bash "$O_WT_RUN" "$O_WT_DST"
assert_file "O12: the PreToolUse registration lands" "$O_WT_DST/.claude/settings.json"
assert_file "O12: …with the hook beside it" "$O_WT_DST/.claude/hooks/outbound_guard.sh"
assert_file "O12: …and the Codex config" "$O_WT_DST/.codex/config.toml"
assert_file "O12: …and its hook" "$O_WT_DST/.codex/hooks/outbound_guard.sh"

# The Codex hook path is absolute. Copied verbatim, the worktree's agent would
# run the SOURCE checkout's hook and write permits into the source tree.
assert_grep "O12: the Codex hook path is repointed at the worktree" \
  "$O_WT_DST/.codex/hooks/outbound_guard.sh" "$O_WT_DST/.codex/config.toml"
assert_no_grep "O12: …and no longer names the checkout it came from" \
  "$O_WT_SRC/.codex/hooks" "$O_WT_DST/.codex/config.toml"

# NEVER overwrite: an entry already there is somebody's, not ours.
printf 'MINE\n' > "$O_WT_DST/.claude/settings.json"
O_WT_AGAIN="$(bash "$O_WT_RUN" "$O_WT_DST" 2>&1)"
assert_grep_str "O12: a second run skips what already exists" "skip (exists)" "$O_WT_AGAIN"
assert_grep "O12: …and does not touch it" "MINE" "$O_WT_DST/.claude/settings.json"

# an unarmed SOURCE must say so rather than silently copy nothing
O_WT_BARE="$TEST_TMP/o_wt_bare"
O_WT_BARE_DST="$TEST_TMP/o_wt_bare_dst"
mkdir -p "$O_WT_BARE/scripts" "$O_WT_BARE_DST"
cp "$O_WT_SCRIPT" "$O_WT_BARE/scripts/"
O_WT_BARE_OUT="$(bash "$O_WT_BARE/scripts/worktree_guard_copy.sh" "$O_WT_BARE_DST" 2>&1)"
assert_grep_str "O12: an unarmed source reports each absent piece" "absent (source)" "$O_WT_BARE_OUT"
assert_grep_str "O12: …and says to arm the source first" "Arm it there first" "$O_WT_BARE_OUT"

assert_exit "O12: no argument is refused, not assumed" 2 bash "$O_WT_RUN"
assert_exit "O12: an unknown flag is refused" 2 bash "$O_WT_RUN" --nope "$O_WT_DST"
assert_exit "O12: a missing directory is refused" 2 bash "$O_WT_RUN" "$TEST_TMP/o_wt_nothing_here"
assert_exit "O12: copying a checkout onto itself is refused" 2 bash "$O_WT_RUN" "$O_WT_SRC"
