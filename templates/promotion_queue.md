# promotion queue — candidate rules waiting on your review

Machine-written, human-emptied. `scripts/distill.sh` appends one dated section per run; nothing here governs anything until **you** copy it into your agent instructions, your verifier checklist, or your journal. That copy is the promotion, and it is the one step in this loop that is not automated on purpose — a rule that promoted itself would be a rule nobody reviewed, and it would govern every run after it, including the one that wrote it.

**How to work this file** (five minutes, once a week):

1. Read a candidate's **evidence** first, not its rule line. The rule line is the distiller's wording; the quote is what actually happened. If the quote does not support the rule, the candidate is wrong no matter how good the sentence is.
2. Decide one of four things and write it on the candidate: **promote** (say where you pasted it) / **park** (worth watching; write down what would make it a yes) / **drop** (and one word why) / **rewrite** (the idea is right, the wording is not).
3. **Promote sparingly.** Every rule you adopt eats the same budget as one you wrote yourself, and a long instruction file stops being obeyed — the head gets read and the tail ignored. Adding the eleventh rule usually costs you one of the first ten. If you cannot name the incident that earned a rule, it is not yours yet.
4. **Prefer trace form.** "Never assert what you haven't checked" cannot be audited; "hit the primary source once before asserting" leaves a trace in the log, and `scripts/discipline_scan.py` can tell you later whether it ever fired.
5. **Delete what you have handled.** This file is a queue, not an archive — the journal is the archive. A queue you never empty becomes a wall you stop reading.

**Rules expire.** Give each promoted rule a freshness date, and when the discipline audit reports it as a dead-letter candidate (no firing all week, trace type), decide deliberately: keep, rewrite in a form that can fire, or retire it. Retiring is *dormancy*, not deletion — the ID stays, so it can come back if the situation that earned it returns. See [`../docs/discipline-audit.md`](../docs/discipline-audit.md).

**The shape of an entry** is defined once, in [`promotion_candidate.md`](promotion_candidate.md) — the eight fields, what each one is for, and why the evidence field is read first. `scripts/distill.sh` substitutes that same file into the prompt it fires, so the format the model writes and the format you read cannot drift apart. If you want to change the shape, change it there; do not restate it here.

**This file ships empty.** `distill.sh` appends the first section the first time your material crosses the threshold.

---

<!-- distill.sh appends below this line. Newest sections at the bottom. -->
