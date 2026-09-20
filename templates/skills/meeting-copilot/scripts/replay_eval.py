#!/usr/bin/env python3
"""replay_eval.py — 終わった会議の逐語を流し直して、判定層を採点する。

会議は1日1回しか来ない。閾値を当日の勘で決めると、外したことに気づくのは
次の会議の最中になる。だから**過去の逐語を時系列で再生**して、発話ごとに
判定層を叩き、答えを ``decisions.jsonl`` に全件残す。人が正解を付けた分だけ
的中率・再現率・校正・遅延・費用が出る。

    # ルール判定だけで最後まで通す（鍵は要りません）
    python3 replay_eval.py --transcript <逐語.jsonl> --meeting <会議フォルダ> \\
        --backend rules

    # 小型 LLM 単独で（Jev と並べて的中率を見るとき）
    python3 replay_eval.py --transcript <逐語.jsonl> --meeting <会議フォルダ> \\
        --backend llm --labels labels.csv

    # 外の判定器で（鍵は環境変数。落ちた発話は鎖の次へ退避して続きます）
    export AI_GATEWAY_API_KEY=...        # 変数の名前は decisions.yaml の key_env
    python3 replay_eval.py --transcript <逐語.jsonl> --meeting <会議フォルダ> \\
        --backend jev --labels labels.csv

    # 何を外へ送るのかだけ見る（1件も送りません）
    python3 replay_eval.py --transcript <逐語.jsonl> --meeting <会議フォルダ> \\
        --backend jev --dry-run

    # レート制限のある枠で、正解を付けた発話だけを間隔をあけて判定する
    python3 replay_eval.py --transcript <逐語.jsonl> --meeting <会議フォルダ> \\
        --backend jev --ids labelled_ids.txt --pace 6 --retry-on-429

逐語 ``transcript.jsonl`` は1行1発話 ``{"ts":..., "speaker": "host"|"guest",
"text": ...}``。**発話の番号は1始まりの行番号**で、これが正解表の鍵になります。

正解表 ``labels.csv`` は3列::

    utterance_id,q,gold
    142,q1_step,s3
    142,q8_commitment,yes

``gold`` に書くのは鍵（``s3`` ``none`` ``yes`` ``no`` ``closing``）です。
鍵と見出しの対応は ``--dry-run`` が先頭に出します。

無料枠には**レート制限**があります（2026-09-20 実測: 最初の32発話は連続で通り、
以後はおよそ6秒に1回＝10回/分。2,077発話のうち通ったのは320で、残り1,754は 429 で
ルールへ退避した）。全部を流すのではなく、**正解を付けた発話だけ** `--ids` で拾い、
`--pace` で間隔をあけるのが現実的です。`--retry-on-429` は混雑のときだけ1回待って
撃ち直します——🔴 **会議中は使いません**（待つぶんカードが遅れるので、会議では
待たずにルールへ退避するのが正しい）。

🔴 遅延の数字は「この機体からこの経路で」の実測です。別の回線・別の時間帯では
   変わります。p95 を1回の再生で決め打ちにしないこと。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import decision_engine as de  # noqa: E402

BUCKETS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01))
YES = {"yes", "y", "true", "1", "はい", "○"}


def load_transcript(path) -> list:
    """逐語を古い順に。**行番号がそのまま発話の番号**（正解表の鍵）。"""
    rows = []
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise SystemExit(f"[replay] --transcript {path} が見つかりません。")
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        text = str(d.get("text") or "").strip()
        if not text:
            continue
        rows.append({"utterance_id": i, "ts": str(d.get("ts") or ""),
                     "speaker": "host" if d.get("speaker") == "host" else "guest",
                     "text": text})
    if not rows:
        raise SystemExit(f"[replay] {p} に発話が1本もありません。")
    return rows


def load_ids(path) -> set:
    """判定する発話の番号（1行1つ・``#`` 以降は注記）。空なら全部。

    間引くのは呼び出し回数を減らすため。**窓の文脈は逐語全体から取る**ので、
    「300発話だけ判定する」と「300発話しかない逐語を流す」は別物になる。
    """
    if not path:
        return set()
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise SystemExit(f"[replay] --ids {path} が見つかりません。")
    out = set()
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.split("#", 1)[0].strip().rstrip(",")
        if s.isdigit():
            out.add(int(s))
    if not out:
        raise SystemExit(f"[replay] --ids {path} に発話番号が1つもありません。")
    return out


def load_labels(path) -> dict:
    """``{(発話番号, 問いid): 正解}``。見出し行は読み飛ばす。"""
    out: dict = {}
    if not path:
        return out
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise SystemExit(f"[replay] --labels {path} が見つかりません。")
    with p.open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            uid, q, gold = row[0].strip(), row[1].strip(), row[2].strip()
            if not uid.isdigit():
                continue          # 見出し行・空行
            out[(int(uid), q)] = gold
    return out


def pct(values, q: float) -> float:
    """素朴な百分位（順位で取る）。件数が少ないときに補間で嘘をつかないため。"""
    if not values:
        return 0.0
    xs = sorted(values)
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


class Tally:
    """問いごとの成績と、全体の遅延・費用。"""

    def __init__(self):
        self.answered: dict = {}
        self.correct: dict = {}
        self.labeled: dict = {}
        self.not_asked: dict = {}         # 正解はあるが、その発話では聞いていない問い
        self.noul_gold_yes: dict = {}
        self.noul_hit: dict = {}          # {(qid, 閾値): 件数}
        self.calib: dict = {}             # {(qid, 帯): [件数, 正解数]}
        self.latency: list = []
        self.backends: dict = {}
        self.in_tok = 0
        self.out_tok = 0

    def add(self, uid: int, answers: de.Answers, latency_ms: float, labels: dict,
            asked=()):
        """1発話ぶんを足す。``asked`` はその発話で実際に聞いた問いの id。

        🔴 聞いていない問いに正解が付いていたら、**不正解ではなく「対象外」**。
        q4/q8 は進行役の発話にしか聞かないので、相手の発話の正解行は分母に
        入れてはいけない。以前は黙って捨てていた——数字は正しかったが、
        「300件に正解を付けたのに196件しか使われていない」ことが画面に出ず、
        使われなかった104件が見えなかった。
        """
        asked = set(asked or answers.by_id)
        for (luid, qid), _gold in labels.items():
            if luid == uid and qid not in asked:
                self.not_asked[qid] = self.not_asked.get(qid, 0) + 1
        self._add(uid, answers, latency_ms, labels)

    def _add(self, uid: int, answers: de.Answers, latency_ms: float, labels: dict):
        self.backends[answers.backend or "-"] = self.backends.get(answers.backend or "-", 0) + 1
        if latency_ms > 0:
            self.latency.append(latency_ms)
        u = answers.usage or {}
        self.in_tok += int(u.get("input_tokens") or 0)
        self.out_tok += int(u.get("output_tokens") or 0)
        for qid, a in answers.by_id.items():
            self.answered[qid] = self.answered.get(qid, 0) + 1
            gold = labels.get((uid, qid))
            if gold is None:
                continue
            self.labeled[qid] = self.labeled.get(qid, 0) + 1
            if a.qtype == "noul":
                want_yes = gold.lower() in YES
                ok = (a.value == "yes") == want_yes
                if want_yes:
                    self.noul_gold_yes[qid] = self.noul_gold_yes.get(qid, 0) + 1
                    for th in (0.5, 0.8):
                        if a.p_yes >= th:
                            k = (qid, th)
                            self.noul_hit[k] = self.noul_hit.get(k, 0) + 1
            else:
                ok = a.value == gold
            if ok:
                self.correct[qid] = self.correct.get(qid, 0) + 1
            for lo, hi in BUCKETS:
                if lo <= a.confidence < hi:
                    cell = self.calib.setdefault((qid, (lo, hi)), [0, 0])
                    cell[0] += 1
                    cell[1] += 1 if ok else 0
                    break

    # -- 出力 ---------------------------------------------------------------
    def report(self, bundle: de.Bundle, n_utt: int, out_path) -> str:
        L = []
        L.append("")
        L.append("═══ 再生の結果 ═══")
        L.append(f"発話 {n_utt} 本 / 記録 {out_path}")
        L.append("担当: " + " ".join(f"{k}={v}" for k, v in sorted(self.backends.items())))
        L.append("")
        L.append("── 問いごと ──")
        L.append(f"{'問い':<18}{'答えた':>7}{'正解付き':>9}{'対象外':>7}{'的中率':>9}  再現率(noul)")
        for qid in sorted(set(self.answered) | set(self.not_asked)):
            n, lab = self.answered.get(qid, 0), self.labeled.get(qid, 0)
            na = self.not_asked.get(qid, 0)
            acc = f"{self.correct.get(qid, 0) / lab:.1%}" if lab else "—"
            rec = ""
            gy = self.noul_gold_yes.get(qid, 0)
            if gy:
                rec = "  ".join(
                    f"@{th}: {self.noul_hit.get((qid, th), 0) / gy:.1%}" for th in (0.5, 0.8))
                rec += f" (正解「はい」{gy}件)"
            L.append(f"{qid:<18}{n:>7}{lab:>9}{na:>7}{acc:>9}  {rec}")
        if any(self.not_asked.values()):
            L.append("  ※ 「対象外」= 正解は付いているが、その発話では聞いていない問い"
                     "（q4/q8 は進行役の発話にしか聞かない）。分母には入れていません")
        if not any(self.labeled.values()):
            L.append("  ※ --labels を渡すと的中率・再現率・校正が出ます"
                     "（列: utterance_id,q,gold）")
        if self.calib:
            L.append("")
            L.append("── 確信度ごとの的中率（校正の簡易確認・数字どおりに当たっていれば右肩上がり） ──")
            for qid in sorted({q for q, _ in self.calib}):
                cells = []
                for lo, hi in BUCKETS:
                    c = self.calib.get((qid, (lo, hi)))
                    cells.append(f"{lo:.1f}-{min(hi, 1.0):.1f}: "
                                 + (f"{c[1] / c[0]:.0%}({c[0]})" if c else "—"))
                L.append(f"  {qid:<16}" + "  ".join(cells))
        L.append("")
        L.append("── 遅延（この機体・この経路の実測。回線と時間帯で変わります） ──")
        if self.latency:
            L.append(f"  p50 {pct(self.latency, 0.5):.0f} ms / "
                     f"p95 {pct(self.latency, 0.95):.0f} ms / "
                     f"最大 {max(self.latency):.0f} ms / {len(self.latency)} 回")
        else:
            L.append("  計測なし")
        L.append("")
        L.append("── 費用 ──")
        L.append(f"  入力 {self.in_tok:,} トークン / 出力 {self.out_tok:,} トークン")
        price = bundle.pricing
        if price.input_per_mtok or price.output_per_mtok:
            cost = (self.in_tok / 1e6) * price.input_per_mtok \
                + (self.out_tok / 1e6) * price.output_per_mtok
            L.append(f"  概算 {cost:.4f} {price.currency}"
                     f"（単価 入力 {price.input_per_mtok}/Mtok・"
                     f"出力 {price.output_per_mtok}/Mtok・decisions.yaml の pricing）")
        else:
            L.append("  単価が未設定なので費用は出しません"
                     "（decisions.yaml の pricing に自分の契約単価を書いてください）")
        return "\n".join(L)


def show_dry_run(bundle, meeting, masker, rows, limit: int) -> None:
    """送る物だけを見せる。1件も送らない。"""
    print("═══ --dry-run: 送る物（1件も送信しません） ═══")
    print(f"退避の鎖: {bundle.chain_label}")
    for label, s in (("jev", bundle.jev), ("llm", bundle.llm)):
        has_key = bool(s.key_env and os.environ.get(s.key_env))
        print(f"  {label}: {s.endpoint if s.base_url else '(未設定)'}"
              f" / model={s.model or '(未設定)'}"
              f" / 鍵の環境変数={s.key_env or '(未設定)'}"
              f" / 鍵は{'あり' if has_key else 'なし'}"
              f" / {s.timeout_sec}秒")
    print("  ※ 下に出るのは jev の送信形です。llm へは同じ問いを言葉にして送ります")
    print(f"窓: 直近 {bundle.window} 発話 / 最大 {bundle.window_chars} 文字")
    print(f"名簿: {len(masker.pairs)} 件の綴りを役名へ置換")
    print("")
    print("── 鍵 → 見出し（labels.csv の gold にはこの鍵を書きます） ──")
    for qid, m in de.label_map(bundle, meeting).items():
        if m:
            print(f"  {qid}: " + " / ".join(f"{k}={v}"[:48] for k, v in m.items()))
        else:
            print(f"  {qid}: （はい/いいえ → gold は yes か no）")
    shown = 0
    for i in range(len(rows)):
        win = de.window_of(rows[:i + 1], bundle.window, bundle.window_chars)
        speaker = win[-1]["speaker"]
        state = de.build_state(win, masker)
        questions = de.build_questions(bundle, meeting, speaker, masker)
        if not questions:
            continue
        print("")
        print(f"── 発話 #{rows[i]['utterance_id']}（{speaker}）に送る内容 ──")
        print(json.dumps({"model": bundle.jev.model, "state": state,
                          "questions": questions}, ensure_ascii=False, indent=2))
        shown += 1
        if shown >= limit:
            break


def main() -> None:
    ap = argparse.ArgumentParser(
        description="過去の逐語を再生して判定層を採点する（送信は --backend jev のときだけ）")
    ap.add_argument("--transcript", required=True, help="逐語 transcript.jsonl")
    ap.add_argument("--meeting", required=True, help="会議フォルダ（候補と名簿の出どころ）")
    ap.add_argument("--backend", default="rules", choices=("rules", "jev", "llm"),
                    help="どこから退避の鎖を始めるか。既定 rules（鍵不要・外へ出ない）。"
                         "llm を選ぶと小型 LLM 単独の成績を Jev と並べて測れる")
    ap.add_argument("--decisions", default="", help="問いの束（既定: 会議フォルダ→同梱の例）")
    ap.add_argument("--llm-model", default="",
                    help="小型 LLM のモデルを差し替えて測る（例: 別ベンダの軽い版）。"
                         "先頭の llm 段がこのモデルになり、後ろの llm 段は外れます")
    ap.add_argument("--labels", default="", help="正解表 csv（utterance_id,q,gold）")
    ap.add_argument("--out", default="", help="記録の書き出し先（既定 ./replay_out/decisions.jsonl）")
    ap.add_argument("--limit", type=int, default=0, help="先頭から何発話だけ流すか（0=全部）")
    ap.add_argument("--ids", default="",
                    help="判定する発話を絞る（utterance_id を1行1つ書いたファイル）。"
                         "窓の文脈は逐語全体から取るので、間引いても文脈は欠けない")
    ap.add_argument("--pace", type=float, default=0.0,
                    help="呼び出しの間隔(秒)。既定 0。無料枠のレート制限を避けるとき用")
    ap.add_argument("--retry-on-429", action="store_true",
                    help="混雑(429/503)のときは退避せず --pace ぶん待って1回だけ撃ち直す"
                         "（既定 off。🔴 会議中は使わない——待つぶんカードが遅れる）")
    ap.add_argument("--dry-run", action="store_true", help="送る内容を表示するだけ")
    ap.add_argument("--append", action="store_true", help="既存の記録に追記する（既定は作り直し）")
    ap.add_argument("--allow-no-roster", action="store_true",
                    help="名簿が無いまま外へ送る（既定は止まる）")
    a = ap.parse_args()

    bundle = de.load_bundle(de.resolve_bundle_path(a.meeting, a.decisions))
    meeting = de.load_meeting_data(a.meeting, bundle.privacy)
    masker = de.Masker(meeting.roster, bundle.privacy.host_alias, bundle.privacy.guest_alias)
    rows = load_transcript(a.transcript)
    if a.limit > 0:
        rows = rows[:a.limit]

    if a.dry_run:
        show_dry_run(bundle, meeting, masker, rows, a.limit if a.limit > 0 else 3)
        return

    # 🔴 外へ送るのに名簿の**ファイルが無い**ときは止まる。
    # 「roster.txt を作り忘れた」は取り返しのつく手違いだが、送ってしまえば
    # 取り返しがつかない。黙って素通しせず、作るか、明示的に押し切るかを選ばせる。
    #
    # 見るのは中身ではなく**ファイルの有無**。meeting.json の相手の呼び方は
    # 自動で名簿に入る（load_meeting_data）が、それは書き忘れの保険であって、
    # 「出席者を数え上げた」ことにはならない。中身で判定すると、保険が効いた
    # ぶんだけこの関門が黙って開く。
    roster_path = pathlib.Path(a.meeting).expanduser() / bundle.privacy.roster
    # 🔴 rules 以外はどれも外へ出る。jev だけを見張ると、llm を足した日に穴が開く。
    if a.backend != "rules" and not roster_path.exists() and not a.allow_no_roster:
        raise SystemExit(
            f"[replay] 名簿 {roster_path} がありません。\n"
            f"         このまま送ると、発話に出てくる名前が平文で外へ出ます"
            f"（いま伏せられるのは meeting.json に書いてある呼び方 {len(meeting.roster)} 件だけ）。\n"
            f"         対処: そのファイルに1行1名で書く\n"
            f"         （名前が出ないと確かめたうえで進めるなら --allow-no-roster）\n"
            f"         送る中身は --dry-run で先に確かめられます。")

    labels = load_labels(a.labels)
    ids = load_ids(a.ids)
    if a.retry_on_429 and not a.pace:
        raise SystemExit("[replay] --retry-on-429 は --pace <秒> と一緒に使ってください"
                         "（待つ長さが 0 では撃ち直しても同じ結果になります）。")
    engine = de.make_engine(a.backend, bundle, meeting,
                            retry_busy_sec=a.pace if a.retry_on_429 else 0.0,
                            llm_model=a.llm_model)
    out_path = pathlib.Path(a.out).expanduser() if a.out \
        else pathlib.Path.cwd() / "replay_out" / "decisions.jsonl"
    if out_path.exists() and not a.append:
        out_path.unlink()
    log = de.DecisionLog(out_path)
    tally = Tally()

    todo = [r for r in rows if not ids or r["utterance_id"] in ids]
    print(f"[replay] {len(rows)} 発話中 {len(todo)} 本を判定 / backend={a.backend}"
          f"（鎖: {bundle.chain_label}） "
          f"/ 問い{len(bundle.questions)}本 / 段{len(meeting.steps)}・"
          f"即答表{len(meeting.quick_facts)}・名簿{len(meeting.roster)}"
          + (f" / 間隔{a.pace}秒" if a.pace else "")
          + ("（混雑したら待って1回撃ち直す）" if a.retry_on_429 else ""))
    if ids:
        missing = sorted(ids - {r["utterance_id"] for r in rows})
        if missing:
            print(f"  ⚠ --ids のうち {len(missing)} 件は逐語に無い"
                  f"（例: {missing[:5]}）", flush=True)
    done, last_call = 0, 0.0
    for i, r in enumerate(rows):
        # 窓は**逐語全体**から作る。間引いても、その発話の直前の文脈は欠けない。
        win = de.window_of(rows[:i + 1], bundle.window, bundle.window_chars)
        if ids and r["utterance_id"] not in ids:
            continue
        if a.pace and last_call:
            wait = a.pace - (time.monotonic() - last_call)
            if wait > 0:
                time.sleep(wait)
        last_call = time.monotonic()
        state, questions, answers, ms = de.evaluate_utterance(
            engine, bundle, meeting, masker, win)
        if not questions:
            continue
        log.write(utterance_id=r["utterance_id"], ts=r["ts"], speaker=r["speaker"],
                  state=state, questions=questions, answers=answers, latency_ms=ms)
        tally.add(r["utterance_id"], answers, ms, labels, asked=questions)
        done += 1
        if a.backend != "rules" and done % 50 == 0:
            print(f"  … {done}/{len(todo)}", flush=True)

    print(tally.report(bundle, done, out_path))


if __name__ == "__main__":
    main()
