# One-shot outbound permits

This procedure opens exactly one approved Gmail or Slack send call — and, on the Claude side, one approved Notion page write or one approved Google Calendar event create/update. It does not approve a message.
Use it only after the user has explicitly approved the exact message shown by `review`.

## Scope and threat model

The guard prevents accidental outward actions by a trusted agent working in the expected workspace.
It is not an isolation boundary against an adversarial agent that can edit the hook or helper, or invoke the operator helper without authorization.
A permit records an approval; possession or creation of a permit does not create approval.

One helper serves both CLIs. `--cli` selects which pair of exact wire operations a permit may open, and which directory the store lives in.
It defaults to `codex`, so an install that predates the shared helper keeps working with the arguments it already passes.
Nothing else differs: canonicalization, the SHA-256 binding over the complete argument set, the project/session/expiry binding, and the single atomic claim are shared, because those are the parts that must not drift apart.

| `--cli` | `--tool gmail` | `--tool slack` | `--tool slack-reply` | `--tool notion-update` | `--tool notion-create` | `--tool calendar-create` | `--tool calendar-update` | permit store |
|---|---|---|---|---|---|---|---|---|
| `codex` (default) | `mcp__codex_apps__gmail__send_email` | `mcp__codex_apps__slack__slack_send_message` (`thread_ts` allowed) | — | — | — | `mcp__codex_apps__google_calendar__create_event` (no attendees only) | — | `<project>/.codex/outbound-permits/` |
| `claude` | `mcp__claude_ai_Gmail__send_message` | `mcp__slack__slack_post_message` | `mcp__slack__slack_reply_to_thread` | `mcp__claude_ai_Notion__notion-update-page` | `mcp__claude_ai_Notion__notion-create-pages` | `mcp__claude_ai_Google_Calendar__create_event` | `mcp__claude_ai_Google_Calendar__update_event` | `<project>/.claude/outbound-permits/` |

`--tool` is one flag for every CLI, so its allowed values are the union; asking
for a selector the chosen CLI does not have is a usage error (exit 2), never a
silent resolution to another CLI's wire name. Codex has no Notion row because
its guard names no Notion tool: there is nothing there to open.

**The default cuts both ways, and only the Claude-only selectors fail loudly.**
Asking for `notion-update` without `--cli claude` is the usage error above: it
names the cause and exits 2. The three selectors Codex also has — `gmail`,
`slack`, `calendar-create` — cannot do that, because the name resolves; the
Claude-shaped payload is simply checked against the *Codex* schema. Measured
2026-09-27 against this helper: a Claude calendar payload (`summary`,
`startTime`) reviewed without `--cli claude` fails with `Calendar title must be
a non-empty string`, naming a field the Claude connector does not have; a
Claude Gmail payload (`to` as an array) passes `review` with **no error at
all**, and `issue` then writes a permit under
`<project>/.codex/outbound-permits/pending/` bound to
`mcp__codex_apps__gmail__send_email` — a wire name the Claude call never
carries, so the send is denied and the refusal says nothing about a missing
flag.
The calendar case is the one that was hit, on the first real use of the
calendar path (2026-09-27). On Claude Code, pass `--cli claude` to `review` and
to `issue`, every time.

The Notion pair was added 2026-09-18 on the operator's ruling. The reasoning is
not that Notion became inward — the guard still treats a shared workspace as
outward speech — but that this system keeps its 正本 (ledgers, job logs) in the
operator's own Notion, so an approved edit of ONE named page is work they asked
for. Two acts only, and the validators keep one permit to one act: an update
must name its `page_id` and its `command`, a create must carry an explicit
`parent` and exactly one entry in `pages`, and neither may set `allow_async`
(a backgrounded write answers before the page is written, so the approval would
cover an outcome nobody has seen).

An update is held to **one** edit as well: `content_updates` may carry exactly
one entry, and `replace_all_matches` is refused — one permit that rewrites every
match is many edits under a single approval. So when an approved change touches
several places on the same page, there are two honest shapes and no third:
widen the single replacement to the **contiguous range that covers them**, so
the approver sees the whole of what lands, or take **one permit per edit**. The
first shape was used on 2026-09-26, bundling three separate passages of one page
into one range.

