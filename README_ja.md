<!-- porch:start -->
# kagemusha（影武者）

<sub>🇯🇵 **日本語** · [🌐 English (canonical) → README.md](README.md)</sub>

[![ci](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml/badge.svg)](https://github.com/yohey-w/kagemusha/actions/workflows/ci.yml)

<!-- contract:identity -->
**判断の中身は配らない。形だけ配る。**

kagemusha は、**あなたが今使っている AI コーディングエージェント**（Claude Code・Codex・Cursor …）のために、**「内向きは自動／外向きは人間の承認」**と、却下理由を次の実行へ恒久規律として戻すループを、**Markdown の書式と、それを動かすスクリプト**で配るキットです。常駐エージェントでも SaaS でもなく、**あなたの判断基準は同梱しません**。

**向く人**: 不可逆な操作があり、却下理由を残せる人。／**向かない人**: 完成済みの判断基準や、チームの承認 SaaS が欲しい人。

[固定証拠 `evidence-v1.0.0`](https://github.com/yohey-w/kagemusha/tree/evidence-v1.0.0)・[10分デモ](docs/getting-started.md#10分デモ)・[導入手順](docs/getting-started.md#手順コピペ)

<!-- contract:demo -->
```bash
git clone https://github.com/yohey-w/kagemusha.git
cd kagemusha
./scripts/demo-distillation.sh   # 約10分・APIキー不要・あなたのファイルに触れない
```
<!-- porch:end -->

*節番号は薄化前の README から引き継いでいます——既存のリンクと引用が解決し続けるためで、飛んでいる番号は意図的です。中身は [`docs/`](docs/README.md) に移りました。*

## 3. これは何を解くのか（1分版）

AIに仕事を渡すと、詰まるのは2つで、どちらもモデルの能力ではありません。**取り消せない操作**と、**却下のたびに捨てられている、あなた自身の判断**です。前者は**承認キュー**が受けます——内向きの作業は自律で走り、外向きの操作はあなたの前で止まる。後者は**判断蒸留**が受けます——却下理由を残し、蒸留し、次のセッションのエージェントが読み直す。設計の全体は [`docs/design.md`](docs/design.md)。

<!-- contract:evidence -->
## 証拠と射程

**固定証拠: [`evidence-v1.0.0`](https://github.com/yohey-w/kagemusha/tree/evidence-v1.0.0)** — 定刻の週次蒸留が実際に走ったことと、訂正が恒久規律へ到達した一例を、実走インスタンスから匿名化した現物で示します。**これは n=1 の実走証拠であり、効果量も一般化可能性も主張しません。** `main` は現在の機構、タグは固定された証拠です。射程と限界: [`cookbook/author/evidence/README.md`](cookbook/author/evidence/README.md)。

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
