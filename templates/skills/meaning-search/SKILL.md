---
name: meaning-search
description: |
  Beta. Search your ledgers by meaning for records that may bear on a topic. Relevant records can still be missed. Splits the case ledger and the decisions journal without cutting a record, has a cheap model pre-read every piece, then follows each hit's `source` into the transcript and reads around it. For what a literal search misses: paraphrases and speech-recognition errors. Claude Code runs the child without tools. Codex runs it in a read-only sandbox and offers no flag to disable connectors. Results are disposable; no index is kept.
  論点に関係する記録を、grep の字面ではなく意味で拾う手順（beta）。台帳と判断台帳を1件ずつ切らずに区切って安いモデルに全部読ませ、拾った記録の出典の欄から逐語の前後をたどってもう一度読ませる。言い換えと音声認識の聞き違いに強い。Claude Code では子に道具を渡さない。Codex は読み取り専用の sandbox で起動するが、接続先（コネクタ）を外す指定は無い。結果は使い捨てで、索引は残さない。
  TRIGGER: 相手の発言に触れて答える・問いを作る前に「この論点の記録を漏れなく」引きたいとき／「意味で探して」「関係する記録を全部」「grep で足りない」「言い換え・聞き違いも拾って」と言われたとき／台帳の要約（title）だけで答えそうになったとき。
  Do NOT use for: 番号や語が決まっている引き当て（grep で足りる）／事実の正誤の判定（拾った番号から正本を開いて確かめる）。
---

# meaning-search — 論点に関係する記録を意味で拾う（beta）

> **English abstract** — A literal search finds only the records written the way you searched for them. To find candidates, this skill splits the case ledger (`ledger.yaml`) and the decisions journal into pieces that never cut a record, asks a cheap model which record ids bear on the topic (twice, with the piece boundaries shifted, and takes the union), checks every returned id against the text it was given, then follows each hit's `source` into the primary record (a meeting transcript, usually speech-recognition output) and has the surrounding lines read again. Relevant records can still be missed. Quotes are taken from the original lines by line number, never from the model's retelling. Claude Code runs the child without tools. Codex runs it in a read-only sandbox and offers no flag to disable connectors. The wrapper validates the returned JSON. Output goes to a throwaway folder — **nothing is written back to the ledgers and no index is kept**, because an index is a second copy that drifts. **Beta:** the engine was run on a real case by its author; this packaged port (configurable paths, the kit's CLI wrapper, the kit's `source` formats) has only been run on the fictional sample. The revisions made after review, covering record splitting, source resolution, response validation and retries, and quote attribution, have only been exercised on the fictional sample and with stubs. Its recall on real cases has yet to be measured. A pre-read is a lead, not a finding: open the records it names before you say anything.

**beta（同梱版は架空の見本でのみ実行。実案件での再現率は未計測）** — 中身の作り（区切り・2回流し・出典をたどる読み）は、著者の別の作業場で実案件に回していたスクリプトの移植。**移植した所（パスの指定・キットの CLI の口・キットの出典の書式）は、同梱の架空の見本でしか回していない。** レビューを受けて作り直した所（記録の区切り方・出典の解き方・答えの検算とやり直し・引用の結び付け）も、架空の見本とスタブでしか回していない。下の数字は元の作業場の報告で、この同梱版で測り直したものではない。

## こういうときに使う

**「あの件について、相手は何と言っていたか」を、台帳と会議の記録から引くとき。** たとえば——

- 相手への返事や問いを書く前に、その論点で相手が言ったことを全部並べたい（「言っていない」と書く前にも）
- 設計や見積もりを変える前に、その論点で決まったこと・保留になったことを洗いたい
- `grep` で探したが、別の言い方で書いた記録がありそうで不安（「納品後の修正」で探しても「検収後の直し」は出ない）
- 会議の記録が音声認識の文字起こしで、誤字が多い（「異動」が「移動」と書かれている）

出てくるのは「関係しそうな記録の一覧」と「逐語のどの行で何と言っているか」。**下読みなので、拾ったものは原文を開いて確かめてから使う。**

## 何のためか

- `grep` は書かれたとおりの言葉しか拾わない。同じ話を別の言い方で書いた記録（「直し」「訂正」「上書き」）と、音声認識が別の字で書いた発言（「異動」→「移動」、「四半期」→「市販機」）は落ちる。
- 台帳の `title` は要約で、留保やその答えを引き出した問いが落ちている。`source` を開けば読めるのに、開かずに「記録に無い」と答えてしまう（[`../../context_ledgers_template.md`](../../context_ledgers_template.md) の「`title` は目次」）。
- つながりの索引（知識グラフ・論点ごとのまとめ）を別に持つと、正本の写しが増えて、つなぎ忘れた日からずれる。だからその場で正本から引いて、使い終わったら捨てる。

