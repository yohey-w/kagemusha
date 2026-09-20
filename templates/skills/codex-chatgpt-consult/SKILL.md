---
name: codex-chatgpt-consult
description: Use when the user asks Codex Desktop to consult a user-selected ChatGPT Web model through the standard in-app Browser and capture its final answer. Not for API calls, external browser automation, or prompt drafting without sending.
---

# Consult ChatGPT Web from Codex Desktop

Carry one authorized consultation through the standard in-app Browser, preserve the complete final answer, and only then synthesize it. Preparing a prompt or clicking Send is not completion.

## Prerequisites and route

- This is a Codex Desktop skill. The current session must list the `browser:control-in-app-browser` skill and support the in-app Browser (`iab`).
- Read that Browser skill and the selected browser's complete current documentation before browser interaction. Those instructions are authoritative for setup and UI control.
- Select the in-app Browser explicitly and keep using that same browser binding. Do not substitute Chrome, Edge, Computer Use, standalone Playwright, a private API, CDP, or a custom browser client.
- If the Browser skill, its required runtime, or `iab` is unavailable, stop and report which prerequisite is missing.

## Authorization boundary

A direct request to consult ChatGPT Web authorizes one scoped consultation message and retrieval of its answer. It does not authorize sending unrelated workspace material, contacting another person or service, changing account or security settings, or starting an additional consultation. A request to draft or review a prompt without sending does not authorize Send.

Follow all higher-priority local outbound restrictions. If a local rule requires separate approval, queue, or user action, stop at that boundary. Never weaken a hook, browser control, account protection, or other security setting to make the consultation work.

`advisor-gate` is optional for checking context sufficiency before sending and auditing the returned answer afterward. It does not expand authorization, replace the user's requested destination, or override stronger local outbound restrictions. Do not launch a second external consultation through it without separate authorization.

## Prepare the consultation packet

1. Identify the decision or question, the exact material the user authorized, confirmed facts, hypotheses, unresolved conditions, constraints, and the requested output.
2. Remove unrelated secrets and personal or project data. Preserve source text that the remote model must inspect; do not replace evidence with a summary that changes its meaning.
3. If the user wants an independent view, do not lead with this agent's recommendation or another model's conclusion.
4. Record the exact model and mode requested by the user. If either matters but is unspecified, ask before opening the consultation. Do not invent a default.
5. Save the exact outbound packet without overwriting an existing file, then calculate and record its SHA-256 hash.

## Authenticate without taking over the account

Use the visible, ordinary sign-in flow only. If sign-in is required, ask the user to sign in in the in-app Browser and tell you when it is ready. If the user explicitly asks for help with visible sign-in steps, stop for passwords, passkeys, MFA approvals, recovery, CAPTCHA, or any account/security change and hand control back to the user.

Never read browser cookies, storage, profiles, passwords, or session databases. Never save credentials or one-time codes in files, prompts, logs, or metadata. If the visibly signed-in account conflicts with an account the user specified, stop and ask the user to switch it.

## Verify the requested model and mode

Start a new chat unless the user explicitly requested an existing conversation. Immediately before sending, inspect the visible model and mode controls and record their labels exactly as shown.

A plan label, a generic label such as `Latest`, or prior knowledge of the product UI is not proof that the requested model or mode is active. Never assume that `Latest` means `Pro`, or that one model generation maps to another label. If the visible UI does not unambiguously confirm the user's requested model and mode, do not send; report the observed labels and ask the user how to proceed.

## Enter and send exactly once

Long pasted text may be converted into an attachment-like paste card while the editor appears empty. Before retyping anything, inspect both the visible page and documented interactive state for the card and any control that reveals its text. An empty editor alone is not evidence that the packet was lost.

- Compare the pending message with the saved packet. Account for harmless editor newline normalization explicitly; never summarize evidence text to make comparison easier.
- Remove only a duplicate draft created during this attempt. Do not alter the user's existing attachments or messages.
- Confirm the target conversation, visible model and mode, packet identity, and absence of an active generation. Then send once.
- Verify that one copy of the user message appears in the conversation and that generation starts.

If send status is uncertain, inspect the conversation and current UI state. Stop unless you can prove the message is unsent. Absence from one DOM query or an empty editor is not proof. If it is definitely unsent, make at most one retry, and only after re-verifying the conversation, packet, model, mode, and non-generating state. If the retry is uncertain, stop. Never risk a duplicate send to make progress.

## Capture the complete final answer

Wait without sending follow-up messages. Treat the response as complete only when generation controls are gone and final-answer actions or equivalent documented completion indicators are present. Errors, partial text, and intermediate status messages are not a final answer.

Use the response's copy action when available, or the documented visible-page method, to capture the complete target answer. Do not read an arbitrary pre-existing clipboard before invoking Copy. Prefer copied Markdown when the UI provides it.

Before writing any synthesis:

1. Save the captured final answer verbatim to a new dedicated file; never overwrite a prior consultation.
2. Read the file back and compare its bytes with the captured answer bytes.
3. Calculate SHA-256 for both byte sequences and record both hashes plus an explicit equality result. Equality must pass before the saved file is treated as the verbatim record.
4. Store metadata separately: conversation URL, visible model and mode labels, capture method, outbound packet hash, response hashes, equality result, and any uncertainty. Do not mix audit notes into the verbatim answer.

If the answer cannot be captured completely or the saved bytes cannot be proven equal, stop and report the failure without presenting a synthesis as complete.

## Audit and report

Check the answer against the packet for unsupported claims, changed numbers, missing conditions, responsibility boundaries, costs, and safety or contractual assumptions. The remote answer is advice, not a verified fact or a user decision.

Return the conclusion, the verbatim-answer path, metadata path, recorded visible model and mode, conversation URL, and any unresolved issue. Clearly distinguish the remote answer from this agent's synthesis.

This workflow can reduce accidental duplication and preserve evidence. It does not guarantee compliance with service terms, account safety, or that an account will never be restricted or banned. Never make such a guarantee.

## Stop conditions

Stop and notify the user when any of these occurs:

- the standard in-app Browser route or its current documentation is unavailable;
- sign-in, MFA, recovery, CAPTCHA, or an account/security change needs the user;
- authorization scope or a superior local outbound restriction does not permit the send;
- the requested model or mode is missing, ambiguous, or not visibly verified;
- the packet shown before Send does not match the saved packet;
- send status is uncertain, a duplicate may already exist, or the single allowed retry remains uncertain;
- the final answer may be incomplete, capture fails, or saved-content equality fails;
- continuing would require weakening security or switching to an unapproved route.

## 日本語クイック利用

前提は Codex Desktop、標準の内蔵 Browser、ChatGPT Web へのログインです。呼び出し例: `$codex-chatgpt-consult を使い、ChatGPT Web の画面で「<表示どおりのモデル名>」「<表示どおりのモード>」を確認してから、この相談を1回だけ送り、最終回答全文を保存・照合して要点を返して。`

モデル名・モードを画面で確認できない、ログイン/MFAが必要、送信済みか不明、重複の恐れがある、最終回答全文や保存一致を確認できない場合は停止します。`Latest` などの一般名を `Pro` とみなして自動送信しません。
