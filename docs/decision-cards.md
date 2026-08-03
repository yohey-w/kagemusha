# 判断カード — 承認の差し出しを認知設計する（decision cards）

`approval_queue.md` は**何を**人間に回すかの設計だった。このドキュメントは**どう見せるか**の設計。

ループの速度は生成では律速しない。承認で律速する。承認の律速は読解で、読解の律速は人間の認知だ——ならば差し出しの書式は、認知の性質に合わせて設計できるし、するべきだ。ここに書くのは実走で承認者に「判断を求めるときの提示が読みにくい」と言われて焼き直した書式と、その背後の原理4つ。どれも認知科学の教科書に載っている話で、新しさはない。**新しくない知見を、キューの書式に落とした**のがこのカードだ。

---

## 差し出しの設計ミス4つ（実走で踏んだ順）

| ミス | 何が起きるか | 原理 | 直し |
|---|---|---|---|
| **判断依頼を末尾に置く** | 承認者が全文を読んでから「で、何を聞かれてるんだ」に辿り着く | 注意は冒頭に集中する（系列位置効果） | 判断はターン・ブリーフ・キューの**冒頭**に固定。証跡・経緯は下 |
| **報告と判断依頼を混ぜる** | 依頼を見落とさないために全文をスキャンする羽目になり、常時警戒を強いる | 重要度の違う信号を同じチャネルに流すと検出が落ちる（信号検出） | FYI はカードにしない。カードは判断専用のチャネルにする |
| **現物でなく要約を見せる** | 「§3 の言い切りを弱めました」と言われても判断できず、結局本文を開きに行く | 人間は思い出すより**見比べる**ほうが速く正確（再認＞想起） | 判断対象そのものを before → after で貼る。要約で代替しない |
| **問いを開いたまま渡す** | 「どうしますか」は選択肢の構築から人間にやらせる | 承認は一瞬、拒否も一瞬。構築は遅い（デフォルト効果） | **推奨を1つ**付け、人間の仕事を「拒否権の行使」まで軽くする |

4つに共通する根は1つ——**エージェントの手間を1増やすと、承認者の手間が10減る**。生成側は疲れない。疲れる側に合わせて書式を寄せる。

---

## カードの型

`approval_queue.md` のエントリの型に、この3行が入っている理由がここにある:

```markdown
- 現物: 判断対象そのもの（変更なら before → after。要約で代替しない）
- 推奨: エージェントならどれにするか1つ＋理由1行
- 無回答時: 期限までに裁定が無いときの既定動作（推奨で進む / 保留 / 落とす）
```

- **現物**は再認のため。承認者がファイルを開きに行った時点でカードは負け。
- **推奨**は「迷い」欄と対になる——**迷いは不確かさの申告、推奨は意見の申告**。両方あると承認者は「エージェントはこう考えたが、ここが不安らしい」を数秒で再構成できる。推奨のないカードは判断の丸投げで、迷いのないカードは過信の申告だ。
- **無回答時**は、キュー全体の滞留既定値（SLA・諦めたときの挙動）の**エントリ単位の前倒し宣言**。承認者が疲れて放置しても事故らない側に倒しておく。

## 重みと枚数

- **重みは2値で見出しに付ける**: 🔴 ＝ これが決まらないと止まる ／ 🟡 ＝ 好みの裁定（無回答なら推奨で進む、と宣言済みのもの）。FYI に印は無い——FYI はそもそもカードにしない。
- **1カード＝1判断。1バッチ≦3枚。** 人間が同時に保持して比較できる塊は3〜4が上限（作業記憶）。4件以上あるなら重要度順に切って、残りは次のバッチへ回す。10枚並んだキューは「全部読んでくれ」と同義で、それは書式の敗北。

## どの面に差すか

カードは**書式**であって、置き場所ではない。キューのファイル・チャットの返信・朝のブリーフ・通知——どの面で差し出しても同じ型を使う。チャットで差すなら**ターンの冒頭**（証跡や作業ログはその下）。朝のブリーフなら**判断セクションを最上段**に置き、🔴 が消えたらその日の判断は完了、と一目で分かる形にする。

## 蒸留への接続

カードへの却下・修正は、ほかの却下と同じく台帳に採取して週次で蒸留する（→ [`judgment-distillation.md`](judgment-distillation.md)）。**カードの書式そのものも却下から育てる**——「読みにくい」と言われたらそれは書式への却下で、このドキュメント自体がその蒸留の産物だ。

<!--
チャット面での最小カード例（キュー外・その場の裁定用）:

🔴 判断 1/1: 督促メールの結び、A/B どちらで送るか
現:「ご対応いただけますと幸いです」→ 案:「◯日までにご返信ください」
推奨: 案。期限が本文に無く、前回この曖昧さで1週間空転したため
返し方: 「A」「B」or 直し指示。無回答なら送らず保留
-->

## English summary

The approval queue decides *what* goes to the human; decision cards decide *how it is presented*. The loop is rate-limited not by generation but by approval, and approval is rate-limited by human cognition — so the hand-off format should be engineered for it. Four field-tested mistakes and their fixes: (1) burying the ask at the bottom — pin the decision at the *top*, evidence below; (2) mixing FYI with decisions — cards are a decision-only channel; (3) showing summaries instead of the artifact — paste the actual before → after, because recognition beats recall; (4) handing over open questions — attach exactly one recommendation, so the human's job shrinks to exercising a veto. Each card also declares its no-answer default (proceed / hold / drop), carries a two-level weight in the heading (🔴 blocking / 🟡 preference), and batches are capped at three cards — working memory holds about three or four items, and a queue of ten cards is just "please read everything" in disguise. One root principle: one unit of agent effort saves ten units of approver effort, and only one side of that loop gets tired. Rejections of a card feed the same weekly distillation as everything else — this document itself was distilled from the feedback "your asks are hard to read."
