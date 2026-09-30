# meeting-copilot — 収録物（§8）

同梱ファイルの役割を確かめたいときに読む。

> 節番号は SKILL.md と共通。§0・§1・§1.5・§3.1・§3.2・§3.2.5・§4 は SKILL.md 本文、§1.8 は `decision-layer.md`、§2 は `env-vars.md`、§3.2 の手動起動と §3.3 は `setup-manual.md`、§5 は `design-notes.md`、§6 と `meeting.json` の各キーは `meeting-folder.md`、§7 は `troubleshooting.md`、§8 は `files.md`。

## 8. 収録物

```
meeting-copilot/
├── SKILL.md
├── config/                          … 全部「架空の案件」の例。中身を入れ替えて使う
│   ├── meeting.example.json         … 会議1回ぶんの構え(会議フォルダの入口・§1.5)
│   ├── ledger.yaml.example          … 事実台帳(前提監視の基準)
│   ├── agenda_steps.example.json    … 段と必須取得物
│   ├── talk_script.example.md       … 台本(テレプロンプターの中身)
│   ├── phrasebook.example.json      … 定型回答・約束の境界の文言
│   ├── stage_resources.example.json … 舞台に出せるもの
│   ├── decisions.example.yaml       … 判定層の問いの束(§1.8)
│   └── example_meeting/             … そのまま起動できるデモ会議フォルダ(全部架空)
│       ├── agenda_sheet.md          … 進行表1枚。ここから下の2つを生成する(§6.2)
│       ├── agenda_steps.json / talk_script.md  … build_agenda.py の出力
│       ├── quick_facts.md           … 即答表(探し物アシストの索引・§6.3)
│       ├── decisions.yaml           … 判定層の問いの束(会議フォルダ側が勝つ)
│       └── roster.txt               … 判定層へ送る前に伏せる名前(§1.8.2)
├── tests/                           … 標準ライブラリだけの回帰テスト(CIのグループL)
│   ├── test_viewer_state.py         … 済の永続化/カード列/資料棚/合言葉/舞台/レイアウト
│   ├── test_mode_signal.py          … 開始合図(書く側と読む側が同じ入力を受理するか)
│   ├── test_build_agenda.py         … 進行表→段取り/カンペ(割り付け・注記・発明しない)
│   ├── test_cards.py                … カードの3要素/催促の抑制/終話検知/探し物/粒度
│   ├── test_responder.py            … 返し役(材料を切り詰めない・接地の関門)
│   ├── test_decision_engine.py      … 判定層(問いの組み立て/マスク/退避/採点)
│   └── test_decision_live.py        … 会議中の配線(カードの発火条件・見送り・予鈴)
└── scripts/
    ├── meetlive_config.py           … 置き場と設定の解決(既定の一元管理)
    ├── mode_signal.py               … 「同席開始」の判定(書く側・読む側で共有する1本)
    ├── step_detect.py               … 「いまどの段か」の判定(番人・画面で共有する1本)
    ├── build_agenda.py              … 進行表1枚 → agenda_steps.json + talk_script.md
    ├── lookup_assist.py             … 探し物アシスト(合図の検知と即答表の索引)
    ├── decision_engine.py           … 判定層(Rules / Jev / 退避・§1.8)
    ├── replay_eval.py               … 過去の逐語を流し直して判定層を採点する
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
