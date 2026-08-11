# 判断カード — 承認の差し出しを認知設計する（decision cards）

`approval_queue.md` は**何を**人間に回すかの設計だった。このドキュメントは**どう見せるか**の設計。

ループの速度は生成では律速しない。承認で律速する。承認の律速は読解で、読解の律速は人間の認知だ——ならば差し出しの書式は、認知の性質に合わせて設計できるし、するべきだ。ここに書くのは実走で承認者に「判断を求めるときの提示が読みにくい」と言われて焼き直した書式と、その背後の原理5つ。どれも認知科学の教科書に載っている話で、新しさはない。**新しくない知見を、キューの書式に落とした**のがこのカードだ。

---

## 差し出しの設計ミス5つ（実走で踏んだ順）

| ミス | 何が起きるか | 原理 | 直し |
|---|---|---|---|
| **判断依頼を末尾に置く** | 承認者が全文を読んでから「で、何を聞かれてるんだ」に辿り着く | 注意は冒頭に集中する（系列位置効果） | 判断はターン・ブリーフ・キューの**冒頭**に固定。証跡・経緯は下 |
| **報告と判断依頼を混ぜる** | 依頼を見落とさないために全文をスキャンする羽目になり、常時警戒を強いる | 重要度の違う信号を同じチャネルに流すと検出が落ちる（信号検出） | FYI はカードにしない。カードは判断専用のチャネルにする |
| **現物でなく要約を見せる** | 「§3 の言い切りを弱めました」と言われても判断できず、結局本文を開きに行く | 人間は思い出すより**見比べる**ほうが速く正確（再認＞想起） | 判断対象そのものを before → after で貼る。要約で代替しない |
| **問いを開いたまま渡す** | 「どうしますか」は選択肢の構築から人間にやらせる | 承認は一瞬、拒否も一瞬。構築は遅い（デフォルト効果） | **推奨を1つ**付け、人間の仕事を「拒否権の行使」まで軽くする |
| **前提知識を仮定する** | 「先日お送りしたリンクの件です」で止まる。承認者に求められるのが判断ではなく**経緯の再構成**になり、そこで裁定が落ちる | 自分が知っていることは相手も知っていると見積もってしまう（知識の呪い）。**しかも承認者は、設計上わざと何も知らない** | 前提（いつ・誰に・何をしたか）を**2〜3行でカードに積む**。合格条件は「**この文面だけで OK/NG が出せるか**」 |

最初の4つに共通する根は1つ——**エージェントの手間を1増やすと、承認者の手間が10減る**。生成側は疲れない。疲れる側に合わせて書式を寄せる。

**5つ目だけ、根が違う。** これは疲労の非対称ではなく**文脈の非対称**だ——承認者は、疲れていて読めないのではない。**設計上、そもそも読んでいない。**

---

## 承認者は、設計上なにも知らない（前提の自己搭載）

このループが目指すのは、**人間が案件の通信と経緯を読まなくても仕事が回る**状態だ。だとすれば、承認者が経緯を知らないのは事故ではなく**仕様**である。エージェントが「あの件です」で通じると期待した瞬間、承認者には**通信を読む仕事が差し戻されている**——ループが引き受けたはずの仕事を、承認の一点で返している。

**失敗形（匿名化）。** エージェントが判断依頼にこう書いた——「先日お送りしたリンクは〜」。返ってきたのは「なんのこと?」。カードは短く、現物も推奨も無回答時も入っていた。欠けていたのは、**その1件がどの往復の続きなのか**だけだ。判断は止まり、承認者は経緯の再構成を始めた。**人間の記憶をキャッシュとして使った時点で、カードの負けである。**

**前提の欄が積むのは3つだけ**——**いつ**（前便・前回の裁定はいつか）／**誰に**（相手は誰か、どの案件か）／**何をしたか**（そのとき出したもの・返ってきたもの）。2〜3行を超えたら、それは前提ではなく経緯だ。経緯は下の証跡へ落とす。**前提は現物の代わりではない**——現物の欄はそのまま残る。

