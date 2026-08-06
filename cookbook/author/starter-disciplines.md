# starter-disciplines — 実走で焼けた規律のスターターセット（選んで持ち帰る）

> **これは展開されないファイル。** `setup.sh` はこれをあなたの作業ディレクトリにコピーしない。
> ここは**読んで選ぶメニュー**であって、そのまま置いて使う雛形ではない。
> 収録は、作者が自分の実走ループで**却下・事故から焼いた**規律のうち、案件も職業も環境も落として残ったものだけ。

---

## 使い方の規律（先に読む）

**このリストは全部入れるものではない。自分が踏んだ穴のものだけ入れろ。**

踏んでいない規律は、あなたの環境ではまだ雑音だ。規律を積みすぎたエージェント指示ファイルは、守られなくなる——だからこのキットは L1（価値判断モデル）に **本文160行・原則32個**という予算を敷いている（理由は README §9「設計の考え方」の「なぜ160行で切るのか」）。**借り物の原則は、自分で焼いた原則と同じ枠を食う。** まとめて貼れば、あなた自身の判断が入る場所がその数だけ減る。

だから順序はこうだ——**まず穴を踏む。踏んだら、ここに戻ってくる。**

### ここに載せる線引き

**ここにあるのは「AIとの協働の物理」だけだ**——職業も業種も問わず、AIに仕事を任せる人間なら誰でも同じ形で踏む穴の規律に限る。**あなたの職業の規律**（顧客への出し方・見積・その業界の作法）は、技術的に単体で効くものであっても**ここには無い**。それはあなたの却下からしか焼けないもので、置き場所は `judgment/judgment_model.md`——**あなたの L1 のほうだ。**

### 可搬性ラベル（各規律に必ず1つ付いている）

規律はかいつまんで取り入れても、うまくいくものといかないものがある。その差はここで読み分ける。

| ラベル | 意味 | 持ち帰り方 |
|---|---|---|
| **［単体で効く］** | 前提機構なしでどの環境でも効く。多くは lint / hook まで落とせる | そのまま貼ってよい。**機械化の形**が書いてあるならそちらを優先 |
| **［機構前提］** | **requires** に書いた機構が無いと空回りする | 前提を先に立てる。前提なしのつまみ食いは、文言だけ増えて何も変わらない |
| **［型だけ持ち帰れ］** | 型は移植できるが、**中身はあなたが自分の却下から焼くもの**（taste の規律） | ここに載っている中身は**作者の環境の例**であって、あなたの正解ではない |

### 貼るときの作法

- **貼り先は各規律に書いてある**（L1 の原則 / エージェント指示ファイル / `verifiers.md`）。判断規範でないもの（手順・置き場所）を L1 に入れない——L1 の本文は**不変の判断規範だけ**という規約がある。
- **L1 へ貼るときは検証マーク `△`（仮・承認者に要確認）を付ける。** 借り物はまだあなたの実発話に裏付けられていない。
  - あなたの台帳が**裏付けた**日、出典タグを自分の `[C:日付]` / `[D:D-...]` に**書き換える**（`△` → `✔`）。
  - あなたの台帳が**反証した**日、**消す**。借り物より、あなたの1件の却下のほうが強い。
- **新しい出典タグの種類を発明しない**（`[C:]` / `[D:]` の2種だけが L1 の規約。増やすと蒸留の lint と参照側が壊れる）。

---

## すでにキットに入っている規律（ここには再掲しない）

つまみ食いの前に、**基礎はもう `setup.sh` が置いている**。ここを二重に貼らないこと。

- **戻せるものは自動／戻せないものは承認**（＝マンデートの軸） → `templates/agent_instructions.md` 中核規律1・`templates/judgment_model.md` P1
- **Done is a claim, not a proof（現物で確かめてから完了と言う）** → 同 中核規律4・P2
- **確認していない断定を断定の形で書くな**（否定・帰属・因果・数量・評価／危ない出所4つ） → `templates/verifiers.md` (A)
- **否定は射程を先に書く**（①どこを ②どこまで見たか） → 同 (A)
- **サブエージェントの報告は検収してから配送する**（射程・引用検収・並列は隔離） → `templates/agent_instructions.md` 中核規律7

---

## A. 差し出しと報告

### A1. An ask is a deliverable — shape it for the reader.

**［単体で効く］**
**貼り先**: エージェント指示ファイル（承認キューを使うならその型にも）

エージェントが人間に**質問・承認依頼を出すときは、読む側の形に整形してから差し出す**。固定の4点——①**冒頭に置く**（末尾に埋めない）②**現物を貼る**（「§3の言い切りを弱めました」でなく before → after そのもの）③**推奨を1つ付ける**（開いた問いを投げない）④**無回答時の既定動作を宣言する**。**1件1判断・1バッチ3件まで。**

