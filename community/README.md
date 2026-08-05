# `community/` — moved to `cookbook/community/` / 移転しました

> **Moved to [`../cookbook/community/README.md`](../cookbook/community/README.md).**
> 規約の正本（置き方・lint 条件・責任の線引き・削除手順）はすべて移転先にあります。

## ⚠️ 新しい PR はこの階層に置かないでください / do not open new PRs here

**自動レーンは `cookbook/community/<あなたの GitHub ログイン名>/` だけ**です（bot の接頭辞がそこへ切り替わりました）。**この旧 `community/` 直下への PR は自動マージされず、管理者に回ります。**

```text
cookbook/community/<your GitHub login>/disciplines.md   ← 今の置き場所
community/<your GitHub login>/                          ← 旧・自動レーンではない
```

**既に旧パスに棚がある場合の削除**は、移行期のあいだ従来どおり受け付けます——削除 issue には新旧どちらの形で書いても、bot が**両方の root から**棚を消します（[`../.github/ISSUE_TEMPLATE/community-removal.md`](../.github/ISSUE_TEMPLATE/community-removal.md)）。

**変わっていないこと**: 内容は誰も読みません（形式 lint のみ）。そして**この移動でプライバシーは1ミリも買っていません**——`cookbook/` は core と同一のリポジトリ・同一の履歴で、**削除は「公開の取り消し」ではない**。責任の線引きは移転先の README を必ず読んでください。

境界の宣言は [`../docs/layers.md`](../docs/layers.md)、当時パスの引き当ては [`../docs/path-migrations.md`](../docs/path-migrations.md)、棚の判子の意味は [`../cookbook/README.md`](../cookbook/README.md)。

---

## English

This shelf **moved to [`cookbook/community/`](../cookbook/community/README.md)**, and the rules — path, lint, the responsibility line, removal — live there. The automatic lane is now **only** `cookbook/community/<your GitHub login>/`: a PR into this pre-split root is **not** auto-merged and goes to the maintainer. Removal issues still accept either form during the transition; the bot deletes from both roots. Nothing about the trade-off changed: nobody reads the content, and **the move buys no privacy** — same repo, same permanent history, and deleting is not un-publishing.
