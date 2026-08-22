"""
meetlive 表示側 v2 — 「画面が会議を運転する」テレプロンプター

進行役は台本を読むだけで会議が終わり、脱線したときだけ下段が助ける、という道具。

縦3段固定 (携帯ディスプレイ横置き・暗い背景・大きい文字):
  上段 = 今日の段【1】〜【N】を横一列。いまの段だけ明るい。予定時刻と経過。取り漏れは⚠
  中段 = いまの段の台本ブロックをそのまま。読み上げる文は大きく。分岐▸は畳んである
  下段 = 番人/第2層のカード1枚だけ。warn=赤 / それ以外=琥珀 / 無ければ「—」

段の判定は copilot.py (番人) と**同じ規則**で計算する。番人は cur をファイルに出さないので、
こちらでも同じ材料 (transcript.jsonl) から同じ式で出す。ここがズレると、下段の
topic カードに書かれた段番号と上段の段番号が食い違って見えるので、規則は番人に合わせる:
  - 段の検知キーワードはこちら側の発話のみ / 必須取得物は両者の発話
  - 「<呼びかけ語>、次/戻って」は先頭6文字の一致で ±1
  - 経過時間は --start から (番人が「<呼びかけ語>、時間」に答えるのと同じ基準)

--- 舞台(相手に見せる別窓) ---
進行役はPCを触らない。共有するのは「名前付きの別窓 meetlive_stage」1枚だけで、
その中身をテレプロンプターのJSが window.open(url, 'meetlive_stage') で航行させる。
iframe は使えない (相手先サイトが x-frame-options: DENY だったり、ログイン cookie が
SameSite=lax だったりして中身が出ない)。
切り替えの出所は3つ。いちばん新しい ts が勝つ:
  auto   = 段の遷移 (資源表の "auto")。遷移した瞬間に1回だけ。同じ段では二度と上書きしない
  voice  = copilot.py が stage_cmd.jsonl に書く音声指令
  manual = この画面のボタン列 (/stage/set?res=)

起動:
    MEETLIVE_DIR=./meetlive_state/2026-01-20-acme \\
    MEETLIVE_AGENDA=... MEETLIVE_SCRIPT=... MEETLIVE_STAGE=... \\
      python3 viewer2.py --start 2026-01-20T15:00:00 >> viewer2.log 2>&1 &
携帯ディスプレイから見るときは、この機体の LAN / VPN のアドレス + --port で開く。
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import pathlib
import re
import socketserver
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import meetlive_config as cfgmod  # noqa: E402

STATE_DIR = cfgmod.state_dir()
AGENDA_PATH = cfgmod.input_path("MEETLIVE_AGENDA", "agenda_steps.example.json", required=True)
SCRIPT_PATH = cfgmod.input_path("MEETLIVE_SCRIPT", "talk_script.example.md", required=True)

CARD_TTL = 45.0        # カードを出しておく既定の秒数
CARD_MAX_TURNS = 2     # このぶん会話が進んだらカードを引っ込める
CARD_MIN_SHOW_SEC = 8.0  # turns条件に関わらず、出してから最低これだけは表示する
                          # (実測: 会話が速い区間だと、書かれてから最初のポーリングが
                          #  来る前に turns 条件で死に、1回も画面に出ないカードがあった)

CALL_WORDS = cfgmod.call_words()
MODE_START_WORD, _MODE_END_WORD, START_HOMOPHONES = cfgmod.mode_words()

_KW_RE_CACHE: dict[str, "re.Pattern | None"] = {}


def kw_hit(kw: str, blob: str) -> bool:
    """検知キーワードを正規表現として当てる(copilot.py と同じ規則)。

    文字列の部分一致だけだと表記ゆれで丸ごと見逃す。キーワードに正規表現の特殊文字が
    無ければ従来どおりの部分一致と同じ結果になるので、平文の設定は無改変で動く。
    壊れた正規表現は部分一致へ退避。
    """
    pat = _KW_RE_CACHE.get(kw, 0)
    if pat == 0:
        try:
            pat = re.compile(kw)
        except re.error:
            pat = None
        _KW_RE_CACHE[kw] = pat
    if pat is not None:
        return bool(pat.search(blob))
    return kw in blob


# ---------------------------------------------------------------- 舞台 (stage)
STAGE_CFG = cfgmod.load_stage()
STAGE_ORDER = [r["res"] for r in STAGE_CFG["resources"]]
STAGE_RES: dict[str, dict] = {}
STAGE_IMG: dict[str, pathlib.Path] = {}
for _r in STAGE_CFG["resources"]:
    url = _r["url"]
    img = cfgmod.resolve_img(_r["img"])
    if img is not None:
        STAGE_IMG[_r["res"]] = img
        if not url:
            url = "/stage/png/" + _r["res"]
    if not url:
        url = "/stage/blank" if _r["res"] == "blank" else ""
    STAGE_RES[_r["res"]] = {"label": _r["label"], "btn": _r["btn"], "url": url}
AUTO_STAGE = STAGE_CFG["auto"]        # 段番号(1始まり) → 資源

STAGE_CMD_FILE = "stage_cmd.jsonl"
STAGE_LOCK = threading.Lock()
STAGE = {"res": "blank", "ts": time.time(), "src": "init", "text": "",
         "last_step": None, "cmd_ts": 0.0}

# URL だけは状態ディレクトリの stage_urls.json で差し替えられる (再起動不要)。
#   例: {"slides": "https://example.com/deck", "free": "https://..."}
# 会議直前にURLが変わったとき、走行中のプロセスを止めずに直すための逃げ道。
STAGE_URLS_FILE = "stage_urls.json"
OUTDIR = STATE_DIR
_URLS = {"key": None, "map": {}}

_URL_KEYS = set(STAGE_RES) | {"free_label"}


def url_overrides() -> dict:
    p = OUTDIR / STAGE_URLS_FILE
    try:
        key = p.stat().st_mtime_ns
    except OSError:
        _URLS["key"], _URLS["map"] = None, {}
        return {}
    if _URLS["key"] != key:
        m = {}
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                m = {k: v for k, v in raw.items()
                     if k in _URL_KEYS and isinstance(v, str) and v.strip()}
        except (OSError, json.JSONDecodeError, ValueError):
            m = {}
        _URLS["key"], _URLS["map"] = key, m
    return _URLS["map"]


def res_url(res: str) -> str:
    d = STAGE_RES.get(res) or STAGE_RES.get("blank") or {"url": "/stage/blank"}
    return url_overrides().get(res) or d.get("url", "")


def res_label(res: str) -> str:
    d = STAGE_RES.get(res) or STAGE_RES.get("blank") or {"label": "打合せ中"}
    if res == "free":
        return url_overrides().get("free_label") or d.get("label", "予備枠")
    return d.get("label", res)


def save_free(url: str, label: str = "") -> bool:
    """予備枠(free)のURL/名前を stage_urls.json へ焼く。走行中に差し込める唯一の資源。"""
    url = (url or "").strip()
    if not url or not re.match(r"^https?://|^/", url):
        return False
    p = OUTDIR / STAGE_URLS_FILE
    cur = {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            cur = raw
    except (OSError, json.JSONDecodeError, ValueError):
        cur = {}
    cur["free"] = url
    if (label or "").strip():
        cur["free_label"] = label.strip()[:40]
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        return False
    return True


def stage_view() -> dict:
    with STAGE_LOCK:
        res = STAGE["res"]
        ts, src, text = STAGE["ts"], STAGE["src"], STAGE["text"]
    return {
        "res": res,
        "label": res_label(res),
        "url": res_url(res),
        "ts": round(ts, 3),
        "src": src,
        "text": text,
        # ボタン列が予備枠を有効にできるよう、いまの行き先を常に添える
        "free": res_url("free"),
        "free_label": url_overrides().get("free_label") or "",
    }


def stage_set(res: str, src: str, text: str = "") -> bool:
    if res not in STAGE_RES:
        return False
    with STAGE_LOCK:
        STAGE["res"] = res
        STAGE["ts"] = time.time()
        STAGE["src"] = src
        STAGE["text"] = text
    return True


def stage_sync(outdir: pathlib.Path, nav) -> None:
    """音声指令(ファイル)と段の遷移を取り込む。新しい ts が勝つ。"""
    # 1) copilot が書く音声指令の末尾
    last = None
    p = outdir / STAGE_CMD_FILE
    if p.exists():
        try:
            with p.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            last = json.loads(line)
                        except json.JSONDecodeError:
                            pass
        except OSError:
            last = None
    if last:
        res = last.get("res")
        try:
            cts = float(last.get("ts") or 0.0)
        except (TypeError, ValueError):
            cts = 0.0
        with STAGE_LOCK:
            fresh = cts > STAGE["ts"] and cts > STAGE["cmd_ts"]
        if res == "free" and fresh:
            # 外の道具がこの行に任意のURLを載せてくることがある
            if last.get("url"):
                save_free(str(last.get("url")), str(last.get("label") or ""))
            if not res_url("free"):
                res = None                      # 行き先が無い free は無視する
        if res in STAGE_RES and fresh:
            stage_set(res, last.get("src", "voice"), str(last.get("text", ""))[:60])
            with STAGE_LOCK:
                STAGE["cmd_ts"] = cts

    # 2) 段の遷移。入った瞬間だけ1回 (同じ段に留まる限り、手動/音声を上書きしない)
    if nav:
        cur = int(nav.get("cur", 0))
        with STAGE_LOCK:
            moved = STAGE["last_step"] != cur
            STAGE["last_step"] = cur
        if moved:
            res = AUTO_STAGE.get(cur + 1)
            if res in STAGE_RES:
                stage_set(res, "auto", f"段{cur + 1}へ")


# ---------------------------------------------------------------- 読み込み

def read_jsonl(path, limit=None):
    out = []
    if not path.exists():
        return out
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        return out
    return out[-limit:] if limit else out


def _ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f").timestamp()
    except (ValueError, TypeError):
        return 0.0


def token(outdir: pathlib.Path):
    """ファイルの変化を1つの文字列にまとめる。長ポーリングの変化検知用。"""
    parts = []
    for n in ("transcript.jsonl", "cards.jsonl", "partial.json", STAGE_CMD_FILE):
        p = outdir / n
        try:
            st = p.stat()
            parts.append(f"{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append("-")
    # 舞台はボタン(/stage/set)でもファイル無しに変わるので、状態そのものも合図に混ぜる
    with STAGE_LOCK:
        parts.append("s%.3f" % STAGE["ts"])
    return "|".join(parts)


def clean_md(s: str) -> str:
    s = re.sub(r"`+", "", s)
    s = re.sub(r"\*\*|\*", "", s)
    s = re.sub(r"^[▸\-\s•>|]+", "", s)
    return s.strip()


def _field(d: dict, ja: str, en: str, default=None):
    """設定JSONは日本語キーを正とし、英語キーも受ける(どちらで書いてもよい)。"""
    if ja in d:
        return d[ja]
    if en in d:
        return d[en]
    return default


def load_agenda(path: pathlib.Path):
    """段取りJSON。無ければ None (画面は台本だけになる)。"""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    steps = []
    for i, s in enumerate(raw.get("steps", []) or []):
        if not isinstance(s, dict):
            continue
        musts = []
        for m in _field(s, "必須取得物", "musts", []) or []:
            if isinstance(m, str):
                musts.append({"name": m, "kw": [m]})
            elif isinstance(m, dict):
                musts.append({
                    "name": _field(m, "名前", "name", "") or "",
                    "kw": [k for k in (_field(m, "検知キーワード", "keywords", []) or []) if k],
                })
        title = s.get("title", f"ステップ{i + 1}")
        steps.append({
            "id": s.get("id", str(i)),
            "title": title,
            "short": short_title(title),
            "min": float(_field(s, "目安分", "minutes", 0) or 0),
            "kw": [k for k in (_field(s, "検知キーワード", "keywords", []) or []) if k],
            "must": musts,
            "nudge": s.get("nudge", ""),
            "script": [x for x in (_field(s, "台本", "script", []) or []) if x],
        })
    if not steps:
        return None
    total = sum(x["min"] for x in steps)
    return {
        "steps": steps,
        "total_min": float(_field(raw, "会議分", "total_minutes", 0) or total),
        "warn_at": float(_field(raw, "警報分", "warn_at_minutes", 12) or 12),
    }


def short_title(title: str, n: int = 9) -> str:
    """上段の横一列に入る長さへ。丸数字と括弧の中は落とす。"""
    t = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩\d\.\s　]+", "", title)
    t = re.sub(r"[（(].*?[）)]", "", t).strip()
    t = t or title
    return t if len(t) <= n else t[: n - 1] + "…"


# ---------------------------------------------------------------- 台本の抽出

def parse_script(path: pathlib.Path) -> dict:
    """talk_script md から【N】節ごとの「進行役が言うブロック」を取り出す。

    行の型:
      say    = 太字で始まる行 (声に出す文)。行末の（注記）は sub として小さく添える
      head   = ### の小見出し
      branch = ▸ の分岐。「→」の前が条件・後が言うこと。既定は畳む
      note   = 丸括弧のト書き・表・その他 (小さく薄く)
    """
    out: dict[str, list] = {}
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out

    cur_n = None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^##\s+【(\d+)】\s*(.*)$", line)
        if m:
            cur_n = m.group(1)
            out.setdefault(cur_n, [])
            continue
        if line.startswith("## "):          # 【N】以外の節に入ったら収集をやめる
            cur_n = None
            continue
        if cur_n is None or not line.strip():
            continue
        s = line.strip()
        if s.startswith("---") or set(s) <= {"-", "|", " ", ":"}:
            continue

        if s.startswith("### "):
            out[cur_n].append({"t": "head", "s": clean_md(s[4:])})
            continue

        if s.startswith("▸"):
            body = s.lstrip("▸ ").strip()
            if "→" in body:
                cond, act = body.split("→", 1)
            else:
                cond, act = body, ""
            out[cur_n].append({
                "t": "branch",
                "s": clean_md(cond).rstrip("、 "),
                "b": clean_md(act),
            })
            continue

        if s.startswith("|"):               # 表は手順の覚え書きとして薄く出す
            cells = [c.strip() for c in s.strip("|").split("|")]
            cells = [c for c in cells if c and not set(c) <= {"-", ":"}]
            if cells:
                out[cur_n].append({"t": "note", "s": clean_md(" / ".join(cells))})
            continue

        if s.startswith("（"):
            out[cur_n].append({"t": "note", "s": clean_md(s)})
            continue

        mb = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", s)
        if mb:
            say = clean_md(mb.group(1))
            sub = clean_md(mb.group(2))
            if say:
                item = {"t": "say", "s": say}
                if sub:
                    item["sub"] = sub
                out[cur_n].append(item)
            continue

        out[cur_n].append({"t": "note", "s": clean_md(s)})

    return {k: v for k, v in out.items() if v}


def build_blocks(agenda, scripts: dict) -> list:
    """段(agenda)と台本節(【N】)を突き合わせて、中段に出すブロックを作る。"""
    blocks = []
    steps = (agenda or {}).get("steps") or []
    for i, s in enumerate(steps):
        items = list(scripts.get(str(i + 1), []))
        src = "台本"
        if not any(x["t"] == "say" for x in items):
            # 台本から拾えない段は agenda の台本行で代替する
            items = [{"t": "say", "s": clean_md(x)} for x in s["script"]] or \
                    [{"t": "note", "s": s["nudge"] or "（この段の台本行がありません）"}]
            src = "段取り"
        blocks.append({
            "n": i + 1,
            "title": s["title"],
            "short": s["short"],
            "min": s["min"],
            "nudge": s["nudge"],
            "src": src,
            "items": items,
        })
    if not blocks:                          # 段取りJSONが無い場合の最後の砦
        for k in sorted(scripts, key=lambda x: int(x)):
            blocks.append({"n": int(k), "title": f"【{k}】", "short": f"【{k}】",
                           "min": 0, "nudge": "", "src": "台本", "items": scripts[k]})
    return blocks


# ---------------------------------------------------------------- 会議ナビ

def _delta_of(text: str) -> int:
    """番人 copilot.answer と同じ判定。「<呼びかけ語>、次」の頭6文字だけを見る。"""
    q = text
    for w in CALL_WORDS:
        q = q.replace(w, "")
    head = q.strip("、。 　,.")[:6]
    if re.match(r"^(次|つぎ|進|すす)", head):
        return 1
    if re.match(r"^(戻|もど|前)", head):
        return -1
    return 0


def build_nav(agenda, lines, mode, start_epoch, total_min_override=None):
    if not agenda:
        return None
    steps = agenda["steps"]

    # 同席開始からの発話だけを見る (番人の reset_state と同じ考え方)。
    # 開始合図の聞き取り揺れも番人と同じく吸収する。
    anchor = None
    for r in lines:
        if r.get("type") == "mode" and r.get("mode") == "start":
            anchor = _ts(r.get("ts", ""))
    if anchor is None:
        marks = tuple(CALL_WORDS) + (MODE_START_WORD,) + tuple(START_HOMOPHONES)
        for r in lines:
            t = r.get("text") or ""
            if r.get("speaker") == "host" and ("開始" in t or "スタート" in t) and any(
                w and w in t for w in marks
            ):
                anchor = _ts(r.get("ts", ""))
                break

    said = [r for r in lines if r.get("text") and (anchor is None or _ts(r.get("ts", "")) >= anchor)]
    all_blob = "\n".join(r.get("text", "") for r in said)
    host_blob = "\n".join(r.get("text", "") for r in said if r.get("speaker") == "host")

    auto = 0
    for i, s in enumerate(steps):
        if any(kw_hit(k, host_blob) for k in s["kw"]):
            auto = max(auto, i)
    delta = 0
    for r in said:
        if r.get("call"):
            delta += _delta_of(r.get("text", ""))
    cur = max(0, min(len(steps) - 1, auto + delta))

    def met(m):
        return bool(m["kw"]) and any(kw_hit(k, all_blob) for k in m["kw"])

    total_min = float(total_min_override or agenda["total_min"] or 60)
    elapsed = (time.time() - start_epoch) / 60.0
    remaining = max(0.0, total_min - elapsed)

    # 上段の各段: 予定の時刻窓と、その段の取り漏れ数
    chips, head = [], 0.0
    for i, s in enumerate(steps):
        a = start_epoch + head * 60
        b = a + s["min"] * 60
        head += s["min"]
        # ⚠ は「もう通った段なのに取れていない」ときだけ。先の段は取れていなくて当然
        unmet_n = sum(1 for m in s["must"] if m["kw"] and not met(m)) if i <= cur else 0
        chips.append({
            "n": i + 1,
            "short": s["short"],
            "title": s["title"],
            "from": datetime.fromtimestamp(a).strftime("%H:%M"),
            "to": datetime.fromtimestamp(b).strftime("%H:%M"),
            "unmet": unmet_n,
            "due": a <= time.time() < b,      # 予定ではいまここ
        })

    unmet = [m["name"] for s in steps[: cur + 1] for m in s["must"] if m["kw"] and not met(m)]
    warn = None
    if elapsed > 0 and unmet and remaining <= agenda["warn_at"]:
        warn = f"残り{int(remaining)}分: {unmet[0]}がまだ"
        if len(unmet) > 1:
            warn += f"（ほか{len(unmet) - 1}件）"

    return {
        "cur": cur,
        "i": cur + 1,
        "n": len(steps),
        "title": steps[cur]["title"],
        "elapsed_min": int(elapsed),
        "remaining_min": int(remaining),
        "script": steps[cur]["script"][:2],
        "nudge": steps[cur]["nudge"],
        "musts": [{"name": m["name"], "ok": met(m)} for m in steps[cur]["must"]],
        "unmet": unmet,
        "chips": chips,
        "warn": warn,
        # 開始前の表示は時刻だけで決める。開始合図の聞き取り揺れを吸収した結果、
        # 前夜の試験発話が anchor に当たっていても、開始予定時刻までは「開始前」と出したい。
        "waiting": elapsed < 0,
        "live": bool(anchor) and mode == "start",
    }


def build_state(outdir: pathlib.Path, agenda, start_epoch, total_min=None):
    # 逐語は切り詰めない。番人 copilot の blob は同席開始から累積で、こちらが末尾N行だけ
    # 見ると、長い会議で古い発話が窓から落ちて段が巻き戻る (✓が□に戻る・警報が誤爆する)。
    lines = read_jsonl(outdir / "transcript.jsonl")
    cards = read_jsonl(outdir / "cards.jsonl", limit=40)
    now = time.time()

    mode = "end"
    for r in lines:
        if r.get("type") == "mode":
            mode = r.get("mode", "end")

    # --- 下段のカードは常に1枚。新しいものが勝つ。呼び出しへの回答は最優先 ---
    card, call_latency = None, None
    if cards:
        latest = cards[-1]
        latest_call = next((c for c in reversed(cards) if c.get("kind") == "call"), None)
        pick = latest_call if (latest_call and latest_call is cards[-1]) else latest
        cts = _ts(pick.get("ts", ""))
        ttl = float(pick.get("ttl", CARD_TTL))
        turns = sum(1 for r in lines if r.get("text") and _ts(r.get("ts", "")) > cts)
        age = now - cts
        alive = pick.get("kind") == "wrap" or (
            age < ttl and (turns <= CARD_MAX_TURNS or age < CARD_MIN_SHOW_SEC)
        )
        if alive:
            card = dict(pick)
            if pick.get("kind") == "call":
                # カード自身が q (質問文) を持っていればそれを正とする。
                # 持っていない古い形式のカードだけ、呼び出し語のtranscript行から拾う
                # フォールバックへ落とす(古いリハ発話で質問欄が固まるバグの元だった経路)。
                if not card.get("q"):
                    q = next((r for r in reversed(lines)
                              if r.get("call") and _ts(r.get("ts", "")) <= cts), None)
                    if q:
                        card["q"] = q.get("text")
                        call_latency = round(cts - _ts(q.get("ts", "")), 2)

    nav = build_nav(agenda, lines, mode, start_epoch, total_min)
    # 台本は中段が持つので、下段の穴埋めは取り漏れ警報だけ
    if card is None and nav and nav["warn"]:
        card = {"kind": "warn", "lines": [nav["warn"]], "confidence": "high"}

    stage_sync(outdir, nav)

    return {
        "nav": nav,
        "card": card,
        "stage": stage_view(),
        "mode": mode,
        "live": (outdir / "partial.json").exists(),
        "call_latency_s": call_latency,
        "start_epoch": start_epoch,
        "total_min": float(total_min or (agenda or {}).get("total_min") or 60),
        "tok": token(outdir),
    }


# ---------------------------------------------------------------- 画面

PAGE = r"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#12151a">
<title>議事メモ</title>
<style>
  :root{
    --bg:#12151a; --panel:#1b1f27; --line:#2a2f39;
    --fg:#e8ecf2; --dim:#8b93a1; --faint:#4d5462;
    --accent:#c79a4a; --hot:#d9534f; --ok:#5aa06e;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{height:100%}
  body{margin:0;background:var(--bg);color:var(--fg);overflow:hidden;
       font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic UI",system-ui,sans-serif;
       display:flex;flex-direction:column}
  .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
        font-variant-numeric:tabular-nums}

  /* ---------- 上段: 今日の段 ---------- */
  #top{flex:0 0 auto;background:var(--panel);border-bottom:1px solid var(--line);
       padding:6px 10px 7px}
  #bar{display:flex;gap:6px;align-items:stretch}
  .chip{flex:1 1 0;min-width:0;border:1px solid var(--line);border-radius:5px;
        background:#171b22;padding:5px 7px;line-height:1.25;position:relative;
        color:var(--faint);cursor:pointer;transition:background .15s,color .15s}
  .chip .t{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;
           text-overflow:ellipsis}
  .chip .w{font-size:10px;letter-spacing:.02em;opacity:.85}
  .chip.due{border-color:#39414f}
  .chip.on{background:#2b3444;border-color:#4d6081;color:var(--fg)}
  .chip.on .w{color:#c3ccdb}
  .chip .m{position:absolute;top:2px;right:4px;font-size:10px;color:var(--accent)}
  #meta{display:flex;align-items:center;gap:14px;margin-top:5px;font-size:11px;
        color:var(--dim);min-height:14px}
  #meta b{color:var(--fg);font-weight:600}
  #clock{margin-left:auto}
  #manual{color:var(--accent);cursor:pointer;display:none}
  body.manual #manual{display:inline}

  /* ---------- 舞台(共有する別窓)の操縦席 ---------- */
  #stage{display:flex;align-items:center;gap:8px;margin-top:6px;
         padding-top:6px;border-top:1px solid var(--line);
         overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}
  #stage::-webkit-scrollbar{display:none}
  #stopen{flex:0 0 auto;background:#3a2f18;color:#f0d9a4;border:1px solid #6b5424;
          border-radius:6px;padding:6px 12px;font-size:13px;font-weight:700;
          cursor:pointer;font-family:inherit;white-space:nowrap}
  #stnow{flex:0 0 auto;font-size:12px;color:var(--dim);white-space:nowrap}
  #stnow b{color:var(--accent);font-weight:600}
  #stbtns{flex:0 0 auto;display:flex;gap:5px}
  .sb{background:#171b22;color:var(--dim);border:1px solid var(--line);border-radius:5px;
      padding:5px 9px;font-size:12px;cursor:pointer;font-family:inherit;white-space:nowrap}
  .sb.on{background:#2b3444;border-color:#4d6081;color:var(--fg)}
  .sb.off{opacity:.3}

  /* ---------- 中段: いま話すこと ---------- */
  #mid{flex:1 1 auto;min-height:0;overflow-y:auto;padding:14px 20px 18px;
       -webkit-overflow-scrolling:touch}
  #h{font-size:12px;color:var(--dim);letter-spacing:.06em;margin:0 0 10px}
  #h b{color:var(--accent);font-weight:600}
  .say{font-size:28px;line-height:1.45;font-weight:600;margin:0 0 14px;
       letter-spacing:.01em}
  .say .sub{display:block;font-size:13px;font-weight:400;color:var(--dim);
            margin-top:3px;letter-spacing:0}
  .hd{font-size:12px;color:var(--accent);letter-spacing:.1em;margin:16px 0 8px;
      border-top:1px solid var(--line);padding-top:9px}
  .nt{font-size:13px;color:var(--faint);line-height:1.5;margin:0 0 10px}
  details.br{margin:0 0 8px;border-left:2px solid #39414f;padding-left:9px}
  details.br>summary{font-size:14px;color:var(--dim);cursor:pointer;list-style:none;
                     padding:2px 0}
  details.br>summary::-webkit-details-marker{display:none}
  details.br>summary::before{content:"▸ ";color:var(--accent)}
  details.br[open]>summary::before{content:"▾ "}
  details.br .bd{font-size:20px;line-height:1.4;font-weight:500;color:#cfd6e1;
                 padding:5px 0 7px}
  #musts{margin-top:18px;border-top:1px solid var(--line);padding-top:10px;
         display:flex;flex-wrap:wrap;gap:6px 16px;font-size:14px;color:var(--dim)}
  #musts span{white-space:nowrap}
  #musts .y{color:var(--ok)}
  #musts .y i{font-style:normal}
  #musts .n b{color:var(--accent);font-weight:600}

  /* ---------- 下段: 助け ---------- */
  #bot{flex:0 0 auto;min-height:92px;border-top:1px solid var(--line);
       background:var(--panel);padding:10px 20px;display:flex;flex-direction:column;
       justify-content:center}
  #none{color:#333a45;font-size:22px;letter-spacing:.3em}
  #card{display:none;border-left:3px solid var(--accent);padding-left:12px}
  body.hascard #card{display:block} body.hascard #none{display:none}
  body.hot #card{border-left-color:var(--hot)}
  #k{font-size:10px;letter-spacing:.16em;color:var(--accent);margin-bottom:5px}
  body.hot #k{color:var(--hot)}
  #cb p{margin:0 0 4px;font-size:21px;line-height:1.35;font-weight:600;color:#f0e6d2}
  body.hot #cb p{color:#ffd9d6}
  #cb p:last-child{margin-bottom:0}
  #q{color:var(--faint);font-size:11px;margin-top:5px}

  @media (max-width:820px){
    .say{font-size:23px} details.br .bd{font-size:17px}
    #mid{padding:11px 14px 14px} #bot{padding:8px 14px;min-height:78px}
    #cb p{font-size:18px} .chip .t{font-size:11px} .chip .w{font-size:9px}
  }

  /* ---------- 和風テーマ (?theme=washitsu のときだけ body[data-theme] が付く。
     既定(属性なし)は下のルールが一切マッチしないので見た目は不変。 ---------- */
  body[data-theme="washitsu"]{
    --bg:#150d09; --line:#5c3a1e;
    --fg:#f1e6d2; --dim:#c9a97a; --faint:#8a6a48;
    --accent:#b3401f; --hot:#b3401f;
    font-family:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif;
  }
  body[data-theme="washitsu"] #top,
  body[data-theme="washitsu"] #bot{
    --panel:#f3ead4; --fg:#2a1912; --dim:#6b4e2e; --faint:#8a6a48; --line:#caa06a;
  }
  body[data-theme="washitsu"] #top{border-bottom-color:#b3401f55}
  body[data-theme="washitsu"] #h,
  body[data-theme="washitsu"] .hd,
  body[data-theme="washitsu"] .chip .t,
  body[data-theme="washitsu"] #k,
  body[data-theme="washitsu"] #cb p{
    font-family:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif;
  }
  body[data-theme="washitsu"] #h{border-bottom:1px solid #d4af3766;padding-bottom:8px}
  /* 以下、元がハードコード色の要素だけ個別上書き(それ以外は上のCSS変数で自動追従) */
  body[data-theme="washitsu"] .chip{background:#efe3c8;color:#5c4326}
  body[data-theme="washitsu"] .chip.on{background:#f7ecd0;border-color:#b3401f;color:#2a1912;
    box-shadow:inset 0 0 0 1px #d4af37}
  body[data-theme="washitsu"] .chip.on .w{color:#5c4326}
  body[data-theme="washitsu"] .sb{background:#efe3c8;color:#5c4326}
  body[data-theme="washitsu"] .sb.on{background:#f7ecd0;border-color:#b3401f;color:#2a1912}
  body[data-theme="washitsu"] #stopen{background:#b3401f;color:#fdf3e2;border-color:#7a2812}
  body[data-theme="washitsu"] #cb p{color:#2a1912}
  body[data-theme="washitsu"].hot #cb p{color:#7a1810}
  body[data-theme="washitsu"] #none{color:#d8c7a0}
  /* お品書き風の段番号: 「1.」はfont-size:0で見た目の場所だけ潰し、counterで「一、」を
     ::before に通常フローで差し込む(絶対配置にすると後続文字と重なるので使わない)。 */
  body[data-theme="washitsu"] #bar{counter-reset:chipnum}
  body[data-theme="washitsu"] .chip{counter-increment:chipnum}
  body[data-theme="washitsu"] .chip .num{font-size:0;letter-spacing:0}
  body[data-theme="washitsu"] .chip .num::before{
    font-size:13px;white-space:nowrap;
    content:counter(chipnum, cjk-decimal) "、";color:var(--accent);font-weight:700;
  }
  @media (min-width:1200px){
    .say{font-size:31px} #cb p{font-size:23px}
  }
</style></head><body>
<div id="top">
  <div id="bar"></div>
  <div id="meta">
    <span id="pos"></span><span id="unmet"></span>
    <span id="manual">▸ 自動に戻す</span><span id="clock" class="mono"></span>
  </div>
  <div id="stage">
    <button id="stopen">🎭 舞台を開く</button>
    <span id="stnow">舞台: <b>—</b></span>
    <span id="stbtns"></span>
  </div>
</div>
<div id="mid">
  <div id="h"></div>
  <div id="blk"></div>
  <div id="musts"></div>
</div>
<div id="bot">
  <div id="none">—</div>
  <div id="card"><div id="k"></div><div id="cb"></div><div id="q"></div></div>
</div>
<script>
const BLOCKS = __BLOCKS__;
const STAGE  = __STAGE__;
const $=s=>document.querySelector(s);
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function ttl(s){return esc((s||'').replace(/^[①②③④⑤⑥⑦⑧⑨⑩\s　]+/,''))}
const KIND={call:'照会への回答',topic:'進行',warn:'確認',wrap:'注意',script:'進行メモ',premise_warn:'前提ズレ',premise_ok:'既知',premise_new:'新情報'};

let state=null, shown=-1, navCur=-1, manual=null, startEpoch=null, totalMin=60;

/* ---- 舞台: 名前付きの別窓を航行させる (新しい窓は作らない) ---- */
let stageOpened=false, stageTs=null, stageUrl='/stage/blank', navUrl=null, stageWin=null;
function stageGo(url, force){
  if(!url) return;
  if(!force){ if(!stageOpened || url===navUrl) return; }
  navUrl=url;
  /* 開いた窓の手綱が残っていればそれを航行させる(ポップアップ判定を通らない)。
     頁を再読込した後や窓を閉じた後は名前で開き直す。 */
  try{
    if(stageWin && !stageWin.closed){ stageWin.location.href=url; return; }
  }catch(e){}
  try{ stageWin=window.open(url,'meetlive_stage'); }catch(e){}
}
function stagePick(res){
  const s=STAGE.filter(function(x){return x.res===res})[0]; if(!s) return;
  if(!s.url) return;                 /* 予備枠(free)にURLが入るまでは押せない */
  stageOpened=true; stageGo(s.url,true);
  fetch('/stage/set?res='+encodeURIComponent(res))
    .then(function(r){return r.json()})
    .then(function(j){ if(j&&j.ts) stageTs=j.ts; })
    .catch(function(){});
}
$('#stbtns').innerHTML=STAGE.map(function(s){
  return '<button class="sb" data-res="'+s.res+'">'+esc(s.btn)+'</button>';
}).join('');
document.querySelectorAll('.sb').forEach(function(el){
  el.addEventListener('click',function(){ stagePick(el.dataset.res); });
});
$('#stopen').addEventListener('click',function(){
  stageOpened=true; stageGo(stageUrl,true);
});
function drawStage(st){
  if(!st) return;
  stageUrl=st.url;
  $('#stnow').innerHTML='舞台: <b>'+esc(st.label)+'</b>';
  /* 予備枠は走行中に外から差し込まれる。ボタンの行き先を毎回貼り替える */
  const f=STAGE.filter(function(x){return x.res==='free'})[0];
  if(f) f.url=st.free||'';
  document.querySelectorAll('.sb').forEach(function(el){
    el.classList.toggle('on', el.dataset.res===st.res);
    if(el.dataset.res==='free'){
      el.classList.toggle('off', !st.free);
      el.textContent = st.free_label || '予備枠';
    }
  });
  if(stageTs===null){ stageTs=st.ts; navUrl=st.url; return; }  /* 初回は開かない */
  if(st.ts!==stageTs){ stageTs=st.ts; stageGo(st.url,false); }
}

/* ---- 中段: 台本ブロック ---- */
function drawBlock(i){
  const b=BLOCKS[i]; if(!b) return;
  $('#h').innerHTML='<b>【'+b.n+'】'+ttl(b.title)+'</b>'
    +(b.nudge?' — '+esc(b.nudge):'')+(b.src==='台本'?'':' <span>（段取りの要点）</span>');
  $('#blk').innerHTML=b.items.map(function(it){
    if(it.t==='say')    return '<p class="say">'+esc(it.s)
      +(it.sub?'<span class="sub">'+esc(it.sub)+'</span>':'')+'</p>';
    if(it.t==='head')   return '<div class="hd">'+esc(it.s)+'</div>';
    if(it.t==='branch') return '<details class="br"><summary>'+esc(it.s)+'</summary>'
      +'<div class="bd">'+esc(it.b)+'</div></details>';
    return '<p class="nt">'+esc(it.s)+'</p>';
  }).join('');
  $('#mid').scrollTop=0;
  shown=i;
  document.querySelectorAll('.chip').forEach(function(c,j){
    c.classList.toggle('on', j===i);
  });
}

/* ---- 上段 ---- */
function drawBar(nav){
  const bar=$('#bar');
  if(bar.children.length!==nav.chips.length){
    bar.innerHTML=nav.chips.map(function(c,j){
      return '<div class="chip" data-i="'+j+'"><div class="t"><span class="num">'+c.n+'.</span> '+esc(c.short)
        +'</div><div class="w mono">'+c.from+'-'+c.to+'</div><span class="m"></span></div>';
    }).join('');
    bar.querySelectorAll('.chip').forEach(function(el){
      el.addEventListener('click',function(){
        manual=+el.dataset.i; document.body.classList.add('manual'); drawBlock(manual);
      });
    });
  }
  bar.querySelectorAll('.chip').forEach(function(el,j){
    const c=nav.chips[j];
    el.querySelector('.m').textContent = c.unmet ? '⚠' : '';
    el.classList.toggle('due', !!c.due);
  });
}

function drawMusts(nav){
  $('#musts').innerHTML = (nav.musts||[]).length
    ? nav.musts.map(function(m){
        return m.ok ? '<span class="y"><i>✓</i> '+esc(m.name)+'</span>'
                    : '<span class="n">□ <b>'+esc(m.name)+'</b></span>';
      }).join('')
    : '<span class="y">この段で取るものはありません</span>';
}

function tick(){
  if(startEpoch==null) return;
  const el=(Date.now()/1000-startEpoch)/60;
  const now=new Date();
  const hm=('0'+now.getHours()).slice(-2)+':'+('0'+now.getMinutes()).slice(-2);
  $('#clock').textContent = el<0
    ? hm+'  開始前 あと'+Math.ceil(-el)+'分'
    : hm+'  '+Math.floor(el)+'分経過 / 残'+Math.max(0,Math.ceil(totalMin-el))+'分';
}

function render(d){
  state=d; const nav=d.nav, c=d.card;
  startEpoch=d.start_epoch; totalMin=d.total_min;
  drawStage(d.stage);

  if(nav){
    drawBar(nav); drawMusts(nav);
    // 中段が段の名前を出すので、ここは「予定とのズレ」だけを出す
    const due=nav.chips.filter(function(c){return c.due})[0];
    $('#pos').innerHTML = nav.waiting ? '開始前・【1】を待機'
      : (due && due.n!==nav.i ? '予定では<b>【'+due.n+'】'+ttl(due.title)+'</b>' : '');
    $('#unmet').innerHTML = nav.unmet.length
      ? '　未取得 <b>'+nav.unmet.length+'</b>: '+esc(nav.unmet.slice(0,2).join(' / '))
      : '';
    if(nav.cur!==navCur){            // 段が進んだら自動で次のブロックへ
      navCur=nav.cur; manual=null; document.body.classList.remove('manual');
      drawBlock(navCur);
    }else if(manual===null && shown!==nav.cur){
      drawBlock(nav.cur);
    }
    drawMusts(nav);
  }else if(shown<0){
    $('#pos').textContent='開始前・【1】を待機';
    drawBlock(0);
  }
  tick();

  const hot = !!c && (c.kind==='warn' || c.kind==='premise_warn');
  document.body.classList.toggle('hascard', !!c);
  document.body.classList.toggle('hot', hot);
  if(c){
    $('#k').textContent = c.confidence==='none' ? '該当なし' : (KIND[c.kind]||'');
    $('#cb').innerHTML=(c.confidence==='none'
      ? ['手元に資料がありません。','確認して後ほど回答、と伝えてください。']
      : (c.lines||[]).slice(0,3)).map(function(l){return '<p>'+esc(l)+'</p>'}).join('');
    $('#q').textContent = c.q ? '（'+c.q+'）' : '';
  }
}

$('#manual').addEventListener('click',function(){
  manual=null; document.body.classList.remove('manual');
  if(state&&state.nav) drawBlock(state.nav.cur);
});

drawBlock(0);
setInterval(tick,1000);
let tok='';
async function loop(){
  for(;;){
    try{
      const r=await fetch('/state?wait=1&tok='+encodeURIComponent(tok));
      const d=await r.json(); tok=d.tok; render(d);
    }catch(e){ $('#pos').textContent='接続待ち'; await new Promise(r=>setTimeout(r,1500)); }
  }
}
loop();
</script></body></html>
"""


