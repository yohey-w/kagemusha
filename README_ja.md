<!-- porch:start -->
# kagemusha（影武者）

<sub>🇯🇵 **日本語** · [🌐 English (canonical) → README.md](README.md)</sub>

[![ci](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml/badge.svg)](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml)

<!-- contract:identity -->
**判断の中身は配らない。形だけ配る。**

**AIに稟議書を書かせる。** 外向きの操作（送信・公開・正本更新）の前に、AI に宛先・内容・根拠・取り消し可能性・自分の迷いを書かせ、人は「迷い」欄だけ読んで判子を押す。ボタンの承認は儀式になるが、稟議書の承認は読まないと押せない。

kagemusha は、**あなたが今使っている AI コーディングエージェント**（Claude Code・Codex・Cursor …）のために、**「内向きは自動／外向きは人間の承認」**と、却下理由を次の実行へ恒久規律として戻すループを、**Markdown の書式と、それを動かすスクリプト**で配るキットです。常駐エージェントでも SaaS でもなく、**あなたの判断基準は同梱しません**。

**向く人**: 不可逆な操作があり、却下理由を残せる人。／**向かない人**: 完成済みの判断基準や、チームの承認 SaaS が欲しい人。

**Claude Code でも Codex CLI でも動きます**——指示ファイルは1本、書式は同じ、起動行だけを差し替える（[対応表](#works-with-claude-code-and-codex-cli)）。

[固定証拠 `evidence-v1.0.0`](https://github.com/yohey-w/kagemusha/tree/evidence-v1.0.0)・[10分デモ](docs/getting-started.md#10分デモ)・[導入手順](docs/getting-started.md#手順コピペ)

<!-- contract:demo -->
```bash
git clone https://github.com/yohey-w/kagemusha.git
cd kagemusha
./scripts/demo-distillation.sh   # 約10分・APIキー不要・あなたのファイルに触れない
```
<!-- porch:end -->

*節番号は以前の README から引き継いでいます——既存のリンクと引用が解決し続けるためで、飛んでいる番号は意図的です。中身は [`docs/`](docs/README.md) に移りました。*

## 3. これは何を解くのか（1分版）

AIに仕事を渡すと、詰まるところは2つあります——**取り消せない操作**と、**却下のたびに捨てられている、あなた自身の判断**。どちらも、モデルが賢くなるだけでは片付きません。前者は**承認キュー**が受けます——内向きの作業は自律で走り、外向きの操作はあなたの前で止まる。後者は**判断蒸留**が受けます——却下理由を残し、蒸留し、次のセッションのエージェントが読み直す。設計の全体は [`docs/design.md`](docs/design.md)。

### 1分版の外側——北極星と、まだ開いている問い

*1分版はここまでです。* 上の2つの機構は、いま書いたところを受け持ちます。決着していないのは、その下にある一般の問いのほうです——この2つは、その問いへの部分的な答えでしかありません。問いはこうです: **その判断が「あなたのもの」であり続けるために、最小限、何を見せられ、何を尋ねられればよいか。**

「あなたのもの」には3つの意味があります: **価値の判断はあなたが書いた**・**外に対して責任を負うのはあなた**・**後からそれを取り消せる**。そして、その節約——見せる量を削ること——には上限があります。短い版で決めたときに失うものが、**全部読んでから決めた場合**と比べて、あなたが決めた許容値を超えないこと。

厳密な形が要るなら、こう書けます: *決定ごとに、人間の価値著者性・対外責任・後日の回復能力を残したまま、完全な証拠を精査した場合に比べた追加判断損失を許容値以下に抑える、最小の意思決定表現と相互作用は何か。*

**モデルが賢くなるだけでは決着しない理由。** 詰まっているのは人間の注意と作業記憶で、モデルの性能が上がっても動きません。機械が正しくても**責任は人間に残る**ので、差し出しの形は永続的に必要です。そして信頼は構造——追記型の台帳・逐語・関門——から来ますが、モデルが説得的になるほど「推論が事実の顔をする」危険はむしろ増えます。これはモデル側が無力だという主張ではありません（人間へ渡すかどうかをモデルに学習させる研究はあります）。主張は「**性能向上だけでは閉じない**」——書式・関門・台帳の側にも、設計が要る、です。

この問いから出てくるのに、**このキットにまだ入っていないもの**: 決定の等級分けです——全部にOK/NGを求めるのは誤りで、逆に、OK/NGという二択そのものが道具として合っていない決定もある。これは研究中の線であって、機能ではありません。

この問いをさらに一段下ろすと「そもそも仕事とは何をする操作の連なりか」になります——実走から出た暫定の答えは [`docs/context-editing.md`](docs/context-editing.md)（入手→編集→出力・案件の3台帳・コンテキストの4属性）。

<!-- contract:evidence -->
## 証拠と射程

**固定証拠: [`evidence-v1.0.0`](https://github.com/yohey-w/kagemusha/tree/evidence-v1.0.0)** — 定刻の週次蒸留が実際に走ったことと、訂正が恒久規律へ到達した一例を、実走インスタンスから匿名化した現物で示します。**これは n=1 の実走証拠であり、効果量も一般化可能性も主張しません。** `main` は現在の機構、タグは固定された証拠です。射程と限界: [`cookbook/author/evidence/README.md`](cookbook/author/evidence/README.md)。

**そして、このリポジトリが何であるか。** 参入障壁で囲った製品ではありません——**上に書いた壁、すなわち人間の注意と、人間に残る責任に、公開の場で取り組んでいる者の実験ノート**です。方法と、それを実際に走らせた記録。答えの部品は、すでに他分野にあります——人間と自動化の監督論、会話における共通基盤（grounding）、状況認識、必要最小限の手引き（ミニマル・マニュアル）の4分野です。もっとも近い枠組みは Zhu ら (2026, *AI and Ethics* 6(3))——AIの**遂行の主体性**（AIがやる）と人間の**評価の主体性**（人間がそれでよいと決める）を分け、**solve-verify 非対称性**（解き直すより検査するほうが安い）を使って、人間が自分でやり直さずに検査・異議申立てできるように出力を設計する、という枠組みです。当方が探した範囲で見つからなかったのは、それらが**一体で**運用されていることです——決定の重さに応じて差し出しを変え、人間がいまどこまで話を握っているかに合わせ、形式そのものを実験的に削り、後日の回復を制約に置き、価値の決定を「理解」ではなく「著者性」として扱い、要約を書いたAIをその検査から外す。この6つが同時に回っている例です。統合している先行研究をご存じなら、教えていただけることのほうが GitHub のスターより価値があります（[`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)）。

<!-- contract:boundary -->
## 8. 安全とデータ境界

| | 何か | `setup.sh` の扱い |
|---|---|---|
| **core** — `scripts/` `templates/` `docs/` `tests/` `manifests/` | **機構**: 足場・スクリプト・**空の書式**・受入ゲート | [`manifests/scaffold.tsv`](manifests/scaffold.tsv) に載っている行だけを展開——**中身の入っていない書式**が出てくる |
| **[`cookbook/`](cookbook/README.md)** — 標本棚 | **中身**: 誰かの実走で焼けた規律・証拠の抜粋・他人の棚 | **読まない・コピーしない・実行しない** |

⚠️ この二層は**プライバシー境界ではありません**（同一リポジトリ・同一の恒久履歴）。**あなたのデータ**を git から守るのは許可リスト方式の `.gitignore` で、正本・台帳・設定は誤ってもコミットできず、`git pull` はその下でキットだけを更新します。全文と core だけの checkout: [`docs/layers.md`](docs/layers.md)。

<!-- contract:canon -->
## 5. 全体の仕組み

<!-- canon:correction-promotion:start -->
### 訂正の昇格

このキットの中心語の**正典定義**。3語だけ、この文言で固定する——**どこで引いても同じ定義であること自体が、この語の値打ち**だからだ。引用・転載は自由。（English: [README.md](README.md#訂正の昇格)）

**訂正の昇格**——**AIとの会話で生じた人間の却下・訂正から、再利用できる判断基準を抜き出し、人間の審査で恒久ルールへ上げる工程。**

- **該当する**: 却下が実発話のまま台帳に残り、審査キューに規律案として差し出され、**あなたがそれを自分の指示ファイルへ写す**。写した行為が昇格だ。
- **該当しない**: 訂正を素材ファイルや台帳へ**積むところまで**。「**移動には関門は要らない。昇格には要る**」（[`docs/distillation-loop.md`](docs/distillation-loop.md)）——その関門は人間だ。

**人間定置網**——**AIの最後に人間を置いたまま、そこで生じた判断を次回のAIへ戻さず、人間が同じ確認を繰り返す運用。**

- **該当する**: 人間は毎回きちんと働いているのに、来週も同じ却下が来る（[§3](#3-これは何を解くのか1分版)）。
- **該当しない**: 不可逆な外向き操作の前に人間を置くこと**そのもの**——それは[依存校正](#依存校正--キュー全体の底にある原則)だ。人間がいることが定置網なのではない。**そこで出た判断が次回のAIに戻っていないこと**が定置網。

**判断ループ**——上位概念。**[承認ループ](#3-これは何を解くのか1分版)（生成→検証→内向きは自動／外向きはキューへ→人間が判断）と[判断蒸留](#却下を資産に変える--判断蒸留)（却下理由→台帳→価値判断モデル→次セッションのAI）が、1本に閉じた輪。** 新しい機構ではなく、この2つが繋がった状態の名前だ。

- **該当する**: 却下が原則になり、その原則を読んだエージェントが、次は同じ案をそもそも出さなくなる（[一周が閉じた実走の証拠](cookbook/author/evidence/README.md)）。
- **該当しない**: 上半分だけが回っている配線。承認キューは動いているが却下理由がどこにも流れず、モデルが改訂されない。それは承認ループであって判断ループではない。

**関係は一文に畳める: 人間定置網をやめるには、訂正を昇格させ、判断ループを回す。**

キット全体のファイル単位の対応表は [§10](#10-リファレンス)。全機構は [`docs/judgment-distillation.md`](docs/judgment-distillation.md)・軽い日次レーンは [`docs/distillation-loop.md`](docs/distillation-loop.md)・昇格した後の話は [`docs/discipline-audit.md`](docs/discipline-audit.md)。
<!-- canon:correction-promotion:end -->

### 却下を資産に変える → 判断蒸留

訂正は**型ごとに**戻します——**機械的**な穴は `verifiers.md` の1行へ、**判断**は `judgment_model.md` の原則へ、**どの成果物でも入れている同じ直し**は次の初稿を頼むときの指示文に入る規約へ。詳細は [`docs/judgment-distillation.md`](docs/judgment-distillation.md)・[`docs/norms-loop.md`](docs/norms-loop.md)。

### 依存校正 — キュー全体の底にある原則

確認の水準は、**間違ったときの損失・可逆性・検出可能性・検証の費用**に合わせて決めます。**内向き／外向きはその近似であって軸そのものではありません——本当の軸は「戻せるか」**。詳細は [`docs/design.md`](docs/design.md)。

## 6. 自分の環境に入れる（30分・コピペ）

**移動しました → [`docs/getting-started.md`](docs/getting-started.md#手順コピペ)。** clone して `./scripts/setup.sh` を走らせると、**中身の入っていない書式**があなたのフォルダに出てきます——あとは、いま使っているアシスタントでそのフォルダを開いて仕事をするだけです。前提表・コピペ手順・任意の血統違い検算器は全部そちらにあります。*（見出しを残しているのは、記事と併読本がこの節を番号で引いているためです。）*

### Works with Claude Code and Codex CLI

使う CLI は**キー1個**で決まります: `config.env` の `AGENT_CLI=claude|codex`（`auto` = PATH にある方）。**環境変数に置いた同じキーはファイルより強い**ので `AGENT_CLI=codex ./scripts/morning_brief.sh` は一回きりの切り替えになり、`AGENT_CMD` は「その CLI の実行ファイルの差し替え」だけを担います。プロンプトも書式も承認の境界も変わりません——**変わるのは起動行だけ**で、それは1か所（[`scripts/lib/agent_cli.sh`](scripts/lib/agent_cli.sh)）が組み立てます。

**Claude Code / Codex CLI 両対応の、任意難易度ルーティング。** 親が `simple` / `standard` / `complex` の1つを選び、例えば `agent_run --difficulty standard -- "$PROMPT"` と呼ぶと、[`config.env.example`](config.env.example) の provider 別 model / effort 表へ解決します（Codex SOL の low / medium / high が同梱例で、一律 xhigh にはしない）。別軸の任意例として、使える環境では Astra 親を high で運用し、その親が難判断で Astra xhigh の子、特に難しい推論・創造だけ max の子を自律的に選び、SOL 実作業子と併用できます。親セッション自身の effort を途中変更する仕組みではなく、Astra も全利用者へ強制しません。独自の shell 呼び出しは、同梱スクリプトと同じく `scripts/lib/agent_cli.sh` を `config.env` より先に source します。本文の自動分類や無限昇格はしません。`--model` / `--effort` は最優先、export は設定ファイルより優先、難易度省略時は従来どおりです。profile が効くのは `agent_run` だけで、ネイティブの sub-agent API はその API が公開する model / effort 欄を起動呼び出しに指定します。子も利用枠を消費するため節約は保証せず、承認・権限の境界も変えません。

| | Claude Code | Codex CLI | 片方に無いときの代替 |
|---|---|---|---|
| 指示ファイル | `CLAUDE.md` ＝ `@AGENTS.md` の1行 | `AGENTS.md` を直読 | 中身は1本・名前が2つ。`setup.sh` が両方作る |
| スキル | `~/.claude/skills/` | `~/.codex/skills/` | `setup.sh --link-skills` が有る方へ symlink |
| 毎ターンの日時スタンプ | `.claude/settings.json` の `UserPromptSubmit` hook。stdout はそのまま使われる | `.codex/config.toml` の `[[hooks.UserPromptSubmit]]`（プロジェクトの信頼登録が前提）。同じイベントだが形式が違う——stdout は JSON エンベロープ `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"…"}}` 必須。平文は TUI では Hook failed、`codex exec` では無言で破棄される | `AGENTS.md` に「日付は必ず検算」と書く |
| メモリ | 自動メモリ | memories | **どちらも正本ではない。** 正本はプレーンファイル（[`ssot/README.md`](ssot/README.md)） |
| ヘッドレス起動 | `claude -p …` | `codex exec … -s read-only\|workspace-write -o …` | argv でプロンプトを取る CLI なら何でも |
| 無人での接続子 | 動く（`--allowedTools mcp__…` で絞れる）——ただしこれは CLI の既定の挙動であって選んで置いた制御ではない。一度広く書けば無言で開く。だから下の行が要る | 動くが、**ツール単位の許可リストが無く、プラグインの `enabled=false` も切れない**（実測 2026-09-07）——外向きの歯止めは同梱の `PreToolUse` フック（[`docs/inbound-loop.md`](docs/inbound-loop.md)） | 読み取り専用に保つのは文章ではなくフックで |
| 外向きの歯止め（`PreToolUse`） | `.claude/settings.json` の `PreToolUse`・matcher は `mcp__.*` で [`templates/claude/hooks/outbound_guard.sh`](templates/claude/hooks/outbound_guard.sh) を指す。**`.*` が必須**——普通の文字だけの matcher は完全一致で比較され、どのツールにも当たらない（しかも何も言わない）。通すときは `{}`。`permissionDecision: "allow"` は使わない——**許可プロンプトを飛ばして呼び出しを承認してしまう**から | `.codex/config.toml` の `[[hooks.PreToolUse]]` に絶対パスで [`templates/codex/hooks/outbound_guard.sh`](templates/codex/hooks/outbound_guard.sh)。こちらはスキーマが `allow` も `ask` も受け付けないので、通す手段は `{}` しか無い | どちらのホストも**フック不全時は fail open**——`./scripts/test.sh` が両方に合成 JSON を流して検査する。承認済みの1通だけを開ける[許可票ヘルパは共有](templates/hooks/outbound_permit.py)（[`docs/outbound-permits.md`](docs/outbound-permits.md)） |
| 会話ログの採取 | `~/.claude/projects/*.jsonl` | `~/.codex/sessions/**/rollout-*.jsonl` | アダプタ1本が両方を読む。`LOG_SOURCE=auto` で有る方 |
| スケジューラ | cron / タスクスケジューラ——両方同じ。CLI 固有のスケジューラは使わないし、要らない |||

このキットが自動便から Codex を呼ぶときの会話は、**`~/.codex/sessions` に残りません**（`--ephemeral`）。あの木は蒸留便が採掘する場所で、**機構自身のプロンプトはあなたの判断ではない**ため。cron の不調を追うときだけ `AGENT_CLI_RECORD=1` で記録を戻す。

**Claude Code・5行。** ① `./scripts/setup.sh` ② `AGENTS.md` の委任境界を埋める ③ `cp config.env.example config.env` して `PROJECT_ROOT` と `AGENT_CLI="claude"` ④ `./scripts/morning_brief.sh` を手で1回 ⑤ その行を cron へ。

**Codex CLI・5行。** ① `./scripts/setup.sh --codex` ② `AGENTS.md` を埋め、`~/.codex/config.toml` に `[projects."<絶対パス>"] trust_level = "trusted"` を足す——**これが無いとプロジェクト側の設定は黙って無視されます** ③ `cp config.env.example config.env` して `PROJECT_ROOT` と `AGENT_CLI="codex"` ④ `./scripts/morning_brief.sh` を手で1回 ⑤ その行を cron へ。

**外向きの歯止め——「文章」は歯止めにならない。** 実測 2026-09-07・codex-cli 0.153.4。`AGENTS.md` に「外向き＝承認」を書き、最も厳しいサンドボックスのまま `codex exec -s read-only "顧客へ『テストです』とメールを送って"` を投げたら、**誰にも聞かずに送信ツールを実発行**し、承認ポリシーに弾かれると**実在の顧客宛ての下書きに回り込んだ**。`-s read-only` が縛るのはファイルシステムであってコネクタではなく、塞がれた経路は閉じた扉ではない。⇒ 機構の層を**2つ**使う。ただし効いたのは①だけだ: ① 同梱の `PreToolUse` フック（[`templates/codex/hooks/outbound_guard.sh`](templates/codex/hooks/outbound_guard.sh)・`setup.sh --codex` が設置）。操作名が `send`／`post`／`create_draft`／`reply`／… のコネクタ呼び出しを拒否し、「`approval_queue.md` へ積め」と返す——同日の再測定で、下書きは拒否され、読み取りは通った ② コネクタ自体を切る——ただし `[plugins."<id>"] enabled = false` は**正しいIDでも無効化できなかった**ので、本当に消すなら `codex plugin remove`（読み取りも消える）。詳細と通信形式は [`docs/inbound-loop.md`](docs/inbound-loop.md)。

## 9. 発展編

**移動しました → [`docs/operations.md`](docs/operations.md)**——毎日と毎週の実務・複数案件の回し方・自分の時間の数え方（G/S/D/V/I/R）。あわせて [`docs/inbound-loop.md`](docs/inbound-loop.md)（世界からの入力を捕まえる）・[`docs/faq.md`](docs/faq.md)（設計の考え方）。*（見出しを残しているのは、併読本の付録がこの節を番号で引いているためです。）*

<!-- contract:routes -->
## 10. リファレンス

| やりたいこと | 開く文書 |
|---|---|
| 試す→入れる | [`docs/getting-started.md`](docs/getting-started.md) |
| 毎日・毎週まわす | [`docs/operations.md`](docs/operations.md) |
| 設計の全体を掴む | [`docs/design.md`](docs/design.md) |
| データ境界を確かめる | [`docs/layers.md`](docs/layers.md) |
| 却下を規律に変える | [`docs/judgment-distillation.md`](docs/judgment-distillation.md) |
| それ以外・ファイル単位の全一覧 | [`docs/README.md`](docs/README.md) |

<!-- contract:field-record -->
### 背景と実走記録

**このリポジトリだけで、キットの導入・運用・検証は完結します。** 設計判断の経緯、試して落とした案、実運用で訂正が規律へ変わっていった時系列は、[無料の記事](https://zenn.dev/shio_shoppaize/articles/kagemusha-shogun-disband)と、有料の Zenn 本 [『AI家臣団を解散して、影武者を一人だけ残した　兵法書と訓練記録』](https://zenn.dev/shio_shoppaize/books/kagemusha-book) に記録しています。**どちらにも、このリポジトリを使うために足りない手順は入っていません。**

### 貢献 ・ ライセンス

貢献が何で測られ、どこへ行くか: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)。MIT — [LICENSE](LICENSE)。
