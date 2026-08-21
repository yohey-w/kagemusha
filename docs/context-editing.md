# コンテキスト編集 — 8/18〜19の実走で確定した設計原理 v2

*日本語が本文。英語版は末尾（English version is at the bottom of this document）。*

`docs/design.md` の承認ループ・判断蒸留は「どう検証し、どこまで任せるか」を扱う。この文書はその一段下——**そもそも仕事とは何をする操作の連なりか**——を扱う。ある受託案件の実走（8/18〜19）で殿が2度言い直した末に着地した1枚。台帳の出所は `judgment/decisions_journal.md` の D-2026-08-18-18 / 23 / 24 / 25、D-2026-08-19-01 / 02。

---

## 1. 仕事の一般形

ホワイトカラーの仕事は、**コンテキストの入手→編集→出力**に尽きる。

- **入手**（get）はツールが増やす——会議・メール・資料・API。
- **出力**（generate）はLLMが速い——下書き・要約・整形。
- **編集**（edit）だけが空白のまま残る。ここが人が最も面倒がり、最も失敗する層。

編集をさらに分解すると: 取得／確認／統合／矛盾解消／穴の発見／**穴埋め（誰が埋めるか）**／優先付け／**決める**／言語化／配送、という操作の連なりになる。人間が必須なのは「決める」（価値・約束・不可逆・好み）と一部の言語化のみ——それ以外はエージェントが担える。**このキットの本体は「編集」器である。**

## 2. 案件が持つ3台帳

案件を「事実」「穴」「分岐」の3台帳に割ると、「人の判断がどこで要るか」が住所つきで見える。

| 台帳 | 1行の中身 | 規律 |
|---|---|---|
| **事実** | 確認済みの1件＋出所 | 出所のない事実は書かない |
| **穴** | 未確認の1件＋**誰が埋められるか**（`fills_by`: `counterpart` 相手／`material` 資料／`research` 調査／`owner` 本人） | 埋め手のない穴は願望であって穴ではない |
| **分岐** | 決めるべき1件＋**誰が決めるか**（`decides_by`: `owner` 本人／`counterpart` 相手／`contract_change` 契約変更／`agent` エージェント） | 選択肢と結果のない分岐は決めようがない |

**穴の属性は2軸に分ける**——`fills_by`（誰が埋められるか＝情報源）と**行動可能性**（`ready` 着手可／`blocked` 依存待ち／`waiting_external` 相手待ち／`needs_judgment` 判断要／`scheduled` 予定済／`unknown` 未確認）は別軸であり、1つのフィールドに両方の意味を持たせない（8/21改訂・D-2026-08-21-06）。

これは `ssot/`（いまの状態・上書き可）の拡張であり、`judgment/decisions_journal.md`（履歴・追記専用）とは分離を保つ。書式とひな型は [`templates/context_ledgers_template.md`](../templates/context_ledgers_template.md) / [`templates/ledger.yaml.example`](../templates/ledger.yaml.example)。

## 3. コンテキストの4属性

コンテキストは**位置**（どこにあるか）・**鮮度**（いつ時点の事実か）・**所有**（誰の情報か）・**配送先**の4つで扱う。**配送先を持たない情報は、あっても無いのと同じ。** ある実走では、相手側の現状に関わる事実が3件、別フォルダに置かれたまま配送先が決まっておらず、会議の場で「知らなかった」反応を招いた——情報が無かったのではなく、届く経路が設計されていなかった。

## 4. 4ループ

会議支援・案件伴走を、開発に特化しない一般語で4つに割る。会議は「入手」の一形態にすぎない。

1. **前** — 相手の現状を知ってから会う。こちらの理解を先に述べる。
2. **中** — 思い込みと相手の言葉のズレに、その場で気づく。事実と**矛盾**⚠️・**既知**✔️・**新情報**＋の3種で足りる。
3. **後** — 相手の言葉が「約束・宿題・決めたこと」から漏れていないかを監査する。A取れていた／B届いていない／C取り逃し／D初出、の4分類。
4. **横断** — 約束・方針同士が矛盾していないかを見る。新しいトピック×既存の裁定/要件/契約前提を突き合わせ、両立／上書き／衝突と、それを誰が決めるかを出す。

## 5. 人の出番の住所

人の出番は、**分岐のうち本人（owner）が決めるものだけ**。それ以外——事実の確認・穴の発見・矛盾の検知・優先付け・言語化・配送——はエージェント側の仕事であり、住所（どの操作か）が決まっているぶん自動化の範囲を狭く言い切れる。

