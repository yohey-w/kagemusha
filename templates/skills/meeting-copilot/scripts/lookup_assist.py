#!/usr/bin/env python3
"""lookup_assist.py — 進行役が「探し始めた」のを検知して、探している物を出す層。

--- なぜ要るか (2026-09-19 殿の要望・逐語) ---
「おれが相手の応答に対して回答するのに情報をさがすときがあるんだけど、いちいち
君にきいてたじゃん。おれが情報をさがしているのを検知して、そのときに探している
情報をだしてくれるとめっちゃたすかる」

会議中に本当に要るのは推論ではなく**索引**。URL・アカウント名・件数・日付・
手順の所在は、その場で1秒以内に出れば足りる。だから LLM を呼ぶ前にここで当てる。

--- 3段構え ---
  1. 合図の検知 … 「ちょっとお待ちください」「確認します」「どこだっけ」など。
                   語彙は phrasebook.json の ``lookup_triggers``(設定側)。
  2. 探し物の特定 … こちら側の発話＋**相手の直前の発話**から手掛かりの語を取る
                   (探し物は直前に相手が言った物であることがほとんど)。
  3. 索引を引く   … quick_facts.md(即答表) → ledger.yaml の facts → kb/ の順。
                   当たらなければ呼び出し側が answerer(LLM)へ回す。

🔴 秘密は出さない。合言葉・鍵・トークンに触れる項目は**値を出さず所在だけ**を返し、
   値らしき長い文字列は伏字にする。画面共有に映る事故を、索引の側で止める。

即答表 quick_facts.md の書き方(会議フォルダ直下・任意):

    ## 検証環境の入口
    画面: 検証用のログイン画面（資料棚の「環境一覧」1行目）
    ID: demo-01 / demo-02 / demo-03

    ## 管理画面の合言葉
    値は書かない。鍵パネル（🔑）に入っています。

見出し(##)が話題、その下の行が「そのまま読める値」。
"""
from __future__ import annotations

import pathlib
import re
import unicodedata

# 探し始めの合図の既定値。phrasebook.json の lookup_triggers があればそちらが勝つ。
DEFAULT_TRIGGERS = (
    "ちょっとお待ち", "少々お待ち", "お待ちください", "確認します", "確認させて",
    "どこだっけ", "なんだっけ", "何だっけ", "えーっと", "えっと",
    "探して", "さがして", "出しますね", "開きますね", "見てみます",
    "いま調べ", "今調べ", "調べます", "何でしたっけ", "なんでしたっけ",
    "one moment", "let me check", "hold on", "bear with me", "looking it up",
)

# 値を画面に出してはいけない話題。見出し・本文のどちらに出ても効く。
SECRET_WORDS = (
    "パスワード", "合言葉", "秘密", "鍵", "トークン", "クレデンシャル",
    "password", "passwd", "secret", "token", "api key", "apikey", "api_key",
    "credential", "private key",
)
# 伏字にする「値らしい塊」。長い英数字・記号列は、名前ではなく値とみなす。
VALUE_RE = re.compile(r"[A-Za-z0-9_\-+/=.]{12,}")

_WORD_RE = re.compile(r"[一-鿿]{2,}|[ァ-ヶー]{2,}|[0-9a-z]{2,}")
# 探し物の手掛かりになりやすい語(相手の直前の発話から拾う足しにする)
HINT_WORDS = ("url", "アドレス", "リンク", "id", "アカウント", "鍵", "キー",
              "件数", "何件", "日付", "いつ", "手順", "料金", "金額", "番号",
              "バージョン", "設定", "場所", "どこ")


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).lower()


def is_lookup(text: str, triggers=DEFAULT_TRIGGERS) -> bool:
    """この発話は「探し始めた」合図か。"""
    t = norm(text)
    return any(norm(w) in t for w in triggers if w)


def words(s: str) -> set:
    """照合用の語。ひらがなを区切りとみなして漢字・カタカナ・英数字の塊だけ拾う。"""
    return set(_WORD_RE.findall(norm(re.sub(r"[（(].*?[)）]", " ", s or ""))))


def is_secret(text: str) -> bool:
    t = norm(text)
    return any(w in t for w in SECRET_WORDS)


def mask(text: str) -> str:
    """値らしい塊を伏字にする。所在の説明は残す。"""
    return VALUE_RE.sub("••••", text or "")


# ---------------------------------------------------------------- 索引

