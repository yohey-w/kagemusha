# Documentation map

*English first, 日本語は下.*

The README answers five things and stops: what this is, whether it is for you, how to run it safely once, where the evidence is, and which document to open next. **This page is that "next".**

## Where to go by task

| What you want to do | Read this |
|---|---|
| Try it without installing, then install it | [`getting-started.md`](getting-started.md) — the 10-minute demo, the prerequisite table, the copy-paste steps |
| Run it day to day and week to week | [`operations.md`](operations.md) — the morning pass, the weekly ruling, multiple projects, counting your own work |
| Understand the whole design | [`design.md`](design.md) — the loop diagram, the four-layer equation, calibrated reliance |
| Know what is yours and what is the kit's | [`layers.md`](layers.md) — the core / cookbook boundary and the data boundaries |
| Turn rejections into rules | [`judgment-distillation.md`](judgment-distillation.md) · the light daily lane: [`distillation-loop.md`](distillation-loop.md) · after promotion: [`discipline-audit.md`](discipline-audit.md) · back into the generator: [`norms-loop.md`](norms-loop.md) |
| Catch what the world sends you | [`inbound-loop.md`](inbound-loop.md) · the watcher pattern behind it: [`fixed-point-sweep.md`](fixed-point-sweep.md) |
| Hand a decision to a human well | [`decision-cards.md`](decision-cards.md) |
| Run it on Windows | [`windows.md`](windows.md) |
| Ask the questions everyone asks | [`faq.md`](faq.md) |
| See where each idea entered the kit | [`provenance.md`](provenance.md) · moved paths: [`path-migrations.md`](path-migrations.md) |

## What's in the box

