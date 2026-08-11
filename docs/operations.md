# Operations — your day and your week, once the loop is running

*English first, 日本語は下。*

The day-to-day after setup is done: the actual handling each morning and each week, and the file each step happens in.

## Your day

**Morning.**

1. **Open the approval queue** — the unprocessed section of `approval_queue.md`. Every card already carries what you need in order to rule *without* re-reading the deliverable — or the correspondence behind it: two or three lines of **premise** (when, to whom, what was done — you are not expected to remember the thread), the artifact itself (never a summary), whether the act can be undone, the agent's declared doubt, its one recommendation, and what it will do if you say nothing. The mark in the heading is the weight — 🔴 nothing moves until you rule, 🟡 taste, so no answer means it proceeds on the recommendation — and a batch is at most three cards. Tick approve / edit-and-approve / reject. → [`../templates/approval_queue.md`](../templates/approval_queue.md), [`decision-cards.md`](decision-cards.md)
2. **Read the one-page board** — `briefs/<date>.md`, written by the time trigger before you woke up: what happened overnight, today's deadlines and promises, what is waiting on you (each with one recommended line), work in progress, and — stated plainly — whatever that unattended run could *not* read. → [`../scripts/morning_brief.sh`](../scripts/morning_brief.sh)

**Whenever you reject — this is the entire fuel supply for the bottom half.**

3. **Write the reason on the card**, in your own words, in the reject line's reason slot. Then the settled card moves to the processed section and the reason is copied **verbatim** into the judgment journal — that verbatim quote is the only thing a principle may later be built from. → [`../templates/approval_queue.md`](../templates/approval_queue.md), [`../templates/decisions_journal.md`](../templates/decisions_journal.md)
4. **If the rejection was a mechanical hole, add one verifier** to `verifiers.md`. One line, and it applies to every future output. → [`../templates/verifiers.md`](../templates/verifiers.md)

## Once a week

5. **Rule on the promotion candidates** (about five minutes) — read `promotion_queue.md` and copy **only the ones you accept** into your own instructions file. The copying *is* the promotion — the distillation lane may write this queue and nothing else: not your instructions file, not the principles, not the source of truth. → [`../templates/promotion_queue.md`](../templates/promotion_queue.md), [`distillation-loop.md`](distillation-loop.md)
6. **Read the discipline audit** — the week's scan quotes the passages where each discipline you adopted fired or was broken, and the prompt turns them into a finding of thirty lines or less. It quotes; it does not judge. A dead-letter candidate is an invitation to look, not a proposal to delete. → [`../scripts/discipline_scan.py`](../scripts/discipline_scan.py), [`discipline-audit.md`](discipline-audit.md)

## Running multiple projects — charters, the system map, and living in the clone

Run the loop on more than one client or project and two structures earn their keep (both scaffolded by `setup.sh`):

- **One charter per project — but the personality stays singular.** Should the judgment model be split per project? No. Corrections are the loop's most valuable signal; split the model per project and that signal scatters into thin, separate streams. What differs per project is not the principles but *how they apply*. So the judgment model stays one file, and each project gets a **charter** (`projects/<name>/charter.md`, ≤60 lines) holding only the *deltas*: the counterpart's decision style, the delegation boundary for this project, pricing discipline, communication register, and which principles bite harder or take exceptions here. Never copy a principle's text into a charter — the same proposition in two places means a correction reaches only one, and the other rots. The agent reads the charter before any work on that project.
- **A one-screen system map** (`system_map.md`, at the instance root — the hottest file gets the shortest path): standing mechanisms (what runs, why, how to stop it), one card per project (status / our next move / waiting on them / deadline), and a one-line roadmap. Status lives in the map, never in charters — **charters carry judgment deltas, the map carries state.**

And you run all of it **directly inside the clone**. The allowlist `.gitignore` tracks only the kit (marked ✓ below); everything you create is untrackable by construction, and `git pull` upgrades the kit under your data. This kills the classic failure of copying a kit out into a separate dir and drifting from upstream:

```text
kagemusha/                     ← your clone = your instance
├── README.md  docs/  scripts/  templates/  tests/  manifests/     ✓ tracked (core)
├── cookbook/                    ✓ tracked (the sample shelf — never scaffolded)
│   ├── author/                  the author's burned disciplines + evidence excerpts
│   └── community/               one directory per contributor, format-lint only
├── CLAUDE.md (or AGENTS.md)      agent instructions — the instance constitution
├── system_map.md                 the one-screen board
├── approval_queue.md             the queue outward operations pile into
├── verifiers.md                  standing verifiers
├── ssot/                         current truth (overwritten in place)
├── judgment/                     append-only past (journal + judgment model)
├── projects/
│   ├── <name>/charter.md         per-project deltas (one folder per map card)
│   └── _archive/                 retired projects (mv, don't delete)
├── briefs/  logs/  local/        daily boards · run logs · machine-local scripts & secrets
```

