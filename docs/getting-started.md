# Getting started — the 10-minute demo, the prerequisites, and the install

*English first, 日本語は下。*

This page is for anyone who came through the README's front door: the whole path from watching it run to putting it in your own setup.

## The 10-minute demo

One command, and the kit acts out from start to finish what it is actually for: how a piece of criticism you gave an AI — "that tone is too pushy for this client" — becomes a standing rule it follows from then on.

**What you need:** one terminal, on macOS / Linux / WSL. The only things that run inside it are `bash` and `python3`, both already on your machine. **No API key, no bill, nothing of yours touched.**

```bash
git clone https://github.com/yohey-w/kagemusha
cd kagemusha
./scripts/demo-distillation.sh
```

Then just press Enter to read your way through it (`DEMO_FAST=1 ./scripts/demo-distillation.sh` runs it with no pauses; `DEMO_KEEP=1` keeps the files the demo made so you can open them).

It plays one full turn out in front of you, on invented data. In order — and **the three screenshots below are that exact command, run for real, with nothing about the output edited**:

1. **You overrule the AI.** A few turns from a (synthetic) work session where you told the agent its draft was wrong, and why.
2. **The correction is picked up.** A free, no-model script finds those turns and files each point as one **event** — say the same thing four ways and it counts once, not four times.
3. **Nothing fires yet.** With only a handful of corrections on hand, the kit deliberately stays quiet: a model asked to draw principles out of thin material will not answer "not enough", it will produce thin principles.

   ![Demo screen: the run below the threshold prints SKIPPED and does nothing; once enough material has landed the next run prints FIRED and distils](../images/demo/01-threshold.png)

   *While the material is thin it stays silent (SKIPPED); only on the day enough has landed does it fire (FIRED). Nothing has cost anything yet.*

4. **More lands, and it drafts a rule.** Past the threshold it proposes one rule line, with the eight things you need in order to rule on it — the exact words it came from, where it applies and where it does not, anything in the material pointing the other way, where the rule should be filed, and when to re-check it.
5. **You decide, and only you.** The proposal goes into a queue for you to read. The machine writes the diff against your instructions file and stops there: you see it, and it is **not applied**.

   ![Demo screen: the review queue shows two candidates with all eight fields filled in, and then asks whether to promote or skip](../images/demo/02-review-card.png)

   *A proposed rule never arrives as a bare line — evidence, scope, exception, counter-evidence, where to file it and when to re-check it all come with it, and then you are asked one thing: promote, or skip.*

6. **A later check asks whether the rule did anything.** The audit walks a subsequent session and quotes the passages where the accepted rule fired — plus the one from before it existed, where it was broken.

   ![Demo screen: the diff against CLAUDE.md.proposed, followed by the audit quoting a FIRE line and a BREACH line](../images/demo/03-diff-and-audit.png)

   *The machine writes the diff and stops — it never applies it. The later audit puts the line where the rule fired (FIRE) next to the one from before it existed, where it was broken (BREACH).*

Everything lives in a `mktemp` sandbox that is deleted on the way out: **no model is called, none of your logs are read, and not one byte is written outside it** — pinned by test group J, which asserts the checkout is byte-identical before and after. The session logs are obviously-synthetic and the distilling model is a stub wired in at `AGENT_CMD`; every other moving part is the shipped script you will be cronning below.