**指標**: 「本人が自発的に言い出した介入の数」。ゼロに近いほど、分岐が問いの形で先に届いている。ある夜の前半は10件だったが、同じ夜の後半に分岐台帳を先に配送すると6分岐すべてが問いの形で届き、自発介入は0だった。

**段階的自律**は "every agent earns trust before it acts alone" の型で進める——`decides_by: agent` への昇格は、的中実績が積み上がってから引き上げる（現状は据え置き）。

## 6. 反例（ある夜の実走）

即答そのものは速かった（応答0.4〜0.6秒）。しかし:

- 役に立つ答えが届いた回数は**0**。
- 相手が既に伝えていた前提3件に「知らなかった」という反応。
- 必須項目の誤判定 6/12。

原因は知識の不足ではなく、**編集**（横断集約・矛盾検知・配送先の指定）の欠落だった。速さは編集の穴を埋めない。

## 7. 会議設計テンプレ v0

3台帳の更新手順を、会議という入手の場に落としたもの。

1. 目的1行
2. 現状の再提示（ライブ・リキャップ）
3. 不明点一覧（優先順位つき）
4. 論点と時間箱（超過はパーキングロットへ）
5. 範囲の線（金額・期限の中/外を明言）
6. 合意と次アクション（復唱）

反例で出た失敗の多くは、この定石（目的の共有・As-Is/To-Beの再提示・in/outスコープ・タイムボックス・網羅的な不明点確認）が既に埋める形の穴だった。

## 8. 射程 — 開発案件に特化しない

3台帳・4ループの中身が要件かコードか議事録かは案件次第。**むしろ営業・交渉では「中」ループ（前提ズレの即時検知）の優先度が最も高い**——開発には検収というやり直しの関門があるが、営業の認識違いはそのまま契約・失注に直結し、やり直しが利かない。

## 9. ゴールコマンド — 委任の制御単位（v0.3・条件付き採用）

8/20夜、ある受託案件の実走で立てた1段。出所は `judgment/decisions_journal.md` の D-2026-08-20-03 / 04。**この節は確定原理ではなく条件付き採用**——8/21の外部レビュー2本を反映した改訂版である（出典noteは §9.7）。

**多段・跨セッション・外部依存を持つ仕事では、委任の制御単位をゴールコマンドに置く。** タスクは、成立条件の未充足から生成される実行単位にすぎない。一方、**原子的・可逆・低リスクな仕事は直接タスクのままでよい** ——ゴール化はコストを伴うので、全部に被せるものではない。タスクだけを渡す限り、タスクとタスクの間を埋める仕事——段取り——は人の頭に残る。ゴールを渡した瞬間、段取りそのものがエージェントの仕事になる。両者は指示の粒度ではなく、**誰が段取りを持つか**で分かれる。

**構造は4層に分かれる。** ①**事実・穴・分岐**（§2の3台帳。認識と判断の単位）②**ゴールコマンド**（本節。成果契約の単位）③**派生アクション／ワークキュー**（実行単位。新設——本節v0.3の主眼）④**イベント受領・処理記録**（何が入ってきて、何に化けたかの記録）。委任の粒度は**直接タスク／軽量ゴール／完全なゴールコマンド**の三段階を持つが、**その一番下に④から生まれる派生アクションを正式な単位として置く**。小作業（共有シートを開いて値を抜く、1件確認する、等）は軽量ゴールへ昇格させない——**成果契約と実行単位の型を混ぜると、親ゴールの成立判定と子作業の完了判定が同じ機構で処理され、区別できなくなる**（詳細はD-2026-08-21-06）。

### 9.1 ゴールコマンドの中身（4項目）

1. **ゴール状態** — 日付つき・検証可能な1文（「◯月◯日までに、Aが完了していること」）
2. **成立条件表** — 行＝真であるべきこと／いまの状態／真にする手／期限／証跡／判定者。**未充足の行が仕事のキューになる**。§2の3台帳（事実・穴・分岐）を駆動する上位構造がこの表であり、台帳自体は状態、成立条件表はゴールを起点にしたキュー生成規則を持つ
3. **人に戻す条件** — `decides_by: owner` の分岐（§2）と、外向きの承認が要る操作
4. **権限境界** — 許可される手段／禁止される手段／予算・時間・試行回数の上限／外向き操作のゲート（送信・公開・課金・不可逆操作）／扱ってよい情報の範囲／**停止条件**（ここに触れたら止めて人に返す）。加えてゴール自体の**版と変更履歴**を持つ

権限境界が無いゴールは、委任ではなく白紙委任になる。**「何をしてよいか」だけでなく「どこで止まるか」を書けていないゴールは発行しない。**

