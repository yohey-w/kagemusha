# distill-prompt.md — the prompt `scripts/distill.sh` fires (edit it; it is yours)

<!--
This file IS the prompt. distill.sh reads it and substitutes:
  {{TODAY}} {{PENDING}} {{THRESHOLD}} {{MATERIAL_FILE}} {{QUEUE_FILE}}
  {{RULES_FILE}} {{PRINCIPLES_BLOCK}} {{MATERIAL}}
Everything above the line is a comment and gets sent along harmlessly; the
substitutions are plain text replacement, so the placeholders must stay spelled
exactly as above. Delete a placeholder and that context simply stops arriving.

Three constraints are load-bearing. If you rewrite this file, keep them:
  (a) IT MAY NOT INVENT A REASON. Only corrections whose reason is visible in
      the material become candidates; the rest stay in the material, unpromoted.
  (b) IT MAY NOT WRITE A RULE ANYWHERE BUT THE QUEUE. Promotion is a review and
      a review is a person.
  (c) The journal is APPENDED (a correction is a fact); a rule is OVERWRITTEN
      (a rule is a norm, and two live versions of a norm is just ambiguity).
-->

---

You are distilling correction material into **promotion candidates** for a human to review. Today is {{TODAY}}. {{PENDING}} correction event(s) have accumulated since the last distillation (firing threshold: {{THRESHOLD}}).

**Scope of writing: you may append to `{{QUEUE_FILE}}` and nothing else.** You may not edit `{{RULES_FILE}}`, any principles or verifier file, any source of truth, or the material file. No outward operation of any kind: no send, no publish, no push, no deploy. If you believe a rule should change, that belief goes in the queue as a candidate — that is the whole output of this job.

**Why the queue and not the rule file:** moving text needs no gate; *promoting a correction into a rule* does, and the gate is the person who was corrected. A rule this run wrote by itself would be a rule nobody reviewed, governing every future run — including this one.

## What counts as a candidate

1. **Do not invent reasons.** A correction tells you *what* was overruled. Whether it also tells you *why* is a fact about the material, not something to be reasoned out afterwards — the same "you were told to stop" is equally explained by several different principles, so a reason reconstructed later is invention, not derivation. **Only a correction whose material carries a fragment of the reason (what was being corrected, what was asked for instead, an explicit "because") may become a candidate.** The rest are not discarded: list them under `## no reason on record` with one line each, so they stay visible and a second instance can revive them later.
2. **Count events, not repetitions.** The material is already grouped into events; four restatements of one point are one event and one piece of evidence. Never let a rephrasing count as a second witness.
3. **Prefer trace form over prohibition form.** "Don't assert what you haven't checked" cannot be audited — obeying it produces a sentence nobody wrote. "Hit the primary source once before asserting" leaves a trace. Where a correction is naturally a prohibition, propose the observable action that replaces it, and say you did.
4. **One correction is one correction.** A single event is enough to *propose* a candidate, but say so in the confidence field. Do not merge unrelated events into one grand principle to make it look better supported.

## The format — every candidate gets all eight fields

Missing fields are not omitted; they are written as `—` or `none on record`. A blank field is information (it tells the reviewer what the material did not contain); a silently dropped field is not.

```
### C-{{TODAY}}-<n> · <one-line rule, imperative, trace form if possible>
- **type:** trace | prohibition (and if prohibition: the trace-form rewrite you propose)
- **evidence:** verbatim quote(s) from the material, with the event id. Never paraphrase.
- **scope:** when this applies — the situations where it should fire
- **exception:** where it should NOT apply (if the material shows none, write "none on record")
- **confidence:** N event(s) in this batch; prior support if any. Cluster-one-vote.
- **counter-evidence:** anything in the material pointing the other way (or "none found")
- **destination:** agent instructions / verifier checklist / journal-only observation
- **freshness:** {{TODAY}} — re-check by <a date or a condition>
```

## Conflicts with what you already believe

Below are the reviewer's existing principles. **Any candidate that contradicts, narrows, or duplicates one of them does not go in the main list** — it goes under `## conflicts — held` with: the existing principle it collides with, the exact nature of the collision (contradiction / narrowing / duplicate), and both quotes side by side. Do not resolve the conflict. A rule that contradicts a live rule is a decision about which one is wrong, and that decision is the reviewer's.

──── existing principles ────
{{PRINCIPLES_BLOCK}}
──── end ────

## Output

Append **one dated section** to `{{QUEUE_FILE}}`, even if the answer is "nothing worth promoting" — a run that writes nothing is indistinguishable from a run that never happened, and the wrapper treats an unwritten queue as a failure. The section is:

```
## {{TODAY}} — <n> candidate(s) from {{PENDING}} correction event(s)
<candidates, in the eight-field format>
## conflicts — held
## no reason on record
```

Then stop. Do not summarise the candidates back into any other file, and do not act on them.

──── material: corrections harvested since the last distillation ────
Machine-extracted and unjudged. A line here is a regex hit, not a correction. Quotes are truncated at harvest time, so if a fragment reads as cut off, it is — say so rather than completing it from imagination. Source file: `{{MATERIAL_FILE}}`.

{{MATERIAL}}
──── end of material ────
