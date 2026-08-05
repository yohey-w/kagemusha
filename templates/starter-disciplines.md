# starter-disciplines — moved to the sample shelf / 標本棚へ移転しました

> **Moved to [`../cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md).**
> 中身（実走で焼けた規律の一覧）はすべてそちらにあります。このファイルは**旧 URL を生かしておくためだけの案内**です。

**なぜ動いたか。** このリポジトリは *core*（機構＝足場・スクリプト・**空の書式**・受入ゲート）と *cookbook*（標本＝誰かの記入済みの中身）の**二層**になりました。焼けた規律の一覧は「**誰かの中身**」なので、`templates/` ではなく標本棚に置くのが正しい位置です。境界の宣言は [`../docs/layers.md`](../docs/layers.md)、棚の判子の意味は [`../cookbook/README.md`](../cookbook/README.md)、移動の引き当ては [`../docs/path-migrations.md`](../docs/path-migrations.md)。

`setup.sh` がこのファイルを展開しないのは移転の前後で変わりません（**メニューは既定値にしない**）。

---

## 残っているのは書式だけ / the empty form

規律を1本書くときの**形**だけをここに残します。中身は入れません——**借り物の原則は、自分で焼いた原則と同じ枠を食う**からです。

```markdown
### <ID>. <English proposition — 命令形の1行・grep で引ける固定表現>

**［単体で効く／機構前提／型だけ持ち帰れ］**   ← 可搬性ラベルを1つ。機構前提なら requires: <何が要るか>
**貼り先**: <エージェント指示ファイル / 検証器 / 価値判断モデル / 憲章 …>

<規律の本文。何をするか・何をしないかを、観測できる言い方で1〜3行>

> 焼けた出自: <これが焼けた実際の却下・事故を1〜3行。ここが書けないなら、その規律はまだ規律ではない>

**機械化**: <検証器・lint・スクリプトで機械層へ落とせるならその方法。落とせないなら「落とせない」と書く>
```

門（何を載せてよいか・4軸）は移転先のファイル自身の `## 増やし方` が正本です。

---

## English

This file has **moved to [`../cookbook/author/starter-disciplines.md`](../cookbook/author/starter-disciplines.md)**; only this signpost and the empty entry form above remain, so the old path keeps resolving. The repository is now **two layers**: *core* (the repository root — mechanism, scripts, **empty forms**, the acceptance gate) and *`cookbook/`* (samples — somebody's filled-in content). A list of disciplines burned in a real loop is content, so it belongs on the shelf. Boundary: [`../docs/layers.md`](../docs/layers.md). What the shelf's stamps mean: [`../cookbook/README.md`](../cookbook/README.md). Old-path lookup: [`../docs/path-migrations.md`](../docs/path-migrations.md). As before, `setup.sh` does **not** scaffold it — a menu must not become a default.
