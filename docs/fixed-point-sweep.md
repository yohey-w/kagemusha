# fixed-point sweep — 定点掃引（差分型監視の設計パターン）

一度きりの調査は**スナップショットなので腐る**（[`../cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md) A6）。動く対象——競合の座標・語の使われ方・同じ棚の新刊・業界の資本の動き——を追い続けるなら、調査を**定点の便**にする。ここに置くのはその設計パターンと落とし穴だけで、**スクリプトの実物は載せない**（監視対象・鍵・パスは機体ローカルの持ち物で、汎用化できるのは形のほうだから）。

親戚のパターンは受信箱側の [`inbound-loop.md`](inbound-loop.md)（世界 → あなた）。あちらが「落ちてくるものを捕まえる」なら、こちらは「**動かないはずのものが動いたかを見に行く**」。設計原則はほぼ共通で、以下は差分型に固有の4点。

---

## (a) 基線を持ち、「新しい動きだけ」を報告する

既知の対象（見た URL・掴んだ ID・前回の値）を**基線ファイル**として持つ。便が報告するのは**基線に無かったものだけ**。

- **初回だけは全量**を基線に落とす（初回に報告させると、既存の全部が「新着」として噴き出して読まれなくなる）。
- 基線が空のとき「全部が新規」ではなく「**初回＝基線構築**」と扱う。ここを分けないと、基線ファイルが消えた日に大量誤報が出る。
- 新規ゼロなら**黙る**。「異常なし」を毎回送る便は、そのうち読まれなくなり、本物の通知も一緒に読まれなくなる。

## (b) 3状態を潰さない — NEW / NOCHANGE / FAILED

差分型の便が壊れる最大の道は、**取得の失敗を「変化なし」に丸めてしまうこと**だ。丸めた瞬間、便が死んでいても盤面は健康に見える。

| 状態 | 意味 | 出口 |
|---|---|---|
| **NEW** | 基線に無いものを見つけた | 通知する |
| **NOCHANGE** | 掃いた結果、新規が無かった | **沈黙**（ログにだけ1行） |
| **FAILED** | 掃けなかった（ネットワーク・認証切れ・レイアウト変更・レート制限） | **NOCHANGE とは別の文面で通知**する |

FAILED の通知は、NEW の通知と**見た目で区別できる文面**にすること。同じ形で届くと、受け取る側が「新着が来た」と誤読する。棚ごとに状態を持つのも要点で、**5棚のうち1棚だけ落ちた**を「全部異常なし」に潰さない（報告の先頭に載る棚リストが、そのまま状態の一覧になる）。

## (c) 基線への追記は、成功時のみの一方向ラチェット

**FAILED の回に基線を書き換えてはいけない。** 空の取得結果で基線を上書きすると、次の回に「全部が新規」として再噴出するか、逆に取り逃したものを既知として飲み込む。

- 基線は**成功した棚のぶんだけ・追記方向にのみ**動かす（削除・縮小はしない）。
- 対象が消えた場合も基線から消さない。消すと、復活したときに「新着」として二度目の通知が出る。
- 基線を人が編集したくなったら、それは通知の設計がずれている合図だ。手で消す運用が定着すると、基線が信用できなくなる。

## (d) 沈黙とスケジューラ故障を区別する

**NOCHANGE の沈黙と、便が起動しなかった沈黙は、受け取る側から見て同じに見える。** これが差分型で一番遅く発覚する壊れ方で、「最近静かだな」と思っていた期間、実は cron が一度も走っていなかった、という形で出る。

- **走ったこと自体を1行ログに残す**（時刻・棚ごとの状態・新規件数）。沈黙した回こそ記録が要る。
- ログの**最終実行時刻**を、定期の点検対象に入れる（盤面や朝の便から見える位置に置く）。
- 「N 回連続で走った形跡が無ければ知らせる」まで作れるなら作る。作らないなら、**沈黙は健康の証拠ではない**ことを運用側が知っていること。

---

> **In English.** A design pattern for *diff-shaped* watchers: keep a baseline of what you already know and report only what is new; never collapse the three states — NEW (notify), NOCHANGE (stay silent, log one line), FAILED (notify, in visibly different wording), because folding FAILED into NOCHANGE makes a dead watcher look healthy; advance the baseline only on success, append-only, one way; and log every run — including silent ones — because "no news" and "the scheduler never fired" are indistinguishable from the receiving end. No script is shipped here: the targets, credentials and paths are machine-local, and only the shape generalises.
