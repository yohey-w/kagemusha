#!/usr/bin/env python3
"""decision_engine.py — 耳（文字起こし）と口（カード）のあいだに置く「判定層」。

発話が1本届くたびに、**あらかじめ決めておいた問いの束**へ一度に答えを付ける。
答えは確率つきなので、呼び出し側は「確信が足りないときは何もしない」を選べる。

--- なぜ要るか (2026-09-19 実走) ---
段の判定・催促・探し物・約束の記帳が、キーワード一致のルールでは軒並み外れた。
段の切替は4回とも無関係な語の偶然一致で、約束は1件も記録に残らなかった。
ルールは「書いた言葉と同じ言葉が出たとき」しか当たらないが、会議で人は毎回
違う言い方をする。そこで判定だけを外の判定器へ出せる口を開ける。

--- 層の形 ---
    発話 → state（直近K発話だけ）＋ questions（問いの束）
         → DecisionEngine.evaluate() → 問いごとの答えと確率
         → （呼び出し側が確信度ゲートを通してカードにする）

実装は差し替えられる:

    JevBackend      … 外部の判定器へ REST で1往復。1発話につき1回・問いは全部積む
    RulesBackend    … いまのキーワード判定を同じ問いの形に包んだもの（退避先）
    FallbackEngine  … 前者が落ちたら後者へ。どちらが答えたかを記録に残す

🔴 **この層は URL を1つも持たない。** 送り先・鍵の環境変数名・モデル名はすべて
   設定ファイル（``decisions.yaml``）から来る。道具の中に宛先を焼き付けると、
   利用者が別の経路を選べないうえ、この配布物が特定の業者に紐づいてしまう。

🔴 **送るのは直近K発話だけ。** 逐語の蓄積は渡さない。判定器は state が伸びるほど
   精度が落ちる（無関係な材料が答えを引っ張る）と、どの判定器の説明書にも書いてある。

🔴 **人名は送る前に伏せる。** 会議フォルダの ``roster.txt`` にある名前を
   〈相手〉〈進行役〉などの役名へ置き換えてから送る。置換は state だけでなく
   **問いの選択肢の説明にも**掛ける（段の見出しや即答表の見出しに相手の名前が
   入っていることがあるため）。
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import time
import unicodedata
import urllib.error
import urllib.request

import lookup_assist
import step_detect

HERE = pathlib.Path(__file__).resolve().parent
CONFIG_DIR = HERE.parent / "config"
# 会議フォルダに置くときの名前と、同梱の例。解決順は
# 「明示の指定 → 会議フォルダ → 同梱の例」（meetlive_config.input_path と同じ考え方）。
DECISIONS_NAME = "decisions.yaml"
DECISIONS_EXAMPLE = CONFIG_DIR / "decisions.example.yaml"

# 候補（段・即答表の見出し）の上限。選択肢が増えるほど1問が長くなり、
# state と合わせたトークン予算を食う。
MAX_CANDIDATES = 30
# 窓の既定。K発話・総文字数の両方で切る（1発話が異様に長いときの保険）。
DEFAULT_WINDOW = 8
DEFAULT_WINDOW_CHARS = 1200
DEFAULT_TIMEOUT = 2.0
NONE_KEY = "none"

_ASCII_KEY = re.compile(r"[^A-Za-z0-9_]")


class DecisionError(RuntimeError):
    """判定器へ届かなかった・答えを読めなかった。呼び出し側が退避する合図。"""


# ---------------------------------------------------------------- 設定


@dataclasses.dataclass
class JevSettings:
    """外部判定器の宛先。**既定値は空**。設定に無ければ Jev は起動しない。"""

    base_url: str = ""
    path: str = "/v1/systemone"
    model: str = ""
    key_env: str = ""
    timeout_sec: float = DEFAULT_TIMEOUT

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.path.lstrip("/")


@dataclasses.dataclass
class Privacy:
    roster: str = "roster.txt"
    host_alias: str = "〈進行役〉"
    guest_alias: str = "〈相手〉"


@dataclasses.dataclass
class Pricing:
    """入力トークンの単価。**既定は 0**（道具の中に他所の値段を焼き付けない）。"""

    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0
    currency: str = "USD"


@dataclasses.dataclass
class Question:
    """問い1つ。``ask`` が host のものは、相手の発話のときは**送らない**。"""

    qid: str
    qtype: str                      # "choice" | "score" | "noul"
    instructions: str = ""
    ask: str = "any"                # "any" | "host" | "guest"
    options: tuple = ()             # choice: ((key, desc), ...)
    levels: tuple = ()              # score: ((key, desc), ...)
    criteria: dict = dataclasses.field(default_factory=dict)  # noul: true/false の説明
    candidates: str = ""            # "" | "agenda_steps" | "quick_facts"
    include_none: bool = False

    def applies_to(self, speaker: str) -> bool:
        return self.ask == "any" or self.ask == speaker


@dataclasses.dataclass
class Bundle:
    """問いの束＋窓＋宛先。``decisions.yaml`` 1枚がこれになる。"""

    questions: tuple = ()
    window: int = DEFAULT_WINDOW
    window_chars: int = DEFAULT_WINDOW_CHARS
    jev: JevSettings = dataclasses.field(default_factory=JevSettings)
    privacy: Privacy = dataclasses.field(default_factory=Privacy)
    pricing: Pricing = dataclasses.field(default_factory=Pricing)

    def question(self, qid: str) -> "Question | None":
        return next((q for q in self.questions if q.qid == qid), None)


def _opts(raw) -> tuple:
    """``[{key, desc}, ...]`` または ``{key: desc}`` を ((key, desc), ...) に。"""
    out = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            out.append((str(k), "" if v is None else str(v)))
    else:
        for item in (raw or []):
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("id") or "")
                out.append((key, str(item.get("desc") or item.get("description") or "")))
            elif item is not None:
                out.append((str(item), ""))
    return tuple((k, d) for k, d in out if k)


def bundle_from_dict(d: dict) -> Bundle:
    """設定の辞書 → Bundle。ファイルを介さずに組めるようにしてある（試験用）。"""
    d = d or {}
    win = d.get("window") if isinstance(d.get("window"), dict) else {}
    jv = d.get("jev") if isinstance(d.get("jev"), dict) else {}
    pv = d.get("privacy") if isinstance(d.get("privacy"), dict) else {}
    pr = d.get("pricing") if isinstance(d.get("pricing"), dict) else {}
    qs = []
    for raw in (d.get("questions") or []):
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        qtype = str(raw.get("type") or "").strip().lower()
        if qtype not in ("choice", "score", "noul"):
            raise SystemExit(
                f"[decisions] 問い {raw.get('id')!r} の type が choice/score/noul ではありません: {qtype!r}")
        crit = raw.get("criteria") if isinstance(raw.get("criteria"), dict) else {}
        qs.append(Question(
            qid=str(raw["id"]),
            qtype=qtype,
            instructions=str(raw.get("instructions") or "").strip(),
            ask=str(raw.get("ask") or "any").strip().lower(),
            options=_opts(raw.get("options")),
            levels=_opts(raw.get("levels")),
            criteria={str(k): str(v) for k, v in crit.items()},
            candidates=str(raw.get("candidates") or "").strip(),
            include_none=bool(raw.get("include_none")),
        ))
    return Bundle(
        questions=tuple(qs),
        window=int(win.get("utterances") or DEFAULT_WINDOW),
        window_chars=int(win.get("max_chars") or DEFAULT_WINDOW_CHARS),
        jev=JevSettings(
            base_url=str(jv.get("base_url") or "").strip(),
            path=str(jv.get("path") or "/v1/systemone").strip(),
            model=str(jv.get("model") or "").strip(),
            key_env=str(jv.get("key_env") or "").strip(),
            timeout_sec=float(jv.get("timeout_sec") or DEFAULT_TIMEOUT),
        ),
        privacy=Privacy(
            roster=str(pv.get("roster") or "roster.txt").strip(),
            host_alias=str(pv.get("host_alias") or "〈進行役〉"),
            guest_alias=str(pv.get("guest_alias") or "〈相手〉"),
        ),
        pricing=Pricing(
            input_per_mtok=float(pr.get("input_per_mtok") or 0.0),
            output_per_mtok=float(pr.get("output_per_mtok") or 0.0),
            currency=str(pr.get("currency") or "USD"),
        ),
    )


def _readable(p: pathlib.Path) -> bool:
    """``decisions.yaml`` そのものか、PyYAML 無しでも読める ``.json`` があるか。"""
    return p.exists() or p.with_suffix(".json").exists()


def resolve_bundle_path(meeting_dir=None, override=None) -> pathlib.Path:
    """``decisions.yaml`` の置き場。明示 → 会議フォルダ → 同梱の例。

    会議フォルダに無くても止めない。問いの束は案件に依らない（候補だけが
    会議フォルダから来る）ので、同梱の例のままでも正しく動く。
    """
    if override:
        p = pathlib.Path(override).expanduser()
        if not _readable(p):
            raise SystemExit(f"[decisions] --decisions {override} が見つかりません。")
        return p
    if meeting_dir is not None:
        p = pathlib.Path(meeting_dir).expanduser() / DECISIONS_NAME
        if _readable(p):
            return p
    return DECISIONS_EXAMPLE


def load_bundle(path) -> Bundle:
    """``decisions.yaml`` を読む。PyYAML が無い機体では ``.json`` の隣を探す。

    この配布物は標準ライブラリだけで動くのが原則で、PyYAML は任意。だから
    「yaml が無い＝判定層が使えない」にはしない。同じ名前で拡張子が ``.json``
    のファイルがあればそれを読む。どちらも読めないときだけ止まる。
    """
    p = pathlib.Path(path)
    sibling = p.with_suffix(".json")
    if not p.exists():
        if sibling.exists():
            return bundle_from_dict(json.loads(sibling.read_text(encoding="utf-8")))
        raise SystemExit(f"[decisions] {p} が見つかりません。")
    try:
        import yaml
    except ImportError:
        yaml = None
    if yaml is None:
        if sibling.exists():
            return bundle_from_dict(json.loads(sibling.read_text(encoding="utf-8")))
        raise SystemExit(
            f"[decisions] {p} を読むには PyYAML が要ります（pip install pyyaml）。\n"
            f"           入れられない機体では、同じ内容を {sibling.name} に置いてください。")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"[decisions] {p} の中身が辞書ではありません。")
    return bundle_from_dict(data)


# ---------------------------------------------------------------- 会議フォルダの材料


def _field(d: dict, *names, default=None):
    """和名・英名のどちらの鍵でも読む（段取りJSONは両方の書き方を許している）。"""
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None:
            return d[n]
    return default


def _key(raw: str, fallback: str) -> str:
    """選択肢の鍵。**判定器へは鍵の綴りを送らない**ので ASCII で足りる。

    人が labels.csv に書き写す値でもあるので、日本語の見出しをそのまま鍵には
    しない（全角と半角の取り違えで正解合わせが崩れる）。
    """
    k = _ASCII_KEY.sub("", (raw or "").strip())
    return k[:24] if k else fallback


@dataclasses.dataclass
class MeetingData:
    """会議フォルダから読む「候補」と、ルール判定に要る語彙。"""

    steps: tuple = ()          # ((key, title, (kw, ...)), ...)
    quick_facts: tuple = ()    # ((key, title), ...)
    roster: tuple = ()         # ((name, alias), ...)
    lookup_triggers: tuple = ()
    farewell_words: tuple = ()
    ask_marks: tuple = ()
    index: object = None       # lookup_assist.Index（即答表の照合に使う）


def _load_json(p: pathlib.Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_roster(path) -> tuple:
    """``roster.txt``（1行1名・任意）。``名前 = 役名`` で役名を指定できる。

    書き方::

        # 会議に出る人の名前。この名前は判定器へ送る前に役名へ置き換わります。
        山田 太郎 = 〈相手〉
        鈴木 花子 = 〈進行役〉
        Acme                      # 役名を省くと〈相手〉になります
    """
    p = pathlib.Path(path)
    if not p.exists():
        return ()
    out = []
    for raw in p.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n"):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" in line:
            name, alias = line.split("=", 1)
        else:
            name, alias = line, ""
        name = name.strip()
        if name:
            out.append((name, alias.strip() or "〈相手〉"))
    return tuple(out)


# 名前の末尾に付く敬称。名簿へ入れる前に落とす（「〇〇さん」と書いてあっても、
# 発話では呼び捨てや「〇〇様」で出るため）。
HONORIFICS = ("さん", "さま", "様", "御中", "殿", "氏", "くん", "君", "ちゃん")


def _strip_honorific(name: str) -> str:
    n = (name or "").strip()
    for h in HONORIFICS:
        if len(n) > len(h) and n.endswith(h):
            return n[: -len(h)].strip()
    return n


def load_meeting_data(meeting_dir, privacy: Privacy | None = None,
                      max_candidates: int = MAX_CANDIDATES) -> MeetingData:
    """会議フォルダ1つから候補・語彙・名簿を読む。無いものは静かに空。

    名簿には ``meeting.json`` の ``counterpart``（相手の呼び方）も自動で入れる。
    そこに相手の名前が書いてあるのに、``roster.txt`` を作り忘れたというだけで
    平文のまま外へ出ていくのは、いちばん起きやすくて気づきにくい事故なので。
    """
    md = pathlib.Path(meeting_dir).expanduser() if meeting_dir else None
    privacy = privacy or Privacy()
    steps, facts = [], []
    triggers, farewell, ask_marks = (), (), ()
    index = None
    if md is not None and md.is_dir():
        agenda = _load_json(md / "agenda_steps.json")
        raw_steps = agenda.get("steps") if isinstance(agenda, dict) else agenda
        for i, s in enumerate(raw_steps or []):
            if not isinstance(s, dict):
                continue
            title = str(_field(s, "title", "題", default="") or "").strip()
            kws = [str(k) for k in (_field(s, "検知キーワード", "keywords", default=[]) or []) if k]
            steps.append((_key(str(s.get("id") or ""), f"s{i + 1}"), title or f"段{i + 1}",
                          tuple(kws)))
            if len(steps) >= max_candidates:
                break
        qf = md / "quick_facts.md"
        if qf.exists():
            for i, e in enumerate(lookup_assist.parse_quick_facts(
                    qf.read_text(encoding="utf-8"))):
                facts.append((f"qf_{i + 1}", e["title"]))
                if len(facts) >= max_candidates:
                    break
            index = lookup_assist.Index(quick_facts=qf)
        phrase = _load_json(md / "phrasebook.json")
        triggers = tuple(phrase.get("lookup_triggers") or lookup_assist.DEFAULT_TRIGGERS)
        farewell = tuple(phrase.get("farewell_words")
                         or ("失礼します", "お疲れさまでした", "また来週", "また次回"))
        ask_marks = tuple(phrase.get("ask_marks") or ("ですか", "でしょうか", "ますか", "？", "?"))
    roster = list(load_roster(md / privacy.roster)) if md is not None else []
    if md is not None:
        known = {n for n, _ in roster}
        for key, alias in (("counterpart", privacy.guest_alias),
                           ("host_label", privacy.host_alias)):
            name = _strip_honorific(str(_load_json(md / "meeting.json").get(key) or ""))
            # 「相手」「進行役」のような既定の呼び方は名前ではないので入れない
            if len(name) >= 2 and name not in known and name not in (
                    "相手", "進行役", privacy.guest_alias, privacy.host_alias):
                roster.append((name, alias))
    return MeetingData(
        steps=tuple(steps), quick_facts=tuple(facts), roster=tuple(roster),
        lookup_triggers=triggers or lookup_assist.DEFAULT_TRIGGERS,
        farewell_words=farewell, ask_marks=ask_marks, index=index)


# ---------------------------------------------------------------- 人名マスク


class Masker:
    """名簿の名前を役名へ置き換える。**送る物の全体**に掛ける。

    state だけに掛けても足りない。段の見出し「④ Acme社の承認の道すじ」や
    即答表の見出しは、そのまま選択肢の説明として送られるため。
    """

    # 名前を分かち書きしたときの、それ自体は名前でない部品。ここを伏せると
    # 会議の実務情報（相手の呼び方）まで消えるので、部品としては登録しない。
    GENERIC = frozenset(("株式会社", "有限会社", "合同会社", "御中", "さん", "さま", "様",
                         "Inc", "Inc.", "Corp", "Corp.", "Ltd", "Ltd.", "LLC", "Co", "Co."))

    def __init__(self, roster=(), host_alias="〈進行役〉", guest_alias="〈相手〉"):
        pairs = []
        for name, alias in roster or ():
            forms = set()
            for whole in {name, unicodedata.normalize("NFKC", name)}:
                if not whole:
                    continue
                forms.add(whole)
                # 🔴 姓だけで呼ばれる方が普通。「山田 太郎」と書いてあっても
                #    発話は「山田です」なので、**部品ごとにも**伏せる
                #    (2026-09-20 実測: 名簿に姓名で書いた名が素通りした)。
                for part in whole.replace("　", " ").split(" "):
                    part = part.strip()
                    if len(part) >= 2 and part not in self.GENERIC:
                        forms.add(part)
            pairs.extend((f, alias) for f in forms)
        # 長い名前から先に置換する（「山田 太郎」を「山田」で先に潰さない）
        self.pairs = tuple(sorted(set(pairs), key=lambda x: len(x[0]), reverse=True))
        self.host_alias = host_alias
        self.guest_alias = guest_alias

    def text(self, s: str) -> str:
        out = s or ""
        for name, alias in self.pairs:
            if name in out:
                out = out.replace(name, alias)
        return out

    def scrub(self, obj):
        """辞書・配列・文字列を再帰的に辿って置換した複製を返す。"""
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            return {k: self.scrub(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.scrub(v) for v in obj]
        return obj

    def speaker(self, who: str) -> str:
        return self.host_alias if who == "host" else self.guest_alias


# ---------------------------------------------------------------- state と questions


def build_state(window, masker: Masker) -> dict:
    """直近K発話だけの state。**逐語の蓄積は入れない**。

    window … [{"speaker": "host"|"guest", "text": ...}, ...] 古い順・最後が今の発話
    """
    rows = [{"speaker": masker.speaker(r.get("speaker") or "guest"),
             "text": masker.text(r.get("text") or "")} for r in window]
    state = {"recent_utterances": rows}
    if rows:
        state["current_utterance"] = rows[-1]
    return state


def _candidates(q: Question, meeting: MeetingData) -> tuple:
    if q.candidates == "agenda_steps":
        return tuple((k, t) for k, t, _kw in meeting.steps)
    if q.candidates == "quick_facts":
        return tuple(meeting.quick_facts)
    return q.options


def build_questions(bundle: Bundle, meeting: MeetingData, speaker: str,
                    masker: Masker) -> dict:
    """この発話に対して送る問いの束（判定器の受け取る形）。

    · host 限定の問いは、相手の発話のときは**組み立てない**（送ってから捨てない）
    · 候補が会議フォルダから来る問いは、候補が1つも無ければ**問い自体を外す**
      （「該当なし」しか選べない問いは、料金だけ掛かって何も判らない）
    """
    out: dict = {}
    for q in bundle.questions:
        if not q.applies_to(speaker):
            continue
        if q.qtype == "choice":
            opts = _candidates(q, meeting)
            if not opts:
                continue
            crit = {k: masker.text(d or k) for k, d in opts}
            if q.include_none:
                crit[NONE_KEY] = "None of the above applies to the recent utterances."
            out[q.qid] = {"type": "choice",
                          "instructions": masker.text(q.instructions),
                          "criteria": crit}
        elif q.qtype == "score":
            levels = q.levels or _candidates(q, meeting)
            if len(levels) < 2:
                continue
            out[q.qid] = {"type": "score",
                          "instructions": masker.text(q.instructions),
                          "criteria": [masker.text(d or k) for k, d in levels]}
        else:
            item = {"type": "noul", "instructions": masker.text(q.instructions)}
            if q.criteria:
                item["criteria"] = {k: masker.text(v) for k, v in q.criteria.items()}
            out[q.qid] = item
    return out


def label_map(bundle: Bundle, meeting: MeetingData) -> dict:
    """鍵 → 人が読む見出し。``--dry-run`` と正解付けのために出す。"""
    out: dict = {}
    for q in bundle.questions:
        if q.qtype == "score":
            keys = [k for k, _ in (q.levels or ())]
        else:
            keys = [k for k, _ in _candidates(q, meeting)]
            if q.qtype == "choice" and q.include_none:
                keys.append(NONE_KEY)
        titles = dict(_candidates(q, meeting)) if q.qtype != "score" else dict(q.levels)
        out[q.qid] = {k: titles.get(k, k) or k for k in keys}
    return out


# ---------------------------------------------------------------- 答え


@dataclasses.dataclass
class Answer:
    """3つの型を1つの形に均す。``value`` は鍵、``confidence`` は 0〜1。"""

    qid: str
    qtype: str
    value: str = ""
    confidence: float = 0.0
    probabilities: dict = dataclasses.field(default_factory=dict)
    score: float = 0.0
    p_yes: float = 0.0

    def as_dict(self) -> dict:
        d = {"type": self.qtype, "value": self.value,
             "confidence": round(self.confidence, 4)}
        if self.probabilities:
            d["probabilities"] = {k: round(float(v), 4)
                                  for k, v in self.probabilities.items()}
        if self.qtype == "score":
            d["score"] = round(self.score, 4)
        if self.qtype == "noul":
            d["p_yes"] = round(self.p_yes, 4)
        return d


@dataclasses.dataclass
class Answers:
    """1発話ぶんの答え。どの実装が答えたかと、費用も一緒に持つ。"""

    by_id: dict = dataclasses.field(default_factory=dict)
    backend: str = ""
    usage: dict = dataclasses.field(default_factory=dict)
    model: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        return {k: a.as_dict() for k, a in self.by_id.items()}


def _level_key(levels, score: float) -> str:
    """Score の実数 → レベルの鍵。レベルの間に落ちることがあるので四捨五入。"""
    if not levels:
        return ""
    i = int(round(score))
    i = max(0, min(len(levels) - 1, i))
    return levels[i][0]


def parse_answer(qid: str, raw: dict, question: Question | None) -> Answer:
    """判定器の返り値1件を Answer に均す。

    🔴 Noul には confidence が無い（返るのは「はい」の確率そのもの）。
       校正を見るときの確信度は ``max(p, 1-p)`` と決めておく——
       Choice で調整した閾値を Noul に持ち込まない、が説明書の注意書き。
    """
    t = str(raw.get("type") or (question.qtype if question else "")).lower()
    if t == "noul":
        p = float(raw.get("noul") or 0.0)
        return Answer(qid=qid, qtype="noul", value="yes" if p >= 0.5 else "no",
                      confidence=max(p, 1.0 - p), p_yes=p)
    probs = raw.get("probabilities")
    probs = {str(k): float(v) for k, v in probs.items()} if isinstance(probs, dict) else {}
    if t == "score":
        score = float(raw.get("score") or 0.0)
        levels = question.levels if question else ()
        conf = raw.get("confidence")
        conf = float(conf) if conf is not None else (max(probs.values()) if probs else 0.0)
        return Answer(qid=qid, qtype="score", value=_level_key(levels, score),
                      confidence=conf, probabilities=probs, score=score)
    conf = raw.get("confidence")
    conf = float(conf) if conf is not None else (max(probs.values()) if probs else 0.0)
    return Answer(qid=qid, qtype="choice", value=str(raw.get("choice") or ""),
                  confidence=conf, probabilities=probs)


# ---------------------------------------------------------------- 実装


class DecisionEngine:
    """判定層の抽象。``evaluate(state, questions) -> Answers`` だけを持つ。"""

    name = "base"

    def evaluate(self, state: dict, questions: dict) -> Answers:
        raise NotImplementedError


class JevBackend(DecisionEngine):
    """外部の判定器へ REST で1往復。**落ちたら例外**（退避は呼び出し側の仕事）。

    再試行はここでは**しない**。会議中の判定は2秒で答えが出ないなら要らない
    ——遅れて出るカードは、会話が次へ行ったあとの邪魔にしかならない。
    """

    name = "jev"

    def __init__(self, settings: JevSettings, bundle: "Bundle | None" = None,
                 opener=None):
        self.settings = settings
        # 問いの定義が要る。Score は実数で返るので、レベルの並びを知らないと
        # 「1.4 は body」に直せない（返ってくる legend は説明文で、鍵ではない）。
        self.bundle = bundle
        self._opener = opener or urllib.request.urlopen
        if not settings.base_url:
            raise SystemExit(
                "[decisions] jev.base_url が設定されていません。\n"
                "           decisions.yaml の jev: に送り先を書いてください"
                "（この道具は宛先を内蔵しません）。")
        if not settings.key_env:
            raise SystemExit("[decisions] jev.key_env（鍵を入れる環境変数の名前）が空です。")

    def api_key(self) -> str:
        key = os.environ.get(self.settings.key_env) or ""
        if not key:
            raise DecisionError(
                f"環境変数 {self.settings.key_env} が空です（鍵は設定ファイルに書かない）")
        return key

    def evaluate(self, state: dict, questions: dict) -> Answers:
        body = {"state": state, "questions": questions}
        if self.settings.model:
            body["model"] = self.settings.model
        req = urllib.request.Request(
            self.settings.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key()}",
                     "Content-Type": "application/json"},
            method="POST")
        try:
            with self._opener(req, timeout=self.settings.timeout_sec) as res:
                payload = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:            # 4xx/5xx
            raise DecisionError(f"HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise DecisionError(f"届かない: {e!r}") from e
        except ValueError as e:                        # JSON が壊れている
            raise DecisionError(f"答えを読めない: {e!r}") from e
        raw = payload.get("answers")
        if not isinstance(raw, dict):
            raise DecisionError("answers が入っていない")
        return Answers(
            by_id={qid: parse_answer(qid, a if isinstance(a, dict) else {},
                                     self.bundle.question(qid) if self.bundle else None)
                   for qid, a in raw.items()},
            backend=self.name,
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
            model=str(payload.get("model") or ""))


class RulesBackend(DecisionEngine):
    """いまのキーワード判定を、同じ問いの形に包んだもの。

    包んだのは**現に動いている2つだけ**（段の検知＝step_detect、
    探し物＝lookup_assist）。発話の種類と約束の検知はルールを持っていないので、
    ここでは「分からない」に相当する答えを返す——**外れるのではなく、
    もともと持っていない**。9/19 に約束が1件も残らなかったのはこれが理由で、
    この空白こそ判定器に埋めてほしい場所。

    確信度は 1.0（規則は決まった通りに当たるか当たらないかで、確率ではない）。
    校正の表に並べたとき、ルールが「確信1.0で外す」のがそのまま見えるようにする。
    """

    name = "rules"

    def __init__(self, meeting: MeetingData, bundle: Bundle):
        self.meeting = meeting
        self.bundle = bundle

    # -- 材料の取り出し -----------------------------------------------------
    @staticmethod
    def _rows(state: dict) -> list:
        rows = state.get("recent_utterances")
        return rows if isinstance(rows, list) else []

    def _is_host(self, row: dict) -> bool:
        return (row or {}).get("speaker") == self.bundle.privacy.host_alias

    def _run(self, rows: list) -> int:
        """相手の発話のあと、こちら側の何発話目か（窓の中だけで数える）。"""
        run = 0
        for r in rows:
            run = run + 1 if self._is_host(r) else 0
        return run

    @staticmethod
    def _kw_hit(kw: str, text: str) -> bool:
        try:
            return re.search(kw, text or "") is not None
        except re.error:
            return (kw or "") in (text or "")

    # -- 問いごとの規則 -----------------------------------------------------
    def _step(self, rows: list) -> Answer:
        cur = rows[-1] if rows else {}
        text = cur.get("text") or ""
        hit = NONE_KEY
        if self._is_host(cur) and step_detect.is_turn_open(self._run(rows), text):
            for key, _title, kws in self.meeting.steps:
                if step_detect.step_hit(kws, text, self._kw_hit):
                    hit = key
        return Answer(qid="", qtype="choice", value=hit, confidence=1.0)

    def _phase(self, rows: list, question: Question) -> Answer:
        blob = " ".join(r.get("text") or "" for r in rows)
        key = "closing" if any(w and w in blob for w in self.meeting.farewell_words) else "body"
        keys = [k for k, _ in (question.levels or ())]
        if key not in keys:
            key = keys[min(1, len(keys) - 1)] if keys else ""
        score = float(keys.index(key)) if key in keys else 0.0
        return Answer(qid="", qtype="score", value=key, confidence=1.0, score=score)

    def _lookup(self, rows: list) -> Answer:
        cur = rows[-1] if rows else {}
        yes = (self._is_host(cur)
               and lookup_assist.is_lookup(cur.get("text") or "",
                                           self.meeting.lookup_triggers))
        return Answer(qid="", qtype="noul", value="yes" if yes else "no",
                      confidence=1.0, p_yes=1.0 if yes else 0.0)

    def _quick_fact(self, rows: list) -> Answer:
        cur = rows[-1] if rows else {}
        prev_guest = next((r.get("text") or "" for r in reversed(rows[:-1])
                           if not self._is_host(r)), "")
        key = NONE_KEY
        # 🔴 いまの実装と同じ順序で当てる。索引を引くのは**探し始めの合図が
        #    出たときだけ**で、合図なしに引くと当たりっぱなしになる
        #    (2026-09-20 実測: 無関係な発話に即答表の行が毎回付いた)。
        if (self.meeting.index is not None and self._is_host(cur)
                and lookup_assist.is_lookup(cur.get("text") or "",
                                            self.meeting.lookup_triggers)):
            found = self.meeting.index.find(cur.get("text") or "", prev_guest)
            if found:
                key = next((k for k, t in self.meeting.quick_facts
                            if t == found.get("target")), NONE_KEY)
        return Answer(qid="", qtype="choice", value=key, confidence=1.0)

    def _unknown(self, question: Question) -> Answer:
        """規則を持っていない問い。「該当なし」「いいえ」を確信0で返す。"""
        if question.qtype == "noul":
            return Answer(qid="", qtype="noul", value="no", confidence=0.0, p_yes=0.0)
        if question.qtype == "score":
            keys = [k for k, _ in (question.levels or ())]
            return Answer(qid="", qtype="score", value=keys[0] if keys else "",
                          confidence=0.0)
        return Answer(qid="", qtype="choice", value=NONE_KEY, confidence=0.0)

    def evaluate(self, state: dict, questions: dict) -> Answers:
        rows = self._rows(state)
        out: dict = {}
        for qid in questions:
            q = self.bundle.question(qid) or Question(qid=qid, qtype="choice")
            if q.candidates == "agenda_steps":
                a = self._step(rows)
            elif q.candidates == "quick_facts":
                a = self._quick_fact(rows)
            elif q.qtype == "score" and q.levels:
                a = self._phase(rows, q)
            elif q.qtype == "noul" and "lookup" in qid:
                a = self._lookup(rows)
            else:
                a = self._unknown(q)
            a.qid = qid
            out[qid] = a
        return Answers(by_id=out, backend=self.name)


class FallbackEngine(DecisionEngine):
    """本命が落ちたら退避先へ。**どちらが答えたかを記録に残す**のが役目。

    「Jev を止めても最後まで通る」を、replay と本番の両方で同じ経路にするため
    ここに1本化する（退避を呼び出し側ごとに書くと、片方だけ直り忘れる）。
    """

    name = "fallback"

    def __init__(self, primary: DecisionEngine, secondary: DecisionEngine):
        self.primary = primary
        self.secondary = secondary

    def evaluate(self, state: dict, questions: dict) -> Answers:
        try:
            return self.primary.evaluate(state, questions)
        except DecisionError as e:
            ans = self.secondary.evaluate(state, questions)
            ans.backend = f"{self.secondary.name}(fallback)"
            ans.error = f"{self.primary.name}: {e}"
            return ans


def make_engine(kind: str, bundle: Bundle, meeting: MeetingData,
                opener=None) -> DecisionEngine:
    """``rules`` / ``jev``（＝Jev、落ちたら rules へ退避）を組み立てる。"""
    rules = RulesBackend(meeting, bundle)
    if kind == "rules":
        return rules
    if kind == "jev":
        return FallbackEngine(JevBackend(bundle.jev, bundle=bundle, opener=opener), rules)
    raise SystemExit(f"[decisions] 知らない backend: {kind!r}（rules か jev）")


# ---------------------------------------------------------------- 記録


class DecisionLog:
    """``decisions.jsonl`` — 送った物と受けた物を**全件**残す。

    残す理由は3つ: ①何を外へ送ったかを後から確かめられる（送信内容の確認）
    ②会議のあとに人が正解を付ければ、そのまま閾値調整の材料になる
    ③usage を足せば1会議ぶんの費用が出る。
    """

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.n = 0

    def write(self, *, utterance_id, ts, speaker, state, questions,
              answers: Answers, latency_ms: float) -> dict:
        rec = {
            "utterance_id": utterance_id,
            "ts": ts,
            "speaker": speaker,
            "backend": answers.backend,
            "latency_ms": round(latency_ms, 1),
            "model": answers.model,
            "state": state,
            "questions": questions,
            "answers": answers.as_dict(),
            "usage": answers.usage,
            "error": answers.error,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.n += 1
        return rec


def window_of(history, k: int, max_chars: int) -> list:
    """直近K発話。合計が ``max_chars`` を超えたら古い方から落とす。"""
    win = list(history[-k:]) if k > 0 else []
    while len(win) > 1 and sum(len(r.get("text") or "") for r in win) > max_chars:
        win.pop(0)
    return win


def evaluate_utterance(engine: DecisionEngine, bundle: Bundle, meeting: MeetingData,
                       masker: Masker, window: list) -> tuple:
    """窓1つぶんを判定する。返りは (state, questions, answers, 掛かったミリ秒)。"""
    speaker = (window[-1].get("speaker") if window else "guest") or "guest"
    state = build_state(window, masker)
    questions = build_questions(bundle, meeting, speaker, masker)
    if not questions:
        return state, questions, Answers(backend=getattr(engine, "name", "")), 0.0
    t0 = time.perf_counter()
    answers = engine.evaluate(state, questions)
    return state, questions, answers, (time.perf_counter() - t0) * 1000.0
