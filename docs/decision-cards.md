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
| **前提知識を仮定する** | 「先日お送りしたリンクの件です」で止まる。承認者に求められるのが判断ではなく**経緯の再構成**になり、そこで裁定が落ちる | 自分が知っていることは相手も知っていると見積もってしまう（知識の呪い）。**しかも承認者は、設計上その経緯を読んでいない** | 前提（いつ・誰に・何をしたか）を**2〜3行でカードに積む**。合格条件は「**この文面だけで OK/NG が出せるか**」 |

最初の4つに共通する根は1つ——**エージェントの手間を1増やすと、承認者の手間が10減る**。生成側は疲れない。疲れる側に合わせて書式を寄せる。

**5つ目だけ、根が違う。** これは疲労の非対称ではなく**文脈の非対称**だ——承認者は、疲れていて読めないのではない。**設計上、そもそも読んでいない。**

---

## 承認者は経緯を読んでいない（前提の自己搭載）

このループが目指すのは、**人間が案件の通信と経緯を読まなくても仕事が回る**状態だ。だとすれば、承認者が経緯を追っていないのは事故ではなく**仕様**である。エージェントが「あの件です」で通じると期待した瞬間、承認者には**通信を読む仕事が差し戻されている**——ループが引き受けたはずの仕事を、承認の一点で返している。

**失敗形（匿名化）。** エージェントが判断依頼にこう書いた——「先日お送りしたリンクは〜」。返ってきたのは「なんのこと?」。カードは短く、現物も推奨も無回答時も入っていた。欠けていたのは、**その1件がどの往復の続きなのか**だけだ。判断は止まり、承認者は経緯の再構成を始めた。**人間の記憶をキャッシュとして使った時点で、カードの負けである。**

**前提の欄が積むのは3つだけ**——**いつ**（前便・前回の裁定はいつか）／**誰に**（相手は誰か、どの案件か）／**何をしたか**（そのとき出したもの・返ってきたもの）。2〜3行を超えたら、それは前提ではなく経緯だ。経緯はカードの下（根拠・証跡の欄）へ落とす。**前提は現物の代わりではない**——現物の欄はそのまま残る。

合格条件は1問だけ: **この文面だけで OK/NG が出せるか。** 出せないなら、足りないのは承認者の記憶ではなく、カードの2〜3行だ。

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

**書き手には、自分が省いた前提が見えない。** 書いた本人は文脈を持っているので、前提の欠落は**書き手のセルフチェックでは構造的に取りこぼす**——知識の呪いは「自分の知識を消して読み直す」ことができない、という形で効く。だから**書き手のセルフチェックは検収と数えない**。対外文書に別の目の初見ロールプレイを当てるのと同じ形を、**内向きのカードにも当てる**。

**手順。** 案件の文脈を一切与えない別エージェント（新しいセッションでよい）に、**カードの文面だけ**を渡す。タスクの説明も、なぜそう書いたかの診断も渡さない——渡した瞬間に文脈を与えたことになり、ゲートは自分の検査対象を汚す。血統は問わない（ここで探すのは事実の誤りではなく**前提の欠落**なので、同じ血統でも検出できる）。

### 検査観点の拡張 — 人間の認知特性への接地

前提ゼロゲートの検査は「書き手が省いた前提の検出」に加えて、**読み手の認知限界**への適合を検査する。根拠は次の3つの実証知見に置く。

- **読み手は画面上の文章の2〜3割しか読まない**（Nielsen Norman Group のアイトラッキング実測、Nielsen 2008）。冒頭で答えが取れない文面は、内容が正しくても読まれずに捨てられる
- **ワーキングメモリは同時に約4チャンクしか保持できない**（Cowan 2001。Miller 1956 の 7±2 の改訂）。読み手に4つを超える「未回収の要素」を持たせる文は、理解される前に崩壊する
- **構成の悪さはそれ自体が認知負荷**（Sweller の認知負荷理論）。内容の難しさと別に、構成由来の負荷は書き手側で全て削れる

### 検査観点（10問）

