# One-shot outbound permits

This procedure opens exactly one approved Gmail or Slack send call. It does not approve a message.
Use it only after the user has explicitly approved the exact message shown by `review`.

## Scope and threat model

The guard prevents accidental outward actions by a trusted agent working in the expected workspace.
It is not an isolation boundary against an adversarial agent that can edit the hook or helper, or invoke the operator helper without authorization.
A permit records an approval; possession or creation of a permit does not create approval.
Only these exact hook wire operations can use a permit:

- Gmail: `mcp__codex_apps__gmail__send_email`
- Slack: `mcp__codex_apps__slack__slack_send_message`

The Slack JavaScript wrapper spelling `mcp__codex_apps__slack_slack_send_message` is different and cannot use a permit.
No permit exception exists for Gmail drafts/replies/forwards or Slack drafts, edits, reactions, uploads, channel changes, invitations, deletion, or scheduling.
The installed Slack connector's read-only get/list/read/search operations remain available through an exact enumerated allowlist; all other operations in the Slack wire namespace fail closed.

Codex's hook host fails open if the hook is missing, unreadable, or emits output rejected by the host schema.
The guard itself denies malformed inputs and missing permit dependencies, but it cannot protect a call if the host never runs it.
Therefore changes to the guard, helper, setup, or hook schema must pass [the complete test suite](../scripts/test.sh) before use.
The implementation sources are [outbound_guard.sh](../templates/codex/hooks/outbound_guard.sh) and [outbound_permit.py](../templates/codex/hooks/outbound_permit.py).

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

For Slack, include the destination and every message option:

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

## Review, approve, and issue

Use the installed helper inside the active project:

```sh
PROJECT_ROOT='<project-root>'
SESSION_ID='<session-id>'
INPUT_FILE='<project-root>/send-input.json'

python3 "$PROJECT_ROOT/.codex/hooks/outbound_permit.py" review \
  --tool gmail \
  --tool-input "$INPUT_FILE"
```

Use `--tool slack` for Slack. The selector is a closed choice of `gmail` or `slack`; omitting it preserves the Gmail default.

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

## Validation baseline

The reference implementation's complete automated test count is recorded by `scripts/test.sh`; the suite includes Gmail and Slack exact binding, rejection of altered arguments, expiry, reuse, wrong session/project/tool, and concurrent double-claim.
A separate native Gmail acceptance run verified exactly one send, full SENT/header/body readback, and permit state (`claimed` present; `pending` empty); it did not attempt a second send.
Slack tests are synthetic and perform no external API write; a live Slack acceptance run must follow the send-once/readback procedure above and preserve `ts` plus permalink as evidence.
Those results reduce regression risk; they do not change the threat model or replace per-message user approval.