> 焼けた出自: 承認者に「判断を求めるときの提示が読みにくい」と言われた。ループの速度は生成では律速せず**承認で律速する**。**生成する側は疲れないが、承認する側は疲れる**——エージェントの手間を1増やすと承認者の手間が10減る、という非対称がここにある。

**機械化**: 差し出しテンプレートを4枠必須にし、欠けた枠があるなら送らない。
※ この4点の背後の原理（系列位置効果・信号検出・再認＞想起・デフォルト効果）は [`../docs/decision-cards.md`](../docs/decision-cards.md)。ここは現物だけ。

### A2. Report the board, not the event.

**［機構前提］** requires: 追記型のタスク台帳＋1画面の盤面（`ssot/tasks.md` / `system_map.md`）
**貼り先**: エージェント指示ファイル

まとまった報告のたびに4区分を添える——①**承認者の判断が要るもの**（何を決めれば何が動くかまで書く）②**走行中**（何を待っているか）③**終わったもの**④**手つかず**。**落ちるのは常に④**なので、④を数えられる台帳が無いとこの規律は成立しない。

> 焼けた出自: 長い仕事が並列で走るほど、承認者からは「何が終わって何が詰まっているか」が見えなくなる。単発の結果だけを報告し続けて、承認者を失明させた。

### A3. Snapshots rot; diffs don't.

**［機構前提］** requires: 追記型の台帳（差分を計算する土台）
**貼り先**: エージェント指示ファイル

**定時に配る「全体像」は、届く前に腐っている**——承認者が最初の1手を打った瞬間に嘘になるからだ。盤面は**作業の区切りで会話に出す**。定時便が運ぶのは**差分と期限だけ**（留守中に落ちてきたもの／今日と明日の期限／壊れた機構／留守中に終わったもの）。**全部空なら黙る。**

> 焼けた出自: 毎朝の全体像ブリーフは、受け取った直後の作業で陳腐化して読まれなくなった。同じループで生き残っていたものを数えたら、**全部が追記型**（判断台帳・承認キュー・区切りごとの報告）で、腐って死んだものは**全部スナップショット**だった。

**機械化**: 定時ジョブは、全セクションが空なら**通知せずに終了**する（「異常なし」を送らない）。

### A4. The file is the archive; the conversation is the delivery.

**［型だけ持ち帰れ］**
**貼り先**: エージェント指示ファイル

長い文書を渡して「読んでおいて」は**配送ではない**。ファイルは書庫（正本・記録・素材）で、承認者の頭に運ぶ形式は会話のほうだ。運ぶときは**1ターン1論点**、「想定 → 実際 → ひとこと → 判断はこれ」の順。承認者が既に断片的に知っている対象なら、**先に相手の理解を吐き出させて、ズレている箱だけ**潰す（説明は上書きでなく修理）。

> 焼けた出自: 同じ内容を、長文のドキュメントで渡したときは頭に入らず、一問一答で運んだときは入った。承認者の言葉で「ファイルを渡されても全然頭に入らない」。

**型だけ持ち帰る理由**: 何問で運ぶか・どこから始めるかは相手の型に依存する。**上の細かい順序は作者の承認者の形であって、あなたの承認者の形ではない。**

### A5. Don't build a dashboard; deliver the decision.

**［単体で効く］**
**貼り先**: `verifiers.md` (B) ——**該当行は同梱されていないので新規行として足す**

成果物は、**相手がすでに開いているチャネル**にだけ置く（通知の push／会話の中／タップ1回で開く URL）。「エディタでファイルを開いてもらう」導線は死ぬ。**置き場所を増やすたびに、読まれない確率が上がる。**

> 焼けた出自: きれいに整えた盤面ファイルが、そもそも開かれなかった。同じ中身を通知と会話に流した途端に動いた。差は中身ではなく面だった。

**機械化**: 成果物を出す前に「これは相手が今日すでに開く面か」を1問。No なら、届く面へ転記するまでが完了条件。

### A6. Report a search by the shelves you swept.

**［単体で効く］**
**貼り先**: `verifiers.md` (B) ——**該当行は同梱されていないので新規行として足す**

調査・リサーチの報告は、**冒頭に「掃いた棚のリスト」を置く**（媒体×ソース×どこまで）。**掃かなかった棚も「未掃」と名指す。**「網羅した」と書くのは禁止——書けるのは「この棚をここまで掃いた」だけだ。競合・市場のような**動く対象を一度きり調べたときは、「◯月◯日時点のスナップショット」と明記**する（継続監視が要るなら定点便を提案する）。

