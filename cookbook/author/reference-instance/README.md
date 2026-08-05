# `reference-instance/` — one filled-in loop, laid out the way it lives

*English summary at the bottom.*

core が配るのは**空の形式**だ（[`../../../docs/layers.md`](../../../docs/layers.md)）。ここにあるのは**その同じ形式に、作者の実走インスタンスの中身が入ったもの**を、ループが実際に置いているパスに並べたものである。

**仕様ではなく実例として読むこと。** 機構は core のもの、中身は作者のもの。あなたのループで正しいかどうかは、[`../../README.md`](../../README.md) の3点目——**適合保証はない**——のとおり、誰も保証していない。

## いまの状態（読む前に）

このディレクトリは**複製であって、移動ではない**。ここのファイルは `templates/` 配下の**現物と1バイト単位で同一**（コピー時に SHA-256 で全件突合済み）で、旧パスのファイルは1バイトも変えていない。

`templates/` 側を「記入内容の入っていない空の形式」へ差し替えるのは**後続の段**で、その差し替えが起きた時点で、ここが**記入済み版の唯一の置き場所**になる。差し替え前のいまは、**同じ内容が2箇所にある**。移動が確定したら [`../../../docs/path-migrations.md`](../../../docs/path-migrations.md) に1行入る。

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

Core ships **empty forms** (see [`../../../docs/layers.md`](../../../docs/layers.md)). This directory holds **the same forms with the author's live-instance content in them**, arranged at the paths a running loop keeps them at. Read it as a **worked example, not a spec** — the mechanism is core's, the content is one person's, and nothing here is warranted to fit your loop.

**Right now these are copies, not moves.** Every file is **byte-identical** to its counterpart under `templates/` (verified by SHA-256 at copy time), and the originals are untouched. Replacing the `templates/` side with genuinely empty forms is a **later step**; when it happens, this becomes the only home of the filled-in versions and a row appears in [`../../../docs/path-migrations.md`](../../../docs/path-migrations.md). Until then the same content exists in two places.

The layout follows **where `setup.sh` scaffolds each file into a real instance**, not the template filenames — this is an *instance*, so it is arranged like one. `correction_patterns.example.txt` and `discipline_catalog.example.yaml` appear under their live names (`judgment/correction_patterns.txt`, `judgment/discipline_catalog.yaml`) because that is what the config and the audit doc read. `inbound_sweep.md` is placed at the working-directory root **provisionally** — `setup.sh` does not scaffold it and no kit document states an instance path for it; treat that one placement as unconfirmed.

Not copied here: `distill-prompt.md` and `discipline-audit-prompt.md` (prompts handed to a model, not instance forms), and `starter-disciplines.md` (a menu, not a filled-in instance — it lives one level up).
