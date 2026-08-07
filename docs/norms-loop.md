# 作業改善を複利にする——修正を生成側へ還流する（norms）

出発点は、どこの現場にもある観察1つ。**AIに書かせた成果物へ同じ直しを毎回入れているのに、初稿の質が上がらない。** 検査は速くなったのに、検査の回数は減らない。これは能力の問題ではなく、**直しの戻し先を1つ間違えている**ときに必ず起きる。このドキュメントは、その戻し先の設計だ。

言葉を3つだけ先に固定する。**生成側**＝初稿を書く工程（人でもモデルでも同じ）。**検出器**＝出来上がったものを検査する工程（チェックリスト・lint・レビュー役）。**還流**＝直した内容を、次に初稿を書く側へ届けること。

（このリポジトリには、**判断**への却下を溜めて規律へ昇格させる配管が別にある——[`judgment-distillation.md`](judgment-distillation.md)。こちらは**成果物**への直しを扱う。片方だけ読んでも成立するので、初めてなら先はこのまま読んで構わない。）

---

## 1. 制御には2つのチャンネルがある

| | **禁止**（やるな） | **品質**（こう、やれ） |
|---|---|---|
| 置ける形 | 条件文。機械が判定できる（lint・正規表現・スキーマ） | 検査員の形でしか置けない。読んで判断する誰か（人かモデル）が要る |
| かかる費用 | **一度書けば発火はタダ**。呼び忘れが起きない | **毎回かかる**。走らせるたびに読解の費用が出る |
| 増え方 | 単調に増える（戻らないラチェット） | 座標（誰の目で読むか）と正解例が育つ |
| 壊れ方 | **誤爆**。正しいものまで止め始める | **過剰適合**。どの成果物も同じ顔になる |

2つは択一ではなく両輪で、大事なのは**人間の同じ1動作——却下と一言——が、両方の蓄えを同時に増やす**ことだ。「その言い方はするな」は禁止側へ、「そこは先に現物を出せ」は品質側へ入る。制御を設計するという別作業は人間に発生しない。

## 2. 戻し先は2つあり、片方しか複利にならない

| 戻し先 | 何が起きるか | 増え方 |
|---|---|---|
| **検出器へ戻す**（検査項目・正解例を増やす） | 同じ失敗は毎回起きる。**見つけるのが速くなるだけ** | 線形——直した数だけ費用も増える |
| **生成側へ戻す**（初稿を書くときに読ませる規約にする） | **最初から起きなくなる** | 複利——次の初稿の土台が上がる |

例。「専門語を使ったら直後に日常語で言い換える」を検査項目にすると、毎回書いて、毎回指摘して、毎回直す。同じ一文を**初稿を頼むときの指示文**に入れると、次の初稿からその失敗が減りはじめる。減ったぶんだけ人間の読解が空く。これが複利の実体で、魔法は何もない。

検出器が無駄なのではない。**検出器は取りこぼしを拾う網であって、質を上げる装置ではない**——役割が違うだけだ。

## 3. 改稿の蒸留——ループの終端に1工程だけ足す

磨き終わった時点で、**確定した修正**（＝実際に直したもの。指摘されただけのものは含めない）を3つに分ける。積む先は**棚**——仕事の種類（文章・提案・調査・帳票…＝**ドメイン**）ごとに1ファイル（`ssot/norms/<ドメイン>.md`）で、棚に載る1行を**エントリ**、各エントリに付ける熟成度の札を**段**（4種類・次章）と呼ぶ。

| 分類 | 判定の質問 | 行き先 |
|---|---|---|
| **一般化できる** | 題材が変わっても同じことが言えるか | 棚へエントリを1行。段は最下段（「観測」）から |
| **この成果物限り** | この題材・この相手だから、か | どこにも積まない（成果物の中で閉じる） |
| **様子見** | 言えそうだが、他でも再現するか分からない | 置き場所は「一般化できる」と同じ。違うのは**確信度**だけなので、`?` を付けて置く |

エントリは**一文＋出典**で書く。**出典には成果物の名前を書き、同じ型の直しがまた確定するたびに、その成果物名を追記する**——次章の件数はこの出典の数そのもので、別の台帳は要らない。

