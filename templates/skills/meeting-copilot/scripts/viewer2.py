"""
meetlive 表示側 v2 — 「画面が会議を運転する」テレプロンプター

進行役は台本を読むだけで会議が終わり、脱線したときだけ助けが出る、という道具。

画面の3つの区画 (携帯ディスプレイ横置き・暗い背景・大きい文字):
  上段 = 今日の段【1】〜【N】を横一列。いまの段だけ明るい。予定時刻と経過。取り漏れは⚠
         + 稼働ライン(受信・逐語・心拍) + 舞台の操縦席 + 資料棚/鍵パネル
  台本 = いまの段の台本ブロックをそのまま。読み上げる文は大きく。分岐▸は畳んである
  カード列 = 番人/返し役のカードを積む。warn=赤 / それ以外=琥珀 / 無ければ「—」

並べ方は meeting.json の ``layout``:
  columns … 左=台本6割 / 右=カード列4割 (2026-09-04 実機確認の既定。カードが台本を潰さない)
  rows    … 上=台本 / 下=カード列 (縦長の画面向き)
  auto    … 横長なら columns、縦置き・狭い画面なら rows へ自動で退避

段の判定は copilot.py (番人) と**同じ規則**で計算する。番人は cur をファイルに出さないので、
こちらでも同じ材料 (transcript.jsonl) から同じ式で出す。ここがズレると、カードに書かれた
段番号と上段の段番号が食い違って見えるので、規則は番人に合わせる:
  - 段の検知キーワードはこちら側(host)の発話のみ / 必須取得物は両者の発話
  - 「<呼びかけ語>、次/戻って」は先頭6文字の一致で ±1
  - 経過時間は --start から (番人が「<呼びかけ語>、時間」に答えるのと同じ基準)

--- カードの消え方 (2026-09-04 改修) ---
カードは自動で消さない。消えるのは進行役が「済」(または Esc) を押したときだけで、
押した事実はサーバ側 (dismissed.jsonl) に残るので再読込しても復活しない。
例外は meeting.json の ``card_policy.auto_dismiss_kinds`` に挙げた種別 (既定 warn /
premise_warn) — 取り漏れが解消したら黙って消えてほしいので、従来どおり自然に引っ込む。

--- 舞台(相手に見せる別窓) ---
進行役はPCを触らない。共有するのは「名前付きの別窓 meetlive_stage」1枚だけで、
その中身をこの画面のJSが window.open(url, 'meetlive_stage') で航行させる。
iframe は使えない (相手先サイトが x-frame-options: DENY だったり、ログイン cookie が
SameSite=lax だったりして中身が出ない)。切り替えの出所は3つ。いちばん新しい ts が勝つ:
  auto   = 段の遷移 (資源表の "auto")。遷移した瞬間に1回だけ。同じ段では二度と上書きしない
  voice  = copilot.py が stage_cmd.jsonl に書く音声指令
  manual = この画面のボタン列 (/stage/set?res=)
出すボタンと順番は meeting.json の ``stage.order`` / ``stage.set_label``。
個々のURLは走行中に ``<state>/stage_urls.json`` で差し替えられる (そちらが勝つ)。

起動:
    MEETLIVE_MEETING=/path/to/meetings/2026-01-20-acme \\
      python3 viewer2.py --start 2026-01-20T15:00:00 >> viewer2.log 2>&1 &
携帯ディスプレイから見るときは、この機体の LAN / VPN のアドレス + --port で開く。
止めるときは kill ではなく手元から ``curl localhost:<port>/quit``。

カードの受け渡し仕様 (cards.jsonl) は copilot.py 冒頭が正本。こちらは読むだけ。
"""
from __future__ import annotations

import argparse
import bisect
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
import mode_signal  # noqa: E402
import step_detect  # noqa: E402

STATE_DIR = cfgmod.state_dir()
AGENDA_PATH = cfgmod.input_path("MEETLIVE_AGENDA", "agenda_steps.example.json", required=True)
SCRIPT_PATH = cfgmod.input_path("MEETLIVE_SCRIPT", "talk_script.example.md", required=True)

# カードは自動で消さない(「済」を押すまで残す)。自動消去が残るのは
# card_policy.auto_dismiss_kinds に挙げた種別だけ — 取り漏れの警報は、解消したら
# 黙って消えてほしいので。既定値の出どころは meetlive_config.card_policy()。
_CARD = cfgmod.card_policy()
CARD_TTL = _CARD["ttl_sec"]          # 自動消去する種別を出しておく既定の秒数
CARD_MAX_TURNS = _CARD["max_turns"]  # このぶん会話が進んだら引っ込める
CARD_MIN_SHOW_SEC = _CARD["min_show_sec"]
                          # turns条件に関わらず、出してから最低これだけは表示する
                          # (実測: 会話が速い区間だと、書かれてから最初のポーリングが
                          #  来る前に turns 条件で死に、1回も画面に出ないカードがあった)
AUTO_DISMISS_KINDS = _CARD["auto_dismiss_kinds"]   # ここだけ自動で消える
CARD_STACK_MAX = _CARD["stack_max"]    # /state が返すカードの上限 (カード列に全部並べる)
CARD_HISTORY_MAX = _CARD["history_max"]  # 「履歴」トグルに出す済カードの上限
DISMISS_FILE = "dismissed.jsonl"     # 「済」の永続化 (build_state は毎回再計算するため)
DOCS_DIR = cfgmod.docs_dir()         # 資料棚 (手元だけ・共有窓には出さない)
DOC_SUFFIXES = (".md", ".txt", ".html", ".htm")
# 合言葉は**会議フォルダに置かない**。MEETLIVE_CREDS_FILE で外を指す (未設定なら鍵パネル無し)
SECRETS_PATH = cfgmod.creds_file()
CREDS_LABEL = cfgmod.creds_label()
LAYOUT = cfgmod.layout()             # columns / rows / auto
HEARTBEAT_PATH = cfgmod.heartbeat_path()
STOP_FILE = cfgmod.stop_file()       # 全層が共通で見る停止ファイル (kill を使わないため)
HEARTBEAT_STALE = cfgmod.heartbeat_stale_sec()

CALL_WORDS = cfgmod.call_words()
MODE_START_WORD, _MODE_END_WORD, START_HOMOPHONES = cfgmod.mode_words()

_KW_RE_CACHE: dict[str, "re.Pattern | None"] = {}


def kw_hit(kw: str, blob: str) -> bool:
    """検知キーワードを正規表現として当てる(2026-08-18評価: 文字列の部分一致では
    「帳票bのレイアウトで」が『案Bで』等のどれにも当たらず見逃した)。
    キーワードに正規表現の特殊文字が無ければ従来どおりの部分一致と同じ結果になるので、
    既存の agenda_steps の平文キーワードは無改変で動く。壊れた正規表現は部分一致へ退避。"""
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
# 資源表(stage_resources.json)がこの一覧の正本。コードは案件の URL を1つも持たない。
#   url が "/" 始まりなら自分が配る頁 (この画面と同じホストで開くので相対のまま使う)
#   img を書いた資源は /stage/png/<res> として画像1枚の頁を配る
STAGE_CFG = cfgmod.load_stage()
STAGE_ORDER = [r["res"] for r in STAGE_CFG["resources"]]
STAGE_RES: dict[str, dict] = {}
STAGE_IMG: dict[str, pathlib.Path] = {}
for _r in STAGE_CFG["resources"]:
    _url = _r["url"]
    _img = cfgmod.resolve_img(_r["img"])
    if _img is not None:
        STAGE_IMG[_r["res"]] = _img
        if not _url:
            _url = "/stage/png/" + _r["res"]
    if not _url:
        _url = "/stage/blank" if _r["res"] == "blank" else ""
    STAGE_RES[_r["res"]] = {"label": _r["label"], "btn": _r["btn"], "url": _url}
AUTO_STAGE = STAGE_CFG["auto"]          # 段番号(1始まり) → 資源

STAGE_CMD_FILE = "stage_cmd.jsonl"

STAGE_LOCK = threading.Lock()
STAGE = {"res": "blank", "ts": time.time(), "src": "init", "text": "",
         "last_step": None, "cmd_ts": 0.0}

# 「同席開始」ボタン (2026-08-22・主手段)。書式は receiver.py の Writer._mode_line と
# 揃える (type/mode の2キーを読む側は見ているので、それ以外は増やしても壊れない)。
MODE_LOCK = threading.Lock()

# URL だけは状態ディレクトリの stage_urls.json で差し替えられる (再起動不要)。
#   例: {"agenda": "https://example.com/agenda-2026-01-20", "slides": "https://example.com/..."}
# 会議直前にURLが変わったとき、走行中のプロセスを止めずに直すための逃げ道。
STAGE_URLS_FILE = "stage_urls.json"
OUTDIR = STATE_DIR
_URLS = {"key": None, "map": {}, "raw": {}}


_URL_KEYS = set(STAGE_RES) | {"free_label"}


def _load_stage_json() -> dict:
    """stage_urls.json を mtime でキャッシュしつつ読む。URL 差し替えと舞台セット
    (set_label / order) の両方がこのファイルに同居する。"""
    p = OUTDIR / STAGE_URLS_FILE
    try:
        key = p.stat().st_mtime_ns
    except OSError:
        _URLS["key"], _URLS["map"], _URLS["raw"] = None, {}, {}
        return {}
    if _URLS["key"] != key:
        m, raw = {}, {}
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(j, dict):
                raw = j
                m = {k: v for k, v in j.items()
                     if k in _URL_KEYS and isinstance(v, str) and v.strip()}
        except (OSError, json.JSONDecodeError, ValueError):
            m, raw = {}, {}
        _URLS["key"], _URLS["map"], _URLS["raw"] = key, m, raw
    return _URLS["raw"]


