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

---

## English

**Under construction — Japanese section above is canonical; this is a working translation, kept short.**

Knowledge work reduces to **get → edit → generate** context. Tools have made *get* cheap and LLMs have made *generate* fast; **edit — fetch, confirm, reconcile, find gaps, fill gaps (by whom), prioritize, decide, put into words, route to the right recipient — is the layer that stayed empty.** A case carries three overwritable ledgers — **facts** (confirmed, sourced), **holes** (unconfirmed, tagged with who can fill them: counterpart / material / research / owner), **forks** (a pending decision, tagged with who decides: owner / counterpart / contract_change / agent) — see [`templates/context_ledgers_template.md`](../templates/context_ledgers_template.md). Context itself is tracked on four axes — **location, freshness, ownership, and destination**; context with no destination is as good as absent. Meeting support runs as four loops in plain, non-technical language: **before** (know the counterpart's current state before meeting), **during** (catch drift between assumption and their words live — contradiction / known / new), **after** (audit whether their words made it into promises/todos/decisions — captured / missed-delivery / missed-entirely / first-seen), **cross-cutting** (check new commitments against existing rulings for conflict). A human is needed only at the forks tagged `decides_by: owner`; the metric is the count of interventions the owner volunteered unprompted, driving toward zero as forks are delivered as pre-formed questions. None of this is development-specific — in sales and negotiation the "during" loop (catching assumption drift live) matters most, because there is no code-review-style redo gate once a misunderstanding ships.