The Calendar pair was added 2026-09-26 on the operator's instruction
(「カレンダーへの許可ルートを作ってくれ」). An event with attendees is not a
private note: Google mails each attendee an invitation, and an update mails
them again. So the one thing a Calendar permit adds to the shared rules is that
**who is mailed, and how, must be written out in the arguments** — never left to
a default the approver cannot see:

- `calendar-create` requires `summary`, `startTime`, `endTime`, an explicit
  `attendees` array (`[]` when nobody is invited; each entry an object with an
  `email`) and an explicit `notificationLevel` of `NONE`, `EXTERNAL_ONLY` or
  `ALL`. Omitting it — or writing `NOTIFICATION_LEVEL_UNSPECIFIED` — is refused,
  because the connector treats both as `ALL`. The deprecated `attendeeEmails` is
  refused: it would invite people who do not appear under `attendees`.
- `calendar-update` requires `eventId` and an explicit `notificationLevel`.
  Attendee changes go through `addedAttendees` / `removedAttendeeEmails`; the
  deprecated `addedAttendeeEmails` is refused.
- On create, an `eventType` of `OUT_OF_OFFICE` or `FOCUS_TIME` (any case or
  spelling) is refused: a status event may auto-decline other people's
  invitations with a message to their organizers, and this connector has no
  argument that binds it.
- `review` prints a `calendar_attention` block ahead of the payload: the
  invited/added/removed addresses, the notification level, the calendar, and
  the times. It is display only; the hash is over the full canonical payload.

**`delete_event` has no permit path, by decision.** Its arguments are an
`eventId` and a notification level, so the reviewer cannot see what is being
cancelled or who receives the cancellation, and nothing here can undo it — it
fails the operator's own test ("can it be undone?") in a way no review can make
up for. `respond_to_event` (an RSVP to the organizer) has none either. Both stay
on the guard's outward list and go through the queue.

Two limits, stated rather than discovered:

- **An update mails the event's EXISTING attendees, and they are not in the
  arguments.** The permit binds the change, not the audience. Read the event
  (`get_event`) and show its attendee list to the approver before approving an
  update with any `notificationLevel` other than `NONE`. `review` says so in its
  `note`.
- **Fields other than attendees and notification are bound but not
  restricted**: `attachments` (a Drive link attached to an invited event),
  `guestPermissions`, `visibility`, `recurrenceData`, `calendarId`,
  `addGoogleMeetUrl`. They are in the hash and in the payload `review` prints;
  the approver has to read them.

