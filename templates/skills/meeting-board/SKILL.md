---
name: meeting-board
description: |
  A one-machine live meeting board. A small browser extension reads Google Meet's own live captions together with the speaker names, hands them to a tiny helper that listens on 127.0.0.1 only, and the helper periodically asks the local Claude Code (`claude -p`) to keep a structured, speaker-attributed "story so far" — topics, who said what, decisions, to-dos, numbers, open questions — plus, if you pasted a pre-meeting memo, a checklist of the things to ask and up to three reminder cards. The result is shown on a board page in a separate browser window. No audio is captured; nothing leaves the PC except what the local Claude Code itself sends. Use it to set it up on a work PC, to run it in a meeting, or to fix the caption selectors when Meet changes its page.
  Meet の字幕（話者の名前つき）をブラウザ拡張が読み、127.0.0.1 だけで待ち受ける小さなヘルパーに渡し、手元の Claude Code（claude -p）に「ここまでの話」を整理させて別窓に出す。事前メモがあれば「聞くことの表」とカード（最大3枚）も出る。音声は扱わない。会議用 PC への導入・会議中の運用・Meet の画面が変わって字幕が読めなくなったときの直しに使う。
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
2. 動作確認は `node helper/server.js --replay sample/sample_transcript.txt --notes sample/sample_notes.md --once` が、`topics`・`checklist`・`cards` のある JSON だけを標準出力に出して終了コード 0（これは手元の `claude` を 1 回呼ぶ。架空の会議なので送ってよい）
3. 拡張機能は人が `chrome://extensions` で読み込む。**エージェントは「拡張機能が動いた」と書かない**——Meet のページを実機で見たのは人だけ

**止まって人に聞く場面**:

- 🔴 待ち受けを `127.0.0.1` 以外にする前・外へ出る通信（`claude` 以外）を足す前・`manifest.json` の権限や `host_permissions` を増やす前
- 🔴 `data/` の中身（実際の会議の逐語）を読む・貼る前。診断（ボードの「診断をコピー」・`GET /diag`）は発言を含まない作りなので、こちらを頼む
- 🔴 `helper/prompt.md` を変える前（出力の形がボードと試験の前提になっている。変えるなら `lib/extract.js`・`board.html`・試験も揃える）

## Meet の画面が変わって字幕が読めないとき

読み取りの要所は `extension/content.js` の `locate()`（字幕の領域を探す 5 つの手順）と `findBlocks()`（話者ブロックを探す）。診断の `tree` は、字幕の領域の下を 3 段、タグ・クラス名・子の数・文字数（長さだけ）で写してある。**診断 1 つあれば、実際の字幕の構造を再現した固定ページを作って、`content.js` を直せる**（本文は要らない）。現行の Meet は、字幕の領域が `[role="region"]` で aria-label が「字幕」、子が 2 つ（字幕の入れ物と「最新の字幕に移動」ボタン）。

## 構成

| 場所 | 役割 |
|---|---|
| `extension/captions-core.js` | 結合規則・話者の読み取り・ブロックの追跡。DOM に触らない純粋な関数（拡張機能と Node の試験の両方から読む） |
| `extension/content.js` / `background.js` | 画面の読み取りと診断 / ヘルパーへの送信・バッジ |
| `helper/server.js` + `helper/lib/*.js` | 起動・HTTP・claude の呼び出し・整理の間隔・保存。`prompt.md` はそのまま使う |
| `helper/board.html` | ボード（1 ファイル・外部リソースなし） |
| `sample/` | 架空の会議と事前メモ（`--replay` 用） |
| `tests/` | `node:test`。偽の `claude`（`tests/fixtures/claude_stub.js`）で全部を試す |
| `data/` | 実行時の保存先。`.gitignore` で中身はコミットできない |

守る線: ヘルパーは `127.0.0.1` だけ・`X-Meeting-Board: 1` の札と Host の確認が無ければ断る・診断に字幕の本文と名前を入れない・音声は扱わない。
