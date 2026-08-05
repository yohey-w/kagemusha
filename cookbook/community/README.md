# `cookbook/community/` — your own shelf, merged by machine

*English first, 日本語は下。*

> **This is the submission path.** PRs go to `cookbook/community/<your GitHub login>/`. The pre-split root `community/` is **no longer the automatic lane** — a PR into it is outside the prefix the workflow builds, so it is not lint-checked, not merged by machine, and left for a maintainer.

---

## What this directory is for

`templates/starter-disciplines.md` is a curated set: only the physics of working with an AI, only what survived having the client, the profession, and the environment stripped off, and every entry ruled on by a maintainer. That gate is deliberately narrow, and it throws away two things that are worth keeping:

- **disciplines burned in *your* environment** — your model, your stack, your team's shape — that don't generalise to everyone's loop;
- **disciplines that belong to your profession** — how you price, how you hand work to a client, what your trade's etiquette punishes. Those can only be burned from your own rejections, and the curated set has no place for them.

This shelf is where those go. One directory per person:

```text
cookbook/community/<your GitHub login>/disciplines.md
```

Nobody edits your shelf but you. Nobody's shelf is promoted into the kit by being here — if a discipline turns out to be general, it moves by a separate PR into the curated set, which a maintainer rules on.

**Living under `cookbook/` does not make this shelf more private.** `cookbook/` and the rest of the repository are the same git history. What the two-layer split *does* say about this shelf is the trust stamp: **`community/` is lint-only, `author/` is maintainer-ruled, and core decides neither.** See [`../README.md`](../README.md) for the trust table, and [`../../docs/layers.md`](../../docs/layers.md) for the boundary itself.

---

## How to place one

**Path.** `cookbook/community/<your GitHub login>/` — the directory name must be your login (case-insensitive). Files must be `*.md`, directly in that directory, at most 3 files per PR, at most 50 KB per file.

**Format.** Per discipline, three lines. Keep the shape; the machine does not check it, your reader does.

```markdown
### <the discipline, one line, in the imperative>

**Applies when**: <the condition under which this bites — model, tool, team shape, kind of work>

> Burned from: <the failure it came out of, one line>
```

**The origin line is the one that carries the weight, and the one to be careful with.** A discipline with no burn behind it is a thought, and thoughts are cheap. But write the burn *at an abstraction where the other party cannot be identified*: not "on the migration for <client>, their CTO said…", but "on a migration where the counterpart's approver changed mid-project…". Same proposition, no one recognisable. If you cannot state the failure without naming who was in it, that discipline belongs in your own judgment model, not here.

---

## Where the responsibility sits — read this twice

**Merging is automatic. There is no review protecting you.**

A PR that touches only `cookbook/community/<your login>/` and passes a mechanical format lint is approved and squash-merged by a workflow. **No human reads the content** — not before the merge, not after. The lint is a string matcher; it catches shapes, not meaning. It does not know whether your text is confidential, wrong, or someone else's to publish.

So:

- **The content is yours and the responsibility for it is yours.** By opening the PR you are publishing it, under this repository's licence, in your name.
- **It goes into git history, and that is permanent.** Not "hard to remove" — permanent in the sense that matters: the moment it merges, every clone, fork, mirror, and archive that pulls can hold a copy, and no action taken here reaches those copies. **Deleting is not un-publishing.** Post with that understood, or don't post.
- **Do not put anything here that belongs to someone else** — your employer's internal detail, a client's situation, a colleague's mistake with their name on it. The abstraction rule above is not politeness; it is the condition on which this lane can stay automatic.

### The lint (what will bounce your PR)

Mechanical, no judgment. If one hits, the workflow comments with the rule name and the line number — **never quoting the matched text**, since that comment would be public and permanent too.

| Rule | Rejected |
|---|---|
| email address | anything shaped like `name@host.tld` |
| phone number | JP-shaped and E.164-shaped numbers |
| company name | `株式会社` / `有限会社` / `合同会社` / `（株）` / `㈱` / `Inc.` / `LLC` / `Ltd` |
| money amount | amounts written with `¥`, `$`, or `円` |
| absolute path | `/home/…`, `/Users/…`, `/mnt/<drive>/…`, `C:\…` |
| parent-directory reference | `../` anywhere in the text |
| link host | any `http(s)` link outside `github.com` and `zenn.dev` |
| kit leak guard | the identifiers in `tests/forbidden_patterns.txt` |
| size / count | over 50 KB per file, over 3 files per PR |
| **path ownership** | **any changed file outside `cookbook/community/<the PR author's own login>/`** |

