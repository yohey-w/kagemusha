# One-shot outbound permits

This procedure opens exactly one approved Gmail `send_email` call. It does not approve a message.
Use it only after the user has explicitly approved the exact message shown by `review`.

## Scope and threat model

The guard prevents accidental outward actions by a trusted agent working in the expected workspace.
It is not an isolation boundary against an adversarial agent that can edit the hook or helper, or invoke the operator helper without authorization.
A permit records an approval; possession or creation of a permit does not create approval.
Only the exact hook wire operation `mcp__codex_apps__gmail__send_email` can use a permit.
No permit exception exists for drafts, replies, forwards, posts, publishing, deletion, or any other tool.

Codex's hook host fails open if the hook is missing, unreadable, or emits output rejected by the host schema.
The guard itself denies malformed inputs and missing permit dependencies, but it cannot protect a call if the host never runs it.
Therefore changes to the guard, helper, setup, or hook schema must pass [the complete test suite](../scripts/test.sh) before use.
The implementation sources are [outbound_guard.sh](../templates/codex/hooks/outbound_guard.sh) and [outbound_permit.py](../templates/codex/hooks/outbound_permit.py).

## Prepare the exact Gmail input

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

## Review, approve, and issue

Use the installed helper inside the active project:

```sh
PROJECT_ROOT='<project-root>'
SESSION_ID='<session-id>'
INPUT_FILE='<project-root>/send-input.json'

python3 "$PROJECT_ROOT/.codex/hooks/outbound_permit.py" review \
  --tool-input "$INPUT_FILE"
```

`review` writes nothing. It prints the complete canonical input and its `sha256`.
Present the reviewed recipients, headers, body, and attachments to the user and obtain explicit approval for that exact payload.
Do not infer approval from silence, a generic earlier instruction, or a permit created by an agent.
Record the real conversation reference and the user's exact approval words, then issue the permit:

```sh
python3 "$PROJECT_ROOT/.codex/hooks/outbound_permit.py" issue \
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
The permit is bound to the complete canonical input, resolved project root, session ID, exact Gmail tool, and expiry.

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

## Validation baseline

The reference implementation passed 1,013 of 1,013 automated tests, including rejection of permit reuse.
A separate native Gmail acceptance run verified exactly one send, full SENT/header/body readback, and permit state (`claimed` present; `pending` empty); it did not attempt a second send.
Those results reduce regression risk; they do not change the threat model or replace per-message user approval.
