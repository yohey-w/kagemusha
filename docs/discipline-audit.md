# 規律の監査 — 取り入れた規律が、自分の環境で動いているか

規律はつまみ食いできる。**ただし、効くものと効かないものがある**（[`../cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md) の可搬性ラベル）。どちらだったかは、貼った本人のログにしか出ない。ここに置くのはそれを測る道具の設計思想で、実物は [`../scripts/discipline_scan.py`](../scripts/discipline_scan.py)（走査）と [`../templates/discipline_catalog.example.yaml`](../templates/discipline_catalog.example.yaml)（カタログ）と [`../templates/discipline-audit-prompt.md`](../templates/discipline-audit-prompt.md)（週次の判定）。

## この監査が証明するもの・しないもの

**目的は「規律が効いている証拠」を出すことではない。「破れを検出する仕組みが動いている証拠」を出すことだ。**

守れた回は数えにくく、破れた回は残る。だからこの道具が出せるのは「今週、破れを見つける網が実際に何かを捕まえた」という事実であって、規律の効果量ではない。効果の証明にすり替えた瞬間、これは自己申告の言い換えになる——**自己申告の限界を認めた上での事後検出**、が正しい位置取りだ。ログの外（口頭・別ツール・そもそも書かなかった仕事）で守った回も、この監査には映らない。

## 2つの型 — ここを混同すると数字が嘘になる

| 型 | 命じるもの | 守った状態 | 数えられるもの |
|---|---|---|---|
| **痕跡型 (trace)** | 行動（「否定を書く前に射程を書け」「書き込んだら読み戻せ」） | ログに**痕跡が残る** | 発火・破れの両方。**発火ゼロ＝死文候補**が成立する |
| **禁止型 (prohibition)** | 自制（「確認せずに断定するな」「網羅したと書くな」） | **書かなかった文**＝ログに無い | 破れだけ。**発火は観測不能** |

禁止型の発火ゼロを「守られている」とも「死文」とも読んではいけない。**何も分かっていない**、が正しい。カタログのパーサは禁止型に `fire:` を書くとエラーで落ちる——この混同はコメントでは防げないので、書式で塞いである。

## だから、監査したい規律は禁止形でなく痕跡形に書け

これがこの道具から出てくる一番実用的な帰結だ。「**確認していないことを断定するな**」は監査できない。「**断定の前に一次情報を1回叩け**」なら叩いた痕跡が残る。禁止したい振る舞いには、**それを置き換える観測可能な行動**を対にして書く（禁止はエージェント指示に残してよい。監査に載せるのは痕跡型のほう）。週次で破れが繰り返される禁止型は、**痕跡形への書き直し候補**として扱う——規律が悪いのではなく、書き方が測れない形なのだ。

## 週次の回し方（3ステップ）

1. **カタログを作る** — `templates/discipline_catalog.example.yaml` を自分のデータ側（例: `judgment/discipline_catalog.yaml`・キットの外）へコピーし、**実際に取り入れた規律だけ**残して、自分の言葉づかいで `fire:` / `breach:` を書く。パターンは意味ではなく**語彙**を狙う。広すぎるのは検品で落とせるが、狭すぎると**偽の死文**が出る（効いていた規律を消しかねない）。
2. **走査する** — `scripts/discipline_scan.py --catalog <catalog> --since 7d --out <file>`。出るのは**候補**であって判定ではない。0ファイル走査は空レポートではなくエラーになる（「証跡なし」と「全部死文」が見分けられなくなるため）。
3. **判定させる** — `templates/discipline-audit-prompt.md` に候補を添付して週次で判定。**N件は原文で支持を確認した実例の数**で、候補数の合算ではない。死文候補は痕跡型からのみ。出力は30行以内。

**死文候補を名指しするのは、削除の提案ではない。** 「この規律、飾りになっていないか」を人間が見るための列挙だ。消すか、書き直すか、環境のほうを直すかは、あなたの判断で決まる。

---

> **In English.** Disciplines can be skimmed off someone else's list, but some transfer and some don't, and only your own logs can tell you which. This is the design note for the tool that reads them. **What the audit proves is not that a discipline is working — it is that the mechanism which detects breaches is running**; compliance is cheap to claim and hard to see, so this is after-the-fact detection that admits the limits of self-report, not an effect size. Everything turns on two types: a **trace** discipline commands an action and leaves a mark, so firings are countable and zero firings is a real dead-letter signal; a **prohibition** commands restraint, so obeying it produces the sentence you never wrote — **firings are unobservable, and zero hits mean nothing**. The catalog parser rejects a `fire:` pattern on a prohibition, because that confusion is what silently turns the numbers into fiction. The practical consequence: **if you want a discipline audited, write it as a trace, not a prohibition** — pair every "never do X" with the observable action that replaces it, and audit the action; a prohibition breached week after week is a candidate to be rewritten in trace form. Run it in three steps: copy the example catalog outside the kit and cut it down to the disciplines you actually took, scan (candidates only — scanning zero files is an error, never an empty report), then judge with the prompt template, where **N is examples confirmed against the quoted text, never a sum of machine candidate counts**. Naming a dead-letter candidate is an invitation to look, not a proposal to delete.