The last row is not a lint failure — the PR is left alone and labelled for the maintainer's adjudication lane. Nothing is rejected, nothing is closed; a human decides. (This is also what happens if you send a PR that changes both your shelf and something in the kit — split it into two PRs and the shelf half merges on its own. A PR into the pre-split root `community/` lands here too.)

---

## Removing your shelf

Open an issue with the **"Remove my community shelf"** template, naming `cookbook/community/<your login>/`. A workflow checks that your login matches the directory, then opens and merges the deletion PR. Requests for someone else's directory are closed with a note — the shelf's owner is the only one who can take it down.

During the migration window the removal workflow also accepts the pre-split form `community/<your login>/` and removes the shelf from **both** roots, so a shelf posted before the move can still be taken down by its owner.

## If you published a secret

In this order.

1. **File the removal issue** (above). It gets the file off `main`.
2. **Rotate whatever leaked.** A token, key, password, or address that was public for one minute is burned. Rotation is the only step that actually takes effect; step 1 is housekeeping. **Deleting it does not un-leak it.**
3. **History is not rewritten here.** A force-pushed rewrite would break every clone and fork of this repository, and it would not reach the copies that already exist — so this repository does not do it. For content cached on GitHub's own side (views of deleted commits, forks), the window is [GitHub Support](https://support.github.com/), who can purge it there.

---
---

# `cookbook/community/` — あなた専用の棚（マージは機械が行う）

> **ここが投稿先です。** PR は `cookbook/community/<GitHub ログイン名>/` 宛に出してください。移転前の直下 `community/` は**もう自動レーンではありません**——そこへの PR はワークフローが組み立てる接頭辞の外なので、lint も走らず、機械マージもされず、管理者の裁定に回ります。

## この置き場の趣旨

`templates/starter-disciplines.md` は選別済みのセットで、載るのは「AIとの協働の物理」だけ・案件も職業も環境も落として残った命題だけ・1本ずつ管理者が裁定したものだけです。この門は意図的に狭く、そのぶん取りこぼすものが2つあります。

- **あなたの環境で焼けた規律** — あなたのモデル・スタック・チームの形に依存していて、万人のループには一般化しないもの
- **あなたの職業の規律** — 値付け・顧客への出し方・その業界の作法。これはあなたの却下からしか焼けず、選別セットには置き場所がありません

その受け皿がこの棚です。1人1ディレクトリ。

```text
cookbook/community/<あなたの GitHub ログイン名>/disciplines.md
```

あなたの棚を編集できるのはあなただけです。ここに置いたことでキット本体に昇格することはありません——一般化すると分かった規律は、別の PR で選別セットへ移り、そちらは管理者が裁定します。

**`cookbook/` の下にあることで、この棚が「より private になる」ことはありません。** `cookbook/` もリポジトリの他の場所も、**同一の git 履歴**です。二層化がこの棚について**言っている**のは判子の違いだけ——**`community/` は lint のみ・`author/` は管理者裁定・core はそのどちらも決めない。** 信頼水準の表は [`../README.md`](../README.md)、境界そのものの宣言は [`../../docs/layers.md`](../../docs/layers.md) にあります。

---

## 置き方

**パス規約。** `cookbook/community/<GitHub ログイン名>/`——ディレクトリ名はあなたのログイン名（大文字小文字は区別しません）。ファイルはそのディレクトリ直下の `*.md`、1 PR あたり3ファイルまで、1ファイル 50 KB まで。

**書式。** 1規律につき3行。機械は検査しません。検査するのは読む人です。

```markdown
### <規律1行・命令形で>

**適用条件**: <これが効く条件——モデル・道具・チームの形・仕事の種類>

> 焼けた出自: <どの失敗から出たか・1行>
```

**重いのは出自の行で、注意が要るのも同じ行です。** 焼けた元の無い規律はただの思いつきで、思いつきは安い。ただし出自は**相手が特定できない抽象度で**書いてください——「<顧客名>の移行案件で先方のCTOが…」ではなく「移行案件で、途中から承認者が交代した…」。命題は同じで、誰も特定できません。**誰がいたかを言わずにその失敗を書けないなら、その規律はここではなく、あなた自身の価値判断モデルに置くもの**です。

