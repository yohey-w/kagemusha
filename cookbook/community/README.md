# `cookbook/community/` — your own shelf, merged by machine (destination in preparation)

*English first, 日本語は下。*

> ## ⚠️ Not the submission path yet
>
> **Send your PR to [`/community/`](../../community/README.md) at the repository root, exactly as before.** The auto-merge and removal workflows still build their path prefix from `community/<your GitHub login>/`, and a PR that touches this directory instead will fall **outside** the automatic lane — it will not be lint-checked, will not be merged by machine, and will sit waiting for a maintainer.
>
> This directory is the **declared destination** for that lane, added ahead of the move so the two-layer boundary can be stated in one place. The switch — workflows, templates, and links moving together — happens in a later, separately reviewed step. Until it lands, the root `community/README.md` is the operative document; this file is a signpost.

## What will be here, and what will not change when it moves

One directory per person, `<your GitHub login>/*.md`, **merged by a workflow with no human reading the content** — not before the merge, not after. The lint is a string matcher: it catches shapes (email addresses, phone numbers, company forms, money amounts, absolute paths, off-allowlist links, size and file count, path ownership), never meaning. It does not know whether your text is confidential, wrong, or someone else's to publish.

**Moving under `cookbook/` changes none of that, and in particular it does not make this shelf more private.** `cookbook/` and the rest of the repository are the same git history. The moment a shelf merges, every clone, fork, mirror, and archive that pulls can hold a copy, and nothing done here reaches those copies. **Deleting is not un-publishing.** If something leaked, the removal issue is housekeeping; **rotating what leaked is the only step that takes effect.**

What the two-layer split *does* say about this shelf is the trust stamp: **`community/` is lint-only, `author/` is maintainer-ruled, and core decides neither.** See [`../README.md`](../README.md) for the trust table, and [`../../docs/layers.md`](../../docs/layers.md) for the boundary itself.

---
---

# `cookbook/community/` — あなた専用の棚（マージは機械が行う・**移転先の予告**）

> ## ⚠️ ここはまだ投稿先ではありません
>
> **PR は従来どおり、リポジトリ直下の [`/community/`](../../community/README.md) 宛に出してください。** 自動マージ bot と削除 bot は、いまも `community/<GitHub ログイン名>/` からパス接頭辞を組み立てています。この階層を触る PR は**自動レーンの外**に落ちます——lint も走らず、機械マージもされず、管理者の裁定待ちで止まります。
>
> この階層は、そのレーンの**移転先を宣言したもの**です。二層の境界を1箇所で言い切れるように、移転そのものより先に置いてあります。切り替え——ワークフロー・テンプレート・リンクを**同時に**動かす作業——は、別途レビューを通す後続の段で行います。それが着地するまでは、直下の `community/README.md` が正本で、このファイルは道標です。

## ここに来るもの／移転しても変わらないもの

1人1ディレクトリ、`<GitHub ログイン名>/*.md`、**内容は誰も読まないままワークフローがマージ**します——マージ前にも、マージ後にも。lint は文字列照合で、見ているのは形だけです（メールアドレス・電話番号・法人格語・金額・絶対パス・許可外リンク・サイズとファイル数・パスの所有）。**意味は見ていません。** その文章が秘密かどうか、間違っているかどうか、公開してよい立場のものかどうかを、機械は知りません。

**`cookbook/` の下へ移ってもそこは何も変わりません。とくに、この棚が「より private になる」ことはありません。** `cookbook/` もリポジトリの他の場所も、**同一の git 履歴**です。棚がマージされた瞬間から、pull した全ての clone / fork / ミラー / アーカイブが写しを持ち得て、**こちら側のどの操作もその写しには届きません。削除は「公開の取り消し」ではない。** 漏らしてしまった場合、削除 issue は後片付けであり、**実際に効くのは「漏れたものをローテーションする」ことだけ**です。

二層化がこの棚について**言っている**のは、判子の違いだけです——**`community/` は lint のみ・`author/` は管理者裁定・core はそのどちらも決めない。** 信頼水準の表は [`../README.md`](../README.md)、境界そのものの宣言は [`../../docs/layers.md`](../../docs/layers.md) にあります。
