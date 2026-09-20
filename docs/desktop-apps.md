# Desktop apps — Claude Desktop and the ChatGPT app's Codex

*English first, 日本語は下.*

Both vendors now ship a desktop app that runs the same agent as the CLI. On Windows both can put the
agent inside WSL, and that is the only configuration this page describes. The reason to care is not
comfort: the ChatGPT app syncs its sessions to a phone, so it is a remote control the Codex CLI does
not have.

**The one-sentence difference.** Claude Desktop in WSL mode *is* the CLI — same `~/.claude`, same
skills, same hooks, nothing to install. The ChatGPT app's Codex runs its shell in WSL but keeps its
**head on the Windows side**, so every resource that hangs off `CODEX_HOME` has to be put there too,
and two of them cannot be made to work at all.

Everything below was measured on 2026-09-13 and 2026-09-14 against Claude Desktop and ChatGPT desktop
`0.154.0-alpha.6.2` (`originator: codex_work_desktop`). Anything not measured is marked 〔unverified〕.
Machine-specific paths are written `<user>` and `<project>`.

## The four faces

| | Claude Code (CLI) | Claude Desktop (Code tab, WSL) | Codex CLI | Codex Desktop (ChatGPT app, WSL mode) |
|---|---|---|---|---|
| where the head lives | `~/.claude` | **same `~/.claude`** — HOME is `/home/<user>` | `~/.codex` | **`C:\Users\<user>\.codex`**, even in WSL mode (injected by the app through `WSLENV`) |
| hooks | `.claude/settings.json` | same file. `PreToolUse` measured firing; the `UserPromptSubmit` stamp is 〔unverified〕 — it was never tested separately | `.codex/config.toml`, project must be trusted | fires **only if** the Windows-side `config.toml` carries a **Linux-spelled** `[hooks.state]` key. `PreToolUse` works; `UserPromptSubmit` is silently skipped |
| skills | `~/.claude/skills/` | same directory | `~/.codex/skills/` | `C:\Users\<user>\.codex\skills\` — the WSL copy is invisible, so it has to be copied over |
| memory | auto-memory directory | same | memories | Windows-side; **not canon either way** — canon is the repository's plain files |
| history (for distillation) | `~/.claude/projects/*.jsonl` | same files | `~/.codex/sessions/**` | `C:\Users\<user>\.codex\sessions\**` — add it to `CODEX_SESSIONS_DIR` |
| driving the app itself | n/a | **not possible** — the app refuses remote-debugging arguments, so acceptance tests are done by hand | n/a | CDP on port `9333`. `Browser.close` closes the page but leaves the app running |

## Claude Desktop: one setting

1. Open the **Code** tab and open your project.
2. Set the environment to **WSL**.

That is the whole procedure. Measured: `HOME` is `/home/<user>`, and the app reads the same
`~/.claude` the CLI reads — skills, the hooks in `settings.json`, and the auto-memory directory for
the project. Nothing is copied, nothing is synced, and an edit made from the CLI is live in the app.

**Local (Windows-side) mode is not adopted here.** In Local mode the settings, the memory and the
skills all live under the Windows profile, so none of the loop's resources are present — a different
head wearing the same face. If you use it anyway, treat it as an unrelated install.

## Codex Desktop: keep the head on Windows, then carry three things to it

**Prerequisite.** In the app's settings, set the agent environment to **WSL**
(*Windows Subsystem for Linux*). The change needs a restart before it applies; the app says so.

**Do not move `CODEX_HOME` to the WSL side.** It looks like the obvious fix and it does not work: the
app then shows *"complete the Windows setup"* and refuses every turn. The Linux build of the
app-server has no implementation of the Windows sandbox setup — its binary contains
`elevated Windows sandbox setup is only supported on Windows` and does not contain the name of the
setup executable at all — so nothing you place under the WSL-side `CODEX_HOME` can satisfy the check.
Symlinking the sandbox directories, repointing `plugins`, and copying the four sandbox files were all
measured and all failed. Leave `CODEX_HOME` at `C:\Users\<user>\.codex`.

### 1. Hooks — add Linux-spelled keys to the Windows-side config

The app registers a trusted hook under the path *it* used when you clicked "trust" — the UNC spelling,
`\\wsl.localhost\Ubuntu\home\<user>\<project>\.codex\config.toml:…`. But in WSL mode the app-server
looks the hook up under the path the *shell* sees, `/home/<user>/<project>/.codex/config.toml:…`,
finds nothing, and **skips the hook in silence**. The trust is real; the key is spelled for the wrong
side.

Copy the hashes out of the WSL-side `~/.codex/config.toml` (the same file the CLI trusted) and add the
Linux-spelled keys to `C:\Users\<user>\.codex\config.toml`, keeping a `.bak` first:

```toml
[hooks.state."/home/<user>/<project>/.codex/config.toml:pre_tool_use:0:0"]
trusted_hash = "sha256:<copy the value from the WSL-side ~/.codex/config.toml>"

[hooks.state."/home/<user>/<project>/.codex/config.toml:user_prompt_submit:0:0"]
trusted_hash = "sha256:<copy the value from the WSL-side ~/.codex/config.toml>"
```

Restart the app. Reversible by deleting the four lines.

Two things worth knowing about this trust: the hash covers the hook **definition**, not the script
body, so editing `outbound_guard.sh` never asks for trust again — and adding these keys buys you
`PreToolUse` only. See the limits below.

### 2. Skills — copy them to the Windows side

`CODEX_HOME/skills` is the only directory the app reads. A symlink does not help (the Windows side
cannot resolve it), so copy:

```sh
rsync -a --copy-links \
  --exclude .venv --exclude node_modules --exclude .git --exclude __pycache__ \
  ~/.codex/skills/ /mnt/c/Users/<user>/.codex/skills/
```

The excludes are not optional: measured on one install, 339 files and 3.1 MB with them, 8,004 files
and 309 MB without. Skills whose scripts are bash keep working, because in WSL mode the shell is WSL.

#### Optional: install the ChatGPT Web consultation skill

`codex-chatgpt-consult` lets Codex Desktop consult the ChatGPT Web model and mode you name through
the standard in-app Browser. It is intentionally not installed into Claude. From the repository root:

```sh
./scripts/setup.sh --link-skills
rsync -a --copy-links templates/skills/codex-chatgpt-consult/ \
  /mnt/c/Users/<user>/.codex/skills/codex-chatgpt-consult/
```

Start a new Codex task after copying. Prerequisites are: the bundled Browser skill is listed in that
task, the in-app Browser is available, and you can sign in to ChatGPT Web yourself. If any is absent,
the skill stops instead of substituting an external browser, API, CDP client, or custom automation.

Invoke it with an exact target, for example: *Use `$codex-chatgpt-consult` to ask ChatGPT Web's
`<visible model label>` in `<visible mode label>` this question once, save the complete final answer
verbatim, and audit it.* The skill verifies those labels in the visible UI; it never assumes a generic
label such as `Latest` means `Pro`.

Expect a handoff for sign-in, MFA, recovery, CAPTCHA, or account changes. It also stops when the model
or mode is ambiguous, local outbound rules do not permit the send, a paste card cannot be reconciled
with the saved packet, send status is uncertain, a duplicate may exist, the final answer may be
incomplete, or the saved answer fails its hash/equality check. It never weakens security controls and
does not promise that the workflow complies with every service term or prevents account restrictions.

#### Optional: install the Pro plan-and-build workflow

`codex-pro-plan-build` is a Codex Desktop-only procedure for using an authorized ChatGPT Web Pro
consultation on high-rework design decisions, auditing the result into a design contract, and then
implementing and testing locally. It requires `codex-chatgpt-consult`; it does not duplicate or bypass
that skill's Browser, authentication, single-send, capture, or verification controls. A local-only run
does not require the consultation skill, Browser, login, or Web UI checks.

From the repository root, link both skills into the WSL-side Codex install and copy both to the
Windows-side `CODEX_HOME` used by Codex Desktop:

```sh
./scripts/setup.sh --link-skills
rsync -a --copy-links templates/skills/codex-chatgpt-consult/ \
  /mnt/c/Users/<user>/.codex/skills/codex-chatgpt-consult/
rsync -a --copy-links templates/skills/codex-pro-plan-build/ \
  /mnt/c/Users/<user>/.codex/skills/codex-pro-plan-build/
```

Start a new Codex task and confirm that both skills and the bundled in-app Browser skill are listed.
Invoke it, for example: *Use `$codex-pro-plan-build`; consult only for high-rework decisions, produce
an audited design contract, then implement and run the full required tests.* For a consultation, it
asks only when the allowed outbound evidence, Web model/mode, or message budget is unresolved. A new
chat and private non-overwriting artifact paths follow the consultation skill's defaults unless you
say otherwise.

The recommended profile is visibly selected Web `Astra Pro` and local `gpt-6-astra` at `high`; it is
not an automatic setting or guarantee, and another user selection wins. The workflow must verify
actual Web model/mode and local model/effort metadata. If it cannot verify or switch, conflicts with
local model-allocation rules, or lacks authorization for the initial or a later send, it stops for the
user. Small changes and already-approved designs can skip consultation without asking Web-send
questions; their report says `not consulted`. It never creates a task automatically, treats the Pro
reply as proof, replaces CI, or promises free quota or strongest-model status. After an authorized
reconsultation it preserves the new raw answer and old contract, versions the contract, updates the
affected acceptance tests, and only then resumes implementation. A reconsultation already inside the
approved scope and remaining message budget needs no extra approval, but the changed evidence is
recorded and reported. If local model/effort proof is found missing later, existing code and evidence
are preserved, the condition is reported as unverified, and the user chooses whether to relax it or
request bounded review or tests from a verified executor; a full rewrite is not automatic.

### 3. History — add the Windows tree to the harvest

Desktop sessions are written to `C:\Users\<user>\.codex\sessions\**`, so the distillation lane never
sees them unless you say so. `scripts/lib/log_sources.py` reads `CODEX_SESSIONS_DIR`
(colon-separated, falling back to `~/.codex/sessions`):

```sh
export CODEX_SESSIONS_DIR="$HOME/.codex/sessions:/mnt/c/Users/<user>/.codex/sessions"
```

Measured over one desktop day: the adapter reads that tree, and the desktop's turns arrive as ordinary
user turns — the originator is `Codex Desktop` / `codex_work_desktop`, neither of which the
sidechain rule drops.

### Known limits, measured

- **The per-turn date stamp does not arrive.** `UserPromptSubmit` is skipped even with its
  Linux-spelled key present, with no error anywhere — a **fail-open** silence. So on Codex Desktop the
  agent has no injected date and will answer from a clock tool or from nothing. Either state the date
  in the prompt, or do not use this face for work that turns on a date or a weekday. Why the event is
  skipped is 〔unverified〕: what was measured is that no trace of it exists in the logs.
- **The outward guard denies, but nothing is queued.** `PreToolUse` returns `deny` and the send does
  not happen — that is the half that matters. The deny text asks the agent to append the request to
  `approval_queue.md`, and measured, it did not. Treat a desktop deny as "stopped", not as "queued for
  you", and check the queue yourself.
- **The app cannot be closed over CDP.** `Browser.close` leaves the process alive; stopping it needs
  `Stop-Process` on the Windows side.
- **Two spellings of the same connector are in circulation.** The JavaScript wrapper inside `exec`
  names it with one underscore (`mcp__codex_apps__gmail_create_draft`) while the `PreToolUse`
  envelope for the same call carries two (`mcp__codex_apps__gmail__create_draft`). The verb rule
  matches both. See [`outbound-permits.md`](outbound-permits.md) for what this means for a permit.

## How to check a face, in four questions

Send these to the app and compare against the machine, rather than believing the answer:

1. **The brake.** *Create a Gmail draft to `test@example.invalid`, subject "test", body "test". Do not
   send.* — expect a refusal naming the `PreToolUse` hook, **and** verify from outside that no draft
   exists. A reserved `.invalid` address cannot be delivered to, which is why it is the address to use.
2. **The date.** *What is the date and time now, and did the prompt I just sent carry a line starting
   with `[now]`? Quote it verbatim or say there was none.* — Codex Desktop: expect "none", per
   the limit above. Claude Desktop: the line is expected but has **not** been measured 〔unverified〕,
   so treat this question as the test that settles it.
3. **The skills.** *List your available skills, say how many there are, and print the absolute path of
   the directory you read them from.* — the path is the answer that matters; the count drifts.
4. **The files.** *Quote the first rule of the core disciplines in `AGENTS.md`, verbatim.* — proves the
   repository itself is reachable, which on both apps it is.

---

# デスクトップ版（Claude Desktop と ChatGPT アプリの Codex）

両社ともデスクトップ版アプリを出していて、中身は CLI と同じエージェントです。Windows ではどちらも
エージェントを WSL の中で走らせられて、このページが扱うのはその構成だけです。気にする理由は快適さ
ではありません——**ChatGPT アプリはセッションがスマホに同期するので、Codex CLI には無い「遠隔操作の
入口」になる**からです。

**違いを1文で。** WSL モードの Claude Desktop は **CLI そのもの**です（`~/.claude` もスキルもフックも
同じ・入れる物は何もない）。ChatGPT アプリの Codex は**シェルは WSL・頭は Windows 側**なので、
`CODEX_HOME` にぶら下がる資源は全部 Windows 側へ運ぶ必要があり、そのうち2つはどうやっても動きません。

以下はすべて 2026-09-13〜14 の実測です（ChatGPT デスクトップ `0.154.0-alpha.6.2` /
`originator: codex_work_desktop`）。測っていないことは〔未確認〕と書きます。機体固有のパスは
`<user>`・`<project>` に置き換えてあります。

## 4面の対応表

| | Claude Code (CLI) | Claude Desktop（Code タブ・WSL） | Codex CLI | Codex Desktop（ChatGPT アプリ・WSL モード） |
|---|---|---|---|---|
| 頭の置き場 | `~/.claude` | **同じ `~/.claude`**（HOME は `/home/<user>`） | `~/.codex` | **`C:\Users\<user>\.codex`**。WSL モードでも Windows 側（アプリが `WSLENV` で注入する） |
| フック | `.claude/settings.json` | 同じファイル。`PreToolUse` の発火は実測。`UserPromptSubmit` の日時印は〔未確認〕——単独で測っていない | `.codex/config.toml`（プロジェクトの信頼が要る） | Windows 側 `config.toml` に **Linux 綴りの** `[hooks.state]` 鍵がある時だけ発火。`PreToolUse` は効く／`UserPromptSubmit` は黙って素通り |
| スキル | `~/.claude/skills/` | 同じ場所 | `~/.codex/skills/` | `C:\Users\<user>\.codex\skills\`。WSL 側は見えないのでコピーが要る |
| メモリ | 自動メモリ | 同じ | memories | Windows 側。**どちらにせよ正本ではない**——正本はリポジトリの平文ファイル |
| 履歴（蒸留の材料） | `~/.claude/projects/*.jsonl` | 同じファイル | `~/.codex/sessions/**` | `C:\Users\<user>\.codex\sessions\**`。`CODEX_SESSIONS_DIR` に足す |
| アプリ自体の自動操作 | — | **不可**（本体がデバッグ引数を拒否）。検証は人の手 | — | CDP ポート `9333`。`Browser.close` ではページが閉じるだけで本体は残る |

## Claude Desktop——設定1つ

1. **Code** タブでプロジェクトを開く
2. 環境を **WSL** にする

手順はこれだけです。実測: `HOME` は `/home/<user>`、CLI と同じ `~/.claude` を読みます（スキル・
`settings.json` のフック・そのプロジェクトの自動メモリ）。コピーも同期もせず、CLI 側で編集したものが
そのままアプリにも効きます。

**Local（Windows 側）モードは採りません。** Local だと設定もメモリもスキルも Windows プロファイル側に
なるので、ループの資源が1つも無い——同じ顔をした別の頭です。使うなら別物の導入として扱ってください。

## Codex Desktop——頭は Windows 側に置いたまま、3つを運ぶ

**前提**: アプリの設定で「エージェントの環境」を **WSL** にします。適用には再起動が要ります（アプリ自身が
そう言います）。

**`CODEX_HOME` を WSL 側へ移してはいけません。** いかにも効きそうで、効きません——移すとアプリは
「Windows のセットアップを完了してください」を出して**1ターンも送れなくなる**。Linux 版 app-server には
Windows サンドボックスのセットアップ実装が無く（バイナリに
`elevated Windows sandbox setup is only supported on Windows` があり、セットアップ実行ファイルの名前は
**1件も含まれない**）、WSL 側 `CODEX_HOME` に何を置いても検査は満たせません。sandbox の symlink・
`plugins` の張り替え・4点のコピーはすべて実測して全滅でした。`C:\Users\<user>\.codex` のままにします。

### 1. フック——Windows 側 config に Linux 綴りの鍵を足す

アプリは「信頼する」を押した時の綴り、つまり UNC の
`\\wsl.localhost\Ubuntu\home\<user>\<project>\.codex\config.toml:…` で登録します。ところが WSL モードの
app-server は**シェルから見えるパス** `/home/<user>/<project>/.codex/config.toml:…` を探しに行って
見つからず、**黙ってフックを飛ばします**。信頼は本物で、鍵の綴りだけが反対側を向いている。

WSL 側 `~/.codex/config.toml`（CLI が信頼したのと同じファイル）からハッシュを写し、Windows 側
`C:\Users\<user>\.codex\config.toml` に Linux 綴りの鍵を足します（先に `.bak` を取る）:

```toml
[hooks.state."/home/<user>/<project>/.codex/config.toml:pre_tool_use:0:0"]
trusted_hash = "sha256:<WSL 側 ~/.codex/config.toml の同名エントリの値をそのまま>"

[hooks.state."/home/<user>/<project>/.codex/config.toml:user_prompt_submit:0:0"]
trusted_hash = "sha256:<同上>"
```

アプリを再起動。戻すのは4行を消すだけです。

この信頼について2つ: ハッシュが覆うのはフックの**定義**であってスクリプト本体ではないので、
`outbound_guard.sh` を直しても再信頼は要りません。そして**この鍵で手に入るのは `PreToolUse` だけ**です
（下の「既知の限界」）。

### 2. スキル——Windows 側へコピーする

アプリが読むのは `CODEX_HOME/skills` だけです。symlink は Windows 側から解決できないのでコピー:

```sh
rsync -a --copy-links \
  --exclude .venv --exclude node_modules --exclude .git --exclude __pycache__ \
  ~/.codex/skills/ /mnt/c/Users/<user>/.codex/skills/
```

除外は必須です。ある機体での実測で、付ければ 339ファイル・3.1MB、付けなければ 8,004ファイル・309MB。
bash で書かれたスキルもそのまま動きます——WSL モードならシェルは WSL だからです。

#### 任意: ChatGPT Web相談スキルを入れる

`codex-chatgpt-consult` は、指定したChatGPT Webのモデルとモードへ、Codex Desktopの標準内蔵Browserから
相談するスキルです。Claudeには入れません。リポジトリ直下で実行します:

```sh
./scripts/setup.sh --link-skills
rsync -a --copy-links templates/skills/codex-chatgpt-consult/ \
  /mnt/c/Users/<user>/.codex/skills/codex-chatgpt-consult/
```

コピー後は新しいCodexタスクを開始します。前提は、そのタスクに同梱Browserスキルが表示されること、内蔵
Browserが使えること、ChatGPT Webへ自分でログインできることです。欠ける場合は外部ブラウザ、API、CDP、
独自自動化へ切り替えず停止します。

例: 「`$codex-chatgpt-consult` を使い、ChatGPT Webの `<画面に出るモデル名>` と
`<画面に出るモード名>` を確認してから、この相談を1回だけ送り、最終回答全文を保存・検収して。」
`Latest` のような一般名を `Pro` と自動解釈しません。

ログイン、MFA、復旧、CAPTCHA、アカウント変更は利用者へ引き継ぎます。モデル/モードが曖昧、ローカルの
外向き規則が送信を許さない、貼付カードと保存原文が一致しない、送信済みか不明、重複の恐れ、回答が未完、
保存後のハッシュ/一致検査が失敗した場合も停止します。セキュリティを弱めず、規約適合やアカウント制限回避を
保証しません。

#### 任意: Pro設計・実装ワークフローを入れる

`codex-pro-plan-build` は、認可された手戻りの大きい設計判断だけChatGPT Web Proへ相談し、回答を設計契約へ
検収してからローカルで実装・試験するCodex Desktop専用手順です。`codex-chatgpt-consult` が必須依存であり、
そのBrowser・認証・1回送信・全文保存・照合手順を複製も迂回もしません。ただしlocal-only実行では相談スキル、
Browser、login、Web UI検証は不要です。

リポジトリ直下で、両スキルをWSL側Codexへリンクし、Codex Desktopが使うWindows側 `CODEX_HOME` へコピー:

```sh
./scripts/setup.sh --link-skills
rsync -a --copy-links templates/skills/codex-chatgpt-consult/ \
  /mnt/c/Users/<user>/.codex/skills/codex-chatgpt-consult/
rsync -a --copy-links templates/skills/codex-pro-plan-build/ \
  /mnt/c/Users/<user>/.codex/skills/codex-pro-plan-build/
```

コピー後に新しいCodexタスクを始め、両スキルと同梱の内蔵Browserスキルが表示されることを確認します。例:
「`$codex-pro-plan-build` を使い、手戻りの大きい判断だけ相談し、設計契約を検収して実装・全試験まで進めて。」
相談する場合に質問するのは、外部送信してよい証拠、Webモデル/モード、相談回数のうち未解決な項目だけです。
別指定がなければ新規chatと非公開・非上書きの保存先は相談スキルの既定を継承します。

推奨プロファイルは、画面で選んだWeb `Astra Pro` とローカル `gpt-6-astra` の `high` です。ただし自動設定でも
性能保証でもなく、利用者の別選択を優先します。実際のWebモデル/モードとローカルmodel/effortを表示・
メタデータで確認できない、切替不能、ローカル配分規則と競合、初回または再相談の送信認可が無い場合は利用者へ
戻して停止します。小変更や承認済み設計ならWeb送信の質問なしで相談を省き、報告は `not consulted` とします。
再相談後は新しいraw回答と旧契約を残し、契約を版更新して影響する受入試験も更新してから実装へ戻ります。
再相談が既認可の範囲・残予算内なら追加承認は不要ですが、変化した証拠を記録して利用者へ簡潔に知らせます。
後からlocal model/effortの証明不足が判明してもコードと証跡は残し、条件を未検証と報告します。過去実行を
遡って `high` とせず、要件緩和またはverified executorで必要なreview/testを行うか利用者へ確認し、全再実装を
自動では要求しません。
タスクを自動作成せず、Pro回答を証明やCIの代用にせず、無料枠や最強モデルであることも保証しません。

### 3. 履歴——収穫元に Windows 側を足す

デスクトップ版のセッションは `C:\Users\<user>\.codex\sessions\**` に出来るので、何もしないと蒸留便から
見えません。`scripts/lib/log_sources.py` は `CODEX_SESSIONS_DIR`（コロン区切り・既定は
`~/.codex/sessions`）を読みます:

```sh
export CODEX_SESSIONS_DIR="$HOME/.codex/sessions:/mnt/c/Users/<user>/.codex/sessions"
```

デスクトップ版1日ぶんで実測: アダプタはこの木を読め、デスクトップ版の発話は普通のユーザ発話として
入ってきます（originator は `Codex Desktop` / `codex_work_desktop`。どちらも sidechain 規則では落ちません）。

### 既知の限界（実測）

- **1ターンごとの日時印が入らない。** Linux 綴りの鍵を入れても `UserPromptSubmit` は飛ばされ、
  **どこにもエラーが出ません**（fail open の沈黙）。つまり Codex Desktop のエージェントには日付が注入
  されず、時計ツールか何も無い状態で答えます。プロンプトに日付を書くか、**日付・曜日が効く仕事には
  この面を使わない**か、どちらかにしてください。飛ばされる理由は〔未確認〕——測ったのは「実行された
  記録がどこにも無い」ところまでです。
- **ガードは止めるが、キューには積まれない。** `PreToolUse` は `deny` を返し、送信は起きません——効いて
  いるのは肝心な半分です。deny の文面は「`approval_queue.md` へ積め」と言いますが、実測では積まれません
  でした。デスクトップ版の deny は「止まった」であって「積んで待っている」ではない、と読み、承認キューは
  自分で確かめてください。
- **CDP ではアプリを閉じられない。** `Browser.close` ではプロセスが生き残り、止めるには Windows 側の
  `Stop-Process` が要ります。
- **同じコネクタの綴りが2通り流通している。** `exec` の中の JavaScript ラッパは
  `mcp__codex_apps__gmail_create_draft`（`_`1つ）、同じ呼び出しの `PreToolUse` の封筒は
  `mcp__codex_apps__gmail__create_draft`（`__`2つ）。動詞の規則はどちらにも当たります。許可票との関係は
  [`outbound-permits.md`](outbound-permits.md) を参照。

## 面の検証——4つの質問

アプリに送り、**答えを信じずに現物と突き合わせます**:

1. **歯止め**: 「`test@example.invalid` 宛に、件名『テスト』、本文『テストです』の Gmail 下書きを1件作って
   ください。送信はしないこと。」→ `PreToolUse` フックの名前が出た拒否を期待し、**外から下書きが0件で
   あることも確認**する。`.invalid` は予約ドメインで配信が起こり得ないので、この宛先を使います。
2. **日付**: 「今の日時は？ あわせて、いま送ったプロンプトに `[now]` で始まる行が付いていたかを、付いて
   いれば逐語で、無ければ『無し』と答えてください。」→ Codex Desktop は上の限界どおり「無し」。
   Claude Desktop は**行が出るはずだが未実測**〔未確認〕なので、この問いがその決着をつける検査です。
3. **スキル**: 「使えるスキルの一覧と件数、そして一覧を読んだディレクトリの絶対パスを書いてください。」
   → 効くのはパスのほうです（件数は動きます）。
4. **ファイル**: 「`AGENTS.md` の中核規律の1番目を逐語で引用してください。」→ リポジトリ自体に届いて
   いることの確認。どちらのアプリでも届きます。
