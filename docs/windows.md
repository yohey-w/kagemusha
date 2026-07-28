# Windows での代替トリガー（タスクスケジューラ）

`morning_brief.sh` は bash スクリプトなので、Windows では次のいずれかで時刻トリガーを組む。

---

## 方式A: WSL2 上でそのまま cron（推奨・一番素直）

WSL2 を使っているなら、Linux 側の cron がそのまま使える。

```bash
# WSL2 のシェルで
sudo service cron start          # 起動していなければ
crontab -e
# 追記:
53 6 * * *  /home/you/kagemusha/scripts/morning_brief.sh
```

注意: WSL2 は Windows 起動時に自動では立ち上がらない。確実に毎朝動かしたいなら、方式B でタスクスケジューラから WSL を叩くのが堅い。

---

## 方式B: タスクスケジューラ → WSL の bash を起動

WSL のスクリプトを Windows のタスクスケジューラから起動する。WSL が寝ていても Windows 側が起こす。

**GUI で:**

1. 「タスク スケジューラ」を開く → 「基本タスクの作成」。
2. 名前: `kagemusha morning brief`。
3. トリガー: 毎日 06:53。
4. 操作: 「プログラムの開始」。
   - プログラム/スクリプト: `wsl.exe`
   - 引数の追加: `-e bash -lc "/home/you/kagemusha/scripts/morning_brief.sh"`
5. 「最上位の特権で実行」は不要。「ユーザーがログオンしているかどうかにかかわらず実行」にするとロック中でも動く。

**`schtasks` コマンドで一発:**

```bat
schtasks /Create /TN "kagemusha morning brief" /SC DAILY /ST 06:53 ^
  /TR "wsl.exe -e bash -lc \"/home/you/kagemusha/scripts/morning_brief.sh\""
```

パス変換に注意: WSL 内の絶対パス（`/home/you/...`）を使う。Windows 側パス（`C:\...`）ではない。

---

## 方式C: ネイティブ Windows（WSL なし）

WSL を使わない場合は、bash スクリプトを PowerShell に移植するか、[Git for Windows](https://gitforwindows.org/) 同梱の bash で動かす。

```bat
schtasks /Create /TN "kagemusha morning brief" /SC DAILY /ST 06:53 ^
  /TR "\"C:\Program Files\Git\bin\bash.exe\" -lc \"/c/Users/you/kagemusha/scripts/morning_brief.sh\""
```

この場合 `config.env` のパスは Git-Bash 形式（`/c/Users/you/...`）で書く。AI CLI と `curl` が Windows 側 PATH から見えることを確認する。

---

## 動作確認

- 手で1回: `wsl.exe -e bash -lc "/home/you/kagemusha/scripts/morning_brief.sh"`
- ログ: `PROJECT_ROOT/logs/morning_brief_cron.log`（実行のたびに1行）と `morning_brief_YYYY-MM-DD.log`（CLI の生ログ）。
- 通知が来ない: `config.env` の `NTFY_TOPIC`、`curl` の疎通、`NTFY_ENABLED=1` を確認。
