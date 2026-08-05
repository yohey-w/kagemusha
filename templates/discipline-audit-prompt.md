# discipline-audit-prompt — 週次「規律の監査」プロンプト雛形

> **使い方**: `scripts/discipline_scan.py` の出力（証跡候補・未判定）を添付して、下のプロンプトを
> LLM に渡す。週次蒸留を回しているなら、その手順の一節として組み込む
> （`scripts/weekly_distill.sh.example` と同じく **内向き・読み取り専用**で回すこと）。
> `<...>` は自分の環境に合わせて埋める。設計思想は [`../docs/discipline-audit.md`](../docs/discipline-audit.md)。
>
> **雛形の急所は「数の作り方」だ。** 機械の候補数をそのまま合算した数字は、規律の効きではなく
> 正規表現の当たり数を報告してしまう。下の縛りはそこを塞ぐためにある。

---

## プロンプト本体（ここから下をコピーする）

```
あなたは <この作業ループ> の週次監査を担当する。以下は直近7日のセッションログから
機械抽出した「規律の証跡候補」である。**これは候補であって判定ではない。**

この節の目的は『規律が効いている証拠』を出すことではない。
**『破れを検出する仕組みが動いている証拠』を承認者に見せること**である。
（自己申告には限界がある、と認めた上での事後検出だ。効いている証明にすり替えるな。）

規律には2つの型がある。混同するな。
- **痕跡型(trace)** = 行動を命じる規律。守るとログに痕跡が残る。
  → 発火件数のカウントと死文候補の判定は、**この型にだけ**適用する。
- **禁止型(prohibition)** = 自制を命じる規律。守った状態＝「書かなかった文」なので
  ログに存在しない。**発火は観測不能**。破れだけを報告し、
  **発火ゼロを死文と呼ぶな**（「観測不能」と明記せよ）。

手順:
1. 候補を1件ずつ**原文の断片で検品**する。断片が規律を支えていない候補は捨てる
   （誤検出を数に入れない）。発火とも破れとも読めるものは無理に分類せず〔判定不能〕へ。
2. **報告する N件／M件は、原文で支持を確認した実例の件数**とする。
   **機械の候補数を合算した数を書くな。** 候補数を併記したいときは括弧で（候補X件）と添える。
3. 破れは、ログの候補だけでなく **<判断台帳／訂正記録>** の直近7日からも拾う
   （承認者の指摘・訂正は破れの一次証拠である）。
4. **死文候補**＝今週ひとつも発火の証跡が無い**痕跡型**の規律を名指しする。
   これは削除の提案ではない——承認者が「飾りになっていないか」を見るための列挙だ。
5. 副産物として、**禁止型で破れが繰り返されている規律は「痕跡形への書き直し候補」**として挙げる
   （例: 「確認せずに断定するな」→「断定の前に一次情報を1回叩け」）。
   禁止形のままでは監査できないので、監査したい規律は痕跡形に書き直すのが正しい対処である。
6. 証跡が無いことを、証跡があることのように書かない。**仮説を発明しない**
   （このログに無い出来事を「たぶん起きた」で埋めない）。

出力（**30行以内**・超えたら例示を削る）:
- 1行目に痕跡型と禁止型の区別を1文で書く（毎週読む人の誤解を防ぐため）。
- `発火 N件（痕跡型のみ）／破れ M件／判定不能 K件`
- 各項目**1行**＋根拠の位置（日時＋セッションID先頭8桁、または台帳のID）。
- `死文候補: <痕跡型の規律idだけ>`
- `書き直し候補: <反復して破れている禁止型 → 痕跡形の案>`
- 最後に1行、**今週この監査が検出できなかったこと**（＝この仕組みの穴）を書く。

添付: 規律の証跡候補（機械抽出・未判定）
<ここに scripts/discipline_scan.py の出力を貼る>
```

---

## 出力例（形だけ・数字は架空）

```
規律の型: 痕跡型は発火が観測できる／禁止型は発火が観測不能で破れだけが見える。
発火 6件（痕跡型のみ・候補11件から検品）／破れ 2件／判定不能 1件
- A6 発火4件: 調査報告の冒頭に棚リスト（08-02 3f9ac1b2 ほか3件）
- A1 発火2件: 承認依頼に推奨と無回答時の既定（08-04 77d0e2aa ほか1件）
- A6-P 破れ1件: 「網羅した」と書いた（08-03 3f9ac1b2）
- A2 破れ1件: 承認者から盤面を聞かれた＝盤面を届けていない（台帳 D-....）
- A5 判定不能1件: 通知に流したが、相手が開いたかはログの外
死文候補: A3, A4（痕跡型で発火ゼロ。禁止型はこの行に入れない）
書き直し候補: A6-P「網羅と書くな」→「報告の第1ブロックを棚リストにせよ」（破れ3週連続）
検出できなかったこと: 会話の外（口頭・別ツール）で守った回は、この監査には映らない。
```

---

## English summary

A prompt template for the weekly discipline audit. Feed it the unjudged candidate
digest from `scripts/discipline_scan.py`.

The point of the section is **not** "proof the disciplines are working" — it is
**proof that the mechanism which detects breaches is running**. The template pins
five things that otherwise go wrong: count firings **only for trace disciplines**;
never call a prohibition with zero hits a dead letter (compliance is unobservable
by construction); **N is the number of examples confirmed against the quoted text,
never a sum of machine candidate counts** (put the candidate count in parentheses
if you want it); dead-letter candidates are drawn **only from trace disciplines**,
and naming one is a prompt for the approver to look, not a proposal to delete; a
prohibition that keeps getting breached is a candidate to be **rewritten as a
trace** ("don't assert what you haven't checked" → "hit the primary source once
before asserting"), because a prohibition cannot be audited in the form it is
written. Output is capped at 30 lines, and the last line names what this audit
could not see.
