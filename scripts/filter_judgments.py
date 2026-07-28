#!/usr/bin/env python3
"""Bucket approver utterances into judgment classes for weekly distillation.

Takes the human-turn extract from mine_conversations.py and tags each turn with
one or more judgment buckets, so the weekly distillation can read a short,
high-signal list instead of the whole corpus:

  RULE     a ruling — picked one option over others / approved / "go with X"
  REJECT   a rejection — "no", "drop it", "not that"
  CORRECT  a correction — overruling the agent's output/assumption/plan
  TEMP+    positive temperature — praise (what pleased the approver)
  TEMP-    negative temperature — frustration (what tripped the approver's gut)
  VALUE    value language — quality / trust / waste / priority / first-principles
  PROBE    a probing question — "why?", "what do you mean?"
  INT      followed an interrupt (Esc mid-generation) — carried from the miner

CORRECT / REJECT / INT are the richest signal: a ruling is something a model will
eventually predict on its own, but a *correction* is the delta between the model
and the approver, and that signal does not go stale. See docs/judgment-distillation.md.

The buckets are heuristic keyword matches — a cheap pre-filter, NOT a verdict.
A human (or a stronger model, in the weekly distill) still reads the matched
turns and decides what actually becomes a principle.

Vocab is configurable. English + Japanese defaults ship inline; override with
--vocab vocab.json (see --dump-vocab for the exact shape). Add your own domain
words, or swap the language, without touching the code.

Usage
-----
  python3 filter_judgments.py --in ~/judgment/mining            # full corpus
  python3 filter_judgments.py --in ~/judgment/mining --week     # last-7d window
  python3 filter_judgments.py --dump-vocab > vocab.json         # edit, then:
  python3 filter_judgments.py --in ~/judgment/mining --vocab vocab.json
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

# Default vocabularies. Each bucket is a list of alternatives OR'd into one regex.
# English and Japanese cues live side by side so a bilingual log matches either.
# These are deliberately broad (high recall); the distillation pass is the filter
# for precision. Tune freely for your own phrasing via --vocab.
DEFAULT_VOCAB = {
    "RULE": [r"\bgo with\b", r"\blet'?s go\b", r"\bship it\b", r"\bapproved?\b",
             r"\bgo ahead\b", r"\bsounds good\b", r"\bdo that\b", r"\bthat works\b",
             r"\byes,? do\b", r"\bLGTM\b",
             "でいこう", "で行こう", "でいく", "にしよう", "それでいい", "承認",
             "採用", "でよい", "頼む", "任せ", "一任", "進めて", "ゴー"],
    "REJECT": [r"\bno,?\b", r"\bdon'?t\b", r"\bnope\b", r"\bstop\b", r"\bscrap\b",
               r"\bdrop (it|that)\b", r"\bnot (this|that|needed)\b", r"\bcancel\b",
               r"\breject", r"\bnever mind\b",
               "やめ", "却下", "だめ", "ダメ", "駄目", "いらない", "いらん", "不要",
               "禁止", "するな", "やるな", "ナシ"],
    "CORRECT": [r"^no,? ", r"\bactually\b", r"\bthat'?s wrong\b", r"\bnot quite\b",
                r"\bnot what i\b", r"\byou made that up\b", r"\bmisread\b",
                r"\bthat'?s off\b", r"\bfix (this|that|it)\b", r"\bredo\b",
                r"\bwait,?\b", r"\bhold on\b", r"\bmisleading\b",
                "いや", "じゃなくて", "ではなく", "待って", "ストップ", "勝手に",
                "捏造", "おかしい", "ずれて", "誤解", "間違", "直して", "修正して"],
    "TEMP+": [r"\bnice\b", r"\bgreat\b", r"\bperfect\b", r"\blove (it|this)\b",
              r"\bexcellent\b", r"\bwell done\b", r"\bthanks?\b", r"\bawesome\b",
              r"\bbrilliant\b",
              "素晴らし", "最高", "すごい", "いいね", "良いね", "ありがと", "助かる",
              "完璧", "優秀"],
    "TEMP-": [r"\bugh\b", r"\bwtf\b", r"\bterrible\b", r"\bawful\b", r"\bdisappoint",
              r"\bfrustrat", r"\bwhy would you\b", r"\bmakes no sense\b", r"\bseriously\?",
              "ふざけ", "ひどい", "がっかり", "萎え", "イライラ", "むかつ", "最悪",
              "は？", "なんでだよ", "意味わかんな"],
    "VALUE": [r"\bhonest", r"\btrust", r"\bquality\b", r"\bsloppy\b", r"\bwaste",
              r"\bprioriti", r"\bfirst principle", r"\bevidence\b", r"\bprimary source\b",
              r"\boverkill\b", r"\bcut corners\b", r"\bwhat matters\b",
              "誠実", "正直", "信頼", "品質", "雑", "丁寧", "もったいない", "無駄",
              "投資", "回収", "資産", "現物", "一次情報", "裏取り", "優先順位",
              "本質", "価値", "やりすぎ", "過剰"],
    "PROBE": [r"\bwhy\b", r"\bwhat do you mean\b", r"\bhow come\b", r"\bwhat'?s the\b.*\breason\b",
              r"\bon what basis\b", r"\bwhat'?s .* mean\b",
              "なんで", "なぜ", "どういうこと", "ってなに", "とは？", "理由は", "根拠"],
}


def build_buckets(vocab):
    buckets = []
    for name, alts in vocab.items():
        if not alts:
            continue
        pattern = "|".join("(?:%s)" % a for a in alts)
        buckets.append((name, re.compile(pattern, re.I)))
    return buckets


def main():
    ap = argparse.ArgumentParser(description="Bucket approver utterances for distillation.")
    ap.add_argument("--in", dest="indir", default=os.environ.get("JUDGMENT_MINING_OUT", "."),
                    help="dir holding corpus.jsonl / corpus_recent.jsonl (default: "
                         "$JUDGMENT_MINING_OUT or cwd).")
    ap.add_argument("--week", action="store_true",
                    help="read corpus_recent.jsonl and write judgments_week.md only.")
    ap.add_argument("--vocab", default=None,
                    help="JSON file overriding the bucket vocabulary "
                         "(see --dump-vocab for the shape).")
    ap.add_argument("--dump-vocab", action="store_true",
                    help="print the default vocabulary as JSON and exit.")
    args = ap.parse_args()

    if args.dump_vocab:
        json.dump(DEFAULT_VOCAB, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    vocab = DEFAULT_VOCAB
    if args.vocab:
        with open(os.path.expanduser(args.vocab)) as f:
            vocab = json.load(f)
    buckets = build_buckets(vocab)

    indir = os.path.expanduser(args.indir)
    infile = os.path.join(indir, "corpus_recent.jsonl" if args.week else "corpus.jsonl")
    if not os.path.exists(infile):
        sys.exit("input not found: %s (run mine_conversations.py%s first)"
                 % (infile, " --since 7d" if args.week else ""))

    recs = [json.loads(l) for l in open(infile)]
    out_md = os.path.join(indir, "judgments_week.md" if args.week else "judgments.md")

    tagged = []
    counts = Counter()
    for r in recs:
        t = r["text"]
        tags = [name for name, rx in buckets if rx.search(t)]
        if r.get("interrupt"):
            tags = ["INT"] + tags
        if not tags:
            continue
        for tag in tags:
            counts[tag] += 1
        tagged.append((r.get("ts", ""), r.get("session", ""), tags, t))

    print("mode:", "week" if args.week else "full", " input:", os.path.basename(infile))
    print("human turns:", len(recs), " matched:", len(tagged))
    print("bucket counts:", dict(counts))

    header = (
        "# Approver judgments — last 7 days (auto-extracted, UNVERIFIED)\n\n"
        "> Input to the weekly distillation. INT=interrupt, CORRECT=correction,\n"
        "> REJECT=rejection, RULE=ruling are the high-value tags.\n\n"
        if args.week else
        "# Approver judgments (auto-extracted, UNVERIFIED)\n\n"
    )
    with open(out_md, "w") as f:
        f.write(header)
        if not tagged:
            f.write("(no matching turns)\n")
        month = ""
        for ts, sess, tags, t in tagged:
            mo = ts[:7]
            if mo != month:
                month = mo
                f.write("\n## %s\n\n" % (mo or "undated"))
            line = t if len(t) <= 500 else t[:500] + "..."
            line = line.replace("\n", " / ")
            f.write("- `%s %s` **[%s]** %s\n" % (ts[5:16], sess[:4], ",".join(tags), line))
    print("written:", out_md)


if __name__ == "__main__":
    main()
