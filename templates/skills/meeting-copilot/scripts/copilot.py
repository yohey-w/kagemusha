#!/usr/bin/env python3
"""
copilot.py — 会議同席の「番人」(LLM無しの第1層)

transcript.jsonl を tail し、**ルールと文字列照合だけ**でカードを1枚ずつ cards.jsonl へ書く。
表示は viewer2.py が行う。重い判断は子プロセス(answerer.py / premise_watch.py)へ回す。

  kind: call  = 「<呼びかけ語>、○○は？」への即答          ttl 60
        warn  = 約束の境界(金額・期限・責任)への警報      ttl 45
        topic = 段取りが次へ進んだ / 取り漏れの催促        ttl 90
        wrap  = 中止条件の検知(注意喚起のみ)              ttl 60

設計メモ:
  - 状態(いまどの段・取り漏れ)は「同席開始」でリセットする。テスト行を本番に持ち込まないため。
  - 段の判定キーワードは**こちら側の発話のみ**。必須取得物は**両者の発話**から拾う
    (答えるのは相手なので、相手の口から出た時点で取れたとみなす)。
  - 「<呼びかけ語>、次/戻って」は viewer2.build_nav と同じ delta 方式で上書きする。
  - この層は LLM を使わない。呼び出しへの回答は設定ファイルと台本からの抽出+定型整形。

起動:
  MEETLIVE_DIR=./meetlive_state/2026-01-20-acme \\
  MEETLIVE_AGENDA=... MEETLIVE_SCRIPT=... MEETLIVE_LEDGER=... \\
  python3 copilot.py --start 2026-01-20T15:00:00 >> copilot.log 2>&1 &
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
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import meetlive_config as cfgmod  # noqa: E402

# ------------------------------------------------------------------ パス
STATE_DIR = cfgmod.state_dir()
TRANSCRIPT = STATE_DIR / "transcript.jsonl"
CARDS = STATE_DIR / "cards.jsonl"
STAGE_CMD = STATE_DIR / "stage_cmd.jsonl"

AGENDA_PATH = cfgmod.input_path("MEETLIVE_AGENDA", "agenda_steps.example.json", required=True)
SCRIPT_PATH = cfgmod.input_path("MEETLIVE_SCRIPT", "talk_script.example.md", required=True)

POLL_SEC = 0.3
TTL = {"call": 60, "warn": 45, "topic": 90, "wrap": 60,
       "premise_warn": 60, "premise_ok": 45, "premise_new": 45}
# topic(取り漏れ催促)の TTL は再発火間隔(SILENCE_COOLDOWN)より長くしてある。
# 短いと「表示が消えてから次が出るまでの間」に見逃す。

CALL_WORDS = cfgmod.call_words()
MODE_START_WORD, MODE_END_WORD, START_HOMOPHONES = cfgmod.mode_words()
MODE_START = "start"

WRAP_STREAK = 3          # 相手が境界へ直球3連続
WRAP_COOLDOWN = 180.0    # wrap は画面上で居座るので撃ちすぎない
WARN_COOLDOWN = 60.0

SILENCE_SEC = 12.0        # これだけ新しい行が来なければ「次の一手」
SILENCE_COOLDOWN = 45.0   # 同じ段での沈黙カードは45秒に1回
OVERRUN_MIN = 2.0         # 予定枠をこれだけ過ぎたら超過を1回だけ
ANSWERER = pathlib.Path(__file__).resolve().parent / "answerer.py"
ANSWERER_MIN_GAP = 30.0   # 第2層の呼び出しは30秒に1回まで(クォータの底が抜けないように)
PREMISE_WATCH = pathlib.Path(__file__).resolve().parent / "premise_watch.py"
PREMISE_MIN_LEN = 6           # 相槌・単語だけの断片は撃たない
Q_TAILS = ("ですか", "ますか", "んですか", "でしょうか", "？", "?", "ですか。", "ますか。", "どう")
Q_MIN_LEN = 30    # 疑問終止形でも短い言いさし断片は拾わない
                  # (実測: 相手の言いさし断片への誤発火が18回中18回だった)

# ------------------------------------------------------------------ 語彙集(設定)
PHRASE = cfgmod.load_phrasebook()
WARN_CATS = {}
for _cat, _d in (PHRASE.get("warn_categories") or {}).items():
    kws = [k for k in (_d.get("keywords") or []) if k]
    if kws:
        WARN_CATS[str(_cat)] = (kws, str(_d.get("message") or f"{_cat}の話。約束の外。"))
# こちら側が既に正しい逃がし方をしている発話は警報しない
ESCAPE_WORDS = tuple(PHRASE.get("escape_words") or ())
# 質問/依頼の形か
ASK_MARKS = tuple(PHRASE.get("ask_marks") or ())
HANDOVER_WORDS = tuple(PHRASE.get("handover_words") or ())
WRAP_LINES = list(PHRASE.get("wrap_lines") or ["通常モードへ。戻るのは失敗ではない。"])
NOT_FOUND_LINES = list(PHRASE.get("not_found_lines")
                       or ["手元にありません。", "「そこは持ち帰って、確認してご連絡します」へ。"])
GOAL_REMINDER = str(PHRASE.get("goal_reminder") or "")
FIXED = [
    (tuple(x.get("keys") or ()), list(x.get("lines") or []), str(x.get("confidence") or "high"))
    for x in (PHRASE.get("fixed_answers") or [])
    if x.get("keys") and x.get("lines")
]

# ------------------------------------------------------------------ 舞台(stage)
# 進行役はPCを触らない。共有中の別窓(舞台)の中身を声で切り替える。
# ここは判定と記録だけ。窓を航行させるのは viewer2.py (stage_cmd.jsonl を読む)。
STAGE = cfgmod.load_stage()
STAGE_LABEL = {r["res"]: r["label"] for r in STAGE["resources"]}
STAGE_MATCH = [(r["res"], re.compile(r["match"])) for r in STAGE["resources"]
               if r["match"] and r["res"] != "blank"]
_ST_TARGET = re.compile(r"(舞台|画面|ステージ|共有)")
_ST_KILL = re.compile(r"(消し|消す|消して|けし|隠|かく|閉じ|とじ|閉め|真っ黒|まっくろ|黒く|オフ)")


def stage_res(text: str):
    """呼び出しの本文から舞台の資源を決める。該当が無ければ None (=従来の検索へ落とす)。

    STT の誤変換に寛容にしたいので、資源ごとの `match` は**正規表現**で書く。
    ただし拾いすぎると台本検索が死ぬので、「舞台に出す物の名前」だけを見て、
    動詞や語尾は見ない。
    """
    q = text or ""
    for w in CALL_WORDS:
        q = q.replace(w, "")
    q = q.strip("、。 　,.")
    if not q:
        return None
    # 1) 消す (「舞台消して」「画面を真っ黒に」) — どの資源よりも先に見る
    if _ST_TARGET.search(q) and _ST_KILL.search(q):
        return "blank"
    # 2) 資源表の順に当てる(先に書いたものが勝つ)
    for res, pat in STAGE_MATCH:
        if pat.search(q):
            return res
    return None


# ------------------------------------------------------------------ 小道具
_KW_RE_CACHE: dict = {}


def kw_hit(kw: str, blob: str) -> bool:
    """検知キーワードを**正規表現**として当てる(viewer2.py と同じ規則)。

    文字列の完全一致だけだと表記ゆれで丸ごと見逃す。平文キーワードは正規表現としても
    そのまま部分一致と同じ結果になるので、既存の平文設定は無改変で動く。
    壊れた正規表現は部分一致へ退避する。
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


