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

## 第2表: README の節の移動（README fragment migrations）

READMEを玄関1枚へ薄くしたときに、**節そのものが別ファイルへ動いた**。上の表と同じ理由でここに引き当てを残す——本と記事が README を**節番号**で引いており（例:「README第6節の現物」「六箱の定義はREADME第9節にもある」）、その文章は書かれた時点では正しかったからだ。

**旧見出しの扱いは3通り**: ①README内からしか参照されていなかった節は**削除**（参照元も同時に更新）②本・記事・SNSから参照されている節は**見出しを1行のstubとして実体で残す**（見出し＝アンカーが生き、本文は移転先を指す1行だけ）③参照実績が不明なものは原稿を確認し、無ければ削除。

| 当時の節（README / README_ja） | 現行の在り処 | コミット | 旧見出しの現況 | 備考 |
|---|---|---|---|---|
| `## 1. What kagemusha is` / `## 1. kagemusha とは` | 玄関の2文（README冒頭） | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除 | 名前の由来の物語は本へ。定義は玄関に圧縮 |
| `## 2. Who it fits — and who it does not` / `## 2. 向く人・向かない人` | [`getting-started.md`](getting-started.md#does-it-fit-you) / [同](getting-started.md#適合条件) | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除（玄関に1往復だけ残す） | 参照実績なし（`zenn-and` を実測） |
| `## 4. Watch it first (10 minutes)` / `## 4. まず見るだけ（10分）` | [`getting-started.md`](getting-started.md#the-10-minute-demo) / [同](getting-started.md#10分デモ) | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除（玄関のデモ3行が入口） | スクショ3枚も移転先へ |
| `## 6. Set it up …` / `## 6. 自分の環境に入れる（30分・コピペ）` | [`getting-started.md`](getting-started.md#the-steps-copy-paste) / [同](getting-started.md#手順コピペ) | `a3ee2fa`・`250c22a`・`2dc2e59` | **互換 stub**（見出しを残し移転先を指す1行） | 本が「README第6節の現物をそのまま貼った」と書いているため。**コマンドはバイト単位で同一のまま移した** |
| `## 7. Your day, once it is running` / `## 7. 走り出したあとの1日` | [`operations.md`](operations.md) | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除 | 朝の情景描写は本へ（キットの手順ではない） |
| `## 9. Going further` / `## 9. 発展編` | [`operations.md`](operations.md)・[`inbound-loop.md`](inbound-loop.md)・[`faq.md`](faq.md)・[`design.md`](design.md) | `a3ee2fa`・`250c22a`・`2dc2e59` | **互換 stub** | 本の付録が「六箱の定義はREADME第9節にもある」と参照。G/S/D/V/I/R は `operations.md` に全文移設 |
| `### Architecture (the whole loop)` / `### 全体アーキテクチャ（ループ全景）` | [`design.md`](design.md) | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除 | Mermaid図ごと移設 |
| `### The four-layer equation` / `### 4層の等式` | [`design.md`](design.md) | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除 | |
| `### Design rationale (Q&A)` / `### 設計の考え方（FAQ形式）` | [`faq.md`](faq.md) | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除 | 4問とも移設 |
| `### What's in the box` / `### 中身の早見表` | [`README.md`](README.md)（docs地図） | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除 | 全パス表はドキュメント地図へ |
| `### Related & prior work` / `### 関連・先行プロジェクト`、`### Genealogy` / `### 系譜` | [`README.md`](README.md)（docs地図） | `a3ee2fa`・`250c22a`・`2dc2e59` | 削除 | 先行者への謝辞は落とさず移設 |
| `## 8. Safety and data boundaries` 本文 / `## 8. 安全とデータ境界` 本文 | [`layers.md`](layers.md) | `a3ee2fa`・`250c22a`・`2dc2e59` | **見出しは残る**（2行表＋注意1行に圧縮） | core だけの checkout 手順も移設 |

> **残した見出し（`## 3.` / `## 5.` / `### 却下を資産に変える → 判断蒸留` / `### 依存校正 …` / `## 10.`）は、正典節 `### 訂正の昇格` が内部リンクで指しているアンカー**である。正典は一字も変えずに README に残るので、**これらの見出しは文字列ごと固定**され、テスト群Kのリンク解決検査がそれを守っている。

## English

**One job:** map a path as it was written at the time — in the companion book, in old commit messages, in issues and bookmarks — onto the path as it is now. Structure moves; the writing that predates the move does not, and rewriting it after the fact would be falsifying a record. So we keep a lookup table instead.

Rules: one row per move (a directory move is one row, not one row per file); the **commit** column is mandatory (dates don't reproduce, commits do); rows are append-only, so a path that moved twice has two rows; this is an *index*, not the *why* — reasons live in [`provenance.md`](provenance.md); and every row states the old path's current status (`deleted` / `compat stub` / `both live`).

**The first three rows are the core/cookbook split.** Note what is *not* recorded: when `cookbook/author/` was first populated the originals were untouched, and **a copy is not a move**, so nothing was written here. The rows exist because the old paths were later replaced by **compat stubs** — they still resolve (200), they name the new path, and each one says the artifact itself is *not* there. Nothing was deleted: the companion book, articles, issues and bookmarks point at those URLs.

**Second table — README fragment migrations.** Thinning the README to a single front page moved whole sections into `docs/`. The same rule applies: the companion book and the articles cite README sections *by number*, and those citations were correct when written. Old headings are handled three ways — deleted (only ever linked from inside the README, and the callers were updated in the same commit), kept as a **one-line stub** (cited from the book, an article, or social media: the heading survives so the anchor resolves, and its body is one line pointing at the new home), or checked against the drafts and deleted when no citation exists. The headings that stay verbatim are the ones the frozen canonical section links to; test group K resolves every link, so a rename cannot silently break them.
