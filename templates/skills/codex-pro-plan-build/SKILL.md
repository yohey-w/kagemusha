---
name: codex-pro-plan-build
description: Plan and deliver high-rework software changes in Codex Desktop by consulting a user-selected ChatGPT Web Pro model for pivotal design decisions, then implementing against an audited design contract. Use when the user asks for Pro-led strategy or design followed by Codex implementation; do not use for routine debugging or automatic model routing.
---

# Codex Pro Plan and Build

Use a user-selected ChatGPT Web Pro model for the few decisions that could cause expensive rework, then use Codex to turn the audited result into a design contract, code, and tested evidence.

This is a procedure for Codex Desktop. It is not an automatic router, model configuration, quota policy, or guarantee that any named model is the strongest or free to use.

## Required dependency

On the consultation route, before any external consultation, read and follow `$codex-chatgpt-consult` completely. That skill owns Browser availability, login and MFA handoff, visible model and mode verification, paste-card detection, single-send behavior, uncertain-send stops, complete verbatim capture, and hash/equality verification. Do not reproduce or bypass those controls here.

If consultation is required and `$codex-chatgpt-consult` or its in-app Browser capability is unavailable, stop. Do not substitute another browser, an API, a CLI, CDP, or custom browser automation. The local-only route does not require that dependency, Browser availability, login, or Web UI verification.

## Boundaries

- Skill discovery is not permission to send anything externally. A request to implement code is not permission to send repository content to ChatGPT Web.
- Obey repository instructions, outbound controls, and the user's model choice. This skill never weakens security or overrides a stricter local rule.
- Treat the Pro response as advice. Check it against repository evidence and keep unsupported claims unresolved.
- A Pro model from the same provider lineage is not independent verification. Passing the repository's required tests and CI remains mandatory.
- Do not create a new task, child, or consultation automatically.

## 1. Establish the local baseline

Read the repository instructions before planning. Collect current evidence locally:

- repository root, current ref, and exact `HEAD`;
- working-tree status plus the relevant staged and unstaged diff, without disturbing unrelated changes;
- relevant implementation, interfaces, configuration, tests, documentation, and migration history;
- observed failures, commands already run, environmental constraints, and explicit user requirements;
- facts separated from inferences and unresolved questions.

Use the smallest evidence set that can support the decision. Do not send the whole repository by default.

## 2. Decide whether consultation is warranted

Consult only when a wrong decision would be expensive to reverse or would affect several downstream parts. Typical candidates are architecture, public APIs, data contracts or migrations, security boundaries, acceptance criteria, rollback strategy, and feasibility that changes the requested scope.

Do not consult for naming, ordinary refactors, local implementation details, routine debugging, or a test failure that the local evidence can resolve.

When the change is small or an approved design already supplies enough evidence and acceptance criteria, skip Web consultation. Do not ask the user for Web-consultation details on this route. Continue at step 5 to write the local design contract once from repository evidence, and report the consultation model/mode and raw-answer artifact as `not consulted`. If the user explicitly asks for a consultation, respect that intent unless a higher-priority safety or outbound rule forbids it.

## 3. Authorize the consultation scope

Before the first consultation, resolve these fields from the user's explicit instructions and ask only when a field is missing or ambiguous:

1. the development purpose and the repository material allowed to leave the local environment, including exclusions such as secrets, customer data, credentials, and unrelated code; and
2. the Web model and mode.

Do not require the user to choose a consultation count in advance. If the user authorizes this development workflow and its external purpose and information scope, that authorization covers useful follow-up questions, confirmations, and design improvements within the same purpose and scope without approval before every message. Honor any count, cost, or time limit the user does state. Ask again before expanding the purpose, expanding the categories or amount of information sent, or exceeding an explicit limit.

Use `$codex-chatgpt-consult`'s new-chat default unless the user requests an existing chat. Select appropriate non-public, non-overwriting paths for the raw answer and design contract and tell the user what they are; ask for paths only when local rules or the user's instructions require specific locations.

A standalone request handled directly by `$codex-chatgpt-consult` remains authorization for one consultation message. The continuing authorization above applies only because the user requested this development workflow and approved its external purpose and information scope.

Prepare a compact evidence packet containing the decision, constraints, relevant excerpts, alternatives already considered, and the answer format needed. Pass each consultation to `$codex-chatgpt-consult` separately. Its one-send rule means exactly once for that message and protects against uncertain resend; it is not a cap on the whole development workflow. Each consultation inherits all of that skill's stop conditions.

## 4. Preserve and audit the answer

Keep the complete verified raw answer and its consultation metadata at the path established before sending. Do not overwrite it with a summary. Make that raw artifact available to the implementation executor.

Separately audit the advice against the current repository evidence. Record what was adopted, rejected, or left unresolved and why. Conflicts with local facts, constraints, tests, or user instructions are resolved in favor of those sources unless the user explicitly changes the requirement.

