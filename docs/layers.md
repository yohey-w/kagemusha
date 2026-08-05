# layers — core と cookbook の境界宣言

*日本語が本文。English summary is at the bottom.*

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