Five invariants drive this layout: **card = folder = charter (1:1:1)** — one map card ↔ one `projects/<name>/` ↔ one `charter.md` inside it, so drift is lintable; **state vs history** — `ssot/` is overwritten truth, the journal is append-only past; **the personality is singular** — `judgment/` never splits per project; **the hottest file gets the shortest path** — the map sits at the root; **archive = one folder move** — retiring a project is `mv projects/<name> projects/_archive/`, and its charter travels with it. Rationale in [`design.md`](design.md).

## Count your work — where does your time actually go? (G/S/D/V/I/R)

The loop's promise is that your day shifts *from doing the work to improving the loop*. That's a claim about **where your time goes** — so make it measurable. Tag each slice of your own effort with one of six letters:

| Tag | Kind of work | What it means |
|---|---|---|
| **G** | Generate | You produce the first substantive draft or candidate. |
| **S** | Specify | You set the goal, the question, the constraints, the context. |
| **D** | Dispose | You accept, reject, partially select, or order a fix. |
| **V** | Verify | You test, fact-check, run an experiment, measure the result. |
| **I** | Integrate | You wire it into a system or the real workplace. |
| **R** | Relate | You persuade, negotiate, reach agreement, share accountability. |

The bet behind the approval loop is that, on repetitive work where candidates are cheap to generate and outputs are cheap to evaluate, the share of **G** falls and the share of **D + V** rises — you spend less time *making the first draft* and more time *disposing of and verifying* the agent's. This codebook lets you check that against your own logs instead of taking it on faith.

One rule keeps the count honest: **S, V, I, and R do not count as D (disposal / judgment).** Specifying, verifying, integrating, and relating are each their own work; folding them into "judgment" inflates the disposal bucket and blurs where your time really went.

---

# 運用 — 走り出したあとの毎日と毎週

導入が終わったあとの実務——毎日と毎週の捌き方と、それがどのファイルで起きるか。

## 毎日

**朝。**

1. **承認キューを開く**——`approval_queue.md` の「未処理」。各札には、成果物も——その裏のやり取りも——読み返さずに裁くために要るものが揃っている: **前提**2〜3行（いつ・誰に・何をしたか。経緯はあなたが覚えていなくてよい）・**現物**（要約で代替しない）・取り消し可能性・エージェントの**迷い**・**推奨**1つ・**無回答時**の既定動作。見出しの印が重み——🔴 は決まらないと止まるもの、🟡 は好みで、無回答なら推奨で進む——そして1バッチは**3枚まで**。承認／修正して承認／却下にチェックを入れる。→ [`../templates/approval_queue.md`](../templates/approval_queue.md)・[`decision-cards.md`](decision-cards.md)
2. **盤面1枚を読む**——`briefs/<日付>.md`。あなたが起きる前に時刻トリガーが書いている: 夜のあいだに起きたこと／今日の締切と約束／あなた待ち（1件1行の推奨つき）／進行中／**この自動実行では読めなかったもの**（読めなかったと明記させる）。→ [`../scripts/morning_brief.sh`](../scripts/morning_brief.sh)

**却下するときは毎回——下半分の燃料はこれしかない。**

3. **理由を札に書く。** 却下欄の「理由:」に自分の言葉で1行。捌いた札は「処理済み」へ移し、理由は**実発話のまま**判断台帳へ写す——後で原則に昇格してよいのは、この quote が引けるものだけだ。→ [`../templates/approval_queue.md`](../templates/approval_queue.md)・[`../templates/decisions_journal.md`](../templates/decisions_journal.md)
4. **その却下が機械的な穴なら、検証器を1本足す**（`verifiers.md`）。1行足すだけで、以後の全出力に効く。→ [`../templates/verifiers.md`](../templates/verifiers.md)

## 毎週

5. **昇格候補を審査する**（5分）——`promotion_queue.md` を読み、**採るものだけ**自分の指示ファイルへ写す。写した行為が昇格だ——蒸留便が書いてよいのはこの審査キューだけで、指示ファイル・原則・正本には書かせない。→ [`../templates/promotion_queue.md`](../templates/promotion_queue.md)・[`distillation-loop.md`](distillation-loop.md)
6. **規律監査を読む**——その週の走査が、取り入れた規律ごとに発火・破れの原文断片を引用し、週次プロンプトがそれを30行以内の所見に変える。引用して止まる——判定はしない。死文候補の名指しは削除の提案ではなく、「見に行け」の列挙だ。→ [`../scripts/discipline_scan.py`](../scripts/discipline_scan.py)・[`discipline-audit.md`](discipline-audit.md)

## 複数案件を回す — 憲章・システム地図・clone に住む

案件（顧客・プロジェクト）が2つ以上になると、2つの構造が効いてくる（どちらも `setup.sh` が展開する）:

