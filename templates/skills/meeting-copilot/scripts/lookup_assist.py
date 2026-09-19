#!/usr/bin/env python3
"""lookup_assist.py — 進行役が「探し始めた」のを検知して、探している物を出す層。

--- なぜ要るか (2026-09-19 実走での要望・逐語) ---
「相手の応答に対して回答するのに情報をさがすときがあるんだけど、いちいち
（AIに）きいてたじゃん。情報をさがしているのを検知して、そのときに探している
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

# --- 伏字にする項目の決め方 ------------------------------------------------
# 🔴 判定は**見出しの型**で行う。本文の語では判定しない。
#
# 旧実装は見出しと本文の全文に「鍵」「秘密」などを部分一致させていた。同梱のデモで
# 実害が出た(2026-09-20 レビュー実測): 「連携の相手先」という項目の本文に
# 「動画配信: 鍵があと1つだけ足りない」と書いてあるだけで、決済・メール配信の状況まで
# **項目まるごと伏字**になった——進行役がその場で言いたい実務情報そのものが消えた。
#
# だから2段で決める。どちらも**見出しだけ**を見る:
#   1. 明示の印  … 「secret: …」「秘密: …」で始まる、または [secret] / [秘密] を含む
#   2. 値の名前  … 見出しがその値そのものを名指している場合だけ(下の語)
# 「鍵」「key」のような**一般語は入れない**。鍵の話題は会議の実務情報でもあるため。
SECRET_MARK = re.compile(r"^\s*(secret|秘密|機密)\s*[:：]|\[\s*(secret|秘密|機密)\s*\]",
                         re.I)
# 見出しがこの語を含むとき、その項目は「値そのもの」を指しているとみなす。
SECRET_HEAD_WORDS = (
    "パスワード", "ぱすわーど", "合言葉", "あいことば", "秘密鍵", "暗証",
    "アクセストークン", "トークン", "apiキー", "api キー", "クレデンシャル",
    "password", "passwd", "passphrase", "private key", "secret key",
    "access token", "auth token", "api key", "apikey", "api_key",
    "credential", "client secret",
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


def is_secret(title: str) -> bool:
    """**見出しだけ**を見て、その項目が「値そのもの」かを決める。

    本文は見ない。本文に鍵やトークンの話が出てくるのは普通のことで、そこで
    項目まるごと伏字にすると実務情報が消える(上のコメントの実害)。
    """
    t = (title or "").strip()
    if SECRET_MARK.search(t):
        return True
    n = norm(t)
    return any(w in n for w in SECRET_HEAD_WORDS)


def strip_mark(title: str) -> str:
    """見出しから「secret:」「[秘密]」の印を落として、画面に出す名前にする。"""
    t = SECRET_MARK.sub("", title or "", count=1)
    return t.strip(" 　:：") or (title or "").strip()


def mask(text: str) -> str:
    """値らしい塊を伏字にする。所在の説明は残す。"""
    return VALUE_RE.sub("••••", text or "")


# ---------------------------------------------------------------- 索引

def parse_quick_facts(text: str) -> list[dict]:
    """即答表 md → [{title, body, line, secret}]。話題は ``##`` 以下の見出し。

    🔴 H1(``# ``)は**読み飛ばす**。H1 はその表そのものの題で、下に続くのは
    「この表の書き方」の説明文であって会議の事実ではない。無差別に拾うと、
    説明文が1件の「事実」として検索に混ざる(2026-09-20 レビュー実測)。
    """
    out: list[dict] = []
    cur = None
    for i, raw in enumerate((text or "").replace("\r\n", "\n").split("\n"), 1):
        st = raw.strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", st)
        if m:
            if len(m.group(1)) == 1:        # H1 = 表の題。ここから次の見出しまでは前書き
                cur = None
                continue
            cur = {"title": re.sub(r"[*`]", "", m.group(2)).strip(),
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
        res.append({"title": strip_mark(e["title"]), "body": body, "line": e["line"],
                    "secret": is_secret(e["title"])})
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
                        # 資料も「見出し」で決める。ここではファイル名がその役
                        # (中身に鍵の話が出てくるだけで資料1件が丸ごと伏字になると、
                        #  会議で読みたい行が消える)
                        "secret": is_secret(fp.stem),
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