| Path | Role |
|---|---|
| **`templates/decisions.md`** | SSOT — what's decided (and what's been superseded). Append-only, event-sourced. |
| **`templates/tasks.md`** | SSOT — who owes what, by when, and where it came from. |
| **`templates/glossary.md`** / **`people.md`** | SSOT — canonical terms and named people (for wording lints & addressee checks). |
| **`templates/approval_queue.md`** | The queue outward operations pile into. Has a **"doubt" field** so review takes seconds. |
| **`templates/verifiers.md`** | Standing verifiers — a machine layer of lints + deliverable-type Definitions of Done. |
| **`templates/decisions_journal.md`** | **Judgment journal (L2)** — append-only log of rulings/corrections/rejections, with verbatim quotes. |
| **`templates/judgment_model.md`** | **Value-judgment model (L1)** — the thin canon (≤160 lines) the agent reads each session. |
| **`templates/system_map.md`** | **System map** — the one-screen board (standing mechanisms + one card per project + roadmap). Scaffolds to the instance root. |
| **`templates/charter.md`** | **Project charter** — per-project *deltas* only (≤60 lines); the judgment model itself never splits. Copy into `projects/<name>/charter.md`. |
| **`templates/agent_instructions.md`** | **The instance constitution** — saved as `CLAUDE.md` (Claude Code) / `AGENTS.md` (Codex) / your tool's rules file. |
| **[`cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md)** | **Starter disciplines** — on the **sample shelf**, a *menu, not a template* (deliberately **not** scaffolded by `setup.sh`): disciplines burned in the author's live instance, each with the burn it came from, a portability label, and a paste target. Take only the ones whose hole you've already fallen into. |
| **`templates/discipline_catalog.example.yaml`** / **`templates/discipline-audit-prompt.md`** | The audit's two halves: the catalog of disciplines you want watched (with the regex that catches each one), and the weekly prompt that turns candidates into a ≤30-line finding. |
| **`templates/inbound_sweep.md`** | **Inbound sweep procedure (Tier 1)** — the inbox trigger run through your assistant's MCP connectors: lanes, closed-enum triage, append-only ledger, quiet hours. |
| `.gitignore` | Allowlist — only the kit is tracked, so your instance data can never be committed. |
| `scripts/setup.sh` | Scaffold all of the above into the clone itself (default) or a target dir (safe to re-run). |
| `scripts/morning_brief.sh` | The time trigger — an inward-only, read-only morning stock-take. |
| **`scripts/mine_conversations.py`** | Extract the approver's own turns from AI-CLI logs (rulings/corrections). |
| **`scripts/filter_judgments.py`** | Bucket those turns into RULE/REJECT/CORRECT/… (vocab configurable, EN+JP defaults). |
| **`scripts/discipline_scan.py`** | **Is a discipline you adopted doing anything?** Walks your own session logs and quotes the passages where each one fired or broke. It matches and quotes; **it does not judge**. See [`docs/discipline-audit.md`](discipline-audit.md). |
| **`scripts/weekly_distill.sh.example`** | The weekly feedback trigger — mine → journal → distill into the model (proposes; you confirm). |
| **`scripts/correction_scan.py`** | The daily harvest, no LLM: yesterday's corrections, grouped into **events**, appended to a local material file plus a provenance index (full session id, line number, sha256) so `--show-event` can reopen any quote in its original context. Your correction vocabulary is not shipped — you supply `--patterns` (menu: `templates/correction_patterns.example.txt`). |
| **`scripts/distill.sh`** | The **material** trigger — fires only when enough corrections have piled up (the time-based fallback is OFF by default — a slow week gets named in the skip line, not distilled), freezes a **batch manifest** before it calls anything, invokes the model **without file permissions** (the report comes back on stdout), validates that report against the manifest, appends it to the promotion queue itself, and keeps FIRED / SKIPPED / **FAILED** apart. [`docs/distillation-loop.md`](distillation-loop.md). |
| **`templates/distill-prompt.md`** / **`templates/promotion_queue.md`** | The distillation prompt (one rule line plus eight fields per candidate; conflicts with your existing principles are *held*, not resolved) and the queue you empty by hand — the promotion step that stays a person. |
| **`scripts/inbound_watch.sh.example`** | The inbox trigger, Tier 2 — inward-only inbound watch for unattended scheduler runs (Slack / Gmail-IMAP / RSS lanes; immutable ledger; quiet-hours roll-up). |
| `scripts/test.sh` | The kit's own acceptance gate — run `./scripts/test.sh` (needs `shellcheck`); CI runs this exact command. It really executes `setup.sh` in a throwaway clone, proves the allowlist `.gitignore` makes instance data uncommittable, and drives `morning_brief.sh` with a fake CLI. No skips: a missing tool is a failure. |
| `docs/design.md` | Implementation guide: the four parts + mandate, mapped to files. |
| **`docs/judgment-distillation.md`** | The feedback side in full: 4 layers, 8 triggers, event sourcing, the weekly 7-step, three-layer change governance. |
| **`docs/inbound-loop.md`** | The inbound-watch loop: lanes & cadences, quiet hours, the immutable ledger, injection defense, the batch-level baseline lesson, Tier 1 / Tier 2. |
| `docs/fixed-point-sweep.md` | Fixed-point sweep — the diff-shaped watcher pattern: a baseline of the known, the three states NEW / NOCHANGE / FAILED kept apart, an append-only baseline advanced on success only, and why a silent run still has to be logged. |
| **`docs/decision-cards.md`** | Decision cards — cognitive design of the approval hand-off: two or three lines of premise (the approver has not read the correspondence — by design), the artifact itself, one recommendation, a no-answer default, severity marks, ≤3 per batch, and the **zero-context gate** an author cannot run on their own card. |
| **`docs/distillation-loop.md`** | The distillation courier — harvest daily for free, fire on **material** rather than the clock, and why the run may write only a promotion queue: moving text needs no gate, promoting a correction into a rule does. |
| **`docs/discipline-audit.md`** | Discipline audit — what it proves is **not** that a discipline works, but that the mechanism detecting breaches is running. **Trace** vs **prohibition** (compliance with a prohibition is unobservable), why an auditable discipline must be written as a trace, and the weekly three steps. |
| **`docs/norms-loop.md`** / **`ssot/norms/`** | **Making your edits compound** — where a correction to a *deliverable* goes. Burn it into the detector and you only get faster at finding the same failure (linear); burn it into the brief the first draft is written from and it stops happening (compounding). The distillation of a revision, the promotion ladder (only the top rungs enter the next brief, so one deliverable's quirk is not transferred onto all of them), the instrument (first-pass findings over time), and the overfit guards. The shelf ships **empty** — a README and one blank `.example`; your entries are uncommittable by the same allowlist that protects the rest of `ssot/`. |
| **`docs/provenance.md`** | Provenance table — which idea entered the kit, in which file, in which commit, and what set it off. Every trigger cell carries a tag saying how strongly it is sourced. |
| `docs/windows.md` / `docs/faq.md` | Task Scheduler alternative; FAQ. |
| **[`cookbook/author/evidence/`](../cookbook/author/evidence/README.md)** | **Proof the loop actually runs** — on the **sample shelf**: hand-redacted excerpts from the author's live instance, one unattended weekly-distillation run, and the two dated journal entries that bracket a correction ending up as a rewritten principle in the judgment model. Scope and limits stated in [`cookbook/author/evidence/README.md`](../cookbook/author/evidence/README.md). |
| **[`docs/getting-started.md`](getting-started.md)** | **Try it, then install it** — the 10-minute demo in full (with the three screenshots), the additive prerequisite table, the copy-paste steps, and the optional verifier from a different model lineage. |
| **[`docs/operations.md`](operations.md)** | **Your day and your week** once the loop runs — the morning pass, the weekly ruling, several projects at once (charter + system map), and the G/S/D/V/I/R codebook for counting where your own time goes. |
| **[`docs/norms-loop.md`](norms-loop.md)** | **Making your edits compound** — sending a correction back to the *generator* rather than the checker: the distillation of a revision, the promotion ladder, the instrument, the overfit guards. |
| `docs/README.md` | This page — the document map plus this table. |

## Related & prior work

This layer already has good pioneers; this kit owes them a lot.

- **[humanlayer](https://github.com/humanlayer/humanlayer)** — the standout approval layer that interposes human approval on an agent's high-risk operations, as an SDK, over Slack/email.
- **[CoWork OS](https://github.com/CoWork-OS/CoWork-OS)** / **[AgentOS (Agno)](https://github.com/agno-agi/agno)** — OS layers for work agents with approval gates and execution visibility.
- **[ACE (Agentic Context Engineering)](https://arxiv.org/abs/2510.04618)** — research on incrementally updating a playbook from execution traces (Generator / Reflector / Curator).
- **[ZOZO's weekly rules-update practice](https://zenn.dev/zozotech/articles/20260423_pr_review_claude_rules)** — collecting and distilling PR-review comments weekly into agent rules (humans review adoption). The same loop as our "distilling rejections," run in the code-review world.

This kit's one differentiator: **it treats the human's judgment log (the queue's reject/edit reasons) as a first-class input, and runs non-code work on plain markdown alone.**

## Genealogy (same author, prior work)

- **[multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun)** — parallel orchestration; topology design across many agents.
- **[CoDD (codd-dev)](https://github.com/yohey-w/codd-dev)** — deliverable verification ("consistency-driven development"); the "prevent false success" idea. This kit's verifiers are its work-world version.

Third in the series: orchestration (who acts) → verification (is it right) → **mandate (how far to trust)**.

---
---

# ドキュメント地図

README が答えるのは5つだけで、そこで止まる——これは何か・あなた向けか・安全に一度動かす道・証拠はどこか・次にどの文書を開くか。**このページがその「次」**。

## 仕事別の行き先

| やりたいこと | 読む文書 |
|---|---|
| 入れずに試す→入れる | [`getting-started.md`](getting-started.md)——10分デモ・前提表・コピペ手順 |
| 毎日と毎週まわす | [`operations.md`](operations.md)——朝の一周・週次の裁定・複数案件・自分の仕事の数え方 |
| 設計の全体を掴む | [`design.md`](design.md)——ループ全景・4層の等式・依存校正 |
| どこまでが自分の物か知る | [`layers.md`](layers.md)——core と cookbook の境界・データ境界 |
| 却下を規律に変える | [`judgment-distillation.md`](judgment-distillation.md)・軽い日次レーン: [`distillation-loop.md`](distillation-loop.md)・昇格した後: [`discipline-audit.md`](discipline-audit.md)・生成側への還流: [`norms-loop.md`](norms-loop.md) |
| 世界からの入力を捕まえる | [`inbound-loop.md`](inbound-loop.md)・その背後の監視パターン: [`fixed-point-sweep.md`](fixed-point-sweep.md) |
| 人間にうまく判断を渡す | [`decision-cards.md`](decision-cards.md) |
| Windows で回す | [`windows.md`](windows.md) |
| よくある疑問 | [`faq.md`](faq.md) |
| どの思想がいつ入ったか | [`provenance.md`](provenance.md)・移動したパス: [`path-migrations.md`](path-migrations.md) |

## 中身の早見表

| パス | 役割 |
|---|---|
| **`templates/decisions.md`** | SSOT——何が決まっているか（と失効したか）。追記専用・イベントソーシング。 |
| **`templates/tasks.md`** | SSOT——誰が・何を・いつまでに・どこから来たか。 |
| **`templates/glossary.md`** / **`people.md`** | SSOT——用語・登場人物（表記 lint・宛名突合用）。 |
| **`templates/approval_queue.md`** | 外向き操作を積むキュー。**「迷い」欄**つきで承認が数十秒に。 |
| **`templates/verifiers.md`** | 常設検証器——機械層の lint ＋ 成果物タイプ別 DoD。 |
| **`templates/decisions_journal.md`** | **判断台帳（L2）**——裁定・訂正・却下の追記専用ログ。実発話 quote 付き。 |
| **`templates/judgment_model.md`** | **価値判断モデル（L1）**——エージェントが毎セッション読む薄い正本（≤160行）。 |
| **`templates/system_map.md`** | **システム地図**——1画面の盤面（恒久機構＋案件カード＋ロードマップ）。実走 dir の直下に展開。 |
| **`templates/charter.md`** | **プロジェクト憲章**——案件ごとの*差分*だけ（≤60行）。価値判断モデル自体は割らない。`projects/<案件>/charter.md` へコピーして使う。 |
| **`templates/agent_instructions.md`** | **実走環境の憲法**——`CLAUDE.md`（Claude Code）/ `AGENTS.md`（Codex）/ 使うツールのルールファイルとして保存。 |
| **[`cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md)** | **スターター規律集**——**標本棚**にある*雛形ではなくメニュー*（`setup.sh` は意図的に展開しない）: 作者の実走で焼けた規律集。各本に「焼けた出自」・可搬性ラベル・貼り先が付く。**自分が踏んだ穴のものだけ**持ち帰る。 |
| **`templates/discipline_catalog.example.yaml`** / **`templates/discipline-audit-prompt.md`** | 規律監査の両輪——監査したい規律のカタログ（規律ごとの検出パターン付き）と、候補を30行以内の所見に変える週次プロンプト雛形。 |
| **`templates/inbound_sweep.md`** | **受信箱スイープ手順書（Tier 1）**——アシスタントの MCP コネクタで回す受信箱トリガー: レーン・閉じた enum 分類・追記専用台帳・quiet hours。 |
| `.gitignore` | allowlist 方式——キットだけを追跡。あなたの実データは構造上 commit 不能。 |
| `scripts/setup.sh` | 上記一式を clone 自身（既定）または任意 dir へ展開（再実行安全）。 |
| `scripts/morning_brief.sh` | 時刻トリガー——内向き専用・読み取り専用の朝の棚卸し。 |
| **`scripts/mine_conversations.py`** | AI CLI ログから承認者の発話（裁定・訂正）を抽出。 |
| **`scripts/filter_judgments.py`** | それを RULE/REJECT/CORRECT/… にバケット分類（語彙は設定可・日英デフォルト）。 |
| **`scripts/discipline_scan.py`** | **取り入れた規律は、自分の環境で動いているか。** 自分のセッションログを走査し、規律ごとに発火・破れの原文断片を引用する。引用して止まる——**判定はしない**。→ [`docs/discipline-audit.md`](discipline-audit.md) |
| **`scripts/weekly_distill.sh.example`** | 週次フィードバックトリガー——採掘 → 台帳 → モデルへ蒸留（提案止まり・承認者が確定）。 |
| **`scripts/correction_scan.py`** | 毎日の採取（LLM不使用）。前日の訂正を**イベント**に束ねてローカルの素材ファイルへ追記し、同時に出典の索引（完全なセッションID・行番号・SHA-256）を書く——`--show-event` で引用を前後文脈ごと開き直せる。訂正の語彙は同梱しない——`--patterns` で自分のものを渡す（メニュー: `templates/correction_patterns.example.txt`）。 |
| **`scripts/distill.sh`** | **材料**トリガー——貯まった時だけ焚く（時間フォールバックは既定OFF——薄い週は焚かずスキップ行で名指し）。呼ぶ前に**バッチ台帳**を固め、モデルは**ファイル権限なし**で叩いて報告を標準出力で受け、台帳と突合してから審査キューへ**ラッパー自身が**追記する。FIRED / SKIPPED / **FAILED** を潰さない。→ [`docs/distillation-loop.md`](distillation-loop.md) |
| **`templates/distill-prompt.md`** / **`templates/promotion_queue.md`** | 蒸留プロンプト（規律案1行＋8欄の審査書式・既存原則との競合は**解決せず保留枠へ**）と、人が手で空にする審査キュー——昇格だけは人間に残る工程。 |
| **`scripts/inbound_watch.sh.example`** | 受信箱トリガー Tier 2——無人スケジューラ実行用の内向き専用 inbound watch（Slack / Gmail-IMAP / RSS レーン・不変台帳・quiet hours ロールアップ）。 |
| `scripts/test.sh` | キット自身の検収ゲート。`./scripts/test.sh` で実行（`shellcheck` が必要）、CIも同じコマンドを回す。使い捨てクローンで `setup.sh` を実地実行し、allowlist `.gitignore` が instance データを構造的にコミット不能にしていることを証明し、偽のCLIで `morning_brief.sh` を走らせる。skipは無い——ツールが無ければ失敗として数える。 |
| `docs/design.md` | 実装の手引き: 4部品＋マンデートのファイル対応表。 |
| **`docs/judgment-distillation.md`** | フィードバック側の全体: 4層・8トリガー・イベントソーシング・週次7段・三層の変更ガバナンス。 |
| **`docs/inbound-loop.md`** | inbound watch の全体: レーンと周期・quiet hours・不変台帳・インジェクション防御・バッチ単位ベースラインの教訓・Tier 1 / Tier 2。 |
| `docs/fixed-point-sweep.md` | 定点掃引——差分型監視の設計パターン: 既知の基線・3状態（NEW / NOCHANGE / FAILED）を潰さない・基線は成功時のみの一方向ラチェット・沈黙した回もログに残す。 |
| **`docs/decision-cards.md`** | 判断カード——承認の差し出しを認知設計する: **前提2〜3行**（承認者は設計上、経緯を読んでいない）・現物・推奨・無回答時・重み・1バッチ3枚と、書き手には回せない**前提ゼロゲート**。 |
| **`docs/distillation-loop.md`** | 蒸留便——採取は毎日ただで・発火は**時刻でなく材料**で。書いてよいのが審査キューだけである理由: 移動に関門は要らないが、**訂正を規律へ昇格させるには要る**。 |
| **`docs/discipline-audit.md`** | 規律の監査——証明できるのは「規律が効いている証拠」ではなく**「破れを検出する仕組みが動いている証拠」**。**痕跡型と禁止型**（禁止型の遵守は観測不能）・監査したい規律は痕跡形で書け・週次の3ステップ。 |
| **`docs/norms-loop.md`** / **`ssot/norms/`** | **作業改善を複利にする**——成果物への**直しをどこへ戻すか**。検出器（検査する工程）へ戻すと同じ失敗を見つけるのが速くなるだけ（線形）、生成側（初稿を書くときの指示文）へ戻すと最初から起きなくなる（複利）。改稿の蒸留・昇格階段（上の段だけが次の指示文に入る＝1本の癖を全成果物へ転写しないための敷居）・複利の計器（1巡目の確定指摘数の推移）・過剰適合のガード。**棚は空で出荷される**——README と空の `.example` だけで、あなたのエントリは `ssot/` の他と同じ許可リストによりコミット不能。 |
| **`docs/provenance.md`** | 来歴表——どの思想が・どのファイルに・どのコミットで・何をきっかけに入ったか。きっかけ欄には「どこまで裏が取れているか」の出所タグが必ず付く。 |
| `docs/windows.md` / `docs/faq.md` | タスクスケジューラ代替／FAQ。 |
| **[`cookbook/author/evidence/`](../cookbook/author/evidence/README.md)** | **一周が実走している証拠**——**標本棚**にある、著者の実走インスタンスから取った匿名化抜粋。無人発火した週次蒸留の実ログ1本と、訂正が価値判断モデルの本文差し替えに至るまでを日付で追える台帳2件。射程と限界は [`cookbook/author/evidence/README.md`](../cookbook/author/evidence/README.md) に明記。 |
| **[`docs/getting-started.md`](getting-started.md)** | **試す→入れる**——10分デモの全文（スクショ3枚つき）・積み上げ式の前提表・コピペ手順・任意の血統違い検算器。 |
| **[`docs/operations.md`](operations.md)** | **走り出したあとの毎日と毎週**——朝の一周・週次の裁定・複数案件（憲章＋システム地図）・自分の時間を数える G/S/D/V/I/R のコードブック。 |
| **[`docs/norms-loop.md`](norms-loop.md)** | **作業改善を複利にする**——直しを検査側でなく**生成側**へ戻す: 改稿の蒸留・昇格階段・複利の計器・過剰適合ガード。 |
| `docs/README.md` | このページ——ドキュメント地図とこの表。 |