## 5. Write the design contract

Create a local design contract with these sections:

1. **Objective**
2. **Non-goals**
3. **Responsibilities and ownership**
4. **Interfaces and data contracts**
5. **Invariants**
6. **Acceptance tests**
7. **Migration and rollback**, when applicable
8. **Unresolved items**

Also identify the evidence baseline (`HEAD` and relevant dirty state) and, when consultation occurred, link the raw answer without replacing it. Every material recommendation must map to repository evidence, an explicit user requirement, or an unresolved item. Do not begin implementation when an unresolved item makes the acceptance tests or safety boundary indeterminate.

## 6. Verify the implementation executor

The recommended profile for this skill is a visibly confirmed Web `Astra Pro` consultation followed by local `gpt-6-astra` at `high`. It is a recommendation, not an automatic setting, free-quota claim, or capability guarantee. Respect another model or effort selected by the user.

When consultation occurs, verify the Web model and mode in the visible UI through `$codex-chatgpt-consult`. Skip that Web check on the local-only route. In both routes, verify the local executor's actual model and effort from available task/runtime metadata when the contract requires a particular executor. Never claim to have switched models or effort when the runtime does not prove it.

If the current executor is not the requested one, use a host capability that exposes the exact model and effort only when the user has authorized that bounded delegation. Otherwise stop and ask the user to switch or choose another executor. Never create a new task automatically.

If the requested pairing conflicts with repository or organization model-allocation rules, state the conflict and ask the user which allowed option to use. Do not silently override either rule.

If missing model/effort evidence is discovered only after implementation has begun or completed, preserve the code, tests, and evidence. Mark the requested execution condition as unverified and never retroactively claim that the work ran at `high` or on a named model. Ask whether the user wants to relax that condition or use a verified executor for the necessary review, test, or other bounded follow-up. Do not discard or reimplement everything unless the resulting contract and evidence actually require it.

## 7. Design, implement, and test locally

Using the verified executor:

1. derive the detailed design and edit plan from the design contract;
2. implement only the authorized scope while preserving unrelated work;
3. add or update tests that demonstrate the acceptance criteria;
4. run focused tests during development;
5. run the repository's required full acceptance suite or CI-equivalent before completion; and
6. reconcile failures with local evidence rather than asking Pro to debug routine implementation issues.

The external answer cannot replace code review, tests, security checks, migration rehearsal, or CI.

## 8. Reconsult only for material design progress

Reconsult when it can materially improve or confirm the design, resolve a new high-impact question, or respond to a contract premise becoming false. Boundary-change examples include:

- a public API must change;
- the data model or migration strategy must change;
- a security boundary or threat assumption changed;
- an acceptance condition is impossible or materially different; or
- the approved design cannot be implemented under the repository's constraints.

Keep ordinary debugging, naming, and small implementation choices local. Do not repeat the same question with the same evidence. If there is no new question or evidence and consultation is no longer producing progress, stop consulting and report why; do not invent a fixed retry limit.

Before reconsulting, record the new question or changed evidence, identify the contract section affected, and notify the user concisely. When the send remains within the authorized workflow purpose and information scope and no explicit count, cost, or time limit has been reached, proceed without additional approval. Ask again before expanding that purpose or sent information, or after an explicit limit is reached. Honor the user's new-chat or existing-chat choice, then invoke `$codex-chatgpt-consult` for one exactly-once message.

After that consultation:

1. save and verify the new raw answer and metadata at a distinct, non-overwriting path;
2. audit the new advice against the changed local evidence;
3. write a new version of the design contract and retain the previous version;
4. update every acceptance test affected by the contract change; and
5. return to step 7 for implementation and the focused plus full required test runs.

## Completion report

Report:

- the verified consultation model/mode and implementation model/effort, using `not consulted` for the consultation fields on the local-only route;
- the design contract path and each preserved raw-answer path, or `not consulted` when none exists;
- implemented changes and tests or CI run, with exact results;
- advice rejected or left unresolved; and
- any remaining risk, failed check, or required user action.

Stop instead of claiming the affected requirement is satisfied when required model metadata is unavailable, a requested switch cannot be performed, authorization is missing, a send may have duplicated, capture verification failed, the design contract is unsafe to implement, or mandatory acceptance tests have not passed. Preserve completed work and report its actual evidence; do not infer missing execution metadata or demand a full rewrite without evidence.

## 日本語での短い使い方

「`$codex-pro-plan-build` を使い、外部送信してよい目的と情報範囲を確認し、重要設計を指定のWeb Proへ相談して設計契約を作り、指定したCodexモデル/effortを実表示で確認してから実装・全試験まで進めて」と依頼します。認可済みの目的・範囲内なら、有益な確認や設計改善は逐一承認なしで続けられます。利用者が指定した回数・費用・時間制限は守り、範囲拡大は再確認します。通常デバッグや小判断はローカルで扱い、同じ問いと証拠を反復しません。
