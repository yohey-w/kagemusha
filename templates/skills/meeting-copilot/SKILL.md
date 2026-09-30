---
name: meeting-copilot
description: |
  A two-machine live meeting copilot. A Windows laptop streams two audio channels (your mic, and a loopback of the other side's voice) to a parent machine, which transcribes them, drives a teleprompter you read from, watches every incoming utterance against a ledger of pre-agreed facts, and answers off-script questions. Ships the parent daemons, the Windows capture agent, and worked config examples. Consumes raw transcripts only — never a meeting-AI summary. Use it the night before a meeting to build the meeting folder and check startup, during the meeting to run it, and afterwards to check what it fired against the transcript.
  会議に同席してリアルタイムで進行ナビ・前提監視・台本外質問への回答を行う2台構成のモニタ。子機(Windowsノート)が2系統の音声を親機へ送り、親機が文字起こし・カード生成・画面配信を行う。親機の常駐一式・子機の取り込み一式・設定の実例つき。入力は逐語のみで、議事録AIの要約は使わない。会議の前夜に会議フォルダを用意して起動を確かめるとき・会議中に動かすとき・会議後に年表で検証するときに使う。
---

# meeting-copilot

**会議に同席して、進行と前提を見張るモニタ一式**

> **English abstract** — Two machines. The **child** (a Windows laptop, in the meeting) captures two physical audio channels — `T` = your microphone, `G` = a WASAPI loopback of the default speaker — and streams both to the **parent** over TCP with a shared token. The parent transcribes each channel separately (speaker identity comes from the *channel*, never from diarization), then runs three layers over the transcript: a rule-only warden (`copilot.py`) that advances the agenda and fires boundary alarms with no LLM at all; a premise watcher (`premise_watch.py`) that classifies every guest utterance against a ledger of pre-agreed facts as contradiction / already-known / new; and an answerer (`answerer.py`) for off-script questions. A teleprompter (`viewer2.py`) serves two different pages — a **prompt screen** only you see on your phone, and a **stage window** you actually screen-share. Everything case-specific lives in config files; the code carries no customer data. Written mainly in Japanese; the structure is language-independent.

## エージェントとして呼ばれたら — 完了の形と止まる場面

頼まれやすいのは、会議の前夜の準備（会議フォルダを作る・進行表から台本を生成する・起動を確かめる）と、会議後の検証（年表と逐語の突き合わせ・検知キーワードと即答表の手直し）。

**前夜の準備の完了**は次の4つがそろった状態:

1. `python3 scripts/build_agenda.py <進行表.md> --out <会議フォルダ> --check` が終了コード0（「（要記入）」の欄が残っていない）
2. `MEETLIVE_MEETING=<会議フォルダ>` を指したうえで `python3 scripts/copilot.py --selfcheck` を走らせ、`同梱の例を読みます` の警告が0件
3. このスキルの `scripts/run.sh --dry-run` の出力（起こす層・ポート・状態ディレクトリ）を人に見せた
4. 子機の2窓の接続とイヤホンは**人が**確かめる。エージェントは確かめたと書かない

**止まって人に聞く場面**（会議の中身が外へ出る・秘密に触れる）:

- 🔴 `decision_backend` を `jev` / `llm` にする前、`replay_eval.py` を `--backend jev` / `llm` で実際に送る前。先に `--dry-run` で送る物を見せる
- 🔴 `MEETLIVE_KNOWLEDGE_DIR` を指す前・`kb/` に資料を置く前（置いたものはそのまま LLM へ送られる）
- 🔴 `roster.txt` を作らずに `--allow-no-roster` で押し切る前
- 🔴 合言葉・鍵の値をファイルや会話に書くことになりそうなとき。書かない——置き場は会議フォルダの外、鍵は環境変数（§1.5・§1.8（[`decision-layer.md`](references/decision-layer.md)））

**会議の最中に壊さない**: 走っている層を畳まない。止めるときは `stop.sh`（停止ファイル）で、`kill` / `pkill` は使わない（§3.2.5・§7.1（[`troubleshooting.md`](references/troubleshooting.md)））。

## 参照ファイル（いつ読むか）

本文は、全体像・使い方・起動と停止・安全の境界を持つ。細目は同じスキルの `references/` にある。節番号は本文と参照ファイルで共通。

| ファイル | 節 | いつ読むか |
|---|---|---|
| [`references/decision-layer.md`](references/decision-layer.md) | §1.8 | 判定層を `rules` 以外で回すとき・問いや閾値を触るとき・`replay_eval.py` で採点するとき |
| [`references/env-vars.md`](references/env-vars.md) | §2 | 会議フォルダを使わず環境変数で指すとき・既定値やモデル設定を確かめるとき |
| [`references/setup-manual.md`](references/setup-manual.md) | §3.2 手動起動・§3.3 | `run.sh` を使わず手で上げるとき・起動順を正確に知りたいとき・子機（Windows）を準備するとき |
| [`references/meeting-folder.md`](references/meeting-folder.md) | `meeting.json`・§6 | 会議フォルダを用意するとき（キーの一覧・進行表・事実台帳・即答表・台本の書き方） |
| [`references/design-notes.md`](references/design-notes.md) | §5 | 罠の理由と実測を確かめたいとき・設定を変える前 |
| [`references/troubleshooting.md`](references/troubleshooting.md) | §7 | 音が届かない・カードが出ない・ポートを差し替えたいとき、稼働ラインの読み方 |
| [`references/files.md`](references/files.md) | §8 | 同梱ファイルの役割を確かめたいとき |

---

## 0. 全体像 — これは2台構成である

一番よくある取り違えが「1台で完結する道具だと思う」こと。**必ず2台要る。**

```
┌─ 子機 (Windows ノートPC・会議に持っていく機体) ────────────┐
│                                                              │
│   マイク ────────────► agent_mic.py  ──┐  ch "T"            │
│                                          │                   │
│   既定スピーカーの                       │                   │
│   ループバック ─────► agent_loop.py ──┤  ch "G"            │
│                                          │                   │
│   音を録って送るだけ。STTもAPIキーも持たない                │
└──────────────────────────────────────────┼──────────────────┘
                                            │
                   TCP + 合言葉(token)      │  16kHz mono ×2本
                   プライベート網(tailscale等)を想定
                                            │
┌─ 親機 (Linux / WSL・自宅や事務所に置きっぱなし) ───────────┼───┐
│                                            ▼                    │
│   receiver.py  … 音を受けて STT へ流し transcript.jsonl へ追記 │
│        │                                                        │
│        ├──► copilot.py       … ルールだけで段の進行・境界警報   │
│        │        ├──► premise_watch.py … 相手の発話×事実台帳     │
│        │        └──► answerer.py      … 台本外の質問に回答      │
│        │                                                        │
│        └──► viewer2.py       … カンペ画面 + 舞台画面を配信      │
└─────────────────────────────────────────────────────────────────┘
        │                              │
        │ カンペ画面(自分だけ見る)     │ 舞台画面(相手に画面共有する)
        ▼                              ▼
    スマホ / 携帯ディスプレイ      名前付き別窓 meetlive_stage
```

### イヤホン／イヤモニが必須な理由は、この構成に直結している

話者の分け方が**物理チャンネル**だからである(`receiver.py` の `CH_SPEAKER = {"T": "host", "G": "guest"}`)。
STT の話者分離(diarization)には一切頼っていない。安いし速いし確実——**ただし1つだけ前提がある**。

> 子機のスピーカーで相手の声を鳴らすと、ch `G`(相手の声)として送っている音を
> ch `T`(自分のマイク)が拾い直し、**同じ声が2チャンネルに二重計上される**。
> こうなると相手の発話が `speaker="host"` として記録される。

そして `host` / `guest` の区別は、この道具の土台になっている:

| 何が壊れるか | どこで効いているか |
|---|---|
| 段の進行が勝手に進む | 段の検知キーワードは **host の発話だけ**に当てる (`copilot.auto_step`) |
| 前提監視が黙る/誤爆する | 前提監視を撃つのは **guest の発話のとき**だけ (`copilot.feed`) |
| 呼びかけが効かない/暴発する | 呼びかけ語の検知は **host の発話だけ** (`receiver.Writer.emit`) |
| 台本外の質問への回答が暴走する | answerer を呼ぶのは **guest の質問**のときだけ |

つまり**イヤホンを忘れると、モニタの機能がほぼ全部おかしくなる**。
`receiver.py --xtalk-gate` は「T の音量より G の音量が1.5倍大きければ T を捨てる」という
**保険**だが、解決ではない。イヤホンを挿すこと。

---

## 1. 層の一覧 — 何がどこまでやるか

| 層 | ファイル | LLM | いつ動くか |
|---|---|---|---|
| 逐語化 | `receiver.py` + `stt.py` | 使わない | 音が来るたび |
| 番人(第1層) | `copilot.py` | **使わない** | 逐語1行ごと。ルールと文字列照合だけ |
| 前提監視 | `premise_watch.py` | 量産呼び出し | **相手の発話ごとに毎回** |
| 回答(第2層) | `answerer.py` | 一発呼び出し | 台本外の質問のときだけ(30秒に1回まで) |
| 返し役 | `responder.py` | 一発呼び出し | 相手の発話がひと区切りするたび |
| 表示 | `viewer2.py` | 使わない | 長ポーリングで配信 |
| 判定層 | `decision_engine.py` | 差し替え式 | 発話1本ごと(§1.8（[`decision-layer.md`](references/decision-layer.md)）。判定器→小型LLM→ルールの順に退避。本線の外で走り、重ねるのは最大3本) |
| 事後検証 | `action_log.py` | 使わない | 会議のあと |
| 採点 | `replay_eval.py` | 使わない | 会議のあと(過去の逐語を流し直す) |

**なぜ第1層に LLM を置かないか**: 会議中は「速い・落ちない・同じ入力に同じ出力」が
何より効く。段の進行と約束の境界(金額・期限・責任)の検知は、キーワード照合で足りる。
LLM を挟むと、その分だけ遅れ、その分だけ落ちる。

**`answerer.py` と `responder.py` の違いは構え**。answerer は「答えを作る」、responder は
**「台本のどこを読み上げればよいかを指す」**。だから responder の出力は毎回 ①該当する節
②そのまま言える返し ③言ってよい数字 ④🚫言ってはいけないこと1つ、の4点に固定してあり、
材料(`kb/`)は**全文**を渡す(切り詰めが何を起こすかは §5.8（[`design-notes.md`](references/design-notes.md)）)。台本があって「その通り話したい」
会議は responder、台本が薄く「その場で答える」会議は answerer。**同時には使わない**。

---

## 1.5 会議フォルダ — 案件固有はここにしか無い

**コードは1本。案件ごとに変わるのは「会議フォルダ」の中身だけ**、という形にしてある。
会議のたびにフォルダを1つ作り、`MEETLIVE_MEETING` でそれを指す。それ以外の環境変数は、
古い運用のための後方互換として残してあるだけで、ふだんは触らない。

```
<会議フォルダ>/                  例: ~/meetings/2026-01-20-acme/ (git に載せない場所)
  meeting.json                  今日の構え(下の表)。この1枚が入口
  agenda_steps.json             段と必須取得物
  talk_script.md                台本(テレプロンプターの中身)
  phrasebook.json               定型回答・約束の境界の文言
  stage_resources.json          舞台に出せるもの(URL・画像・声で呼ぶ語)
  ledger.yaml                   事実台帳(前提監視の基準・任意)
  bank.json                     先読み回答(任意)
  kb/                           台本外の回答の材料。🔴 置いたものはそのままLLMへ送られる
  docs/                         資料棚。会議中に画面のボタンで開く手元資料(.md/.txt/.html)
```

```bash
export MEETLIVE_MEETING=~/meetings/2026-01-20-acme
export MEETLIVE_DIR=~/meetlive_state/2026-01-20-acme      # 省略時は ./meetlive_state/<フォルダ名>
export MEETLIVE_CREDS_FILE=~/secrets/acme_logins.md       # 🔴 会議フォルダの外
python3 scripts/viewer2.py --port 47328
```

### 解決の順番（キー単位・迷ったらこの順）

1. **会議フォルダの中のファイル** … あればこれが勝つ
2. **個別の環境変数**（`MEETLIVE_AGENDA` 等）… 会議フォルダに無いときだけ
3. **同梱の `config/*.example`** … どちらも無いとき。必須の入力は stderr に警告を出す

前の案件の `MEETLIVE_AGENDA` がシェルに残っていても、会議フォルダが勝つので事故らない。
逆に、**環境変数が指すファイルが存在しないときは例へ落ちずに止まる**(黙って別の案件の
台帳を読んでいた、が起きないように)。会議フォルダ自体が無いときも同じく止まる。

`meeting.json` の各キー（既定値つき）は [`references/meeting-folder.md`](references/meeting-folder.md)。
画面上段の「受信・逐語・心拍」の稼働ラインで、材料が来ていないのか機構が落ちているのかを見分けられる（読み方は [`references/troubleshooting.md`](references/troubleshooting.md) の 7.5）。

### 秘密の置き場 — 会議フォルダには置かない

合言葉・管理画面のログインは `MEETLIVE_CREDS_FILE` で**会議フォルダの外**を指す。
会議フォルダは資料置き場なので、うっかりリポジトリに載る事故が起きうるため。

書式は md の表。`| 用途 | URL | 合言葉 |` の行だけを拾う:

```markdown
| 用途 | URL | 合言葉 |
|---|---|---|
| 管理画面 | https://example.com/admin | `xxxxxxxx` |
```

この中身は**HTMLに一切埋め込まない**。手元の画面が `/creds` を叩いた瞬間にだけ読む。
共有する別窓(`/stage/*`)はこの経路に触れないので、画面共有に合言葉は映らない
(この不変条件は `tests/test_viewer_state.py` が毎回確かめている)。

---

## 1.8 判定層の要点（詳細は [`references/decision-layer.md`](references/decision-layer.md)）

番人のキーワード照合は、書いた言葉と同じ言葉が出たときしか当たらない。判定層は、その判定を**差し替えられる口**にする層で、発話ごとに決めた問い（段・局面・発話の種類・探し物・約束）へ確率つきで答える。

| 実装 | 何をするか | 外へ出るか |
|---|---|---|
| `RulesBackend` | いまのキーワード判定を同じ問いの形に包んだもの | **出ない**（既定） |
| `JevBackend` | 設定した宛先へ REST で1往復 | 出る |
| `LLMBackend` | 同じ問いの束を小型 LLM に JSON で答えさせる | 出る |

Jev は、問いの束に確率つきで答える外部の判定モデル（README の例では TypeSafe の小型分類器を Vercel AI Gateway 経由で呼ぶ）。退避の順は `fallback_chain` で決まり、最後は必ず `rules` になる。

- 🔴 **この道具は宛先を内蔵しない。** 送り先・鍵の環境変数名・モデル名は設定ファイル側。既定の `decision_backend: "rules"` なら外へ1バイトも出ない
- 🔴 **外へ送るのは直近K発話だけで、人名は送る物の全体で伏せる。** ただし名簿の関門は `roster.txt` が在って中身が1件以上あるときだけ開く。無ければ `replay_eval.py` は止まり、会議中は外へ送る段を組み立てない
- 🔴 **これは匿名化の保証ではない。** 書き漏らした名前は素通りする。何が出るかは `--dry-run` と `decisions.jsonl` に残った送った物の現物で判断する
- 🔴 **鍵はファイルに書かない。** 設定に書くのは環境変数の名前だけ
- 判定の答えを画面に出すのは `show_decision_cards: true` のときだけ（既定は記録だけ）。**閾値は先に `replay_eval.py` で実測してから**画面に出す

---

## 2. 環境変数リファレンス（後方互換）

**ふだんは `MEETLIVE_MEETING` 1本でよい**（§1.5）。会議フォルダを使わない場合と、会議フォルダに置けないもの（状態Dir・秘密・モデル）の一覧は [`references/env-vars.md`](references/env-vars.md)。未設定でも**顧客データへは絶対に落ちない**（落ちる先は `./meetlive_state` と同梱の `config/*.example` だけ）。環境変数が指すファイルが存在しないときは、例へ落ちずに止まる。

### 2.1 🔴 `MEETLIVE_KNOWLEDGE_DIR` に何を置くかは、そのまま「LLMへ送るもの」を決める

`answerer.py` はこのディレクトリ直下の `.md` / `.txt` を**名前順に全部**、逐語でプロンプトへ載せる。ファイル名の allowlist は無い。**案件フォルダをまるごと指さず**、送ってよい資料だけを置いた専用ディレクトリを指す（✗ と ✓ の例は [`references/env-vars.md`](references/env-vars.md) の 2.1）。

---

## 3. セットアップ

### 3.1 前提

- **親機**: Linux または WSL2。Python 3.9+。**`claude` か `codex` のどちらかの CLI**が
  PATH にあり、認証済みであること。`premise_watch.py` / `answerer.py` / `responder.py` は
  `scripts/agent_cli.py` 経由でサブプロセスを起動する(claude なら
  `claude -p <prompt> --model <m> --effort <e>`、codex なら
  `codex exec -m <m> -c model_reasoning_effort=<e> --ephemeral -s read-only -o <tmp> <prompt>`)。
  どちらも無いと、この3つは黙って何も出さない。使う CLI は `MEETLIVE_AGENT_CLI` で固定できる
  (未指定なら PATH にある方・両方あれば `claude`)
- **子機**: Windows ノートPC。Python 3.9+(`setup.cmd` が無ければ winget で入れる)
- **2台をつなぐ網**: 子機から親機の TCP ポートへ届くこと。実運用では tailscale 等の
  プライベート網を想定。同じ LAN 内なら LAN の IP でよい
- **STT の API キー**: Deepgram(`DEEPGRAM_API_KEY`)または OpenAI(`OPENAI_API_KEY`)。
  **キー無しでも `--backend stub` で配管の検証だけはできる**(発話区間を検知して
  `[STUB] host の発話 1.2秒` のような行を transcript へ書く。話者・時刻・遅延・
  jsonl の形式は本番と完全に同じ経路を通る)
- **イヤホン／イヤモニ**(§0を読むこと。任意ではない)

### 3.2 親機のセットアップ

```bash
# 1) 置き場を作る
cd <このスキルの scripts/ を置いた場所>
python3 -m venv venv
./venv/bin/pip install numpy websockets pyyaml
```

依存はこれだけ(実際の import から数えたもの):

| 部品 | どこで使うか |
|---|---|
| `numpy` | `receiver.py`(リサンプラ・音量測定)、`stt.py`(VAD・PCM変換) |
| `websockets` | `stt.py` の OpenAI / Deepgram バックエンド(関数の中で import している) |
| `pyyaml` | `premise_watch.py` が事実台帳を読む |

`copilot.py` / `viewer2.py` / `answerer.py` / `action_log.py` / `meetlive_config.py` は
**標準ライブラリだけ**で動く。

案件の入力を環境変数で1本ずつ指して、各層を手で起動する手順は [`references/setup-manual.md`](references/setup-manual.md)。ふだんは下の `run.sh` を使う。
会議より前に上げるなら、`--start` を必ず明示する（省略すると番人の側だけ起動時刻が開始になり、会議前から「予定超過」のカードが出る。詳細は同じ参照ファイル）。

### 3.2.5 起動と停止 — `run.sh` / `stop.sh`

親機の層（`receiver.py` / `copilot.py` / `viewer2.py`）を毎回手で並べるかわりに、**会議フォルダ1つを渡して必要な層だけ起こす**口がある。
起こす層は `meeting.json` の `features` が決める。

```bash
export MEETLIVE_MEETING=~/meetings/2026-01-20-acme
export MEETLIVE_DIR=~/meetlive_state/2026-01-20-acme
export MEETLIVE_CREDS_FILE=~/secrets/acme_logins.md   # 🔴 会議フォルダの外
export MEETLIVE_PYTHON=$PWD/venv/bin/python            # 省略時は python3

./run.sh --dry-run                       # 何をどう起こすかを見るだけ（前夜にこれを見る）
./run.sh --port 47323 --backend deepgram --keywords "固有名詞,を,カンマ区切り"
./stop.sh --port 47323
```

ログは状態ディレクトリの `logs/<層>.log`、pid は `logs/<層>.pid`。

| 層 | `features` のキー | 備考 |
|---|---|---|
| `receiver.py` | `receiver`(既定 true) | 子機が繋ぐ先。**先に上げる** |
| `viewer2.py` | (常に起こす) | これが無いと何も見えない |
| `copilot.py` | `copilot` | 進行の番人。ルールだけ |
| `responder.py` | `responder` | そのまま言える返し。材料は `kb/` 全量 |
| `premise_watch.py` | `premise_watch` | **常駐ではない**。copilot が発話ごとに起こす子プロセス |

**`copilot` と `responder` を両方 true にはできない**（同じ `cards.jsonl` に書くので、
片方のカードがもう片方を押し出す）。`run.sh` は両方 true なら起動せずに止まる。
`features` の既定は全部 true なので、`meeting.json` でどちらか一方を false にしておく（同梱の `config/meeting.example.json` も両方 true のままなので、写したら直す）。
**`premise_watch: true` でも `copilot: false` なら前提監視は動かない**（起こす親がいない）。
`run.sh` はその組み合わせのとき警告を出す。**8時に画面を見てから気づく類の穴なので、前夜の
`--dry-run` で読むこと。**

#### 停止 — 全層で1つのファイル。`kill` は使わない

停止の合図は **`<状態Dir>/meetlive.stop` を1つ置くだけ**。各層がそれを見に行き、
**自分で**終わる。`stop.sh` はそのファイルを置き、ついでに viewer2 の `/quit` も叩く。

| 層 | 見る周期 | ほかの口 |
|---|---|---|
| `copilot.py` | tail の周回（0.3秒） | 終話を検知したら**自分でこのファイルを置く** |
| `receiver.py` | 2秒 | — |
| `viewer2.py` | 2秒 | HTTP `GET /quit`（localhost からのみ） |
| `responder.py` | 周回ごと | 自分あての `responder.stop` |

`run.sh` は起動前に**前回の停止ファイルを片付ける**（残っていると、起こした層が起動した
瞬間に自分で終わり、「画面は上がるのに番人が居ない」という一番分かりにくい壊れ方をする）。
`kill` / `pkill` は会議中に走っている別の python を巻き込み、書きかけの逐語やカードを
壊すので使わない（§7.1（[`troubleshooting.md`](references/troubleshooting.md)） も同じ理由）。

##### 終話の自動検知 — 会議の最中には止めない

会議のあとプロセスが残ると、誰も見ていない画面に同じカードを描き続ける（実走の記録は §5.9（[`design-notes.md`](references/design-notes.md)））。
番人が終話を検知して自分で畳むのがこの機構。

畳む条件は3つ。**どれも「無音」とセット**になっている:

| 合図 | 条件 |
|---|---|
| 長い無音 | 双方の発話が `auto_stop.silence_min`（既定10分）来ない |
| 別れの言葉 | `phrasebook.json` の `farewell_words` → そのあと `farewell_grace_min`（既定5分）の無音 |
| 予定の終わり | `end` + `end_grace_min` を過ぎ、**かつ** `farewell_grace_min` の無音 |

**予定を過ぎただけでは止めない。** 実際の会議は予定を大きく超えることがある（§5.9（[`design-notes.md`](references/design-notes.md)））。
「予定＋猶予で停止」だと会議の真っ最中に3層とも落ちる。会議の最中に落ちる害のほうが、
畳み忘れの害より大きい。同じ理由で、無音の閾値は秒ではなく**分**で置いてある
（実測で会議の途中に150秒の片側ギャップがあった）。
`farewell_words` に「ありがとうございました」「よろしくお願いします」を**入れないこと**
——日本語の商談では会議の途中に何度も出る。

### 3.3 子機(Windows)のセットアップ

`scripts/portable/` の中身をそのままノートPCへ持っていき、`setup.cmd` → `config.txt` を書き換え → **イヤホンを挿す** → `START.bat`。窓が2つ開き、**2つとも「送信中」になって初めて成功**。手順の全体・同梱ファイルの役割・子機と親機をつなぐ線の仕様は [`references/setup-manual.md`](references/setup-manual.md)。
🔴 `config.txt` は**親機のアドレスと合言葉が平文で入るファイル**。git に入れない・他人に渡さない。配るのは `config.txt.example` の方だけ。

---

## 4. 使い方

### 4.1 2つの画面の違い（取り違えると事故る）

| | カンペ画面 | 舞台画面 |
|---|---|---|
| URL | `http://<親機>:47323/` | `http://<親機>:47323/stage/...` |
| 誰が見るか | **自分だけ**。スマホ／携帯ディスプレイで見る | **相手**。これを画面共有する |
| 中身 | 段の一覧・台本・カード・舞台の操縦ボタン | 資源1枚だけ(黒画面・スライド・画像など) |

舞台は `window.open(url, 'meetlive_stage')` で開く**名前付きの1枚の窓**。
共有するのはこの窓だけで、中身が声やボタンで切り替わる。
iframe は使っていない(相手先サイトが `x-frame-options: DENY` だったり、ログイン
cookie が `SameSite=lax` だったりして中身が出ないため)。

カンペ画面をPCに出すと画面共有に映り込むので、**カンペはスマホで見る**。

`?theme=washitsu` を付けると和風の見た目になる(既定は暗い配色)。

起動のたびに、カンペの上部へ**舞台の使い方3行**が1回だけ出る（「分かった」で消える）。
手順が資源表にしか無いと、会議の冒頭で操作が分からなくなるため（実走の記録は §5.9（[`design-notes.md`](references/design-notes.md)））。

### 4.1.5 カードの読み方 — 必ず3行

カードはすべて同じ形をしている。**上から順に読めば、そのまま声に出せる**。

```
 進行      進行役へ   未解決 4回              10:47:10   [済]
 対象   メール配信サービスの契約名義
 状況   まだ取れていません
 言うこと 「ご契約は御社名義でよろしいですか」            ← これを読む
```

| 行 | 意味 |
|---|---|
| 【対象】 | 何についての話か。**内部ID（`F-011` 等）は本文に出さない**——台帳の事実文が出る |
| 【状況】 | 何が起きた・何が分かった |
| 【言うこと】 | その場でそのまま読み上げられる完成文。**大きく出ているのがこれ** |

右上のラベル:

- **進行役へ** … 声に出すもの
- **記録のみ** … 裏で記録しただけ（舞台の切替・「考え中…」など。読まなくてよい）
- **未解決 N回** … 同じ対象の催促が N 回目。**同じカードは積み上がらない**

**なぜこの形か。** 対象だけあって「何が問題で・何を言えばよいか」が本文に無いカードは、読んでも動けない。
同じ文言の催促を繰り返すと、「読む／消える」の区別自体が意味を失う（実走の記録は §5.9（[`design-notes.md`](references/design-notes.md)））。
だから同じ対象の催促は**初回だけフルカード**、以後は件数のバッジになる。

### 4.2 会議の流れ

1. 子機の2窓が「送信中」になっているのを確認する
2. カンペ画面をスマホで開く
3. 舞台を使うなら、カンペ画面の「🎭 舞台を開く」を押して別窓を出し、それを画面共有する
4. **「同席開始」と声に出す** → ここで番人の状態がリセットされる
   (前夜のリハ発話やテスト行を本番に持ち込まないため。この合図が無いと、
   起動時に読んだ古い逐語が段の判定に混ざる)
5. 会議中に使える声のコマンド:
   - `<呼びかけ語>、次` / `<呼びかけ語>、戻って` … 段を手で送る／戻す
   - `<呼びかけ語>、時間` … 経過・残り・いまの段の予定枠
   - `<呼びかけ語>、成果は` … 必須取得物の未達一覧
   - `<呼びかけ語>、スライド` … 舞台を切り替える(語は `stage_resources.json` の `match`)
   - `<呼びかけ語>、舞台消して` … 舞台を黒画面に戻す
   - それ以外 … 台本と段取りの全文検索。当たらなければ「手元にありません」
6. **「同席終了」と言う** → 逐語に区切りが入る(判定は続くが状態は保持される)
7. 子機の `STOP.bat`、親機は `stop.sh` で止める（`kill` は使わない）

### 4.3 会議のあと — 何をしたか検証する

```bash
MEETLIVE_DIR=$PWD/meetlive_state/2026-01-20-acme \
  python3 action_log.py --date 2026-01-20 --md action_log_0120.md
```

カード発火・舞台切替・前提監視の判定・段の進行を、**1本の時刻順の年表**にする。
`--kind card` などで種別を絞れる。`--from-time` / `--to-time` で実開始で切れる。

これは飾りではない。**「モニタが鳴らし続けたあの催促は、誤検知だったのか、
本当に未達だったのか」を後から確かめる唯一の手段**である(§5.4（[`design-notes.md`](references/design-notes.md)）)。
年表と `transcript.jsonl` を並べて読むこと。

---

## 5. 罠の要点（理由と実測は [`references/design-notes.md`](references/design-notes.md)）

- **議事録AIの要約を入力に使わない。逐語の生ログだけを信じる**（§5.1）。要約は疑問形を約束に格上げし、前提監視が間違った前提を基準に鳴り始める
- **前提監視は量産呼び出し。既定を安いモデルに置き、呼ぶ回数は減らさず単価を下げる**（§5.2）。一発呼び出しの answerer には上位モデルを置いてよい
- **イヤホン／イヤモニは必須**（§0・§5.3）
- **必須取得物の検知キーワードは、実際の会話で試さないと機能しない**（§5.4）。モニタは「キーワード設計が悪い」と「本当に取れていない」を区別できないので、会議後に年表と逐語を突き合わせてキーワードへ反映する
- **案件・会議ごとに状態ディレクトリ（`MEETLIVE_DIR`）を分ける**（§5.5）。古い逐語は消えずに段の判定に効き続ける
- **前提監視は呼ばれ待ちをしない**（§5.6）。カードを出さなかった判定も `premise_watch.jsonl` に全件残る
- **事実台帳は10〜20件に絞る**（§5.7）。今日の会議で覆されたら困る事実だけ
- **材料の切り詰めは「沈黙」ではなく「捏造」を生む**（§5.8）。`kb/` に置くものは、そのまま送られる分量として選ぶ。切るなら棚から抜くのであって、コードに切らせない

---

## 6. 自分の案件に合わせる — 書くのは**進行表1枚と台帳**

**コードは1本・案件ごとに違うのは会議フォルダの中身だけ。** 会議のたびに用意するのは
次の2つで、`agenda_steps.json` と `talk_script.md` は**進行表から生成する**（§6.2（[`meeting-folder.md`](references/meeting-folder.md)））。

| 書くもの | 何に効くか |
|---|---|
| 進行表 `agenda_sheet.md` | 相手に渡す1枚。ここからカンペと段取りを作る（§6.2（[`meeting-folder.md`](references/meeting-folder.md)）） |
| 事実台帳 `ledger.yaml` | 前提監視の基準（§6.1（[`meeting-folder.md`](references/meeting-folder.md)）） |
| （任意）即答表 `quick_facts.md` | 探し物アシストの索引（§6.3（[`meeting-folder.md`](references/meeting-folder.md)）） |

残り2つ(`phrasebook.json` / `stage_resources.json`)は既定のままでも成立する。

書き方の全体（`build_agenda.py` の注記・手で書く `agenda_steps.json` と `talk_script.md`・即答表・呼びかけ語）は [`references/meeting-folder.md`](references/meeting-folder.md)。とくに次の4つは外すと会議中に気づけない:

- `build_agenda.py` は**埋まらなかった欄に文章を発明しない**。「（要記入）」と書いて出し、`--check` が終了コード1で知らせる
- **段の検知キーワードは「言い方の例」に文字どおり含まれる**ように作る（キメ台詞を読み上げれば段が進む）
- 事実台帳の `title` は**一文で言い切る**。「〜について」のような見出しだと矛盾を判定できない
- 🔴 **即答表（`quick_facts.md`）に合言葉・パスワード・トークンの値は書かない。** 書くのは「どこにあるか」だけ

---

## 7. トラブルシュート（詳細は [`references/troubleshooting.md`](references/troubleshooting.md)）

- **ポートが埋まっている／差し替えたい — `kill` を使わない。** 3層とも自分で席を譲る: `viewer2.py` は `curl http://127.0.0.1:47323/quit`（localhost からのみ）、`copilot.py` は新しいのをそのまま起動すれば古い方が降りる、`receiver.py` はすぐ上げ直せる。`kill -9` は状態ファイルを中途半端に残す
- 音が届かない・カードが出ない・段が進まないときの確認の順序、会議前の1分点検は参照ファイルにある

収録物の一覧は [`references/files.md`](references/files.md)。**この一式に案件のデータは入っていない。** 顧客名・URL・合言葉・金額・実在のパスはすべて設定ファイル側にあり、設定ファイルの実物はこのスキルの外に置く。
