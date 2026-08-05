<!--
  Three places, two kinds of review — see .github/CONTRIBUTING.md
    · core            : the kit itself. A maintainer rules on it.
    · cookbook/author : the author's sample loop. A maintainer rules on it.
    · cookbook/community : cookbook/community/<your GitHub login>/*.md only.
                       Format lint passes → auto-approved and squash-merged,
                       and NOBODY reads the content.
                       See cookbook/community/README.md.
  Delete the section that does not apply.

  3つの置き場所・2つの審査（.github/CONTRIBUTING.md 参照）。
  該当しない側の節は消してください。
-->

## Where / 置き場所

- [ ] **core** — the kit (`templates/`, `docs/`, `scripts/`, formats) / キット本体。管理者が裁定します
- [ ] **`cookbook/author/`** — the author's sample loop / 標本ループ。管理者が裁定します
- [ ] **`cookbook/community/`** — only `cookbook/community/<my GitHub login>/*.md` / 自分の棚のみ。lint 合格で自動マージされます

---

## The discipline / 規律

**One line, imperative / 1行・命令形:**

<!-- e.g. "Write the scope before you write a negation." -->

**Applies when / 適用条件:**

<!-- the condition under which it bites — model, tool, team shape, kind of work -->

**Burned from / 焼けた出自:**

<!-- the failure it came out of, one line, at an abstraction where no client,
     person, or trade-specific context is identifiable
     相手・案件が特定できない抽象度で1行 -->

---

## core lane only / core レーンのみ

The gate is `cookbook/author/starter-disciplines.md` §増やし方 — four axes:

- [ ] **Burned from an actual rejection or accident**, not correct-in-theory / 実際の却下・事故から焼けた（理屈だけで正しい規律ではない）
- [ ] **The proposition survives having the profession stripped off** — the physics of working with an AI. Working standalone is not a reason to include it / 職業を落としても命題が残る（AIとの協働の物理）。単体で効くことは理由にならない
- [ ] **"Delete this one line — does the agent then get it wrong?"** Yes / 「この1本を消したら、エージェントは間違えるか」＝Yes
- [ ] **Carries the entry metadata**: portability label (`［単体で効く］`/`［機構前提］`+requires/`［型だけ持ち帰れ］`), paste target, burn origin / メタ3点（可搬性ラベル・貼り先・焼けた出自）を備えている
- [ ] `./scripts/test.sh` is green locally / ローカルで緑

---

## Before you post — self-declaration / 出す前の自己申告

- [ ] **I have checked there is no client name, personal name, proper noun, money amount, internal path, or contact detail in what I am adding.** / **顧客名・固有名・金額・内部パス・連絡先が無いことを確認した。**
- [ ] **I understand this goes into git history and stays there** — deleting it later removes it from `main`, not from the clones, forks, and mirrors that already pulled it. If a secret gets in, rotating it is the only step that actually takes effect. / **gitの履歴に残り、そこから消えないことを理解した**——後から削除しても消えるのは `main` からだけで、既に pull された clone / fork / ミラーからは消えない。秘密が入った場合、実際に効くのはローテーションだけ。