def render_page(blocks, theme: str = "") -> bytes:
    js = json.dumps(blocks, ensure_ascii=False).replace("</", "<\\/")
    cat = json.dumps(
        [{"res": r, "label": STAGE_RES[r]["label"], "btn": STAGE_RES[r]["btn"],
          "url": res_url(r)} for r in STAGE_ORDER],
        ensure_ascii=False,
    ).replace("</", "<\\/")
    html = PAGE.replace("__BLOCKS__", js).replace("__STAGE__", cat)
    # ?theme=washitsu のときだけ <body> に data-theme を足す。既定(theme="")は無改変。
    if theme == "washitsu":
        html = html.replace("<body>", '<body data-theme="washitsu">', 1)
    return html.encode("utf-8")


# ---------------------------------------------------------------- 舞台の頁
# 共有されるのはこの窓だけ。余計な線・文字・ポーリングを置かない。

STAGE_BLANK = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>打合せ中</title><style>
html,body{height:100%;margin:0;background:#000;color:#1e2229;
  font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic UI",system-ui,sans-serif;
  display:flex;align-items:center;justify-content:center}
p{font-size:4vw;letter-spacing:.5em;margin:0;user-select:none}
</style></head><body><p>打合せ中</p></body></html>"""

STAGE_IMG_PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
html,body{height:100%;margin:0;background:#fff}
img{width:100%;height:100%;object-fit:contain;display:block}
</style></head><body><img src="__SRC__" alt="__TITLE__"></body></html>"""


