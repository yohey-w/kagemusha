#!/usr/bin/env python3
"""meetlive 前提監視カード

**呼ばれ待ちをやめる層**。番人(copilot.py)は呼ばれるまで動かないので、
「相手の発話が、こちらの設計上の前提を覆した/裏づけた/新しい穴を開けた」場面を
まるごと取りこぼしていた。ここは相手の発話1件ごとに、事前に確定している事実台帳と
突き合わせて自発的に撃つ。

出力3値:
  矛盾⚠ — 前提と食い違う              → カード kind=premise_warn (赤・目立たせる)
  既知✔ — 相手が既に言ったこと        → カード kind=premise_ok
  新しい穴＋ — 台帳に無い新情報       → カード kind=premise_new
  なし   — 該当なし                    → カードは出さない

判定ログは全件 <state>/premise_watch.jsonl に残す(カードを出さなかった判定も含む)。

--- モデル選択の規律(ここが一番クォータを食う) ---
これは**発話ごとに毎回叩く量産呼び出し**。1回の会議(50分)で200回超の呼び出しになる実測がある。
だから既定は安いモデル(Sonnet相当・effort=medium)で、異常時(429/529等で空が返る)のときだけ
上位モデルへ1回だけフォールバックする。
発話をフィルタで間引いて呼び出し回数を減らす手は**採らない**——途切れ途切れの発話も拾わないと
精度が落ちるため。呼ぶ頻度は変えず、単価だけ下げる。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time
import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import meetlive_config as cfgmod  # noqa: E402

STATE = cfgmod.state_dir()
LOG = STATE / "premise_watch.jsonl"
CARDS = STATE / "cards.jsonl"
LEDGER = cfgmod.input_path("MEETLIVE_LEDGER", "ledger.yaml.example", required=True)

SAME_TYPE_COOLDOWN = float(os.environ.get("MEETLIVE_PREMISE_COOLDOWN", "45"))
# 同種(矛盾/既知/新規)の連発はカードとしては既定45秒に1回まで。
# 判定とログは毎回行う(スキップするのはカード表示だけ)。

# 前提リストは10〜20件に絞る。全部入れるとプロンプトが膨らみ、判定がぼやける。
# 絞り方は「今日の会議で、覆されたら困る事実」。契約の範囲境界と、相手の現状認識が核。
PREMISE_MAX = int(os.environ.get("MEETLIVE_PREMISE_MAX", "16"))
_env_ids = os.environ.get("MEETLIVE_PREMISE_IDS")
PREMISE_IDS = [x.strip() for x in _env_ids.split(",") if x.strip()] if _env_ids else None


def _load_premises() -> list[dict]:
    try:
        import yaml
    except ImportError:
        raise SystemExit("[premise_watch] PyYAML が要ります: pip install pyyaml")
    try:
        d = yaml.safe_load(LEDGER.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"[premise_watch] 台帳を読めません {LEDGER}: {e!r}")
    facts = [f for f in (d.get("facts") or []) if isinstance(f, dict) and f.get("id")]
    if not facts:
        raise SystemExit(
            f"[premise_watch] {LEDGER} に facts がありません。"
            " facts: [{id, title}, ...] の形の台帳を MEETLIVE_LEDGER で指してください。"
        )
    if PREMISE_IDS:
        by_id = {f["id"]: f for f in facts}
        picked = [by_id[pid] for pid in PREMISE_IDS if pid in by_id]
        missing = [pid for pid in PREMISE_IDS if pid not in by_id]
        if missing:
            print(f"[premise_watch] ⚠ MEETLIVE_PREMISE_IDS に台帳へ無いidがあります: "
                  f"{','.join(missing)}", file=sys.stderr, flush=True)
        if not picked:
            raise SystemExit(
                "[premise_watch] MEETLIVE_PREMISE_IDS のidが台帳に1つも見つかりません。"
                " 台帳と id 一覧が食い違っています(別案件の設定が残っていませんか)。"
            )
    else:
        # id を明示しないときは台帳の先頭から。多すぎると判定がぼやけるので上限で切る。
        picked = facts[:PREMISE_MAX]
        print(f"[premise_watch] MEETLIVE_PREMISE_IDS 未設定。台帳の先頭 {len(picked)} 件を"
              f"前提として使います", file=sys.stderr, flush=True)
    return [{"id": f["id"], "title": str(f.get("title", ""))} for f in picked]


PREMISES = _load_premises()


def _premise_block() -> str:
    return "\n".join(f"{p['id']}: {p['title']}" for p in PREMISES)


HOST = cfgmod.host_label()
SYSTEM = (
    "あなたは会議同席AIの前提監視係。以下は事前に確定している前提(事実)のリストです。"
    f"相手({cfgmod.counterpart()})の直近の発話1件だけを読み、この前提リストと照らして"
    "次の3値のどれかで1行だけ判定してください。\n"
    "出力形式(必ずこの形式・前置きなし・1行のみ):\n"
    f"  矛盾|前提=<該当するid番号と一言>|相手=<発話の要旨を15字程度>|返し=<{HOST}がその場で言う1文(口語・15〜30字)>\n"
    f"  既知|出所=<該当するid番号>|返し=<{HOST}がその場で言う1文(口語・15〜30字)>\n"
    f"  新規|要旨=<発話の要旨を20字程度>|確認=<{HOST}が聞き返す1文(口語)>\n"
    "  なし\n"
    "『矛盾』は前提リストと明確に食い違うときだけ。『既知』は前提リストに既にある内容を相手が繰り返し/確認したとき。"
    "『新規』は前提リストのどれにも無い具体的な新情報のときだけ。あいさつ・相槌・言いさし・雑談は『なし』。"
    "出力は日本語のみ。英語や説明文を書かない。1行以外は書かない。\n\n"
    "# 前提リスト\n" + _premise_block()
)


def _run(prompt: str, model: str, effort: str, timeout: float) -> str:
    r = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--effort", effort],
        capture_output=True, text=True, timeout=timeout,
    )
    return (r.stdout or "").strip()


def classify(utterance: str) -> dict:
    prompt = f"{SYSTEM}\n\n# 相手の直近発話\n{utterance}\n\n# 判定(1行)"
    t0 = time.time()
    m1, e1, m2, e2 = cfgmod.model("premise")
    src = f"{m1}/{e1}"
    out = ""
    try:
        out = _run(prompt, m1, e1, 20)
    except Exception:
        out = ""
    if not out:
        # 既定モデルが空を返した(過負荷・レート制限等)ときだけ、上位モデルで1回撃ち直す
        try:
            out = _run(prompt, m2, e2, 20)
            src = f"{m2}/{e2}(fallback)"
        except Exception:
            out = ""
    latency = round(time.time() - t0, 1)

    line = out.splitlines()[0].strip() if out else "なし"
    result = {"ts": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000"),
              "utterance": utterance[:80], "src": src, "latency_s": latency,
              "raw": line[:200]}

    m = re.match(r"矛盾\|前提=(.*?)\|相手=(.*?)\|返し=(.*)", line)
    if m:
        result.update(type="矛盾", premise=m.group(1).strip(), gist=m.group(2).strip(),
                      reply=m.group(3).strip())
        return result
    m = re.match(r"既知\|出所=(.*?)\|返し=(.*)", line)
    if m:
        result.update(type="既知", source=m.group(1).strip(), reply=m.group(2).strip())
        return result
    m = re.match(r"新規\|要旨=(.*?)\|確認=(.*)", line)
    if m:
        result.update(type="新規", gist=m.group(1).strip(), confirm=m.group(2).strip())
        return result
    result.update(type="なし")
    return result


def to_card(result: dict) -> dict | None:
    t = result.get("type")
    ts = result["ts"]
    if t == "矛盾":
        lines = [f"⚠前提ズレ: {result.get('premise','')}",
                 f"相手: {result.get('gist','')}",
                 f"返し: {result.get('reply','')}"]
        return {"ts": ts, "kind": "premise_warn", "lines": lines, "confidence": "high",
                "ttl": 60, "src": "premise-watch", "q": result.get("utterance", "")[:60]}
    if t == "既知":
        lines = [f"✔既知: {result.get('source','')}",
                 f"返し: {result.get('reply','')}"]
        return {"ts": ts, "kind": "premise_ok", "lines": lines, "confidence": "high",
                "ttl": 45, "src": "premise-watch", "q": result.get("utterance", "")[:60]}
    if t == "新規":
        lines = [f"＋新情報: {result.get('gist','')}",
                 f"確認: {result.get('confirm','')}"]
        return {"ts": ts, "kind": "premise_new", "lines": lines, "confidence": "low",
                "ttl": 45, "src": "premise-watch", "q": result.get("utterance", "")[:60]}
    return None


def _recent_same_type_within(t: str, seconds: float) -> bool:
    """直近ログ(末尾50件で十分)を見て、同種のカードが最近出ていたら間引く。"""
    if t not in ("矛盾", "既知", "新規"):
        return False
    try:
        lines = LOG.read_text(encoding="utf-8").splitlines()[-50:]
    except OSError:
        return False
    now = time.time()
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") != t:
            continue
        try:
            ts = datetime.datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%S.%f").timestamp()
        except (KeyError, ValueError):
            continue
        return (now - ts) < seconds
    return False


def watch(utterance: str) -> dict:
    result = classify(utterance)
    debounced = _recent_same_type_within(result.get("type", "なし"), SAME_TYPE_COOLDOWN)
    result["debounced"] = debounced
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if debounced:
        return result
    card = to_card(result)
    if card:
        try:
            with CARDS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(card, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return result


if __name__ == "__main__":
    u = " ".join(sys.argv[1:]) or "その資料はもう先方にも共有してあります"
    print(json.dumps(watch(u), ensure_ascii=False, indent=2))
