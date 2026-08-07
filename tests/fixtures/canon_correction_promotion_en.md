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
