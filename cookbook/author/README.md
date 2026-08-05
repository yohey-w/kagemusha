# `cookbook/author/` — the author's live-instance shelf

*English first, 日本語は下。*

Everything under this directory came out of **one running loop** — the author's — and was **ruled on entry by entry by a maintainer**. Read the three claims and their limit in [`../README.md`](../README.md) before taking anything: *ran for real* · *was selected* · **not warranted to fit you.** This is a shelf, not a recommendation, and nothing here is scaffolded by `setup.sh` — you copy what you want, and the copying is where you choose it.

## What is on the shelf

| Path | What it is |
|---|---|
| `starter-disciplines.md` | **Starter disciplines — a menu, not a template.** Disciplines burned in the author's live instance, each carrying the burn it came from, a portability label (*works standalone* / *needs a mechanism, stated* / *take the shape, the content is yours to burn*), and a paste target. Its own `## 増やし方` section is the gate a PR into it is measured against. Take only the ones whose hole you have already fallen into. |
| `evidence/` | **Proof the loop actually runs, plus what it accumulated** — hand-redacted excerpts from the live instance (one unattended weekly-distillation run, published with its non-zero exit intact; the dated journal entries bracketing a correction that became a rewritten principle), **and the disclosure package**: the instance's own judgment principles, state guardrails, memory schema, and misassertion record, released under a four-class policy (`evidence/disclosure-policy.md`) that was fixed *before* the selection. **31 principles: 21 verbatim, 7 transformed, 3 withheld. 9 misassertions: 3 published in full, 6 counted only.** Withheld items still appear in `evidence/manifest.yaml` as rows with a class and a broad reason — never a title. Scope, redaction level, and **what it does not prove** are stated in `evidence/README.md`. |
| `reference-instance/` | **A worked-through instance, laid out the way a loop actually lives.** The forms core ships are blank; these are the same forms **written out with worked examples and placeholders** — the shape, the length, the bluntness — in the paths the loop keeps them at. **They are not the author's real data**: the entries, names, and numbers are illustrative, and the real records are published only under `evidence/`, under the disclosure policy. Its own README states the mapping. |

## Specimen, not default

Everything on this shelf is a **specimen — not a default.** Nothing here is scaffolded, injected,
imported, or read by core; `setup.sh` never touches it and the acceptance gate stays green with this
whole directory deleted. A principle in `evidence/principles/` is **one instance's operating rule
under a stated scope**, not a belief and not a recommendation — each file carries `scope`,
`version`, `adopted_at`, and `status` precisely so you can check it against your conditions and
find it inapplicable. The disclosure classes in `evidence/disclosure-policy.md` are likewise **one
maintainer's ruling on his own records**, published so the arithmetic can be audited, not so it can
be copied. Take a specimen only after you have hit the hole it came out of.

## Why `reference-instance/` exists at all

Core ships **shape, never content**. But a form you have never seen filled in is hard to fill in — the empty template does not tell you how long an entry runs, how blunt a journal line is allowed to be, or what a verifier looks like when it is doing work. This directory answers that, **at the cost of being one person's answer**. Read it as a worked example, not a spec: the mechanism is core's, the worked-through content is the author's **illustration** — not his records — and the gap between them is yours to fill.

---
---

# `cookbook/author/` — 作者の実走インスタンス棚

この階層のものは全て**ひとつの走っているループ**——作者のもの——から出てきたもので、**管理者が1本ずつ裁定**しています。持ち帰る前に、[`../README.md`](../README.md) の3つの主張とその限界を読んでください: **実走した**・**選別された**・**あなたに適合する保証はない**。これは棚であって推奨ではありません。ここにあるものを `setup.sh` が展開することはありません——**欲しいものはあなたがコピーする**のであって、**そのコピーがあなたの選択の地点**です。

## 棚の中身

| パス | 中身 |
|---|---|
| `starter-disciplines.md` | **スターター規律集——雛形ではなくメニュー。** 作者の実走で焼けた規律。各本に**焼けた出自**・**可搬性ラベル**（*単体で効く* ／ *機構前提（requires を明記）* ／ *型だけ持ち帰れ*）・**貼り先**が付きます。このファイル自身の `## 増やし方` が、ここへの PR を測る門です。**自分が踏んだ穴のものだけ**持ち帰ってください。 |
| `evidence/` | **一周が実走している証拠と、回った結果溜まったもの**——実インスタンスからの手作業匿名化抜粋（無人発火した週次蒸留の実ログ1本＝**非ゼロ終了もそのまま**／訂正が価値判断モデルの本文差し替えに至るまでを日付で追える台帳）に加え、**判断公開パッケージ**——この実インスタンスの判断原則・状態ガードレール・記憶のスキーマ・誤断定の記録を、**選別より先に固定した**4区分の方針（`evidence/disclosure-policy.md`）で公開したもの。**31原則中 21本を原文・7本を派生・3本は非公開／誤断定9件中 3件を全文公開・6件は集計のみ**。非公開分も `evidence/manifest.yaml` に区分と広い理由分類だけの行として載る（**題名は載せない**）。射程・匿名化水準・**何を証明していないか**は `evidence/README.md` に明記。 |
| `reference-instance/` | **記入済みインスタンス一式を、ループが実際に living する配置のまま置いたもの。** core が配る書式は空です。これはその同じ書式を、**書式と例示（プレースホルダ入り）で書き起こしたもの**——1エントリの長さ・粒度・身も蓋もなさが見える形——を、ループが実際に置いているパスに並べたものです。**作者の実データではありません**（記入内容・人名・数値は例示。実記録は `evidence/` に、公開方針つきで出しています）。対応関係はその中の README にあります。 |

## 見本であって既定値ではない / specimen, not default

この棚のものはすべて**見本（specimen）であって既定値（default）ではありません。** `setup.sh` は展開せず、
core はここを読まず、**このディレクトリを丸ごと消しても検収ゲートは緑のまま**です。
`evidence/principles/` の原則1本は、**一定条件下の運用規則**であって信条でも推奨でもありません——
各ファイルが `scope` `version` `adopted_at` `status` を持っているのは、
**あなたの条件と突き合わせて「これは自分には当てはまらない」と判定できるようにする**ためです。
`evidence/disclosure-policy.md` の公開区分も同じで、**1人の管理者が自分の記録に下した裁定**を、
コピーされるためではなく**計算を検算できるように**置いてあります。
**自分が踏んだ穴のものだけ**持ち帰ってください。

## `reference-instance/` がなぜ要るのか

core が配るのは**形であって中身ではない**。しかし**記入済みを一度も見たことのない書式は、埋めにくい**——空のテンプレートは、1エントリがどれくらいの長さか、台帳の1行はどこまで身も蓋もなくてよいか、検証器が仕事をしているときどう見えるかを教えてくれません。この階層はそれに答えます。ただし**「一人の答え」であるという代償つき**です。**仕様ではなく実例として読んでください**——機構は core のもの、書き起こした中身は作者の**例示**（実データではない）、その間の隙間を埋めるのがあなたです。
