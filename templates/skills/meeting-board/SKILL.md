---
name: meeting-board
description: |
  A one-machine live meeting board. A small browser extension reads Google Meet's own live captions together with the speaker names, hands them to a tiny helper that listens on 127.0.0.1 only, and the helper periodically asks the local Claude Code (`claude -p`) to keep a structured, speaker-attributed "story so far". During the meeting the board shows only what can be read while talking — the next thing to say or ask, a red warning only when the talk drifts, contradicts a premise from the pre-meeting memo or is about to skip something, a one-line progress note, and the memo's "to ask / to tell" items as done / taken away / not yet. A second tab holds the full record (decisions, to-dos, open questions, premise conflicts, topics with who said what), which can be exported as a Markdown minutes draft. No audio is captured; nothing leaves the PC except what the local Claude Code itself sends. Use it to set it up on a work PC, to run it in a meeting, to export the minutes draft afterwards, or to fix the caption selectors when Meet changes its page.
  Meet の字幕（話者の名前つき）をブラウザ拡張が読み、127.0.0.1 だけで待ち受ける小さなヘルパーに渡し、手元の Claude Code（claude -p）に整理させて別窓に出す。会議中の画面は「次の一手」「警告（ずれ・前提と違う・言い忘れのときだけ）」「順調」「伝え済み／まだ」の 4 つだけ。全体の記録は「会議の前と後」タブにあり、議事録の素（Markdown）に書き出せる。音声は扱わない。会議用 PC への導入・会議中の運用・会議後の書き出し・Meet の画面が変わって字幕が読めなくなったときの直しに使う。
---

# meeting-board

**Meet の字幕を、話者つきで整理して別窓に出す**（手順と使い方は [`README.md`](README.md)）

```
Meet のタブ ── 拡張機能（content.js）── background.js ──▶ ヘルパー（helper/server.js・127.0.0.1:47431）
                  字幕の文字だけ読む                         │  字幕がたまったら claude -p へ
                                                             ▼
                                         別窓のボード（http://127.0.0.1:47431/）
```

## エージェントとして呼ばれたら — 完了の形と止まる場面

頼まれやすいのは、会議用 PC への導入の手伝い・会議の前の動作確認・「字幕が出ない」の切り分け・Meet の画面変更への追従。

**完了の形**:

1. `node templates/skills/meeting-board/tests/run.js` が全部通る（Node 18 以上のどれでも同じ。外部ライブラリなし・本物の `claude` は呼ばない）
2. 動作確認は `node helper/server.js --replay sample/sample_transcript.txt --notes sample/sample_notes.md --once` が、`next_action`（次の一手）・`checklist`（`state` が `done`／`deferred`／`open`）・`topics` のある JSON だけを標準出力に出して終了コード 0（これは手元の `claude` を 1 回呼ぶ。架空の会議なので送ってよい）
   画面は、偽 claude（`CLAUDE_BIN=tests/fixtures/claude_stub.js`・`STUB_BOARD=tests/fixtures/board_v2_sample.json`）で `--replay` を立て、`http://127.0.0.1:<port>/`（会議中）と `/?view=after`（会議の前と後）を見る
3. 拡張機能は人が `chrome://extensions` で読み込む。**エージェントは「拡張機能が動いた」と書かない**——Meet のページを実機で見たのは人だけ

**止まって人に聞く場面**:

- 🔴 待ち受けを `127.0.0.1` 以外にする前・外へ出る通信（`claude` 以外）を足す前・`manifest.json` の権限や `host_permissions` を増やす前
- 🔴 `data/` の中身（実際の会議の逐語）を読む・貼る前。診断（ボードの「診断をコピー」・`GET /diag`）は発言を含まない作りなので、こちらを頼む
- 🔴 `helper/prompt.md`・`helper/prompt_patch.md` を変える前（出力の形がボードと試験の前提になっている。変えるなら `lib/board.js`・`board-core.js`・`board.html`・試験も揃える。`lib/extract.js` の `normalizeBoard()` は 0.1 の形の土台なので変えない）
- 🔴 議事録の素（`--minutes`）を、ファイルと標準出力以外へ送る仕組みを足す前（メール・チャットなどへの自動送信はしない作り）

## Meet の画面が変わって字幕が読めないとき