def parse_ts(iso: str):
    try:
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def sents(text: str) -> list[str]:
    out = []
    for chunk in re.split(r"(?<=。)|\n", text):
        c = chunk.strip()
        if c:
            out.append(c.rstrip("。"))
    return out


def clean_md(s: str) -> str:
    s = re.sub(r"`+", "", s)
    s = re.sub(r"\*\*|\*", "", s)
    s = re.sub(r"^[▸\-\s•>|]+", "", s)
    s = re.sub(r"（[^）]*画面[^）]*）", "", s)
    return s.strip()


def shorten(s: str, n: int = 54) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _agenda_field(d: dict, ja: str, en: str, default=None):
    """設定JSONは日本語キーを正とし、英語キーも受ける(どちらで書いてもよい)。"""
    if ja in d:
        return d[ja]
    if en in d:
        return d[en]
    return default


# ------------------------------------------------------------------ 知識の読込
class Knowledge:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.total_min = 60.0
        self.index: list[tuple[str, str]] = []   # (出所, 一行)
        self.counts: dict[str, int] = {}
        self.branch_phrases: list[str] = []

    # -- 段取り(進行判定の正本) ---------------------------------------
    def load_agenda(self) -> None:
        raw = json.loads(AGENDA_PATH.read_text(encoding="utf-8"))
        self.total_min = float(_agenda_field(raw, "会議分", "total_minutes", 60) or 60)
        for i, s in enumerate(_agenda_field(raw, "steps", "steps", []) or []):
            musts = []
            for m in _agenda_field(s, "必須取得物", "musts", []) or []:
                if isinstance(m, str):
                    musts.append({"name": m, "kw": [m]})
                    continue
                musts.append({
                    "name": _agenda_field(m, "名前", "name", "") or "",
                    "kw": [k for k in (_agenda_field(m, "検知キーワード", "keywords", []) or []) if k],
                })
            self.steps.append(
                {
                    "id": s.get("id", str(i)),
                    "title": _agenda_field(s, "title", "title", f"ステップ{i+1}"),
                    "min": float(_agenda_field(s, "目安分", "minutes", 0) or 0),
                    "kw": [k for k in (_agenda_field(s, "検知キーワード", "keywords", []) or []) if k],
                    "must": musts,
                    "nudge": s.get("nudge", ""),
                    "script": [x for x in (_agenda_field(s, "台本", "script", []) or []) if x],
                }
            )
        if not self.steps:
            raise SystemExit(f"[copilot] {AGENDA_PATH} に steps がありません")
        for s in self.steps:
            for line in s["script"]:
                self.index.append((s["title"], clean_md(line)))
        self.counts["steps"] = len(self.steps)
        self.counts["musts"] = sum(len(s["must"]) for s in self.steps)

    # -- 台本(索引と分岐の想定発話) --------------------------------------
    def load_script(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        # 「▸」行に書かれた分岐の想定発話(「」で囲んだ部分)を集める。
        # 第2層(answerer)の発火判定で、「疑問符が無くても台本が既に想定している
        # 言い回しなら発火してよい」の材料に使う。
        self.branch_phrases = []
        for line in text.splitlines():
            if not line.strip().startswith("▸"):
                continue
            for m in re.finditer(r"「([^」]{2,20})」", line):
                p = m.group(1)
                if p and p not in self.branch_phrases:
                    self.branch_phrases.append(p)
        for line in text.splitlines():
            c = clean_md(line)
            if not c or c.startswith(("#", "|", "---", "[ ]", "- [ ]")):
                continue
            if len(c) < 6:
                continue
            self.index.append(("台本", c))
        self.counts["台本行"] = sum(1 for s, _ in self.index if s == "台本")
        self.counts["分岐"] = len(self.branch_phrases)
        self.counts["索引"] = len(self.index)

    def load(self) -> None:
        self.load_agenda()
        self.load_script()
        log("知識: " + " / ".join(f"{k}={v}" for k, v in self.counts.items()))


# ------------------------------------------------------------------ 検索
_HIRA = re.compile(r"^[ぁ-ん]+$")
# 検索語から落とす語。呼びかけ語は設定から取る(ここを固定値にすると呼びかけ語を
# 変えたときに検索が静かに劣化する)。
_DROP = tuple(CALL_WORDS) + ("教えて", "おしえて", "ってなんだっけ", "だっけ",
                             "ですか", "ますか", "って")


def bigrams(q: str) -> list[str]:
    for d in _DROP:
        q = q.replace(d, "")
    q = re.sub(r"[、。 　,.?？!！「」『』()（）]", "", q)
    return [q[i : i + 2] for i in range(max(0, len(q) - 1))]


def search(kb: Knowledge, query: str, top: int = 2):
    bg = bigrams(query)
    if len(bg) < 2:
        return [], "none"
    best = []
    for src, line in kb.index:
        hit = [b for b in bg if b in line]
        content = [b for b in hit if not _HIRA.match(b)]
        if not content:
            continue
        ratio = len(hit) / len(bg)
        best.append((ratio, len(content), src, line))
    if not best:
        return [], "none"
    best.sort(key=lambda x: (x[1], x[0], -len(x[3])), reverse=True)
    ratio, content, src, line = best[0]
    if content < 1 or ratio < 0.15:
        return [], "none"
    out = [shorten(line, 58)]
    for _r, _c, _s, l2 in best[1:top]:
        if _c >= content - 1 and l2 != line:
            out.append(shorten(l2, 58))
    return out, ("high" if (content >= 2 and ratio >= 0.35) else "low")


# ------------------------------------------------------------------ 本体
class Copilot:
    def __init__(self, kb: Knowledge, start: datetime, test_mode: bool = False) -> None:
        self.kb = kb
        self.start = start
        self.test_mode = test_mode          # [TEST] 行を処理してよいのは検査のときだけ
        self.last_answerer = 0.0
        self.reset_state("起動")
        self.last_warn: dict[str, float] = {}
        self.last_wrap = 0.0
        self.card_count = 0
        self.last_line_ts = datetime.now()   # 沈黙検知の基準(transcriptのtsで更新される)
        self.last_silence: dict[int, float] = {}
        self.overrun_done: set[int] = set()
        self.ans_proc: subprocess.Popen | None = None
        self.premise_proc: subprocess.Popen | None = None
        # 呼び出し語だけを剥がすための文字クラス(短い呼び出しの保留判定に使う)。
        self._call_chars = re.compile(
            "[" + re.escape("".join(set("".join(CALL_WORDS)))) + "、。 　]"
        )

    def reset_state(self, why: str) -> None:
        self.all_blob = ""       # 両者の発話(必須取得物の検知に使う)
        self.host_blob = ""      # こちら側の発話(段の検知に使う)
        self.delta = 0           # 「<呼びかけ語>、次/戻って」の手動送り
        self.cur = 0
        self.guest_streak = 0
        self.started = False
        self.last_silence = {}
        self.overrun_done = set()
        self.last_line_ts = datetime.now()
        log(f"状態リセット: {why}")

    # ---- 時間 --------------------------------------------------------
    def elapsed_min(self) -> float:
        return (datetime.now() - self.start).total_seconds() / 60.0

    def window(self, i: int) -> str:
        head = sum(s["min"] for s in self.kb.steps[:i])
        a = self.start + timedelta(minutes=head)
        b = a + timedelta(minutes=self.kb.steps[i]["min"])
        return f"{a:%H:%M}〜{b:%H:%M}"

    # ---- 段と取り漏れ -------------------------------------------------
    def auto_step(self) -> int:
        auto = 0
        for i, s in enumerate(self.kb.steps):
            if any(kw_hit(k, self.host_blob) for k in s["kw"]):
                auto = max(auto, i)
        return auto

    def calc_cur(self) -> int:
        return max(0, min(len(self.kb.steps) - 1, self.auto_step() + self.delta))

    def unmet(self, upto: int) -> list[str]:
        return [
            m["name"]
            for s in self.kb.steps[: upto + 1]
            for m in s["must"]
            if m["kw"] and not any(kw_hit(k, self.all_blob) for k in m["kw"])
        ]

    # ---- カード書き出し -----------------------------------------------
    def emit(self, kind: str, lines: list[str], confidence: str, reason: str, ttl=None) -> None:
        lines = [l for l in lines if l][:3] or ["手元にありません。"]
        rec = {
            "ts": now_iso(),
            "kind": kind,
            "lines": lines,
            "confidence": confidence,
            "ttl": TTL.get(kind, 45) if ttl is None else ttl,
        }
        with CARDS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.card_count += 1
        log(f"CARD {kind}/{confidence} 理由={reason} → {' | '.join(lines)}")

    # ---- 舞台 -----------------------------------------------------------
    def write_stage(self, res: str, text: str, src: str = "voice") -> None:
        """舞台の指令を1行足すだけ。窓を動かすのは viewer2 の仕事。"""
        rec = {"ts": time.time(), "iso": now_iso(), "res": res, "src": src,
               "text": (text or "")[:80]}
        try:
            with STAGE_CMD.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log(f"STAGE {res} src={src} in={(text or '')[:28]}")
        except OSError as e:
            log(f"舞台指令を書けず（続行）: {e!r}")

    def stage_card(self, res: str, text: str) -> None:
        self.emit("call", [f"舞台→{STAGE_LABEL.get(res, res)}"], "low",
                  f"舞台={res} in={(text or '')[:28]}", ttl=20)

    # ---- 呼び出しへの回答 ---------------------------------------------
    def answer(self, text: str):
        q = text
        for w in CALL_WORDS:
            q = q.replace(w, "")
        q = q.strip("、。 　,.")

        # 1) 次 / 戻る
        head = q[:6]
        if re.match(r"^(次|つぎ|進|すす)", head):
            self.delta += 1
            self.cur = self.calc_cur()
            s = self.kb.steps[self.cur]
            must = "・".join(m["name"] for m in s["must"]) or "なし"
            return (
                [f"【{self.cur+1}】{s['title']}（{self.window(self.cur)}）",
                 shorten(clean_md(s["script"][0]) if s["script"] else s["nudge"], 58),
                 f"取るもの: {must}"],
                "high",
                "呼び出し=次",
            )
        if re.match(r"^(戻|もど|前)", head):
            self.delta -= 1
            self.cur = self.calc_cur()
            s = self.kb.steps[self.cur]
            return (
                [f"【{self.cur+1}】{s['title']}（{self.window(self.cur)}）",
                 shorten(clean_md(s["script"][0]) if s["script"] else s["nudge"], 58)],
                "high",
                "呼び出し=戻る",
            )

        # 2) 時間
        if any(k in q for k in ("時間", "何分", "経過", "残り時間", "時計", "押してる")):
            el = self.elapsed_min()
            s = self.kb.steps[self.cur]
            if el < 0:
                head_l = f"開始前。あと{int(-el)}分で{self.start:%H:%M}。"
            else:
                head_l = f"開始から{int(el)}分。残り{max(0, int(self.kb.total_min - el))}分。"
            return (
                [head_l,
                 f"いま【{self.cur+1}】{s['title']}（予定 {self.window(self.cur)}・{int(s['min'])}分枠）"],
                "high",
                "呼び出し=時間",
            )

        # 3) 必須取得物の未達
        if any(k in q for k in ("成果", "ゴール", "達成", "未達", "取れて", "取りこぼ", "宿題")):
            miss = self.unmet(len(self.kb.steps) - 1)
            if not miss:
                return (["必須取得物は全部取れています。", "復唱して閉じて大丈夫です。"],
                        "high", "呼び出し=成果")
            return (
                ["未達: " + "・".join(miss[:3]) + (f" ほか{len(miss)-3}件" if len(miss) > 3 else ""),
                 GOAL_REMINDER],
                "high",
                "呼び出し=成果",
            )

        # 4) 頻出の一問一答(設定ファイル。検索より先に当てる)
        for keys, lines, conf in FIXED:
            if any(k in q for k in keys):
                return (list(lines), conf, f"呼び出し=定型({keys[0]})")

        # 5) 知識の全文検索
        lines, conf = search(self.kb, q)
        if conf == "none":
            return (list(NOT_FOUND_LINES), "none", "呼び出し=該当なし")
        return (lines, conf, "呼び出し=検索")

    # ---- 1行を処理 -----------------------------------------------------
    def feed(self, rec: dict) -> None:
        if rec.get("type") == "mode":
            if rec.get("mode") == MODE_START:
                self.reset_state("同席開始")
                self.started = True
            else:
                log("同席終了を検知（判定は続けるが状態は保持）")
            return

        text = (rec.get("text") or "").strip()
        if not text:
            return
        speaker = rec.get("speaker", "guest")
        # 合図の聞き取り揺れ対策。開始合図は STT に化けることがある(実測あり)ので、
        # 「呼びかけ語 or 開始合図 or その誤変換」+「開始/スタート」の形でも開始として扱う。
        if speaker == "host" and not self.started:
            marks = tuple(CALL_WORDS) + (MODE_START_WORD,) + tuple(START_HOMOPHONES)
            if ("開始" in text or "スタート" in text) and any(w and w in text for w in marks):
                self.reset_state("同席開始(音声揺れ吸収)")
                self.started = True
                self.emit("topic", ["同席、始めます。"], "high", f"開始合図 in={text[:20]}")
                return
        if text.startswith("[TEST]"):
            # 本番では素通し。--test のときだけ印を外して本番と同じ経路に通す
            if not self.test_mode or self.started:
                log(f"無視: テスト行 {text[:24]}")
                return
            text = re.sub(r"^\[TEST\]\s*", "", text)
            if not text:
                return

        self.last_line_ts = parse_ts(rec.get("ts", "")) or datetime.now()
        called = any(w in text for w in CALL_WORDS)

        # --- 舞台コマンドは何よりも先。短い指示ほど下の「保留(連結待ち)」に食われるので、
        #     ここで断ち切って即座に舞台へ回す (「<呼びかけ語>、管理画面」は保留の閾値6文字内)。
        if called:
            res = stage_res(text)
            if res:
                self._pend_call = None
                self.all_blob += "\n" + text
                if speaker == "host":
                    self.host_blob += "\n" + text
                self.write_stage(res, text)
                self.stage_card(res, text)
                self.cur = self.calc_cur()
                return

        # 呼び出しの分割対策(実測: 呼びかけ語＋用件が2行に割れて、どちらも判定に落ちた)。
        # 呼びかけ語を含む短い行は保留し、3秒以内に来た同話者の次行を連結して1発話として扱う。
        now = time.time()
        pend = getattr(self, "_pend_call", None)
        if pend and speaker == "host" and now - pend["t"] <= 3.0 and not called:
            text = pend["text"] + " " + text
            called = True
            self._pend_call = None
            log(f"呼び出し連結: {text[:40]}")
        elif called and speaker == "host" and len(self._call_chars.sub("", text)) <= 6:
            self._pend_call = {"text": text, "t": now}
            log(f"呼び出し保留(短い): {text[:24]}")
            return
        else:
            self._pend_call = None

        # --- 状態の更新(段=こちら側の発話 / 必須取得物=両者) ---
        self.all_blob += "\n" + text
        if speaker == "host":
            self.host_blob += "\n" + text

        # --- 呼び出し(最優先。topic とは二重に出さない) ---
        if called:
            # 連結してはじめて舞台コマンドになる場合
            res = stage_res(text)
            if res:
                self.write_stage(res, text)
                self.stage_card(res, text)
                self.cur = self.calc_cur()
                return
            if speaker != "host":
                log(f"注意: guest 側に呼び出し語（話者判定のブレ。イヤホンを確認）: {text[:24]}")
            lines, conf, reason = self.answer(text)
            self.emit("call", lines, conf, f"{reason} in={text[:28]}")
            self.cur = self.calc_cur()
            return

        # --- 警報: 約束の境界 ---
        cat = self.warn_cat(speaker, text)
        if cat:
            t = time.time()
            if t - self.last_warn.get(cat, 0.0) >= WARN_COOLDOWN:
                self.last_warn[cat] = t
                self.emit("warn", [WARN_CATS[cat][1]], "high", f"境界={cat} in={text[:28]}")
            else:
                log(f"間引き: {cat}の警報は{int(WARN_COOLDOWN)}秒以内に既出 in={text[:24]}")

        # --- 中止条件(注意喚起) ---
        if self.check_wrap(speaker, text, bool(cat)):
            return

        # --- 台本外の質問は第2層(answerer)へ回す。境界の語があるときは警報だけ ---
        if speaker == "guest" and self.is_question(text):
            if cat:
                log(f"answerer は呼ばない(約束の境界={cat}): {text[:24]}")
            elif self.on_script(text):
                log(f"台本内の質問なので answerer は呼ばない: {text[:24]}")
            else:
                self.call_answerer(text)

        # --- 前提監視(呼ばれ待ちをしない) ---
        if speaker == "guest":
            self.call_premise_watch(text)

        # --- 進行 ---
        if speaker == "host":
            new = self.calc_cur()
            if new != self.cur:
                prev, self.cur = self.cur, new
                self.topic_card(prev)

    # ---- 台本外の質問 → 第2層 -------------------------------------------
    def is_question(self, text: str) -> bool:
        """発火は「明確な疑問形の語尾 かつ 30字以上」、または「台本が分岐で想定している
        言い回し」のどちらかに限る。緩めると相手の言いさし断片で撃ちまくって画面が死ぬ。
        呼びかけ経由の発火はここを通らない(feed() の called 分岐)。"""
        t = text.rstrip("。 　")
        clear_q = t.endswith(Q_TAILS) and len(t) >= Q_MIN_LEN
        on_branch = any(kw_hit(p, text) for p in self.kb.branch_phrases)
        return clear_q or on_branch

    def on_script(self, text: str) -> bool:
        return any(kw_hit(k, text) for s in self.kb.steps for k in s["kw"])

    def call_answerer(self, text: str) -> None:
        if self.ans_proc is not None and self.ans_proc.poll() is None:
            log(f"間引き: answerer 走行中なので見送り in={text[:24]}")
            return
        # 走行中でなくても連打しない(上位モデルのクォータは有限)
        if time.time() - self.last_answerer < ANSWERER_MIN_GAP:
            log(f"間引き: answerer は{int(ANSWERER_MIN_GAP)}秒に1回まで in={text[:24]}")
            return
        if not ANSWERER.exists():
            log(f"answerer.py が無いので見送り: {ANSWERER}")
            return
        self.emit("call", ["考え中…"], "low", f"台本外の質問 in={text[:28]}", ttl=15)
        try:
            self.ans_proc = subprocess.Popen(
                [sys.executable, str(ANSWERER), text],
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
            self.last_answerer = time.time()
            log(f"answerer 起動 pid={self.ans_proc.pid} q={text[:40]}")
        except Exception as e:
            log(f"answerer を起動できず（続行）: {e!r}")

    # ---- 前提監視 (呼ばれ待ちをしない) --------------------------------------
    def call_premise_watch(self, text: str) -> None:
        """相手の発話ごとに前提リストと突き合わせる。1発話1判定が理想だが、
        判定に数秒かかるので走行中は重ねて撃たない(自然な間引き。取りこぼしはログで見える)。"""
        if len(text.strip()) < PREMISE_MIN_LEN:
            return
        if self.premise_proc is not None and self.premise_proc.poll() is None:
            log(f"間引き: premise_watch 走行中なので見送り in={text[:24]}")
            return
        if not PREMISE_WATCH.exists():
            log(f"premise_watch.py が無いので見送り: {PREMISE_WATCH}")
            return
        try:
            self.premise_proc = subprocess.Popen(
                [sys.executable, str(PREMISE_WATCH), text],
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
            log(f"premise_watch 起動 pid={self.premise_proc.pid} in={text[:40]}")
        except Exception as e:
            log(f"premise_watch を起動できず（続行）: {e!r}")

    # ---- 時間で駆動するもの(沈黙・予定超過) --------------------------------
    def tick(self) -> None:
        now, wall = time.time(), datetime.now()
        if wall < self.start:          # 会議前は黙る
            return
        # 沈黙: 現ステップの未取得を1つだけ差し出す。ステップ0(未着手)では出さない。
        # 時計は1本に揃える: last_line_ts は transcript の ts(発話が起きた壁時計)を正とする。
        # 「行が来た受信時刻」を使うと、STT の再接続でチャンネルごとに時刻がずれたときに
        # 沈黙の判定まで巻き添えになる。
        idle = (datetime.now() - self.last_line_ts).total_seconds()
        if idle >= SILENCE_SEC and (self.auto_step() > 0 or self.delta > 0):
            if now - self.last_silence.get(self.cur, 0.0) >= SILENCE_COOLDOWN:
                miss = [
                    m["name"] for m in self.kb.steps[self.cur]["must"]
                    if m["kw"] and not any(kw_hit(k, self.all_blob) for k in m["kw"])
                ]
                if miss:
                    self.last_silence[self.cur] = now
                    self.emit("topic", [f"{miss[0]}を聞くと進みます"], "high",
                              f"沈黙{int(idle)}秒 段={self.cur+1}")
                else:
                    self.last_silence[self.cur] = now
                    log(f"沈黙{int(idle)}秒だが【{self.cur+1}】の必須は取得済み。黙る")
        # 予定超過: 各ステップ1回だけ
        i = self.cur
        if i not in self.overrun_done:
            end = self.start + timedelta(minutes=sum(s["min"] for s in self.kb.steps[: i + 1]))
            if wall > end + timedelta(minutes=OVERRUN_MIN):
                self.overrun_done.add(i)
                if i + 1 < len(self.kb.steps):
                    line = f"【{i+1}】は予定超過。次は【{i+2}】{self.kb.steps[i+1]['title']}"
                else:
                    line = f"【{i+1}】は予定超過。" + (self.kb.steps[i]["nudge"] or "復唱して閉じる")
                self.emit("topic", [shorten(line, 58)], "high",
                          f"予定超過 枠切れ{end:%H:%M}+{int(OVERRUN_MIN)}分")

    def warn_cat(self, speaker: str, text: str):
        if speaker == "host" and any(e in text for e in ESCAPE_WORDS):
            return None
        if ASK_MARKS and not any(a in text for a in ASK_MARKS):
            return None
        for cat, (kws, _msg) in WARN_CATS.items():
            if any(k in text for k in kws):
                return cat
        return None

    def check_wrap(self, speaker: str, text: str, boundary: bool) -> bool:
        fire = None
        if speaker == "guest":
            self.guest_streak = self.guest_streak + 1 if boundary else 0
            if self.guest_streak >= WRAP_STREAK:
                fire = f"相手の直球{self.guest_streak}連続"
        elif HANDOVER_WORDS and any(w in text for w in HANDOVER_WORDS):
            fire = "こちらの「持ち帰ります」"
        if not fire:
            return False
        t = time.time()
        if t - self.last_wrap < WRAP_COOLDOWN:
            log(f"間引き: 中止条件は{int(WRAP_COOLDOWN)}秒以内に既出 ({fire})")
            return False
        self.last_wrap = t
        self.guest_streak = 0
        self.emit("wrap", list(WRAP_LINES), "high", f"中止条件={fire}")
        return True

    def topic_card(self, prev: int) -> None:
        s = self.kb.steps[self.cur]
        lines = []
        if self.cur > prev:
            miss = self.unmet(self.cur - 1)
            if miss:
                lines.append("取り漏れ: " + miss[0] + (f"（ほか{len(miss)-1}件）" if len(miss) > 1 else ""))
        el = self.elapsed_min()
        rest = max(0, int(self.kb.total_min - el)) if el > 0 else int(self.kb.total_min)
        lines.append(f"【{self.cur+1}】{s['title']}へ。残り{rest}分・あと{len(self.kb.steps)-self.cur-1}段")
        must = "・".join(m["name"] for m in s["must"])
        lines.append(f"取るもの: {must}" if must else (s["nudge"] or "取るもの: なし"))
        self.emit("topic", lines, "high", f"進行 {prev+1}→{self.cur+1}")


# ------------------------------------------------------------------ tail
def tail(cop: Copilot) -> None:
    # 起動時: 直近の「同席開始」以降だけを無言で復元。無ければ履歴は捨てる。
    offset = 0
    if TRANSCRIPT.exists():
        raw = TRANSCRIPT.read_bytes()
        offset = len(raw)
        recs = []
        for line in raw.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        last_start = max(
            (i for i, r in enumerate(recs)
             if r.get("type") == "mode" and r.get("mode") == MODE_START),
            default=None,
        )
        if last_start is None:
            log(f"履歴{len(recs)}行は同席開始が無いので状態に取り込まない（クリーン起動）")
        else:
            emit_backup, stage_backup = cop.emit, cop.write_stage
            cop.emit = lambda *a, **k: None         # 復元中はカードを書かない
            cop.write_stage = lambda *a, **k: None  # 舞台も動かさない(再生で窓が飛ぶ)
            for r in recs[last_start:]:
                cop.feed(r)
            cop.emit, cop.write_stage = emit_backup, stage_backup
            log(f"履歴を復元: 同席開始以降{len(recs)-last_start}行 → 現在【{cop.cur+1}】")
    else:
        TRANSCRIPT.touch()
    log(f"待機開始: {TRANSCRIPT} をポーリング{POLL_SEC}秒 / 開始時刻 {cop.start:%Y-%m-%d %H:%M}")

    buf = ""
    LOCK = TRANSCRIPT.parent / "copilot.owner"
    my_pid = os.getpid()
    LOCK.write_text(str(my_pid), encoding="utf-8")
    log(f"番人の席を取得 pid={my_pid}")
    while True:
        try:
            try:
                owner = int(LOCK.read_text(encoding="utf-8").strip() or "0")
            except Exception:
                owner = my_pid
            if owner != my_pid:
                log(f"新しい番人(pid={owner})に席を譲って終了 pid={my_pid}")
                return
            size = TRANSCRIPT.stat().st_size if TRANSCRIPT.exists() else 0
            if size < offset:
                log("transcript が縮んだ（作り直し）。先頭から読み直す")
                offset, buf = 0, ""
            if size > offset:
                with TRANSCRIPT.open("rb") as f:
                    f.seek(offset)
                    chunk = f.read()
                offset += len(chunk)
                buf += chunk.decode("utf-8", "replace")
                *lines, buf = buf.split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        log(f"壊れた行を飛ばす: {line[:40]}")
                        continue
                    try:
                        cop.feed(rec)
                    except Exception as e:  # 番人は落ちないことが最優先
                        log(f"判定でエラー（無視して続行）: {e!r} rec={line[:60]}")
            cop.tick()   # 沈黙・予定超過は行が来なくても進む
        except Exception as e:
            log(f"tailでエラー（続行）: {e!r}")
        time.sleep(POLL_SEC)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="", help="会議開始 (例 2026-01-20T15:00:00・実行機のローカル時刻)")
    ap.add_argument("--test", action="store_true",
                    help="[TEST] で始まる行も判定に通す(検査専用・本番では付けない)")
    ap.add_argument("--selfcheck", action="store_true",
                    help="設定を読めるかだけ確かめて終了する(会議前の点検用)")
    a = ap.parse_args()
    start = datetime.now()
    if a.start:
        try:
            start = datetime.fromisoformat(a.start)
        except ValueError:
            log(f"--start を読めないので起動時刻を使う: {a.start!r}")
    kb = Knowledge()
    kb.load()
    log(f"舞台の資源: {len(STAGE['resources'])}件 / 声で呼べるもの {len(STAGE_MATCH)}件")
    log(f"語彙集: 定型{len(FIXED)}件 / 境界{len(WARN_CATS)}種")
    if a.selfcheck:
        log(f"状態ディレクトリ: {STATE_DIR}")
        log(f"段取り: {AGENDA_PATH}")
        log(f"台本: {SCRIPT_PATH}")
        log("selfcheck OK")
        return
    if a.test:
        log("⚠ テストモード: [TEST] 行も判定に通す")
    cop = Copilot(kb, start, test_mode=a.test)
    tail(cop)


if __name__ == "__main__":
    main()