## 関連・先行プロジェクト

この層には既に良い先行者がいる。本キットは彼らの仕事に多くを負っている。

- **[humanlayer](https://github.com/humanlayer/humanlayer)** — エージェントの高リスク操作に人間の承認を割り込ませる承認レイヤーの本命。Slack/メール経由の承認ワークフローを SDK として提供する。
- **[CoWork OS](https://github.com/CoWork-OS/CoWork-OS)** / **[AgentOS (Agno)](https://github.com/agno-agi/agno)** — 承認ゲートや実行可視化を備えた、業務エージェントの OS レイヤー。
- **[ACE (Agentic Context Engineering)](https://arxiv.org/abs/2510.04618)** — 実行トレースからプレイブックを増分更新する自己改善の研究（Generator / Reflector / Curator）。
- **[ZOZO の週次 rules 更新運用](https://zenn.dev/zozotech/articles/20260423_pr_review_claude_rules)** — PR レビュー指摘を週次で収集・蒸留してエージェントのルールへ還流する（採用は人間がレビュー）先行実践。本キットの「却下の蒸留」と同じ輪をコードレビューの世界で回している。

本キットの差別化は一点: **人間の裁定ログ（承認キューの却下・修正理由）を第一級の入力とし、非コード業務を素の markdown だけで回す最小構成**であること。

## 系譜（同じ作者の前作）

- **[multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun)** — 並列オーケストレーション。複数エージェントのトポロジー設計。
- **[CoDD (codd-dev)](https://github.com/yohey-w/codd-dev)** — 成果物の検証（整合性駆動開発）。「偽の成功を防ぐ」思想。本キットの検証器は、その業務版。

3作目にあたる: オーケストレーション（誰が動くか）→ 検証（正しいか）→ **マンデート（どこまで任せるか）**。
