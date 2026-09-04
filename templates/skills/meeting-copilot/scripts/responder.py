#!/usr/bin/env python3
"""meetlive 返し役 — 相手の発話1つに「そのまま言える返し」を返す層。

台本外の質問に答える ``answerer.py`` との違いは**構え**にある。answerer は
「答えを作る」、こちらは**「台本のどこを読み上げればよいかを指す」**。だから
出力は必ず次の4点で、どれも材料の中にしか無い:

  ①該当する台本の節(§)  ②そのまま言える返し1〜2文  ③言ってよい数字  ④🚫言ってはいけないこと1つ

**🔴 材料は切り詰めない。** 会議フォルダの ``kb/`` の中身を**全文**連結して渡す。
2026-09-03 の実測: 台本を9,000字に切ると、答えが後半にある問いに対して
「手元にない」ではなく**台本と逆の答えを自信をもって作る**。
**切り詰めは沈黙ではなく捏造を生む**。だから文字数の上限設定 (``MEETLIVE_KNOWLEDGE_*``) には従わない。

先読み(bank): 音声入力の遅延に備えて、想定発話の返しを事前に焼いておく
(``<会議フォルダ>/bank.json``)。実行時はキーワード一致で即出しし、LLM は未知発話だけ。

置き場・モデル・呼びかけ語はすべて ``meetlive_config`` が解決する
(このファイルは環境変数を直接読まない)。案件固有の値は1つも持たない。

    MEETLIVE_MEETING=<会議フォルダ> MEETLIVE_DIR=<状態Dir> python3 responder.py --watch
    python3 responder.py --meeting <会議フォルダ> --state <状態Dir> --ask "その件はいくらですか"

止め方は ``touch <状態Dir>/responder.stop`` (kill は使わない)。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import meetlive_config as cfgmod  # noqa: E402

# viewer2 が読む時刻の書式。ここを崩すとカードが「同席開始より前」に落ちて消える。
TS_FMT = "%Y-%m-%dT%H:%M:%S.000"
PACK_NAME = "pack_full.md"
STOP_NAME = "responder.stop"
LOG_NAME = "responder.jsonl"
HEARTBEAT_SEC = 20.0
# 材料として読むもの。バイナリ(pdf/画像)は LLM へ送れないので黙って飛ばす。
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".tsv", ".html", ""}

NO_MATERIAL = "材料になし"
FALLBACK = {
    "sec": NO_MATERIAL,
    "reply": "手元にないので持ち帰ります、と受けてください。",
    "nums": "なし",
    "forbid": "その場で仕様や金額を約束すること",
}


# ---------------------------------------------------------------- 置き場


def state_dir() -> pathlib.Path:
    return cfgmod.state_dir()


def kb_dir() -> pathlib.Path:
    return cfgmod.knowledge_dir()


def stop_path() -> pathlib.Path:
    return state_dir() / STOP_NAME


def reset_config() -> None:
    """環境変数を差し替えた後に呼ぶ(meeting.json の読み込みキャッシュを捨てる)。"""
    cfgmod.load_meeting(refresh=True)


def system_prompt() -> str:
    """相手・こちらの呼び方だけ会議フォルダから差す。それ以外は案件に依存しない。"""
    return f"""あなたは会議の同席役。{cfgmod.host_label()}の隣で、{cfgmod.counterpart()}の発話に対する「そのまま言える返し」を渡す。
下の材料だけを根拠にする。材料に無いことは書かない。

出力は必ず次の4行だけ。行頭のラベルを変えない。前置き・説明・箇条書き記号・英語は一切書かない。
節: <該当する台本の§番号と見出し。複数なら主たるもの1つ。該当が無ければ「{NO_MATERIAL}」とだけ書く>
返し: <そのまま読み上げられる1〜2文。台本の「>」引用ブロックの文言をできるだけそのまま使う。発明しない>
数字: <その場面で言ってよい数字を「想定◯〜◯時間・◯〜◯万円・上限◯万円」の形で。言ってはいけない場面・数字が無い場面は「なし」とだけ書く>
禁: <その場面で言ってはいけないことを1つ。台本の🚫や「言わない」の記述を優先する>
根拠語: <その節だと判断した根拠になる語を、相手の発話の中からそのまま1〜3個・読点区切りで。発話に無い語は書かない>