3分類が要る理由は単純で、**全部を一般化すると棚が汚れ、全部を捨てると複利が回らない**から。判定は蒸留のときに1回だけやる。作業中に一般化を考えはじめると、目の前の成果物が終わらない。

## 4. 昇格階段——n=1を法則にしないための敷居

| 段（エントリに付ける札） | 上がる条件（目安） | 使われ方 |
|---|---|---|
| **観測** | 出典1件——1つの成果物で確定した直しを一般形にしたもの | 棚に載るだけ。**指示文には入れない** |
| **候補** | 出典3件——別の成果物でも**同じ型の直しがまた確定した** | 棚に載るだけ。指示文には入れない |
| **規約** | 出典8件——同上 | **ここから上だけが、初稿の指示文に入る** |
| **常設** | 指示文に入れたあと、**別の題材でも1巡目に出てこなくなった** | 常時入る |

**下の3段が数えているのは「再発」で、「防げた回数」ではない。** 理由は単純で、上位2段に上がるまでそのエントリは指示文に入っておらず、**生成側は一度もそれを読んでいない**——防げたかどうかは原理的に観測できず、観測できるのは「また出た」だけだからだ。**防止が効いたかを測るのは、指示文に入れた後**（次章の計器と、最上段の条件がそれにあたる）。

数える手間は増やさない。**件数＝そのエントリの出典欄に並んだ成果物名の数**で、蒸留のたびに1件足すか足さないかを決めるだけ。別の集計表は持たない。

**棚には4段すべてのエントリが載る。** 段は棚の出し入れの基準ではなく、各行に付ける札だ。振り分けているのは「棚に置くか」ではなく「**初稿の指示文に入れるか**」で、入るのは上の2段だけ。段の名前は好きに変えてよい——**動かせないのは名前ではなく、「入る／入らない」の境界がどこかを、棚を見た全員が一目で分かること**。

**「入れる」のは誰か。** あなたが初稿を頼むときに使う**指示文のひな型**——プロンプトのテンプレート、エージェントの指示ファイル、依頼メモ——が棚を参照して、上の2段だけを差し込む。**それを仕組みで自動化するか、毎回自分で貼るかは実装の自由**で、決まっているのは差し込む前の**選別のほう**だ。手で貼る運用でも複利は回る（回らないのは、選別せずに全部貼ったときと、何も貼らないとき）。

敷居が要るのは、**1本で効いた直しをそのまま次の初稿に強制すると、その1本の癖が全部に転写される**から。件数（3・8）はあなたの成果物の頻度で決める目安で、写して使うものではない。動かせないのは数字ではなく、**「棚に記録する段」と「初稿に効かせる段」を別々に持つ**という形のほうだ。

## 5. 複利の計器——効いているかを、数える

成果物ごとに**1巡目の確定指摘数**（初稿に対する最初の検査で、実際に直すと決まった件数）を1行ずつ記録する。

- **重ねて下がる** → 還流が効いている。生成側に届いた証拠
- **下がらない** → 検出器にしか戻っていない証拠。棚が厚くなっているのに数字が動かないなら、積む場所を間違えている

この数字には**注意が1つ**ある。「指摘が減った」は検査が甘くなっても起きる。**検査の仕様（誰の目で・何を見るか）を固定したうえでの比較でなければ意味を持たない**。緩めた検査の下で出た改善は、改善ではない。

## 6. 過剰適合のガード——棚は放っておくと負債になる

複利が成立するのは**保守がセットになっている場合だけ**だ。

- **どの成果物も同じ顔になってきたら負債**。「誰が書いても同じ説明文」は、エントリが効きすぎた姿であって、質が上がった姿ではない
- **週に1回、剪定する**。矛盾した行・誤爆する禁止・もう発火しないエントリを落とす。増える一方の棚は、いずれ読まれなくなる
- **最後の検出器はループの外に置く**。棚を育てた本人と、その棚で書いた成果物を検査する目が同じだと、過剰適合は原理的に見つからない。ループ外＝本人以外の実読・別系統のモデル・市場の反応