### 9.2 発行トリガー（3分類）

トリガーは「鳴る条件」で並べるのではなく、**鳴った結果どの処理に流すか**で分ける。新規ゴールの生成と、既存ゴールの更新を同じ口に流すと重複ゴールが増える。

| 分類 | 何が起きたとき | 流す先 |
|---|---|---|
| **goal_birth**（新規生成） | 日付つきの約束が生まれた／不可逆イベントの予定が確定した | 新しいゴールの殻を作り、成立条件表を起こす |
| **goal_transition**（既存の再開・変更・取消） | 相手のボールが返ってきて着工可能になった／前提が変わった／約束が取り下げられた | 既存ゴールを特定して状態遷移（再開・改版・supersede・取消）。**新規生成に流さない** |
| **corrective_action**（再発防止） | 同種の指摘が2回目に入った | ゴールではなく規約・検査の追加として処理し、必要なら既存ゴールの成立条件行を増やす |

### 9.3 ハーネスの責任は「検知」ではなく「閉包」

**トリガーの検知を人（モデル）の注意に置くと、確率的に蒸発する。** 指示ファイルに「気づいたら発行せよ」と書いても、それは注意という不安定な層に依存する規律であり、繰り返し漏れる。だが**検知→通知までをハーネスに置くだけでは足りない**。通知は鳴ったのにモデルが何もしなかった、という状態が「正常終了」として見えてしまうからだ。

**ハーネスは状態遷移を閉じるところまで持つ。**

1. **候補作成** — 約束の発生源（送信メール・台帳追記・議事録）からトリガー候補を機械的に起こす
2. **殻の自動生成** — 候補からゴールの空殻（ID・ゴール状態の下書き・空の成立条件表）を作る
3. **重複照合** — 既存ゴールと突き合わせ、同一案件なら goal_transition へ回す
4. **未解決として保持** — 候補は `issued` / `merged` / `rejected`（理由必須）/ `superseded` のいずれかに落ちるまで**未解決のまま残す**。無視は終端状態ではない
5. **滞留エスカレーション** — 未解決のまま一定時間を超えた候補は人へ上げる

**「鳴ったが、モデルが何もしなかった」を正常終了にしない。** これが検知と閉包の差である。

さらに逆向きの不変条件を1本置く——**不在照合**。確定済みの不可逆イベント（本番日・締切・送信済みの約束）に対して、有効なゴールが1つも紐づいていない状態を**異常として検知する**。トリガーの取りこぼしは「鳴らなかった」ので気づけないが、不在照合はイベント側から見るので取りこぼしを拾える。

**イベント処理の完了不変条件**——これは③派生アクション層の検査であり、プロンプト規律（「発注し尽くせ」と書く）ではなく状態遷移の検査として持つ。**イベント処理は、派生結果が「作業投入」「明示的保留（期限つき）」「人への返却」「作業なし（理由コード）」のいずれかに記録されるまで完了扱いにしない。** 旧い言い方「全部発注し尽くす」は撃ち切りの基準として曖昧なので、次に差し替える——**全部を作業レコードへ変換し、即時発注（読取・可逆・低コストなもの）／期限つき待機／依存待ち／人戻し／不要のいずれかに確定するまで完了にしない**。

検知は3本立てで持つ——**イベント完全性**（入ってきたイベントを取りこぼしていないか）／**状態遷移完全性**（各イベントが上記4終端のいずれかに落ちたか）／**実行健全性**（投入した作業が実際に進んでいるか）。このとき**ゼロ件と検査不能（`coverage_unknown`）を区別する**。「対象イベントが0件だった」と「そもそも走査できていない」は別の状態であり、後者をゼロ件に丸めると欠落が消える。

### 9.4 成立条件表の完全性ゲート

**表を作ったことは、条件が揃っていることを意味しない。** 埋めた行がすべて真になっても、書かれなかった行があれば本番は落ちる。したがって表それ自体の完全性を、表の外から検査する。

- **案件種別テンプレート** — 種別ごとに「最低限この観点は行があるか」を定める。本番イベント（納品・稼働開始・対外発表）の場合は、**通し試験／接続方式／項目対応／当日の役割分担／承認／失敗時の代替・撤退／ロールバック／証跡**を必須観点とする
- **独立の抜け検査** — 表を書いた者と別の者（別血統のモデル、あるいは人）が、テンプレートに照らして抜けを探す。**自分の表を自分で完全と判定しない**

