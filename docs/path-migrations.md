# path-migrations — 移行台帳

**このファイルの用途はひとつ**: 過去のドキュメント・過去のコミットメッセージ・併読される本の中に出てくる**当時のパス**を、**現行のパス**へ引き当てられるようにすること。

リポジトリの構造は動く。動いたあとで困るのは、**動く前に書かれた文章**だ——本の本文、ブログ記事、issue のコメント、外部のブックマーク、そして自分の古いコミットメッセージ。そこに書かれたパスは**その時点では正しかった**ので、後から書き換えるのは記録の改竄になる。だから**書き換えるかわりに、引き当て表を持つ**。

## 記入規律

- **1移動1行。** ディレクトリごと動いた場合はディレクトリの行を1本立て、個別ファイルの行は立てない（表が実質の `find` 出力になると読めなくなる）
- **コミット欄は必須。** 「いつ動いたか」ではなく「**どのコミットで動いたか**」を書く。日付は再現に使えないが、コミットは使える
- **行は消さない・追記のみ。** 2回動いたパスは2行になる。中間のパスを消すと、中間の時期に書かれた文章が引き当てられなくなる
- **`docs/provenance.md` とは役割が違う。** provenance は「**何が・なぜ**変わったか」の出自表。ここは「**どこにあったものが・どこへ**行ったか」だけを引く索引で、理由は書かない
- **旧パスの現況**を必ず書く: `削除` / `互換 stub`（旧パスにファイルが残り、新パスを指している） / `併存`（旧新どちらも実体・移行期のみ）

## 表

| 当時パス | 現行パス | コミット | 旧パスの現況 | 備考 |
|---|---|---|---|---|
| *(まだ移動は確定していない)* | | | | |

> **いま（`pre-cookbook-split` 直後）の状態**: `cookbook/` 以下は**加算されただけ**で、旧パスのファイルは1バイトも変わっていない。`cookbook/author/` にあるものは旧パスの**複製**であり、移動ではない。したがってこの表はまだ空である——**複製は移動ではないので、ここには書かない**。旧パスが stub 化・削除された段で、その1行がここに入る。

## English

**One job:** map a path as it was written at the time — in the companion book, in old commit messages, in issues and bookmarks — onto the path as it is now. Structure moves; the writing that predates the move does not, and rewriting it after the fact would be falsifying a record. So we keep a lookup table instead.

Rules: one row per move (a directory move is one row, not one row per file); the **commit** column is mandatory (dates don't reproduce, commits do); rows are append-only, so a path that moved twice has two rows; this is an *index*, not the *why* — reasons live in [`provenance.md`](provenance.md); and every row states the old path's current status (`deleted` / `compat stub` / `both live`).

**Right now the table is empty on purpose.** Everything under `cookbook/` so far is an **addition**: the files there are *copies*, the originals are untouched, and **a copy is not a move**. Rows appear here when an old path is stubbed or deleted.