## 使い方

キットの直下で実行する。実行前に `config.env` か環境変数で `MSEARCH_MODEL` または `AGENT_MODEL_FAST` を設定する。計画だけ見る場合はモデル設定を省ける。

```sh
project="example-co"  # projects/ の下にある自分の案件フォルダ名に置き換える
# 先に計画だけ見る（モデルを1回も呼ばない。区切りの数と事前に分かる呼び出しの回数が出る）
python3 templates/skills/meaning-search/scripts/meaning_search.py \
  --project "$project" --topic "納品後の修正" --hint "検収・引き渡しのあとの直しも含む" --dry-run

# 流す
python3 templates/skills/meaning-search/scripts/meaning_search.py \
  --project "$project" --topic "納品後の修正" --hint "検収・引き渡しのあとの直しも含む"
```

`--project <name>` は、キットの置き場所から次を既定に取る（在るものだけ。無かったものは実行の記録に出る）: `projects/<name>/ledgers/ledger.yaml`・`judgment/decisions_journal.md`・`ssot/glossary.md`・`projects/<name>/ledgers/mishearings.md`・`projects/<name>/transcripts/`。別の場所にあるなら `--ledger`・`--journal`・`--glossary`・`--mishearings`・`--transcripts` で指す。

よく使う引数（全部は `--help`）:

| 引数 | 既定 | 意味 |
|---|---|---|
| `--hint` | なし | 論点の言い換えなど、拾いたい範囲を補足する |
| `--case` | `MSEARCH_CASE` →（説明なし） | 案件の一行説明（プロンプトの冒頭に入る） |
| `--chunk-tokens` | 25000 | 1区切りの見積りの大きさ |
| `--passes` | 2 | 下読みを何回流して和集合にするか。2回目以降は区切りの境目をずらす |
| `--parallel` | 10 | 同時に流す数。利用上限のエラーが出たら減らす |
| `--expand-grep` | 切 | 言い換え・関係語・聞き違いの語をモデルに出させて grep で足す経路 |
| `--meeting` | なし | パスまたは名前の一部で逐語を指定し、該当する逐語を丸ごと読ませる。複数指定可 |
| `--whole-meetings N` | 3 | 「直接」の記録が行の指定なしに指す逐語を、指す記録が多い順に N 本、丸ごと読ませる。0 で無効 |
| `--pad` | 20 | 出典の位置から前後を何行読むか |
| `--timeout` | `MSEARCH_TIMEOUT` → 900 秒 | 呼び出し1回の時間上限。独自の `--agent` も指定秒数で打ち切る |
| `--retries` | 2 | 失敗した呼び出しをやり直す回数 |
| `--out` | `MSEARCH_OUT_DIR` の下、または一時領域に実行ごとのフォルダを作る | 出力先を直接指定する。計画だけを書いたフォルダは再利用できる。実行中・本実行済みの場所や入力フォルダは拒否する。キット内では `local/`・`projects/` 配下だけに出力できる |

結果のフォルダには `plan.json`（区切りの計画）・`run.log`（実行記録）が出る。実行するとさらに `result.md`（先頭に**見た範囲**——どのファイルを・何区切り・何回・失敗した区切り・解けなかった出典。続いて A＝台帳・判断台帳で拾った記録を 直接／関連／周辺 の順、B＝逐語の関係する所を原文の行つきで）・`result.json`・`hits.json`・`stats.json`（呼び出し統計）が出る。モデルを呼んだ場合は `calls/` に依頼と各試行の答えを残す。**使い終わったら消してよい**（正本ではない）。

記録に入らなかった空でない行は、件数と先頭の行範囲を計画と結果の「見た範囲」に示す。台帳のメタ情報や判断台帳の前書きは別に数える。`--max-windows` で省いた窓の数も「見た範囲」と結果の件数に出る。

終了コード: `0`＝全部の呼び出しが成功、または計画のみの実行が成功／`3`＝失敗した区切りがある（結果は出るが `PARTIAL`。**別の回が同じ記録を拾っていても、失敗は失敗として出す**——補えたのは偶然で、次も補える保証が無い）／`2`＝使い方・設定の誤り。対象の台帳や判断台帳から記録を1件も読めない場合や、指定した案件フォルダが存在しない場合も終了する。

回答の JSON が途中で切れていた場合、読めた部分を救済として記録し、再試行する。完全な回答を得られなければ、拾えた番号を残して区切りを `FAILED` とする。逐語の回答で、渡した窓のIDが欠けていたり、指定の形式に合わなかったりした場合も再試行する。

`result.md` に表示するモデルの自由文は1行・200字以内に整える。引用には一次の記録の原文を使う。

## 手順の中身

