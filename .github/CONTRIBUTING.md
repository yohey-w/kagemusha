# Contributing — three places, two kinds of review

*English first, 日本語は下。*

The repository is in two layers: **core** at the root (the kit itself — shape, never content) and **`cookbook/`** (samples — one shelf ruled by the maintainer, one shelf ruled by a string matcher). That makes **three places** a contribution can land in, and **two kinds of review** they are judged by. Pick the place before you write the PR.

| | **core** (the kit) | **`cookbook/author/`** (the sample loop) | **`cookbook/community/`** (your shelf) |
|---|---|---|---|
| What you change | `templates/`, `docs/`, `scripts/`, formats | the author's reference instance and its disciplines | `cookbook/community/<your GitHub login>/*.md` only |
| What qualifies | the physics of working with an AI, burned in a live loop | corrections to the sample itself — it is one loop's record, not a recommendation | anything you burned — including disciplines specific to your profession or environment |
| Who decides | **a maintainer rules on it.** No automation merges here | **a maintainer rules on it.** No automation merges here | **a format lint.** Pass and it is auto-approved and squash-merged |
| Turnaround | as long as the ruling takes | as long as the ruling takes | minutes |
| Review of content | yes | yes | **none — nobody reads it** |
| Responsibility | shared with the maintainer who merged it | shared with the maintainer who merged it | **yours** |
| Take-down | normal PR | normal PR | issue with the removal template, owner-only, automated |

So: **two of the three places are the maintainer's adjudication lane, and exactly one is automatic.** The boundary between core and `cookbook/` is declared in [`docs/layers.md`](../docs/layers.md); what each shelf's stamp does and does not mean is in [`cookbook/README.md`](../cookbook/README.md).

Read [`cookbook/community/README.md`](../cookbook/community/README.md) before using the automatic lane. It is short, and the part about git history being permanent is the part people skip.

---

## The maintainer's lane — the kit itself, and the sample loop

The kit's curated discipline set is [`cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md). Its own `## 増やし方` section states the gate, and a PR into that file is measured against it — **three conditions, plus the metadata every entry carries.**

1. **Burned from an actual rejection or accident.** *「実際の却下・事故から焼けたこと。理屈だけで正しい規律は入れない。」* A discipline that is merely correct in theory does not go in. The PR body has to say what went wrong, in a live loop, that produced it.
2. **The proposition survives having the profession stripped off.** *「職業を落としても命題が残ること。」* Only the physics of working with an AI — holes anyone delegating work to an agent falls into, whatever their trade. **Working standalone is not a reason to include it**: a discipline that belongs to your profession goes to your own `judgment/judgment_model.md`, or to the `cookbook/community/` lane here. This is the condition most PRs fail.
3. **It passes the kit's own audit: "delete this one line — does the agent then get it wrong?"** *「この1本を消したら、エージェントは間違えるか。No なら足さない。」* If the agent behaves identically without it, it is words, and words consume the same ≤160-line / ≤32-principle budget as the rules that bite.
4. **It carries the metadata the file's own entry template requires** — a **portability label** (`［単体で効く］` / `［機構前提］` + a stated `requires` / `［型だけ持ち帰れ］`), a **paste target** (L1 judgment model / agent instructions / `verifiers.md`), and the **burn it came from**, written so no client, person, or trade-specific context is identifiable. Entries without all three are incomplete, not merely unpolished.

Also welcome in this lane, and judged the same way: **"this rule did not transfer to my setup, and here is what broke."** A discipline only one person has been burned by is n=1; the second report of the same hole is what makes it shippable.

Format changes, doc fixes, and scripts are the same lane: a maintainer rules. So is anything under [`cookbook/author/`](../cookbook/author/README.md) — that shelf is the record of one live loop, so a PR into it is a correction to a record, and a maintainer rules on whether it still describes what happened. Keep `scripts/test.sh` green — it is the acceptance gate, it runs in CI unchanged, and there is no skip primitive in it.

---

## The `cookbook/community/` lane — auto-merged

A pull request is auto-approved and squash-merged when **all** of the following hold. Any one of them failing means it is not merged automatically; nothing is rejected or closed by the machine.