行の状態は真偽の二値ではない。次の7値で持つ——`satisfied`（真・証跡あり）／`unsatisfied`（偽）／`unknown`（未確認）／`blocked`（他者・外部待ち）／`stale`（かつて真だが証跡が古く再確認が要る）／`waived`（意図的に免除・理由と承認者を記録）／`not_applicable`（この案件では非該当）。**二値にすると `unknown` が `unsatisfied` か `satisfied` のどちらかに丸められ、丸めた側の情報が消える。**

### 9.5 反例（匿名・ある受託案件）

本番日が確定してから2日間、案件はゴール化されなかった。渡された材料（実データ）は本番の2週間半前から手元にあり、通し検証は工程として置けば実施可能だったが、置いていなかった。その結果、通しリハーサル未実施・接続方式未決・当日項目の未確認が本番9日前に露呈した。

**評価は正直に置く。この設計があれば防げた、とは言えない。** ゴールコマンドを発行していても、成立条件表に「通し試験」の行が無ければ同じ結末になる。言えるのは**有力な対策候補である**ところまでで、反例は設計の証明ではなく設計の出所である。

真因は**動機の問題ではなく状態遷移の閉包不足**である。「本番日が確定した」という不可逆イベントは記録に残っていたのに、それがゴールの生成に接続されず、接続されなかったこと自体も検知されなかった（§9.3の不在照合が拾うべき型）。「気づけなかった」「気が回らなかった」と読むと、対策が注意喚起になって再発する。

### 9.6 指標

**「オーナー（本人）が初出しした成立条件の行数」単独は危険な指標である。** ゼロに近いほど表が先に埋まっていたことを意味する——が、**オーナーが何も言わなかっただけの状態と区別がつかない**。単独で追うと「聞かれない表」を作る方向に最適化される。次の3つと組で読む。

- 凍結後に追加された**重大条件の数**（表の完全性の代理指標。多いほど初期の表が甘い）
- 本番後に判明した**欠落の数**（最も遅く、最も重い指標）
- **成果の成否そのもの**（上の指標が良くて成果が失敗しているなら、指標のほうが間違っている）

### 9.7 出典note

GPT-5.6 SOL Pro の外部レビュー（2026-08-21）を受けた改訂。逐語は `local/state/gpt_gate_answers/gpt_gate_1_goal_command_answer_20260821.md`。**先行手法との関係**——プロジェクト管理のマイルストーンと DoD、SRE のアラート運用、軍事の Mission Command（意図を渡して手段を委ねる）、Magentic-One 等のエージェント動的計画。**部品の新規性は主張しない。** ここが提案しているのは、それらを「外部の約束 → ゴール → 成立条件 → 3台帳 → キュー → 人の判断」として、一人の実務で継続的に閉じる統合実装パターンである。

**第2回外部レビュー（2026-08-21・小作業のゴール化は不適との裁定）**を追記反映。真因診断＝実行モデル55％／台帳規律40％／ゴール粒度5％。逐語は `local/state/gpt_gate_answers/gpt_gate_3_micro_goals_answer_20260821.md`（D-2026-08-21-06）。

---

## English

**Under construction — Japanese section above is canonical; this is a working translation, kept short.**

