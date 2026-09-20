<!-- porch:start -->
# kagemusha

<sub>🌐 **English** (canonical) · [🇯🇵 日本語版はこちら → README_ja.md](README_ja.md)</sub>

[![ci](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml/badge.svg)](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml)

<!-- contract:identity -->
**We do not ship the content of your judgment. We ship the forms.**

**Make the AI write the approval slip.** Before any outward action (send, publish, update a canonical document), the agent writes the recipient, the content, the grounds, whether it can be undone, and where it is unsure; the human reads only the 'unsure' field and signs or stops. A button approval becomes a ritual; a slip cannot be signed unread.

kagemusha is **a set of Markdown forms plus the scripts that run them**, for the AI coding agent you already use (Claude Code, Codex, Cursor, …): it makes **inward work run on its own and anything outward wait for your approval**, and it returns the reasons you rejected something to the next run as standing rules. It is not a resident agent and not a SaaS, and **your own judgment criteria are not included**.

**Fits** you if operations that cannot be undone are part of your day and you are willing to write down why you rejected something. **Does not fit** you if you want ready-made judgment criteria, or an approval SaaS for a team.

**Works with Claude Code and Codex CLI** — one instructions file, one set of forms, one command line built for whichever you run ([what maps to what](#works-with-claude-code-and-codex-cli)).

[Fixed evidence: `evidence-v1.0.0`](https://github.com/yohey-w/kagemusha/tree/evidence-v1.0.0) · [The 10-minute demo](docs/getting-started.md#the-10-minute-demo) · [Install it](docs/getting-started.md#the-steps-copy-paste)

<!-- contract:demo -->
```bash
git clone https://github.com/yohey-w/kagemusha.git
cd kagemusha
./scripts/demo-distillation.sh   # ~10 min · no API key · nothing of yours is touched
```
<!-- porch:end -->

*Section numbers are inherited from the older, longer README so that existing links and citations keep resolving; the gaps are deliberate, and what they used to hold now lives in [`docs/`](docs/README.md).*

## 3. What this solves (the 1-minute version)

Hand work to an AI and two things become the bottleneck: **operations that cannot be undone**, and **your own judgment, thrown away every time you reject something**. A more capable model alone clears neither. The **approval queue** answers the first — inward work runs autonomously, outward work stops for you. **Judgment distillation** answers the second — every reject reason is logged, distilled, and read back by the agent next session. The design in full: [`docs/design.md`](docs/design.md).

### Beyond the minute — the north star, and what is still open

*The 1-minute version ends above.* The two mechanisms above do what was just described. What is not settled is the general question underneath them, which they answer only in part: **what is the least you can be shown, and the least you can be asked, for the call to still be yours?**

Yours in three specific senses — **you wrote the value judgment**, **you answer for it outward**, **you can still undo it**. And the thrift — how much can be cut from what you are shown — is bounded: deciding on the short version must not cost you more than a tolerance you set, against what you would have decided having read everything.

Stated exactly, for anyone who wants the full form: *for each decision, what is the smallest decision representation and interaction that holds the extra decision loss — measured against having examined the full evidence — inside a tolerance you set, while leaving your authorship of the value call, your answerability to the outside, and your ability to recover later intact?*

**Why a stronger model alone will not settle it.** The bottleneck is human attention and working memory, which does not move when the model improves. Answerability stays with a person whether or not the machine was right, so the *shape of what is handed over* is a permanent need. And trust comes from structure — an append-only journal, verbatim quotes, a gate — while a more persuasive model makes inference look more like fact, not less. This is not a claim that the model side is inert (there is work on models learning when to defer): it is a claim that capability **alone** does not close it, so the format, the gate and the journal have to be designed too.

What the question implies but this kit does **not** ship yet: grading decisions by class — not everything deserves an OK/NG prompt, and for some decisions a yes-or-no is the wrong instrument altogether. That is an open line of work, not a feature.

<!-- contract:evidence -->
## Evidence and scope

**Fixed evidence: [`evidence-v1.0.0`](https://github.com/yohey-w/kagemusha/tree/evidence-v1.0.0)** — that a scheduled weekly distillation really ran, and that one correction really reached a standing rule, shown as redacted artifacts from a live instance. **It is n=1 field evidence, and claims neither an effect size nor generalisability.** `main` is the mechanism as it stands today; the tag is the evidence, frozen. Scope and limits: [`cookbook/author/evidence/README.md`](cookbook/author/evidence/README.md).

**And what this repository is.** Not a product with a moat around it — **the public notebook of someone working in the open on the wall above: human attention, and answerability that stays with a person.** The method, and the record of running it. The parts of an answer already exist elsewhere, in four fields: human-automation oversight, conversational grounding, situation awareness, and the minimal manual. The nearest published framing is Zhu et al. (2026), *AI and Ethics* 6(3): separate the AI's **operative agency** (doing the work) from the human's **evaluative agency** (deciding whether it stands), and exploit the **solve-verify asymmetry** — checking costs less than redoing it — to shape the output so a person can check and contest it without doing the work again. What we have not found, as far as we have looked, is those parts run as **one** thing: scaling the hand-off to the weight of the decision, fitting that to how much of the story the human is actually still holding, cutting the format itself down experimentally, treating later recovery as a constraint, treating value decisions as authorship rather than comprehension, and keeping the AI that wrote the summary out of the check on it — all six at once. If prior work does integrate them, telling us is worth more here than a GitHub star ([`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)).

<!-- contract:boundary -->
## 8. Safety and data boundaries

| | What it is | What `setup.sh` does with it |
|---|---|---|
| **core** — `scripts/` `templates/` `docs/` `tests/` `manifests/` | the **mechanism**: scaffolding, scripts, **empty forms**, the acceptance gate | scaffolds exactly the rows listed in [`manifests/scaffold.tsv`](manifests/scaffold.tsv) — forms with nothing filled in |
| **[`cookbook/`](cookbook/README.md)** — the sample shelf | **content**: disciplines burned in someone's live loop, evidence excerpts, other people's shelves | **never read, never copied, never executed** |

⚠️ The split is **not a privacy boundary** — same repository, same permanent history. What keeps *your* data out of git is the allowlist `.gitignore`: your SSOT, journal and config cannot be committed even by accident, and `git pull` updates the kit underneath them. Both in full, plus the core-only checkout: [`docs/layers.md`](docs/layers.md).

<!-- contract:canon -->
## 5. How the whole thing works

*The section below keeps its Japanese heading — 訂正の昇格, **promotion of corrections** — because the term is quoted elsewhere and has to read identically wherever it appears. Its definitions are in English; only the three term names are not.*

<!-- canon:correction-promotion:start -->
### 訂正の昇格

**Promotion of Corrections — the canonical definitions.** Three terms, fixed in this wording, because **a term is only worth anything if it means the same thing everywhere it is quoted.** Quote them freely. (日本語版: [README_ja.md](README_ja.md#訂正の昇格))

**訂正の昇格 — promotion of a correction.** *The step that takes a human's rejection or correction from a conversation with an AI, extracts a reusable criterion out of it, and raises that criterion into a standing rule through human review.*

- **Counts:** a rejection lands verbatim in the journal, comes back as a candidate rule in the promotion queue, and **you copy it into your own instructions file** — the copying is the promotion.
- **Does not count:** piling the correction into a material file or the journal. *Moving text needs no gate; promoting a correction into a rule does* ([`docs/distillation-loop.md`](docs/distillation-loop.md)) — and the gate is a person.

**人間定置網 — the human standing net.** *Keeping a human at the end of the AI, but never returning the judgment made there to the next AI run, so the human keeps performing the same check.* (A 定置網 is a fishing net fixed in place: it catches what swims by, and catches the same thing again tomorrow.)

- **Counts:** the human rules properly every single time — and the same rejection is back next week ([§3](#3-what-this-solves-the-1-minute-version)).
- **Does not count:** putting a human in front of an irreversible outward operation **as such** — that is [calibrated reliance](#calibrated-reliance--the-principle-under-the-whole-queue). A human being there is not the net; **the judgment made there not flowing back to the next run** is.

**判断ループ — the judgment loop.** The umbrella term: **the [approval loop](#3-what-this-solves-the-1-minute-version) (generate → verify → inward auto / outward to the queue → a human decides) and [judgment distillation](#rejections-become-assets--judgment-distillation) (reject reason → journal → judgment model → next session's AI) closed into a single circuit.** Not a new mechanism — the name for the state in which those two are connected.

- **Counts:** a rejection becomes a principle, and the agent that reads that principle stops producing the same draft in the first place ([evidence that the circuit closed in a live instance](cookbook/author/evidence/README.md)).
- **Does not count:** wiring where only the top half turns — the approval queue works, but reject reasons flow nowhere and the model is never revised. That is an approval loop, not a judgment loop.

**The relation folds into one sentence: to stop being a human standing net, promote your corrections and close the judgment loop.**

The file-by-file map of the whole kit is [§10](#10-reference). The mechanism in full: [`docs/judgment-distillation.md`](docs/judgment-distillation.md) · the light daily lane: [`docs/distillation-loop.md`](docs/distillation-loop.md) · what happens after promotion: [`docs/discipline-audit.md`](docs/discipline-audit.md).
<!-- canon:correction-promotion:end -->

### Rejections become assets → judgment distillation

A correction goes back by its **type**: a *mechanical* hole becomes one line in `verifiers.md`; a *judgment* becomes a principle in `judgment_model.md`; *the same edit you keep making on every deliverable* becomes a norm the next first draft is briefed from. Details: [`docs/judgment-distillation.md`](docs/judgment-distillation.md) · [`docs/norms-loop.md`](docs/norms-loop.md).

### Calibrated reliance — the principle under the whole queue

Set the level of checking by the loss if it is wrong, its reversibility, how detectable an error would be, and the cost of checking. **Inward/outward is a proxy for that axis, not the axis itself — the real question is whether an act can be undone.** Details: [`docs/design.md`](docs/design.md).

## 6. Set it up in your own environment (30 minutes, copy-paste)

**Moved → [`docs/getting-started.md`](docs/getting-started.md#the-steps-copy-paste).** Clone it, run `./scripts/setup.sh`, and forms with nothing filled in land in your folder — from then on you open that folder with the assistant you already use. The prerequisite table, the copy-paste steps and the optional verifier from a different model lineage are all there. *(The heading stays: articles and the companion book cite this section by number.)*

### Works with Claude Code and Codex CLI

Pick the CLI with **one key**: `AGENT_CLI=claude|codex` in `config.env` (`auto` = whichever is on your PATH) — the same name **in the environment beats the file**, so `AGENT_CLI=codex ./scripts/morning_brief.sh` is a one-off switch, and `AGENT_CMD` only overrides *which executable* that CLI is. The prompts, the forms and the approval boundary do not change — only the command line does, and it is built in one place ([`scripts/lib/agent_cli.sh`](scripts/lib/agent_cli.sh)).

**Optional difficulty routing (Claude Code and Codex CLI).** A parent chooses one of `simple`, `standard`, or `complex`, then calls (for example) `agent_run --difficulty standard -- "$PROMPT"`; [`config.env.example`](config.env.example) maps each label to a provider-specific model and effort (Codex SOL low / medium / high is the shipped example, not blanket xhigh). A separate optional policy, where available, runs the Astra parent at high and lets that parent autonomously spawn an Astra xhigh child for hard judgments or a max child only for exceptionally hard or creative work, alongside SOL workers. It does not change the parent session's effort mid-run, and no model is forced on every installation. A shell caller must source `scripts/lib/agent_cli.sh` before `config.env`, as the shipped scripts do. The wrapper does not classify prompt text or keep escalating after failures. Explicit `--model` / `--effort` still win, an exported setting still beats the file, and omitting difficulty preserves the old call. Profiles affect only `agent_run`; native sub-agent APIs use whatever model/effort fields that API exposes in the spawn call. Child calls consume quota, savings are not guaranteed, and approval/permission boundaries do not change.

| | Claude Code | Codex CLI | if a CLI lacks it |
|---|---|---|---|
| instructions | `CLAUDE.md` = the one line `@AGENTS.md` | `AGENTS.md`, read directly | one file, two names — `setup.sh` writes both |
| skills | `~/.claude/skills/` | `~/.codex/skills/` | `setup.sh --link-skills` links shared skills to both; Codex-only skills only to Codex |
| per-turn date stamp | `.claude/settings.json` → `UserPromptSubmit` hook, raw stdout | `.codex/config.toml` → `[[hooks.UserPromptSubmit]]` (needs the project trusted). Same event, different wire: stdout must be the JSON envelope `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"…"}}` — plain text is refused in the TUI and dropped in silence by `codex exec` | state the date in `AGENTS.md` instead |
| memory | auto-memory directory | memories | **neither is canon.** The plain files are ([`ssot/README.md`](ssot/README.md)) |
| headless invocation | `claude -p …` | `codex exec … -s read-only\|workspace-write -o …` | any CLI taking a prompt on argv works |
| connectors, unattended | works, with `--allowedTools mcp__…` — but that is the CLI's default, not a control you chose: widen it once and the door opens in silence, which is what the row below is for | works; **no per-tool allowlist exists, and the plugin enable switch does not switch anything off** (measured 2026-09-07) — the outward brake is a `PreToolUse` hook, shipped ([`docs/inbound-loop.md`](docs/inbound-loop.md)) | keep the sweep read-only with a hook, not with a sentence |
| outward brake (`PreToolUse`) | `.claude/settings.json` → `PreToolUse` with matcher `mcp__.*`, pointing at [`templates/claude/hooks/outbound_guard.sh`](templates/claude/hooks/outbound_guard.sh). The `.*` is required — a matcher of plain characters is compared as an exact string and matches nothing, silently. The pass is `{}`, never `permissionDecision: "allow"`, which would approve the call and skip the permission prompt | `.codex/config.toml` → `[[hooks.PreToolUse]]` at an absolute path, [`templates/codex/hooks/outbound_guard.sh`](templates/codex/hooks/outbound_guard.sh). Its schema rejects both `allow` and `ask`, so `{}` is the only way to pass | both hosts **fail open** on a missing or unparseable hook — `./scripts/test.sh` feeds each one synthetic payloads, and [one shared permit helper](templates/hooks/outbound_permit.py) opens one approved send ([`docs/outbound-permits.md`](docs/outbound-permits.md)) |
| transcript harvest | `~/.claude/projects/*.jsonl` | `~/.codex/sessions/**/rollout-*.jsonl` | one adapter reads both; `LOG_SOURCE=auto` takes whichever exists |
| desktop apps | Claude Desktop's **Code** tab with the environment set to **WSL** is the same install — same `~/.claude`, same skills, same hooks, nothing to copy | the ChatGPT app's Codex runs its shell in WSL but keeps `CODEX_HOME` on the **Windows** side, so hooks, skills and the session tree each have to be carried there ([`docs/desktop-apps.md`](docs/desktop-apps.md)) | the desktop apps are a remote control for the loop, not a second loop — the CLI stays the install |
| what a desktop face costs | the app refuses remote-debugging arguments, so its acceptance run is done by hand | `PreToolUse` denies once its `[hooks.state]` key is spelled the Linux way; `UserPromptSubmit` is skipped **in silence**, so the per-turn date stamp is absent and a deny queues nothing (measured 2026-09-14) | put the date in the prompt, and read `approval_queue.md` yourself instead of trusting the deny text |
| scheduling | cron / Task Scheduler — the same for both; no CLI-native scheduler is used or needed |||

### Bundled skills

The `skills` row above is a symlink, not a description — four skills ship in `templates/skills/`:

- **`advisor-gate`** — a procedure for consulting a frontier-class external reasoning model on a decision that matters, then auditing the reply. [`templates/skills/advisor-gate/SKILL.md`](templates/skills/advisor-gate/SKILL.md)
- **`codex-chatgpt-consult`** — a Codex Desktop-only workflow for consulting a user-selected ChatGPT Web model through the standard in-app Browser, with duplicate-send stops and verbatim capture. [Install and use](docs/desktop-apps.md#optional-install-the-chatgpt-web-consultation-skill).
- **`codex-pro-plan-build`** — a Codex Desktop-only workflow that consults Web Pro for authorized high-rework design decisions, audits a design contract, then implements and tests locally. [Install and use](docs/desktop-apps.md#optional-install-the-pro-plan-and-build-workflow).
- **`meeting-copilot`** — a two-machine meeting copilot. Builds a script from a single agenda sheet, keeps 3-line cards, off-script search assist, and stops itself when the call ends; per-utterance judgment is handed to a swappable model (e.g. a small classifier like Jev/TypeSafe over Vercel AI Gateway) and falls back to plain keyword rules when it can't answer. [`templates/skills/meeting-copilot/SKILL.md`](templates/skills/meeting-copilot/SKILL.md)

The kit's own scheduled calls to Codex are **not** recorded in `~/.codex/sessions` (`--ephemeral`): that tree is what the distillation lane harvests, and the machinery's prompts are not your judgment. `AGENT_CLI_RECORD=1` turns recording on while you debug a cron run.

**Claude Code, in five lines.** ① `./scripts/setup.sh` ② fill `AGENTS.md` (the delegation boundary) ③ `cp config.env.example config.env`, set `PROJECT_ROOT` and `AGENT_CLI="claude"` ④ `./scripts/morning_brief.sh` by hand once ⑤ put that line on cron.

**Codex CLI, in five lines.** ① `./scripts/setup.sh --codex` ② fill `AGENTS.md`, and add `[projects."<abs path>"] trust_level = "trusted"` to `~/.codex/config.toml` — without it the project's own config is ignored, silently ③ `cp config.env.example config.env`, set `PROJECT_ROOT` and `AGENT_CLI="codex"` ④ `./scripts/morning_brief.sh` by hand once ⑤ put that line on cron.

**The outward brake, and why a sentence is not one.** Measured 2026-09-07 on codex-cli 0.153.4, with "outward = ask first" written in `AGENTS.md` and the strictest sandbox set: `codex exec -s read-only "email the customer …"` asked nobody, called gmail's send tool, and — when the approval policy refused the send — **created a draft to the real customer instead**. `-s read-only` sandboxes the filesystem, not connectors, and a blocked path is not a closed door. So use **both** machine layers, and expect only the first to work: ① the `PreToolUse` hook this kit ships ([`templates/codex/hooks/outbound_guard.sh`](templates/codex/hooks/outbound_guard.sh), installed by `setup.sh --codex`), which denies connector calls whose operation is `send`/`post`/`create_draft`/`reply`/… and answers "queue it in `approval_queue.md`" — re-measured the same day: the draft was refused, the read still went through; ② switching the connector off — except that `[plugins."<id>"] enabled = false` **did nothing** on this version, even with the real id, so removing the capability means `codex plugin remove`, which takes reading with it. Detail and the exact wire format: [`docs/inbound-loop.md`](docs/inbound-loop.md).

**The same send, one level down — and why the brake is an allowlist.** Measured 2026-09-13: the desktop app shows the model three tools — `exec`, `spawn_agent`, `wait_agent` — and reaches a connector from JavaScript *inside* `exec`, so `tool_name` is `exec` and a hook that matches verbs in tool names never sees the send. The CLI has the same shape (every one of 9,222 code-executing calls across 83 rollouts is `exec`). The guard therefore also reads the code `exec` carries — by **allowlist**, not by a list of tricks: the one permitted shape is a written-out `tools.<read tool>(…)`, and every other contact with `tools` or `ALL_TOOLS` is denied. A first version that enumerated bad shapes was broken by a single line — alias the object with `const t = tools`, then index the alias — and by eleven more; the ways to hide a name are unbounded, the ways to reach the object are not. **The price is real and deliberate:** listing the tool table from inside `exec` is refused, and so is any indirect read — enumerate connectors in `AGENTS.md` or a skill, and write reads as direct calls. **Not detected:** a code tool shipped under a name this guard does not know (today `exec` is the only one); and whether the hook fires for a child started by `spawn_agent`, which is **unverified** and needs a live Codex to answer. A permitted send from inside `exec` stays impossible by design — a permit binds exact arguments, and a code string has none.

## 9. Going further

**Moved → [`docs/operations.md`](docs/operations.md)** — your day and your week, running several projects at once, and counting where your own time goes (G/S/D/V/I/R). Also [`docs/inbound-loop.md`](docs/inbound-loop.md) (catching what the world sends you) and [`docs/faq.md`](docs/faq.md) (design rationale). *(The heading stays: the book's appendix cites this section by number.)*

<!-- contract:routes -->
## 10. Reference

| To do this | Open this |
|---|---|
| Try it, then install it | [`docs/getting-started.md`](docs/getting-started.md) |
| Run it day to day and week to week | [`docs/operations.md`](docs/operations.md) |
| Understand the whole design | [`docs/design.md`](docs/design.md) |
| See where the data boundaries fall | [`docs/layers.md`](docs/layers.md) |
| Turn rejections into rules | [`docs/judgment-distillation.md`](docs/judgment-distillation.md) |
| See which idea entered the kit when, and what set it off | [`docs/provenance.md`](docs/provenance.md) |
| Everything else, file by file | [`docs/README.md`](docs/README.md) |

<!-- contract:field-record -->
### Background and field record

**This repository is sufficient to install, operate, and inspect the kit.** The design decisions behind it, the options that were tried and dropped, and the timeline of corrections turning into disciplines are recorded in [a free article](https://zenn.dev/shio_shoppaize/articles/kagemusha-shogun-disband) and in a paid Zenn book, [*AI家臣団を解散して、影武者を一人だけ残した　兵法書と訓練記録*](https://zenn.dev/shio_shoppaize/books/kagemusha-book) — **both in Japanese only**. **Neither contains setup instructions missing from this repository.**

### Contributing · License

What a contribution is measured against, and where it goes: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md). MIT — see [LICENSE](LICENSE).