def parse_quick_facts(text: str) -> list[dict]:
    """即答表 md → [{title, body, line, secret}]。見出し(#〜###)が話題。"""
    out: list[dict] = []
    cur = None
    for i, raw in enumerate((text or "").replace("\r\n", "\n").split("\n"), 1):
        st = raw.strip()
        m = re.match(r"^#{1,6}\s+(.*)$", st)
        if m:
            cur = {"title": re.sub(r"[*`]", "", m.group(1)).strip(),
                   "body": [], "line": i}
            out.append(cur)
            continue
        if cur is None or not st or st.startswith(("---", ">")):
            continue
        cur["body"].append(re.sub(r"^[-*+]\s+", "", st))
    res = []
    for e in out:
        body = " / ".join(e["body"]).strip()
        if not e["title"] and not body:
            continue
        res.append({"title": e["title"], "body": body, "line": e["line"],
                    "secret": is_secret(e["title"] + " " + body)})
    return res


def load_facts(ledger_path) -> list[dict]:
    """台帳 ledger.yaml の facts。PyYAML が無ければ静かに空を返す(この層は任意)。"""
    try:
        import yaml
    except ImportError:
        return []
    try:
        d = yaml.safe_load(pathlib.Path(ledger_path).read_text(encoding="utf-8")) or {}
    except Exception:       # noqa: BLE001  索引が読めなくても会議は続ける
        return []
    out = []
    for f in (d.get("facts") or []):
        if isinstance(f, dict) and f.get("id") and f.get("title"):
            out.append({"id": str(f["id"]), "title": str(f["title"])})
    return out


class Index:
    """即答表 + 台帳 + kb/ をまとめて引ける索引。作るのは会議の開始時に1回。"""

    def __init__(self, quick_facts=None, ledger=None, kb_dir=None, kb_max=40):
        self.entries: list[dict] = []
        if quick_facts is not None:
            p = pathlib.Path(quick_facts)
            if p.exists():
                for e in parse_quick_facts(p.read_text(encoding="utf-8")):
                    self.entries.append({
                        "target": e["title"] or "即答表",
                        "status": f"即答表 {p.name} の {e['line']}行目",
                        "say": e["body"] or e["title"],
                        "ref": "",
                        "secret": e["secret"],
                        "bag": words(e["title"] + " " + e["body"]),
                    })
        for f in load_facts(ledger) if ledger is not None else []:
            self.entries.append({
                "target": f["title"][:40],
                "status": "台帳にある事実",
                "say": f["title"],
                "ref": f["id"],
                "secret": is_secret(f["title"]),
                "bag": words(f["title"]),
            })
        if kb_dir is not None:
            d = pathlib.Path(kb_dir)
            if d.is_dir():
                for fp in sorted(d.glob("*"))[:kb_max]:
                    if not fp.is_file():
                        continue
                    try:
                        head = fp.read_text(encoding="utf-8", errors="replace")[:400]
                    except OSError:
                        continue
                    line = next((l.strip() for l in head.splitlines() if l.strip()), "")
                    self.entries.append({
                        "target": fp.stem,
                        "status": f"資料 {fp.name}",
                        "say": line[:80] or fp.name,
                        "ref": "",
                        "secret": is_secret(head),
                        "bag": words(fp.stem + " " + head),
                    })

    def __len__(self) -> int:
        return len(self.entries)

    def find(self, host_text: str, guest_text: str = "") -> dict | None:
        """探し物を1件返す。当たらなければ None。

        手掛かりはこちらの発話と相手の直前の発話の両方。相手の側を強くする
        (探しているのは、たいてい相手が直前に言った物)。
        """
        bag = words(host_text)
        gbag = words(guest_text)
        if not bag and not gbag:
            return None
        best, score = None, 0.0
        for e in self.entries:
            n = sum(len(w) for w in (bag & e["bag"]))
            n += 1.5 * sum(len(w) for w in (gbag & e["bag"]))
            if n > score:
                best, score = e, n
        if best is None or score < 2.0:
            return None
        return self.render(best)

    @staticmethod
    def render(e: dict) -> dict:
        say, status = e["say"], e["status"]
        if e["secret"]:
            say = "値は画面に出しません。鍵パネル（🔑）で確認してください。 " + mask(say)
            status += "・秘密のため値は伏せています"
        return {"target": e["target"], "status": status, "say": say[:120],
                "ref": e.get("ref", "")}


def hints(guest_text: str) -> list[str]:
    """相手の直前の発話に「探し物らしい語」が入っていれば返す(記録用の手掛かり)。"""
    t = norm(guest_text)
    return [w for w in HINT_WORDS if w in t]
