---
name: "Remove my community shelf / community 棚の削除依頼"
about: "Delete community/<your-login>/ from main. Only the shelf's owner can ask. / 自分の棚を main から削除する（本人のみ）"
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
-->

## Path to remove / 削除するパス

```
community/<your-login>/
```

Replace the line above with your own shelf, e.g. `community/octocat/`.
上の行を自分の棚に書き換えてください（例: `community/octocat/`）。

## Read this before you file / 出す前に読む

- [ ] Removal deletes the directory from `main`. **It does not remove it from the git history**, or from the clones, forks, and mirrors that already pulled it. / 削除は `main` からディレクトリを消すだけです。**git の履歴からは消えません**——既に pull された clone / fork / ミラーからも消えません。
- [ ] If a secret (token, key, password, address) was in the file, **rotate it**. Rotation is the only step that actually takes effect; deletion is housekeeping. / 秘密情報（トークン・鍵・パスワード・住所）が入っていたなら、**ローテーションしてください**。実際に効くのはローテーションだけで、削除は後片付けです。
- [ ] History rewriting is not done on this repository. For cached views on GitHub's side, contact [GitHub Support](https://support.github.com/). / このリポジトリで履歴の書き換えは行いません。GitHub 側のキャッシュについては [GitHub Support](https://support.github.com/) が窓口です。