def url_overrides() -> dict:
    _load_stage_json()
    return _URLS["map"]


def stage_setinfo() -> dict:
    """今回の舞台セット = 「今日はこのボタンだけ出す」の宣言。

    **優先順位はキー単位** (設計の契約):
      - set_label / order … meeting.json の ``stage`` が正 (今日の構えは静的に決まる)
      - 個々の URL       … 走行中に外から書ける stage_urls.json が勝つ (res_url)
    meeting.json に stage が無いときだけ、後方互換で stage_urls.json の
    set_label / order も見る。どちらも無ければ資源表の全部をその順で出す。
    """
    m = cfgmod.stage_setinfo()
    label, order = m["label"], [x for x in m["order"] if x in STAGE_RES]
    if not label or not order:
        raw = _load_stage_json()
        if not label:
            lb = raw.get("set_label")
            label = lb.strip() if isinstance(lb, str) else ""
        if not order:
            o = raw.get("order")
            if isinstance(o, list):
                order = [x for x in o if isinstance(x, str) and x in STAGE_RES]
    return {"label": label[:60], "order": order or list(STAGE_ORDER),
            "custom": bool(order)}


def res_url(res: str) -> str:
    d = STAGE_RES.get(res) or STAGE_RES["blank"]
    return url_overrides().get(res) or d["url"]


def res_label(res: str) -> str:
    d = STAGE_RES.get(res) or STAGE_RES["blank"]
    if res == "free":
        return url_overrides().get("free_label") or d["label"]
    return d["label"]


def save_free(url: str, label: str = "") -> bool:
    """空き枠(free)のURL/名前を stage_urls.json へ焼く。走行中に差し込める唯一の資源。"""
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
        # ボタン列が予備枠を有効にできるよう、いまの空き枠を常に添える
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


def write_mode_start(outdir: pathlib.Path) -> str:
    """「同席開始」ボタンが押されたら呼ぶ。receiver.py の Writer._mode_line と同じ形の
    行を transcript.jsonl へ追記する — 音声で「同席開始」と言ったのと同じ効果になる
    (build_nav も copilot.py もこの1行だけを見てセッションを区切っている)。

    receiver.py (別プロセス) も同じファイルへ追記するが、1行=1write()でO_APPENDの
    追記なので競合しても行が壊れることはない。ここのロックは viewer2 自身のスレッド間
    の重複押下だけを防ぐもの。
    """
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    line = json.dumps(
        {"ts": ts, "type": "mode", "mode": "start", "src": "button"},
        ensure_ascii=False,
    )
    with MODE_LOCK:
        with (outdir / "transcript.jsonl").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return ts


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
            if res:
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
    # dismissed.jsonl = 「済」の押下、docs/ = 資料棚の増減。どちらも長ポーリングを
    # 起こさないと、押しても画面が変わらない / 追加した資料が出ない。
    for n in ("transcript.jsonl", "cards.jsonl", "partial.json", STAGE_CMD_FILE,
              DISMISS_FILE):
        p = outdir / n
        try:
            st = p.stat()
            parts.append(f"{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append("-")
    # 資料棚は状態Dirの外(会議フォルダ)にも置ける。棚の増減も長ポーリングを起こす。
    try:
        st = DOCS_DIR.stat()
        parts.append(f"{st.st_mtime_ns}:{st.st_size}")
    except OSError:
        parts.append("-")
    # 舞台はボタン(/stage/set)でもファイル無しに変わるので、状態そのものも合図に混ぜる
    with STAGE_LOCK:
        parts.append("s%.3f" % STAGE["ts"])
    return "|".join(parts)


# ------------------------------------------------- 「済」の永続化 (2026-09-04)
# カードは自動で消えない。消すのは進行役が「済」を押したときだけ。
# build_state は毎回 cards.jsonl から作り直すので、クライアント側の非表示だけでは
# 再読込で復活してしまう。押した事実をサーバ側のファイルに残す。

DISMISS_LOCK = threading.Lock()
_DISMISS = {"key": None, "set": frozenset()}


def dismissed_keys(outdir: pathlib.Path) -> frozenset:
    p = outdir / DISMISS_FILE
    try:
        key = p.stat().st_mtime_ns
    except OSError:
        _DISMISS["key"], _DISMISS["set"] = None, frozenset()
        return _DISMISS["set"]
    if _DISMISS["key"] != key:
        ks = set()
        for r in read_jsonl(p):
            k = r.get("key")
            if isinstance(k, str) and k:
                ks.add(k)
        _DISMISS["key"], _DISMISS["set"] = key, frozenset(ks)
    return _DISMISS["set"]


def dismiss_card(outdir: pathlib.Path, key: str) -> bool:
    key = (key or "").strip()
    if not key:
        return False
    line = json.dumps({"ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
                       "key": key}, ensure_ascii=False)
    try:
        with DISMISS_LOCK:
            with (outdir / DISMISS_FILE).open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError:
        return False
    _DISMISS["key"] = None          # 次の読みで確実に取り直す
    return True


def undismiss_card(outdir: pathlib.Path, key: str) -> bool:
    """履歴から戻す。dismissed.jsonl から該当キーの行を落とす(追記型の例外)。"""
    key = (key or "").strip()
    if not key:
        return False
    p = outdir / DISMISS_FILE
    rows = [r for r in read_jsonl(p) if r.get("key") != key]
    try:
        with DISMISS_LOCK:
            tmp = p.with_suffix(".jsonl.tmp")
            tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                   for r in rows), encoding="utf-8")
            tmp.replace(p)
    except OSError:
        return False
    _DISMISS["key"] = None
    return True


# ------------------------------------------------- 資料棚 (手元だけ・共有窓には出さない)
# 運用側が会議前に <会議フォルダ>/docs/ (会議フォルダを使わないなら <state>/docs/) へ
# .md/.txt/.html を書き出す。ここは「あるものを並べる」だけ。中身の用意はコードの仕事ではない。
# 置き場の決定は meetlive_config.docs_dir() が正本 (MEETLIVE_DOCS で上書きできる)。

def doc_list(outdir: pathlib.Path | None = None) -> list:
    d = DOCS_DIR
    out = []
    try:
        entries = sorted(d.iterdir(), key=lambda x: x.name)
    except OSError:
        return out
    for f in entries:
        try:
            if not f.is_file() or f.suffix.lower() not in DOC_SUFFIXES:
                continue
            st = f.stat()
        except OSError:
            continue
        out.append({
            "name": f.name,
            "title": f.stem.replace("_", " "),
            "kind": f.suffix.lower().lstrip("."),
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%m/%d %H:%M"),
            "mtime_epoch": int(st.st_mtime),
            "bytes": st.st_size,
            "url": "/doc/" + f.name,
        })
    return out


def doc_path(name: str, outdir: pathlib.Path | None = None):
    """パス遡上を塞ぐ。docs/ 直下・許可拡張子のファイルだけ。

    `..%2f` などで棚の外へ出ようとした要求は None (呼び出し側が 404 を返す)。
    親ディレクトリが棚そのものであることを resolve 後に確認しているので、
    シンボリックリンク経由の抜け道も塞がる。
    """
    try:
        d = DOCS_DIR.resolve()
    except OSError:
        return None
    try:
        fp = (d / name).resolve()
    except OSError:
        return None
    if fp.parent != d or fp.suffix.lower() not in DOC_SUFFIXES:
        return None
    if not fp.is_file():
        return None
    return fp


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _md_inline(s: str) -> str:
    """エスケープしてから、その上に最小の装飾だけ戻す(外部ライブラリ不可)。"""
    s = _esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"(?<![\"'>=])(https?://[^\s<>\"）)]+)",
               r'<a href="\1" target="_blank" rel="noopener">\1</a>', s)
    return s


DOC_CSS = """html,body{margin:0;background:#12151a;color:#e8ecf2;
 font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic UI",system-ui,sans-serif;
 line-height:1.7;font-size:17px}
.wrap{max-width:860px;margin:0 auto;padding:22px 20px 80px}
.meta{color:#8b93a1;font-size:12px;border-bottom:1px solid #2a2f39;padding-bottom:8px;
 margin-bottom:18px}
h1{font-size:26px;margin:22px 0 10px} h2{font-size:22px;margin:24px 0 8px;
 border-top:1px solid #2a2f39;padding-top:14px} h3{font-size:18px;margin:18px 0 6px;
 color:#c79a4a}
p{margin:0 0 12px} ul,ol{margin:0 0 12px 1.2em;padding:0} li{margin:0 0 5px}
code{background:#1b1f27;color:#f0d9a4;padding:1px 5px;border-radius:4px;font-size:.92em}
pre{background:#1b1f27;border:1px solid #2a2f39;border-radius:6px;padding:12px;
 overflow-x:auto} pre code{background:none;padding:0;color:#cfd6e1}
table{border-collapse:collapse;margin:0 0 14px;width:100%}
th,td{border:1px solid #2a2f39;padding:6px 9px;text-align:left;font-size:15px}
th{background:#1b1f27;color:#c79a4a}
a{color:#7fb2ff} blockquote{border-left:3px solid #c79a4a;margin:0 0 12px;
 padding:2px 0 2px 12px;color:#b6bdc9}
hr{border:0;border-top:1px solid #2a2f39;margin:18px 0}"""


