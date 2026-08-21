# 正本記述テンプレート / Canonical Context Template

対象は"系"に限らない。**外部レビュー・新しい班への発注・引き継ぎ・将来の自分**に渡す文脈の正本を作るための型。
This is not limited to "systems." Use it whenever you need a single authoritative snapshot of context to hand to an external reviewer, a new team, a successor, or your future self.

## ヘッダ / Header

- **対象名 / Subject**: {この記述が指す系・案件・仕組みの名前}
- **版 / Version**: v{N} — {YYYY-MM-DD}
- **更新規律 / Update rule**: 変更したら版を上げる。外部に渡すときは常に最新版を丸ごと渡す。
  Bump the version on any change. When handing this out, always attach the full latest version — never a stale copy or an excerpt.

## §1 目的と境界 / Purpose & Boundary

この系・案件は何で、何でないか。1〜3行。
例: 「これは顧客との週次同期の運用フローであり、開発の実装仕様ではない」

## §2 構成要素 / Components

層で分解し、各要素を1行で。
例:
- 入力層: 顧客Slack・メール
- 判断層: 判断台帳
- 出力層: 台本・確認シート

## §3 界面 / Interfaces

入出力・イベントソースを**全列挙**。各項目に「機械可視か / 監視は自動か」を添える。
例: 「顧客Slackチャンネル ― 機械可視: Yes（MCP経由） ― 監視: 手動起動」

## §4 不変条件と権限境界 / Invariants & Authority Boundaries

崩してはいけない前提・誰が何を決めてよいか。
例: 「¥に関わる範囲の決定は殿のみ」

## §5 実装状態の正直な表 / Honest Implementation State

「あるべき姿」と「いまの姿」を混ぜない。3区分で書く。
| 区分 | 内容 | 場所 |
|---|---|---|
| 実装済み | {何が} | {ファイル/場所} |
| 未実装 | {何が} | — |
| 手動運用 | {何が} | {誰がどうやって} |

## §6 既知の穴・未解決 / Known Gaps & Open Issues

射程（どこまで確認したか）をつけて書く。断定するな、埋まっていなければ〔要確認〕。
例: 「エラー時のリトライ挙動〔要確認・コード未読〕」

## §7 計器 / Instrumentation

何で健全性を測るか。ログ・台帳・メトリクスの場所。

---

## 使い方note / Usage note

外部諮問・新しい班への発注・引き継ぎには、**本文を丸ごと**添付すること。
切り抜き（一部の節だけ）を渡すと、相手には見えていない層の穴を指摘できない——MECEが崩れる。
Attach the whole document to external consultations, handoffs, or new-team briefs. A partial excerpt breaks MECE coverage: the recipient can't flag problems in a layer they were never shown.
