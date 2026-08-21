# Context Ledgers — three ledgers per case ／ 案件がもつ3つの台帳

**EN.** Work is the operation of sharpening context until it is dense enough to act on with confidence. Break a case into three ledgers — **facts**, **holes**, **forks** — and the question "where is a human actually needed?" answers itself: only at the forks a human must decide.

**JA.** 仕事とは、コンテキストを「確実に動ける濃さ」まで詳細化する操作の連なり。案件を**事実／穴／分岐**の3台帳に割ると、「人の判断がどこで要るか」が住所つきで見える。**人の出番は、分岐のうち人が決めるものだけ。**

This is an extension of `ssot/` (**the current state, overwritable**). History stays in `judgment/decisions_journal.md` (**append-only**). The split is unchanged.
これは `ssot/`（いまの状態・上書き可）の拡張。履歴は `judgment/decisions_journal.md`（追記のみ）に残す——分離は保つ。

## Start here ／ 始め方

```sh
mkdir -p projects/<name>/ledgers
cp templates/ledger.yaml.example projects/<name>/ledgers/ledger.yaml
```

`ledger.yaml` is the single source of truth. Any `facts.md` / `holes.md` / `forks.md` are **generated views** — if you write them by hand, say so at the top of the file.
正本は `ledger.yaml` 1本。`facts.md` / `holes.md` / `forks.md` は**生成ビュー**——手書きするなら冒頭に「YAMLが正本・このMDは生成物」と明記する。

Case data lives under `projects/`, which the allowlist `.gitignore` makes structurally uncommittable. Only this template and the `.example` ship.
案件データは `projects/` 配下＝allowlist .gitignore で構造的にコミット不能。出荷するのはこのテンプレと `.example` だけ。

---

## 1. The three ledgers ／ 3台帳の定義

| Ledger | One row is | Rule |
|---|---|---|
| **facts** 事実 | one confirmed fact, with its source | **no guesses.** If you have not seen the primary source, it is a hole, not a fact |
| **holes** 穴 | one unknown, plus **who can fill it** | a hole without a filler is a wish, not a hole |
| **forks** 分岐 | one decision, plus **who decides** | a fork without options and consequences cannot be decided |

## 2. Columns ／ 各列の意味

**facts**

| field | meaning |
|---|---|
| `id` | `F-001` — prefix by kind so cross-references are unambiguous |
| `title` | the fact, in one line |
| `status` | `confirmed` |
| `kind` | counterpart's current state ／ agreed ／ our own implementation state（相手の現状／合意済み／こちらの実装状態） |
| `source` | `file:line` ／ `mail:YYYY-MM-DD` ／ `talk:HH:MM:SS` — where you saw it |
| `fresh` | the date the fact was true |

**holes**

| field | meaning |
|---|---|
| `why` | which deliverable or fork stalls without it（これが無いと何が止まるか） |
| `fills_by` | **4 values**: `counterpart` 相手／`material` 資料／`research` 調査／`owner` 本人 |
| `material` | which document, when `fills_by: material` |
| `how` | ask at the next meeting ／ send an email ／ have the team look it up |
| `due` / `priority` | `must_<meeting>` ／ `nice_<meeting>` ／ `later` |
| `blocks` | IDs of the facts/forks that stall |
| `status` | `open` ／ `filled` ／ `dropped` |

**EN.** When research comes back "not found," always record two things together: the **scope actually covered** (where you looked, how far) and the **next move to widen that scope**. A hole stays `open` as long as a next move exists — that is what keeps it detectable as workable, instead of silently read as "checked, nothing there."

**JA.** 調査の結果が「見つからない」のときは、**射程(どこをどう見たか)**と、**射程を広げる次の一手**を必ず併記する。次の一手が存在する限り穴は `open` のまま(＝着工可能として検知され続ける)。

**forks**

| field | meaning |
|---|---|
| `options` | 2–3, each with a `consequence` in money / deadline / relationship / implementation terms |
| `decides_by` | **4 values**（下の§3） |
| `recommend` + `why` | your pick and one line of reasoning — never leave the human to choose blind |
| `depends_on` | hole IDs that must be filled first |
| `status` | `open` ／ `decided`（+ `decision`） |

## 3. `decides_by` — who decides ／ 誰が決めるか

| value | when | 意味 |
|---|---|---|
| `owner` | value, promises, irreversible, taste | **人（依頼主）が決める**。ここだけが人の出番 |
| `counterpart` | the other party's domain, timing, their own operation | 相手が決める |
| `contract_change` | the answer changes a signed agreement | 契約変更が要る |
| `agent` | everything else — **set a default, act, report afterwards** | 影武者が決めて事後報告 |

**The discipline is the fourth value.** Without `agent`, every open question drifts to `owner` and the human becomes the bottleneck again. The test: *value, promise, irreversibility, taste* — if none apply, it is not the human's fork.
**規律の本体は4つ目の値。** これが無いと未決が全部 `owner` に流れ、人がまたボトルネックになる。判定は「価値・約束・不可逆・好み」——どれでもなければ人の分岐ではない。

## 4. Operating loop ／ 運用

| phase | what happens to the ledgers |
|---|---|
| **before** 準備 | refresh holes and forks, then **deliver** them — to the human (only `decides_by: owner`, one topic at a time) and to the assistant (the whole file) |
| **during** 会議 | the meeting is **the place where the counterpart fills holes and decides their forks**. Nothing else belongs on the agenda |
| **after** 会議後 | update: facts gained, holes closed, new holes opened, forks resolved |
| **audit** 監査 | re-read the counterpart's materials against the ledgers — new holes surface here, not in the meeting |

Three signals are enough for a live assistant: **⚠ contradicts a fact ／ ✔ a hole just got filled ／ ＋ a new hole**.
ライブ支援の合図は3種で足りる: **⚠ 事実と矛盾／✔ 穴が埋まった／＋ 新しい穴**。

## 5. Meeting template v0 ／ 会議設計テンプレv0 との対応

| step | ledger it moves |
|---|---|
| 1. purpose in one line ／ 目的1行 | states which holes and forks close today |
| 2. re-state what we understand ／ 現状の再提示 | **facts**, read aloud so the counterpart only has to correct |
| 3. list of unknowns ／ 不明点一覧 | **holes** with `fills_by: counterpart`, in priority order |
| 4. topics and timeboxes ／ 論点と時間箱 | one hole or fork per box; overflow goes to the parking lot |
| 5. the scope line ／ 範囲の線 | **forks** about in/out — say the line out loud |
| 6. agreement and next actions ／ 合意と次アクション | forks now `decided`; new holes get an owner and a due date |

Step 2 exists because of a specific failure: the counterpart says something they already told you, and you react with surprise. Saying it first makes that structurally impossible.
2があるのは失敗の型に対応する——相手が既に伝えたことに「えっそうなんですか」と反応する事故は、**こちらが先に述べれば構造的に起きない**。

## 6. Anti-patterns ／ アンチパターン

- Putting a guess in **facts**. Guesses belong in holes, tagged.（推測を事実台帳に入れる）
- A hole with no `fills_by`.（誰が埋めるか無しの穴）
- A fork with no `recommend`.（推しの無い分岐＝丸投げ）
- Twelve `owner` forks. Re-run the test on each; most are `agent`.（人の分岐が10件超えたら分類をやり直す）
- Hand-editing a generated view and losing it on the next render.（生成ビューを手で直す）
- A scope table with "undecided" rows that have no fork ID — assert it mechanically.（未決なのに分岐IDを持たない行）
