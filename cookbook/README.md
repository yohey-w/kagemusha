# `cookbook/` — the sample shelf

*English first, 日本語は下。*

This repository is **two layers in one repo**, and they are deliberately asymmetric.

| | **core** (the repository root: `scripts/` `templates/` `tests/` `docs/` `lib/`) | **`cookbook/`** (this directory) |
|---|---|---|
| What it is | the **mechanism** — scaffolding, scripts, empty forms, the acceptance gate | **samples** — filled-in instances, burned disciplines, other people's shelves |
| What it decides for you | **nothing about which judgments to hold.** Core ships the shape, never the content | it shows *someone's* content, so you can see what a filled form looks like |
| Dependency direction | core **never** reads, copies, or executes anything under `cookbook/` | `cookbook/` may reference core freely |
| Enforced by | `manifests/scaffold.tsv` + test group **H** in `scripts/test.sh` | — |

The boundary itself is stated in [`../docs/layers.md`](../docs/layers.md). This file is about what lives on the shelf.

---

## The two shelves, and what each one's stamp means

### `author/` — ruled on by the maintainer, from the author's live instance

Three separate claims, which are easy to collapse into one and shouldn't be:

1. **It has actually run.** Every file here came out of a loop that was running on real work, not a specimen written for the repository. The evidence excerpts under `author/evidence/` are the receipts.
2. **It has been selected.** A maintainer ruled on each entry — against the gate each file states for itself (for disciplines, `starter-disciplines.md` §増やし方). Nothing lands here by passing a lint.
3. **It is not warranted to fit you.** Ruled-on is not the same as correct-for-your-loop. A discipline burned on someone else's model, stack, and clients can be exactly wrong in yours, and a borrowed principle eats the same slot as one you burned yourself. **This shelf is not a recommendation.** Take what matches a hole you have already fallen into; leave the rest.

The third point is the one that gets dropped. "Curated" reads as "endorsed"; here it means *reviewed*, not *prescribed*.

### `community/` — mechanical format lint only, no human reads it

One directory per person, merged by a workflow. **No human reads the content**, before or after the merge. The lint is a string matcher: it catches shapes, not meaning — not whether the text is confidential, wrong, or someone else's to publish. Full rules and the responsibility line: [`community/README.md`](community/README.md).

### Trust levels — read the stamp, not the folder

