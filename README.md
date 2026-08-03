# kagemusha

<sub>🌐 **English** (canonical) · [🇯🇵 日本語版はこちら → README_ja.md](README_ja.md)</sub>

[![ci](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml/badge.svg)](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml)

**Inward work runs on its own. Anything going outward stops for your approval. Even your rejections become an asset.**

Hand it your repetitive work — first-pass inbox handling, drafts, research, prep for recurring meetings — and every morning a "board" arrives: finished drafts and research, plus an approval queue you can clear from your phone in a few minutes.

You are the approver of record. The AI is your back office. Your rejection reasons are its curriculum.

**Why "kagemusha"?** A *kagemusha* (影武者) was a feudal lord's body double — acting in the lord's place within delegated bounds, but never signing in his name. That is this kit's mandate design, baked into the name: inward acts run on their own; outward acts wait for your seal. (Formerly `approval-loop` — the approval queue lives on as the mechanism's name inside.)

> **A morning with the loop.** Overnight, notifications stay silent — **but the inbound watch never stops.** At 06:53 your phone buzzes ([ntfy](https://ntfy.sh/)): today's board — 3 drafts and 1 research memo the loop finished yesterday, 2 requests that landed overnight, 2 items waiting in the approval queue.
> Coffee in hand, you answer from your phone: YES, YES, NO — "too pushy for this client." Two minutes.
> That NO, verbatim, is appended to the decisions journal.
> On Sunday night the weekly distiller turns it into a principle in the judgment model.
> The agent reads that model every session — the same rejection never comes back.

Start with one paste:

```bash
git clone https://github.com/yohey-w/kagemusha && cd kagemusha && ./scripts/setup.sh
```

Then open the folder with your AI assistant (Claude Code / Codex / any) — details in [Quickstart](#3-quickstart-30-minutes-copy-paste).

> 📖 Background article (Japanese, Zenn): **[Loop engineering isn't just for engineers anymore — running it on real work, the fourth thing you have to design turned out to be "mandate" (authority)](https://zenn.dev/shio_shoppaize/articles/loop-mandate-design)**

---

## 1. What this solves (the 1-minute version)

Hand a slice of your work to an AI and two things immediately become the bottleneck — neither of them the model's raw capability:

1. **Approval.** Some operations can't be undone. A sent chat can't be unsent; a published page is public. **At work, the "send failure" costs far more than the "generation failure."** You cannot let the agent fire those on its own — but gating *everything* makes you the bottleneck.
2. **Judgment criteria.** Once approvals flow, *you* become the loop's slowest part: you keep making the same calls by hand — reject this tone, fix that number, no source no claim. That judgment is an asset, and it's being thrown away every time you click "reject."

kagemusha answers both:

- **The receiving side — the approval queue.** Split every operation in two. **Inward** (drafting, analysis, tidying, local edits) → the agent does autonomously. **Outward** (sending, publishing, mutating the source of truth) → the agent does *not* execute; it appends one entry to an **approval queue** and moves on. You clear the queue a few times a day. Autonomous speed *and* zero un-undoable mistakes.
- **The feedback side — judgment distillation.** Every rejection/correction, with its reason, gets logged and periodically distilled into a thin **value-judgment model** the agent reads each session — so it pre-judges the way you would, and fewer weak drafts ever reach the queue. Your day shifts from *doing the work* to *improving the loop.*

That's the whole thesis: **the approval queue makes it safe; judgment distillation makes it smarter over time.**

---

## What you actually need

The mechanism is **files and discipline** — a harness-agnostic core. The prerequisites are additive: the minimal setup needs exactly one thing — a folder plus an assistant that can touch it. Each level of automation and each listening channel adds exactly one more:

| What you want to run | Prerequisites (additive) |
|---|---|
| Minimal: approval queue + SSOT + journal, run by hand | A folder of Markdown files + one AI assistant **that can read/write files in that folder** (Claude Code CLI or desktop, Codex CLI, Cursor, …). ⚠️ A plain chat window with no file access does **not** qualify — this is the most-missed hidden prerequisite. |
| Morning board / weekly distill, semi-automatic | + any nudge (a calendar reminder is enough) |
| Same, fully automatic | + a headlessly-launchable CLI + a scheduler (cron on Linux/macOS, Task Scheduler on Windows; macOS can also use the native launchd) — for one reason only: a scheduler cannot click a GUI |
| Inbound catch, Tier 1 (recommended) | + MCP connectors for your channels (Gmail / Slack / Notion) connected in your client — OAuth handled by the platform. Availability varies by plan and client. |
| Inbound catch, fully automatic (the Tier 2 script) | + channel credentials (Slack bot token / Gmail app password) — because an interactively-authenticated MCP session may be unavailable under an unattended scheduler |
| Approving from your phone | + a push channel ([ntfy](https://ntfy.sh/) or similar, free) |

**Three ways to kick off the weekly run** — all three are fine: **fully automatic** (the scheduler launches an AI *CLI* — the only mode that needs a CLI), **semi-automatic** (the scheduler just *notifies* you; you paste the weekly prompt into a desktop or web chat), or **manual** (on a fixed weekday, you simply ask your AI yourself — make it a small ritual).

In this mechanism a human has to approve principle revisions anyway (the weekly distiller *proposes*; new principles wait for your OK). So a human doing the kick-off is **not a failure of automation** — the approval and the kick-off just collapse into the same single tap.

(Those three are about *who* kicks off the same OS-scheduled run — a separate question from *which* loop mechanism to use at all. An OS scheduler, an agent's own built-in loop (e.g. Claude Code's `/loop`), and a schedule run by the coding agent's own service or app are not interchangeable — they differ in who holds the clock and whether the job can reach your local files. Comparison: [`docs/inbound-loop.md`](docs/inbound-loop.md).)

That's it. The `scripts/` in this repo are a **convenience layer** (headless automation, log mining, budget lints), not a prerequisite. Delete them and the loop still runs: the core is the Markdown files plus the discipline of *inward = auto / outward = approval queue*. A CLI + a scheduler is just the example wiring — a desktop app + a weekly calendar nudge is equally valid.

---

## 2. Architecture (the whole loop)

```mermaid
graph TD
    T1["time trigger<br/>(morning / weekly)"] --> GEN
    T2["inbox trigger<br/>(a request lands)"] --> GEN
    W["inbound watch<br/>(mail · chat · RSS …)"] -.-> T2
    subgraph LOOP["the agent's loop"]
        GEN["generate<br/>(draft · research · tidy)<br/>+ pre-judge using the model"] --> VER["machine verify<br/>(lint · SSOT cross-check)"]
        VER -->|"fail"| GEN
    end
    VER -->|"pass"| BR{"outward<br/>operation?"}
    BR -->|"inward"| AUTO["auto-run<br/>(local only)"]
    BR -->|"outward<br/>(send · publish · mutate SSOT)"| Q["approval queue"]
    Q --> HUMAN["human: approve / edit / reject"]
    HUMAN -->|"approve"| OUT["out into the world<br/>(no undo)"]

    HUMAN -->|"reject / edit<br/>(reason, verbatim)"| J["decisions journal<br/>(append-only events)"]
    MINE["mine conversation logs"] -.->|"catch corrections that<br/>never hit the queue"| J
    J -->|"weekly distill"| M["judgment model<br/>(thin canon ≤160 lines)"]
    M -.->|"injected each session"| GEN
    CH["project charter<br/>(per-project deltas)"] -.->|"read before<br/>project work"| GEN

    classDef feedback fill:#eef,stroke:#88a;
    class J,MINE,M feedback;
    classDef ctx fill:#efe,stroke:#8a8;
    class CH ctx;
```

The top half is the **approval loop** (mandate): generate → verify → inward auto / outward to the queue → a human decides. The bottom half (shaded) is **judgment distillation** (the feedback arm): the human's reject/edit reasons flow into an append-only **journal**, a weekly job **distills** them into the **judgment model**, and that model is injected back so the agent pre-judges — closing the loop. A finished agent *product* is someone else's frozen trigger/verifier/stop-rule/mandate; here you design and **evolve your own criteria**.

### Catching the world's input — the three loops

The diagram has two triggers. The **time trigger** (T1) ships as `morning_brief.sh` / `weekly_distill.sh.example`. The **inbox trigger** (T2) is a loop of its own — an **inbound watch** that polls the channels where work lands on you (mail, chat, SNS mentions, blog reactions), classifies each new item with a closed enum, holds the night's noise for one morning roll-up, and appends every detection to an immutable ledger so nothing dies silently. Connect your Gmail / Slack via your assistant's connectors and run the sweep procedure ([`templates/inbound_sweep.md`](templates/inbound_sweep.md)) — the script ([`scripts/inbound_watch.sh.example`](scripts/inbound_watch.sh.example)) is only for unattended scheduler runs. Three loops, one system: **inbound catch** (the world → you) → **work loop** (generate → verify → queue) → **judgment feedback** (your rejections → the model). Design + setup: [`docs/inbound-loop.md`](docs/inbound-loop.md).

---

## 3. Quickstart (30 minutes, copy-paste)

**Prerequisites** (for this scripted path only — the loop itself needs just the three things above)**:** `bash`; one AI CLI that runs a prompt non-interactively (default is the [Claude CLI](https://code.claude.com/), swappable to Codex/Gemini/etc.); optionally [ntfy.sh](https://ntfy.sh/) for phone notifications; Python 3 (only for the distillation scripts). Prefer not to script it? Skip to the semi-automatic / manual kick-off above and just paste the prompts into any assistant.

**Installing an AI CLI (if you don't have one).** Any agentic CLI works; the two most common:

- **Claude Code** (Anthropic): native installer is the recommended path — `curl -fsSL https://claude.ai/install.sh | bash` (macOS/Linux/WSL; Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`), then run `claude` once to sign in ([docs](https://code.claude.com/docs/en/setup); npm install also works). Its per-directory instructions file is `CLAUDE.md` — which `setup.sh` creates for you.
- **Codex CLI** (OpenAI, GPT models): `npm install -g @openai/codex`, then run `codex` once to sign in with your ChatGPT account ([repo](https://github.com/openai/codex)). Its instructions file is `AGENTS.md` — rename the generated `CLAUDE.md` to `AGENTS.md` and you're done.

The instructions themselves (`templates/agent_instructions.md`) are tool-agnostic; `setup.sh` just saves them under the filename your tool reads.

```bash
# 1. Scaffold (5 min) — clone, then scaffold INTO the clone and live in it.
#    The allowlist .gitignore means your SSOT / journal / config can never be
#    committed, and `git pull` updates the kit without touching your data.
#    Never clobbers existing files. (Prefer a separate dir? ./scripts/setup.sh ~/work-loop)
git clone https://github.com/yohey-w/kagemusha.git
cd kagemusha
./scripts/setup.sh

# 2. Fill the source of truth (15 min) — the one part a machine can't do.
#    Edit ssot/{decisions,tasks,glossary,people}.md — a few real entries each.
#    (tasks.md: always include a "source" column so nothing is "he-said / she-said".)

# 3. Wire the time trigger (5 min).
cp config.env.example config.env      # git-ignored; holds your paths + notify topic
$EDITOR config.env                    # set PROJECT_ROOT / AGENT_CMD / NTFY_TOPIC
./scripts/morning_brief.sh            # run once by hand (read-only, ~a few minutes)

# 4. Put it on cron (or Windows Task Scheduler → docs/windows.md, or a daily
#    calendar reminder to run it by hand — any OS scheduler is equivalent;
#    other loop mechanisms are not, see docs/inbound-loop.md).
#    53 6 * * *  /path/to/kagemusha/scripts/morning_brief.sh
```

Each morning a one-page board arrives; anything outward is stacked in `approval_queue.md`; you approve / edit / reject. **Add one rule to `verifiers.md` and it applies to every future output.**

**Then, once the loop is running, turn on the feedback side (optional):**

```bash
# 5. Seed a few of your own principles in judgment/judgment_model.md
# 6. Copy the weekly distiller and edit its CONFIG block:
cp scripts/weekly_distill.sh.example scripts/weekly_distill.sh && $EDITOR scripts/weekly_distill.sh
# 7. Cron it weekly (proposes changes; new principles wait for your OK):
#    17 21 * * 0  /path/to/kagemusha/scripts/weekly_distill.sh
```

See [`docs/judgment-distillation.md`](docs/judgment-distillation.md) for how it works.

**Optional but recommended: a verifier from a different model lineage.** This kit is built around the assumption that AI output can be wrong — that's the whole reason the approval queue and the verifiers exist. But there's a blind spot: if the model that checks the work shares a lineage with the model that did the work, a failure mode common to that lineage slips past both. (Research on inference-time scaling reports a pattern — getting pulled off track by irrelevant context the longer a model reasons — that shows up across a model *family*, not just one model: [Inverse Scaling in Test-Time Compute](https://arxiv.org/abs/2507.14417).) So it's worth wiring in one checker from a different vendor.

- **What:** the [Codex plugin for Claude Code](https://github.com/openai/codex-plugin-cc) — an official plugin that calls OpenAI's Codex CLI from inside Claude Code — plus the Codex CLI itself and an OpenAI-side login. Its usage quota is billed separately from Claude usage, so reaching for it doesn't eat into your main work's budget.
- **When to reach for it:** (1) a second diagnosis when you're stuck, (2) designing a fix for your *own* blind spot — don't ask the side that has the blind spot to design around it, (3) an independent check before a big publish or delivery. Having it review this kit's own verifiers, or a distilled change to the judgment model, is the typical case.
- **How to install** (verified against the plugin's own README):

  ```bash
  # inside Claude Code
  /plugin marketplace add openai/codex-plugin-cc
  /plugin install codex@openai-codex
  /reload-plugins
  /codex:setup   # checks whether Codex is ready; can install/log you in if not
  ```

  Requires a ChatGPT subscription (Free tier included) or an OpenAI API key, and Node.js 18.18+. Full requirements and usage: the plugin's own [README](https://github.com/openai/codex-plugin-cc).

---

## 4. What's in the box

| Path | Role |
|---|---|
| **`templates/decisions.md`** | SSOT — what's decided (and what's been superseded). Append-only, event-sourced. |
| **`templates/tasks.md`** | SSOT — who owes what, by when, and where it came from. |
| **`templates/glossary.md`** / **`people.md`** | SSOT — canonical terms and named people (for wording lints & addressee checks). |
| **`templates/approval_queue.md`** | The queue outward operations pile into. Has a **"doubt" field** so review takes seconds. |
| **`templates/verifiers.md`** | Standing verifiers — a machine layer of lints + deliverable-type Definitions of Done. |
| **`templates/decisions_journal.md`** | **Judgment journal (L2)** — append-only log of rulings/corrections/rejections, with verbatim quotes. |
| **`templates/judgment_model.md`** | **Value-judgment model (L1)** — the thin canon (≤160 lines) the agent reads each session. |
| **`templates/system_map.md`** | **System map** — the one-screen board (standing mechanisms + one card per project + roadmap). Scaffolds to the instance root. |
| **`templates/charter.md`** | **Project charter** — per-project *deltas* only (≤60 lines); the judgment model itself never splits. Copy into `projects/<name>/charter.md`. |
| **`templates/agent_instructions.md`** | **The instance constitution** — saved as `CLAUDE.md` (Claude Code) / `AGENTS.md` (Codex) / your tool's rules file. |
| **`templates/starter-disciplines.md`** | **Starter disciplines** — a *menu, not a template* (deliberately **not** scaffolded by `setup.sh`): disciplines burned in the author's live instance, each with the burn it came from, a portability label, and a paste target. Take only the ones whose hole you've already fallen into. |
| **`templates/inbound_sweep.md`** | **Inbound sweep procedure (Tier 1)** — the inbox trigger run through your assistant's MCP connectors: lanes, closed-enum triage, append-only ledger, quiet hours. |
| `.gitignore` | Allowlist — only the kit is tracked, so your instance data can never be committed. |
| `scripts/setup.sh` | Scaffold all of the above into the clone itself (default) or a target dir (safe to re-run). |
| `scripts/morning_brief.sh` | The time trigger — an inward-only, read-only morning stock-take. |
| **`scripts/mine_conversations.py`** | Extract the approver's own turns from AI-CLI logs (rulings/corrections). |
| **`scripts/filter_judgments.py`** | Bucket those turns into RULE/REJECT/CORRECT/… (vocab configurable, EN+JP defaults). |
| **`scripts/weekly_distill.sh.example`** | The weekly feedback trigger — mine → journal → distill into the model (proposes; you confirm). |
| **`scripts/inbound_watch.sh.example`** | The inbox trigger, Tier 2 — inward-only inbound watch for unattended scheduler runs (Slack / Gmail-IMAP / RSS lanes; immutable ledger; quiet-hours roll-up). |
| `scripts/test.sh` | The kit's own acceptance gate — run `./scripts/test.sh` (needs `shellcheck`); CI runs this exact command. It really executes `setup.sh` in a throwaway clone, proves the allowlist `.gitignore` makes instance data uncommittable, and drives `morning_brief.sh` with a fake CLI. No skips: a missing tool is a failure. |
| `docs/design.md` | Implementation guide: the four parts + mandate, mapped to files. |
| **`docs/judgment-distillation.md`** | The feedback side in full: 4 layers, 8 triggers, event sourcing, the weekly 7-step, three-layer change governance. |
| **`docs/inbound-loop.md`** | The inbound-watch loop: lanes & cadences, quiet hours, the immutable ledger, injection defense, the batch-level baseline lesson, Tier 1 / Tier 2. |
| **`docs/decision-cards.md`** | Decision cards — cognitive design of the approval hand-off: the artifact itself, one recommendation, a no-answer default, severity marks, ≤3 per batch. |
| `docs/windows.md` / `docs/faq.md` | Task Scheduler alternative; FAQ. |
| **`evidence/`** | **Proof the loop actually runs** — hand-redacted excerpts from the author's live instance: one unattended weekly-distillation run, and the two dated journal entries that bracket a correction ending up as a rewritten principle in the judgment model. Scope and limits stated in [`evidence/README.md`](evidence/README.md). |

---

## 5. The four-layer equation

| Layer | The question | The answer at work |
|---|---|---|
| Context | What does it know? | **SSOT** (`decisions` / `tasks` / `glossary` / `people`) |
| Harness | What can it do? | CLIs, scripts, file ops |
| Loop | When does it act, how is it checked? | triggers (time / inbox) + verifiers |
| **Mandate** | **How far is it trusted; who is accountable?** | **reversible = auto / irreversible = approval queue** (proxy: inward / outward) |

The first three are "how to make it run"; only the fourth is "how far to trust it." Out of the lab and into real work, the fourth is what actually bites. Put in workplace words, the parts are all old ideas: **trigger = the setup, verifier = the checklist, stop rule = the deadline, mandate = sign-off authority.** The agent writes the code; drawing the loop's blueprint stays — given current capability, authority, and risk thresholds — with the person who knows the work best.

---

## 6. Rejections become assets → judgment distillation

The highest-leverage field in the approval queue is **"doubt"**: the agent declares *where to look to make the ship/no-ship call*, so you don't re-read every draft in full. Queue-clearing drops to tens of seconds an item.

Then there's a second level. **The reasons you reject or edit are the most valuable log you produce** — and there are two things to distill them into:

- **Into `verifiers.md`** — when a rejection is a *mechanical* hole (wrong weekday, missing addressee, unverified number), add one verifier and the whole class of error dies in the machine layer. You never give the same note twice.
- **Into `judgment_model.md`** — when a rejection is a *judgment* ("that tone is wrong", "price from hours not vibes"), distill it into a principle in the thin value-judgment model. The agent reads it next session and pre-judges — so that draft never reaches the queue.

Why corrections matter most: a *ruling* (which option to pick) is something a model eventually predicts on its own; a *correction* (you overruling its output) is the **delta between the model and you**, and that signal doesn't go stale. This is the part a finished agent product — someone else's frozen criteria — can never have: **it doesn't learn *your* judgment.** Full mechanism: [`docs/judgment-distillation.md`](docs/judgment-distillation.md). **Proof this circuit actually closed — an unattended distillation run and the journal entries behind one principle in this repo:** [`evidence/`](evidence/README.md).

---

## This kit grows — and that is the design, not a slogan

§6 is about your rejections becoming your assets. The same circuit runs one level up, on the kit itself.

- **From the author's live instance.** This repository is not written *about* a loop; it is written *from inside* one. The author runs it on real work daily, and the weekly distiller turns that week's rejections into principles. Whatever survives having the client, the profession, and the environment stripped off comes back here as a change to the templates and docs.
- **From yours.** A discipline only one person has been burned by is n=1. The second person to report the same hole is what turns it into something worth shipping — so issues and PRs are the other inflow, especially "this rule didn't transfer to my setup, and here's what broke."

Why growth is structural rather than a promise: **append-only artifacts accrete; snapshots rot.** A frozen best-practices document is a snapshot — stale the moment your work moves — which is exactly why §6 sends your rejections to an append-only journal instead of a rewrite. The author's long-form writing on this material is split along the same seam: the theory half is *revised* and carries a freshness date, the practice half is *appended to*.

The first thing shipped out of that inflow is **[`templates/starter-disciplines.md`](templates/starter-disciplines.md)** — a **menu, not a template**, and deliberately not scaffolded. Each discipline carries the burn it came from, a **portability label** (*works standalone* / *needs a mechanism, stated* / *take the shape, the content is yours to burn*), and a **paste target**. Two rules govern it: **take only the ones whose hole you have already fallen into** — an unearned rule is noise, and borrowed principles eat the same ≤32-principle budget as the ones you earn — and **only the physics of working with an AI qualifies.** Disciplines belonging to your profession can be burned only from your own rejections, and their home is your own judgment model.

---

Want to contribute a discipline forged in your own loop? There are **two lanes**, and they are judged by different things — see [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md).

- **The kit itself** (`templates/starter-disciplines.md`, docs, formats) — **a maintainer rules on it**, against the same four axes the file's own `## 増やし方` states: burned from a real rejection, the proposition survives having the profession stripped off, "delete this line — does the agent then get it wrong?", and the entry metadata (portability label / paste target / burn origin). No automation merges here.
- **Your own shelf** — [`community/<your GitHub login>/`](community/README.md), for what the curated gate throws away on purpose: disciplines that are specific to your environment, and disciplines that belong to your profession. A PR touching only your directory and passing a mechanical format lint is **auto-approved and squash-merged with nobody reading it** — which is exactly why [`community/README.md`](community/README.md) is about where the responsibility sits, and why it stays in the git history whatever you delete later.

## 7. Running multiple projects — charters, the system map, and living in the clone

Run the loop on more than one client or project and two structures earn their keep (both scaffolded by `setup.sh`):

- **One charter per project — but the personality stays singular.** Should the judgment model be split per project? No. Corrections are the loop's most valuable signal (§6); split the model per project and that signal scatters into thin, separate streams. What differs per project is not the principles but *how they apply*. So the judgment model stays one file, and each project gets a **charter** (`projects/<name>/charter.md`, ≤60 lines) holding only the *deltas*: the counterpart's decision style, the delegation boundary for this project, pricing discipline, communication register, and which principles bite harder or take exceptions here. Never copy a principle's text into a charter — the same proposition in two places means a correction reaches only one, and the other rots. The agent reads the charter before any work on that project.
- **A one-screen system map** (`system_map.md`, at the instance root — the hottest file gets the shortest path): standing mechanisms (what runs, why, how to stop it), one card per project (status / our next move / waiting on them / deadline), and a one-line roadmap. Status lives in the map, never in charters — **charters carry judgment deltas, the map carries state.**

And you run all of it **directly inside the clone**. The allowlist `.gitignore` tracks only the kit (marked ✓ below); everything you create is untrackable by construction, and `git pull` upgrades the kit under your data. This kills the classic failure of copying a kit out into a separate dir and drifting from upstream:

```text
kagemusha/                     ← your clone = your instance
├── README.md  docs/  scripts/  templates/  evidence/  community/  ✓ tracked (the kit)
├── CLAUDE.md (or AGENTS.md)      agent instructions — the instance constitution
├── system_map.md                 the one-screen board
├── approval_queue.md             the queue outward operations pile into
├── verifiers.md                  standing verifiers
├── ssot/                         current truth (overwritten in place)
├── judgment/                     append-only past (journal + judgment model)
├── projects/
│   ├── <name>/charter.md         per-project deltas (one folder per map card)
│   └── _archive/                 retired projects (mv, don't delete)
├── briefs/  logs/  local/        daily boards · run logs · machine-local scripts & secrets
```

Five invariants drive this layout: **card = folder = charter (1:1:1)** — one map card ↔ one `projects/<name>/` ↔ one `charter.md` inside it, so drift is lintable; **state vs history** — `ssot/` is overwritten truth, the journal is append-only past; **the personality is singular** — `judgment/` never splits per project; **the hottest file gets the shortest path** — the map sits at the root; **archive = one folder move** — retiring a project is `mv projects/<name> projects/_archive/`, and its charter travels with it. Rationale in [`docs/design.md`](docs/design.md).

---

## 8. Calibrated reliance — the principle under the whole queue

Why gate outward operations at all? Because of one quiet failure mode: **the fact that an AI produced something is not evidence that it's correct.** Fluency and a confident tone are not proof. The approval queue is only the operational form of a deeper rule this kit adopts (arrived at through outside audit of the design):

> **Short form.** The fact that an AI produced it is not evidence that it's right. Before you use an output as an answer, put it through verification proportional to its use.

The full form spells out *how much* verification:

> Don't treat an LLM's output as correct on the strength of fluency or a decisive tone alone. For each output, set the level of checking by the loss if it's wrong, its reversibility, how detectable an error would be, and the cost of checking — then verify with independent sources, deterministic tests, experiments, a separate line of evaluation, or expert human judgment. For low-risk, reversible uses, a sample audit or after-the-fact monitoring can be enough; for high-risk or irreversible uses, require independent verification *before* execution. The goal is not to distrust AI at all times, but to design the *right* reliance — adopt the correct outputs, reject the wrong ones.

This is exactly why the split is **inward = auto / outward = approval queue.** Inward operations are reversible and low-loss, so a sample audit after the fact is enough; outward operations are often irreversible and high-loss, so they get independent verification *before* they fire. The queue is calibrated reliance applied to the one axis that bites hardest at work — whether an action can be undone.

**Which means inward/outward is a proxy, not the axis itself.** In practice it misfires in exactly two places: **reversible-outward** (a push that leaves history and can be reverted — gating each one buys no safety and makes you the bottleneck) and **irreversible-inward** (a local-only data operation with no way back). Use the proxy where it's convenient; in those two places, re-decide on the real axis — **can this be undone?** (See [`docs/design.md`](docs/design.md) and P1 of [`templates/judgment_model.md`](templates/judgment_model.md).)

---

## 9. Count your work — where does your time actually go? (G/S/D/V/I/R)

The loop's promise is that your day shifts *from doing the work to improving the loop* (§1). That's a claim about **where your time goes** — so make it measurable. Tag each slice of your own effort with one of six letters:

| Tag | Kind of work | What it means |
|---|---|---|
| **G** | Generate | You produce the first substantive draft or candidate. |
| **S** | Specify | You set the goal, the question, the constraints, the context. |
| **D** | Dispose | You accept, reject, partially select, or order a fix. |
| **V** | Verify | You test, fact-check, run an experiment, measure the result. |
| **I** | Integrate | You wire it into a system or the real workplace. |
| **R** | Relate | You persuade, negotiate, reach agreement, share accountability. |

The bet behind the approval loop is that, on repetitive work where candidates are cheap to generate and outputs are cheap to evaluate, the share of **G** falls and the share of **D + V** rises — you spend less time *making the first draft* and more time *disposing of and verifying* the agent's. This codebook lets you check that against your own logs instead of taking it on faith.

One rule keeps the count honest: **S, V, I, and R do not count as D (disposal / judgment).** Specifying, verifying, integrating, and relating are each their own work; folding them into "judgment" inflates the disposal bucket and blurs where your time really went.

---

## 10. FAQ (design Q&A)

**Q. Why are rejections/corrections the "highest-value log"?**
Because a ruling is predictable and a correction is not. Models get better at guessing which option you'll pick; they do not get better, on their own, at the exact places where *your* judgment diverges from theirs — that's what a correction marks. Mine your own logs and corrections outnumber clean rulings, yet the queue discards them the instant you click reject. Distillation captures that delta before it evaporates.

**Q. Why build principles only from things the approver actually said?**
The classic failure is promoting *your guess about the approver's reasoning* into a principle — it then silently biases every later call, and no one notices. So a principle is promoted only if a **verbatim quote** can be cited from the journal. Inferences stay tagged `[working hypothesis]` in the journal until the approver confirms them. Real utterances only; guesses stay quarantined.

**Q. Why cap the judgment model at ~160 lines / ~32 principles?**
Adherence, not aesthetics. Long instruction files stop being followed — the head is read, the tail ignored, and auto-bloated instructions can *lower* accuracy. So the one file injected every session is kept deliberately thin, and a machine lint enforces the budget. Want to add a principle past the cap? Merge or retire an old one first. **The cap is a cost, not a moat — the thinness is the point.** (Both limits are configurable in `weekly_distill.sh`.)

**Q. How is this different from HITL (human-in-the-loop)?**
HITL is the *mechanism* ("put a human in the loop"); this kit is the *design* — *where* to insert the human, *what* to make the agent declare (basis, undo-ability, doubt), *how* to turn rejections into assets, and *how* to widen trust over time. Having a stop button and designing when to stop are different things.

**Q. Does the weekly distillation rewrite my judgment model unattended?**
No — it proposes. Reinforcing an existing principle (adding a citation) is applied directly; a **new** principle or a **contradiction** is written to a `*_pending.md` file for you to confirm. An unattended rewrite of the model that governs the agent's calls is exactly the kind of un-undoable change this whole kit exists to gate.

**Q. Can I use a CLI other than Claude?**
Yes. Swap `AGENT_CMD` / `AGENT_MODEL` / `AGENT_FLAGS` in `config.env` and edit the one invocation line at the "CLI-SWAP POINT" comment in the scripts. Any CLI that takes a prompt on argv and runs non-interactively works (Codex, Gemini, …). Prompts and SSOT formats are model-agnostic.

More in [`docs/faq.md`](docs/faq.md).

---

## Related & prior work

This layer already has good pioneers; this kit owes them a lot.

- **[humanlayer](https://github.com/humanlayer/humanlayer)** — the standout approval layer that interposes human approval on an agent's high-risk operations, as an SDK, over Slack/email.
- **[CoWork OS](https://github.com/CoWork-OS/CoWork-OS)** / **[AgentOS (Agno)](https://github.com/agno-agi/agno)** — OS layers for work agents with approval gates and execution visibility.
- **[ACE (Agentic Context Engineering)](https://arxiv.org/abs/2510.04618)** — research on incrementally updating a playbook from execution traces (Generator / Reflector / Curator).
- **[ZOZO's weekly rules-update practice](https://zenn.dev/zozotech/articles/20260423_pr_review_claude_rules)** — collecting and distilling PR-review comments weekly into agent rules (humans review adoption). The same loop as our "distilling rejections," run in the code-review world.

This kit's one differentiator: **it treats the human's judgment log (the queue's reject/edit reasons) as a first-class input, and runs non-code work on plain markdown alone.**

---

## Genealogy (same author, prior work)

- **[multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun)** — parallel orchestration; topology design across many agents.
- **[CoDD (codd-dev)](https://github.com/yohey-w/codd-dev)** — deliverable verification ("consistency-driven development"); the "prevent false success" idea. This kit's verifiers are its work-world version.

Third in the series: orchestration (who acts) → verification (is it right) → **mandate (how far to trust)**.

---

## License

MIT. See [LICENSE](LICENSE).