- **Every changed path** — including the old name of a rename — is `cookbook/community/<the PR author's own login>/<name>.md`. The prefix is built from the PR author's login, so touching another person's shelf and touching the kit are the same case. **The pre-split root `community/` is no longer this lane**: a PR into it goes to the maintainer.
- At most **3 files** in the PR, at most **50 KB** per file.
- The PR is **not a draft** and targets the **default branch**.
- The content passes the format lint: no email address, no phone number, no company-form word (`株式会社` / `Inc.` / `LLC` / `Ltd` …), no `¥`/`$`/`円` amount, no absolute path (`/home/…`, `/Users/…`, `C:\…`), no `../`, no `http(s)` link outside `github.com` / `zenn.dev`, no private-key block or API-token shape, and nothing matching the kit's leak guard (`tests/forbidden_patterns.txt`). **Every one of those rules is applied twice** — to the bytes as written, and to their Unicode NFKC normalisation — so a full-width or compatibility spelling is not a way past it.
- The changed files are **plain UTF-8 text blobs**. A symlink, a submodule, a non-UTF-8 byte, or a C0 control character leaves the lane. File modes are read from the PR head's tree — **metadata, never a checkout of the PR's code** — and anything unreadable fails closed to the maintainer.
- The repository variable `COMMUNITY_AUTOMERGE_ENABLED` is `true`. This is the maintainer's kill switch and it is **default-off**: while it is unset or set to anything else, **nothing is auto-merged** and every PR in this lane goes to the adjudication lane instead. A fork of this repository therefore does not inherit an armed auto-merger.

If a path is outside the lane, the PR is **labelled `管理者裁定レーン`** and left for a maintainer — untouched otherwise. If the lint hits, the workflow comments with **the rule name and the line number only**, never quoting the matched text: that comment is public and permanent, and quoting the match would spread exactly what the rule exists to stop.

The full rule table, the format for an entry, and the removal procedure live in [`cookbook/community/README.md`](../cookbook/community/README.md).

---
---

# コントリビュート — 3つの置き場所・2つの審査

このリポジトリは二層です。**core**（直下＝キット本体。配るのは形だけで中身は配らない）と **`cookbook/`**（標本。管理者が裁定する棚と、文字列照合が判定する棚）。つまり置き場所は**3つ**、審査は**2種類**しかありません。PR を書く前に置き場所を選んでください。

| | **core**（キット本体） | **`cookbook/author/`**（標本ループ） | **`cookbook/community/`**（あなたの棚） |
|---|---|---|---|
| 変えるもの | `templates/`・`docs/`・`scripts/`・書式 | 作者の実走インスタンスとその規律集 | `cookbook/community/<GitHub ログイン名>/*.md` のみ |
| 載る条件 | 実走で焼けた「AIとの協働の物理」 | 標本そのものの訂正（**1つのループの記録**であって推奨ではない） | あなたが焼いたものなら何でも（職業固有・環境固有の規律も可） |
| 判定者 | **管理者の裁定。** 自動マージは一切なし | **管理者の裁定。** 自動マージは一切なし | **形式 lint。** 合格すれば自動承認＋squash マージ |
| 所要 | 裁定にかかるだけ | 裁定にかかるだけ | 数分 |
| 内容のレビュー | あり | あり | **なし——誰も読みません** |
| 責任 | マージした管理者と分担 | マージした管理者と分担 | **投稿者** |
| 取り下げ | 通常の PR | 通常の PR | 削除テンプレの issue（本人のみ・自動） |

つまり**3つのうち2つは管理者裁定レーンで、自動なのはちょうど1つだけ**です。core と `cookbook/` の境界そのものは [`docs/layers.md`](../docs/layers.md)、それぞれの棚の判子が何を意味し何を意味しないかは [`cookbook/README.md`](../cookbook/README.md) にあります。

自動レーンを使う前に [`cookbook/community/README.md`](../cookbook/community/README.md) を読んでください。短いですが、**git 履歴が恒久である**という段が、いちばん飛ばされる段です。

---

## 管理者裁定レーン — キット本体と標本ループ