> 焼けた出自: 競合調査が1つの棚（SNS 検索）だけで終わり、別の棚（イベント／動画コミュニティ）の最前線を丸ごと落とした。**依頼した側から網羅性は監査できない**——中身を全部知っていなければ結論は検品できないからだ。**棚のリストなら10秒で穴を刺せる。**

**機械化**: 報告の第1ブロックが棚リスト（未掃を含む）でなければ出さない、を出荷条件にする。
※ 一度きりを定点の便に変えるときの設計は [`../docs/fixed-point-sweep.md`](../docs/fixed-point-sweep.md)。

---

## B. 仕事の割り振り

### B1. Forks go to dialogue; recipes go to one shot.

**［単体で効く］**
**貼り先**: エージェント指示ファイル

**分かれ道がある仕事**（仕様・設計・方針）は、承認者との対話で1個ずつ潰す＝これが「要件の凍結」のやり方。**レシピが決まった仕事**（実装・文書化・調査）は、凍結後に一発で委譲する。**成果物は、また対話で検収する。**

> 焼けた出自: 対話で詰めた仕様は、承認者の反問で強くなった（事前のブリーフには書けない論点が出た）。同じ日に**対話を飛ばして一発に出した成果物は重心を外し、作り直しになった**。順序の差だけで結果が割れた。

※ 何を「分かれ道」と数えるかの線引きはあなたの環境次第——ただし線が動いても、**分かれ道を一発委譲に流すと壊れる**という向きは変わらない。

### B2. The orchestrator designs and inspects; execution is delegated.

**［機構前提］** requires: サブエージェント（あるいは別セッション）へ委譲できる手段
**貼り先**: エージェント指示ファイル

指揮する側の**文脈が希少資源**だ。指揮側が自分でやってよいのは、設計・委譲先の選定・承認者との対話・**検収**、そして1回の検索で終わる確認まで。編集・調査・生成の実作業は、サイズに関わらず委譲する。

> 焼けた出自: 指揮側が「これくらいなら」と自分で手を動かし、**検収に使うはずだった文脈を実作業で使い切った**。安いはずの作業が、いちばん高い枠を食っていた。

### B3. Deliverables go to persistent storage, never to scratch.

**［単体で効く］**
**貼り先**: `verifiers.md` (B) ——**該当行は同梱されていないので新規行として足す**（A5 と同じ行にまとめてよい）

相手に渡すもの・後で使うものを、**揮発領域（一時ディレクトリ・スクラッチパッド）に書くな**。案件フォルダなど永続領域に書く。

> 焼けた出自: 打ち合わせ資料一式がスクラッチパッドに書かれ、領域ごと消えた。セッションログから復元できたのは僥倖であって、設計ではなかった。

**機械化**: 書き込みパスの lint——成果物タイプの出力先が一時ディレクトリなら拒否する。

---

## C. 検算と第二の目

### C1. Measure what's measurable — don't summon a second model for what a search or a test settles.

**［単体で効く］**
**貼り先**: L1 の原則（`judgment/judgment_model.md`）

手元の一次情報で測れること（検索・テスト・突合）に、別モデルの意見を呼ぶな。**呼んだ時点で、測れたはずの事実が意見になる。**

> 焼けた出自: 「別モデルのほうが良い指摘をした」と結論しかけた比較を分解したら、**勝敗を決めた2点はどちらも1回の検索で出る事実**だった。差はモデルの血統ではなく手続きだった。

**機械化**: 第二の目を呼ぶ前に1問——「この論点は、手元のコマンド1回で決着するか」。Yes なら叩く。

### C2. Second-opinion hygiene: don't hand over your diagnosis, fix your answer first, keep the loser with its reason.

**［単体で効く］**
**貼り先**: エージェント指示ファイル

別の目に見てもらうときの手順を固定する——①**自分の診断を渡すな**（渡すのは問題・現物・制約だけ）②**自分の案は、相手の回答を見る前に固定して出す**（後出しで寄せない）③**採らなかった案も、捨てた理由ごと残す**。

> 焼けた出自: 自分の診断を一緒に渡した比較は、相手が同じ結論に寄って何も検出しなかった。勝った案だけを残した記録は、後から読むと「制作秘話」になっていて、次の判断に使えなかった。

**機械化**: 依頼テンプレートを「問題・現物・制約」の3枠に固定し、診断欄を持たせない。

### C3. If you wrote "I'll do X," the next action is X.

**［単体で効く］**
**貼り先**: エージェント指示ファイル

「〜しておきます」「あとで直します」と書いたら、**直後の操作がそれ**であること。書いた時点で予定になり、予定は落ちる。すぐやらないなら、書くのは宣言ではなく**タスク台帳への1件**。