**Two ways on from here.** Want it running in your own setup now → **[What you actually need](#what-you-actually-need)**. Want the mechanism first → **[how the whole thing works](../README.md)**.

## What you actually need

The mechanism is **files and discipline** — a harness-agnostic core. The prerequisites are additive: the minimal setup needs exactly one thing — a folder plus an assistant that can touch it. Each level of automation and each listening channel adds exactly one more:

| What you want to run | Prerequisites (additive) |
|---|---|
| Minimal: approval queue + SSOT + journal, run by hand | A folder of Markdown files + one AI assistant **that can read/write files in that folder** (Claude Code CLI or desktop, Codex CLI, Cursor, …). ⚠️ A plain chat window with no file access does **not** qualify — this is the most-missed hidden prerequisite. |
| Morning board / weekly distill, semi-automatic | + any nudge (a calendar reminder is enough) |
| Same, fully automatic | + a headlessly-launchable CLI + a scheduler (cron on Linux/macOS, Task Scheduler on Windows; macOS can also use the native launchd) — for one reason only: a scheduler cannot click a GUI |
| Inbound catch, Tier 1 (recommended) | + MCP connectors for your channels (Gmail / Slack / Notion) connected in your client — OAuth handled by the platform. Availability varies by plan and client. |
| Inbound catch, fully automatic (the Tier 2 script) | + channel credentials (Slack bot token / Gmail app password) — because an interactively-authenticated MCP session may be unavailable under an unattended scheduler |
| Approving from your phone | + a push channel ([ntfy](https://ntfy.sh/) or similar, free) |

**Three ways to kick off the weekly run** — all three are fine: **fully automatic** (the scheduler launches an AI *CLI* — the only mode that needs a CLI), **semi-automatic** (the scheduler just *notifies* you; you paste the weekly prompt into a desktop or web chat), or **manual** (on a fixed weekday, you simply ask your AI yourself — make it a small ritual).

In this mechanism a human has to approve principle revisions anyway (the weekly distiller *proposes*; new principles wait for your OK). So a human doing the kick-off is **not a failure of automation** — the approval and the kick-off just collapse into the same single tap.

(Those three are about *who* kicks off the same OS-scheduled run — a separate question from *which* loop mechanism to use at all. An OS scheduler, an agent's own built-in loop (e.g. Claude Code's `/loop`), and a schedule run by the coding agent's own service or app are not interchangeable — they differ in who holds the clock and whether the job can reach your local files. Comparison: [`inbound-loop.md`](inbound-loop.md).)

That's it. The `scripts/` in this repo are a **convenience layer** (headless automation, log mining, budget lints), not a prerequisite. Delete them and the loop still runs: the core is the Markdown files plus the discipline of *inward = auto / outward = approval queue*. A CLI + a scheduler is just the example wiring — a desktop app + a weekly calendar nudge is equally valid.

## The steps (copy-paste)

**Prerequisites** (for this scripted path only — the loop itself needs just the three things above)**:** `bash`; one AI CLI that runs a prompt non-interactively (default is the [Claude CLI](https://code.claude.com/), swappable to Codex/Gemini/etc.); optionally [ntfy.sh](https://ntfy.sh/) for phone notifications; Python 3 (only for the distillation scripts). Prefer not to script it? Skip to the semi-automatic / manual kick-off above and just paste the prompts into any assistant.

**Installing an AI CLI (if you don't have one).** Any agentic CLI works; the two most common:

- **Claude Code** (Anthropic): native installer is the recommended path — `curl -fsSL https://claude.ai/install.sh | bash` (macOS/Linux/WSL; Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`), then run `claude` once to sign in ([docs](https://code.claude.com/docs/en/setup); npm install also works). Its per-directory instructions file is `CLAUDE.md` — which `setup.sh` creates for you.
- **Codex CLI** (OpenAI, GPT models): `npm install -g @openai/codex`, then run `codex` once to sign in with your ChatGPT account ([repo](https://github.com/openai/codex)). Its instructions file is `AGENTS.md` — rename the generated `CLAUDE.md` to `AGENTS.md` and you're done.

The instructions themselves (`templates/agent_instructions.md`) are tool-agnostic; `setup.sh` just saves them under the filename your tool reads.

```bash
# 1. Scaffold (5 min) — clone, then scaffold INTO the clone and live in it.
#    The allowlist .gitignore means your SSOT / journal / config can never be
#    committed, and `git pull` updates the kit without touching your data.
#    Never clobbers existing files. (Prefer a separate dir? ./scripts/setup.sh ~/work-loop)
git clone https://github.com/yohey-w/kagemusha.git
cd kagemusha
./scripts/setup.sh

# 2. Fill the source of truth (15 min) — the one part a machine can't do.
#    Edit ssot/{decisions,tasks,glossary,people}.md — a few real entries each.
#    (tasks.md: always include a "source" column so nothing is "he-said / she-said".)

# 3. Wire the time trigger (5 min).
cp config.env.example config.env      # git-ignored; holds your paths + notify topic
$EDITOR config.env                    # set PROJECT_ROOT / AGENT_CMD / NTFY_TOPIC
./scripts/morning_brief.sh            # run once by hand (read-only, ~a few minutes)

# 4. Put it on cron (or Windows Task Scheduler → docs/windows.md, or a daily
#    calendar reminder to run it by hand — any OS scheduler is equivalent;
#    other loop mechanisms are not, see docs/inbound-loop.md).
#    53 6 * * *  /path/to/kagemusha/scripts/morning_brief.sh
```

**Then, once the loop is running, turn on the feedback side (optional):**

```bash
# 5. Seed a few of your own principles in judgment/judgment_model.md
# 6. Copy the weekly distiller and edit its CONFIG block:
cp scripts/weekly_distill.sh.example scripts/weekly_distill.sh && $EDITOR scripts/weekly_distill.sh
# 7. Cron it weekly (proposes changes; new principles wait for your OK):
#    17 21 * * 0  /path/to/kagemusha/scripts/weekly_distill.sh
```

See [`judgment-distillation.md`](judgment-distillation.md) for how it works.

**Or start with the light lane: harvest daily, distill only when there is material.**

```bash
# 5'. Cut templates/correction_patterns.example.txt down to phrases YOU use, then:
#     7  6 * * *  scripts/correction_scan.py --patterns … --material … --state … --since 1d --dir …
#                 (--dir is NOT optional under cron: without it the log path is guessed
#                  from the working directory, which cron sets to $HOME. setup.sh prints yours.)
#    23 6 * * *  scripts/distill.sh     # fires only past the threshold; silent otherwise
```

`correction_scan.py` costs nothing (no LLM) and groups the day's corrections into **events** — four rephrasings of one point are one event, never four witnesses. `distill.sh` runs daily and almost always does nothing: a model asked to distill principles from two thin corrections will not say "not enough", it will produce two thin principles, so the threshold is what keeps the output honest. What it produces is a **promotion queue** for you to read — never an edit to your rules file. [`distillation-loop.md`](distillation-loop.md).

## Optional: a verifier from a different model lineage

This kit is built around the assumption that AI output can be wrong — that's the whole reason the approval queue and the verifiers exist. But there's a blind spot: if the model that checks the work shares a lineage with the model that did the work, a failure mode common to that lineage slips past both. (Research on inference-time scaling reports a pattern — getting pulled off track by irrelevant context the longer a model reasons — that shows up across a model *family*, not just one model: [Inverse Scaling in Test-Time Compute](https://arxiv.org/abs/2507.14417).) So it's worth wiring in one checker from a different vendor.

- **What:** the [Codex plugin for Claude Code](https://github.com/openai/codex-plugin-cc) — an official plugin that calls OpenAI's Codex CLI from inside Claude Code — plus the Codex CLI itself and an OpenAI-side login. Its usage quota is billed separately from Claude usage, so reaching for it doesn't eat into your main work's budget.
- **When to reach for it:** (1) a second diagnosis when you're stuck, (2) designing a fix for your *own* blind spot — don't ask the side that has the blind spot to design around it, (3) an independent check before a big publish or delivery. Having it review this kit's own verifiers, or a distilled change to the judgment model, is the typical case.
- **How to install** (verified against the plugin's own README):

  ```bash
  # inside Claude Code
  /plugin marketplace add openai/codex-plugin-cc
  /plugin install codex@openai-codex
  /reload-plugins
  /codex:setup   # checks whether Codex is ready; can install/log you in if not
  ```

  Requires a ChatGPT subscription (Free tier included) or an OpenAI API key, and Node.js 18.18+. Full requirements and usage: the plugin's own [README](https://github.com/openai/codex-plugin-cc).

## Does it fit you?

**It fits you if:**

- **Operations that can't be undone** — sending, publishing, delivering, mutating a source of truth — are part of your day; you want to hand that work to an AI and you cannot afford the accident.
- You keep giving the AI **the same note over and over**, and you know the reason is thrown away each time.
- Most of what you'd hand over **isn't code**: mail, drafts, research, prep for recurring meetings.
- You want to **design and evolve your own criteria** rather than borrow someone else's frozen ones.

**It does not fit you if:**

- All you have is **a chat window with no file access** — not even the minimal setup works (full prerequisite table: [What you actually need](#what-you-actually-need)).
- You want a shared approval **UI or SaaS** for a team: the queue here is one Markdown file and there is no dashboard ([humanlayer](https://github.com/humanlayer/humanlayer) is the closer fit).
- You are not willing to **write down why you rejected something** — that is the only fuel the feedback arm has, and without it the bottom half never turns.
- You need a guarantee about **how much** it helps: what's on offer is n=1, one instance (scope and limits: [`../cookbook/author/evidence/README.md`](../cookbook/author/evidence/README.md)).

---

# はじめに — 10分デモ・前提・導入

このページは README の玄関から来た人のための、試す→入れるの全手順です。

## 10分デモ

コマンド1本で、この道具が何をするものか——あなたがAIに出したダメ出し（「この相手にこのトーンは押しつけがましい」）が、どうやってAIが以後ずっと守る恒久ルールに変わるのか——を、作り物のデータで最後まで実演する。

**要るもの**: macOS / Linux / WSL のターミナルが1つ。中で動くのは `bash` と `python3` だけで、どちらも最初から入っている。**APIキーは要らない。課金もない。あなたのファイルには触れない。**

```bash
git clone https://github.com/yohey-w/kagemusha
cd kagemusha
./scripts/demo-distillation.sh
```

あとは Enter を押して読み進めるだけだ（`DEMO_FAST=1 ./scripts/demo-distillation.sh` なら止まらずに走り、`DEMO_KEEP=1` を付けるとデモが作ったファイルが残って中を覗ける）。

作り物のデータで、一周がそのまま目の前で回る。順番はこうだ——**下の3枚は、いま書いたこの手順をそのまま実走して撮った画面で、出力には一切手を入れていない**。

1. **あなたがAIにダメ出しをする。** 「その下書きは違う、理由はこうだ」と言った場面を、架空の作業ログから拾う。
2. **そのダメ出しが拾い上げられる。** モデルを呼ばない（＝無料の）スクリプトがログからそれを見つけ、**1つの論点＝1件**として記録する——同じことを4回言い直しても、証人が4人になったりはしない。
3. **まだ何も起きない。** ダメ出しが数件しか無いうちは、この道具はわざと黙る。材料の薄いままモデルに原則を書かせると、「材料が足りません」とは言わずに、薄い原則をひねり出すからだ。

   ![デモ画面: しきい値に届かない回は distill が SKIPPED と表示して何もせず、材料が溜まった回に FIRED と表示して蒸留が走る](../images/demo/01-threshold.png)

   *材料が薄いうちは黙る（SKIPPED）。溜まった日に初めて火が入る（FIRED）。ここまで一円もかかっていない。*

4. **溜まると、ルール案が出てくる。** しきい値を超えると、ルール案が1行と、それを判定するために要る8項目——元になった発言そのもの・どこで効いてどこでは効かないか・逆を示す材料はあるか・どのファイルに貼るのか・いつ見直すか——が出てくる。
5. **決めるのはあなただけ。** 案はあなたが読むキューに積まれる。機械は指示ファイルへの差分を書くところまでで止まる——差分は見えるが、**適用はされない**。

   ![デモ画面: 審査キューに8欄そろった候補が2本並び、最後に昇格させるか見送るかを聞かれている](../images/demo/02-review-card.png)

   *ルール案は1行では出てこない——証拠・範囲・例外・反証・貼り先・期限まで揃って出て、最後に「昇格させるか、見送るか」だけを聞かれる。*

6. **後日、そのルールが効いたかを見に行く。** 監査が後のセッションを走査し、採用したルールが実際に効いている箇所を引用する——ルールが無かった頃の、破れている箇所も一緒に。

   ![デモ画面: CLAUDE.md.proposed への差分が表示され、続く監査が FIRE と BREACH の行を引用している](../images/demo/03-diff-and-audit.png)

   *機械が書くのは差分まで——適用はしない。後日の監査が、規律が効いた行（FIRE）と、規律が無かった頃の破れ（BREACH）を並べて引いてくる。*

全部 `mktemp` のサンドボックスの中で起き、終了時に消える——**モデルは呼ばず・あなたのログは読まず・その外へは1バイトも書かない**（テスト群Jが「チェックアウトはbefore/afterでバイト同一」を実測して固定している）。偽物はセッションログ（明らかに架空の合成）と蒸留モデル（`AGENT_CMD` に挿すスタブ）の2つだけで、残りは下でcronに載せる出荷スクリプトそのものだ。

**ここから先は2つに分かれる。** 今すぐ自分の環境で動かしたい人は **[必要なもの](#必要なもの)** へ。仕組みを先に知りたい人は **[README の「仕組みの全景」](../README_ja.md)** へ。

## 必要なもの

この機構の本体は**ファイルと規律**——ツール非依存（harness-agnostic）だ。前提条件は積み木式で、最小構成に要るのは実質1つ——フォルダと、それに触れるアシスタント。自動化を1段上げるごと・聴くチャンネルを1本足すごとに、前提が1つずつ増えるだけだ:

| 何を動かしたいか | 前提条件（積み木式・上に足すだけ） |
|---|---|
| 最小構成: 承認キュー＋SSOT＋台帳を手動で回す | Markdown のフォルダ ＋ **そのフォルダのファイルを読み書きできる** AI アシスタント1つ（Claude Code の CLI/デスクトップ・Codex CLI・Cursor 等）。⚠️ ファイルに触れないただのチャット画面は**不可**——ここが一番見落とされる隠れ前提。 |
| 朝の盤面・週次蒸留を半自動で | ＋ 何かしらの合図（カレンダーのリマインダーで十分） |
| 同じものを全自動で | ＋ ヘッドレス起動できる CLI ＋ スケジューラ（Linux/macOS なら cron、Windows ならタスクスケジューラ。macOS 純正の launchd でも可）——理由はただ1つ、スケジューラは GUI をクリックできないから |
| 受信箱キャッチ Tier 1（推奨） | ＋ 使うチャンネル（Gmail / Slack / Notion）の MCP コネクタをクライアントに接続——OAuth はプラットフォーム持ち。利用可否はプランとクライアントによる。 |
| 受信箱キャッチを全自動で（Tier 2 スクリプト） | ＋ チャンネルの認証情報（Slack Bot トークン / Gmail アプリパスワード）——無人スケジューラ実行では対話認証済み MCP セッションが使えないことがあるため |
| スマホから承認 | ＋ push 通知チャンネル（[ntfy](https://ntfy.sh/) 等・無料） |

**週次の着火（kick-off）の3段階**——どれでもよい: **全自動**（スケジューラが AI の *CLI* を定時起動——CLI が要るのはこのモードだけ）、**半自動**（スケジューラは*通知だけ*。人間がデスクトップ／Web のチャットに週次プロンプトを貼る）、**手動**（決まった曜日に、自分で AI に頼む——小さな儀式にしてしまえばいい）。

この機構では、原則の改訂にどのみち人間の承認が要る（週次蒸留は*提案*止まりで、新規原則はあなたの OK を待つ）。だから着火を人間がやることは**自動化の失敗ではない**——承認と着火が同じワンタップに畳まれるだけだ。

（この3段階は「同じOSスケジューラ駆動の実行を誰が着火するか」の話で、「そもそもループをどこで回すか」とは別の問いだ。OSのスケジューラ・動いているセッション自身に繰り返させる方法（例: Claude Code の `/loop`）・AIコーディングエージェントのサービス側やアプリ側に時計を持たせる方法は、互換ではない——誰が時計を持ち、どこで走るかが違い、それが手元のファイルに届くかどうかを決める。比較: [`inbound-loop.md`](inbound-loop.md)。）

これだけだ。このリポジトリの `scripts/` は**おまけの効率化**（ヘッドレス自動化・ログ採掘・予算 lint）であって、前提ではない。消してもループは回る——本体は Markdown ファイルと「**内向き＝自動 / 外向き＝承認キュー**」という規律だ。CLI ＋ スケジューラはあくまで一例の配線で、デスクトップ版アプリ ＋ 週次のカレンダー通知でも等価に成立する。

## 手順（コピペ）

**前提**（この「スクリプトで回す」経路だけの前提——ループ本体は上記3つで足りる）**:** `bash`／プロンプトを非対話で走らせる AI CLI 1本（既定は [Claude CLI](https://code.claude.com/)・Codex/Gemini 等に差し替え可）／通知に [ntfy.sh](https://ntfy.sh/)（任意）／Python 3（蒸留スクリプト用のみ）。スクリプトを組みたくなければ、上の半自動／手動の着火に飛んで、プロンプトを任意のアシスタントに貼るだけでよい。

**AI CLI の導入（まだ持っていなければ）。** エージェント型の CLI なら何でもよい。代表的な2つ:

- **Claude Code**（Anthropic）: 公式推奨はネイティブインストーラ——`curl -fsSL https://claude.ai/install.sh | bash`（macOS/Linux/WSL。Windows PowerShellは `irm https://claude.ai/install.ps1 | iex`）のあと `claude` を一度起動してサインイン（[公式ドキュメント](https://code.claude.com/docs/en/setup)。npm経由も可）。ディレクトリごとの指示ファイルは `CLAUDE.md`——`setup.sh` が作ってくれる。
- **Codex CLI**（OpenAI・GPT系モデル）: `npm install -g @openai/codex` のあと `codex` を一度起動して ChatGPT アカウントでサインイン（[公式リポジトリ](https://github.com/openai/codex)）。指示ファイルは `AGENTS.md`——生成された `CLAUDE.md` を `AGENTS.md` にリネームすれば完了。

指示の中身（`templates/agent_instructions.md`）はツール非依存で、`setup.sh` は使うツールが読むファイル名で保存するだけだ。

```bash
# 1. 展開する（5分）——clone して、その clone の中に展開してそのまま住む。
#    allowlist 方式の .gitignore により SSOT・台帳・config は commit 不能で、
#    `git pull` はあなたのデータに触れずキットだけ更新する。既存ファイルは上書きしない。
#    （別ディレクトリ派は ./scripts/setup.sh ~/work-loop でも可）
git clone https://github.com/yohey-w/kagemusha.git
cd kagemusha
./scripts/setup.sh

# 2. 正本を埋める（15分）——ここだけは機械にできない。
#    ssot/{decisions,tasks,glossary,people}.md を数件ずつ埋める。
#    （tasks.md は「出典」列を必ず1列——後の「言った/言ってない」を防ぐ。）

# 3. 時刻トリガーを設定（5分）。
cp config.env.example config.env      # git管理外。パスと通知先を持つ
$EDITOR config.env                    # PROJECT_ROOT / AGENT_CMD / NTFY_TOPIC を自分用に
./scripts/morning_brief.sh            # 手で1回試す（読み取り専用・数分）

# 4. cron に載せる（Windows はタスクスケジューラ→docs/windows.md／
#    手動なら毎朝のカレンダー通知でも可——OSのスケジューラはどれも等価。
#    他の実行基盤（エージェント内蔵ループ等）とは別物→docs/inbound-loop.md）。
#    53 6 * * *  /path/to/kagemusha/scripts/morning_brief.sh
```

**ループが回り始めたら、フィードバック側を有効化（任意）:**

```bash
# 5. judgment/judgment_model.md に自分の原則を数件、種として書く
# 6. 週次蒸留をコピーして CONFIG ブロックを編集:
cp scripts/weekly_distill.sh.example scripts/weekly_distill.sh && $EDITOR scripts/weekly_distill.sh
# 7. 週次で cron（改訂は提案止まり・新規原則はあなたの承認待ち）:
#    17 21 * * 0  /path/to/kagemusha/scripts/weekly_distill.sh
```

仕組みは [`judgment-distillation.md`](judgment-distillation.md) を参照。

**あるいは軽いレーンから: 採取は毎日・蒸留は材料が貯まった日だけ。**

```bash
# 5'. templates/correction_patterns.example.txt を「自分の言い回し」だけに削ってから:
#     7  6 * * *  scripts/correction_scan.py --patterns … --material … --state … --since 1d --dir …
#                 （cron では --dir を省略できない。省略するとログの場所をカレントディレクトリから
#                  推測するが、cron のそれは $HOME だ。自分用の --dir は setup.sh が出力する）
#    23 6 * * *  scripts/distill.sh     # 閾値未満は黙ってスキップ（無料）
```

`correction_scan.py` はLLMを使わず（＝ただ）、その日の訂正を**イベント**に束ねる——4回言い直したことは4人の証人ではない。`distill.sh` は毎日走るがほぼ何もしない: **薄い2件を渡されたモデルは「材料が足りません」とは言わず、薄い2件ぶんの原則をひねり出す**からだ。閾値は出力を正直に保つ仕掛けであって、節約ではない。出てくるのは**あなたが読む審査キュー**で、規則ファイルへの書き込みではない。→ [`distillation-loop.md`](distillation-loop.md)

## 任意: 血統の違うモデルによる検算器

このキットは「AIの出力は間違いうる」ことを前提に組んである——承認キューも検証器も、そのために存在する。だが1つ死角がある: 検証する側と作業する側が同じ血統のモデルだと、**その血統に共通する失敗モードは両方をすり抜ける**。（推論を長くするほど無関係な文脈に引きずられる、という失敗パターンが個々のモデルでなくモデル*系列*全体に現れるとする研究がある: [Inverse Scaling in Test-Time Compute](https://arxiv.org/abs/2507.14417)。）だから、別ベンダーの検算役を1本つないでおく価値がある。

- **何を**: [Claude Code 用 Codex プラグイン](https://github.com/openai/codex-plugin-cc)——OpenAI の Codex CLI を Claude Code の中から呼び出す公式プラグイン——と Codex CLI 本体、OpenAI 側のログイン。利用枠は Claude の利用枠と別会計なので、検算に回しても本業の枠を食わない。
- **どう使うか**: ①詰まったときのもう1つの診断 ②**自分の弱点への対策の設計**（弱点を持つ側に、その弱点を埋める設計を発注しない）③大きな公開・納品の前の独立検品。このキット自身の検証器や、蒸留した価値判断モデルの改訂案を、別血統に検品させるのが典型。
- **導入手順**（プラグイン本体の README で裏取り済み）:

  ```bash
  # Claude Code 内で
  /plugin marketplace add openai/codex-plugin-cc
  /plugin install codex@openai-codex
  /reload-plugins
  /codex:setup   # Codexの準備状況を確認し、未導入ならインストール/ログインを提案してくれる
  ```

  ChatGPT サブスクリプション（Free でも可）または OpenAI API キー、Node.js 18.18 以降が必要。詳細な要件と使い方はプラグイン本体の [README](https://github.com/openai/codex-plugin-cc) を参照。

## 適合条件

**向いている**

- **取り消せない操作**（送信・公開・納品・正本の書き換え）が日常にあり、AI に任せたいが事故は許容できない
- AI に**同じダメ出しを何度も**している。その理由が毎回捨てられている自覚がある
- 渡したい仕事の多くが**コードではない**——メール・下書き・調査・定例の準備
- 判断基準を**自分で設計して育てたい**（他人が凍結した基準を借りるのではなく）

**向いていない**

- 使えるのが**ファイルに触れないチャット画面だけ**——最小構成すら成立しない（前提の全表は[必要なもの](#必要なもの)）
- チームで共有する承認**画面・SaaS** が欲しい——ここでの承認キューは Markdown ファイル1枚で、ダッシュボードは無い（近いのは [humanlayer](https://github.com/humanlayer/humanlayer)）
- 却下の**理由を書き残す気がない**——フィードバック側の燃料はそれしかないので、下半分が回らない
- 効き目の**大きさ**の保証が要る——出せるのは n=1・1インスタンスの証拠だけだ（射程と限界: [`../cookbook/author/evidence/README.md`](../cookbook/author/evidence/README.md)）
