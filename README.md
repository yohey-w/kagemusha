<!-- porch:start -->
# kagemusha

<sub>🌐 **English** (canonical) · [🇯🇵 日本語版はこちら → README_ja.md](README_ja.md)</sub>

[![ci](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml/badge.svg)](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml)

<!-- contract:identity -->
**We do not ship the content of your judgment. We ship the forms.**

kagemusha is a kit that ships, as Markdown forms plus scripts, an AI agent's **"inward runs on its own / outward waits for human approval"** rule and the loop that returns your rejection reasons to the next run as standing rules. It is not a resident agent and not a SaaS, and **your own judgment criteria are not included**.

**Fits** you if operations that cannot be undone are part of your day and you are willing to write down why you rejected something. **Does not fit** you if you want ready-made judgment criteria, or an approval SaaS for a team.

[Fixed evidence: `evidence-v1.0.0`](https://github.com/yohey-w/kagemusha/tree/evidence-v1.0.0) · [The 10-minute demo](docs/getting-started.md#the-10-minute-demo) · [Install it](docs/getting-started.md#the-steps-copy-paste)

<!-- contract:demo -->
```bash
git clone https://github.com/yohey-w/kagemusha.git
cd kagemusha
./scripts/demo-distillation.sh   # ~10 min · no API key · nothing of yours is touched
```
<!-- porch:end -->

## 3. What this solves (the 1-minute version)

Hand work to an AI and two things become the bottleneck, neither of them the model's capability: **operations that cannot be undone**, and **your own judgment, thrown away every time you click reject**. The **approval queue** answers the first — inward work runs autonomously, outward work stops for you. **Judgment distillation** answers the second — every reject reason is logged, distilled, and read back by the agent next session. The design in full: [`docs/design.md`](docs/design.md).

<!-- contract:evidence -->
## Evidence and scope

**Fixed evidence: [`evidence-v1.0.0`](https://github.com/yohey-w/kagemusha/tree/evidence-v1.0.0)** — that a scheduled weekly distillation really ran, and that one correction really reached a standing rule, shown as redacted artifacts from a live instance. **It is n=1 field evidence, and claims neither an effect size nor generalisability.** `main` is the mechanism as it stands today; the tag is the evidence, frozen. Scope and limits: [`cookbook/author/evidence/README.md`](cookbook/author/evidence/README.md).

<!-- contract:boundary -->
## 8. Safety and data boundaries

| | What it is | What `setup.sh` does with it |
|---|---|---|
| **core** — `scripts/` `templates/` `docs/` `tests/` `manifests/` | the **mechanism**: scaffolding, scripts, **empty forms**, the acceptance gate | scaffolds exactly the rows listed in [`manifests/scaffold.tsv`](manifests/scaffold.tsv) — forms with nothing filled in |
| **[`cookbook/`](cookbook/README.md)** — the sample shelf | **content**: disciplines burned in someone's live loop, evidence excerpts, other people's shelves | **never read, never copied, never executed** |

⚠️ The split is **not a privacy boundary** — same repository, same permanent history. What keeps *your* data out of git is the allowlist `.gitignore`: your SSOT, journal and config cannot be committed even by accident, and `git pull` updates the kit underneath them. Both in full, plus the core-only checkout: [`docs/layers.md`](docs/layers.md).

<!-- contract:canon -->
## 5. How the whole thing works

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

Moved → [`docs/getting-started.md`](docs/getting-started.md#the-steps-copy-paste) — the prerequisite table, the copy-paste steps, and the optional verifier from a different model lineage.

## 9. Going further

Moved → [`docs/operations.md`](docs/operations.md) (your day and your week, multiple projects, counting your own work G/S/D/V/I/R) · [`docs/inbound-loop.md`](docs/inbound-loop.md) (catching what the world sends you) · [`docs/faq.md`](docs/faq.md) (design rationale).

<!-- contract:routes -->
## 10. Reference

| To do this | Open this |
|---|---|
| Try it, then install it | [`docs/getting-started.md`](docs/getting-started.md) |
| Run it day to day and week to week | [`docs/operations.md`](docs/operations.md) |
| Understand the whole design | [`docs/design.md`](docs/design.md) |
| See where the data boundaries fall | [`docs/layers.md`](docs/layers.md) |
| Turn rejections into rules | [`docs/judgment-distillation.md`](docs/judgment-distillation.md) |
| Everything else, file by file | [`docs/README.md`](docs/README.md) |

<!-- contract:field-record -->
### Background and field record

This repository is sufficient to install, operate, and inspect the kit. The design decisions behind it, the options that were tried and dropped, and the timeline of corrections turning into disciplines are recorded in [a free article](https://zenn.dev/shio_shoppaize/articles/kagemusha-shogun-disband) (Japanese) and in the paid Zenn book [*AI家臣団を解散して、影武者を一人だけ残した　兵法書と訓練記録*](https://zenn.dev/shio_shoppaize/books/kagemusha-book). Neither contains setup instructions missing from this repository.

### Contributing · License

What a contribution is measured against, and where it goes: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md). MIT — see [LICENSE](LICENSE).