- **憲章は案件ごと——だが人格は1本のまま。** 価値判断モデルを案件ごとに分割すべきか？ 否。訂正はループで最も価値の高い信号であり、モデルを案件ごとに割るとその信号が細い別々の流れに分散して薄れる。案件ごとに違うのは原則そのものではなく**適用のされ方**だ。だから価値判断モデルは1ファイルのまま、案件ごとに**憲章**（`projects/<案件>/charter.md`・≤60行）を置き、*差分*だけを書く: 相手の意思決定の型・この案件の委任境界・価格規律・文体レジスタ・どの原則が強く効き/例外を取るか。原則の本文を憲章にコピーしてはならない——同じ命題が2箇所にあると、訂正が片方にしか届かず、もう片方が腐る。エージェントはその案件の作業前に必ず憲章を読む。
- **1画面のシステム地図**（`system_map.md`・実走 dir の直下——最も熱いファイルは最短パスに）: 恒久機構（何が動き・なぜ・どう止めるか）、案件ごとのカード1枚（状況／次の一手＝こちら側／待ち＝相手のボール／期限）、ロードマップ1行。状況は地図に書き、憲章には書かない——**憲章＝判断の差分、地図＝状態。**

そしてこれら全部を **clone の中でそのまま回す**。allowlist 方式の `.gitignore` はキット（下図 ✓）だけを追跡するので、あなたが作るものは構造上 commit 不能であり、`git pull` はあなたのデータの下でキットだけを更新する。これが、キットを別ディレクトリへコピーして本家から乖離していく古典的な失敗（copy-drift）を殺す:

```text
kagemusha/                     ← あなたの clone ＝ あなたの実走環境
├── README.md  docs/  scripts/  templates/  tests/  manifests/     ✓ 追跡（core＝機構）
├── cookbook/                     ✓ 追跡（標本棚——setup.sh は決して展開しない）
│   ├── author/                   作者が焼いた規律集＋実走の証拠抜粋
│   └── community/                投稿者1人1ディレクトリ・形式 lint のみ
├── CLAUDE.md (または AGENTS.md)  エージェント指示——実走環境の憲法
├── system_map.md                 1画面の盤面
├── approval_queue.md             外向き操作が積まれるキュー
├── verifiers.md                  常設検証器
├── ssot/                         現在の真実（上書き更新）
├── judgment/                     追記専用の過去（台帳＋価値判断モデル）
├── projects/
│   ├── <案件>/charter.md         案件別の差分（地図のカード1枚にフォルダ1つ）
│   └── _archive/                 終わった案件（mv で休眠・削除しない）
├── briefs/  logs/  local/        朝の盤面・実行ログ・マシン固有のスクリプトと秘密情報
```

この配置を駆動する不変則は5つ: **カード＝フォルダ＝憲章（1:1:1）**——地図のカード1枚 ↔ `projects/<案件>/` 1つ ↔ その中の `charter.md` 1本。だから乖離を機械 lint できる。**状態と履歴の分離**——`ssot/` は上書きされる真実、台帳は追記専用の過去。**人格は単数**——`judgment/` は案件で割らない。**最も熱いファイルは最短パスに**——地図は直下に置く。**アーカイブはフォルダ移動1回**——案件の引退は `mv projects/<案件> projects/_archive/` で、憲章も一緒に旅をする。設計根拠は [`design.md`](design.md)。

## 仕事を数える — 時間は実際どこへ行くのか（G/S/D/V/I/R）

ループの約束は、日々が「作業」から「ループの改善」へ移ることだった。これは**時間の行き先**についての主張だ——なら測れるようにする。自分の労力の一片ずつに、6つの文字のどれかを貼る:

| 記号 | 仕事の種類 | 意味 |
|---|---|---|
| **G** | 直接生成 | 最初の実質的な下書き・候補を自分で作る。 |
| **S** | 仕様化 | 目的・問い・制約・文脈を定める。 |
| **D** | 処分 | 採用・棄却・部分選択・修正指示を下す。 |
| **V** | 検証 | テスト・事実確認・実験・結果測定をする。 |
| **I** | 統合・実行 | システムや現場に組み込む。 |
| **R** | 関係・調整 | 説得・交渉・合意・責任分担をする。 |

承認ループの賭けは、候補生成が安く出力評価も安い反復業務では、**G** の比率が下がり **D＋V** の比率が上がる、というものだ——*最初の下書きを作る*時間が減り、エージェントの出力を*処分し検証する*時間が増える。このコードブックは、それを信仰でなく自分のログで確かめるための物差しだ。

数えを正直に保つ規律が一つ: **S・V・I・R を D（処分＝判断）に含めない。** 仕様化・検証・統合・調整はそれぞれ固有の仕事だ。これらを「判断」に畳み込むと、処分の枠が実際より大きく見え、時間の本当の行き先がぼやける。
