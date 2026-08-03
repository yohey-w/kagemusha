# evidence/ — 一周が実走している証拠 / proof the loop actually runs

このリポジトリの他の場所は**書式**だ（`templates/` はひな型、`docs/` は設計、`scripts/` は配管）。
書式は「こう回せる」と主張するが、「回っている」とは言えない。ここはその差分を埋める1本だ
——**著者の実走インスタンスから取った、手作業で匿名化した抜粋**。

> **In English.** Everything else in this repo is *form*: `templates/` are blanks, `docs/` is the
> design, `scripts/` is the plumbing. A form can claim the loop is runnable; it cannot show the
> loop running. This directory closes that gap with **hand-redacted excerpts from the author's
> live instance** — one unattended weekly-distillation run, and the two journal entries around a
> correction that ended up rewriting a principle in the model the agent reads each session.
> Two files, ~5 minutes to read. Scope and limits are stated below; nothing here is a benchmark.

---

## 中身 / what is here

| ファイル | 何の証拠か |
|---|---|
| [`weekly_distill_log_excerpt.txt`](weekly_distill_log_excerpt.txt) | **機構が無人で発火している**——OSスケジューラが日曜 21:04 に週次蒸留を起動し、その週の AI-CLI ログから承認者の発話 469 件を採り、142 件を判断信号として分類し、L1 の行数・原則数を lint した実ログ。**非ゼロ終了で終わった事実もそのまま載せてある**（成果物は出ている——詳細はファイル冒頭）。 |
| [`ledger_excerpt.md`](ledger_excerpt.md) | **訂正がモデルまで届いている**——2026-07-28 に承認者が一言で規律を曲げ（台帳へ記帳）、その週の蒸留が残した保留を 2026-08-03 に裁定した結果、**L1 原則の本文が同じ命題へ差し替わった**。台帳2件（追記専用・実発話 quote つき）。 |

**2つで一周が閉じる。** ログ側が「機構が回っている」、台帳側が「回った結果、判断が更新された」。
片方だけでは cron が動いているだけ、あるいは手で書いた作文と区別がつかない。

---

## いま常時動いている機構 / the standing mechanisms

このインスタンスで OS スケジューラに登録されている機構（2026-08-04 時点。キット同梱のものと、インスタンス固有のもの）:

| 周期 | 機構 | 対応するキットのファイル |
|---|---|---|
| 毎日 06:53 | 朝の差分アラーム（時刻トリガー T1） | `scripts/morning_brief.sh` |
| 10分ごと | 受信箱ウォッチ（受信箱トリガー T2） | `scripts/inbound_watch.sh.example` |
| 10分ごと | ハートビート監視（無音死の検知） | 実走インスタンス側 |
| **日曜 21:04** | **週次蒸留**（判断フィードバック） | `scripts/weekly_distill.sh.example` |
| 日曜 21:30 | 増補審査（台帳→執筆物への還流） | 実走インスタンス側 |

⚠️ **射程**: 無人発火の現物をこのディレクトリに置いてあるのは**週次蒸留（日曜 21:04）だけ**だ。
日曜 21:30 の増補審査は cron に登録済みだが、**スクリプトのタイムスタンプが 2026-08-03（月）で、
ログも同日の手動実行2本しか無い**——登録後まだ日曜を迎えていないので、「定刻で発火した」とは書かない。
また、週次蒸留の実走ランナーは**インスタンス側の変種**で、同梱の `.example` そのものではない
（採掘スクリプトのラベル差については `weekly_distill_log_excerpt.txt` の冒頭を参照）。

---

## 何を証明していて、何を証明していないか / scope

**証明している:**

- 週次蒸留が**人の起動なしに**定刻で走り、その週の実データを処理して成果物を出したこと
- 台帳が**追記専用の実ファイル**として存在し、実発話の quote を保持していること
- 訂正の日付・蒸留の窓・L1 差し替えの文言が**この順序で並んでいる**こと（配管内部の受け渡しそのものは非公開。→ `ledger_excerpt.md` の ⚠️ 注記）
- その原則が、**いまあなたが読んでいるキット本体**（README §5 の表・`templates/judgment_model.md` の原則1）に載っていること

**証明していない:**