読み取りの要所は `extension/content.js` の `locate()`（字幕の領域を探す 5 つの手順）と `findBlocks()`（話者ブロックを探す）。診断の `tree` は、字幕の領域の下を 3 段、タグ・クラス名・子の数・文字数（長さだけ）で写してある。**診断 1 つあれば、実際の字幕の構造を再現した固定ページを作って、`content.js` を直せる**（本文は要らない）。現行の Meet は、字幕の領域が `[role="region"]` で aria-label が「字幕」、子が 2 つ（字幕の入れ物と「最新の字幕に移動」ボタン）。

## 構成

| 場所 | 役割 |
|---|---|
| `extension/captions-core.js` | 結合規則（同じブロックの書き換えは最新の文面で置き換え・頭の切り詰めだけ積み上げる）・話者の読み取り・ブロックの追跡。DOM に触らない純粋な関数（拡張機能と Node の試験の両方から読む） |
| `extension/content.js` / `background.js` | 画面の読み取りと診断 / ヘルパーへの送信・バッジ |
| `helper/server.js` + `helper/lib/*.js` | 起動・HTTP・claude の呼び出し・整理の間隔・保存。`prompt.md` はそのまま使う |
| `helper/lib/notes.js` | 事前メモから「今日聞くこと・伝えること」「こちらの理解・前回の決定」「自分：名前」を読む（表の文言と順番を固定する） |
| `helper/lib/board.js` | claude の返事を schema 2 のボードに整える（話題の id・聞くことの 3 状態・次の一手の規則の補い・警告の検証・前提と食い違ったことの記録・差分の重ね合わせ・人が直した状態）。何が来ても例外を出さない |
| `helper/lib/script.js` | 台本（`--script`）を節と台詞に分け、直近の字幕から「いま台本のどこか」を規則で当てる（claude は使わない） |
| `helper/lib/importers.js` | `--replay` の文字起こしの形を見分ける（「話者：本文」・WebVTT・「名前 時刻」＋本文。Teams・Zoom の形は推定で、実物では未確認） |
| `helper/prompt_patch.md` | 差分の整理（2 回目から）のときだけ `prompt.md` のあとに足す、出力の決まり。`board.js` の `mergePatch()` が前回のボードに重ねる |
| `helper/lib/minutes.js` | 保存したボードから議事録の素（Markdown）を作る（`--minutes`） |
| `helper/board-core.js` | 画面に何を出すかを決める純粋な関数（会議中 / 会議の前と後・古い内容の判定）。`GET /` で `board.html` に埋め込む |
| `helper/board.html` | ボード（1 ファイル・外部リソースなし）。会議中（既定）と「会議の前と後」のタブ |
| `sample/` | 架空の会議と事前メモ（`--replay` 用） |
| `tests/eval/score_board.js` | 品質の物差し（手で回す・`node --test` には入れない）。付属の会議の `--once` の結果を採点する |
| `tests/` | `node:test`。偽の `claude`（`tests/fixtures/claude_stub.js`）で全部を試す。`tests/fixtures/board_v2_sample.json` は画面と議事録の確認用の架空のボード |
| `data/` | 実行時の保存先。`.gitignore` で中身はコミットできない |

画面は 3 つの場面で使い分ける: 会議の前（事前メモを貼り、「会議の前と後」タブで読めたか確かめる）／会議中（次の一手・警告／順調・伝え済み／まだ だけ。項目を押すと状態を直せる）／会議の後（「会議の前と後」タブで振り返り・状態を直し、`--minutes` で議事録の素）。人が直した状態は `POST /override` で会議フォルダの `overrides.json` に残り、整理より優先する。

主なオプション: `--notes` 事前メモ・`--script 台本.md`（会議中の画面に台本の位置と直近の字幕）・`--me 名前` 字幕に出る自分の名前・`--mode diff|full`（既定 full＝毎回全体。diff＝2 回目から差分の整理・試験中）・`--replay ファイル`（`--speed auto` が既定。行に `[時:分:秒]` があればその間隔）・`--once`・`--minutes 会議フォルダ [--out ファイル]`・`--data-dir`。

守る線: ヘルパーは `127.0.0.1` だけ・`X-Meeting-Board: 1` の札と Host の確認が無ければ断る・診断に字幕の本文と名前を入れない・音声は扱わない。