def md_to_html(text: str) -> str:
    """見出し・箇条書き・表・コードブロック程度の簡易変換(外部ライブラリなし)。"""
    out, lines = [], text.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    list_tag = None

    def close_list():
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    while i < n:
        ln = lines[i]
        st = ln.strip()
        if st.startswith("```"):
            close_list()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + _esc("\n".join(buf)) + "</code></pre>")
            continue
        if not st:
            close_list()
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", st)
        if m:
            close_list()
            lv = min(len(m.group(1)), 3)
            out.append(f"<h{lv}>{_md_inline(m.group(2))}</h{lv}>")
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", st):
            close_list()
            out.append("<hr>")
            i += 1
            continue
        if st.startswith("|"):
            close_list()
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            sep = 1 if len(rows) > 1 and all(set(c) <= set("-: ") and c for c in rows[1]) else 0
            out.append("<table>")
            for r_i, cells in enumerate(rows):
                if sep and r_i == 1:
                    continue
                tag = "th" if (sep and r_i == 0) else "td"
                out.append("<tr>" + "".join(
                    f"<{tag}>{_md_inline(c)}</{tag}>" for c in cells) + "</tr>")
            out.append("</table>")
            continue
        m = re.match(r"^[-*+]\s+(.*)$", st)
        if m:
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append(f"<li>{_md_inline(m.group(1))}</li>")
            i += 1
            continue
        m = re.match(r"^\d+[.)]\s+(.*)$", st)
        if m:
            if list_tag != "ol":
                close_list()
                out.append("<ol>")
                list_tag = "ol"
            out.append(f"<li>{_md_inline(m.group(1))}</li>")
            i += 1
            continue
        if st.startswith(">"):
            close_list()
            out.append("<blockquote>" + _md_inline(st.lstrip("> ")) + "</blockquote>")
            i += 1
            continue
        close_list()
        out.append("<p>" + _md_inline(st) + "</p>")
        i += 1
    close_list()
    return "\n".join(out)


def render_doc(fp: pathlib.Path) -> bytes:
    try:
        raw = fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return b"read error"
    mt = datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    suf = fp.suffix.lower()
    if suf in (".html", ".htm"):
        return raw.encode("utf-8")          # 出来合いのHTMLはそのまま配る
    body = md_to_html(raw) if suf == ".md" else "<pre>" + _esc(raw) + "</pre>"
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_esc(fp.name)}</title><style>{DOC_CSS}</style></head><body>"
        f'<div class="wrap"><div class="meta">{_esc(fp.name)} ・ 更新 {mt}</div>'
        f"{body}</div></body></html>"
    ).encode("utf-8")


# ------------------------------------------------- ログイン情報 (リクエスト時に読む)
# 🔴 HTMLテンプレートには絶対に埋め込まない。/creds を叩いたときだけファイルを読む。
#    共有窓 (/stage/*) はこの経路に一切触れない = 画面共有に合言葉が映らない。
#    置き場は MEETLIVE_CREDS_FILE (会議フォルダの外・gitに載らない場所)。未設定なら鍵パネル無し。
#    書式は md の表: | 用途 | URL | 合言葉 |  (見出し行と区切り行は読み飛ばす)

def read_creds() -> dict:
    """合言葉の md 表 (用途 | URL | 合言葉) をリクエストのたびに読む。"""
    out = {"ok": False, "rows": [], "src": str(SECRETS_PATH or ""), "id": "", "note": ""}
    if SECRETS_PATH is None:
        out["error"] = "MEETLIVE_CREDS_FILE が未設定です"
        return out
    try:
        text = SECRETS_PATH.read_text(encoding="utf-8")
    except OSError as e:
        out["error"] = f"読めません: {e.__class__.__name__}"
        return out
    for ln in text.splitlines():
        st = ln.strip()
        if not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if any(set(c) <= set("-: ") and c for c in cells):
            continue
        use, url, sec = cells[0], cells[1], cells[2]
        if use in ("用途",) or not re.search(r"https?://", url):
            continue
        out["rows"].append({
            "use": re.sub(r"`", "", use),
            "url": (re.search(r"https?://\S+", url).group(0)).rstrip("|` "),
            "secret": sec.strip("` "),
        })
    # 表とは別に「ID: xxxx」の1行があれば拾う(ログイン名が表に入らない書き方への対応)。
    m = re.search(r"^[-*]?\s*ID\s*[:：]\s*(\S+)", text, re.M)
    if m:
        out["id"] = m.group(1).strip("`")
    out["ok"] = bool(out["rows"])
    if not out["ok"] and "error" not in out:
        out["error"] = "表 (| 用途 | URL | 合言葉 |) の行が見つかりません"
    return out


def clean_md(s: str) -> str:
    s = re.sub(r"`+", "", s)
    s = re.sub(r"\*\*|\*", "", s)
    s = re.sub(r"^[▸\-\s•>|]+", "", s)
    return s.strip()


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
        for m in s.get("必須取得物", []) or []:
            if isinstance(m, str):
                musts.append({"name": m, "kw": [m]})
            elif isinstance(m, dict):
                musts.append({
                    "name": m.get("名前", "") or m.get("name", ""),
                    "kw": [k for k in (m.get("検知キーワード") or m.get("keywords") or []) if k],
                    "ask": m.get("問い", "") or m.get("ask", ""),
                })
        title = s.get("title", f"ステップ{i + 1}")
        steps.append({
            "id": s.get("id", str(i)),
            "title": title,
            "short": short_title(title),
            "min": float(s.get("目安分", 0) or 0),
            "kw": [k for k in (s.get("検知キーワード") or []) if k],
            "must": musts,
            "nudge": s.get("nudge", ""),
            "script": [x for x in (s.get("台本") or []) if x],
            "ask": s.get("抜けたら出す問い", "") or s.get("ask", ""),
        })
    if not steps:
        return None
    total = sum(x["min"] for x in steps)
    return {
        "steps": steps,
        "total_min": float(raw.get("会議分", 0) or total),
        "warn_at": float(raw.get("警報分", 12) or 12),
    }


def short_title(title: str, n: int = 9) -> str:
    """上段の横一列に入る長さへ。丸数字と括弧の中は落とす。"""
    t = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩\d\.\s　]+", "", title)
    t = re.sub(r"[（(].*?[）)]", "", t).strip()
    t = t or title
    return t if len(t) <= n else t[: n - 1] + "…"


# ---------------------------------------------------------------- 台本の抽出

SKIP_HEAD = ("成果", "議論の地図", "言ってはいけない", "開始前チェック")