| Shelf | Who checked it | What was checked | What it does **not** mean |
|---|---|---|---|
| `author/` | a maintainer, entry by entry | ran in a real loop · survived the stated gate · carries its burn, portability label, paste target | not "recommended for you" · not tested in your environment · not a default |
| `community/` | **nobody** (a workflow's format lint) | shape only: path, file count, size, privacy regex | not reviewed · not endorsed · not checked for accuracy or for whether it was the poster's to publish |
| core (repo root) | the acceptance gate (`scripts/test.sh`) | the mechanism works and is uncommittable-by-construction | core still holds **no opinion** about which judgments you should adopt |

---

## What this directory is **not**

**It is not a privacy boundary.** `cookbook/` and core are the same git repository and the same history. A file placed here is as public, and as permanent, as one placed anywhere else in the repo: the moment it merges, every clone, fork, mirror, and archive that pulls can hold a copy, and no action taken here reaches those copies. The two-layer split is about **where dependency may point** — it buys you nothing on privacy, and nothing on deletion. **Deleting is not un-publishing.**

**It is not a promotion queue.** Nothing moves from `community/` to `author/` by sitting here. If a discipline turns out to be general, it moves by a separate PR that a maintainer rules on.

**It is not read by `setup.sh`.** Scaffolding never reaches into this directory. If a sample here is useful to you, **you copy it yourself** — and that act of copying is the point: it is where you choose it.

---
---

# `cookbook/` — 標本棚

このリポジトリは**1リポジトリの中の二層**で、その二層は**意図的に非対称**です。

| | **core**（リポジトリ直下: `scripts/` `templates/` `tests/` `docs/` `lib/`） | **`cookbook/`**（この階層） |
|---|---|---|
| 何か | **機構**——足場・スクリプト・空の書式・受入ゲート | **標本**——記入済みの実例・焼けた規律・他の人の棚 |
| 利用者の何を決めるか | **どの判断を持つかは決めない。** core が配るのは形であって中身ではない |「誰かの中身」を見せる。記入済みの書式がどう見えるかを見るためのもの |
| 依存の向き | core は `cookbook/` を**読み込まない・コピーしない・実行しない** | `cookbook/` から core を参照するのは自由 |
| 強制する仕組み | `manifests/scaffold.tsv` ＋ `scripts/test.sh` の**群H** | — |

境界そのものの宣言は [`../docs/layers.md`](../docs/layers.md) にあります。このファイルは「棚に何が載るか」の話です。

---

## 2つの棚と、それぞれの判子の意味

### `author/` — 管理者が裁定した、作者の実走インスタンス由来のもの

**3つの別々の主張**で、まとめてしまいがちですが、まとめてはいけません。

1. **実走している。** ここにあるファイルは、リポジトリのために書かれた標本ではなく、実際の仕事で回っていたループから出てきたものです。`author/evidence/` の抜粋がその領収書です。
2. **選別されている。** 各エントリを管理者が1本ずつ裁定しています——基準は各ファイル自身が掲げる門（規律なら `starter-disciplines.md` の `## 増やし方`）。**lint を通ったから載る、という経路はここにはありません。**
3. **あなたに適合する保証はない。** 裁定済みは、あなたのループにとって正しい、とは違います。他人のモデル・スタック・顧客で焼けた規律は、あなたのところでは正確に間違っていることがあり、**借り物の原則は自分で焼いた原則と同じ枠を食います**。**この棚は推奨ではありません。** 自分が既に踏んだ穴に対応するものだけ持ち帰り、あとは置いていってください。

落ちるのは3つ目です。「選別済み」は「推奨」と読まれますが、ここでは**裁定済み**という意味であって、**処方ではありません**。

### `community/` — 形式 lint のみ・内容は誰も読まない

1人1ディレクトリ、マージはワークフローが行います。**内容は誰も読みません**——マージ前にも、マージ後にも。lint は文字列照合で、見ているのは形だけです。その文章が秘密かどうか、間違っているかどうか、公開してよい立場のものかどうかは判定しません。規約全文と責任の線引き: [`community/README.md`](community/README.md)。

### 信頼水準——フォルダではなく判子を読む

| 棚 | 誰が見たか | 何を見たか | **意味しないこと** |
|---|---|---|---|
| `author/` | 管理者が1本ずつ | 実走したか・掲げた門を通ったか・焼けた出自／可搬性ラベル／貼り先が付いているか | 「あなたへの推奨」ではない・あなたの環境で検証されていない・既定値ではない |
| `community/` | **誰も見ていない**（ワークフローの形式 lint） | 形だけ: パス・ファイル数・サイズ・プライバシー正規表現 | レビュー済みではない・推奨ではない・正確さも「公開してよい立場か」も未検査 |
| core（リポジトリ直下） | 受入ゲート（`scripts/test.sh`） | 機構が動くこと・インスタンスデータが構造的にコミット不能であること | core は**どの判断を採用すべきかについて意見を持たない** |

---

## この階層が**そうではない**もの

**プライバシー境界ではない。** `cookbook/` と core は**同一のリポジトリ・同一の履歴**です。ここに置いたファイルは、リポジトリの他のどこに置いたものとも同じだけ公開で、同じだけ恒久です——マージされた瞬間から、pull した全ての clone / fork / ミラー / アーカイブが写しを持ち得て、**こちら側のどの操作もその写しには届きません**。二層化が買っているのは**依存が向いてよい向き**であって、プライバシーは1ミリも買っていません。削除についても同じです。**削除は「公開の取り消し」ではない。**

**昇格キューではない。** ここに置いたことで `community/` から `author/` へ上がることはありません。一般化すると分かった規律は、**別の PR** で移り、そちらは管理者が裁定します。

**`setup.sh` は読まない。** 足場作りがこの階層へ手を伸ばすことは決してありません。ここの標本が役に立つなら、**あなたが自分でコピーします**——そしてその「コピーするという行為」こそが要点です。**そこがあなたが選んだ地点**だからです。
