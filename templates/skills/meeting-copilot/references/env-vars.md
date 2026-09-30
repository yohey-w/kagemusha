# meeting-copilot — 環境変数リファレンス（§2）

会議フォルダ（`MEETLIVE_MEETING`）を使わずに入力を指すとき、既定値を確かめるとき、モデル・接続の設定を変えるときに読む。`scripts/meetlive_config.py` が指す「環境変数リファレンス」の本体はこのファイル。

> 節番号は SKILL.md と共通。§0・§1・§1.5・§3.1・§3.2・§3.2.5・§4 は SKILL.md 本文、§1.8 は `decision-layer.md`、§2 は `env-vars.md`、§3.2 の手動起動と §3.3 は `setup-manual.md`、§5 は `design-notes.md`、§6 と `meeting.json` の各キーは `meeting-folder.md`、§7 は `troubleshooting.md`、§8 は `files.md`。

## 2. 環境変数リファレンス（後方互換）

**ふだんは `MEETLIVE_MEETING` 1本でよい**(§1.5（[`SKILL.md`](../SKILL.md)）)。以下は、会議フォルダを使わない場合と、
会議フォルダに置けないもの(状態Dir・秘密・モデル)のための一覧。

未設定でも**顧客データへは絶対に落ちない**。落ちる先は次の2つだけ:
状態ディレクトリ = `./meetlive_state`(カレント直下)、入力ファイル = 同梱の `config/*.example`。
環境変数が指すファイルが**存在しない**ときは、例へ落ちずに `SystemExit` で止まる
(解決は `scripts/meetlive_config.py` の1箇所に集約してある。各スクリプトは
環境変数を直接読まない ── その規律は `tests/test_l_meeting_copilot.sh` が見張っている)。

### 置き場

| 変数 | 既定 | 意味 |
|---|---|---|
| `MEETLIVE_DIR` | `./meetlive_state` | 状態(逐語・カード・ログ)の置き場。**案件ごと・会議ごとに必ず分ける** |
| `MEETLIVE_LEDGER` | `config/ledger.yaml.example` | 前提監視が読む事実台帳(YAML・`facts[].id` / `.title`) |
| `MEETLIVE_AGENDA` | `config/agenda_steps.example.json` | 段と必須取得物 |
| `MEETLIVE_SCRIPT` | `config/talk_script.example.md` | 台本(テレプロンプターの中身) |
| `MEETLIVE_PHRASEBOOK` | `config/phrasebook.example.json` | 定型回答・約束の境界の文言 |
| `MEETLIVE_STAGE` | `config/stage_resources.example.json` | 舞台に出せるもの(URL・画像・声で呼ぶ語) |
| `MEETLIVE_KNOWLEDGE_DIR` | `config/` | answerer の接地資料ディレクトリ。🔴**この直下の `.md`/`.txt` を名前順に全部読み、そのままLLMへ送る**(§2.1) |
| `MEETLIVE_SCRIPT_NAME` | `talk_script.example.md` | 接地資料のうち先頭に置く台本のファイル名 |
| `MEETLIVE_MEETING` | (空) | **会議フォルダ**(§1.5（[`SKILL.md`](../SKILL.md)）)。これ1本で上の入力が全部決まる |
| `MEETLIVE_CREDS_FILE` | (空) | 合言葉の md(§1.5（[`SKILL.md`](../SKILL.md)）)。未設定なら鍵パネルは中身なし |
| `MEETLIVE_DOCS` | `<会議フォルダ>/docs` | 資料棚。会議フォルダが無ければ `<状態Dir>/docs` |
| `MEETLIVE_BANK` | `<会議フォルダ>/bank.json` | 先読み回答バンク(任意) |
| `MEETLIVE_LAYOUT` | `auto` | 画面の並べ方。`meeting.json` の `layout` が優先 |
| `MEETLIVE_HEARTBEAT_STALE_SEC` | `60` | これより古い心拍は「心拍なし」と出す |

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
| `MEETLIVE_SCRIPT_MODE` | `with_lines` | カンペの粒度。`answers_only` で言い方の例を隠す（`meeting.json` の `script_mode` が勝つ） |
| `MEETLIVE_QUICK_FACTS` | (空→会議フォルダの `quick_facts.md`) | 即答表の置き場。指した先が無ければ止まる |
| `MEETLIVE_LOOKUP_COOLDOWN` | `120` | 同じ探し物を撃ち直すまでの秒数 |