## 7. 置き場所——棚は道具の持ち物ではなく、家の持ち物

棚は `ssot/norms/<ドメイン>.md` に置く（`ssot/` ＝ single source of truth＝この仕事の正本を置く場所）。1ドメイン1ファイル。スキルやプロンプト——つまり**道具**の中に置かないのは、**そこに置くと他のドメインの作り手から見えなくなる**からだ（「文章の規約」を文章用スキルの中に入れると、提案書や帳票を書く側はその存在を知らない）。**道具は棚を所有せず、参照だけする。**

棚の書式と、階段・計器・ガードの凡例は [`../ssot/norms/README.md`](../ssot/norms/README.md) にある。**このリポジトリが配るのは棚と凡例だけで、エントリは1行も入っていない**——他人の現場で効いた規約は、あなたの現場では正確に間違っていることがあり、借り物の規約は、あなたが自分の却下から取り出した規約と同じ枠を食う。

## 8. 天井を正直に

複利が効くのは**「毎回同じ型の失敗」の帯域だけ**だ。何を書くか・どう構成するか・どこで勝負するかという一回性の判断は、還流しても回数が溜まらないので、階段が回らない。そこはプロセスのまま残る。

この装置が置き換えるのは判断ではなく、**判断のたびに毎回払っていた同じ説明の費用**だ。

---

## English summary

Corrections to *judgment* flow into the judgment model. This document is the other pipe: where corrections to a *deliverable* go. The symptom it addresses is common and specific — you keep making the same edits, review keeps getting faster, and the number of edits never falls. That happens when corrections are burned into the **detector** (the checklist, the reviewing pass) rather than into the **generator** (the brief the first draft is written from). Burning into the detector makes you faster at *finding* the same failure; burning into the generator makes it stop happening. The first is linear, the second compounds.

Control comes in two channels that trade off differently: **prohibitions** ("don't") are conditionals a machine can evaluate — write once, fire free, fail by false positives, and they ratchet upward; **quality norms** ("do it this way") can only be held in the shape of a reviewer — they cost something on every run, they grow a set of coordinates and worked examples, and they fail by overfitting. One human action (a rejection plus one sentence) stocks both, which is why nobody has to sit down and "design the controls."

The mechanism is four small pieces. **(1) Distil the revision** at the end of the polishing loop: sort the edits you actually made into generalisable / this-deliverable-only / not-sure-yet. **(2) A promotion ladder** — observation (1 source) → candidate (3) → norm (8) → standing (still absent from the first pass after it went into the brief). **All four rungs live on the shelf**; the rung decides only whether an entry is injected into the brief the next first draft is written from, and **only norms and above are**. Note what the lower rungs count: **recurrences, not preventions** — until an entry is promoted it was never in the brief, so the generator never read it and prevention is not observable; only "it came up again" is. The count needs no separate ledger, because it *is* the number of deliverables listed in the entry's source field. What does the injecting is whatever you brief from — a prompt template, an agent instructions file, a note you paste by hand; automating that is optional, the selection before it is not. The threshold exists so one deliverable's quirk is not transferred onto all of them (counts are a starting point, not a spec to copy). **(3) An instrument**: log the number of confirmed findings on the *first* review pass, per deliverable. Falling over time means the feedback reached the generator; flat means it only reached the detector. The number is only comparable while the review spec is held fixed — findings also fall when the review gets lazier. **(4) Overfitting guards**: if every deliverable starts to read the same way, the stock has become a liability; prune weekly, and keep the final detector *outside* the loop (a real reader, a different model lineage, the market), because a stock and a checker that grew together cannot see their own overfit.

Where it lives: `ssot/norms/<domain>.md`, one file per domain, owned by the instance rather than by any one tool — a tool holds a pointer, not the stock. **The kit ships the shelf and the legend and no entries at all**; a norm burned in someone else's shop can be exactly wrong in yours, and it eats the same slot as one you earned. Ceiling, stated honestly: this compounds only over failures of a repeating shape. One-off judgment — what to write, how to structure it — never accumulates the repetitions the ladder needs, and stays a process. What the device removes is not the judgment; it is the cost of explaining the same thing before every judgment.