1. **直答**: 1文目が相手の質問の述語への直接の答え（Yes/No/事実）か。相手の具体的な状況に当てはめた答えか（一般論だけ返して翻訳を相手にやらせていないか）。**依頼された内容そのものが実施されたと分かるか**（近い別の対応で完了報告にすり替えていないか）
2. **冒頭集中**（逆ピラミッド）: 結論と相手のアクションが文面の前半3割までに出ているか。各段落の1文目がその段落の主題か（Kieras 1978）
3. **完結性**: この文面だけで相手は次の行動（クローズ・返信・判断）ができるか。判断に必要な情報の欠落はないか
4. **前提ゼロ**: 前提知識を要求する語・指示語・既知扱いの名詞句・内輪語はないか
5. **既知→新規**（given-new contract）: 新情報が相手の既知（相手の発言・対象文書の記載）に接続して出ているか。唐突な新主張はないか（Clark & Haviland 1977）
6. **認知負荷**: 読み手が保持すべき未回収要素（番号の対応・括弧・後で説明される語）が4つを超えていないか（Cowan 2001）。入れ子構文・文中への長い挿入はないか（Gibson 1998）。**結論より先に必要な理由が、結論の後ろの括弧に押し込まれていないか**
7. **一文一義**: 接続の連鎖（「〜が、〜ので、〜して」が3つ以上）で1文に複数の主張が詰まっていないか（文化審議会「公用文作成の考え方」2022）
8. **冗長**: 削れる行・同じ内容の言い換え重複はないか。並列の列挙が地の文のままになっていないか（箇条書きにすべき）。30秒で読み切れるか
9. **時制**: 「〜しました」が反映済みの報告か、これからやる提案かが一意か
10. **クローズ分離**: 閉じてよい範囲と、まだ判断待ち・確認中の事項が文で分離されているか（混ざると相手はクローズしてよいか判断できず、往復が1回増える）

判断カードでは、観点3の「次の行動」が OK/NG の裁定にあたる——上の合格条件「この文面だけで OK/NG が出せるか」そのものだ。

指摘を潰してから届ける。**このゲートが拾うのは、たとえばこの4類型だ**:

- **判断に効かない行** — 現物より先に経緯が積まれている。
- **確かめた事実の書き漏れ** — 送る物が実際に開くかを試したのに、カードに書いていない（**承認者の側では、未確認と区別がつかない**）。
- **タイミング未記載** — いつ出すのか・いつまでに答えが要るのか。
- **内輪語** — 自分のループの中でしか通じない略語や機構名。

観点3と観点8は逆を向いている——ゲートは「足せ」とも「削れ」とも言う。**直すときは、削るほうが先だ**（30秒と枚数の予算が先にあり、前提はその中に収める）。費用は生成側にかかり、消えるのは承認者の往復だ——冒頭の非対称が、ここでも効いている。

### 運用で見つかった系統的な穴（実測）

初回のバッチ運用で不合格になった文面は、ほぼ次の3パターンに収束した。個別の表現の問題ではなく**書き手の構造的な盲点**なので、検査側で明示的に狙う。

1. **時制の曖昧さ** — 「直します/追記済み」が反映済みの報告なのか提案なのか、読み手が確定できない（観点9）
2. **クローズ範囲と未決事項の混載** — 「解決してよい」と「まだ確認中」が同じ段落に同居し、相手が動けない（観点10）
3. **依頼のすり替え** — 依頼された内容の近くにある「別の対応」を実施して完了報告する。書き手は対応した気になっているため、セルフチェックでは構造的に検出できない（観点1）

### 出典

- Nielsen, J. (2008). How Little Do Users Read? / Nielsen Norman Group eye-tracking studies
- Cowan, N. (2001). The magical number 4 in short-term memory. *Behavioral and Brain Sciences*
- Miller, G. A. (1956). The magical number seven, plus or minus two. *Psychological Review*
- Sweller, J. (1988). Cognitive load during problem solving. *Cognitive Science*
- Clark, H. H., & Haviland, S. E. (1977). Comprehension and the given-new contract
- Gibson, E. (1998). Linguistic complexity: locality of syntactic dependencies. *Cognition*
- Kieras, D. E. (1978). Good and bad structure in simple paragraphs. *Journal of Verbal Learning and Verbal Behavior*
- 文化審議会 (2022). 公用文作成の考え方

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