規律:
- 数字は台本に書かれている数字だけを使う。材料に無い数字を作らない。金額を自分で計算しない。
- 「節」が{NO_MATERIAL}のときは、返しに「{FALLBACK['reply']}」と書く。
- 相手の発話が文の断片で意図が定まらないときも、無理に節を当てず「{NO_MATERIAL}」にする。"""


# ---------------------------------------------------------------- 材料(全量)


def material_files() -> list:
    """``kb/`` の中身を全部。台本(``knowledge_script_name()``)だけ先頭に置く。

    どれを載せるかを**コード側で選ばない**のが肝。9/4版はファイル名の表を
    コードに持っていたので、材料を足しても読まれなかった。棚に置いたものが
    そのまま材料になる、という約束にしてある(🔴 置いたものはLLMへ送られる)。
    """
    d = kb_dir()
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        out.append(p)
    head = cfgmod.knowledge_script_name()
    out.sort(key=lambda p: (0 if p.name == head else 1, str(p)))
    return out


def build_pack(files: list | None = None) -> str:
    """材料を**全文**で連結する。🔴 切り詰めない(冒頭の実測を参照)。"""
    parts = []
    for f in files if files is not None else material_files():
        try:
            body = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parts.append(f"\n\n===== 【{f.stem}】 {f.name} ({len(body)}字・全文) =====\n{body}")
    return "".join(parts)


def load_pack() -> str:
    """材料パックを返す。材料のどれかがパックより新しければ黙って作り直す
    (前夜に台本を直しても、古い材料のまま会議に入らないようにする)。"""
    files = material_files()
    p = state_dir() / PACK_NAME
    newest = max((f.stat().st_mtime for f in files), default=0.0)
    if (not p.exists()) or p.stat().st_mtime < newest:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(build_pack(files), encoding="utf-8")
        print(f"[responder] 材料を読み直しました ({len(files)}件 → {p})", flush=True)
    return p.read_text(encoding="utf-8")


def script_path() -> pathlib.Path | None:
    """接地の基準にする台本。``kb/`` の中の ``knowledge_script_name()``。"""
    p = kb_dir() / cfgmod.knowledge_script_name()
    return p if p.is_file() else None


def corpus_text(pack: str | None = None) -> str:
    """関門と数字検査が突き合わせる本文。

    台本が ``kb/`` にあればそれ(9/4 の実測で閾値を決めたのはこの形)。無ければ
    材料パック全部で代用する ── **台本が特定できないときに関門を厳しいままにすると、
    正しい返しまで「材料になし」へ落ちる**(沈黙は故障に見えるので、緩い側に倒す)。
    """
    p = script_path()
    if p is not None:
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            pass
    return pack if pack is not None else load_pack()


# ---------------------------------------------------------------- 正規化・検査

_NOISE = re.compile(r"[*_`>\s　🔴🚫⚠✅📐🔬⚙️]+")


def norm(s: str) -> str:
    """逐語照合用の正規化。台本は太字記号(**)や絵文字が挟まるため、
    素のまま比較すると『台本の文言そのまま』でも一致しない(2026-09-03 実測)。"""
    return _NOISE.sub("", s or "")


_NUM = re.compile(r"[0-9０-９]+(?:[.,][0-9０-９]+)?")
_Z2H = str.maketrans("０１２３４５６７８９", "0123456789")
# 会議時刻・日付・§番号など、値付けと無関係で誤検出になるものは除く
_SAFE = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}


def numbers_in(s: str) -> list:
    return [m.group(0).translate(_Z2H) for m in _NUM.finditer(s)]


def check_numbers(out_text: str, corpus: str) -> list:
    """材料に現れない数字を返す(空なら健全)。"""
    corpus_nums = set(numbers_in(corpus))
    return sorted({n for n in numbers_in(out_text)
                   if n not in _SAFE and n not in corpus_nums})


def parse_out(raw: str) -> dict:
    d = {"sec": "", "reply": "", "nums": "", "forbid": ""}
    key = {"節": "sec", "返し": "reply", "数字": "nums", "禁": "forbid"}
    cur = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(節|返し|数字|禁)\s*[:：]\s*(.*)$", line)
        if m:
            cur = key[m.group(1)]
            d[cur] = m.group(2).strip()
        elif cur:
            d[cur] += " " + line
    return d


# ---- 関門: 出過ぎを機械で止める(2026-09-03 実測で最大の欠陥だったため) ----
# 実測(31本): 議題外の発話に対して、それらしい節へ吸い寄せられ、台本に無い約束や
# 文脈違いの金額を返す事故が7件。断定の向きを安全側へ倒す = 判断がつかないものは
# 「材料になし」に落とす。
_TOKEN = re.compile(r"[一-龥ァ-ヶー]{2,}")
# 節名に必ず出る「構造の語」は根拠にならないので除く
_STRUCT = {"台本", "想定問答", "決着済", "決着", "別紙", "別表", "検知", "参照", "以下", "上記"}
GROUND_MIN = 30


def sec_tokens(sec: str) -> list:
    return [t for t in _TOKEN.findall(sec) if t not in _STRUCT]


def gate(rec: dict, corpus: str, utterance: str, recent: str = "") -> dict:
    """2つの関門。どちらかに落ちたら「材料になし」へ降格する。"""
    if rec["sec"].startswith(NO_MATERIAL):
        return rec
    hay = utterance + "\n" + recent
    reasons = []

    # 関門1: 接地 — 返しの中に台本の30字以上の連続片が無ければ、台本の文言ではない。
    # 🔴 閾値は実測で決めた(2026-09-03)。材料を切り詰めたときの捏造答えは台本と
    #   17字しか一致せず、本番経路で実際に返した15本は64〜142字一致していた。
    #   10字だと捏造が短い定型句の借り物で通ってしまう。
    body, hay_s = norm(rec["reply"]), norm(corpus)
    grounded = any(body[i:i + GROUND_MIN] in hay_s
                   for i in range(0, max(0, len(body) - GROUND_MIN) + 1))
    if not grounded:
        reasons.append("接地なし(返しが台本の文言でない)")

    # 関門2: 節の語が発話に無い — 相手が言っていない話題の節へ吸い寄せられた形
    toks = sec_tokens(rec["sec"])

    def seen(t):
        # 長い見出し語は3字窓でも照合する(発話は見出しの一部しか言わないため)
        if t in hay:
            return True
        return any(t[i:i + 3] in hay for i in range(len(t) - 2)) if len(t) > 3 else False

    if toks and not any(seen(t) for t in toks):
        reasons.append("節の語が発話に無い(" + "/".join(toks[:3]) + ")")

    if reasons:
        rec["gated"] = reasons
        rec["sec_raw"], rec["reply_raw"] = rec["sec"], rec["reply"]
        rec.update(FALLBACK)
        rec["bad_numbers"] = []
    return rec


# ---------------------------------------------------------------- 先読み(bank)


def load_bank() -> list:
    """先読みカードを読み、いまの台本と食い違っていないかを起動時に検品する。

    カードの返しは台本からの逐語なので、台本が直れば古くなる。黙って古い文言を
    読み上げさせないため、合わなくなった枚数を起動ログに出す。
    """
    p = cfgmod.bank_path()
    if p is None or not p.exists():
        return []
    try:
        bank = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"[responder] ⚠ 先読みを読めません: {p}", flush=True)
        return []
    if not isinstance(bank, list):
        return []
    sc = norm(corpus_text())
    stale = [c.get("key", "?") for c in bank
             if not any(norm(c.get("reply", ""))[i:i + 20] in sc
                        for i in range(0, max(0, len(norm(c.get("reply", ""))) - 20) + 1))]
    if stale:
        print(f"[responder] ⚠ 台本と合わなくなった先読みカード {len(stale)}枚: "
              f"{'/'.join(stale)} → 先読みを焼き直すこと", flush=True)
    return bank


def bank_hit(text: str, bank: list):
    """先読みカードの一致。

    誤爆を避けるため、①一意語が1つ当たれば採用、②そうでなければ普通語が2つ以上
    当たったときだけ採用する。1語だけの弱い一致で撃つと、議題外の発話に金額つきの
    カードが出る(2026-09-03 実測の最大の事故)。
    """
    best, best_s, best_why = None, 0.0, ""
    for c in bank:
        u = [k for k in c.get("uniq", []) if k in text]
        g = [k for k in c.get("kw", []) if k in text]
        if u:
            s = 10.0 + len(u) + 0.1 * len(g)
            why = "一意語:" + "/".join(u)
        elif len(g) >= 2:
            s = float(len(g))
            why = "語:" + "/".join(g[:3])
        else:
            continue
        if s > best_s:
            best, best_s, best_why = c, s, why
    if best:
        return best, round(best_s, 2), best_why
    return None, 0.0, ""


# ---------------------------------------------------------------- LLM


def call_llm(text: str, recent: str, pack: str, timeout: float = 90.0) -> str:
    """材料+直近の会話+相手の発話を渡して4行を得る。落ちたら空を返す(黙って続行)。"""
    model, effort, _, _ = cfgmod.model("answer")
    prompt = (f"{system_prompt()}\n\n{pack}\n\n# 直近の会話(文字起こし・参考)\n{recent[-1200:]}\n\n"
              f"# 相手の発話\n{text}\n\n# 出力(4行)")
    try:
        r = subprocess.run(["claude", "-p", "--model", model, "--effort", effort],
                           input=prompt, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return ""


# ---------------------------------------------------------------- 1件を答える


def answer(text: str, recent: str = "", pack=None, bank=None, use_bank: bool = True,
           gate_context: str = "", timeout: float = 90.0) -> dict:
    t0 = time.time()
    pack = pack if pack is not None else load_pack()
    bank = bank if bank is not None else (load_bank() if use_bank else [])
    src = "llm"
    hit = None
    if use_bank:
        hit, score, why = bank_hit(text, bank)
    if hit:
        d = {k: hit.get(k, "") for k in ("sec", "reply", "nums", "forbid")}
        src = f"bank/{hit.get('key', '?')}({why})"
    else:
        d = parse_out(call_llm(text, recent, pack, timeout=timeout))
        if not d["sec"]:
            d = dict(FALLBACK)
            src = "fallback-empty"
    corpus = corpus_text(pack)
    rec = {
        "ts": datetime.now().strftime(TS_FMT),
        "kind": "reply", "q": text[:80], "src": src,
        "latency_s": round(time.time() - t0, 1),
        "sec": d["sec"], "reply": d["reply"], "nums": d["nums"], "forbid": d["forbid"],
        "bad_numbers": check_numbers(" ".join([d["reply"], d["nums"]]), corpus),
        "gated": [],
    }
    # 先読みカードは台本から直接作ってあるので関門を通さない。LLM の答えだけ通す。
    if src == "llm":
        # 関門の文脈は「相手の直前の発話」だけ。こちら側の発話を混ぜると、自分が
        # 言った語を相手の断片が借りて関門を通ってしまう。
        rec = gate(rec, corpus, text, gate_context)
    return rec


def to_card(rec: dict) -> dict:
    """viewer2 が読む cards.jsonl の形へ。lines は上から §/返し/数字/禁。"""
    lines = [f"§ {rec['sec']}", rec["reply"]]
    if rec["nums"] and rec["nums"] not in ("なし", "無し"):
        lines.append(f"数字 {rec['nums']}")
    if rec["forbid"]:
        lines.append(f"🚫 {rec['forbid']}")
    if rec["bad_numbers"]:
        lines.append("⚠ 台本に無い数字: " + "/".join(rec["bad_numbers"]) + " → 口に出さない")
    return {"ts": rec["ts"], "kind": rec.get("kind", "reply"), "lines": lines,
            "confidence": "none" if rec["sec"].startswith(NO_MATERIAL) else "high",
            "ttl": 90, "q": rec["q"], "src": rec["src"]}


def emit(rec: dict) -> None:
    """ログには全件、画面には中身のあるものだけ。

    「材料になし」までカードにすると、議題外の雑談のたびに画面が「手元に資料が
    ありません」で塗り替わり、直前の使える返しを押し出す(2026-09-03 実測: 過去の
    逐語20本のうち半数が材料になし)。ただし**声で呼ばれたとき(kind=call)は必ず出す**
    ── 呼んだのに何も出ないと、壊れたのか材料が無いのかが手元から区別できない。
    """
    out = state_dir()
    out.mkdir(parents=True, exist_ok=True)
    with (out / LOG_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if rec["sec"].startswith(NO_MATERIAL) and rec.get("kind") != "call":
        return
    with (out / "cards.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(to_card(rec), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 心拍


def write_heartbeat(note: str = "") -> pathlib.Path:
    """稼働ラインへ「返し役は生きている」と書く。書式は viewer2 の read_heartbeat が正。

    書き途中を viewer に読まれると「壊れている」に見えるので、tmp へ書いて置き換える。
    """
    p = cfgmod.heartbeat_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    model, _, _, _ = cfgmod.model("answer")
    payload = {"ts": datetime.now().strftime(TS_FMT), "role": "responder",
               "model": model, "note": note}
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


# ---------------------------------------------------------------- 呼びかけ


def is_call(rec: dict) -> bool:
    """こちら側(host)がモニタを名指しで呼んだ行か。

    receiver が立てる ``call`` を第一の根拠にしつつ、呼びかけ語での照合も自前で持つ
    ── 判定を1か所に閉じると、receiver を通さない経路(手入力・再生)で呼べなくなる。
    相手(guest)の発話で呼びかけ語が出ても撃たない(相手が言った語で暴発するため)。
    """
    if rec.get("speaker") != "host":
        return False
    if rec.get("call"):
        return True
    text = rec.get("text") or ""
    return any(w and w in text for w in cfgmod.call_words())


# ---------------------------------------------------------------- watch


def watch(min_chars: int = 18, quiet: float = 2.0, timeout: float = 90.0) -> None:
    """guest の発話を溜め、無音 quiet 秒 or 十分な長さで1回返す(断片ごとに撃たない)。"""
    pack, bank = load_pack(), load_bank()
    out = state_dir()
    tj = out / "transcript.jsonl"
    tj.touch(exist_ok=True)
    f = tj.open("r", encoding="utf-8")
    f.seek(0, 2)
    buf, last, recent, gbuf = [], 0.0, [], []
    stop = stop_path()
    if stop.exists():
        stop.unlink()
    model, effort, _, _ = cfgmod.model("answer")
    print(f"[responder] 監視開始 model={model} effort={effort} "
          f"材料={len(material_files())}件/{len(pack)}字 先読み={len(bank)}枚", flush=True)
    print(f"[responder] 停止は  touch {stop}  （kill は使わない）", flush=True)
    write_heartbeat("起動")
    last_hb = time.time()
    while True:
        # 静かな終了口。kill/pkill を使わずに自プロセスを畳む(viewer2 の /quit と同じ考え方)
        if stop.exists():
            stop.unlink()
            print("[responder] 停止合図を受けたので終了します", flush=True)
            return
        if time.time() - last_hb >= HEARTBEAT_SEC:
            write_heartbeat(f"待機 先読み{len(bank)}枚")
            last_hb = time.time()
        line = f.readline()
        if line:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            txt = (r.get("text") or "").strip()
            if not txt or txt.startswith("[STT"):
                continue
            recent.append(f"{r.get('speaker')}: {txt}")
            recent = recent[-12:]
            # 声で呼ばれた照会は相手の発話より優先し、溜めずに即答する。
            if is_call(r):
                rec = answer(txt, "\n".join(recent), pack, bank,
                             gate_context=txt, timeout=timeout)
                rec["kind"] = "call"
                emit(rec)
                write_heartbeat(f"呼出 {rec['src']}")
                last_hb = time.time()
                print(f"[呼出 {rec['src']} {rec['latency_s']}s] {rec['sec']}", flush=True)
                continue
            if r.get("speaker") == "guest":
                buf.append(txt)
                gbuf.append(txt)
                gbuf[:] = gbuf[-6:]
                last = time.time()
            continue
        if buf and (time.time() - last) >= quiet:
            text = " ".join(buf).strip()
            n_buf = len(buf)
            buf = []
            if len(text) < min_chars:
                continue
            ctx = gbuf[:-n_buf] if len(gbuf) > n_buf else []
            rec = answer(text, "\n".join(recent), pack, bank,
                         gate_context="\n".join(ctx), timeout=timeout)
            emit(rec)
            write_heartbeat(f"返し {rec['src']}")
            last_hb = time.time()
            print(f"[{rec['src']} {rec['latency_s']}s] {rec['sec']} | {rec['reply'][:50]}",
                  flush=True)
            continue
        time.sleep(0.2)


# ---------------------------------------------------------------- CLI


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="meetlive 返し役")
    ap.add_argument("--meeting", default="", help="会議フォルダ (既定 MEETLIVE_MEETING)")
    ap.add_argument("--state", default="", help="状態ディレクトリ (既定 MEETLIVE_DIR)")
    ap.add_argument("--watch", action="store_true", help="逐語を見張って返しを出し続ける")
    ap.add_argument("--ask", default="", help="1件だけ答えて終わる(点検用)")
    ap.add_argument("--no-bank", action="store_true", help="先読みを使わない")
    ap.add_argument("--emit", action="store_true", help="--ask の結果も cards.jsonl へ書く")
    ap.add_argument("--min-chars", type=int, default=18,
                    help="これより短い相手の発話は溜めるだけで撃たない")
    ap.add_argument("--quiet-sec", type=float, default=2.0, help="この秒数の無音で1回返す")
    ap.add_argument("--timeout", type=float, default=90.0, help="LLM 1回の待ち時間(秒)")
    ap.add_argument("--selfcheck", action="store_true", help="材料を読めるかだけ見て終わる")
    a = ap.parse_args(argv)

    # CLI は環境変数へ流し込む。解決の規則は meetlive_config の1箇所だけに置く。
    if a.meeting:
        os.environ["MEETLIVE_MEETING"] = a.meeting
    if a.state:
        os.environ["MEETLIVE_DIR"] = a.state
    reset_config()

    if a.selfcheck:
        files = material_files()
        pack = build_pack(files)
        sp = script_path()
        print(f"状態ディレクトリ: {state_dir()}")
        print(f"材料: {kb_dir()} — {len(files)}件 / {len(pack)}字(全文・切り詰めなし)")
        for f in files:
            print(f"  - {f.name}")
        print(f"接地の基準: {sp if sp else '(台本が見つからないので材料パック全体)'}")
        print(f"先読み: {len(load_bank())}枚 / 呼びかけ語: {','.join(cfgmod.call_words())}")
        print("selfcheck OK")
        return 0
    if a.watch:
        watch(min_chars=a.min_chars, quiet=a.quiet_sec, timeout=a.timeout)
        return 0
    if a.ask:
        rec = answer(a.ask, use_bank=not a.no_bank, timeout=a.timeout)
        if a.emit:
            emit(rec)
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