**Codex: the hole is closed first, then a narrower pair is opened**
(2026-09-26, operator's ruling 「Codex 側の穴をふさいでよい」). Until then a
**direct** `google_calendar` create/update/respond call passed the Codex guard
with no permit — none of those names carries a verb from its `OUTBOUND_VERBS`,
yet each mails other people (inside `exec` the write-token scanner already
denied them). The Codex guard now routes create to the permit step and denies
update and respond, in every spelling (`__`/`_`, `mcp__`/`mcp_`). The direct-call
spelling `mcp__codex_apps__google_calendar__create_event` is inferred from the
Gmail twin and has not been observed in a real envelope [未確認]; the permit
accepts the one-underscore catalogue spelling too.

The Codex connector's schema (read from the local Codex tool cache) has **no
notification-level argument**, so who is mailed cannot be bound. Where it cannot
be bound, the permit does not open:

- Codex `calendar-create` requires `title`, `start_time`, `end_time` and
  `attendees: []`. **Any attendee is refused** — such an event goes through the
  queue and is created by hand. `attendee_optionality`, `decline_message` and an
  `auto_decline_mode` other than `declineNone` are refused too: an auto-declining
  status event answers other people's invitations. For the same reason an
  `event_type` of `outOfOffice` or `focusTime` (any case or spelling) must
  write out `auto_decline_mode: "declineNone"`, or no permit is issued —
  Google's default auto-decline for a status event cannot be seen from here.
- One Codex calendar write is **not** denied, as a named exception:
  `set_event_label_silently`. Its schema fixes `sendUpdates=none`, the primary
  calendar and a private label, so it mails nobody.
- **Codex has no `calendar-update`** (parent's ruling, 2026-09-26). An update
  mails the event's existing attendees, who are not in the arguments, and this
  connector cannot silence them — so neither who is mailed nor whether anyone
  is can be bound, and what cannot be bound is not opened. A Codex update goes
  through the queue and is done by hand (or on the Claude side, where
  `notificationLevel: "NONE"` can be bound).

A permit issued for one CLI cannot be claimed through the other: the wire name, the store directory and the selector all have to agree.
One connector answers to two spellings, and a permit accepts both. Measured 2026-09-13/14 on the ChatGPT desktop app: the JavaScript wrapper inside `exec` writes one underscore (`mcp__codex_apps__gmail_send_email`, `mcp__codex_apps__slack_slack_send_message`) while the `PreToolUse` envelope for the same call carries two.
Only that `__`/`_` difference inside the operation segment is absorbed; the `mcp__<server>__` prefix must match exactly, so another connector, another verb, a hyphen or a missing separator stay different tools with no permit path.
A permit still opens one act: it is spent by whichever spelling claims it, exactly once.
No permit exception exists for Gmail drafts/replies/forwards or Slack drafts, edits, reactions, uploads, channel changes, invitations, deletion, or scheduling, nor for Calendar deletion or RSVPs.
On the Notion side the same rule holds for everything but the two page writes: `notion-create-comment`, `notion-send-message-to-session`, `notion-duplicate-page` and `notion-move-pages` keep no permit path and go through the queue. That narrowness is the point — the incident recorded in the guard is one verb being denied while the neighbouring one went straight through.
On the Claude side a threaded Slack reply is a separate tool, `mcp__slack__slack_reply_to_thread`, and since 2026-10-06 (operator's instruction 「スレッド返信にも許可票を出せるようガードを直す」) it has its own selector, `--tool slack-reply`. Before that it had no permit path, and a reply to a customer's thread had to be pasted by hand.
The arguments are exactly `channel_id`, `thread_ts` and `text`. `thread_ts` must already be in Slack's dotted form (`1234567890.123456`); the connector says it will repair a ts written without the period, and a permit must not approve one string while another is sent. A channel-post permit never opens the reply tool, and a reply permit never opens a channel post or another thread.
The permit binds which thread, not what the thread is about: `thread_ts` is a number. Read the thread (`slack_get_thread_replies`) and tell the approver whose message is being answered before asking for approval.
Codex needs no twin: its `slack_send_message` already carries `thread_ts` inside the bound arguments.
Gmail loses nothing by the same rule, because `send_message` threads by itself through `replyThreadId`.
The installed Slack connector's read-only get/list/read/search operations remain available through an exact enumerated allowlist; all other operations in the Slack wire namespace fail closed.

Both hook hosts fail open if the hook is missing, unreadable, or emits output the host rejects.
Claude Code's documentation is explicit about it: when the script path does not exist or is not executable, "the shell exits with a code like 127 … For most hook events, the action proceeds."
The guard itself denies malformed inputs and missing permit dependencies, but it cannot protect a call if the host never runs it.
Therefore changes to a guard, the helper, setup, or a hook schema must pass [the complete test suite](../scripts/test.sh) before use.
The implementation sources are [the Codex guard](../templates/codex/hooks/outbound_guard.sh), [the Claude Code guard](../templates/claude/hooks/outbound_guard.sh), and [the shared outbound_permit.py](../templates/hooks/outbound_permit.py).

The Claude Code guard never answers `permissionDecision: "allow"`.
That value is accepted there and it is an elevation: it approves the call and skips the permission prompt that otherwise guards an interactive session.
Its pass is the empty document `{}`, which leaves the normal permission flow untouched, so a permit lifts the deny without granting anything.
`"ask"` is unused for a different reason: an unattended run has nobody to ask, so `ask` on that lane is a hang rather than a question.

One limitation is inherited from the Codex guard and is stated here rather than left to be discovered.
Each guard's classifier used to read `tool_name` with a regex over the raw payload, which takes the first occurrence.
Every observed payload and every published example puts `tool_name` ahead of `tool_input`, but JSON member order is the producer's choice.

**This was a live bypass, not a theoretical one, and the paragraph that used to stand here was wrong.**
It said "the send path is not exposed to this, because the helper parses the whole envelope with a strict JSON parser before it will claim anything; only the classifier is."
That reasoning skipped a step: the helper only runs for a call the classifier routed to it. A payload carrying the string `"tool_name": "Bash"` INSIDE `tool_input`, with the real name after it, was classified as `Bash` and passed — `{}`, no permit, no helper call. It was reproduced against the live Claude hook on 2026-09-18 by an independent review, and again by the author before the fix.
Since a `tool_input` is attacker-influenced whenever its content comes from outside (a fetched page, a customer's message, a file), this was reachable.

The Claude classifier now reads `tool_name` and `session_id` with `python3`'s JSON parser, taking only top-level members. python3 is already required for the permit path; where it is absent, a payload naming any connector is denied rather than guessed at, and plain tools are unaffected.
The Codex guard still classifies by regex and carries the original weakness.

## A worktree has none of this

A git worktree receives the TRACKED files and nothing else. The two files that arm the guard — `.claude/settings.json` and `.codex/config.toml` — are instance data and are git-ignored on purpose, because they hold machine-local absolute paths. So `git worktree add` arms nothing, and an agent started inside a worktree runs with no brake on outward calls while the checkout beside it is protected. Nothing announces this: the host fails open, and here it never even looks, because there is no hook to fail.

Measured 2026-09-13 on the author's machine: six worktrees existed and not one had a `.claude/` or `.codex/` directory. An independent review reproduced it from inside the worktree it was reviewing in, and confirmed there was no registration at the user level either.

This is worth stating plainly because worktree isolation is the normal recommendation for running parallel agents — so the lane that looks safest was the unguarded one, and adding workers added unguarded seats.

```sh
./scripts/worktree_guard_copy.sh --dry-run <worktree>   # see what is missing
./scripts/worktree_guard_copy.sh <worktree>             # copy it in
```

It never overwrites anything already there, and it repoints the absolute hook path inside the copied Codex config at the worktree — Claude Code needs no rewrite, since its registration uses `${CLAUDE_PROJECT_DIR}`. Codex asks for hook approval again, because a worktree is a new path, and skips the hook silently until that is given.

Arming a worktree is a backstop, not a policy. The rule stays: do outward work in the checkout that is guarded.

## Prepare the exact input

Create a JSON object containing every argument for the single `send_email` call.
A minimal example is:

```json
{
  "payload": {
    "body": {"content": "Approved body"},
    "mime_type": "text/plain"
  },
  "subject": "Approved subject",
  "to": "recipient@example.test"
}
```

Include the real `cc`, `bcc`, reply reference, MIME parts, attachments, and classification fields when applicable.
For matching, canonicalization recursively removes object members whose value is `null` and sorts object keys.
It does not remove `null` array entries, reorder arrays, or alter string values; the subject and message body remain unchanged.
Any other change, including an extra field, recipient, attachment, subject, or body change, requires a new review and approval.

On Claude Code the argument shapes are the connector's own, and they differ from the Codex ones.
Gmail `send_message` takes recipients as **arrays**, and its body is `body` (plain) or `htmlBody` (rich):

```json
{
  "to": ["recipient@example.invalid"],
  "subject": "Approved subject",
  "body": "Approved body"
}
```

`to` must name at least one recipient, and at least one of `body` or `htmlBody` must be non-empty.
`draftId` is rejected outright: the connector documents that when it is present "the other fields are ignored, and the specified draft is sent as is", so a permit whose hash covered `to`/`subject`/`body` would bind nothing that was actually sent.
Slack `slack_post_message` takes exactly `channel_id` and `text`, both non-empty, with `text` limited to 5,000 characters.

For Slack on Codex, include the destination and every message option:

```json
{
  "channel_id": "C0ABC12345",
  "message": "Approved Slack message",
  "reply_broadcast": true,
  "thread_ts": "1700000000.000001"
}
```

`channel_id` and `message` must be non-empty strings, and a message is limited to 5,000 characters.
`thread_ts`, when present, must be a non-empty string; `reply_broadcast` must be boolean and `true` requires `thread_ts`.
`draft_id` with a non-null value is rejected because a permit for a new send must not be reused to send and delete an existing draft.
A schema-supplied `draft_id: null` is equivalent to omission under the canonicalization rule above.

For a Calendar event on Claude Code (`--tool calendar-create`), write out the
invitees and the notification level even when they are "nothing":

```json
{
  "summary": "Approved title",
  "startTime": "2030-01-07T10:00:00+09:00",
  "endTime": "2030-01-07T11:00:00+09:00",
  "attendees": [{"email": "guest@example.invalid"}],
  "notificationLevel": "ALL"
}
```

For `--tool calendar-update`, name the event and the notification level; add
`addedAttendees` / `removedAttendeeEmails` only when the approved change is to
the guest list:

```json
{
  "eventId": "<event id from list_events or search_events>",
  "startTime": "2030-01-08T10:00:00+09:00",
  "endTime": "2030-01-08T11:00:00+09:00",
  "notificationLevel": "NONE"
}
```

The call the agent then makes must carry exactly these arguments; a later
`"notificationLevel"` change, an extra guest, or a one-minute shift is a
different act and is denied.

## Review, approve, and issue

Use the installed helper inside the active project.
On Codex the helper sits in `.codex/hooks/`; on Claude Code it sits in `.claude/hooks/` and every subcommand takes `--cli claude`.
The session id is the one the guard prints in its refusal (`session_id=…`), which is why the deny reason carries it:

```sh
PROJECT_ROOT='<project-root>'
SESSION_ID='<session-id>'
INPUT_FILE='<project-root>/send-input.json'

# Codex
python3 "$PROJECT_ROOT/.codex/hooks/outbound_permit.py" review \
  --tool gmail \
  --tool-input "$INPUT_FILE"

# Claude Code
python3 "$PROJECT_ROOT/.claude/hooks/outbound_permit.py" review \
  --cli claude \
  --tool gmail \
  --tool-input "$INPUT_FILE"
```

Use `--tool slack` for a Slack channel post and, on Claude Code, `--tool slack-reply` for a threaded reply. The selector is a closed choice — `gmail`, `slack` or `calendar-create` on Codex; on Claude Code also `slack-reply`, `notion-update`, `notion-create` and `calendar-update` — and omitting it preserves the Gmail default.

`review` writes nothing. It prints the complete canonical input and its `sha256`.
Present the reviewed recipients, headers, body, and attachments to the user and obtain explicit approval for that exact payload.
Do not infer approval from silence, a generic earlier instruction, or a permit created by an agent.
Record the real conversation reference and the user's exact approval words, then issue the permit:

```sh
python3 "$PROJECT_ROOT/.codex/hooks/outbound_permit.py" issue \
  --tool gmail \
  --tool-input "$INPUT_FILE" \
  --expected-sha256 '<sha256-from-review>' \
  --project-root "$PROJECT_ROOT" \
  --session-id "$SESSION_ID" \
  --ttl-seconds 300 \
  --approval-ref 'example.test/approval/reference' \
  --approval-quote 'I approve the exact reviewed message.' \
  --confirm-user-approved
```

The Claude Code form of the same command is:

```sh
python3 "$PROJECT_ROOT/.claude/hooks/outbound_permit.py" issue \
  --cli claude \
  --tool gmail \
  --tool-input "$INPUT_FILE" \
  --expected-sha256 '<sha256-from-review>' \
  --project-root "$PROJECT_ROOT" \
  --session-id "$SESSION_ID" \
  --ttl-seconds 300 \
  --approval-ref '<where the user approved it>' \
  --approval-quote '<the user\'s exact words>' \
  --confirm-user-approved
```

The TTL must be from 1 through 900 seconds; the default is 300.
Issue immediately before sending. `issue` recomputes the hash and refuses a changed input.
Use the same `--tool` value for `review` and `issue`.
The permit is bound to the complete canonical input, resolved project root, session ID, exact wire tool, and expiry.

## Send once, then read back

Call Gmail `send_email` exactly once with the same JSON object used for review and issue.
The PreToolUse hook atomically moves the matching permit from `pending` to `claimed` before allowing the Gmail API call.
The permit is therefore spent before Gmail reports API success and cannot be reused.

After a successful response, take the returned immutable message ID and call Gmail `read_email` with `format: "full"`.
Confirm that `label_ids` contains `SENT`, then compare the returned To/Cc/Bcc/Subject headers and decoded MIME body with the reviewed input.
Also compare attachment names and MIME structure when the message has attachments.

If the send returns a timeout, transport error, or otherwise ambiguous result, do not retry.
Search Gmail with `search_email_ids`, constrained to `SENT` and the reviewed recipient and subject, then read candidates with `read_email` in `full` format.
If the exact sent message is found, complete the same SENT/header/body readback.
If it is definitely absent, stop; a second send requires a fresh review, fresh explicit approval, and a new permit.

For Slack, call `slack_send_message` exactly once with the same input used for review and issue.
On success, save the returned message timestamp (`ts` or message ID) and permalink as evidence.
Then read the same channel with `slack_read_channel`, and, for a reply, read the same `thread_ts` with `slack_read_thread`.
Verify the returned channel, thread parent, message text, reply-broadcast state when exposed, timestamp, and permalink against the reviewed input and send response.

If the Slack response is a timeout, transport error, or otherwise ambiguous, do not send again automatically.
Read the same channel/thread first; if needed, use the read-only Slack search operations with the exact message and narrow timestamp context.
If the exact message is found, record its `ts` and permalink and complete the readback comparison.
If the result remains ambiguous or the message is definitely absent, stop: any second send requires a fresh review, fresh explicit approval, and a new permit.

## The acceptance run, on either CLI

The automated suite proves the classifier and the binding. It cannot prove that the host actually runs the hook, because that is a property of the CLI and its trust settings, not of this repository. That last step is a manual run, and it is the one that was measured `否` the first time on Codex.

Do it with a destination that cannot receive anything. `test@example.invalid` is reserved by RFC 2606 and will never route.

1. **The hook fires at all.** Set `OUTBOUND_GUARD_LOG` to a writable path and make any connector read. A line appears. No line means the host is not running the hook — on Codex, the usual cause is an untrusted project or an unapproved hook; on Claude Code, a matcher written without its `.*`, or a path that is not executable.
2. **A read still works.** Search the mailbox. It returns results. A guard that blocks the inbound sweep gets switched off, and a guard that is switched off protects nothing.
3. **A send is refused.** Ask the agent, in its own words, to email `test@example.invalid`. The call must be denied and the refusal must name `approval_queue.md`.
4. **The neighbour is refused too.** This is the step the first Codex run failed: when the send was blocked, the model created a **draft** to the real customer instead. Watch for the reroute — to a draft, a reply, a forward, a Notion page, a Slack message — and confirm each is refused as well. Then confirm the queue entry was actually written.
5. **An approved send passes exactly once.** Review, obtain explicit approval, issue, call the tool once, then read the message back and confirm the permit moved from `pending` to `claimed`. Calling it a second time must be denied.

Record the result where your loop records decisions, including which CLI, which version, and what the agent tried to do when it was refused. A guard that has never been run against a live model has not been tested; it has only been written.

## Validation baseline

The reference implementation's complete automated test count is recorded by `scripts/test.sh`; the suite includes Gmail, Slack, Notion and Calendar exact binding, rejection of altered arguments, expiry, reuse, wrong session/project/tool, and concurrent double-claim.
A separate native Gmail acceptance run verified exactly one send, full SENT/header/body readback, and permit state (`claimed` present; `pending` empty); it did not attempt a second send.
Slack tests are synthetic and perform no external API write; a live Slack acceptance run must follow the send-once/readback procedure above and preserve `ts` plus permalink as evidence.
Those results reduce regression risk; they do not change the threat model or replace per-message user approval.