The first four share one root — one unit of agent effort saves ten units of approver effort, and only one side of that loop gets tired. **The fifth has a different root: not an asymmetry of fatigue but of context.** The point of this loop is that the human does not have to read the correspondence, so an approver who has not followed the thread is not an accident, it is the specification. Ask them to remember and you have handed the reading back at the one point the loop was supposed to cover. So every card **carries its own premise**: two or three lines of *when · to whom · what was done*, ahead of the artifact. More than three lines is history, not premise, and history belongs below with the evidence. The pass condition is a single question — **can this text alone produce an OK or a NO?** If it cannot, what is missing is not the approver's memory, it is two or three lines of the card. Writing them presupposes that somebody is tracking what was promised to whom and when: that ledger belongs to the agent, not the human — see [`operations.md`](operations.md).

And because a writer cannot see the premises they omitted — the curse of knowledge is precisely the inability to re-read yourself without your own knowledge — **the author's self-check does not count as review.** Before delivery, hand the card text *alone* (no task description, no diagnosis of your own) to an agent with zero context on the matter. The inspection covers more than omitted premises: it checks the text against the **reader's cognitive limits**, on three empirical findings — readers take in only 20–30% of the text on a screen (Nielsen Norman Group eye-tracking; Nielsen 2008), so a message that does not answer up front gets discarded unread even when it is right; working memory holds about four chunks at once (Cowan 2001, revising Miller's 7±2), so a text that makes the reader carry more than four unresolved elements collapses before it is understood; and poor structure is cognitive load in its own right (Sweller), separate from the difficulty of the content and entirely removable on the writer's side. Ten questions: (1) **direct answer** — does the first sentence directly answer the predicate of the reader's question (yes/no/fact), applied to their specific situation rather than as a generality they must translate, and does it show the requested thing itself was done, not a nearby substitute reported as complete; (2) **front-loading** (inverted pyramid) — conclusion and the reader's action within the first 30% of the text, each paragraph opening with its topic sentence (Kieras 1978); (3) **completeness** — can the reader take the next action (close, reply, rule) on this text alone, with nothing a ruling needs missing (for a decision card this is the pass condition itself: can this text alone produce an OK or a NO); (4) **zero premises** — no phrase, demonstrative, noun treated as known, or in-house shorthand that demands prior knowledge; (5) **given–new contract** — new information attached to something the reader already holds (their own words, what the document under discussion states), no claims out of nowhere (Clark & Haviland 1977); (6) **cognitive load** — no more than four unresolved elements held open (numbered cross-references, parentheses, terms explained later; Cowan 2001), no nested syntax or long mid-sentence insertions (Gibson 1998), no reason the conclusion depends on shoved into a parenthesis after it; (7) **one sentence, one claim** — no chains of three or more connectives packing several claims into one sentence (Council for Cultural Affairs, *Kōyōbun sakusei no kangaekata*, 2022); (8) **redundancy** — no deletable lines or restated content, parallel enumerations as bullets rather than prose, readable in thirty seconds; (9) **tense** — is "done" unambiguously a report of something already applied, or a proposal of what will be done; (10) **close separation** — is what may be closed kept in separate sentences from what is still pending or under confirmation, because when they mix the reader cannot tell whether to close, and the exchange grows by one round trip. Four kinds of defect are what the gate is there to catch — lines that do not bear on the decision, a check you actually ran but did not state (indistinguishable from an unverified claim on the reader's side), missing timing, and in-house jargon. And the first batch run of the gate found its failures collapsing into three systematic holes — structural blind spots of the writer, not local wording, so the inspection targets them by name: **tense ambiguity** (question 9), **closable scope mixed with open items** in the same paragraph (question 10), and **request substitution** — doing something *near* what was asked and reporting completion, which a self-check is structurally unable to detect (question 1). Sources are listed once, in the Japanese section above. Cut before you add: the thirty-second budget comes first.

Each card also declares its no-answer default (proceed / hold / drop), carries a two-level weight in the heading (🔴 blocking / 🟡 preference), and batches are capped at three cards — working memory holds about three or four items, and a queue of ten cards is just "please read everything" in disguise. Rejections of a card feed the same weekly distillation as everything else — this document itself was distilled from the feedback "your asks are hard to read."
