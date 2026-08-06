# ledger_excerpt.md — 判断台帳からの匿名化抜粋 / redacted excerpt from the live journal

> **実台帳からの匿名化抜粋。** 書式の完全版（ひな型・4つの規律・記帳判定器8トリガー）は
> [`templates/decisions_journal.md`](../../../templates/decisions_journal.md)。
> **実ファイル側では、この2件は書かれて以降 in-place で編集されていない**
> ——台帳は追記専用で、**訂正は上書きではなく `revises:` を付けた新エントリで行う**（イベントソーシング）。
> **ただしこの抜粋自体は逐語ではない**: 下記の方針で語彙を置換してある（実発話の quote だけは逐語）。
>
> **A redacted excerpt from the real journal.** The full format lives in
> [`templates/decisions_journal.md`](../../../templates/decisions_journal.md). In the real file
> neither entry has been edited in place since it was written — the journal is append-only and
> corrections arrive as *new* entries carrying `revises:`. **This excerpt, however, is not
> verbatim**: vocabulary was substituted per the policy below. The quoted speech is.

**匿名化で落としたもの / what was removed:** 承認者・エージェントの呼称は
キットの語彙（承認者 / サブエージェント）へ置換。他エントリへの `D-` 番号参照は
一般化。案件名・相手・金額・内部パス・内部文書名は削除。
**残したもの:** 実発話の quote（要約禁止が台帳の規律その2）・日付・判断の骨格。

---

## なぜこの2件か / why these two

この2件だけで**一周が閉じている**のが見えるから。

1. **2026-07-28** — 承認者が一言で規律を曲げた（**訂正**）。台帳に記帳。エントリ末尾に
   「一般化できる原則の候補＝**承認ゲートは可逆/不可逆で設計する**」を残した。
2. **2026-08-02（日）21:04** — 週次蒸留が無人発火し、07-26〜08-02 の窓を処理
   （＝この窓に 07-28 の記帳が入っている。実ログは [`weekly_distill_log_excerpt.txt`](weekly_distill_log_excerpt.txt)）。
   この run は**非ゼロ終了で終わっているが、保留リストは 21:20 に書き出されている**——下記の保留4件がそれだ。
3. **2026-08-03** — その蒸留が残した保留4件を承認者が裁定。**保留1は L1（価値判断モデル）の原則の本文差し替え**で、
   その差し替え文言は 07-28 の「原則の候補」と**同じ命題**だった。

`却下・訂正 → 台帳（L2） → 週次蒸留 → 価値判断モデル（L1） → 次のセッションの一次判断`
——README §5「却下を資産に変える」の主張が、日付の付いた3イベントとして残っている。

⚠️ **ここで観測できるのは「窓の重なり」と「文言の一致」と「順序」であって、
配管の中で候補が運ばれた瞬間そのものではない**（蒸留の中間出力は非公開のため）。断定を1段落とすなら:
*07-28 に記帳された候補と同じ命題が、その週の蒸留の保留として 08-03 に差し出され、裁可された。*

**そして一周はこのリポジトリの外まで出ている。** 差し替わった原則
「承認ゲートは可逆/不可逆で切る」は、キット本体の README §5 の表
（*reversible = auto / irreversible = approval queue*）と
[`templates/judgment_model.md`](../../../templates/judgment_model.md) の原則1（P1）に載っている。
**下の 2026-07-28 の一言と同じ命題が、いまあなたが読んでいるキットの本文になっている。**

> **In English.** Three dated events. 07-28: the approver overruled a standing rule in one
> sentence; the entry closes with a *candidate principle* — gate on reversible/irreversible.
> 08-02 21:04: the weekly distiller fired unattended over the 07-26→08-02 window, which contains
> that entry. 08-03: the approver ruled on the four items the run had left pending; item 1 was a
> **text replacement of an L1 principle**, carrying the same proposition as the 07-28 candidate.
> ⚠️ What is observable here is the overlapping window, the matching proposition and the ordering
> — not the intermediate hand-off inside the pipeline, which is not published. The claim is kept
> at that strength deliberately. The circuit does reach outside this repo, though: that same
> proposition is what README §5 and principle 1 (P1) of `templates/judgment_model.md` now say.

---

## D-2026-07-28-13 git push は承認不要へ（判定基準を「外向きか」から「戻せるか」へ付け替え）