合格条件は1問だけ: **この文面だけで OK/NG が出せるか。** 出せないなら、足りないのは承認者の記憶ではなく、カードの2行だ。

前提が2〜3行で書けるのは、**いつ誰に何を約束したかがどこかに残っている**ときだけだ。その台帳を誰が持つかは [`operations.md`](operations.md) の「約束・期限・ボール」の節にある——**持つのはエージェントで、人間ではない。**

---

## カードの型

`approval_queue.md` のエントリの型に、この4行が入っている理由がここにある:

```markdown
- 前提: 承認者がこの1件を初見で読む前提で、いつ・誰に・何をしたかを2〜3行
- 現物: 判断対象そのもの（変更なら before → after。要約で代替しない）
- 推奨: エージェントならどれにするか1つ＋理由1行
- 無回答時: 期限までに裁定が無いときの既定動作（推奨で進む / 保留 / 落とす）
```

- **前提**は自己搭載のため。「あの件」「前回の」で通じることを当てにした行は、承認者の側では止まる。
- **現物**は再認のため。承認者がファイルを開きに行った時点でカードは負け。
- **推奨**は「迷い」欄と対になる——**迷いは不確かさの申告、推奨は意見の申告**。両方あると承認者は「エージェントはこう考えたが、ここが不安らしい」を数秒で再構成できる。推奨のないカードは判断の丸投げで、迷いのないカードは過信の申告だ。
- **無回答時**は、キュー全体の滞留既定値（SLA・諦めたときの挙動）の**エントリ単位の前倒し宣言**。承認者が疲れて放置しても事故らない側に倒しておく。

## 重みと枚数

- **重みは2値で見出しに付ける**: 🔴 ＝ これが決まらないと止まる ／ 🟡 ＝ 好みの裁定（無回答なら推奨で進む、と宣言済みのもの）。FYI に印は無い——FYI はそもそもカードにしない。
- **1カード＝1判断。1バッチ≦3枚。** 人間が同時に保持して比較できる塊は3〜4が上限（作業記憶）。4件以上あるなら重要度順に切って、残りは次のバッチへ回す。10枚並んだキューは「全部読んでくれ」と同義で、それは書式の敗北。

## 前提ゼロゲート — 配送前に、文脈を知らない目で1回読ませる

**書き手には、自分が省いた前提が見えない。** 書いた本人は文脈を持っているので、前提の欠落だけは**構造的に自己検出できない**——知識の呪いは「自分の知識を消して読み直す」ことができない、という形で効く。だから**書き手のセルフチェックは検収と数えない**。対外文書に別の目の初見ロールプレイを当てるのと同じ形を、**内向きのカードにも当てる**。

**手順。** 案件の文脈を一切与えない別エージェント（新しいセッションでよい）に、**カードの文面だけ**を渡す。タスクの説明も、なぜそう書いたかの診断も渡さない——渡した瞬間に文脈を与えたことになり、ゲートは自分の検査対象を汚す。血統は問わない（ここで探すのは事実の誤りではなく**前提の欠落**なので、同じ血統でも検出できる）。

**5問。**

1. **これだけで OK/NG を判断できるか。**
2. **前提知識を要求している語・参照を全部挙げよ。**（「例の件」「前回の」「あのリンク」——指示語と、既知扱いされた名詞句が主犯）
3. **判断に必要なのに書かれていない情報は何か。**
4. **判断に効かない行はどれか**（消せる行）。
5. **30秒で読み切れるか。**

指摘を潰してから届ける。落ちるのは主にこの4類型だ——**判断に効かない行**（現物より先に経緯が積まれている）・**確かめた事実の書き漏れ**（送る物が実際に開くかを試したのに、カードに書いていない＝承認者からは未確認と区別がつかない）・**タイミング未記載**（いつ出すのか・いつまでに答えが要るのか）・**内輪語**（自分のループの中でしか通じない略語や機構名）。

