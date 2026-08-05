# 蒸留便 — 毎日ただで採り、材料が貯まった日だけ焚く

訂正はチャットの途中で起きて、片付けられて、流れていく。**採るのは毎日・蒸留は材料が貯まった日だけ**、が蒸留便の全部だ。実物は [`../scripts/correction_scan.py`](../scripts/correction_scan.py)（採取・LLM不使用）・[`../scripts/distill.sh`](../scripts/distill.sh)（発火判定）・[`../templates/distill-prompt.md`](../templates/distill-prompt.md)（蒸留プロンプト）・[`../templates/promotion_queue.md`](../templates/promotion_queue.md)（審査キュー）。

既存の [`judgment-distillation.md`](judgment-distillation.md) の週次蒸留とは**別レーン**だ。あちらは時刻トリガーで**価値判断モデル**を改訂する重い便。こちらは**訂正だけを材料に、規律の昇格候補を差し出すだけ**の軽い便で、正本には一切触らない。片方だけ回してもよい。

## 回し方

```cron
7  6 * * *  /path/to/kagemusha/scripts/correction_scan.py --patterns ~/judgment/correction_patterns.txt \
              --material ~/judgment/correction_material.md --state ~/judgment/distill_state.json --since 1d
23 6 * * *  /path/to/kagemusha/scripts/distill.sh
```

1. **採取（毎日・無料）**: 直近1日のセッションログから訂正らしき発話を拾い、素材ファイルへ追記。**同一セッション・同一時間帯の言い換えは1件に束ねてから数える**——4回言い直したことは4人の証人ではない。パターンは同梱の[メニュー](../templates/correction_patterns.example.txt)から**自分の言い回しだけ**を選んで使う（スクリプトに既定語彙は無い。無いのが正しい）。
2. **発火判定（毎日・ほぼ無料）**: 未蒸留の**件数**が閾値（既定5）以上なら蒸留する。未満なら黙ってスキップ（ログ1行）。**7日発火しなければ、1件でも溜まっていれば焚く**（貯まらない人でも最低週1・ただし0件の週は焚かない）。
3. **蒸留（たまに）**: 候補を**規律案1行＋8欄**の審査書式（型・**原文**・適用範囲・例外・確信度・反例・貼り先・鮮度）で審査キューへ追記するだけ。既存原則と矛盾する候補は解決せず「競合・保留」枠へ回す。
4. **審査（人間・週5分）**: キューを読み、**採るものだけ**自分の指示ファイルへ写す。写した行為が昇格だ。

## なぜ毎日固定で焚かないか

材料が薄い日にモデルを焚くと、**モデルは「材料が足りません」とは言わない**。薄い2件から2件ぶんの原則をひねり出す。閾値はコスト節約ではなく、**出力を正直に保つための仕掛け**だ。

## なぜ自動で書き込まないか

移動には関門は要らない。**昇格には要る**。この便が自分で規律を書けるなら、それは誰もレビューしていない規律が以後の全実行を——自分自身を含めて——統べるということだ。だからスクリプトが書いてよいのは審査キューだけで、指示ファイル・原則・正本は書かせない。台帳は**追記**（訂正は事実）・規律は**上書き**（規範に2版あるのは曖昧なだけ）。

## 3状態を潰さない

FIRED / SKIPPED / **FAILED** を混ぜない（[`fixed-point-sweep.md`](fixed-point-sweep.md)）。**未蒸留カウンタが進むのは成功時だけ**——失敗を「蒸留済み」に丸めると証拠が床に落ち、盤面だけ健康に見える。終了コード0も証明にはならないので、キューが実際に増えたかを**読み戻して**から進める。

## 昇格した規律も永久ではない

規律には鮮度の日付を付ける。[`discipline-audit.md`](discipline-audit.md) の週次走査が、**痕跡型で今週一度も発火しなかった規律**を死文候補として名指しする。そこで「残す／発火する形に書き直す／退役」を決める。退役は削除でなく**休眠**——ID は残し、状況が戻れば復帰しうる。**採る側の門（この便）と、捨てる側の門（死文監査）を両方持ってはじめて規律の在庫が回る。**

## 素材の扱い

素材ファイルはローカル完結で、引用は採取時点で**上限文字数まで切り詰めてある**（ログの索引であって複製ではない）。機外に出るのは蒸留の1回のLLM呼び出しだけ——**その1回に何が乗るかは、素材ファイルを開けば全部見える**。git 管理外に置くこと（キットの allowlist `.gitignore` は既定でそうなっている）。

---

> **In English.** Harvest daily for free; distill only when there is material. `correction_scan.py` walks yesterday's session logs for turns that look like you overruling the agent, groups them into **events** (session + time bucket — four rephrasings of one point are one event, never four witnesses), and appends them to a local, truncated material file. `distill.sh` runs daily too and almost always does nothing: below the threshold it stays silent, and it fires only on enough material — or on a 7-day fallback when at least one event is waiting, so a light week still gets distilled and an empty one never does. **Firing on a fixed schedule is the failure mode**: a model asked to distill principles from two thin corrections will not say "not enough", it will produce two thin principles. The distillation writes **only** to a promotion queue, in a review format of one rule line plus eight fields (type / verbatim evidence / scope / exception / confidence / counter-evidence / destination / freshness), routing anything that collides with your existing principles to a separate *held* section rather than resolving it. It may never touch your instructions file: moving text needs no gate, **promoting a correction into a rule does, and the gate is you**. Three states are kept apart — FIRED / SKIPPED / FAILED — and the pending counter advances only after a successful run whose write has been **read back**, so a failure leaves the material pending instead of dropping it while the board still looks healthy. Promoted rules carry a freshness date and are handed to the dead-letter side of [`discipline-audit.md`](discipline-audit.md): an intake gate without a retirement gate just fills the file up.
