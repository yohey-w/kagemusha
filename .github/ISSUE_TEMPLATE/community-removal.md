---
name: "Remove my community shelf / community 棚の削除依頼"
about: "Delete cookbook/community/<your-login>/ from main. Only the shelf's owner can ask. / 自分の棚を main から削除する（本人のみ）"
title: "community: remove my shelf"
labels: community-removal
assignees: ""
---

<!--
  Automated. `.github/workflows/community-remove.yml` checks that the login of
  whoever opened this issue matches the directory below, then opens and merges
  the deletion PR. If they don't match, the issue is closed with a note.
  Leave the `<...>` placeholder alone if you are not editing the line — the
  workflow ignores it and will ask you for the path.

  自動処理されます。起票者のログイン名と下のディレクトリが一致した場合だけ、
  削除 PR が自動で作られマージされます。一致しない場合は定型コメントで閉じます。

  DO NOT DELETE the marker line below. On a fork or a fresh clone the
  `community-removal` label does not exist yet, and a label that does not exist
  cannot be applied — the marker is what wakes the workflow there.
  下のマーカー行は消さないでください。fork や新規 clone には
  `community-removal` ラベルがまだ無く、無いラベルは付けられません。
  そこでワークフローを起こすのはこのマーカーです。
-->

<!-- kagemusha:community-removal -->

## Path to remove / 削除するパス

```
cookbook/community/<your-login>/
```

**Replace `<your-login>` above with your own GitHub login**, and leave the rest
of the line as it is. There is deliberately no worked example here: the
workflow reads **every** path in this issue body — including ones inside HTML
comments — so a sample path that is not yours reads as a request to take down
**someone else's** shelf, and your own correct request is refused and closed.

**上の `<your-login>` を自分の GitHub ログイン名に置き換えてください**（行の残りはそのまま）。
**見本のログイン名をここに書いていないのは意図的です**——ワークフローは本文中の
**全ての**パスを読みます（HTML コメントの中も含みます）。自分のものでない見本の
パスが残っていると「**他人の棚**の削除依頼」として拒否され、あなた自身の正しい
依頼まで閉じられます。

If your shelf was posted before the move and still lives at the old root, the
pre-split form `community/<your-login>/` is accepted too — the workflow removes
the shelf from both roots. / 移転前に置いた棚が旧パスに残っている場合、
`community/<ログイン名>/` の形でも受け付けます（新旧どちらからも削除します）。

## Read this before you file / 出す前に読む

- [ ] Removal deletes the directory from `main`. **It does not remove it from the git history**, or from the clones, forks, and mirrors that already pulled it. / 削除は `main` からディレクトリを消すだけです。**git の履歴からは消えません**——既に pull された clone / fork / ミラーからも消えません。
- [ ] If a secret (token, key, password, address) was in the file, **rotate it**. Rotation is the only step that actually takes effect; deletion is housekeeping. / 秘密情報（トークン・鍵・パスワード・住所）が入っていたなら、**ローテーションしてください**。実際に効くのはローテーションだけで、削除は後片付けです。
- [ ] History rewriting is not done on this repository. For cached views on GitHub's side, contact [GitHub Support](https://support.github.com/). / このリポジトリで履歴の書き換えは行いません。GitHub 側のキャッシュについては [GitHub Support](https://support.github.com/) が窓口です。
