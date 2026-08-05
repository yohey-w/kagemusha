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
| `templates/starter-disciplines.md` | `cookbook/author/starter-disciplines.md` | `e793fa8` | 互換 stub | 二層化——焼けた規律の一覧は「中身」なので core から標本棚へ。旧パスには移転案内と**規律1件の空書式**だけが残る。門（`## 増やし方`）の正本は移転先 |
| `evidence/` | `cookbook/author/evidence/` | `e793fa8` | 互換 stub | 3ファイルとも（`README.md` / `ledger_excerpt.md` / `weekly_distill_log_excerpt.txt`）。**証拠の現物は移転先にしかない**——旧パスに残るのは案内だけで、実ログ本文は1行も入っていない |
| `community/` | `cookbook/community/` | `f96de0d`（bot・規約）／`e793fa8`（旧 README の stub 化） | 互換 stub | 自動マージレーンの接頭辞ごと移動。**旧 root への PR はもう自動レーンではない**（管理者へ）。削除 issue だけは移行期のあいだ新旧どちらの形も受け、bot が両 root から消す |

> **`cookbook/` に「移動」ではなく「複製」で入ったものは、ここに書かない。** Phase 2（`8dd82d5`）の時点では旧パスのファイルが1バイトも変わっておらず、複製は移動ではないからだ。上の3行が立ったのは、**旧パスの実体が stub に置き換わった**段（`e793fa8`）である。
>
> **旧パスは削除していない。** 本・記事・issue・ブックマークが指しているので、URL は 200 のまま残す。stub には必ず「現行パスはどこか」と「**現物はここには無い**」の2つが書いてある。

## English

**One job:** map a path as it was written at the time — in the companion book, in old commit messages, in issues and bookmarks — onto the path as it is now. Structure moves; the writing that predates the move does not, and rewriting it after the fact would be falsifying a record. So we keep a lookup table instead.

Rules: one row per move (a directory move is one row, not one row per file); the **commit** column is mandatory (dates don't reproduce, commits do); rows are append-only, so a path that moved twice has two rows; this is an *index*, not the *why* — reasons live in [`provenance.md`](provenance.md); and every row states the old path's current status (`deleted` / `compat stub` / `both live`).

**The first three rows are the core/cookbook split.** Note what is *not* recorded: when `cookbook/author/` was first populated the originals were untouched, and **a copy is not a move**, so nothing was written here. The rows exist because the old paths were later replaced by **compat stubs** — they still resolve (200), they name the new path, and each one says the artifact itself is *not* there. Nothing was deleted: the companion book, articles, issues and bookmarks point at those URLs.