Knowledge work reduces to **get → edit → generate** context. Tools have made *get* cheap and LLMs have made *generate* fast; **edit — fetch, confirm, reconcile, find gaps, fill gaps (by whom), prioritize, decide, put into words, route to the right recipient — is the layer that stayed empty.** A case carries three overwritable ledgers — **facts** (confirmed, sourced), **holes** (unconfirmed, tagged with who can fill them: counterpart / material / research / owner), **forks** (a pending decision, tagged with who decides: owner / counterpart / contract_change / agent) — see [`templates/context_ledgers_template.md`](../templates/context_ledgers_template.md). Context itself is tracked on four axes — **location, freshness, ownership, and destination**; context with no destination is as good as absent. Meeting support runs as four loops in plain, non-technical language: **before** (know the counterpart's current state before meeting), **during** (catch drift between assumption and their words live — contradiction / known / new), **after** (audit whether their words made it into promises/todos/decisions — captured / missed-delivery / missed-entirely / first-seen), **cross-cutting** (check new commitments against existing rulings for conflict). A human is needed only at the forks tagged `decides_by: owner`; the metric is the count of interventions the owner volunteered unprompted, driving toward zero as forks are delivered as pre-formed questions. None of this is development-specific — in sales and negotiation the "during" loop (catching assumption drift live) matters most, because there is no code-review-style redo gate once a misunderstanding ships.

**§9 — goal commands (v0.3, conditionally adopted, not settled doctrine).** **For work that is multi-step, spans sessions, and depends on outside parties, put the unit of delegation at the goal command**; a task is just an execution unit generated by an unmet condition, and **atomic, reversible, low-risk work stays a plain task**. Hand an agent a task and the scheduling between tasks stays in the human's head; hand it a goal and that scheduling becomes the agent's job. **The structure has four layers**: (1) facts/holes/forks (§2, cognition and judgment), (2) goal command (this section, the outcome contract), (3) **derived actions / work queue** (the execution unit — new in v0.3), (4) event intake and disposition record. Delegation granularity has three tiers — plain task / lightweight goal / full goal command — and **derived actions from layer 4 now sit formally at the bottom tier; small chores are not promoted into lightweight goals**, because mixing the outcome-contract type with the execution-unit type collapses the distinction between a parent goal's completion and a child chore's completion. A goal command carries four parts: (1) a dated, verifiable goal state; (2) a conditions-of-satisfaction table (row = what must be true / current state / the move that makes it true / deadline / evidence / who judges — unmet rows are the work queue, and this table is the upstream structure driving the three ledgers in §2); (3) hand-back conditions (`decides_by: owner` forks plus anything needing outward approval); and (4) **authority bounds** — permitted and forbidden means, caps on budget/time/attempts, gates on outward actions, what information may be touched, **stop conditions**, plus the goal's own version and change history. A goal without authority bounds is a blank cheque, not a delegation.

Triggers sort into three kinds by what they feed, not by how they fire: **goal_birth** (a dated commitment, a scheduled irreversible event) → mint a new goal shell; **goal_transition** (the counterpart's ball comes back, premises change, a promise is withdrawn) → find the existing goal and move its state (resume / revise / supersede / cancel) — never route these into new-goal creation; **corrective_action** (a second occurrence of the same gap) → a rule or check, not a goal. Detection belongs in the harness rather than the model's attention, but **detect-and-notify is not enough**: the harness owns the **closure** — candidate creation, auto-minting the goal shell, dedupe against existing goals, holding every candidate open until it lands in `issued` / `merged` / `rejected` (reason required) / `superseded`, and escalating candidates that sit too long. **"It fired and the model did nothing" must not count as a normal exit.** Add the inverse invariant — **absence checking**: a confirmed irreversible event with no live goal attached is itself an anomaly, because a trigger that never fired cannot be noticed from the trigger side.

**Completion invariant for event processing** (layer 3, a state-transition check, not a prompt rule): an event is not done until its derived outcome lands in one of **work dispatched / explicit hold (dated) / handed back to a person / no action (reason code)**. Detection runs three checks — event completeness, state-transition completeness, execution health — and **distinguishes zero matches from unknown coverage**: "nothing to do" and "we couldn't scan it" are different states, and collapsing the latter into the former hides the gap.

**A table's existence does not prove its conditions are complete.** Gate completeness from outside the table: per-case-type templates (for a production event: end-to-end rehearsal, connection method, item-by-item mapping, on-day roles, approvals, fallback, rollback, evidence) plus an **independent** gap review by someone other than the table's author. Row state is not a boolean — `satisfied` / `unsatisfied` / `unknown` / `blocked` / `stale` / `waived` / `not_applicable`; collapsing to two values silently rounds `unknown` into one of them and destroys the distinction.

In one anonymized case, a delivery case went two days without being turned into a goal command after its delivery date was fixed, even though the data needed for an end-to-end rehearsal had been on hand for two and a half weeks — the rehearsal, connection method, and on-day checklist all surfaced unresolved nine days out. **We cannot claim this design would have prevented it** — a goal command whose table lacks a "rehearsal" row ends the same way; it is a *plausible countermeasure*, and the case is the design's origin, not its proof. The root cause is **an unclosed state transition, not a lapse of motivation**: the fixed date was on record and simply never connected to a goal, and that non-connection was itself undetected. As a metric, "conditions-of-satisfaction rows the owner had to surface first" is **unsafe alone** — it cannot distinguish a well-prepared table from an owner who stayed silent; read it together with the number of grave conditions added after freeze, the number of gaps discovered after the event, and the actual success or failure of the work.

*Source note: revised after an external review by GPT-5.6 SOL Pro (2026-08-21). Relation to prior art: PM milestones and Definition of Done, SRE alerting, Mission Command, and agentic dynamic planning (e.g. Magentic-One). **No novelty is claimed for the parts** — the claim is the integrated pattern that closes external promise → goal → conditions → three ledgers → queue → human judgment, continuously, in a one-person practice.*
