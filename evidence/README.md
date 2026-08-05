# evidence/ — moved to the sample shelf / 標本棚へ移転しました

> **Moved to [`../cookbook/author/evidence/`](../cookbook/author/evidence/README.md).**
> 抜粋の**現物（実ログ・台帳2件・匿名化方針・「何を証明していないか」の節）は、すべて移転先にあります**。このディレクトリに残っているのは案内だけで、**ここには証拠の現物は無い**——読む先を間違えないでください。

| 旧パス | 現行パス |
|---|---|
| `evidence/README.md` | [`../cookbook/author/evidence/README.md`](../cookbook/author/evidence/README.md) |
| `evidence/ledger_excerpt.md` | [`../cookbook/author/evidence/ledger_excerpt.md`](../cookbook/author/evidence/ledger_excerpt.md) |
| `evidence/weekly_distill_log_excerpt.txt` | [`../cookbook/author/evidence/weekly_distill_log_excerpt.txt`](../cookbook/author/evidence/weekly_distill_log_excerpt.txt) |

**なぜ動いたか。** このリポジトリは *core*（機構＝足場・スクリプト・空の書式・受入ゲート）と *cookbook*（標本＝誰かの記入済みの中身）の**二層**になりました。実走インスタンスの抜粋は「作者の中身」そのものなので、標本棚の `author/` が正しい位置です。境界の宣言は [`../docs/layers.md`](../docs/layers.md)、移動の引き当ては [`../docs/path-migrations.md`](../docs/path-migrations.md)。

**移転しても変わっていないこと**: 匿名化の水準・「何を証明していないか」の但し書き・非ゼロ終了をそのまま載せる方針。そして `.gitignore` の allowlist が**この抜粋群もリーク検査の走査対象に含める**ことも変わりません（棚は同じリポジトリ・同じ履歴です——[`../cookbook/README.md`](../cookbook/README.md)）。

---

## English

The evidence excerpts have **moved to [`cookbook/author/evidence/`](../cookbook/author/evidence/README.md)**. The artifacts themselves — the unattended weekly-distillation log, the two dated journal entries, the redaction policy, and the "what this does not prove" section — **live there, not here**; this file is a signpost only. The repository is now two layers: core ships shape, `cookbook/` holds samples, and excerpts from the author's live instance are samples. Boundary: [`../docs/layers.md`](../docs/layers.md). Old-path lookup: [`../docs/path-migrations.md`](../docs/path-migrations.md).