上の `MEETLIVE_SCRIPT_MODE` と下の終話検知の3つは、いずれも `meeting.json`（`script_mode` / `auto_stop.*`）で
会議ごとに書くほうが本筋。環境変数は**その場だけ上書きしたいとき**の口。

### 終話検知（全層の自動停止）

| 変数 | 既定 | 意味 |
|---|---|---|
| `MEETLIVE_STOP_SILENCE_MIN` | `10` | 双方の無音がこれだけ続いたら終話(分) |
| `MEETLIVE_STOP_FAREWELL_MIN` | `5` | 別れの言葉のあと、この無音で終話(分) |
| `MEETLIVE_STOP_END_MIN` | `10` | 予定の終わりからこれだけ過ぎ、**かつ無音**なら終話(分) |

どれも「無音」とセットで効く。予定を過ぎただけでは止まらない（§3.2.5（[`SKILL.md`](../SKILL.md)））。

### モデル・接続

| 変数 | 既定 | 意味 |
|---|---|---|
| `MEETLIVE_AGENT_CLI` | (空→PATHにある方・両方あれば `claude`) | 使う CLI: `claude` / `codex` |
| `MEETLIVE_MODEL_PREMISE` / `_EFFORT_PREMISE` | claude: `claude-sonnet-5`/`medium`<br>codex: `gpt-5.6-sol`/`low` | 前提監視(量産呼び出し) |
| `MEETLIVE_MODEL_PREMISE_FALLBACK` / `_EFFORT_PREMISE_FALLBACK` | claude: `claude-opus-5`/`medium`<br>codex: `gpt-5.6-sol`/`medium` | 既定が空を返したときだけ1回 |
| `MEETLIVE_MODEL_ANSWER` / `_EFFORT_ANSWER` | claude: `claude-opus-5`/`low`<br>codex: `gpt-5.6-sol`/`xhigh` | 台本外の回答(一発呼び出し) |
| `MEETLIVE_MODEL_ANSWER_FALLBACK` / `_EFFORT_ANSWER_FALLBACK` | claude: `claude-sonnet-5`/`low`<br>codex: `gpt-5.6-sol`/`low` | 同上のフォールバック |

**既定が CLI ごとに違うのは、モデルidがCLIをまたいで通用しないから**(片方の既定を
もう片方に渡すと、CLI 自身のエラーで空が返る＝画面の上では「材料になし」と区別が
つかない)。`MEETLIVE_MODEL_*` を明示すれば、どちらの CLI でもそれが勝つ。

⚠️ **codex の前提監視だけ effort が低いのは節約ではない。** 前提監視は発話ごとに
叩き、呼び出し側の制限は20秒。実測(gpt-5.6-sol・短い1往復・2026-09-06)は
**low 8.8秒 / medium 7.3秒 / xhigh 17.3秒**——xhigh は本番の長い前提リストでは
入らず、**間に合わないと沈黙する**(空振りではなく無音になる)。

### 接地資料・子機・STT

| 変数 | 既定 | 意味 |
|---|---|---|
| `MEETLIVE_KNOWLEDGE_PER_FILE` / `_TOTAL` | `9000` / `40000` | 接地資料の文字数上限 |
| `MEETLIVE_TOKEN` | (空) | 子機との合言葉。`receiver.py --token` の既定値 |
| `DEEPGRAM_API_KEY` / `OPENAI_API_KEY` | — | 使う STT バックエンドに応じて必須 |