3と4は逆を向いている——ゲートは「足せ」とも「削れ」とも言う。**順序は削るのが先**（30秒と枚数の予算が先にあり、前提はその中に収める）。1周は数十秒で、費用は生成側にかかり、消えるのは承認者の往復だ。冒頭の非対称がここでも効いている。

## どの面に差すか

カードは**書式**であって、置き場所ではない。キューのファイル・チャットの返信・朝のブリーフ・通知——どの面で差し出しても同じ型を使う。チャットで差すなら**ターンの冒頭**（証跡や作業ログはその下）。朝のブリーフなら**判断セクションを最上段**に置き、🔴 が消えたらその日の判断は完了、と一目で分かる形にする。

## 蒸留への接続

カードへの却下・修正は、ほかの却下と同じく台帳に採取して週次で蒸留する（→ [`judgment-distillation.md`](judgment-distillation.md)）。**カードの書式そのものも却下から育てる**——「読みにくい」と言われたらそれは書式への却下で、このドキュメント自体がその蒸留の産物だ。

<!--
チャット面での最小カード例（キュー外・その場の裁定用）:

🔴 判断 1/1: 督促メールの結び、A/B どちらで送るか
前提: ◯◯社へ先週◯日に見積を送付・支払期日は今週末・先方の返信は無し。督促は今回が1通目
現:「ご対応いただけますと幸いです」→ 案:「◯日までにご返信ください」
推奨: 案。期限が本文に無く、前回この曖昧さで1週間空転したため
返し方: 「A」「B」or 直し指示。無回答なら送らず保留
-->

## English summary

The approval queue decides *what* goes to the human; decision cards decide *how it is presented*. The loop is rate-limited not by generation but by approval, and approval is rate-limited by human cognition — so the hand-off format should be engineered for it. Five field-tested mistakes and their fixes: (1) burying the ask at the bottom — pin the decision at the *top*, evidence below; (2) mixing FYI with decisions — cards are a decision-only channel; (3) showing summaries instead of the artifact — paste the actual before → after, because recognition beats recall; (4) handing over open questions — attach exactly one recommendation, so the human's job shrinks to exercising a veto; (5) **assuming shared context** — "about the link I sent the other day" stops the approver dead, because what you are asking of them is no longer a judgment but a reconstruction of the history.

The first four share one root — one unit of agent effort saves ten units of approver effort, and only one side of that loop gets tired. **The fifth has a different root: not an asymmetry of fatigue but of context.** The point of this loop is that the human does not have to read the correspondence, so an approver who does not know the history is not an accident, it is the specification. Ask them to remember and you have handed the reading back at the one point the loop was supposed to cover. So every card **carries its own premise**: two or three lines of *when · to whom · what was done*, ahead of the artifact. More than three lines is history, not premise, and history belongs below with the evidence. The pass condition is a single question — **can this text alone produce an OK or a NO?** If it cannot, what is missing is not the approver's memory, it is two lines of the card. Writing those two lines presupposes that somebody is tracking what was promised to whom and when: that ledger belongs to the agent, not the human — see [`operations.md`](operations.md).

And because a writer cannot see the premises they omitted — the curse of knowledge is precisely the inability to re-read yourself without your own knowledge — **the author's self-check does not count as review.** Before delivery, hand the card text *alone* (no task description, no diagnosis of your own) to an agent with zero context on the matter, and ask five questions: can you rule on this alone; list every phrase that assumes prior knowledge; what is missing that a ruling needs; which lines do not bear on the decision; does it read in thirty seconds. Four kinds of defect fall out most often — lines that do not bear on the decision, a check you actually ran but did not state (indistinguishable from an unverified claim on the reader's side), missing timing, and in-house jargon. Cut before you add: the thirty-second budget comes first.

Each card also declares its no-answer default (proceed / hold / drop), carries a two-level weight in the heading (🔴 blocking / 🟡 preference), and batches are capped at three cards — working memory holds about three or four items, and a queue of ten cards is just "please read everything" in disguise. Rejections of a card feed the same weekly distillation as everything else — this document itself was distilled from the feedback "your asks are hard to read."
