# `reference-instance/` — one filled-in loop, laid out the way it lives

*English summary at the bottom.*

core が配るのは**空の形式**だ（[`../../../docs/layers.md`](../../../docs/layers.md)）。ここにあるのは**その同じ形式を、書式と例示（プレースホルダ入り）で書き起こしたもの**を、ループが実際に置いているパスに並べたものである。**作者の実データではない**——記入内容・人名・数値は例示であり、実記録は [`../evidence/`](../evidence/) に公開方針つきで出している。

**仕様ではなく実例として読むこと。** 機構は core のもの、書き起こした中身は作者の例示。あなたのループで正しいかどうかは、[`../../README.md`](../../README.md) の3点目——**適合保証はない**——のとおり、誰も保証していない。

## いまの状態（読む前に）

このディレクトリは**複製であって、移動ではない**。複製した時点（2026-08）では `templates/` 配下の現物と1バイト単位で同一だった（コピー時に SHA-256 で全件突合）。その後 `templates/` 側は「記入内容の入っていない空の形式」へ差し替わり、改訂も続いているので、**いまは同一ではない**。記入済み版の置き場所はここだけだ。

ここにある書き方は複製時点（2026-08）のもので、キットの現行の規約と食い違う箇所がある（例: 標本の `CLAUDE.md` 中核規律4「検証器を報告前に1周」は、いまの `templates/agent_instructions.md` では「完了の線は `verifiers.md` にある」という完了条件の形になっている）。**現行の規約は `templates/` 側を正とする。**

## 配置の対応

配置は `setup.sh` が**実インスタンスへ展開する先**に合わせてある——「記入済みインスタンス」なのだから、テンプレート名ではなくインスタンスのパスで並ぶのが自然だからだ。

| 複製元（現行の `templates/`） | ここでの配置 | 根拠 |
|---|---|---|
| `agent_instructions.md` | `CLAUDE.md` | `setup.sh` の展開先（Codex なら `AGENTS.md`） |
| `approval_queue.md` | `approval_queue.md` | 同上（作業ディレクトリ直下） |
| `verifiers.md` | `verifiers.md` | 同上 |
| `system_map.md` | `system_map.md` | 同上 |
| `decisions.md` / `tasks.md` / `glossary.md` / `people.md` | `ssot/` 配下に同名 | 同上 |
| `decisions_journal.md` / `judgment_model.md` / `promotion_queue.md` | `judgment/` 配下に同名 | 同上 |
| `charter.md` | `projects/_charter_template.md` | 同上 |
| `correction_patterns.example.txt` | `judgment/correction_patterns.txt` | `setup.sh` の手順10・`config.env.example` の `DISTILL_PATTERNS_FILE` が読む実運用名 |
| `discipline_catalog.example.yaml` | `judgment/discipline_catalog.yaml` | `docs/discipline-audit.md` §1 が指定する実運用名 |
| `inbound_sweep.md` | `inbound_sweep.md`（直下） | 〔要確認〕**`setup.sh` は展開せず、キット内のどのドキュメントも実インスタンス側の置き場所を指定していない**。手順書としてその場で実行される種類のファイルなので、暫定的に作業ディレクトリ直下に置いた |

**複製していないもの**: `distill-prompt.md` と `discipline-audit-prompt.md`（モデルに渡すプロンプトであって、記入されるインスタンス側の書式ではない）、`starter-disciplines.md`（記入済みインスタンスではなく**メニュー**なので、1階層上の [`../starter-disciplines.md`](../starter-disciplines.md) にある）。

## 読み方の順番

1. `system_map.md` — 1画面の盤面。何が並んでいるかが最初に分かる
2. `approval_queue.md` と `verifiers.md` — 何が承認に回り、報告前に何が1周するか
3. `judgment/decisions_journal.md` → `judgment/judgment_model.md` — 訂正が原則に化けるまでの往復。ここが**このキットが売っている唯一の非対称な資産**の実物
4. 残り（`ssot/` `projects/`）は上の3つを支える台帳

---

## English

Core ships **empty forms** (see [`../../../docs/layers.md`](../../../docs/layers.md)). This directory holds **the same forms written out with formats and illustrative content (placeholders included)**, arranged at the paths a running loop keeps them at. **It is not the author's live data** — the entries, names, and numbers are illustrative; the real records are published, with a disclosure policy, under [`../evidence/`](../evidence/). Read it as a **worked example, not a spec** — the mechanism is core's, the written-out content is the author's illustration, and nothing here is warranted to fit your loop.

**These are copies, not moves.** At copy time (2026-08) every file was **byte-identical** to its counterpart under `templates/` (verified by SHA-256). Since then the `templates/` side has been replaced with genuinely empty forms and revised further, so **the two are no longer identical**, and this directory is the only home of the filled-in versions. The wording here is the 2026-08 wording and differs from the kit's current conventions in places (for example, the sample `CLAUDE.md` rule 4 "run the verifiers once before reporting" is now phrased in `templates/agent_instructions.md` as a completion condition: "the line for done lives in `verifiers.md`"). **For the current conventions, `templates/` is canonical.**

The layout follows **where `setup.sh` scaffolds each file into a real instance**, not the template filenames — this is an *instance*, so it is arranged like one. `correction_patterns.example.txt` and `discipline_catalog.example.yaml` appear under their live names (`judgment/correction_patterns.txt`, `judgment/discipline_catalog.yaml`) because that is what the config and the audit doc read. `inbound_sweep.md` is placed at the working-directory root **provisionally** — `setup.sh` does not scaffold it and no kit document states an instance path for it; treat that one placement as unconfirmed.

Not copied here: `distill-prompt.md` and `discipline-audit-prompt.md` (prompts handed to a model, not instance forms), and `starter-disciplines.md` (a menu, not a filled-in instance — it lives one level up).

注: 判断モデル内の原則の例示のうち2件は、作者の公開済み原則(evidence/のP0区分)と同内容の実物から採っている。顧客・案件・交渉に関わる原則は含まれない。出典タグは月粒度(T6準拠)。