def render_img_page(src: str, title: str) -> bytes:
    return (STAGE_IMG_PAGE.replace("__SRC__", src)
            .replace("__TITLE__", title)).encode("utf-8")


# ---------------------------------------------------------------- 起動

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0", help="携帯ディスプレイから見るので既定で外に開く")
    ap.add_argument("--port", type=int, default=47323)
    ap.add_argument("--outdir", default="")
    ap.add_argument("--start", default="",
                    help="会議の開始予定 (例 2026-01-20T15:00:00)。番人 copilot.py と同じ値を渡すこと。"
                         "未指定なら起動時刻")
    ap.add_argument("--total-min", type=float, default=None, help="既定は段取りJSONの会議分")
    a = ap.parse_args()
    global OUTDIR
    outdir = OUTDIR = pathlib.Path(a.outdir) if a.outdir else STATE_DIR
    outdir.mkdir(parents=True, exist_ok=True)
    if a.start:
        try:
            start_epoch = datetime.fromisoformat(a.start).timestamp()
        except ValueError:
            raise SystemExit(f"--start が読めません: {a.start} (例 2026-01-20T15:00:00)")
    else:
        start_epoch = time.time()
        print("--start 未指定。起動時刻を会議開始として扱います", flush=True)

    agenda = load_agenda(AGENDA_PATH)
    scripts = parse_script(SCRIPT_PATH)
    blocks = build_blocks(agenda, scripts)
    n_script = sum(1 for b in blocks if b["src"] == "台本")
    print(f"台本ブロック: {n_script}/{len(blocks)} 段を {SCRIPT_PATH.name} から抽出 "
          f"(残りは段取りJSONの台本行)", flush=True)
    print(f"舞台の資源: {len(STAGE_ORDER)}件 {STAGE_ORDER}", flush=True)

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send(self, body, ctype, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # ---- 舞台 -------------------------------------------------------
        def _stage(self):
            from urllib.parse import parse_qs, unquote, urlparse

            u = urlparse(self.path)
            p = u.path.rstrip("/") or "/stage"

            if p == "/stage/state":
                self._send(json.dumps(stage_view(), ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
            if p == "/stage/set":
                q = parse_qs(u.query)
                res = q.get("res", [""])[0]
                if res == "free":
                    url = q.get("url", [""])[0]
                    label = q.get("label", [""])[0]
                    if url:
                        save_free(url, label)
                    elif label:
                        save_free(res_url("free"), label)
                ok = bool(res != "free" or res_url("free")) and \
                    stage_set(res, "manual", "ボタン")
                body = stage_view()
                body["ok"] = ok
                if not ok:
                    body["known"] = STAGE_ORDER
                    if res == "free":
                        body["hint"] = "free は url= を渡すか stage_urls.json の free を先に設定"
                self._send(json.dumps(body, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
            if p in ("/stage", "/stage/blank"):
                self._send(STAGE_BLANK.encode("utf-8"), "text/html; charset=utf-8")
                return
            if p.startswith("/stage/png/"):
                name = unquote(p[len("/stage/png/"):])
                if name not in STAGE_IMG:
                    self._send(b"unknown image", "text/plain; charset=utf-8", 404)
                    return
                self._send(render_img_page("/stage/img/" + name, res_label(name)),
                           "text/html; charset=utf-8")
                return
            if p.startswith("/stage/img/"):
                name = unquote(p[len("/stage/img/"):])
                fp = STAGE_IMG.get(name)
                if fp is None or not fp.exists():
                    self._send(b"no image", "text/plain; charset=utf-8", 404)
                    return
                try:
                    self._send(fp.read_bytes(), "image/png")
                except OSError:
                    self._send(b"read error", "text/plain; charset=utf-8", 500)
                return
            self._send(b"no such stage", "text/plain; charset=utf-8", 404)

        def do_POST(self):
            if self.path.startswith("/stage"):
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n:
                        self.rfile.read(n)
                except (TypeError, ValueError):
                    pass
                self._stage()
                return
            self._send(b"not found", "text/plain; charset=utf-8", 404)

        def do_GET(self):
            if self.path.split("?")[0].rstrip("/") == "/quit":
                # 差し替えのための自主降板。外から止められると事故るので手元からだけ
                if self.client_address[0] not in ("127.0.0.1", "::1", "localhost"):
                    self._send(b"local only", "text/plain; charset=utf-8", 403)
                    return
                self._send(b"bye", "text/plain; charset=utf-8")
                try:
                    self.wfile.flush()
                except OSError:
                    pass
                print(f"/quit を受けたので降板 pid={os.getpid()}", flush=True)
                threading.Timer(0.3, os._exit, [0]).start()
                return
            if self.path.startswith("/stage"):
                self._stage()
                return
            if not self.path.startswith("/state"):
                from urllib.parse import parse_qs as _pq, urlparse as _up
                # 台本mdを読み直してから配る (直前の差し替えが再読込で効く)
                bl = build_blocks(load_agenda(AGENDA_PATH), parse_script(SCRIPT_PATH)) or blocks
                theme = _pq(_up(self.path).query).get("theme", [""])[0]
                self._send(render_page(bl, theme), "text/html; charset=utf-8")
                return
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            if q.get("wait", ["0"])[0] == "1":
                old = q.get("tok", [""])[0]
                deadline = time.time() + 25
                while time.time() < deadline and token(outdir) == old:
                    time.sleep(0.1)
            # 段取りJSONは起動時に1回だけ読む（番人 copilot.py と同じ扱い。
            # ここだけ読み直すと、番人が持つ古いキーワードと段の判定がズレる）
            state = build_state(outdir, agenda, start_epoch, a.total_min)
            # 振り返り用 (action_log.py の材料): 表示対象が変わった瞬間だけ残す
            try:
                sig = json.dumps({"card": state.get("card"), "nav": state.get("nav"),
                                  "stage": (state.get("stage") or {}).get("res")},
                                 ensure_ascii=False, sort_keys=True)
                if sig != getattr(self.server, "_last_disp_sig", None):
                    self.server._last_disp_sig = sig
                    with open(outdir / "display_log.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
                            "client": self.client_address[0],
                            "card": state.get("card"), "nav": state.get("nav"),
                            "stage": state.get("stage"),
                            "mode": state.get("mode"), "live": state.get("live"),
                            "v": 2,
                        }, ensure_ascii=False) + "\n")
            except Exception:
                pass
            self._send(json.dumps(state, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")

    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    print(f"meetlive viewer2: http://{a.host}:{a.port}  ({outdir})", flush=True)
    S((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
