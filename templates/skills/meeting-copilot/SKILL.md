---
name: meeting-copilot
description: |
  A two-machine live meeting copilot. A Windows laptop streams two audio channels (your mic, and a loopback of the other side's voice) to a parent machine, which transcribes them, drives a teleprompter you read from, watches every incoming utterance against a ledger of pre-agreed facts, and answers off-script questions. Ships the parent daemons, the Windows capture agent, and worked config examples. Consumes raw transcripts only — never a meeting-AI summary.
  会議に同席してリアルタイムで進行ナビ・前提監視・台本外質問への回答を行う2台構成のモニタ。子機(Windowsノート)が2系統の音声を親機へ送り、親機が文字起こし・カード生成・画面配信を行う。親機の常駐一式・子機の取り込み一式・設定の実例つき。入力は逐語のみで、議事録AIの要約は使わない。
---

# meeting-copilot

**会議に同席して、進行と前提を見張るモニタ一式**

> **English abstract** — Two machines. The **child** (a Windows laptop, in the meeting) captures two physical audio channels — `T` = your microphone, `G` = a WASAPI loopback of the default speaker — and streams both to the **parent** over TCP with a shared token. The parent transcribes each channel separately (speaker identity comes from the *channel*, never from diarization), then runs three layers over the transcript: a rule-only warden (`copilot.py`) that advances the agenda and fires boundary alarms with no LLM at all; a premise watcher (`premise_watch.py`) that classifies every guest utterance against a ledger of pre-agreed facts as contradiction / already-known / new; and an answerer (`answerer.py`) for off-script questions. A teleprompter (`viewer2.py`) serves two different pages — a **prompt screen** only you see on your phone, and a **stage window** you actually screen-share. Everything case-specific lives in config files; the code carries no customer data. Written mainly in Japanese; the structure is language-independent.

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

### 🔴 イヤホン／イヤモニが必須な理由は、この構成に直結している

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

## 1. 4つの層 — 何がどこまでやるか

| 層 | ファイル | LLM | いつ動くか |
|---|---|---|---|
| 逐語化 | `receiver.py` + `stt.py` | 使わない | 音が来るたび |
| 番人(第1層) | `copilot.py` | **使わない** | 逐語1行ごと。ルールと文字列照合だけ |
| 前提監視 | `premise_watch.py` | 量産呼び出し | **相手の発話ごとに毎回** |
| 回答(第2層) | `answerer.py` | 一発呼び出し | 台本外の質問のときだけ(30秒に1回まで) |
| 表示 | `viewer2.py` | 使わない | 長ポーリングで配信 |
| 事後検証 | `action_log.py` | 使わない | 会議のあと |

**なぜ第1層に LLM を置かないか**: 会議中は「速い・落ちない・同じ入力に同じ出力」が
何より効く。段の進行と約束の境界(金額・期限・責任)の検知は、キーワード照合で足りる。
LLM を挟むと、その分だけ遅れ、その分だけ落ちる。

---

## 2. 環境変数リファレンス

未設定でも**顧客データへは絶対に落ちない**。落ちる先は次の2つだけ:
状態ディレクトリ = `./meetlive_state`(カレント直下)、入力ファイル = 同梱の `config/*.example`。
環境変数が指すファイルが**存在しない**ときは、例へ落ちずに `SystemExit` で止まる
(解決は `scripts/meetlive_config.py` の1箇所に集約してある)。

### 置き場

| 変数 | 既定 | 意味 |
|---|---|---|
| `MEETLIVE_DIR` | `./meetlive_state` | 状態(逐語・カード・ログ)の置き場。🔴**案件ごと・会議ごとに必ず分ける** |
| `MEETLIVE_LEDGER` | `config/ledger.yaml.example` | 前提監視が読む事実台帳(YAML・`facts[].id` / `.title`) |
| `MEETLIVE_AGENDA` | `config/agenda_steps.example.json` | 段と必須取得物 |
| `MEETLIVE_SCRIPT` | `config/talk_script.example.md` | 台本(テレプロンプターの中身) |
| `MEETLIVE_PHRASEBOOK` | `config/phrasebook.example.json` | 定型回答・約束の境界の文言 |
| `MEETLIVE_STAGE` | `config/stage_resources.example.json` | 舞台に出せるもの(URL・画像・声で呼ぶ語) |
| `MEETLIVE_KNOWLEDGE_DIR` | `config/` | answerer の接地資料ディレクトリ。🔴**この直下の `.md`/`.txt` を名前順に全部読み、そのままLLMへ送る**(§2.1) |
| `MEETLIVE_SCRIPT_NAME` | `talk_script.example.md` | 接地資料のうち先頭に置く台本のファイル名 |

### 2.1 🔴 `MEETLIVE_KNOWLEDGE_DIR` に何を置くかは、そのまま「LLMへ送るもの」を決める

`answerer.py` はこのディレクトリ直下の `.md` / `.txt` を**名前順に全部**読み、
上限(`MEETLIVE_KNOWLEDGE_PER_FILE` / `_TOTAL`)まで**逐語でプロンプトへ載せる**。
ファイル名の allowlist は持っていない。**置いたものは送られる。**

したがって、**案件フォルダをまるごと指さないこと**。値付けの検討メモ・社内の下書き・
相手に見せられない判断の記録が同じ階層にあれば、それも一緒に送られる。

```bash
# ✗ 危ない: 何が入っているか分からない階層を丸ごと指す
export MEETLIVE_KNOWLEDGE_DIR=/path/to/projects/acme

# ✓ 送ってよい資料だけを置いた専用ディレクトリを作って指す
mkdir -p /path/to/projects/acme/meetlive_knowledge
cp talk_script.md requirements.md minutes_prev.md /path/to/projects/acme/meetlive_knowledge/
export MEETLIVE_KNOWLEDGE_DIR=/path/to/projects/acme/meetlive_knowledge
```

サブディレクトリは読まない(直下だけ)。拡張子が `.md` / `.txt` 以外のものも読まない。

### 会議の中身

| 変数 | 既定 | 意味 |
|---|---|---|
| `MEETLIVE_CALL_WORDS` | `コパイロット,こぱいろっと,秘書,ひしょ` | 呼びかけ語(カンマ区切り)。**STT の誤変換の綴りも並べる** |
| `MEETLIVE_COUNTERPART` | `相手` | 相手の呼び方(プロンプト内で使う。例:「〇〇さん」) |
| `MEETLIVE_HOST_LABEL` | `進行役` | こちら側の呼び方(プロンプト内で使う) |
| `MEETLIVE_MODE_START_WORD` | `同席開始` | 同席の開始合図 |
| `MEETLIVE_MODE_END_WORD` | `同席終了` | 同席の終了合図 |
| `MEETLIVE_START_HOMOPHONES` | (空) | 開始合図が STT で化けた綴り。実際に化けた語を足す |
| `MEETLIVE_PREMISE_IDS` | (空→台帳の先頭N件) | 監視する事実idのカンマ区切り |
| `MEETLIVE_PREMISE_MAX` | `16` | id 未指定のとき台帳から取る件数の上限 |
| `MEETLIVE_PREMISE_COOLDOWN` | `45` | 同種の前提カードを間引く秒数 |

### モデル・接続

| 変数 | 既定 | 意味 |
|---|---|---|
| `MEETLIVE_MODEL_PREMISE` / `_EFFORT_PREMISE` | `claude-sonnet-5` / `medium` | 前提監視(量産呼び出し) |
| `MEETLIVE_MODEL_PREMISE_FALLBACK` / `_EFFORT_PREMISE_FALLBACK` | `claude-opus-5` / `medium` | 既定が空を返したときだけ1回 |
| `MEETLIVE_MODEL_ANSWER` / `_EFFORT_ANSWER` | `claude-opus-5` / `low` | 台本外の回答(一発呼び出し) |
| `MEETLIVE_MODEL_ANSWER_FALLBACK` / `_EFFORT_ANSWER_FALLBACK` | `claude-sonnet-5` / `low` | 同上のフォールバック |
| `MEETLIVE_KNOWLEDGE_PER_FILE` / `_TOTAL` | `9000` / `40000` | 接地資料の文字数上限 |
| `MEETLIVE_TOKEN` | (空) | 子機との合言葉。`receiver.py --token` の既定値 |
| `DEEPGRAM_API_KEY` / `OPENAI_API_KEY` | — | 使う STT バックエンドに応じて必須 |

---

## 3. セットアップ

### 3.1 前提

- **親機**: Linux または WSL2。Python 3.9+。`claude` CLI が PATH にあり、認証済みであること
  (`premise_watch.py` / `answerer.py` は `claude -p <prompt> --model <m> --effort <e>` を
  サブプロセスで叩く。CLI が無いと、この2つは黙って何も出さない)
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

```bash
# 2) 案件の設定を指す
export MEETLIVE_DIR=$PWD/meetlive_state/2026-01-20-acme   # 会議ごとに別のディレクトリ
export MEETLIVE_LEDGER=/path/to/projects/acme/ledgers/ledger.yaml
export MEETLIVE_AGENDA=/path/to/projects/acme/agenda_steps.json
export MEETLIVE_SCRIPT=/path/to/projects/acme/talk_script.md
export MEETLIVE_PHRASEBOOK=/path/to/projects/acme/phrasebook.json
export MEETLIVE_STAGE=/path/to/projects/acme/stage_resources.json
export MEETLIVE_KNOWLEDGE_DIR=/path/to/projects/acme/meetlive_knowledge  # 🔴 §2.1
export MEETLIVE_SCRIPT_NAME=talk_script.md
export MEETLIVE_COUNTERPART="〇〇さん"
export MEETLIVE_CALL_WORDS="コパイロット,こぱいろっと,秘書,ひしょ"
export MEETLIVE_TOKEN="$(openssl rand -base64 18)"   # 子機の config.txt と同じ値にする
export DEEPGRAM_API_KEY=...

# 3) 会議前に設定が読めるか確かめる(LLMもネットワークも使わない)
./venv/bin/python copilot.py --selfcheck
```

`--selfcheck` は段取り・台本・語彙集・舞台の資源を読んで件数を出して終わる。
**`⚠ MEETLIVE_XXX が未設定です。同梱の例を読みます` が出たら、その環境変数が
効いていない**(=架空の例のまま会議に入るところだった)。

```bash
# 4) 起動 (3つとも別プロセス。nohup なりターミナル多重化なりで並べる)
./venv/bin/python receiver.py --backend deepgram --port 47311 >> receiver.log 2>&1 &
./venv/bin/python copilot.py  --start 2026-01-20T15:00:00 >> copilot.log 2>&1 &
./venv/bin/python viewer2.py  --start 2026-01-20T15:00:00 --port 47323 >> viewer2.log 2>&1 &
```

#### 起動順について（正確に）

**硬い制約は1つだけ**: `receiver.py` が待ち受けていないと子機は繋がらない
(繋がらない間、子機は最大30秒まで待ち時間を伸ばして繰り返し試す)。
**だから receiver を先に上げる。**

`copilot.py` と `viewer2.py` の間には順序の制約は無い。どちらも同じ
`transcript.jsonl` を独立に読み、**同じ式で段を計算する**だけだからである。
ただし次の2つは守らないと、画面と番人が食い違う:

1. **`--start` を copilot と viewer2 で同じ値にする**。経過時間・予定時刻・超過判定が
   この値基準。(`receiver.py` に `--start` は無い。逐語を書くだけなので要らない)
2. **`MEETLIVE_AGENDA` を同じファイルにし、編集したら copilot と viewer2 の
   両方を上げ直す**。
   - `copilot.py` は段取りJSONを**起動時に1回だけ**読む
   - `viewer2.py` は、中段に出す台本ブロックだけは毎リクエスト読み直すが、
     **段の判定に使う段取りは起動時に読んだものを使い続ける**
     (ここだけ読み直すと、番人が持つ古いキーワードと段の判定がズレるため)

   片方だけ上げ直すと、下段のカードに書かれた段番号と上段の段番号がズレる。

### 3.3 子機(Windows)のセットアップ

`scripts/portable/` の中身を、そのままノートPCへ持っていく(zip でよい)。

1. **`setup.cmd` をダブルクリック**(初回だけ・2〜3分)
   - Python を探し、無ければ winget で入れる
   - `venv/` を作り、`soundcard` と `numpy` を入れる
   - `config.txt.example` を `config.txt` へコピーし、メモ帳で開く
2. **`config.txt` を書き換える**
   ```
   host=<親機のアドレス>          ← プライベート網のIP
   port=47311                     ← receiver.py --port と同じ
   token=<親機と同じ合言葉>       ← MEETLIVE_TOKEN と同じ値
   rate=16000
   mic_match=                     ← 任意。§6 を見よ
   ```
   🔴 `config.txt` は**親機のアドレスと合言葉が平文で入るファイル**。
   git に入れない・他人に渡さない。配るのは `config.txt.example` の方だけ。
   例のまま(`CHANGE_ME...`)で起動すると、その場で止まって何を直すか出す。
3. **イヤホンを挿す**(START.bat より先に。§0)
4. **`START.bat` をダブルクリック** → 窓が2つ開く
   - `MIC (agent_mic) - my voice` … `[mic-only] 接続OK -> 送信中` が出れば成功
   - `LOOP (agent_loop) - other side` … `[loop-only] connected OK -> sending` が出れば成功
   - **2つとも出て初めて成功**。片方だけだと片側の声が丸ごと落ちる
   - 親機側のログにも `++ host 接続` `++ guest 接続` が出る
5. 止めるときは `STOP.bat`(または2つの窓を閉じる)

`portable/` の中身:

| ファイル | 役割 |
|---|---|
| `agent_mic.py` | 自分の声。**推奨経路**。デバイス列挙もループバックもしない最小版 |
| `agent_loop.py` | 相手の声(WASAPI ループバック)。v10。録音スレッドと送信ループを分けてある |
| `agent_loop_v9.py` | 上の旧版。**無音が続くと1バイトも送らない**ので実運用不可。デバイスが開けるかの切り分け用 |
| `agent.py` | 2系統を1プロセスで扱う簡易版。片方が落ちると両方死ぬので非推奨 |
| `agent_common.py` | `config.txt` の読み込み(接続先の既定値をコードに持たない) |
| `START.bat` / `start_all.ps1` | MIC窓とLOOP窓を開くランチャ。LOOP窓は落ちたら3秒後に自動再起動 |
| `STOP.bat` / `stop.cmd` | 止める |
| `setup.cmd` / `start.cmd` | 初回セットアップ / `agent.py` の起動 |
| `config.txt.example` | 設定の雛形 |
| `手順.txt` | 子機を使う人へ渡す手順書(この SKILL.md を読まない人向け) |

#### 子機と親機をつなぐ線の仕様

自前の取り込みプログラムを書くならこれに合わせる。

```
接続直後に JSON 1行 + "\n":
    {"ch":"T","rate":16000,"token":"合言葉"}
      ch = "T"(こちらのマイク) / "G"(相手側のループバック)
以降くり返し:
    struct "<dI" = (子機の時刻 float64, 続く PCM のバイト数 uint32) + PCM int16 LE mono
```

子機の時刻は**参考値で、親機は使わない**。親機は「受け取ったサンプル数」だけで
時間を進める(WSL2 では `time.time()` がホスト再同期で巻き戻り、`time.monotonic()` が
実時間より約7%速い、という実測があったため。48kHz の水晶で刻まれた音のサンプル数だけが
正しい時間を持っている)。
だから子機側は、**無音の間も無音サンプルを送り続けなければならない**。
送らないとそのチャンネルの時刻だけが実時間から遅れていく。

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
7. 子機の `STOP.bat`、親機のプロセスを止める

### 4.3 会議のあと — 何をしたか検証する

```bash
MEETLIVE_DIR=$PWD/meetlive_state/2026-01-20-acme \
  python3 action_log.py --date 2026-01-20 --md action_log_0120.md
```

カード発火・舞台切替・前提監視の判定・段の進行を、**1本の時刻順の年表**にする。
`--kind card` などで種別を絞れる。`--from-time` / `--to-time` で実開始で切れる。

これは飾りではない。**「モニタが鳴らし続けたあの催促は、誤検知だったのか、
本当に未達だったのか」を後から確かめる唯一の手段**である(§5.4)。
年表と `transcript.jsonl` を並べて読むこと。

---

## 5. 実戦で得た設計知見

ここは「そう決めた理由」を残す節。同じ穴を掘り直さないために書いてある。

### 5.1 🔴 議事録AIの要約を入力に使わない。逐語の生ログだけを信じる

Gemini 等の議事録AIが出す要約を、モニタや台帳の入力に使ってはならない。
実測で、要約から取った項目は**10件中4件しか正しくなかった**。
最悪の壊れ方は「**疑問形を約束に格上げする**」——相手が「〜できますか？」と聞いただけの
ものが、要約では「〜することで合意」になる。これが事実台帳に入ると、前提監視は
**間違った前提**を基準に「矛盾」を判定し始める。

この道具の配管は最初からそうなっている: `receiver.py` が STT の確定発話だけを
`transcript.jsonl` へ追記し、`copilot.py` はそれを tail する。要約が入る隙間が無い。
**会議後の台帳更新でも同じ規律を守ること**(要約は索引としてなら使ってよい。
配管には使わない)。

### 5.2 前提監視は量産呼び出しになる。既定を安いモデルに置く

`premise_watch.py` は**相手の発話1件ごとに1回**呼ばれる(`copilot.call_premise_watch`)。
実測で **50分の会議で218回**。ここに上位モデルを置くとクォータの底が抜ける。

だから既定は Sonnet 相当・`--effort medium`、**異常時(空が返ったとき)だけ上位モデルへ
1回フォールバック**する形にしてある。

**呼ぶ回数を減らす方向で節約しないこと。** 発話をフィルタで間引くと精度が落ちる——
会話は途切れ途切れで、断片も拾わないと文脈が繋がらない。**呼ぶ頻度は変えず、単価を下げる。**

対照的に `answerer.py` は台本外の質問のときだけ・30秒に1回まで(`ANSWERER_MIN_GAP`)の
**一発呼び出し**なので、上位モデルを置いてよい。
**量産呼び出しか一発呼び出しか**で、置くモデルを分けるのが原則。

### 5.3 🔴 イヤホン／イヤモニは必須。任意ではない

§0 に書いたとおり。話者分離を物理チャンネルでやっている以上、
スピーカーで相手の声を鳴らした瞬間に土台が崩れる。`--xtalk-gate` は保険。

### 5.4 🔴 必須取得物の検知キーワードは、実際の会話で試さないと機能しない

`unmet()` は「その必須取得物の検知キーワード(正規表現)が、蓄積した発話全文に
1つも当たらない」ときに未達とみなす。つまり**キーワードが実際の言い回しに
当たらなければ、永遠に未達のまま催促が鳴り続ける**。

実際に、**18分間ずっと同じ催促が鳴り続けた**会議があった。
ただし——**あとで逐語と突き合わせたら、それは誤検知ではなく、本当に未達だった**。
モニタは正しく鳴らし続けていた。

ここが両面である。

> **モニタは「キーワード設計が悪い」と「本当に取れていない」を区別できない。**
> どちらも同じ「鳴り続ける」として出てくる。

したがって:

- **キーワード設計をサボると、真実を鳴らし続けるだけの装置にもなりうる**
  (鳴っていること自体は情報量ゼロ。原因が2つあるので)
- 正規表現として当たるので、**言い換えを `|` で並べておく**のが実用的。
  例: `"(月末|来月末|末日)まで"`
- 会議の前に、**想定される相手の言い回しを声に出して1度通す**こと
- 会議の後に、必ず `action_log.py` の年表と逐語を突き合わせ、
  **「鳴っていた催促はどちらだったのか」を判定して、キーワードへ反映する**

会議1回ごとにこれを回さないと、キーワードは永遠にチューニングされない。

### 5.5 🔴 案件を移すときは、必ず状態ディレクトリ(`MEETLIVE_DIR`)を隔離する

同じディレクトリを使い回すと、**過去の会議の逐語が段の判定に混ざる**。
`copilot.tail()` は起動時に既存の `transcript.jsonl` を読み、直近の「同席開始」以降を
無言で再生して状態を復元する。`viewer2.build_nav()` も逐語を**切り詰めずに全部**読む
(末尾N行だけ見ると、長い会議で古い発話が窓から落ちて段が巻き戻るため)。

つまり**古い逐語は消えずに効き続ける**。案件ごと・会議ごとに分けること。

```bash
MEETLIVE_DIR=$PWD/meetlive_state/2026-01-20-acme     # 会議1回 = 1ディレクトリ
```

`cards.jsonl` / `premise_watch.jsonl` / `stage_cmd.jsonl` / `display_log.jsonl` も
すべてここに溜まるので、隔離しておくと会議後の検証もそのまま案件別になる。

### 5.6 番人は呼ばれ待ちをしない層を持つ

初期版は「呼ばれたら答える」だけだった。その結果、**相手が前提を覆す発言をしても、
呼ばれない限り何も出なかった**。前提監視(`premise_watch.py`)はこれを直すために、
相手の発話ごとに自発的に撃つ層として足したもの。

判定は3値(矛盾⚠ / 既知✔ / 新規＋)で、**カードを出さなかった判定も含めて全件**
`premise_watch.jsonl` に残る。画面に出なかったからといって、判定していないわけではない。

### 5.7 事実台帳は10〜20件に絞る

`MEETLIVE_PREMISE_MAX` の既定が16なのはこのため。全部入れるとプロンプトが膨らみ、
「矛盾」の判定がぼやけて鳴らなくなる。**今日の会議で覆されたら困る事実**だけを選ぶ:
契約・約束の範囲境界、相手の現状についてこちらが握っている認識、前回決まったこと。

---

## 6. 自分の案件に合わせる — 書くのは3ファイル

最低限これだけ書けば動く。残り2つ(`phrasebook.json` / `stage_resources.json`)は
既定のままでも成立する。

### 6.1 `ledger.yaml` — 事実台帳（前提監視の基準）

```yaml
facts:
  - id: F-001
    title: 発注は保守フェーズのみ。新規開発は今回の範囲に含まない
  - id: F-002
    title: 相手先の在庫管理は今も表計算ソフトで、担当者1名に集中している
```

`id` と `title` だけあればよい(他の列は人間の管理用)。
既に3台帳(`templates/context_ledgers_template.md`)を運用しているなら、
**その `ledger.yaml` をそのまま `MEETLIVE_LEDGER` に指せる**。

`title` は**一文で言い切る**こと。「〜について」のような見出しだと、
LLM が矛盾を判定できない。

### 6.2 `agenda_steps.json` — 段と必須取得物

```json
{
  "会議分": 45,
  "警報分": 10,
  "steps": [
    {
      "id": "s1",
      "title": "① 現状の確認",
      "目安分": 10,
      "検知キーワード": ["まず現状", "いまの運用"],
      "必須取得物": [
        {"名前": "現行の担当者数",
         "検知キーワード": ["(担当|運用)(は|が)?\\s*\\d+\\s*(名|人)", "一人でやって"]}
      ],
      "nudge": "相手に喋らせる。こちらの案はまだ出さない",
      "台本": ["まず、いまの運用を確認させてください。"]
    }
  ]
}
```

- **段の検知キーワード**は**こちら側の発話にだけ**当たる。
  → **台本で必ず口にする語**を選ぶ。相手が言いそうな語を入れると勝手に進む
- **必須取得物の検知キーワード**は**両者の発話に**当たる(答えるのは相手なので)
  → 🔴 §5.4 を読むこと。**ここのチューニングが全体の当たり外れを決める**
- 英語キー(`title` / `minutes` / `keywords` / `musts` / `name` / `script` /
  `total_minutes` / `warn_at_minutes`)でも書ける

### 6.3 `talk_script.md` — 台本（テレプロンプターの中身）

```markdown
## 【1】 現状の確認

**まず、いまの運用を確認させてください。**

### 聞く順番

**データは、何年分くらい残っていますか。** （移行範囲の見積りに効く）

▸ 「わからない」と言われたら → 「では、いまの置き方で仮に作っておきます」

（ト書き。小さく薄く出る）
```

| 行の形 | 画面での出方 |
|---|---|
| `## 【N】 見出し` | 段N の始まり。N は `agenda_steps.json` の並び順(1始まり)と対応 |
| `**声に出す文**` | 大きく表示。後ろに続く文字は小さい注記になる |
| `### 小見出し` | 段の中の区切り |
| `▸ 条件 → 言うこと` | 折りたたまれた分岐 |
| `（ト書き）`・表 | 小さく薄い注記 |

`▸` 行の「」で囲んだ部分は、番人が「**台本が想定している言い回し**」として拾う。
相手がその言い方をしたら、疑問符が無くても第2層(answerer)を呼んでよい、の判定材料になる。
`## 【N】` 以外の `##` 節はテレプロンプターに出ないので、準備メモはそちらへ書く。

### 6.4 呼びかけ語は、誤変換の綴りも並べる

```bash
export MEETLIVE_CALL_WORDS="コパイロット,こぱいろっと,カタカナ以外の誤変換,..."
```

STT は呼びかけ語を高確率で化かす。**1回でも化けた綴りは、そのまま足す。**
開始合図が化けた場合は `MEETLIVE_START_HOMOPHONES` に足す(こちらは「開始/スタート」との
組み合わせでのみ効くので、多少広く入れても暴発しにくい)。

---

## 7. トラブルシュート

### 7.1 ポートが埋まっている / 差し替えたい — `kill` を使わない

3つとも**自分で席を譲る仕組みを持っている**ので、プロセスを撃つ必要がない。

| プロセス | 差し替え方 | 仕組み |
|---|---|---|
| `viewer2.py` | `curl http://127.0.0.1:47323/quit` してから新しいのを起動 | `/quit` は**localhost からのみ**受け付け、0.3秒後に自ら終了する。外から止められると会議中に事故るのでこの制限がある |
| `copilot.py` | **新しいのをそのまま起動するだけ** | 起動時に `<state>/copilot.owner` へ自分のpidを書く。古い方は次のポーリング(0.3秒)で持ち主が変わったのに気づき、自分から降りる |
| `receiver.py` | `allow_reuse_address` が立っているので、止めた直後に上げ直せる | 子機の二重接続も同様に、**新しい接続が古い接続を打ち切って差し替える**(取り残しがあると全行が二重に出るため) |

`kill -9` で落とすと、`copilot.owner` に死んだpidが残ったり、状態ファイルが中途半端に
なったりする。**上の経路を使うこと。**

### 7.2 音が届かない — 確認の順序

1. **子機の2窓**に `接続OK -> 送信中` / `connected OK -> sending` が出ているか
   - 出ていない → `config.txt` の `host` / `port`、プライベート網の接続を見る
   - `合言葉が違う` が親機のログに出る → `token` が親機と一致していない
2. **親機のログ**に `++ host 接続` `++ guest 接続` が両方出ているか
3. **`<state>/transcript.jsonl` が増えているか**
   - 増えない → STT のキー(`DEEPGRAM_API_KEY` / `OPENAI_API_KEY`)を確認
   - 切り分け: `--backend stub` で上げ直す。キー無しで `[STUB] ... の発話 N秒` が
     出るなら、**配管は生きていて STT だけが問題**と分かる
4. **片側だけ入らない**
   - 相手の声だけ入らない → 会議アプリの音が出ているデバイスが「既定のスピーカー」か。
     イヤホンを挿し直したら `START.bat` を叩き直す(取り込み先は起動時に決まる)
   - 自分の声だけ入らない → 既定のマイクを確認。既定マイクが Bluetooth 機器だと
     取得時にネイティブ層ごと落ちることがある。その場合は `config.txt` の
     `mic_match` に内蔵マイク名の一部を書いて指名する
5. **文字が二重に出る** → 子機が2つ動いている。`STOP.bat` してから `START.bat`

### 7.3 カードが出ない — 確認の箇所

1. **`MEETLIVE_DIR` が copilot と viewer2 で同じか**。
   `copilot.py` は `<state>/cards.jsonl` へ書き、`viewer2.py` は同じファイルの末尾40行を読む。
   ここが食い違うと、番人は動いているのに画面には永遠に何も出ない
2. **`<state>/cards.jsonl` に行が増えているか**
   - 増えている → 表示側の問題。カードは `ttl` 秒で消え、**新しい発話が2つ来ても消える**
     (ただし出してから最低8秒は残る)。会話が速い区間では見逃しやすい
   - 増えていない → `copilot.log` を見る。`CARD` の行が出ていなければ判定に達していない
3. **前提カードが出ない**
   - `<state>/premise_watch.jsonl` を見る。**カードを出さなかった判定も全件残っている**
   - `type: なし` ばかり → 事実台帳の `title` が見出し調で、矛盾を判定できていない
   - `debounced: true` ばかり → 同種の連発を45秒で間引いている(`MEETLIVE_PREMISE_COOLDOWN`)
   - ファイル自体が空 → `claude` CLI が PATH に無い / 認証が切れている。
     手で `python3 premise_watch.py "テストの発話"` を叩いて確かめる
4. **台本外の質問に答えない**
   - 発火条件が厳しい: 「明確な疑問形の語尾 **かつ 30字以上**」または
     「台本の `▸` 行が想定している言い回し」のどちらか。しかも30秒に1回まで
   - これは意図的に厳しくしてある(緩めると相手の言いさし断片で撃ちまくり、
     画面がカードで埋まって台本が読めなくなる)
   - `<state>/answerer_log.jsonl` に、カードを出さなかった「手元にない」も含めて全件残る
5. **段が進まない / 勝手に進む**
   - 段の検知キーワードは**こちら側の発話にだけ**当たる。イヤホンをしていないと
     相手の声が `host` として入り、勝手に進む(§0)
   - `<呼びかけ語>、次` で手で送れる。手動の送りは自動判定に**加算**される

### 7.4 会議前の点検（1分）

```bash
python3 copilot.py --selfcheck     # 設定が読めるか・件数は妥当か
python3 premise_watch.py "テストの発話です"   # LLM経路と台帳が生きているか
```

`--selfcheck` で `⚠ ... 未設定です。同梱の例を読みます` が1行でも出たら、
**架空の例のまま本番に入るところだった**ということ。環境変数を見直す。

---

## 8. 収録物

```
meeting-copilot/
├── SKILL.md
├── config/                          … 全部「架空の案件」の例。中身を入れ替えて使う
│   ├── ledger.yaml.example          … 事実台帳(前提監視の基準)
│   ├── agenda_steps.example.json    … 段と必須取得物
│   ├── talk_script.example.md       … 台本(テレプロンプターの中身)
│   ├── phrasebook.example.json      … 定型回答・約束の境界の文言
│   └── stage_resources.example.json … 舞台に出せるもの
└── scripts/
    ├── meetlive_config.py           … 置き場と設定の解決(既定の一元管理)
    ├── receiver.py                  … 音を受けて逐語へ
    ├── stt.py                       … STTアダプタ(stub / OpenAI / Deepgram)
    ├── copilot.py                   … 番人(第1層・LLM無し)
    ├── premise_watch.py             … 前提監視(量産呼び出し)
    ├── answerer.py                  … 台本外の回答(一発呼び出し)
    ├── viewer2.py                   … カンペ画面 + 舞台画面
    ├── action_log.py                … 会議後の行動年表
    └── portable/                    … 子機(Windows)一式。ノートPCへ持っていく
        ├── agent_mic.py / agent_loop.py / agent_loop_v9.py / agent.py
        ├── agent_common.py
        ├── START.bat / STOP.bat / start_all.ps1
        ├── setup.cmd / start.cmd / stop.cmd / agent_loop.cmd
        ├── config.txt.example       … 🔴 実物(config.txt)はコミットしない
        └── 手順.txt                 … 子機を使う人へ渡す手順書
```

**この一式に案件のデータは入っていない。** 顧客名・URL・合言葉・金額・実在のパスは
すべて設定ファイル側にあり、設定ファイルの実物はこのスキルの外に置く。
