# promotion_candidate.md — the shape of ONE promotion candidate (the single source of truth)

<!--
WHY THIS FILE EXISTS. The candidate format used to be written out twice: once in
templates/distill-prompt.md (the prompt the model is given) and once in
templates/promotion_queue.md (the file the reviewer reads). Two copies of one
format is one copy that goes stale — and the prompt is a file its owner is
explicitly invited to rewrite, so the drift was designed in.

Now there is one copy: this file. `scripts/distill.sh` reads it and substitutes
it into the prompt at {{CANDIDATE_FORMAT}}; promotion_queue.md links here rather
than restating it. Edit the fields here and both sides move together.

THIS FILE SHIPS EMPTY, and that is the point: it defines the SHAPE of a
candidate, never a candidate. Every rule in your queue has to have been earned
by something that happened to you.
-->

---

## The contract

**Every candidate gets all eight fields.** Missing fields are not omitted; they are
written as `—` or `none on record`. A blank field is information — it tells the
reviewer what the material did *not* contain. A silently dropped field is not.

**The evidence field is the load-bearing one.** A reviewer reads it *before* the
rule line: the rule line is the distiller's wording, the quote is what actually
happened. If the quote does not support the rule, the candidate is wrong no matter
how good the sentence is. Quotes are verbatim and carry the event id, so the full
turn can be reopened (`correction_scan.py --material … --show-event <id>`).

## The eight fields

```
### C-<YYYY-MM-DD>-<n> · <one-line rule, imperative, trace form if possible>
- **type:** trace | prohibition (and if prohibition: the trace-form rewrite you propose)
- **evidence:** verbatim quote(s) from the material, with the event id. Never paraphrase.
- **scope:** when this applies — the situations where it should fire
- **exception:** where it should NOT apply (if the material shows none, write "none on record")
- **confidence:** N event(s) in this batch; prior support if any. Cluster-one-vote.
- **counter-evidence:** anything in the material pointing the other way (or "none found")
- **destination:** agent instructions / verifier checklist / journal-only observation
- **freshness:** <date> — re-check by <a date or a condition>
```

## Field notes

- **type** — `trace` commands an action and leaves a mark a scanner can find;
  `prohibition` commands restraint, and obeying it produces the sentence nobody
  wrote, so its firings are unobservable. Prefer trace form, and when the
  correction is naturally a prohibition, propose the observable action that
  replaces it and say that you did.
- **scope / exception** — a rule with no stated scope fires everywhere, which is
  how a queue of good rules becomes an instruction file nobody follows.
- **confidence** — count *events*, never repetitions. One point restated four
  times is one witness (cluster-one-vote).
- **destination** — the machine layer of `verifiers.md` if a regex can check it;
  the agent-instructions file only if a human has to hold it in mind; otherwise
  journal-only, which is a legitimate answer.
- **freshness** — a rule with no expiry never gets re-examined. See
  [`../docs/discipline-audit.md`](../docs/discipline-audit.md).