- 効果の大きさ。**n=1・1インスタンス・1週間**であり、ベンチマークではない
- 他人の環境で同じ数字が出ること。バケット分布（CORRECT 64 件）は著者の仕事の性質に依存する
- 全機構の無人発火（上の射程を参照）
- 蒸留の**質**。ここにあるのは「一周した」証拠であって、「良い原則が出た」証拠ではない

---

## 匿名化の方針 / redaction policy

**手作業で削り、削った種類をここに明示する**（自動マスクは掛けていない。掛けたと書けるほど検証していないため）。

削ったもの: ①個人・機械のパス（`[HOME]` へ置換）②取引先・案件の名前と、業種・関係・時期の組で相手が特定できる記述
③金額・見積の数字 ④メールアドレス・非公開 URL・チャンネル識別子 ⑤内部文書名と、他の台帳エントリへの `D-` 番号参照
⑥ローカルのプロジェクトディレクトリ名（`[dir-1]` 等へ置換）⑦承認者・エージェントの内輪の呼称
（キットの語彙＝**承認者 / サブエージェント**へ置換）。

残したもの: **実発話の quote**（要約は台帳の規律違反）・日付・件数・判断の骨格・失敗の記録。

**残っている抜けの可能性は残っている抜けとして扱う。** 匿名化は人手であり、
機械ゲート（`tests/forbidden_patterns.txt`）が拾うのはそのうち既知のパターンだけだ。
見落としを見つけたら issue を立ててほしい——**「検査した」は「無い」の証明ではない**、
というのはこのキットが最初のページから言っていることでもある。

### allowlist は弱まっていない

`.gitignore` は「ルート直下は全部無視・キットだけ un-ignore」の allowlist 方式で、
**あなたの実データが構造上コミットできない**ことが売りだ（`scripts/test.sh` のグループ D がこれを実地検査する）。
`evidence/` を un-ignore したことでこの保証は**弱まっていない**:

- 追跡されるのは `evidence/` に**人が手で置いたファイルだけ**。`ssot/` `judgment/` `projects/` `briefs/` `logs/` `local/` は従来どおり構造的にコミット不能で、**ここへ自動で流れ込む経路は無い**
- したがって `evidence/` の中身は「漏れた実データ」ではなく、**1件ずつ検品して公開すると決めた抜粋**だ
- 追跡対象になったことで、**リーク検査（グループ C）がこのディレクトリも走査するようになった**——追跡しないほうが検査が緩くなる

---

## ひな型との食い違いについて / a note on the templates

[`templates/decisions_journal.md`](../templates/decisions_journal.md) にも「承認ゲートの軸を可逆/不可逆へ」という
サンプルエントリが `D-2026-07-28-01` として載っている。**あれは実記録ではなく、書式を見せるための例示だ**
（quote も読みやすく書き直してある。実台帳の `D-2026-07-28-01` はまったく別の件で、この裁定の実 ID は
[`ledger_excerpt.md`](ledger_excerpt.md) にあるとおり `D-2026-07-28-13` だ）。

**この食い違いこそ、このディレクトリを作った理由**だ。ひな型のサンプルはどこまで行っても著者が書いた説明文であり、
証拠にはならない。証拠として読んでよいのは、ここに置いた**実ファイルからの抜粋のほう**だけだ。

> **In English.** The sample entry in `templates/decisions_journal.md` is an *illustration* with a
> tidied-up quote and a sample ID; the real ruling is `D-2026-07-28-13`, reproduced in
> `ledger_excerpt.md` — redacted, but with the spoken quote left verbatim, which the template's
> is not. Template samples are the author explaining a format — they can never be
> evidence for it. Only the excerpts in this directory are.

---

## 自分で確かめられること / what you can check yourself

1. `bash scripts/test.sh` — キット自身の検収ゲート（skip 無し）。グループ C はこのディレクトリも走査する
2. `ledger_excerpt.md` の 2026-07-28 の裁定と、`templates/judgment_model.md` の原則1・README §5 の表を突き合わせる。**同じ命題が同じ軸で書かれているはず**
3. `weekly_distill_log_excerpt.txt` の lint 行（`L1本文=75行/上限160・原則数=31/上限32`）と、`templates/judgment_model.md` が宣言している上限（≤160行）を突き合わせる