> 焼けた出自: 報告文の中でだけ実行された「やっておきます」が複数回あった。承認者から見ると完了に見え、実際には何も起きていない——**偽緑の、自分で自分に対する版**。

**機械化**: 出力中の意思表明（`〜しておく/後で/次に`）を検出し、各ヒットに**直後の実操作**か**台帳の1件**が対応しているかを報告前に確認。

---

## 増やし方

このファイル自体も却下から育つ。**足す条件は3つ**——

1. **実際の却下・事故から焼けたこと。** 理屈だけで正しい規律は入れない。
2. **職業を落としても命題が残ること。** 「AIとの協働の物理」ならここ、「あなたの職業の作法」ならあなたの `judgment/judgment_model.md`。技術的に単体で効くことは、ここに載せる理由にならない。
3. **キット自身の審査を通ること**——**「この1本を消したら、エージェントは間違えるか」。** No なら足さない。

<!--
1本足すときのひな型:

### 見出し（English proposition・grep で引ける固定表現）

**［単体で効く／機構前提／型だけ持ち帰れ］** requires: ＜機構前提のときだけ＞
**貼り先**: L1 の原則 / エージェント指示ファイル / verifiers.md (A) or (B)n

＜命題の補足・2〜3行＞

> 焼けた出自: ＜どの却下・事故から。案件名・人名・職業固有の文脈は落とす＞

**機械化**: ＜単体で効くものだけ。lint / hook / 1問チェックの形で＞
-->

---

## 取り入れたあとに

**ここから持ち帰った規律が自分の環境で動いているかは、[`../scripts/discipline_scan.py`](../scripts/discipline_scan.py) で監査できる**（A 群を監査可能な形に書いたカタログの実例が [`discipline_catalog.example.yaml`](discipline_catalog.example.yaml)、設計思想は [`../docs/discipline-audit.md`](../docs/discipline-audit.md)）。つまみ食いの当たり外れは、ラベルではなくあなたのログが決める。

---

## English summary

A **menu, not a template** — `setup.sh` deliberately does not scaffold this file. It collects disciplines the author burned in a live instance of this loop, stripped of client, profession, and environment until only the proposition was left.

**The rule for using it: don't take all of them. Take the ones whose hole you have already fallen into.** A discipline you haven't been burned by is still noise in your environment, and borrowed principles consume the same scarce budget (≤160 lines / ≤32 principles) as the ones you earn — paste them all and you have that many fewer slots for your own judgment. Fall in the hole first, then come back here.

**What qualifies: the physics of working with an AI, and nothing else** — holes that anyone delegating work to an agent falls into, whatever their trade. Disciplines belonging to *your profession* (how to pitch a client, how to price, your industry's etiquette) are absent even when they'd work standalone. Those can only be burned from your own rejections, and their home is your own `judgment/judgment_model.md`.

Every entry carries a **portability label**, because skimming disciplines off someone else's list works for some and fails for others, and the difference is structural: **[works standalone]** — no prerequisite, and where possible written down to a lint or hook; **[needs a mechanism]** — a stated `requires`, without which the rule just adds words and changes nothing; **[take the shape, not the content]** — taste disciplines, where the shape transfers but the content is yours to burn; what's printed is the author's environment, not your answer.

Each entry also names its **paste target** (L1 judgment model / agent instructions file / `verifiers.md`) and the **burn it came from**. Paste into L1 with the `△` mark (provisional, pending the approver's confirmation): rewrite the source tag to your own `[C:]`/`[D:]` the day your journal confirms it, delete it the day your journal contradicts it. Your one rejection outranks any borrowed principle.

The five foundational disciplines — reversibility as the mandate axis, done-is-a-claim, no unverified assertions, scope-before-negation, inspect a delegate's report before forwarding it — are **already shipped** by `setup.sh` and are pointed to rather than repeated here. The ones in this file are what those don't cover: **the hand-off and reporting** (an ask is a deliverable, shaped for the reader; report the board, not the event; diffs over snapshots; the conversation is the delivery and the file is the archive; deliver the decision, not a dashboard; report a search by the shelves you swept), **splitting the work** (forks to dialogue, recipes to one shot; the orchestrator designs and inspects; deliverables never land in scratch), and **checking** (measure what's measurable before summoning a second model; second-opinion hygiene; if you wrote "I'll do X," the next action is X).

Whether the ones you took are doing anything in *your* environment is answerable only from your own logs: [`../scripts/discipline_scan.py`](../scripts/discipline_scan.py) audits them (section A written up as a working catalog in [`discipline_catalog.example.yaml`](discipline_catalog.example.yaml); the design note is [`../docs/discipline-audit.md`](../docs/discipline-audit.md)).
