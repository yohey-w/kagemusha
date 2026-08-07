# layers — core と cookbook の境界宣言

*日本語が本文。English summary is at the bottom.*
*安全とデータ境界（`setup.sh` が展開するもの／しないもの）は、末尾に対訳の全文がある — the full English text of the safety and data-boundary section is at the bottom, not just a summary.*

このリポジトリは**1リポジトリの中の二層**である。ディレクトリを2つに割ったのではなく、**依存の向きを片方向に固定した**のがこの設計の中身だ。

```text
kagemusha/
├── scripts/  templates/  tests/  docs/  README.md  …        ← core（機構）
├── manifests/                                                 ← core（境界の宣言）
└── cookbook/                                                  ← 標本棚
    ├── author/       … 管理者裁定・実走標本
    └── community/    … 形式 lint のみ
```

`core/` というディレクトリは**作らない**。core は「リポジトリ直下にあるもの」であって、名前を持つ箱ではない。箱を作れば URL も看板コマンド（`./scripts/setup.sh`）も既存 clone の生活も本の参照も一斉に壊れる——**境界のために導線を壊すのは、境界のために払う代金として高すぎる**。

---

## 規範（この3行が本文で、残りは全部その説明）

1. **core は、利用者がどの判断を採用すべきかを決めない。** core が配るのは**形**（足場・スクリプト・空の書式・受入ゲート）であって、**中身**（どの規律を持つか・どう値付けするか・何を承認に回すか）ではない。
2. **`setup.sh`・core のスクリプト・core のテンプレートは、`cookbook/` を読み込んでも・コピーしても・実行してもならない。** 例外はない。標本が欲しければ**利用者が自分でコピーする**。
3. **依存は片方向。** `cookbook/` → core の参照は自由。core → `cookbook/` は禁止。

### なぜ2が「読み込みも」なのか

コピーだけ禁じても足りない。core のスクリプトが `cookbook/` の中身を**読んで振る舞いを変えた**時点で、標本は既定値になる。「配っていないが、無いと動かない」は配っているのと同じだ。**`cookbook/` を丸ごと消しても core の受入ゲートが緑のままであること**——これが2の運用上の意味であり、群Hが測ろうとしているものだ。

### なぜ「コピーするという行為」を利用者に残すのか