- **承認者の実発話**: 「Gitのpushはおれの許可無しでやってよい。**だってもどせるから**。これをいちいちおれが承認をやりだしたらきりがない」
- **裁定**: **git push は顧客リポジトリを含めて承認不要**。エージェント指示ファイル（`CLAUDE.md`）の中核規律1を改訂。
- **なぜ(仮説)**: 旧規律は「顧客リポへの push ＝外向き＝承認」だったが、**外向きかどうかは本当の判定軸ではなかった**。守るべきは「**取り消せない操作**」であり、git は履歴が残り revert できる。**取り消せる操作にまで承認を掛けると、承認そのものが律速になる**——本日、サブエージェントの push を2回「規律を越えた」と報告する事態が起き、承認者の帯域を消費した。北極星（**承認者をボトルネックにしない**）に照らすと、**可逆な操作の承認は削るべき律速**。
- **残した例外（git でも戻せなくなるもの）**: ①`--force`（`--force-with-lease` 以外）②タグ・ブランチの削除 ③履歴の書き換え ④公開リリースの作成（外部が取得したら取り消せない）⑤**push が本番へ自動デプロイされる場合**——**push は戻せてもデプロイ済みの副作用は戻せない**。
- **あわせて課した義務**: **押した事実は報告する**。承認は不要でも、何をどこへ push したかを黙るのは別問題。
- **一般化できる原則の候補**: **承認ゲートは「外向き／内向き」でなく「可逆／不可逆」で設計する**。外向きでも戻せるものは自動化し、内向きでも戻せないもの（DB削除・データ移行）は承認を残す。**OSSキットのマンデート設計に反映する価値がある**——現行の README は「内向き＝自動／外向き＝承認」の二分法で書かれており、この軸のほうが正確。
- **検証（反復）**: 次に承認を求めた操作が「戻せるもの」だったら、この規律が機能していない証拠。週次蒸留で確認する。

> **Gloss.** *"You can push git without my permission. **Because it can be undone.** If I start
> approving each one, there's no end to it."* → Ruling: `git push` needs no approval, client repos
> included. Kept as exceptions the five git operations that genuinely cannot be undone
> (`--force`, tag/branch deletion, history rewrite, publishing a release, and a push that
> auto-deploys to production — *the push is revertible, the deployed side effect is not*).
> Added obligation: **you don't need approval, but you do have to report what you pushed where.**
> Candidate principle: gate on reversible/irreversible, not inward/outward — and note the entry
> flags that the kit's own README was, at that moment, still written on the weaker axis.

---

## D-2026-08-03-02 週次蒸留・初回の保留4件の裁定（承認者「君の判断どおりでよい」）

- 保留1: ✅ 反映済み。**L1原則(12) を「戻せる限り先行してよい——承認ゲートは可逆/不可逆で切る」へ本文差し替え**（ID不変・例外5件明記・送信/公開は不可逆側として承認維持）。形式確認は実走インスタンス本体がこの場で実施
- 保留2: 血統の異なるモデル（Codex）へ設計諮問を発注（**未確認の断定を出力前に強制チェックする機構**・red team 込み）
- 保留3: 寝かせる（n=1。2件目が出たら昇格候補）
- 保留4: ✅ 反映済み。L1 に引用書式規約を追記（引用は安定 ID のみ・表示番号では引かない）

> **Gloss.** The first weekly distillation run had left four items pending for the approver.
> Ruling: *"your call is fine."* (1) The L1 principle text was **replaced** with "act first as long
> as it can be undone — gate on reversible/irreversible", ID unchanged, five exceptions spelled
> out, sending/publishing kept on the approval side. (2) A design question was sent to a
> *different-vendor* model on purpose — same-vendor review does not catch same-vendor failure
> modes. (3) One proposal was **left to sit**: n=1 is not a principle. (4) A citation rule was
> appended: cite by stable ID, never by display number.
>
> Note what (3) is doing there. The distiller is allowed to propose and the approver is allowed to
> say "not yet" — **a distiller that never gets told "wait" is a distiller nobody is reading.**

---

## この2件から読めること / what the pair demonstrates

| 主張（README） | この抜粋での現れ方 |
|---|---|
| 台帳は追記専用・訂正は `revises:` の新エントリ | 実台帳では、08-03 の裁定後も 07-28 のエントリがそのまま残っている（差し替えではなくエントリが増える） |
| quote は要約しない（実発話をコピペ） | 「だってもどせるから」——裁定の理由が**承認者の言葉のまま**残り、6日後の蒸留がこれを材料にできた |
| 訂正 > 裁定（訂正はモデルと人間の差分） | 07-28 は裁定ではなく**訂正**（既に焼いてあった規律を曲げた）。差分だから L1 まで届いた |
| 蒸留は提案止まり・確定は承認者 | 保留4件が承認者に差し出され、うち1件は「寝かせる」で**採用されなかった** |
| L1 は薄く保つ（≤160行・原則数に上限） | 原則の**追加ではなく本文差し替え**・ID 不変（`weekly_distill_log_excerpt.txt` の lint 行が 75/160行・31/32原則を実測） |