---

## 責任の線引き（ここは2回読んでください）

**マージは自動です。レビューによる保護はありません。**

`cookbook/community/<あなたのログイン名>/` だけを触る PR は、形式 lint を通ればワークフローが自動承認して squash マージします。**内容は誰も読みません**——マージ前にも、マージ後にも。lint は文字列照合であって、形を見ているだけで意味は見ていません。その文章が秘密かどうか、間違っているかどうか、公開してよい立場のものかどうかを、機械は知りません。

したがって:

- **内容はあなたのもので、責任もあなたのもの**です。PR を出した時点で、あなたの名前で、このリポジトリのライセンスの下に公開したことになります。
- **git の履歴に残ります。これは恒久的です。** 「消しにくい」ではなく、効いてくる意味で恒久です——マージされた瞬間から、pull した全ての clone / fork / ミラー / アーカイブが写しを持ち得て、**こちら側のどの操作もその写しには届きません。削除は「公開の取り消し」ではない。** そう理解した上で出してください。出さない、も選択です。
- **他人のものを置かないこと**——勤務先の内部事情・顧客の状況・同僚の失敗を名指しで、は不可。上の抽象度の規約は礼儀の話ではなく、**このレーンを自動のままにしておける条件**です。

### lint（PR が弾かれる条件）

機械的で、判断は入りません。1つでも当たると、ワークフローが**ルール名と行番号だけ**をコメントします——**該当箇所の中身は引用しません**（そのコメントもまた公開・恒久だからです）。

| ルール | 弾くもの |
|---|---|
| メールアドレス | `name@host.tld` の形をしたもの |
| 電話番号 | 日本の形式・E.164 形式 |
| 法人格語 | `株式会社` / `有限会社` / `合同会社` / `（株）` / `㈱` / `Inc.` / `LLC` / `Ltd` |
| 金額 | `¥` `$` `円` を伴う数値 |
| 絶対パス | `/home/…`, `/Users/…`, `/mnt/<ドライブ>/…`, `C:\…` |
| 親ディレクトリ参照 | 本文中の `../` |
| リンク先 | `github.com` と `zenn.dev` 以外への `http(s)` リンク |
| キットの漏洩ガード | `tests/forbidden_patterns.txt` の識別子 |
| サイズ・件数 | 1ファイル 50 KB 超、1 PR 3ファイル超 |
| **パスの所有** | **`cookbook/community/<PR作者自身のログイン名>/` の外にある変更ファイルが1つでもある場合** |

最後の行だけは lint 失敗ではありません。その PR は**自動処理せず**「管理者裁定レーン」のラベルが付くだけです。却下もクローズもされず、人が判断します。（自分の棚とキット本体を同時に変更した PR もここに入ります。2つの PR に割れば、棚のほうは自動でマージされます。移転前の直下 `community/` 宛の PR もここに入ります。）

---

## 棚を削除する

**「Remove my community shelf」** テンプレートで issue を立て、`cookbook/community/<あなたのログイン名>/` を明記してください。ワークフローが起票者のログイン名とディレクトリの一致を照合し、一致した場合のみ削除 PR を自動作成してマージします。他人のディレクトリに対する依頼は定型コメントで閉じます——棚を下ろせるのは本人だけです。

移行期のあいだは、移転前の形 `community/<ログイン名>/` でも受け付け、**新旧どちらの棚も**削除します。移転前に置いた棚も、本人の手で下ろせます。

## 秘密を上げてしまったら

この順で。

1. **削除 issue を立てる**（上記）。`main` からファイルが消えます。
2. **漏れたものをローテーションする。** 1分でも公開されたトークン・鍵・パスワード・住所は、焼けたものとして扱ってください。**実際に効くのはこの手順だけ**で、1 は後片付けです。**削除しても、漏れたものは漏れた。**
3. **履歴の完全抹消はこのリポジトリでは行いません。** force push による書き換えは全ての clone と fork を壊し、しかも**既に存在する写しには届きません**。GitHub 側にキャッシュされたもの（削除済みコミットの表示・fork）については [GitHub Support](https://support.github.com/) が窓口で、そちらでのパージが可能です。
