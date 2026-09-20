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

When the change is small or an approved design already supplies enough evidence and acceptance criteria, skip Web consultation. Do not ask the user for outbound-send authorization, model resolution, or a consultation budget on this route. Continue at step 5 to write the local design contract once from repository evidence, and report the consultation model/mode and raw-answer artifact as `not consulted`. If the user explicitly asks for a consultation, respect that intent unless a higher-priority safety or outbound rule forbids it.

## 3. Authorize one bounded consultation

Before the first consultation, resolve only these authorization fields from the user's explicit instructions and ask only when a field is missing or ambiguous:

1. the exact question, repository material allowed to leave the local environment, and exclusions such as secrets, customer data, credentials, and unrelated code;
2. the Web model and mode; and
3. the allowed number of consultation messages.

Use `$codex-chatgpt-consult`'s new-chat default unless the user requests an existing chat. Select appropriate non-public, non-overwriting paths for the raw answer and design contract and tell the user what they are; ask for paths only when local rules or the user's instructions require specific locations.

Authorization for one consultation does not authorize a later one. A later consultation is allowed only when it stays inside a previously explicit scope and message-count budget; otherwise obtain fresh authorization first.

Prepare a compact evidence packet containing the decision, constraints, relevant excerpts, alternatives already considered, and the answer format needed. Pass that one bounded consultation to `$codex-chatgpt-consult`. Each consultation sends exactly one user message and inherits all of that skill's stop conditions.

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

## 8. Reconsult only on a boundary change

Reconsult only when a contract premise has become false or the implementation reveals a high-cost boundary change, such as:

- a public API must change;
- the data model or migration strategy must change;
- a security boundary or threat assumption changed;
- an acceptance condition is impossible or materially different; or
- the approved design cannot be implemented under the repository's constraints.

Before reconsulting, record the changed evidence, identify the exact contract section affected, and notify the user concisely. Verify that the extra send is inside the authorized scope and remaining message budget. When it is, no additional approval is required. Honor the user's new-chat or existing-chat choice again. If authorization is absent, out of scope, or exhausted, stop and obtain it. Then use `$codex-chatgpt-consult` for one message only.

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

「`$codex-pro-plan-build` を使い、外部送信してよい範囲と相談回数を先に確認し、重要設計だけ指定のWeb Proへ相談して設計契約を作り、指定したCodexモデル/effortを実表示で確認してから実装・全試験まで進めて」と依頼します。通常デバッグや小判断では再相談せず、API・データ・セキュリティ・受入条件・実装可能性の前提が崩れた時だけ、残りの送信認可を確認して再相談します。