選別済みの規律集は [`cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md) で、そのファイル自身の `## 増やし方` が門になっています。この PR はその門で測ります——**3条件＋各エントリが必ず持つメタ情報**の4軸。

1. **実際の却下・事故から焼けたこと。** 原文: 「理屈だけで正しい規律は入れない。」PR 本文に、実走ループで**何が壊れてこの規律が出たか**を書いてください。
2. **職業を落としても命題が残ること。** 載るのは「AIとの協働の物理」だけ——職業も業種も問わず、AIに仕事を任せる人間なら同じ形で踏む穴に限ります。**技術的に単体で効くことは、ここに載せる理由になりません**。職業の規律の置き場所はあなたの `judgment/judgment_model.md` か、この repo なら `cookbook/community/` レーンです。**落ちる PR の大半はここ。**
3. **キット自身の審査を通ること——「この1本を消したら、エージェントは間違えるか」。** No なら足さない。無くても挙動が変わらないなら、それは文言であり、**噛む規律と同じ ≤160行・≤32原則の枠**を食います。
4. **ひな型が要求するメタ3点を備えること**——**可搬性ラベル**（`［単体で効く］` / `［機構前提］`＋`requires` 明記 / `［型だけ持ち帰れ］`）・**貼り先**（L1 の原則 / エージェント指示ファイル / `verifiers.md`）・**焼けた出自**（案件名・人名・職業固有の文脈を落とした形で）。3点が揃っていないものは「磨き不足」ではなく**未完成**として差し戻します。

このレーンでは **「この規律は自分の環境に移植できなかった、こう壊れた」** も歓迎で、同じ基準で裁定します。1人しか踏んでいない穴は n=1——**同じ穴を2人目が報告した時点**で、出荷する価値のある規律になります。

書式修正・ドキュメント・スクリプトも同じレーン（管理者の裁定）です。[`cookbook/author/`](../cookbook/author/README.md) も同じで——あの棚は**1つの実走ループの記録**なので、そこへの PR は「記録の訂正」であり、いま起きたことをまだ正しく書けているかを管理者が裁定します。`scripts/test.sh` は緑のまま保ってください——これが受け入れゲートで、CI はこれをそのまま実行し、この suite には skip の仕組みがありません。

---

## `cookbook/community/` レーン — 自動マージ

次を**すべて**満たす PR は自動承認＋squash マージされます。1つでも欠けると自動マージされないだけで、機械が却下したりクローズしたりはしません。

- **変更ファイルが全て**（リネーム前の名前も含む）`cookbook/community/<PR作者自身のログイン名>/<名前>.md` であること。接頭辞は PR 作者のログイン名から組み立てるので、**他人の棚を触ること**と**キット本体を触ること**は同じ扱いになります。**移転前の直下 `community/` はもうこのレーンではありません**——そこへの PR は管理者に回ります。
- 1 PR **3ファイル**まで、1ファイル **50 KB** まで。
- **draft でない**こと、**デフォルトブランチ宛て**であること。
- 形式 lint に合格すること: メールアドレス・電話番号・法人格語（`株式会社` / `Inc.` / `LLC` / `Ltd` …）・`¥`/`$`/`円` の金額・絶対パス（`/home/…`, `/Users/…`, `C:\…`）・`../`・`github.com` と `zenn.dev` 以外への `http(s)` リンク・秘密鍵ブロックや API トークンの形・キットの漏洩ガード（`tests/forbidden_patterns.txt`）に当たるものが無いこと。**これら全ての規則は2回**——書かれたままのバイト列と、その Unicode NFKC 正規化——に対して適用されるので、全角や互換文字での書き換えは抜け道になりません。
- 変更ファイルが**素の UTF-8 テキスト**であること。symlink・submodule・非 UTF-8 バイト・C0 制御文字はレーンから外れます。ファイルモードは PR head の tree から読みます（**メタ情報だけ・PR のコードは checkout しません**）。読めなかったものは全て「管理者へ」に倒します（fail closed）。
- リポジトリ変数 `COMMUNITY_AUTOMERGE_ENABLED` が `true` であること。これは管理者の**緊急停止スイッチ**で、**既定は off**です——未設定または `true` 以外の間は**自動マージを一切行わず**、このレーンの PR も管理者裁定レーンに回ります。したがって、このリポジトリを fork しても「起動済みの自動マージ機」は付いてきません。

レーン外のパスが1つでもあれば、その PR は **`管理者裁定レーン` ラベルが付くだけ**で、他には何もせず管理者に回ります。lint に当たった場合、ワークフローは**ルール名と行番号だけ**をコメントします——**該当箇所は引用しません**。そのコメントも公開・恒久であり、引用したら、そのルールが止めようとしているものをそのまま広げることになるからです。

ルール表の全文・エントリの書式・削除手順は [`cookbook/community/README.md`](../cookbook/community/README.md) にあります。
