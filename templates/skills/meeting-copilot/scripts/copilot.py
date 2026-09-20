#!/usr/bin/env python3
"""
copilot.py — 会議同席の「番人」(LLM無しの第1層)

transcript.jsonl を tail し、**ルールと文字列照合だけ**でカードを1枚ずつ cards.jsonl へ書く。
表示は viewer2.py が行う。重い判断は子プロセス(answerer.py / premise_watch.py)へ回す。

  kind: call  = 「<呼びかけ語>、○○は？」への即答          ttl 60
        warn  = 約束の境界(金額・期限・責任)への警報      ttl 45
        topic = 段取りが次へ進んだ / 取り漏れの催促        ttl 90
        wrap  = 中止条件の検知(注意喚起のみ)              ttl 60
        lookup= 進行役が探し物を始めたときの即答          ttl 90

🔴 カードは**必ず3要素**を持つ (2026-09-19 実走の反省・カード1013件中、3要素が
   そろっていたのは14件=1.4%だった。残りは「対象は分かるが、何が問題で・何を
   言えばよいかが本文に無い」型で、進行役は読んでも動けなかった):

     target … 【対象】 何について言っているか (内部IDではなく人が読める言葉)
     status … 【状況】 何が起きた・何が分かった
     say    … 【言うこと】 その場でそのまま読み上げられる完成文
     to     … 宛先 "進行役へ" | "記録のみ" (声に出すものと、裏の記録を区別する)
     ref    … 内部ID(F-011 等)。本文には出さず、小さく添えるだけ

   lines は後方互換のため残す(この3要素から自動で組み立てる)。

🔴 同じ対象の催促は**初回だけフルカード**。以後は件数のバッジだけ
   (実走で同一文言の催促が960件。TTLで消えて再び出るのを12時間繰り返した)。

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
import collections
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import decision_engine as de  # noqa: E402
import lookup_assist  # noqa: E402
import meetlive_config as cfgmod  # noqa: E402
import mode_signal  # noqa: E402
import step_detect  # noqa: E402

# ------------------------------------------------------------------ パス
STATE_DIR = cfgmod.state_dir()
TRANSCRIPT = STATE_DIR / "transcript.jsonl"
CARDS = STATE_DIR / "cards.jsonl"
STAGE_CMD = STATE_DIR / "stage_cmd.jsonl"

AGENDA_PATH = cfgmod.input_path("MEETLIVE_AGENDA", "agenda_steps.example.json", required=True)
SCRIPT_PATH = cfgmod.input_path("MEETLIVE_SCRIPT", "talk_script.example.md", required=True)

STOP_FILE = cfgmod.stop_file()
LOOKUP_MISSES = STATE_DIR / "lookup_misses.jsonl"
DECISIONS = STATE_DIR / "decisions.jsonl"
DECISION_HINT = STATE_DIR / "decision_hint.json"

POLL_SEC = 0.3
TTL = {"call": 60, "warn": 45, "topic": 90, "wrap": 60, "lookup": 90,
       "premise_warn": 60, "premise_ok": 45, "premise_new": 45, "commit": 90}
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
# 判定層の班を同時に何本まで走らせるか。1本だと、鎖が遅い日に「走行中につき
# 見送り」が大半になってカードが出ない。増やしすぎると会議が終わったあとに
# 答えが届く。4本目が来たら、いちばん古い未完了を諦めて枠を空ける。
MAX_DECISION_WORKERS = 3
# 会議はおよそ4秒に1発話。鎖の上限がこれ×本数を超えると、構造的に追いつかない。
SEC_PER_UTTERANCE = 4.0
Q_TAILS = ("ですか", "ますか", "んですか", "でしょうか", "？", "?", "ですか。", "ますか。", "どう")
Q_MIN_LEN = 30    # 疑問終止形でも短い言いさし断片は拾わない
                  # (実測: 相手の言いさし断片への誤発火が18回中18回だった)

# 同じ対象の催促を撃ち直す回数。初回はフルカード、以後はここに挙げた回数に達した
# ときだけ「未解決バッジ」を1枚。45秒に1回×2時間=160回でも、出るカードは6枚。
BADGE_AT = (2, 4, 8, 16, 32, 64, 128, 256)
STOP = cfgmod.stop_policy()
LOOKUP_COOLDOWN = cfgmod.lookup_cooldown()

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
# 別れの言葉。これが出たら終話の**予鈴**(即停止はしない。無音が続いてはじめて畳む)
# 🔴 「ありがとうございました」「よろしくお願いします」は**入れない**。日本語の
#    商談では会議の途中で何度も出るので、予鈴が会議の最中に鳴り続ける。
FAREWELL_WORDS = tuple(PHRASE.get("farewell_words")
                       or ("失礼します", "お疲れさまでした", "また来週", "また次回",
                           "では失礼", "ごきげんよう"))
# 探し始めの合図(探し物アシスト)。既定は lookup_assist が持つ汎用の語彙。
LOOKUP_TRIGGERS = tuple(PHRASE.get("lookup_triggers") or lookup_assist.DEFAULT_TRIGGERS)
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
                    # 取れていないときに、その場でそのまま読み上げる問い。
                    # これが無いと催促カードの【言うこと】が作れず、1要素カードに戻る。
                    "ask": _agenda_field(m, "問い", "ask", "") or "",
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
                    # build_agenda.py が入れる3要素。手書きの段取りJSONには無くてよい
                    # (無ければ従来どおり title / nudge / 台本 から組み立てる)。
                    "answer": _agenda_field(s, "取る答え", "answer", "") or "",
                    "say": _agenda_field(s, "言い方の例", "say", "") or "",
                    "ask": _agenda_field(s, "抜けたら出す問い", "ask", "") or "",
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
def build_lookup() -> "lookup_assist.Index":
    """探し物の索引を、設定の解決を通して1回だけ組む(即答表→台帳→資料)。"""
    return lookup_assist.Index(
        quick_facts=cfgmod.quick_facts_path(),
        ledger=cfgmod.meeting_file("ledger.yaml"),
        kb_dir=cfgmod.knowledge_dir(),
    )


class Copilot:
    def __init__(self, kb: Knowledge, start: datetime, test_mode: bool = False,
                 end: datetime | None = None, lookup: "lookup_assist.Index | None" = None) -> None:
        self.kb = kb
        self.start = start
        self.end = end                      # 終わりの予定(終話検知に使う・無くてよい)
        self.lookup = lookup if lookup is not None else build_lookup()
        self.last_guest = ""                # 相手の直前の発話(探し物の手掛かり)
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
        # カードは番人の本線と判定層の班の両方から書かれる。順番は前後してよいが、
        # 1枚が途中で割れると読み手(viewer2)が行の途中を JSON として読む。
        self._card_lock = threading.Lock()
        self.setup_decisions()

    # ---- 判定層 (decision_engine) ----------------------------------------
    def setup_decisions(self) -> None:
        """会議中に判定層を使う構えを作る。使わないなら ``self.decision = None``。

        🔴 **判定は本線(逐語を読む輪)の外で走らせる。** 1発話ごとに最大で
        「判定器のタイムアウト＋退避先のタイムアウト」だけ待つ作りにすると、
        発話が4秒に1本来る会議では本線が二度と追いつかない。だから班は1本だけ
        走らせ、走っている間に来た発話は**判定を見送る**(前提監視と同じ作法)。
        見送りはログに出る。
        """
        self.decision = None
        self.decision_thread: threading.Thread | None = None   # 直近の1本(後方互換)
        self._jobs: list = []                  # 走行中の班
        self._jobs_lock = threading.Lock()
        self.decision_seen: set[str] = set()   # 約束カードの重複よけ(発話ごと1回)
        self.ended_streak = 0                  # 「終わった」が続いた回数
        self.suppress_nudge_until = 0.0        # 雑談のあと催促を見送る期限
        self.recent: collections.deque = collections.deque(maxlen=de.DEFAULT_WINDOW)
        kind = cfgmod.decision_backend()
        self.show_decisions = cfgmod.show_decision_cards()
        if kind == "rules" and not self.show_decisions:
            log("判定層: 使いません（decision_backend=rules・カードも出さない）")
            return
        try:
            bundle = de.load_bundle(de.resolve_bundle_path(cfgmod.meeting_dir()))
            meeting = de.load_meeting_data(cfgmod.meeting_dir(), bundle.privacy)
            # 🔴 会議中は撃ち直さない(retry_busy_sec=0)。混雑で待つと、その発話の
            #    カードは会話が次へ行ったあとに出る——遅れたカードは邪魔なだけ。
            engine = de.make_engine(kind, bundle, meeting, retry_busy_sec=0.0,
                                    note=log)
        except SystemExit as e:
            log(f"判定層を組み立てられないので使いません（続行）: {e}")
            return
        self.recent = collections.deque(maxlen=bundle.window)
        self.decision = {
            "bundle": bundle, "meeting": meeting, "engine": engine,
            "masker": de.Masker(meeting.roster, bundle.privacy.host_alias,
                                bundle.privacy.guest_alias),
            "log": de.DecisionLog(DECISIONS),
        }
        budget = 0.0
        for st in bundle.fallback_chain:
            if st.name == "jev" and bundle.jev.base_url:
                budget += st.timeout_sec or bundle.jev.timeout_sec
            elif st.name == "llm" and bundle.llm.base_url:
                budget += st.timeout_sec or bundle.llm.timeout_sec
        log(f"判定層: backend={kind} 鎖={bundle.chain_label} "
            f"/ カードに出す={'はい' if self.show_decisions else 'いいえ（記録だけ）'} "
            f"/ 1発話あたり最大{budget:.1f}秒")
        room = SEC_PER_UTTERANCE * MAX_DECISION_WORKERS
        if budget > room:
            # 班を増やしたぶん、遅い鎖でも追いつける。追いつけないのは
            # 「1発話あたりの間隔 × 本数」を超えたときだけ。
            log(f"⚠ 判定に最大{budget:.1f}秒かかりうる鎖です（班{MAX_DECISION_WORKERS}本で"
                f"捌ける上限は{room:.0f}秒）。取り落としが出ます"
                f"——timeout_sec を詰めるか、段を減らしてください")
        if meeting.roster:
            log(f"判定層: 名簿{len(meeting.roster)}件を役名へ置換して送ります")
        else:
            log("⚠ 判定層: 名簿が空です。発話に出る名前がそのまま外へ出ます"
                "（会議フォルダに roster.txt を置いてください）")

    def kick_decisions(self, speaker: str, text: str, uid: str) -> None:
        """判定を後ろで走らせる。**発話を取り落とさない**のがここの役目。

        1本ずつだと、鎖が遅い日は「走行中につき見送り」が大半になり、カードが
        まったく出ない会議になる。だから ``MAX_DECISION_WORKERS`` 本まで重ねて
        走らせ、それでも溢れたら**いちばん古い未完了を諦める**（新しい発話の方が
        価値がある。古い判定が今ごろ返ってきても、会話は先へ行っている）。

        🔴 「諦める」は結果を捨てて枠を空けることで、通信を止めることではない
        （走っているスレッドは外から止められない）。諦めた班はタイムアウトで
        自然に終わるので、瞬間的に本数を超えることはあっても際限なくは増えない。
        """
        if not self.decision:
            return
        window = list(self.recent)
        flag = {"abandoned": False}
        th = threading.Thread(target=self._decide, daemon=True,
                              args=(window, speaker, text, uid, flag))
        with self._jobs_lock:
            self._jobs = [j for j in self._jobs if j["th"].is_alive()]
            while len(self._jobs) >= MAX_DECISION_WORKERS:
                old = self._jobs.pop(0)
                old["flag"]["abandoned"] = True
                log(f"判定層が詰まったので古い方を諦めます: uid={old['uid']}"
                    f"（走行中{len(self._jobs) + 1}本）")
            self._jobs.append({"th": th, "flag": flag, "uid": uid})
        self.decision_thread = th
        th.start()

    def wait_decisions(self, timeout: float = 5.0) -> None:
        """走行中の班が終わるのを待つ（試験と、畳む前の後片付けのため）。"""
        with self._jobs_lock:
            jobs = list(self._jobs)
        for j in jobs:
            j["th"].join(timeout)

    def _decide(self, window, speaker: str, text: str, uid: str, flag) -> None:
        """班の中身。**例外をここから外に出さない**——判定層の不具合で番人が
        落ちたら、会議のあいだ画面が死ぬ。落ちたらログだけ残して次へ。"""
        d = self.decision
        try:
            state, questions, answers, ms = de.evaluate_utterance(
                d["engine"], d["bundle"], d["meeting"], d["masker"], window)
            if not questions:
                return
            dropped = bool(flag.get("abandoned"))
            d["log"].write(utterance_id=uid, ts=now_iso(), speaker=speaker,
                           state=state, questions=questions, answers=answers,
                           latency_ms=ms, abandoned=dropped)
            if dropped:
                # 記録には残す（採点の材料になる）が、画面には出さない——
                # 会話が先へ行ったあとのカードは、読む人の邪魔にしかならない。
                log(f"諦めた判定が今ごろ返りました。記録だけ残します uid={uid}")
                return
            self.apply_decisions(answers, speaker, text, uid)
        except Exception as e:                       # noqa: BLE001
            log(f"判定層で例外（会議は続行）: {e!r}")

    def apply_decisions(self, answers, speaker: str, text: str, uid: str) -> None:
        """判定の答えを会議の画面と状態へ配る。

        出す/出さないの境目は問いごと（decisions.yaml の thresholds）。
        **確信が足りないものは何もしない**——外れたカードは、無いカードより悪い。
        """
        d = self.decision
        bundle = d["bundle"]
        by = answers.by_id

        def conf(qid):
            a = by.get(qid)
            return a, (a.confidence if a else 0.0)

        # --- Q8 約束: 進行役がいま約束した ---------------------------------
        a, c = conf("q8_commitment")
        if a is not None and a.value == "yes" and a.p_yes >= de.threshold(bundle, "q8_commitment"):
            key = f"commit:{uid}"
            if key in self.decision_seen:
                log(f"間引き: 約束カードは同じ発話で既出 in={text[:24]}")
            else:
                self.decision_seen.add(key)
                self.emit("commit", [], "high",
                          f"約束 p={a.p_yes:.2f} 担当={answers.backend} in={text[:28]}",
                          target=self.commit_target(),
                          status=f"進行役がいま約束した「{shorten(text, 40)}」",
                          say="確定なら「はい」と一声 → 台帳（commitments）へ記帳",
                          to="進行役へ")

        # --- Q4 探し物: 合図の語と **OR**（言い回しが毎回違うので両方で拾う）---
        a, c = conf("q4_lookup")
        if (speaker == "host" and a is not None and a.value == "yes"
                and a.p_yes >= de.threshold(bundle, "q4_lookup")):
            # try_lookup は自分で合図語を見るので、ここでは索引だけ引く。
            # 同じ探し物の撃ち直しは try_lookup 側の間引きが効く。
            self.lookup_from_decision(text, a.p_yes)

        # --- Q1 段: 画面の上に小さく「推定の段」。**自動切替はしない** -------
        a, c = conf("q1_step")
        if (self.show_decisions and a is not None and a.value
                and a.value != de.NONE_KEY and c >= de.threshold(bundle, "q1_step")):
            self.write_hint(a.value, c)

        # --- Q3 種類: 内部だけ。雑談のあとは催促を見送る ---------------------
        a, c = conf("q3_kind")
        if a is not None and c >= de.threshold(bundle, "q3_kind") and a.value == "small_talk":
            self.suppress_nudge_until = time.time() + SILENCE_COOLDOWN
            log(f"雑談と判定（p={c:.2f}）。次の催促は{int(SILENCE_COOLDOWN)}秒見送ります")

        # --- Q2 局面: 「終わった」が続いたら終話の**予鈴**だけ鳴らす ---------
        #     🔴 予鈴は停止ではない。畳むには無音が続くことが従来どおり必要。
        a, c = conf("q2_phase")
        if a is not None:
            if a.value == "ended" and c >= de.threshold(bundle, "q2_phase"):
                self.ended_streak += 1
                need = int(de.threshold(bundle, "q2_phase", "streak"))
                if self.ended_streak >= need and self.farewell_at is None:
                    self.farewell_at = time.time()
                    log(f"終話の予鈴: 「終わった」が{self.ended_streak}発話続きました"
                        f"（畳むには無音が続くことが必要）")
            elif a.value:
                self.ended_streak = 0

    def commit_target(self) -> str:
        """約束カードの【対象】。いまの段の名前、無ければ相手の直前の発話の要旨。"""
        i = self.cur
        if 0 <= i < len(self.kb.steps):
            title = (self.kb.steps[i].get("title") or "").strip()
            if title:
                return shorten(title, 28)
        return shorten(self.last_guest, 28) if self.last_guest else "この会議の約束"

    def lookup_from_decision(self, text: str, p: float) -> bool:
        """判定層が「探している」と言ったときの索引引き。

        合図の語には当たらなかった発話のための経路なので、当たらなくても
        answerer(LLM)へは回さない（合図が無い＝探していない可能性も残るため、
        外れたときに黙って引き下がる方が安全）。
        """
        hit = self.lookup.find(text, self.last_guest)
        if hit is None:
            log(f"探し物(判定層 p={p:.2f}): 索引に当たりなし in={text[:28]}")
            return False
        key = f"lookup:{hit['target']}"
        if time.time() - self.looked_up.get(key, 0.0) < LOOKUP_COOLDOWN:
            log(f"間引き: 『{hit['target']}』は直近に出した")
            return True
        self.looked_up[key] = time.time()
        self.emit("lookup", [], "high", f"探し物(判定層 p={p:.2f}) in={text[:28]}",
                  target=hit["target"], status=hit["status"], say=hit["say"],
                  ref=hit.get("ref", ""))
        return True

    def write_hint(self, step_key: str, c: float) -> None:
        """画面の上に出す「推定の段」。カードではないので1ファイルを上書きする。"""
        title = next((s.title for s in self.decision["meeting"].steps
                      if s.key == step_key), step_key)
        try:
            DECISION_HINT.write_text(json.dumps(
                {"ts": now_iso(), "step": step_key, "title": title,
                 "confidence": round(c, 3)}, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            log(f"推定の段を書けず（続行）: {e!r}")

    def reset_state(self, why: str) -> None:
        self.all_blob = ""       # 両者の発話(必須取得物の検知に使う)
        self.delta = 0           # 「<呼びかけ語>、次/戻って」の手動送り
        self.cur = 0
        self.auto_hi = 0         # 段の高水位。発話単位で判定する(step_detect)
        self.host_run = 0        # 相手のあと、こちらが続けて話した発話数
        self.guest_streak = 0
        self.started = False
        self.last_silence = {}
        self.overrun_done = set()
        self.last_line_ts = datetime.now()
        self.nudged = {}         # 対象 -> 催促した回数(同じ催促の反復をやめるため)
        self.looked_up = {}      # 探し物の対象 -> 最後に出した時刻
        self.farewell_at = None  # 別れの言葉を聞いた時刻(終話の予鈴)
        self.stopping = False
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
        """段の高水位。判定は発話が来たときに step_detect が1回ずつ進める。

        旧実装は「こちら側の全発話を連結した文字列」に当てていたので、雑談の中の
        1語で段が4つ飛んだ(2026-09-19 実測: 段の切替4回中、台本の文脈と関係のある
        切替は0回)。規則は step_detect.py に1本化して画面側と共有する。
        """
        return self.auto_hi

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
    def emit(self, kind: str, lines: list[str], confidence: str, reason: str, ttl=None,
             target: str = "", status: str = "", say: str = "",
             to: str = "進行役へ", ref: str = "", extra: dict | None = None) -> None:
        """カードを1枚書く。3要素(target/status/say)が本体で、lines は後方互換。

        3要素を渡さなかった呼び出しは lines から埋める(古い経路が黙って
        1要素カードに戻らないように、必ず何かが入る形にする)。
        """
        lines = [l for l in lines if l][:3]
        if lines:
            target = target or shorten(lines[0], 28)
            status = status or (lines[1] if len(lines) > 1 else "")
            say = say or (lines[-1] if len(lines) > 1 else lines[0])
        else:
            # 3要素から lines を作る。ここを空のままにすると、履歴・display_log・
            # 古い読み手が全部「手元にありません。」を見ることになる。
            lines = [x for x in (target, status, say) if x] or ["手元にありません。"]
        rec = {
            "ts": now_iso(),
            "kind": kind,
            "lines": lines,
            "target": target,
            "status": status,
            "say": say,
            "to": to,
            "confidence": confidence,
            "ttl": TTL.get(kind, 45) if ttl is None else ttl,
        }
        if ref:
            rec["ref"] = ref
        if extra:
            rec.update(extra)
        # 本線と判定層の班の2箇所から書かれる。1枚が途中で割れると読み手が壊れる。
        with self._card_lock:
            with CARDS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.card_count += 1
        log(f"CARD {kind}/{confidence} 宛={to} 理由={reason} → {target} / {status} / {say}")

    def nudge(self, key: str, target: str, status: str, say: str, reason: str,
              kind: str = "topic") -> None:
        """同じ対象の催促。初回はフルカード、以後は未解決バッジだけ。

        実走(2026-09-19)で同一文言の催促が960件出た。TTLで消えては再び出るので、
        「消える／読む」の区別そのものが意味を失っていた。数え直すのは対象ごと。
        """
        n = self.nudged.get(key, 0) + 1
        self.nudged[key] = n
        if n == 1:
            self.emit(kind, [], "high", reason, target=target, status=status, say=say)
            return
        if n in BADGE_AT:
            self.emit(kind, [], "high", f"{reason}(未解決{n}回目)",
                      target=target, status=f"未解決のまま{n}回目", say=say,
                      extra={"badge": True, "count": n})
            return
        log(f"間引き: 『{target}』の催促は既出({n}回目・バッジは次の節目で)")

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
        label = STAGE_LABEL.get(res, res)
        self.emit("call", [], "low", f"舞台={res} in={(text or '')[:28]}", ttl=20,
                  target="舞台（共有窓）", status=f"{label} に切り替えました",
                  say=f"いま画面に {label} を出しています。", to="記録のみ")

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
        # 合図の聞き取り揺れ対策。判定は mode_signal.py に1本化してある
        # (書く側 receiver.py / 読む側 viewer2.py と同じ述語。ここだけ独自に持つと、
        #  かつてのように「片方は拾い、片方は拾わない」非対称が復活する)。
        if speaker == "host" and not self.started:
            if mode_signal.is_start_signal(
                text, call_words=CALL_WORDS, start_word=MODE_START_WORD,
                homophones=START_HOMOPHONES,
            ):
                self.reset_state("同席開始(音声揺れ吸収)")
                self.started = True
                s0 = self.kb.steps[0]
                self.emit("topic", [], "high", f"開始合図 in={text[:20]}",
                          target=f"【1】{s0['title']}",
                          status="同席を始めました",
                          say=shorten(s0["say"] or (clean_md(s0["script"][0])
                                                    if s0["script"] else s0["title"]), 58))
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
                self.host_run = step_detect.next_run(self.host_run, speaker)
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

        # --- 状態の更新(段=一発話ごとの高水位 / 必須取得物=両者の連結) ---
        self.all_blob += "\n" + text
        self.host_run = step_detect.next_run(self.host_run, speaker)
        self.auto_hi = step_detect.advance(
            self.auto_hi, self.kb.steps, speaker, self.host_run, text, kw_hit)
        if speaker == "guest":
            self.last_guest = text
        if speaker == "host" and any(w in text for w in FAREWELL_WORDS):
            self.farewell_at = time.time()
            log(f"終話の予鈴: 別れの言葉 in={text[:24]}")

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
            self.emit("call", lines, conf, f"{reason} in={text[:28]}",
                      target=shorten(self._bare(text), 28),
                      status="照会への回答" if conf != "none" else "手元に無し",
                      say=lines[0])
            self.cur = self.calc_cur()
            return

        # --- 探し物アシスト(進行役が資料を探し始めた) ---
        #     answerer(LLM)より**先**に、即答表と台帳をキーワードで当てる。
        #     ここは**足すだけ**。警報も進行も、この発話で動くものは動かす
        #     (探し始めの発話に金額の話が混ざっていたら、両方出るのが正しい)。
        if speaker == "host":
            self.try_lookup(text)

        # --- 警報: 約束の境界 ---
        cat = self.warn_cat(speaker, text)
        if cat:
            t = time.time()
            if t - self.last_warn.get(cat, 0.0) >= WARN_COOLDOWN:
                self.last_warn[cat] = t
                self.emit("warn", [WARN_CATS[cat][1]], "high", f"境界={cat} in={text[:28]}",
                          target=f"{cat}の話", status="約束の外",
                          say=WARN_CATS[cat][1])
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

        # --- 判定層（本線の外で1本だけ走らせる。ここまでの処理は止めない）---
        #     🔴 この位置なのは、上の層（警報・探し物・前提監視・進行）が
        #     **判定層の有無に関わらず同じに動く**ようにするため。判定層は
        #     足すだけで、既にあるものを置き換えない。
        self.recent.append({"speaker": speaker, "text": text})
        if self.decision and self.started:
            self.kick_decisions(speaker, text, rec.get("ts") or now_iso())

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
        self.emit("call", [], "low", f"台本外の質問 in={text[:28]}", ttl=15,
                  target=shorten(text, 28), status="台本の外。調べています",
                  say="考え中…（数秒お待ちください）", to="記録のみ")
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
        if now < self.suppress_nudge_until:
            # 直前が雑談だと判定された。催促を差し込む間ではない。
            return
        if idle >= SILENCE_SEC and (self.auto_step() > 0 or self.delta > 0):
            if now - self.last_silence.get(self.cur, 0.0) >= SILENCE_COOLDOWN:
                miss = [
                    m for m in self.kb.steps[self.cur]["must"]
                    if m["kw"] and not any(kw_hit(k, self.all_blob) for k in m["kw"])
                ]
                self.last_silence[self.cur] = now
                if miss:
                    m = miss[0]
                    self.nudge(
                        key=f"must:{self.cur}:{m['name']}",
                        target=m["name"],
                        status="まだ取れていません",
                        say=self.ask_for(m, self.cur),
                        reason=f"沈黙{int(idle)}秒 段={self.cur+1}",
                    )
                else:
                    log(f"沈黙{int(idle)}秒だが【{self.cur+1}】の必須は取得済み。黙る")
        # 予定超過: 各ステップ1回だけ
        i = self.cur
        if i not in self.overrun_done:
            end = self.start + timedelta(minutes=sum(s["min"] for s in self.kb.steps[: i + 1]))
            if wall > end + timedelta(minutes=OVERRUN_MIN):
                self.overrun_done.add(i)
                over = int((wall - end).total_seconds() // 60)
                if i + 1 < len(self.kb.steps):
                    nxt = self.kb.steps[i + 1]
                    say = nxt["say"] or (clean_md(nxt["script"][0]) if nxt["script"] else "")
                    say = say or f"次は「{nxt['title']}」へ進ませてください。"
                else:
                    say = (self.kb.steps[i]["ask"] or self.kb.steps[i]["nudge"]
                           or "決まったことを読み上げて、ここで閉じさせてください。")
                self.emit("topic", [], "high",
                          f"予定超過 枠切れ{end:%H:%M}+{int(OVERRUN_MIN)}分",
                          target=f"【{i+1}】{self.kb.steps[i]['title']}",
                          status=f"予定を{over}分超過",
                          say=shorten(say, 58))
        self.check_end(now, idle)

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
        self.emit("wrap", list(WRAP_LINES), "high", f"中止条件={fire}",
                  target="中止条件", status=fire, say=WRAP_LINES[0])
        return True

    def ask_for(self, must: dict, step_i: int) -> str:
        """取り漏れの【言うこと】。**その場で読み上げられる完成文**にする。

        優先は「必須取得物に添えられた問い」→「その段の抜けたら出す問い」→
        名前から作る定型。旧実装の「○○を聞くと進みます」は、何と言えばよいかが
        書いていないので進行役が動けなかった(実測1013件中の95%がこれ)。
        """
        ask = (must.get("ask") or "").strip()
        if ask:
            return shorten(ask, 58)
        step_ask = (self.kb.steps[step_i]["ask"] or "").strip()
        if step_ask:
            return shorten(step_ask, 58)
        return shorten(f"「{must['name']}について、いまどうなっていますか」", 58)

    def topic_card(self, prev: int) -> None:
        s = self.kb.steps[self.cur]
        el = self.elapsed_min()
        rest = max(0, int(self.kb.total_min - el)) if el > 0 else int(self.kb.total_min)
        status = f"残り{rest}分・あと{len(self.kb.steps)-self.cur-1}段"
        if self.cur > prev:
            miss = self.unmet(self.cur - 1)
            if miss:
                status = ("取り漏れ: " + miss[0]
                          + (f"（ほか{len(miss)-1}件）" if len(miss) > 1 else "")
                          + f" / {status}")
        say = s["say"] or (clean_md(s["script"][0]) if s["script"] else "")
        if not say:
            must = "・".join(m["name"] for m in s["must"])
            say = f"ここで取るのは「{must}」です。" if must else (s["nudge"] or "")
        self.emit("topic", [], "high", f"進行 {prev+1}→{self.cur+1}",
                  target=f"【{self.cur+1}】{s['title']}",
                  status=status, say=shorten(say, 58))

    # ---- 探し物アシスト ---------------------------------------------------
    def _bare(self, text: str) -> str:
        q = text or ""
        for w in CALL_WORDS:
            q = q.replace(w, "")
        return q.strip("、。 　,.")

    def try_lookup(self, text: str) -> bool:
        """進行役が資料を探し始めたら、即答表と台帳から1秒以内に答えを出す。

        実走での要望(2026-09-19): 「相手の応答に回答するのに情報をさがすとき、いちいち
        聞いていた。探しているのを検知して、探している情報を出してくれると助かる」。
        当たらなかったら lookup_misses.jsonl に残す(会議後に即答表を育てる材料)。
        """
        if not lookup_assist.is_lookup(text, LOOKUP_TRIGGERS):
            return False
        prev_guest = self.last_guest
        hit = self.lookup.find(text, prev_guest)
        if hit is None:
            rec = {"ts": now_iso(), "host": text[:120], "guest": (prev_guest or "")[:120]}
            try:
                with LOOKUP_MISSES.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError as e:
                log(f"探し物の外しを記録できず（続行）: {e!r}")
            log(f"探し物: 当たりなし in={text[:28]} → answerer へ")
            self.call_answerer(self._bare(text) or text)
            return True
        key = f"lookup:{hit['target']}"
        last = self.looked_up.get(key, 0.0)
        if time.time() - last < LOOKUP_COOLDOWN:
            log(f"間引き: 『{hit['target']}』は直近に出した")
            return True
        self.looked_up[key] = time.time()
        self.emit("lookup", [], "high", f"探し物 in={text[:28]}",
                  target=hit["target"], status=hit["status"], say=hit["say"],
                  ref=hit.get("ref", ""))
        return True

    # ---- 終話の検知 -------------------------------------------------------
    def check_end(self, now: float, idle: float) -> None:
        """会議が終わったら**自分で**畳む。

        実走(2026-09-19)では会議のあと12時間近くプロセスが残り、誰も見ていない
        画面に同じカードを903件描き続けた。畳むのは停止ファイルを置くだけで、
        kill は使わない(全層が自分で見に行って自分で終わる)。

        誤って会議の**最中**に止めるほうが害が大きいので、判定は分単位で余裕を取る。
        """
        if self.stopping or not STOP["enabled"] or not self.started:
            return
        # 🔴 畳む条件は**必ず無音とセット**にする。予定の時刻だけでは止めない——
        #    実走の会議は60分の予定に対して133分かかった。「予定＋猶予で停止」だと
        #    会議の真っ最中に3層とも落ちる。予定超過は「畳むのを早める」だけに使う。
        if self.last_line_ts < self.start:
            return              # リハの逐語を復元しただけ。まだ本番の発話が1つも無い
        grace = STOP["farewell_grace_min"] * 60.0
        why = None
        if idle >= STOP["silence_min"] * 60.0:
            why = f"双方の無音が{int(idle//60)}分続きました"
        elif self.farewell_at is not None and idle >= grace:
            why = f"別れの挨拶のあと{int(idle//60)}分の無音がありました"
        elif (self.end is not None and idle >= grace
              and datetime.now() > self.end + timedelta(minutes=STOP["end_grace_min"])):
            why = (f"予定の終わり {self.end:%H:%M} から{int(STOP['end_grace_min'])}分過ぎ、"
                   f"{int(idle//60)}分の無音がありました")
        if not why:
            return
        self.stopping = True
        self.emit("topic", [], "high", f"終話検知: {why}",
                  target="同席", status=why,
                  say="同席を終わります。画面と受信もいっしょに畳みます。",
                  to="記録のみ")
        log(f"終話検知: {why} → 停止ファイルを置きます: {STOP_FILE}")
        try:
            STOP_FILE.write_text(
                json.dumps({"ts": now_iso(), "by": "copilot", "why": why},
                           ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as e:
            log(f"停止ファイルを書けず（続行）: {e!r}")


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
            # 停止ファイル: 自分で置いたもの(終話検知)も、stop.sh が置いたものも同じ。
            # 🔴 畳むのはプロセス自身。kill は使わない。
            if STOP_FILE.exists():
                log(f"停止ファイルを見つけたので終わります: {STOP_FILE}")
                return
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
    ap.add_argument("--end", default="",
                    help="会議終了の予定 (ISO8601 か HH:MM)。ここから猶予を過ぎたら自分で畳む")
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
    end = None
    raw_end = a.end or cfgmod.meeting_end_iso()
    if raw_end:
        if re.fullmatch(r"\d{1,2}:\d{2}", raw_end):
            h, m = (int(x) for x in raw_end.split(":"))
            end = start.replace(hour=h, minute=m, second=0, microsecond=0)
        else:
            try:
                end = datetime.fromisoformat(raw_end)
            except ValueError:
                log(f"--end を読めないので終話の予定は使わない: {raw_end!r}")
    kb = Knowledge()
    kb.load()
    lookup = build_lookup()
    log(f"舞台の資源: {len(STAGE['resources'])}件 / 声で呼べるもの {len(STAGE_MATCH)}件")
    log(f"語彙集: 定型{len(FIXED)}件 / 境界{len(WARN_CATS)}種")
    log(f"探し物の索引: {len(lookup)}件 / 合図{len(LOOKUP_TRIGGERS)}語"
        + (f" / 即答表 {cfgmod.quick_facts_path()}" if cfgmod.quick_facts_path() else
           " / 即答表なし（quick_facts.md を会議フォルダに置くと即答できます）"))
    # 判定層（decision_engine.py）。**この版では番人はまだ判定層を呼ばない** ——
    # 通っているのは設定の2つだけ。何で回すつもりか・画面に出すつもりかを
    # 起動時に読み上げておく（「出るはずだった」を会議の最中に気づく、を防ぐ）。
    log(f"判定層: backend={cfgmod.decision_backend()}"
        f" / カンペに出す={'はい' if cfgmod.show_decision_cards() else 'いいえ'}"
        "（この版では番人からは呼びません。採点は replay_eval.py で）")
    if a.selfcheck:
        log(f"状態ディレクトリ: {STATE_DIR}")
        log(f"段取り: {AGENDA_PATH}")
        log(f"台本: {SCRIPT_PATH}")
        log(f"終わりの予定: {end:%H:%M}" if end else "終わりの予定: 未設定")
        log(f"終話検知: {'入' if STOP['enabled'] else '切'}"
            f"（無音{STOP['silence_min']:.0f}分 / 別れの言葉のあと"
            f"{STOP['farewell_grace_min']:.0f}分 / 予定超過{STOP['end_grace_min']:.0f}分）")
        log(f"カンペの粒度: {cfgmod.script_mode()}")
        log("selfcheck OK")
        return
    if a.test:
        log("⚠ テストモード: [TEST] 行も判定に通す")
    if STOP_FILE.exists():
        # 前の会議の停止ファイルが残っていると、起動した瞬間に自分で終わる。
        # 「画面は上がるのに番人が居ない」がいちばん分かりにくい壊れ方なので消しておく。
        log(f"前回の停止ファイルを片付けます: {STOP_FILE}")
        try:
            STOP_FILE.unlink()
        except OSError as e:
            log(f"停止ファイルを消せず（続行）: {e!r}")
    cop = Copilot(kb, start, test_mode=a.test, end=end, lookup=lookup)
    tail(cop)


if __name__ == "__main__":
    main()