1. **区切る** — 台帳と判断台帳を、1件を途中で切らずに区切る（日本語は1字≒1トークンで見積もる）。台帳の既定の読み方では、各セクションの直下にある `- id:` を記録の先頭とする。`--passes` 回ぶん、2回目以降は境目をずらす。
2. **下読み** — 区切りごとにモデルへ（`prompts/common.md`＋`prompts/scan.md`）。答えは JSON（番号・理由・聞き違いと読んだ語・強さ）。全回の和集合を取る。
3. **検算** — 返った番号が、渡した原文に在るかを機械で照らす。無い番号は捨てて、件数を結果に出す。
4. **言い換えの grep**（`--expand-grep` のときだけ）— 語の一覧をモデルに出させ（`prompts/terms.md`）、部分一致で当てる。ほとんどの記録に当たる語は捨てる。当たりが多ければ、当たった記録だけをもう一度判定させる。判定できなかった番号は `hits.json` の `unjudged_ids` に記録する。
5. **出典をたどる** — 拾った記録の `source` から一次の記録の場所を解き、前後を切り出して読ませる（`prompts/verbatim.md`）。引用は原文の行をそのまま取り、記録ごとの出典範囲に含まれる行だけを結び付ける。一部でも解けなかった位置は理由つきで一覧に出す。逐語の呼び出しに失敗した窓には `source` 経路を付けない。

### `source` の解き方

| 書き方 | 解き方 |
|---|---|
| `path/to/file.md:42` | 相対パスは明示した `--source-root` から探し、異なる実体が複数あれば未解決にする。指定が無ければ案件のフォルダから探す。案件名を指定せず台帳を直接渡した場合の既定は台帳の2つ上のフォルダ。見つかったファイルのその行の前後 |
| `talk:<逐語の名前（拡張子なし）>@HH:MM:SS` | 逐語の名前を完全一致で照合し、指定時刻以下で最も遅い時刻の行の前後。時刻の行が無ければ丸ごと読む。最後の時刻から60秒を超える指定は未解決 |
| `talk:HH:MM:SS` | 会議が書かれていないので、その記録の `fresh` の日付を名前に含む逐語が**ちょうど1本**のときだけ解く。0本・2本以上は「未解決」。1本に決まった後は会議名つきと同じ方法で読む |
| `mail:YYYY-MM-DD` | `--mail-dir` があり、日付を名前に含むファイルがちょうど1つのときだけ丸ごと読む |
| 上のどれでもない・`source` 無し | 「未解決（書式外）」「出典なし」として一覧に出る。文中の `L123`・`123行`・時刻・日付は、読める範囲で手がかりにする |

出典先を読む前に symlink を解き、実体が許可した根の内側にあるかを確認する。許可する根は `--source-root`、`--transcripts`、`--mail-dir`、および既定の根。根の外にある出典やUTF-8として読めない出典は「未解決」として理由を出す。`--transcripts` で探すのは `.txt`・`.md`・`.vtt`・`.srt` のファイル。

## プロンプトに必ず入る4点（`prompts/common.md`）

① 逐語は音声認識の文字起こしで、同じ音の別の字の誤りが多い。字面でなく、音と業務の意味で読む／② 業務の言葉（用語集を渡す）／③ 分かっている聞き違いの対応表／④ 迷ったら拾う・理由と聞き違いと読んだ語を添える・無いものを作らない。

**聞き違いの対応表は案件のもの**なので、スキルのフォルダには置かない。雛形（[`mishearings.md.example`](mishearings.md.example)・エントリ0件）を `projects/<name>/ledgers/mishearings.md` へコピーして、気づくたびに1行足す（どの逐語・どの記録で確かめたかを出典の欄に）。**逐語そのものは直さない。**

## 使うときの決まり

- **結果は下読みであって、正本ではない。** 拾った番号から、台帳・判断台帳・逐語の原文を開いて読んでから答える。
- 拾いは「漏らさない」側に倒してある（余計に拾う）。まず 直接 と 関連 を読む。**関係ありの判定の精度は測っていない。**
- **拾い漏れが無いことは保証しない。** モデルの拾いは回ごとにぶれる。読んだ行の範囲の外にある発言は拾えない。特定の逐語を丸ごと読ませるには `--meeting` を使う。
- 聞き違いの読みはモデルの読みで、人の確認ではない。
- 子に調べ物を頼むなら、親が先にこれを流して、結果のフォルダの場所を指示に添えると、子が正本を探し直す量が減る見込み（**効果は未計測**）。

## 安全