キットが持つ唯一の非対称な資産は**あなた自身の却下から焼けた判断**で、借り物の原則はそれと**同じ枠を食う**。だから標本を既定で展開しないのは不親切ではなく、**設計**だ。コピーの手間そのものが「これは自分が踏んだ穴か」を1回問う関門になっている。`setup.sh` が [`../cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md) を意図的に展開しないのも、`judgment/correction_patterns.txt` を**メニューのコピーではなくコメントだけの空ファイルとして生成する**のも、同じ1つの規範の現れである。

> ⚠️ **訂正パターンの扱いは一度変わっている。** 以前ここには「`correction_patterns.example.txt` を実運用名へコピーしない」と書いてあった。現在の `setup.sh` はそもそも**コピーしない**——`judgment/correction_patterns.txt` を heredoc から**中身ゼロ（コメントのみ）で生成**し、走査スクリプトは利用者が自分の語彙を書くまで動くことを拒否する。「配らない」の実装が *コピーの省略* から *空の生成* に変わったので、記述をそこへ合わせてある（`manifests/scaffold.tsv` の "DELIBERATELY NOT IN THIS MANIFEST" 節が同じことを書いている）。

---

## `setup.sh` が展開するもの・意図的に展開しないもの

**このキットがあなたのデータに対して何をしないか**を、先に固定しておく。このリポジトリは**二層**で、その境目が「いま自分は何をインストールしたのか」の答えになっている。

| | **core**——`scripts/` `templates/` `docs/` `tests/` `manifests/`（リポジトリ直下） | **[`cookbook/`](../cookbook/README.md)**——標本棚 |
|---|---|---|
| 何か | **機構**: 足場・スクリプト・**空の書式**・受入ゲート | **中身**: 作者が実走で焼いた規律・実走の証拠抜粋・他の人の棚 |
| `setup.sh` | **触るのはここだけ。** コピーする全ファイルは [`manifests/scaffold.tsv`](../manifests/scaffold.tsv) に列挙されている | **読まない・コピーしない・実行しない**——1ファイルも |
| 手に入るもの | 何も記入されていない書式（原則0本・有効パターン0本・日付入りエントリ0件） | **既定では何も入らない。** 読んで・選んで・**手で移した**ぶんだけ |

**core は、あなたがどの判断を採用すべきかについて意見を持たない。** 借り物の原則は自分で焼いた原則と同じ枠を食うので、標本を既定で展開しないのは不親切ではなく設計だ——**コピーするという行為そのものが、あなたが選んだ地点**になる。境界の全文はこの文書の冒頭「規範」節、棚の判子が意味すること／しないことは [`cookbook/README.md`](../cookbook/README.md)。

⚠️ この分割は**プライバシー境界ではない**。`cookbook/` と core は同一のリポジトリ・同一の恒久的な履歴だ。

<details>
<summary><b>core だけを checkout する</b>——他人の中身を作業ツリーに置きたくない場合</summary>

core は棚を読まないので、**そもそも checkout しない**という選択ができる（clone → `ls` → `setup.sh` exit 0 まで実測済み）:

```bash
git clone --filter=blob:none --no-checkout https://github.com/yohey-w/kagemusha.git
cd kagemusha
git sparse-checkout set --no-cone '/*' '!/cookbook'
git checkout
./scripts/setup.sh          # 棚がある時とまったく同じに走る
```

`--filter=blob:none` は転送量を減らすだけ（対応していない転送方式では無害に無視される）。棚を外しているのは2つのパターンのほうだ。戻すのは `git sparse-checkout disable` でいつでもできる。

**これが買っていないもの——頼る前に読むこと。** これは**作業ツリーの大きさの都合であって、それ以上の何かではない。** 棚はリモートにも、この clone のオブジェクトDBにも、履歴にも残っている（`git log`・`git show`・後からの `git checkout` は届く）。プライバシーも隔離も、中身の保証も**買っていない**——**この文書**と [`cookbook/README.md`](../cookbook/README.md) と同じ但し書きだ。**これを privacy mode と呼ぶな。** キット自身の受入ゲートは、その下にある性質のほうを直接測っている——群Hは `cookbook/` を丸ごと削除して、`setup.sh` が exit 0 のまま**まったく同じ集合のファイルを作る**ことを毎回実測する。

</details>

**あなたが作る実データが git に入らない仕組み**は allowlist 方式の `.gitignore` だ——追跡されるのはキット自身のファイルだけなので、SSOT・台帳・config は事故でも commit できず、`git pull` はその下でキットだけを更新する。どのパスがキットで、どこからがあなたのものかは、リポジトリ直下の allowlist `.gitignore` がファイル単位で定めている（配置の設計根拠は [`design.md`](design.md) の「ディレクトリ配置の5不変則」）。

---

## 構造で強制する（宣言だけでは腐るので）

| 仕組み | 何を固定するか |
|---|---|
| `manifests/scaffold.tsv` | **足場が触ってよいソースの全集合**。source 列は `templates/` 起点のみ・`..` 不可・**`cookbook/` の出現で即エラー**。「setup.sh が何をコピーするか」を script の中ではなく**データとして外に出した**ので、境界違反が diff に見える |
| `scripts/test.sh` 群H | 宣言を毎回実測する。H1（manifest に `cookbook/` 参照0件）・**H2（棚の全ファイルに sentinel を植えて `setup.sh` を実走し、生成物に1件も届かないことを確認）**・**H2b（棚を丸ごと削除しても `setup.sh` が exit 0 で同じ集合を作る）**・H3（core のテンプレは有効な原則0本・有効regex0本・日付入りエントリ0件）・H4（コピー一覧が manifest 駆動であることを、manifest を書き換えて出力が追随することで証明）・H5（`scripts/` と `config.env.example` から `cookbook/` への**実行時依存**0件。案内コメントのみ許可）。**H2〜H4は有効化済み**——ここが「後続の段で有効化」と書いてあった時期がある |
| `scripts/test.sh` 群I | community レーンの防壁を**出荷 YAML から抜き出して** node で評価する（規則を書き写すと「テストは緑・bot は間違い」になるため）。パス所有の照合・トラバーサル拒否・symlink/submodule/非UTF-8の拒否 |
| `.gitignore`（allowlist） | `cookbook/` と `manifests/` は**追跡対象**（キット本体側）。実走インスタンスデータは従来どおり構造的にコミット不能 |

---

## この境界が**買っていないもの**（ここを取り違えると危ない）

**プライバシー境界ではない。** `cookbook/` と core は**同一のリポジトリ・同一の git 履歴**だ。`cookbook/` に置いたものは、リポジトリの他のどこに置いたものとも同じだけ公開で、同じだけ恒久である。誤ってマージされた秘密は、`cookbook/` の下にあったからといって隔離されない——**爆発半径は「解決」されておらず、明示的に受容した上で、マージ前の防壁（形式 lint・パス所有の照合・トラバーサル拒否）を厚くする**という取り方をしている。

**信頼の等級でもない、少なくとも自動的には。** `author/` と `community/` の差は**誰が見たか**の差であって、置き場所が中身を保証するわけではない。判子の意味は [`../cookbook/README.md`](../cookbook/README.md) の信頼水準表を読むこと。

**品質ゲートでもない。** core が緑であることは機構が動く証拠であって、`cookbook/` の標本があなたの環境で正しいことの証拠ではない。

---

## English summary

This repository is **two layers in one repo**, asymmetric by design. There is deliberately **no `core/` directory**: core *is* the repository root, because boxing it would break the URLs, the headline command, existing clones, and the companion book's references — too high a price to pay for a boundary.

The norm, in three lines:

1. **Core does not decide which judgments a user should adopt.** Core ships **shape** — scaffolding, scripts, empty forms, the acceptance gate — never **content**.
2. **`setup.sh`, core's scripts, and core's templates must not read, copy, or execute anything under `cookbook/`.** No exceptions. If you want a sample, **you copy it yourself**.
3. **Dependency is one-way.** `cookbook/` → core is free; core → `cookbook/` is forbidden.

"Read" is in rule 2 on purpose: a script that merely *reads* the shelf and changes behaviour has made the sample a default. The operational test is that **deleting `cookbook/` entirely leaves core's acceptance gate green** — which is what test group H exists to measure, backed by `manifests/scaffold.tsv` (source column must be `templates/`-rooted, no `..`, and any `cookbook/` occurrence is a hard error).

What this boundary **does not buy**: it is **not a privacy boundary** (same repo, same permanent history — a mis-merged secret is not isolated by living under `cookbook/`; the blast radius is explicitly *accepted*, with the pre-merge guards hardened instead), it is **not automatically a trust grade** (`author/` vs `community/` is a difference in *who looked*, not a guarantee about content — see the trust table in [`../cookbook/README.md`](../cookbook/README.md)), and it is **not a quality gate** for the samples.

---

## English — safety and data boundaries

Full English text of the Japanese section "`setup.sh` が展開するもの・意図的に展開しないもの" above.

First, what this kit **does not** do to your data.

### What `setup.sh` expands, and what it deliberately does not

This repository is **two layers**, and the line between them is the answer to "what did I just install?"

| | **Core** — `scripts/` `templates/` `docs/` `tests/` `manifests/` (the repository root) | **[`cookbook/`](../cookbook/README.md)** — the sample shelf |
|---|---|---|
| What it is | the **mechanism**: scaffolding, scripts, **empty forms**, the acceptance gate | **content**: disciplines the author burned in a live loop, evidence excerpts, other people's shelves |
| `setup.sh` | **touches only this.** Every file it copies is listed in [`manifests/scaffold.tsv`](../manifests/scaffold.tsv) | **never read, never copied, never executed** — not one file |
| What you get | forms with nothing filled in: zero principles, zero active patterns, zero dated entries | nothing, until **you read it, pick a line, and move it by hand** |

**Core holds no opinion about which judgments you should adopt.** A borrowed principle eats the same budget as one you burned yourself, so the shelf is not a default and copying from it is a manual act on purpose — that act is where you choose. Boundary in full: the norm at the top of this document (English summary above). What the shelf's stamps do and don't mean: [`cookbook/README.md`](../cookbook/README.md).

⚠️ The split is **not a privacy boundary**: `cookbook/` and core are the same repository and the same permanent history.

<details>
<summary><b>core-only checkout</b> — don't want other people's content in your working tree at all?</summary>

Because core never reads the shelf, you can simply not check it out. Verified end to end (clone → `ls` → `setup.sh` exits 0):

```bash
git clone --filter=blob:none --no-checkout https://github.com/yohey-w/kagemusha.git
cd kagemusha
git sparse-checkout set --no-cone '/*' '!/cookbook'
git checkout
./scripts/setup.sh          # runs exactly as it does with the shelf present
```

`--filter=blob:none` only saves bandwidth (it is ignored by some transports, harmlessly); the pattern pair is what leaves `cookbook/` out. Get it back any time with `git sparse-checkout disable`.

**What this does not buy — read this before you rely on it.** It is a **checkout-size convenience, and nothing else.** The shelf is still in the remote, still in this clone's object database, and still in the history: `git log`, `git show`, and any later `git checkout` reach it. It grants no privacy, no isolation, and no guarantee about content — the same disclaimer as **this document** and [`cookbook/README.md`](../cookbook/README.md). **Do not call it a privacy mode.** The kit's own acceptance gate measures the underlying property directly: test group H deletes `cookbook/` outright and proves `setup.sh` still exits 0 and creates exactly the same set of files.

</details>

**What keeps the data you create out of git** is the allowlist `.gitignore`: only the kit's own files are tracked, so your SSOT, journal, and config cannot be committed even by accident — and `git pull` updates the kit underneath them. Which paths are the kit's and which are yours is drawn file by file by the allowlist `.gitignore` at the repository root (the rationale for the layout is in [`design.md`](design.md), "ディレクトリ配置の5不変則").