def parse_script(path: pathlib.Path) -> dict:
    """talk_script md から【N】節ごとの「こちらが言うブロック」を取り出す。

    行の型:
      say    = 太字で始まる行 (声に出す文)。行末の（注記）は sub として小さく添える
      head   = ### の小見出し
      branch = ▸ の分岐。「→」の前が条件・後が言うこと。既定は畳む
      note   = 丸括弧のト書き・表・その他 (小さく薄く)

    さらに build_agenda.py が作る3行には役割の札を付ける (``role``):
      answer … 「取る答え:」  この段で必ず取るもの
      line   … 言い方の例。``script_mode: answers_only`` のとき**隠す**
      ask    … 「抜けたら:」  取れていないときに出す問い
    札の付いた行は、頭の「取る答え:」「抜けたら:」を落として表示する。
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
                item = {"t": "say", "s": say, "role": "line"}
                ma = re.match(r"^(抜けたら|抜けたら出す問い)\s*[:：]\s*(.*)$", say)
                if ma:
                    item["s"], item["role"] = ma.group(2).strip(), "ask"
                if sub:
                    item["sub"] = sub
                out[cur_n].append(item)
            continue

        plain = clean_md(s)
        mn = re.match(r"^(取る答え|取るもの)\s*[:：]\s*(.*)$", plain)
        if mn:
            out[cur_n].append({"t": "note", "s": mn.group(2).strip(), "role": "answer"})
            continue
        out[cur_n].append({"t": "note", "s": plain})

    return {k: v for k, v in out.items() if v}


def build_blocks(agenda, scripts: dict) -> list:
    """段(agenda)と台本節(【N】)を突き合わせて、中段に出すブロックを作る。

    ``script_mode: answers_only`` のときは「言い方の例」(role=line)を落とす。
    読み上げ用の台詞が画面にあると、そこを読もうとして会話が固くなる
    (2026-09-19 実走: 台本の特徴句40件のうち実際に口に出たのは1件で、
     進行役は結局、確認シートの流れで自分の言葉で話していた)。
    """
    blocks = []
    hide_lines = cfgmod.script_mode() == "answers_only"
    steps = (agenda or {}).get("steps") or []
    for i, s in enumerate(steps):
        items = list(scripts.get(str(i + 1), []))
        if hide_lines:
            kept = [x for x in items if x.get("role") != "line"]
            # 全部が「言い方の例」だった段は、隠すと空になる。そのときは隠さない
            # (空の段が並ぶほうが、台詞が見えるより困る)。
            if kept:
                items = kept
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
    # 開始合図の聞き取り揺れも番人と同じく吸収する。判定そのものは mode_signal.py に
    # 1本化してあり、**書く側 (receiver.py) とまったく同じ語彙・同じ述語**で当てる
    # (かつてここだけが揺れを吸収し、書く側が完全一致だったせいで、実際の会議で
    #  画面が自動で切り替わらなかった。tests/test_mode_signal.py が対称性を毎回見る)。
    anchor = None
    for r in lines:
        if r.get("type") == "mode" and r.get("mode") == "start":
            anchor = _ts(r.get("ts", ""))
    if anchor is None:
        for r in lines:
            t = r.get("text") or ""
            if r.get("speaker") == "host" and mode_signal.is_start_signal(
                t, call_words=CALL_WORDS, start_word=MODE_START_WORD,
                homophones=START_HOMOPHONES,
            ):
                anchor = _ts(r.get("ts", ""))
                break

    said = [r for r in lines if r.get("text") and (anchor is None or _ts(r.get("ts", "")) >= anchor)]
    all_blob = "\n".join(r.get("text", "") for r in said)

    # 段の判定は step_detect に1本化（番人 copilot.py とまったく同じ規則）。
    # 連結した host_blob へのキーワード一致は、雑談の1語で段が飛ぶので使わない。
    auto = step_detect.scan(steps, said, kw_hit)
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

    pending = [m for s in steps[: cur + 1] for m in s["must"] if m["kw"] and not met(m)]
    unmet = [m["name"] for m in pending]
    warn = warn_say = None
    if elapsed > 0 and unmet and remaining <= agenda["warn_at"]:
        warn = f"残り{int(remaining)}分: {unmet[0]}がまだ"
        if len(unmet) > 1:
            warn += f"（ほか{len(unmet) - 1}件）"
        # 【言うこと】= 進行表に書いた問いそのまま。無ければ段の問い、それも無ければ定型
        step_i = next((i for i, s in enumerate(steps[: cur + 1])
                       if pending[0] in s["must"]), cur)
        warn_say = (pending[0].get("ask") or steps[step_i].get("ask")
                    or f"「{unmet[0]}について、いまどうなっていますか」")

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
        "warn_say": warn_say,
        "chips": chips,
        "warn": warn,
        # 開始前の表示は時刻だけで決める。合図(同席開始)の聞き取り揺れを吸収した結果、
        # 前夜の試験発話が anchor に当たっていても 8:00 までは「開始前」と出したい。
        "waiting": elapsed < 0,
        "live": bool(anchor) and mode == "start",
    }


# ------------------------------------------------- 稼働ライン (沈黙と故障の区別)
# 「起動してもなにも表示されない」ときに、材料が来ていないのか機構が死んでいるのかを
# 画面の上段だけで見分けられるようにする。3つとも**時刻**で出す:
#   受信 … 最後に音声が届いた時刻 (latency.jsonl の末尾 / partial.json の更新)
#   逐語 … 最後に確定発話が書かれた時刻 (transcript.jsonl)
#   心拍 … 返し役/番人が書く heartbeat.json。無い / 60秒より古い = 「心拍なし」
# 心拍ファイルが無くても落ちない。3つとも「—」でもそれは異常ではなく、
# 「まだ誰も喋っていない」ことがある = だから文言で「材料なし=カードなしは設計」と添える。

def _fmt_clock(epoch: float) -> str:
    if not epoch:
        return "—"
    return datetime.fromtimestamp(epoch).strftime("%H:%M:%S")


def _last_audio_epoch(outdir: pathlib.Path) -> float:
    """受信側が最後に音を書いた時刻。ファイルの更新時刻で見る(中身は読まない)。"""
    newest = 0.0
    for n in ("partial.json", "latency.jsonl"):
        try:
            newest = max(newest, (outdir / n).stat().st_mtime)
        except OSError:
            pass
    return newest


def read_heartbeat(path: pathlib.Path | None = None) -> dict:
    """返し役/番人の心拍。無い・壊れている・古い、のどれでも落ちずに「心拍なし」を返す。

    書式: {"ts": ISO8601, "role": "responder"|"copilot", "model": str, "note": str}
    """
    p = HEARTBEAT_PATH if path is None else path
    out = {"ok": False, "age_s": None, "role": "", "model": "", "note": "", "at": ""}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return out
    if not isinstance(raw, dict):
        return out
    ts = _ts(str(raw.get("ts") or ""))
    if not ts:
        try:
            ts = p.stat().st_mtime          # ts が読めなくてもファイルの更新時刻で救う
        except OSError:
            ts = 0.0
    out["role"] = str(raw.get("role") or "")
    out["model"] = str(raw.get("model") or "")
    out["note"] = str(raw.get("note") or "")[:80]
    if ts:
        age = time.time() - ts
        out["age_s"] = round(age, 1)
        out["at"] = _fmt_clock(ts)
        out["ok"] = age <= HEARTBEAT_STALE
    return out


def watch_stop_file(poll_sec: float = 2.0) -> None:
    """停止ファイルが置かれたら自分で降りる。

    /quit は手元からしか叩けないので、番人が終話を検知したときの畳み方が無かった
    (2026-09-19 実走: 会議のあと12時間近く3プロセスが残った)。停止の合図を
    ファイル1つにして、各層が**自分で**見に行く。kill は使わない。
    """
    def loop():
        while True:
            try:
                if STOP_FILE.exists():
                    print(f"停止ファイルを見つけたので降板 pid={os.getpid()} "
                          f"({STOP_FILE})", flush=True)
                    os._exit(0)
            except Exception:       # noqa: BLE001  監視で落ちない
                pass
            time.sleep(poll_sec)

    threading.Thread(target=loop, daemon=True).start()


def build_health(outdir: pathlib.Path, lines: list) -> dict:
    """稼働ライン。画面の上段に1行で出す(文言もここで作って /state に載せる)。"""
    audio = _last_audio_epoch(outdir)
    last_line = 0.0
    for r in reversed(lines):
        if r.get("text"):
            last_line = _ts(r.get("ts", ""))
            break
    hb = read_heartbeat(outdir / "heartbeat.json")
    if hb["ok"]:
        hb_txt = f"心拍 {hb['at']}" + (f"（{hb['role']}）" if hb["role"] else "")
    elif hb["age_s"] is not None:
        hb_txt = f"心拍なし（最後 {hb['at']}・{int(hb['age_s'])}秒前）"
    else:
        hb_txt = "心拍なし（ファイルがありません）"
    return {
        "audio_at": _fmt_clock(audio),
        "line_at": _fmt_clock(last_line),
        "heartbeat": hb,
        "heartbeat_text": hb_txt,
        "text": f"受信 {_fmt_clock(audio)} ・ 逐語 {_fmt_clock(last_line)} ・ {hb_txt}",
        "note": "材料が無ければカードは出ません（それは設計どおり・故障ではありません）",
        "silent": not audio and not last_line,
    }


def build_state(outdir: pathlib.Path, agenda, start_epoch, total_min=None):
    # 逐語は切り詰めない。番人 copilot の blob は同席開始から累積で、こちらが末尾N行だけ
    # 見ると、長い会議で古い発話が窓から落ちて段が巻き戻る (✓が□に戻る・警報が誤爆する)。
    lines = read_jsonl(outdir / "transcript.jsonl")
    cards = read_jsonl(outdir / "cards.jsonl", limit=200)
    now = time.time()

    mode = "end"
    start_anchor = 0.0          # 直近の「同席開始」。これより前のカードは出さない
    for r in lines:
        if r.get("type") == "mode":
            mode = r.get("mode", "end")
            if r.get("mode") == "start":
                start_anchor = _ts(r.get("ts", ""))

    # --- 下段はスタック (2026-09-04改修) -------------------------------------
    # ・カードは自動で消えない。消えるのは「済」(dismissed.jsonl) を押したときだけ
    # ・例外は警報系 (warn / premise_warn) — 従来どおり ttl/turns で自然に引っ込む
    # ・直近の「同席開始」より前のカードは対象外 (リハの発話が本番に積み上がらない)
    dropped = dismissed_keys(outdir)
    # 発話の時刻は1回だけ作る (カード×行で strptime すると長ポーリングが詰まる)
    said_ts = sorted(_ts(r.get("ts", "")) for r in lines if r.get("text"))

    def _turns_after(cts: float) -> int:
        return len(said_ts) - bisect.bisect_right(said_ts, cts)

    def _call_q(c: dict, cts: float):
        """カード自身が q (質問文) を持っていればそれを正とする
        (2026-08-19改修: answerer/copilot が emit 時に埋め込むようになった)。
        持っていない古い形式のカードだけ、呼び出し語のtranscript行から拾う
        フォールバックへ落とす(「07:51のリハ発話で1時間固まる」バグの元だった経路)。"""
        if c.get("q"):
            return None
        q = next((r for r in reversed(lines)
                  if r.get("call") and _ts(r.get("ts", "")) <= cts), None)
        if q:
            c["q"] = q.get("text")
            return round(cts - _ts(q.get("ts", "")), 2)
        return None

    def merge_badges(items: list) -> list:
        """同じ (種別, 対象) のカードを1枚に畳む。

        番人は同じ催促を撃ち直さない（初回フルカード＋節目のバッジ）が、画面側でも
        畳んでおく。2026-09-19 の実走では同一文言のカードが960件積み上がり、
        「読む／消える」の区別そのものが意味を失った。残すのは**中身のあるほう**で、
        バッジからは件数だけを引き継ぐ。
        """
        out, seen = [], {}
        for c in items:
            key = (c.get("kind"), c.get("target") or "")
            if not key[1]:
                out.append(c)
                continue
            first = seen.get(key)
            if first is None:
                seen[key] = c
                out.append(c)
                continue
            # 件数は大きいほうを採る。本文はバッジでないほう(=最初のフルカード)を残す
            n = max(int(first.get("count") or 1), int(c.get("count") or 1))
            if first.get("badge") and not c.get("badge"):
                first.update({k: v for k, v in c.items()
                              if k in ("lines", "say", "status", "confidence")})
                first["badge"] = False
            first["count"] = n
        for c in out:
            if int(c.get("count") or 0) > 1:
                c["unresolved"] = int(c["count"])
        return out

    stack, history, call_latency = [], [], None
    for pick in reversed(cards):                    # 新しいものが先頭
        key = str(pick.get("ts") or "")
        cts = _ts(key)
        if cts < start_anchor:                      # 同席開始より前 = リハの残骸
            continue
        kind = pick.get("kind")
        c = dict(pick)
        c["key"] = key
        c["at"] = key[11:19] if len(key) >= 19 else ""
        if kind == "call":
            lat = _call_q(c, cts)
            if lat is not None and call_latency is None:
                call_latency = lat
        if key and key in dropped:
            c["done"] = True
            if len(history) < CARD_HISTORY_MAX:
                history.append(c)
            continue
        if kind in AUTO_DISMISS_KINDS:              # 警報だけは今までどおり自動で消える
            ttl = float(pick.get("ttl", CARD_TTL) or CARD_TTL)
            age = now - cts
            if not (age < ttl and (_turns_after(cts) <= CARD_MAX_TURNS
                                   or age < CARD_MIN_SHOW_SEC)):
                continue
        c["pin"] = (kind == "call")
        stack.append(c)

    stack = merge_badges(stack)
    # 呼びかけへの回答 (call) は「済」を押すまで最上段に固定する
    stack.sort(key=lambda c: 0 if c.get("pin") else 1)

    nav = build_nav(agenda, lines, mode, start_epoch, total_min)
    # 台本は中段が持つので、下段の穴埋めは取り漏れ警報だけ (v1 の script 穴埋めはしない)
    # 取り漏れが解消すれば nav["warn"] が None になり、このカードは自動で消える。
    if nav and nav["warn"]:
        # このカードも3要素で出す（番人のカードと同じ読み方にする）。
        # ここだけ lines 1本のままだと、進行役から見て「何を言えばよいか本文に無い」
        # 旧形式のカードが1枚だけ混ざる（2026-09-20 レビュー指摘）。
        w = {"kind": "warn", "lines": [nav["warn"]], "confidence": "high",
             "key": "nav:warn", "at": "", "auto": True, "to": "進行役へ",
             "target": nav["unmet"][0] if nav["unmet"] else "取り漏れ",
             "status": f"残り{nav['remaining_min']}分・まだ取れていません"
                       + (f"（ほか{len(nav['unmet']) - 1}件）"
                          if len(nav["unmet"]) > 1 else ""),
             "say": nav.get("warn_say") or nav["warn"]}
        stack.insert(sum(1 for c in stack if c.get("pin")), w)

    stack = stack[:CARD_STACK_MAX]
    card = stack[0] if stack else None

    stage_sync(outdir, nav)

    return {
        "nav": nav,
        "card": card,                   # 後方互換 (display_log の署名など)
        "cards": stack,
        "history": history,
        "docs": doc_list(),
        "stage_set": stage_setinfo(),
        "stage": stage_view(),
        "health": build_health(outdir, lines),
        "layout": LAYOUT,
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

  /* ---------- 稼働ライン: 沈黙と故障の区別 ---------- */
  /* 「起動したのに何も出ない」ときに、材料が来ていないのか機構が落ちているのかを
     ここだけで見分ける。カードが無いのは異常ではない、と文言でも言っておく。 */
  #health{display:flex;align-items:center;gap:12px;margin-top:4px;font-size:11px;
          color:var(--dim);min-height:14px;flex-wrap:wrap}
  #health .hb{color:var(--ok)}
  #health.dead .hb{color:var(--hot)}
  #health .note{color:var(--faint)}

  /* ---------- 舞台(共有する別窓)の操縦席 ---------- */
  #stage{display:flex;align-items:center;gap:8px;margin-top:6px;
         padding-top:6px;border-top:1px solid var(--line);
         overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}
  #stage::-webkit-scrollbar{display:none}
  #stopen{flex:0 0 auto;background:#3a2f18;color:#f0d9a4;border:1px solid #6b5424;
          border-radius:6px;padding:6px 12px;font-size:13px;font-weight:700;
          cursor:pointer;font-family:inherit;white-space:nowrap}
  /* 同席開始ボタン: 音声より確実な主手段(2026-08-22)。押し間違えないよう一段大きく、
     押した瞬間に見た目が変わって分かるようにする(押しっぱなし連打の防止も兼ねる)。 */
  #modestart{flex:0 0 auto;background:#173a24;color:#a8f0c0;border:1px solid #2f7a49;
          border-radius:6px;padding:9px 16px;font-size:14px;font-weight:700;
          cursor:pointer;font-family:inherit;white-space:nowrap}
  #modestart:active{transform:scale(.97)}
  #modestart:disabled{opacity:.6;cursor:default}
  #modestart.sent{background:#2f7a49;color:#eafff0;border-color:#4fae74}
  #stnow{flex:0 0 auto;font-size:12px;color:var(--dim);white-space:nowrap}
  #stnow b{color:var(--accent);font-weight:600}
  #stbtns{flex:0 0 auto;display:flex;gap:5px}
  .sb{background:#171b22;color:var(--dim);border:1px solid var(--line);border-radius:5px;
      padding:5px 9px;font-size:12px;cursor:pointer;font-family:inherit;white-space:nowrap}
  .sb.on{background:#2b3444;border-color:#4d6081;color:var(--fg)}
  .sb.off{opacity:.3}

  /* ---------- 台本とカード列の並べ方 ---------- */
  /* 既定は左右2列。左=進行ナビ+台本(60%) / 右=カード列(40%)。
     カード列が台本を押し潰す縦積みをやめた (2026-09-04 実機確認)。
     meeting.json の layout が rows なら上下、auto なら画面の向きで自動退避。 */
  #main{flex:1 1 auto;min-height:0;display:flex;align-items:stretch}
  #mid{flex:1 1 60%;min-width:0;min-height:0;overflow-y:auto;padding:14px 20px 18px;
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

  /* ---------- 資料棚 (手元だけ・共有窓には出さない) ---------- */
  #setlbl{margin-top:6px;font-size:11px;color:var(--dim);letter-spacing:.04em}
  #setlbl b{color:var(--accent);font-weight:600}
  #shelf{display:flex;align-items:center;gap:6px;margin-top:6px;padding-top:6px;
         border-top:1px solid var(--line);overflow-x:auto;scrollbar-width:none}
  #shelf::-webkit-scrollbar{display:none}
  #shelf .lb{flex:0 0 auto;font-size:11px;color:var(--dim);white-space:nowrap}
  .db{flex:0 0 auto;background:#171b22;color:var(--fg);border:1px solid var(--line);
      border-radius:5px;padding:4px 9px;font-size:12px;cursor:pointer;
      font-family:inherit;white-space:nowrap;text-decoration:none;display:inline-block}
  .db .mt{color:var(--faint);font-size:10px;margin-left:5px}
  .db.key{background:#3a2f18;color:#f0d9a4;border-color:#6b5424;font-weight:700}
  #creds{display:none;margin-top:6px;border:1px solid #6b5424;border-radius:6px;
         background:#1b1710;padding:8px 10px;font-size:13px}
  body.creds #creds{display:block}
  #creds .row{display:flex;align-items:center;gap:10px;margin:0 0 5px;flex-wrap:wrap}
  #creds .use{color:var(--dim);min-width:9em}
  #creds .sec{font-family:ui-monospace,Menlo,Consolas,monospace;background:#2a2115;
              border:1px solid #6b5424;border-radius:4px;padding:2px 8px;cursor:pointer;
              color:#f0d9a4;letter-spacing:.08em}
  #creds .op{background:#2b3444;color:var(--fg);border:1px solid #4d6081;border-radius:4px;
             padding:2px 9px;font-size:12px;cursor:pointer;font-family:inherit;
             text-decoration:none}
  #creds .nt{color:var(--faint);font-size:11px;margin-top:4px}

  /* ---------- 下段: 助け (スタック・手で消す) ---------- */
  #bot{flex:0 0 40%;min-width:0;min-height:0;border-left:1px solid var(--line);
       background:var(--panel);padding:8px 16px 14px;overflow-y:auto;
       -webkit-overflow-scrolling:touch}
  #botbar{display:flex;align-items:center;gap:10px;font-size:11px;color:var(--faint);
          margin-bottom:5px;position:sticky;top:-8px;background:var(--panel);
          padding:4px 0 5px;z-index:2}
  #histbtn{margin-left:auto;background:none;border:1px solid var(--line);color:var(--dim);
           border-radius:5px;padding:3px 9px;font-size:11px;cursor:pointer;
           font-family:inherit}
  #histbtn.on{background:#2b3444;border-color:#4d6081;color:var(--fg)}
  #none{color:#333a45;font-size:22px;letter-spacing:.3em}
  body.hascard #none{display:none}
  .cd{border-left:3px solid var(--accent);padding:2px 0 2px 12px;margin:0 0 9px}
  .cd:last-child{margin-bottom:0}
  .cd.hot{border-left-color:var(--hot)}
  .cd.pin{border:1px solid var(--hot);border-left-width:3px;border-radius:6px;
          padding:6px 10px 6px 12px;background:#241618}
  .ch{display:flex;align-items:center;gap:9px;margin-bottom:4px}
  .cd .k{font-size:10px;letter-spacing:.16em;color:var(--accent)}
  .cd.hot .k,.cd.pin .k{color:var(--hot)}
  .cd .at{font-size:10px;color:var(--faint)}
  .cd .dn{margin-left:auto;background:#171b22;border:1px solid var(--line);
          color:var(--dim);border-radius:5px;padding:3px 12px;font-size:12px;
          cursor:pointer;font-family:inherit}
  .cd .dn:active{transform:scale(.96)}
  .cd .cb p{margin:0 0 4px;font-size:21px;line-height:1.35;font-weight:600;color:#f0e6d2}
  .cd.hot .cb p,.cd.pin .cb p{color:#ffd9d6}
  .cd .cb p:last-child{margin-bottom:0}
  /* 3行固定: 対象 / 状況 / 言うこと。「言うこと」だけを大きく出す
     (進行役はそこを読み上げる。ほかの2行は、それが何の話か分かるための下地) */
  .cd .cb p>b{display:inline-block;min-width:3.6em;margin-right:7px;font-size:10px;
   letter-spacing:.14em;color:var(--faint);font-weight:600;vertical-align:2px}
  .cd .cb p.ct{font-size:15px;font-weight:600;color:#cfd6e1}
  .cd .cb p.cl{font-size:14px;font-weight:500;color:var(--faint)}
  .cd .cb p.cs{font-size:21px;font-weight:700}
  .cd .cb .rf{font-size:10px;color:var(--faint);letter-spacing:.06em}
  .cd .to{font-size:10px;letter-spacing:.08em;color:var(--accent);
   border:1px solid var(--line);border-radius:9px;padding:1px 7px}
  .cd .to.quiet{color:var(--faint)}
  .cd .bg{font-size:10px;letter-spacing:.06em;color:var(--hot);
   border:1px solid var(--hot);border-radius:9px;padding:1px 7px}
  #stagehelp{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;
   margin:6px 0 0;padding:7px 10px;border:1px solid var(--accent);border-radius:7px;
   background:#181c24;font-size:12px;color:#cfd6e1}
  #stagehelp b{color:var(--accent);letter-spacing:.06em}
  #stagehelp i{font-style:normal;color:var(--accent)}
  #stagehelp button{margin-left:auto;background:#171b22;border:1px solid var(--line);
   color:#cfd6e1;border-radius:6px;padding:3px 11px;font-size:12px;cursor:pointer}
  body.shdone #stagehelp{display:none}
  .cd .q{color:var(--faint);font-size:11px;margin-top:5px}
  .cd.sm .cb p{font-size:17px;font-weight:500;color:#cfd6e1}
  #hist{display:none;margin-top:8px;border-top:1px dashed var(--line);padding-top:7px}
  body.hist #hist{display:block}
  #hist .hr{font-size:13px;color:var(--faint);line-height:1.4;margin:0 0 4px;
            display:flex;gap:8px}
  #hist .hr .at{flex:0 0 auto;font-size:10px}
  #hist .hr .un{flex:0 0 auto;cursor:pointer;color:var(--dim);text-decoration:underline}

  /* layout=rows: 画面の大きさに関わらず上下に積む */
  body[data-layout="rows"] #main{flex-direction:column}
  body[data-layout="rows"] #mid{flex:1 1 auto}
  body[data-layout="rows"] #bot{flex:0 0 auto;max-height:45vh;border-left:0;
                                border-top:1px solid var(--line)}
  /* layout=auto: 縦置き・狭い画面(携帯を立てて持つ等)のときだけ縦積みへ退避する。
     layout=columns を選んだときは、狭くても左右2列のまま(選択を尊重する)。 */
  @media (max-width:900px),(orientation:portrait){
    body[data-layout="auto"] #main{flex-direction:column}
    body[data-layout="auto"] #mid{flex:1 1 auto}
    body[data-layout="auto"] #bot{flex:0 0 auto;max-height:45vh;border-left:0;
                                  border-top:1px solid var(--line)}
  }
  @media (max-width:820px){
    .say{font-size:23px} details.br .bd{font-size:17px}
    #mid{padding:11px 14px 14px} #bot{padding:8px 14px}
    .cd .cb p{font-size:18px} .chip .t{font-size:11px} .chip .w{font-size:9px}
  }
  /* 画面が低いとき(携帯横置き 1280x720 相当)は上段と行間を詰めて、
     台本本文が12行以上見える高さを確保する */
  @media (max-height:820px){
    #top{padding:4px 10px 5px}
    .chip{padding:3px 6px} .chip .t{font-size:12px} .chip .w{font-size:9px}
    #meta{margin-top:3px} #setlbl{margin-top:4px}
    #stage{margin-top:4px;padding-top:4px}
    #modestart{padding:6px 13px;font-size:13px} #stopen{padding:5px 11px}
    #shelf{margin-top:4px;padding-top:4px}
    #mid{padding:9px 16px 12px}
    .say{font-size:22px;line-height:1.38;margin:0 0 8px}
    .hd{margin:10px 0 6px;padding-top:6px} .nt{margin:0 0 6px}
    #musts{margin-top:10px;padding-top:7px}
    .cd .cb p{font-size:18px}
  }

  /* ---------- 料亭テーマ (?theme=ryotei のときだけ body[data-theme] が付く。
     既定(属性なし)は下のルールが一切マッチしないので見た目は不変。
     地(--bg)=漆黒〜焦げ茶・パネル(--panel, #top/#botのみ)=生成り・アクセント=朱。
     CSS変数の差し替えが軸だが、一部の色は元々ハードコードのため個別に上書きする。 ---------- */
  body[data-theme="ryotei"]{
    --bg:#150d09; --line:#5c3a1e;
    --fg:#f1e6d2; --dim:#c9a97a; --faint:#8a6a48;
    --accent:#b3401f; --hot:#b3401f;
    font-family:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif;
  }
  body[data-theme="ryotei"] #top,
  body[data-theme="ryotei"] #bot{
    --panel:#f3ead4; --fg:#2a1912; --dim:#6b4e2e; --faint:#8a6a48; --line:#caa06a;
  }
  body[data-theme="ryotei"] #top{border-bottom-color:#b3401f55}
  body[data-theme="ryotei"] #h,
  body[data-theme="ryotei"] .hd,
  body[data-theme="ryotei"] .chip .t,
  body[data-theme="ryotei"] .cd .k,
  body[data-theme="ryotei"] .cd .cb p{
    font-family:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif;
  }
  body[data-theme="ryotei"] #h{border-bottom:1px solid #d4af3766;padding-bottom:8px}
  /* 以下、元がハードコード色の要素だけ個別上書き(それ以外は上のCSS変数で自動追従) */
  body[data-theme="ryotei"] .chip{background:#efe3c8;color:#5c4326}
  body[data-theme="ryotei"] .chip.on{background:#f7ecd0;border-color:#b3401f;color:#2a1912;
    box-shadow:inset 0 0 0 1px #d4af37}
  body[data-theme="ryotei"] .chip.on .w{color:#5c4326}
  body[data-theme="ryotei"] .sb{background:#efe3c8;color:#5c4326}
  body[data-theme="ryotei"] .sb.on{background:#f7ecd0;border-color:#b3401f;color:#2a1912}
  body[data-theme="ryotei"] #stopen{background:#b3401f;color:#fdf3e2;border-color:#7a2812}
  body[data-theme="ryotei"] #modestart{background:#2f6b3f;color:#f3fdf5;border-color:#1f4d2c}
  body[data-theme="ryotei"] #modestart.sent{background:#3f8a54;border-color:#2f6b3f}
  body[data-theme="ryotei"] .cd .cb p{color:#2a1912}
  body[data-theme="ryotei"] .cd.hot .cb p,
  body[data-theme="ryotei"] .cd.pin .cb p{color:#7a1810}
  body[data-theme="ryotei"] .db{background:#efe3c8;color:#5c4326}
  body[data-theme="ryotei"] .db.key{background:#b3401f;color:#fdf3e2;border-color:#7a2812}
  body[data-theme="ryotei"] #none{color:#d8c7a0}
  /* お品書き風の段番号: 「1.」はfont-size:0で見た目の場所だけ潰し、counterで「一、」を
     ::before に通常フローで差し込む(絶対配置にすると後続文字と重なるので使わない)。 */
  body[data-theme="ryotei"] #bar{counter-reset:chipnum}
  body[data-theme="ryotei"] .chip{counter-increment:chipnum}
  body[data-theme="ryotei"] .chip .num{font-size:0;letter-spacing:0}
  body[data-theme="ryotei"] .chip .num::before{
    font-size:13px;white-space:nowrap;
    content:counter(chipnum, cjk-decimal) "、";color:var(--accent);font-weight:700;
  }
  /* 大きな据置きディスプレイのときだけ台本を一段大きく。
     min-height を付けないと、携帯横置き(1280x720)にもこの31pxが当たって
     台本の可視行数が11行まで落ちる(2026-09-04 headless実測)。 */
  @media (min-width:1200px) and (min-height:900px){
    .say{font-size:31px} .cd .cb p{font-size:23px}
  }
</style></head><body>
<div id="top">
  <div id="bar"></div>
  <div id="meta">
    <span id="pos"></span><span id="unmet"></span>
    <span id="manual">▸ 自動に戻す</span><span id="clock" class="mono"></span>
  </div>
  <div id="health"><span class="ln mono">受信 — ・ 逐語 — ・ 心拍なし</span>
    <span class="note">材料が無ければカードは出ません（それは設計どおり・故障ではありません）</span>
  </div>
  <div id="setlbl"></div>
  <div id="stage">
    <button id="modestart">🟢 同席開始</button>
    <button id="stopen">🎭 舞台を開く</button>
    <span id="stnow">舞台: <b>—</b></span>
    <span id="stbtns"></span>
  </div>
  <div id="shelf"><span class="lb">📁 資料棚（手元だけ・共有しません）</span>
    <button class="db key" id="credbtn">__CREDS_LABEL__</button>
    <span id="docbtns"></span>
  </div>
  <div id="creds"></div>
  <!-- 舞台の使い方。起動のたびに1回だけ出して、押したら消える。
       2026-09-19 実走の開始56秒後の実発話:「舞台が見えてるけどどうすればいんだっけ
       操作方法教えて」。手順は資源表にしか無く、進行画面には出ていなかった。 -->
  <div id="stagehelp">
    <b>舞台（相手に見せる別窓）の使い方</b>
    <span>① 「🎭 舞台を開く」を押す → 別窓が開くので、会議アプリでその窓を共有する</span>
    <span>② 出すものは右の丸ボタン、または声で「<i id="shcall">呼びかけ語</i>、〇〇を出して」</span>
    <span>③ 見せ終わったら「消す」。この画面（カンペ）は共有されません</span>
    <button id="shdone">分かった</button>
  </div>
</div>
<div id="main">
  <div id="mid">
    <div id="h"></div>
    <div id="blk"></div>
    <div id="musts"></div>
  </div>
  <div id="bot">
    <div id="botbar"><span id="botlbl"></span><button id="histbtn">履歴</button></div>
    <div id="none">—</div>
    <div id="stack"></div>
    <div id="hist"></div>
  </div>
</div>
<script>
const BLOCKS = __BLOCKS__;
const STAGE  = __STAGE__;
const CALLW  = __CALLW__;   /* 呼びかけ語(舞台の使い方に出す) */
const $=s=>document.querySelector(s);
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function ttl(s){return esc((s||'').replace(/^[①②③④⑤⑥⑦⑧⑨⑩\s　]+/,''))}
const KIND={call:'照会への回答',topic:'進行',warn:'確認',wrap:'注意',script:'進行メモ',premise_warn:'前提ズレ',premise_ok:'既知',premise_new:'新情報',reply:'相手への返し',lookup:'探し物'};

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
  if(!s.url) return;                 /* 空き枠(free)にURLが入るまでは押せない */
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

/* ---- 同席開始ボタン(主手段・2026-08-22): 音声の開始合図と同じ効果を手で起こす ---- */
$('#modestart').addEventListener('click',function(){
  const b=$('#modestart');
  b.disabled=true; b.textContent='…送信中';
  fetch('/mode/start').then(function(r){return r.json()}).then(function(j){
    b.classList.toggle('sent', !!(j&&j.ok));
    b.textContent = (j&&j.ok) ? '✓ 開始しました' : '✗ 失敗(再試行可)';
    setTimeout(function(){
      b.disabled=false; b.textContent='🟢 同席開始'; b.classList.remove('sent');
    },3000);
  }).catch(function(){
    b.textContent='✗ 通信エラー(再試行可)';
    setTimeout(function(){ b.disabled=false; b.textContent='🟢 同席開始'; },3000);
  });
});
/* ---- 稼働ライン: 受信・逐語・心拍。ここが動いていれば「沈黙」、止まっていれば「故障」 ---- */
function drawHealth(h){
  if(!h) return;
  const el=$('#health');
  el.classList.toggle('dead', !(h.heartbeat&&h.heartbeat.ok));
  el.innerHTML='<span class="ln mono">受信 '+esc(h.audio_at)+' ・ 逐語 '+esc(h.line_at)
    +' ・ <span class="hb">'+esc(h.heartbeat_text)+'</span></span>'
    +'<span class="note">'+esc(h.note)+'</span>';
}
function drawStage(st, set){
  if(set){ $('#setlbl').innerHTML='🎭 今回の舞台セット: <b>'
      +esc(set.label||(set.custom?'（名前なし）':'既定（全部）'))+'</b>'
      +(set.custom?'':' <span>— meeting.json の stage.set_label / stage.order で絞れます</span>'); }
  if(!st) return;
  stageUrl=st.url;
  $('#stnow').innerHTML='舞台: <b>'+esc(st.label)+'</b>';
  /* 空き枠は走行中に外から差し込まれる。ボタンの行き先を毎回貼り替える */
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
  drawHealth(d.health);
  drawStage(d.stage, d.stage_set);

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

  drawStack(d.cards||[], d.history||[]);
  drawShelf(d.docs||[]);
}

/* ---- 右列: カードの並び (call を上端に固定・その下は新着順・手で消す) ----
   カードは3行固定。【対象】何について / 【状況】何が起きた / 【言うこと】そのまま読む文。
   2026-09-19 の実走で、3要素そろっていたカードは1013件中14件(1.4%)しかなく、
   残りは「対象は分かるが、何が問題で何を言えばよいか本文に無い」型だった。 */
function cardHTML(c, small){
  const hot = (c.kind==='warn'||c.kind==='premise_warn');
  let body;
  if(c.confidence==='none' && !c.say){
    body = '<p class="cl"><b>状況</b>手元に資料がありません</p>'
         + '<p class="cs"><b>言うこと</b>確認して後ほどご連絡します、と伝えてください</p>';
  }else if(c.target || c.status || c.say){
    body = (c.target?'<p class="ct"><b>対象</b>'+esc(c.target)
             +(c.ref?' <span class="rf">'+esc(c.ref)+'</span>':'')+'</p>':'')
         + (c.status?'<p class="cl"><b>状況</b>'+esc(c.status)+'</p>':'')
         + (c.say?'<p class="cs"><b>言うこと</b>'+esc(c.say)+'</p>':'');
  }else{
    /* 3要素を持たない古い形式のカード(responder の返し等)は今までどおり */
    body = (c.lines||[]).slice(0,(c.kind==='reply'||c.kind==='call')?5:3)
      .map(function(l){return '<p>'+esc(l)+'</p>'}).join('');
  }
  const to = c.to || '進行役へ';
  return '<div class="cd'+(hot?' hot':'')+(c.pin?' pin':'')+(small?' sm':'')+'" data-key="'+esc(c.key||'')+'">'
    +'<div class="ch"><span class="k">'+(c.confidence==='none'&&!c.say?'該当なし':esc(KIND[c.kind]||c.kind||''))+'</span>'
    +'<span class="to'+(to==='記録のみ'?' quiet':'')+'">'+esc(to)+'</span>'
    +(c.unresolved?'<span class="bg">未解決 '+esc(String(c.unresolved))+'回</span>':'')
    +'<span class="at mono">'+esc(c.at||'')+'</span>'
    +(c.auto?'<span class="at">（解消すると自動で消えます）</span>'
            :'<button class="dn" data-key="'+esc(c.key||'')+'">済</button>')
    +'</div><div class="cb">'+body+'</div>'
    +(c.q?'<div class="q">（'+esc(c.q)+'）</div>':'')+'</div>';
}
function drawStack(cards, hist){
  const n=cards.length;
  document.body.classList.toggle('hascard', n>0);
  /* 「＋N件」は廃止。右列は縦スクロールなので全部並べる (2026-09-04 10:42) */
  document.body.classList.toggle('hot',
    cards.some(function(c){return c.kind==='warn'||c.kind==='premise_warn'}));
  $('#stack').innerHTML = cards.map(function(c,i){return cardHTML(c, i>0)}).join('');
  $('#botlbl').textContent = n ? (n+'件（新しい順・「済」で消える）') : '';
  $('#stack').querySelectorAll('.dn').forEach(function(b){
    b.addEventListener('click',function(ev){ ev.stopPropagation(); doDismiss(b.dataset.key); });
  });
  $('#hist').innerHTML = hist.length
    ? hist.map(function(c){
        return '<div class="hr"><span class="at mono">'+esc(c.at||'')+'</span>'
          +'<span>'+esc((c.lines||[]).join(' / ')).slice(0,140)+'</span>'
          +'<span class="un" data-key="'+esc(c.key||'')+'">戻す</span></div>';
      }).join('')
    : '<div class="hr">まだ「済」にしたカードはありません</div>';
  $('#hist').querySelectorAll('.un').forEach(function(b){
    b.addEventListener('click',function(){ doUndismiss(b.dataset.key); });
  });
}
function doDismiss(key){
  if(!key) return;
  const el=$('#stack').querySelector('.cd[data-key="'+key+'"]'); if(el) el.remove();
  fetch('/card/dismiss?key='+encodeURIComponent(key),{method:'POST'}).catch(function(){});
}
function doUndismiss(key){
  if(!key) return;
  fetch('/card/undismiss?key='+encodeURIComponent(key),{method:'POST'}).catch(function(){});
}
/* ---- 舞台の使い方: 起動のたびに1回だけ。押したらこのタブでは出さない ---- */
(function(){
  const el=$('#shdone'); if(!el) return;
  const call=$('#shcall');
  if(call && Array.isArray(CALLW) && CALLW.length) call.textContent = CALLW[0];
  try{ if(sessionStorage.getItem('shdone')==='1') document.body.classList.add('shdone'); }catch(e){}
  el.addEventListener('click',function(){
    document.body.classList.add('shdone');
    try{ sessionStorage.setItem('shdone','1'); }catch(e){}
  });
})();

$('#histbtn').addEventListener('click',function(){
  const on=document.body.classList.toggle('hist');
  $('#histbtn').classList.toggle('on', on);
});
/* Esc = 最上段を済に (nav 警報は自動で消えるので飛ばす) */
document.addEventListener('keydown',function(e){
  if(e.key!=='Escape') return;
  const c=((state&&state.cards)||[]).filter(function(x){return !x.auto})[0];
  if(c) doDismiss(c.key);
});

/* ---- 資料棚: 手元だけ。舞台(meetlive_stage)には絶対に流さない ---- */
let docSig='';
function drawShelf(docs){
  const sig=JSON.stringify(docs);
  if(sig===docSig) return;
  docSig=sig;
  $('#docbtns').innerHTML = docs.length
    ? docs.map(function(d){
        return '<a class="db" href="'+esc(d.url)+'" target="_blank" rel="noopener">'
          +esc(d.title)+'<span class="mt">'+esc(d.mtime)+'</span></a>';
      }).join(' ')
    : '<span class="lb">（docs/ は空です）</span>';
}
$('#credbtn').addEventListener('click',function(){
  const on=document.body.classList.toggle('creds');
  if(!on) return;
  $('#creds').textContent='読み込み中…';
  fetch('/creds').then(function(r){return r.json()}).then(function(j){
    if(!j||!j.ok){ $('#creds').textContent='合言葉ファイルが読めません'+((j&&j.error)?'（'+j.error+'）':''); return; }
    $('#creds').innerHTML = j.rows.map(function(r){
      return '<div class="row"><span class="use">'+esc(r.use)+'</span>'
        +'<a class="op" href="'+esc(r.url)+'" target="_blank" rel="noopener">開く</a>'
        +'<span class="sec" data-v="'+esc(r.secret)+'">••••</span></div>';
    }).join('')
    + (j.id ? '<div class="row"><span class="use">ID</span><span>'+esc(j.id)+'</span></div>' : '')
    + '<div class="nt">合言葉はクリックで表示・もう一度で隠す。この列は共有窓には出ません。</div>';
    $('#creds').querySelectorAll('.sec').forEach(function(el){
      el.addEventListener('click',function(){
        const shown = el.textContent!=='••••';
        el.textContent = shown ? '••••' : el.dataset.v;
      });
    });
  }).catch(function(){ $('#creds').textContent='通信エラー'; });
});

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


def render_page(blocks, theme: str = "", layout: str = "") -> bytes:
    js = json.dumps(blocks, ensure_ascii=False).replace("</", "<\\/")
    # 今回の舞台セット (meeting.json の stage.order) があればその順・そのボタンだけ。
    # 前の会議のボタンを今日の画面に出さないための絞り。指定が無ければ資源表の全部。
    order = stage_setinfo()["order"]
    cat = json.dumps(
        [{"res": r, "label": res_label(r), "btn": STAGE_RES[r]["btn"],
          "url": res_url(r)} for r in order],
        ensure_ascii=False,
    ).replace("</", "<\\/")
    lay = layout if layout in ("columns", "rows", "auto") else LAYOUT
    callw = json.dumps(list(CALL_WORDS), ensure_ascii=False).replace("</", "<\\/")
    html = (PAGE.replace("__BLOCKS__", js).replace("__STAGE__", cat)
            .replace("__CALLW__", callw)
            .replace("__CREDS_LABEL__", _esc(CREDS_LABEL))
            .replace("<body>", f'<body data-layout="{_esc(lay)}">', 1))
    # ?theme=ryotei のときだけ <body> に data-theme を足す。既定(theme="")は無改変のまま
    # PAGE を返す(replace自体を呼ばないので、既定の見た目・バイト列は元の経路と同一)。
    if theme == "ryotei":
        html = html.replace("<body data-layout=", '<body data-theme="ryotei" data-layout=', 1)
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

# ---------------------------------------------------------------- HTTPハンドラ
# ハンドラは**モジュール直下の工場**で作る。main() の中に閉じ込めると、テストから
# プロセスを起こさずに叩けない (会議道具は会議の日にしか動かせない、では検査にならない)。


def make_handler(outdir, agenda, blocks, start_epoch, total_min=None):
    """この会議1回ぶんの設定を閉じ込めた HTTPRequestHandler を返す。

    状態Dirは stage_urls.json の読み書きにも要るので、ここで OUTDIR も合わせる
    (テストから直接この工場を呼んでも、本番と同じ置き場を見るようにするため)。
    """
    global OUTDIR
    OUTDIR = outdir

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
                label = (STAGE_RES.get(name) or {}).get("label") or name
                self._send(render_img_page("/stage/img/" + name, label),
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

        # ---- 資料棚・合言葉・「済」 (2026-09-04) ------------------------
        # ここは手元の画面だけが叩く経路。共有窓 (/stage/*) からは到達しない。
        def _shelf(self) -> bool:
            from urllib.parse import parse_qs, unquote, urlparse

            u = urlparse(self.path)
            p = u.path.rstrip("/") or "/"
            q = parse_qs(u.query)
            if p == "/creds":
                # 合言葉はテンプレートに埋めない。叩かれた瞬間にファイルを読む。
                self._send(json.dumps(read_creds(), ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return True
            if p == "/docs":
                self._send(json.dumps(doc_list(), ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return True
            if p.startswith("/doc/"):
                fp = doc_path(unquote(p[len("/doc/"):]))
                if fp is None:
                    self._send(b"no such doc", "text/plain; charset=utf-8", 404)
                    return True
                self._send(render_doc(fp), "text/html; charset=utf-8")
                return True
            if p in ("/card/dismiss", "/card/undismiss"):
                bk = self._body_key()       # 本文は必ず読み切る (keep-alive を壊さない)
                key = q.get("key", [""])[0] or bk
                fn = dismiss_card if p == "/card/dismiss" else undismiss_card
                ok = fn(outdir, key)
                self._send(json.dumps({"ok": ok, "key": key}, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return True
            return False

        def _body_key(self) -> str:
            from urllib.parse import parse_qs

            try:
                n = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                return ""
            if n <= 0 or n > 8192:
                return ""
            raw = self.rfile.read(n).decode("utf-8", "replace").strip()
            if raw.startswith("{"):
                try:
                    return str(json.loads(raw).get("key") or "")
                except (json.JSONDecodeError, ValueError, AttributeError):
                    return ""
            return parse_qs(raw).get("key", [""])[0]

        def do_POST(self):
            if self._shelf():
                return
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
            if self._shelf():
                return
            if self.path.split("?")[0].rstrip("/") == "/mode/start":
                # 「同席開始」ボタン。音声より確実な主手段 (2026-08-22 実戦で決めた)。
                # 手元専用ではない — 携帯ディスプレイ(tailscale経由)から押すボタンなので
                # /quit と違って localhost 制限はかけない。
                try:
                    ts = write_mode_start(outdir)
                    body = {"ok": True, "ts": ts}
                except OSError as e:
                    body = {"ok": False, "error": str(e)}
                self._send(json.dumps(body, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
            if not self.path.startswith("/state"):
                from urllib.parse import parse_qs as _pq, urlparse as _up
                # 台本mdを読み直してから配る (直前の差し替えが再読込で効く)
                bl = build_blocks(load_agenda(AGENDA_PATH), parse_script(SCRIPT_PATH)) or blocks
                _q = _pq(_up(self.path).query)
                theme = _q.get("theme", [""])[0]
                # ?layout=rows で、その場の1枚だけ並べ方を変えられる(設定は書き換えない)
                lay = _q.get("layout", [""])[0]
                self._send(render_page(bl, theme, lay), "text/html; charset=utf-8")
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
            state = build_state(outdir, agenda, start_epoch, total_min)
            # 実験の振り返り用 (viewer.py と同じ振る舞い): 表示対象が変わった瞬間だけ残す
            try:
                sig = json.dumps({"card": state.get("card"), "nav": state.get("nav"),
                                  "keys": [c.get("key") for c in (state.get("cards") or [])],
                                  "stage": (state.get("stage") or {}).get("res")},
                                 ensure_ascii=False, sort_keys=True)
                if sig != getattr(self.server, "_last_disp_sig", None):
                    self.server._last_disp_sig = sig
                    with open(outdir / "display_log.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
                            "client": self.client_address[0],
                            "card": state.get("card"), "cards": state.get("cards"),
                            "nav": state.get("nav"),
                            "stage": state.get("stage"),
                            "mode": state.get("mode"), "live": state.get("live"),
                            "v": 2,
                        }, ensure_ascii=False) + "\n")
            except Exception:
                pass
            self._send(json.dumps(state, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")

    return H


# ---------------------------------------------------------------- 起動

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0",
                    help="携帯ディスプレイから見るので既定で外に開く")
    ap.add_argument("--port", type=int, default=47323)
    ap.add_argument("--outdir", default="", help="既定は MEETLIVE_DIR (state_dir)")
    ap.add_argument("--start", default="",
                    help="会議の開始予定 (例 2026-01-20T15:00:00)。番人 copilot.py と同じ値を"
                         "渡すこと。未指定なら meeting.json の start、それも無ければ起動時刻")
    ap.add_argument("--total-min", type=float, default=None,
                    help="既定は meeting.json の total_min / 段取りJSONの会議分")
    a = ap.parse_args()
    global OUTDIR
    outdir = OUTDIR = pathlib.Path(a.outdir) if a.outdir else STATE_DIR
    outdir.mkdir(parents=True, exist_ok=True)
    start_raw = a.start or cfgmod.meeting_start_iso()
    if start_raw:
        try:
            start_epoch = datetime.fromisoformat(start_raw).timestamp()
        except ValueError:
            raise SystemExit(f"開始時刻が読めません: {start_raw} (例 2026-01-20T15:00:00)")
    else:
        start_epoch = time.time()
        print("--start も meeting.json の start も無し。起動時刻を会議開始として扱います",
              flush=True)
    total_min = a.total_min or (cfgmod.total_min() or None)

    agenda = load_agenda(AGENDA_PATH)
    scripts = parse_script(SCRIPT_PATH)
    blocks = build_blocks(agenda, scripts)
    n_script = sum(1 for b in blocks if b["src"] == "台本")
    print(f"台本ブロック: {n_script}/{len(blocks)} 段を {SCRIPT_PATH.name} から抽出 "
          f"(残りは段取りJSONの台本行)", flush=True)
    print(f"舞台の資源: {len(STAGE_ORDER)}件 {STAGE_ORDER}", flush=True)
    print(f"資料棚: {DOCS_DIR}  合言葉: {SECRETS_PATH or '(未設定)'}", flush=True)
    H = make_handler(outdir, agenda, blocks, start_epoch, total_min)

    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    print(f"meetlive viewer2: http://{a.host}:{a.port}  ({outdir})  layout={LAYOUT}",
          flush=True)
    print(f"  携帯ディスプレイからは この機体の LAN / VPN アドレス + :{a.port}", flush=True)
    print(f"  止めるときは kill ではなく手元から: curl localhost:{a.port}/quit", flush=True)
    print(f"  停止ファイル({STOP_FILE.name})が置かれても自分で降ります", flush=True)
    watch_stop_file()
    S((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