- 逐語とメールは第三者の文章で、間接的な指示の入り口になる。資料中の閉じタグは、依頼文の囲みを閉じない形に置き換える。**Claude Code では下読みの子に道具を1つも渡さない。** `--tools= --strict-mcp-config --no-session-persistence` で起こし、`AGENT_FLAGS` の権限の旗は引き継がない。子の出力は標準出力だけで、ファイルに書くのはスクリプト。返ってきた JSON は形と番号を検算してから使う。実物の Claude Code 2.1.331 をこの指定で起動したとき、初期化の出力で `tools` と `mcp_servers` がともに0件であることを確認した。
- Codex の子はOSの一時領域に作った空のフォルダから起動するため、案件のフックは掛からない。制約は読み取り専用の sandbox と、依頼の先頭に置く「道具を使わずに答える」という指示。接続先（コネクタ）を外す指定は無いため、起動時に標準エラーへ警告を出す。コネクタが設定されている環境で信頼できない逐語を渡すときは、この制約を承知して使う（[`../../../docs/inbound-loop.md`](../../../docs/inbound-loop.md)）。
- `--agent` は試験・差し替え用。差し替えたコマンドには道具の制限もモデルの確認も掛からない。
- 台帳・判断台帳・逐語は読むだけ。結果の置き場に入力のフォルダやスキルのフォルダを指すと断る。

## 設定（`config.env` と環境変数）

| キー | 意味 |
|---|---|
| `MSEARCH_CLI` | 下読みだけに使う CLI（`claude` または `codex`）。空なら `AGENT_CLI` の決まりに従う |
| `MSEARCH_MODEL` | 下読みのモデル。優先順は `--model` → `MSEARCH_MODEL` → `AGENT_MODEL_FAST`。**どれも空ならスキルは起動を断る**（数十回の呼び出しが、黙って既定の高いモデルへ落ちないように） |
| `MSEARCH_EFFORT` | 推論の強さ。明示した `--effort` が優先。どちらも空なら CLI の既定 |
| `MSEARCH_PARALLEL`・`MSEARCH_CHUNK_TOKENS`・`MSEARCH_PASSES` | 引数 → 環境変数 → `config.env` の単純な整数代入 → 既定値（10・25000・2）の順で選ぶ |

既定の呼び出しは [`scripts/ms_agent.sh`](scripts/ms_agent.sh) で、キットの `scripts/lib/agent_cli.sh`（`agent_run`）を通る。スキルを別の場所へコピーして使うときは、`MSEARCH_KIT_ROOT` でキットの置き場所を指す。

## かかるもの・分かっていること（元の作業場の報告）

元の実装を、ある受託案件の台帳で、答えの分かっている7つの論点（拾うべき記録は合わせて85件）に流した報告。**この同梱版で測り直した数字ではない。**

| 設定 | 拾えた数 | 1回の流し |
|---|---|---|
| 区切り5万・1回・grep なし | 85件中82件（落とした3件は、長い記録の1文・括弧書きにだけ論点が出る記録。同じ設定でも回によって拾えたり拾えなかったりした） | 3〜5.5分・呼び出し17〜20回 |
| 区切り2万5千・2回（境目をずらす）・grep あり | 85件中85件 | 5.5〜16分・呼び出し65〜82回 |

- 区切り2万5千・2回・grep ありの組合せで85件中85件を拾った。**言い換えの grep だけで足せた必須の記録は0件で、余計な件を増やしただけだった**ので、この同梱版では既定で切ってある（言い換えだけで書かれた記録での効き目は測れていない）。
- 推論の強さは既定と high を2つの論点で比べ、拾えた数は同じ・時間は約2倍だった（1回ずつなので断定はできない）。
- 利用枠の節約（上位のモデルが正本を読み直す量が減るか）は測っている途中で、数字は無い。

## 自分の台帳で確かめる

`sample/` に架空の案件（台帳・判断台帳・逐語2本・用語集・対応表・正解表）がある。

この見本（台帳14件・判断台帳5件）は、Claude Code の軽いモデルと Codex の軽いモデルでそれぞれ流し、2つの論点とも正解表の記録7件・引用6行を全部拾った。**見本は1区切りに収まる大きさなので、これは「実物のモデルで道が通る」ことの確認であって、再現率の測定ではない。** 区切りが何十にも分かれる台帳でどれだけ拾えるかは、自分の台帳と正解表で測る。

```sh
# 実モデルで見本を流して、正解表と突き合わせる（見本ではモデルを10回ほど呼ぶ。試験の一部ではない）
templates/skills/meaning-search/scripts/try_sample.sh

# 自分の正解表と突き合わせる（再現率と、拾い損ねの一覧）
result_dir="実行時に表示された result.md の親フォルダ"
answer_key="自分の正解表.json"
python3 templates/skills/meaning-search/scripts/score.py "$result_dir/result.json" "$answer_key"
```

正解表は、論点ごとに「拾うべき番号」と「逐語のファイル・行」を根拠つきで書いたもの（形は `sample/answer_key.json`）。正解表の相対パスは表の親フォルダを基準に解き、結果の引用元と実体が一致することを確かめる。**設定を変えたら、答えの分かっている論点で測り直す。**
