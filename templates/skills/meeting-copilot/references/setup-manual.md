# meeting-copilot — 手動の起動と子機のセットアップ（§3.2 の手動起動・§3.3）

`run.sh` を使わずに親機の層を手で上げるとき、起動順と `--start` の扱いを正確に知りたいとき、子機（Windows）を準備するとき、自前の取り込みプログラムを書くときに読む。

> 節番号は SKILL.md と共通。§0・§1・§1.5・§3.1・§3.2・§3.2.5・§4 は SKILL.md 本文、§1.8 は `decision-layer.md`、§2 は `env-vars.md`、§3.2 の手動起動と §3.3 は `setup-manual.md`、§5 は `design-notes.md`、§6 と `meeting.json` の各キーは `meeting-folder.md`、§7 は `troubleshooting.md`、§8 は `files.md`。

## 3.2 親機の手動起動（環境変数で指す場合）

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
   - **会議より前に上げるなら `--start` は必ず明示する。省略は「同じ値」にならない。**
     `viewer2.py` は省略時に `meeting.json` の `start`(`meetlive_config.meeting_start_iso()`)
     へ退避するが、**`copilot.py` の `main()` はそこを見ず、読めない値を渡したときと同じく
     起動時刻を開始とする**。早めに上げるのは通常運用なので、既定のままだと番人の側だけ
     会議前から経過時間が進み、**開始前に「予定超過」のカードが出る**。
     実測(2026-09-26): 09:30 開始の会議のモニタを 08:49 に上げ、会議前に超過カードが出た。
     `--start 2026-09-26T09:30:00` を明示して上げ直し、会議前に出たカードは別ディレクトリへ
     退避した。`run.sh` も `--start` を渡されたときだけ両層へ転送するので、同じことが起きる。
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
   mic_match=                     ← 任意。§7.2 を見よ
   ```
   🔴 `config.txt` は**親機のアドレスと合言葉が平文で入るファイル**。
   git に入れない・他人に渡さない。配るのは `config.txt.example` の方だけ。
   例のまま(`CHANGE_ME...`)で起動すると、その場で止まって何を直すか出す。
3. **イヤホンを挿す**(START.bat より先に。§0（[`SKILL.md`](../SKILL.md)）)
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
