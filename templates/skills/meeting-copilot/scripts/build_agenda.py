#!/usr/bin/env python3
"""build_agenda.py — 進行表1枚から agenda_steps.json と talk_script.md を作る。

    python3 build_agenda.py 進行表.md --out ~/meetings/2026-01-20-acme
    python3 build_agenda.py 進行表.md --out <会議フォルダ> --total-min 60 --check

--- なぜ要るか (2026-09-19 実走の実測) ---
台本(talk_script.md)と、相手にも見せる進行表(Notion の確認シート)を**二重に**
書いていた。会議では進行表の流れで話し、台本は一度も見られなかった。突合の結果、
台本の特徴句40件のうち実際の発話に現れたのは**1件**（しかも別件の偶然一致）。
段②③④⑥⑨⑩は語彙レベルで一度も現れず、段の自動切替は4回とも無関係な語の一致。

⇒ **正本を1枚にする**。相手に貼る進行表と、こちらのカンペは、同じファイルから作る。
   コードは OSS 1本・会議ごとに違うのはこの Markdown 1枚だけ。

--- 入力 (汎用の Markdown 進行表) ---
見出し + チェックリストの、ごく普通の Markdown。Notion にそのまま貼れる形。

    ## 📋 アジェンダ（60分）
    - [ ] **1. 今日決めたいこと（5分）** — ①合否 ②請求の宛名
    - [ ] **2. 現状のすり合わせ（10分）** — 5行で読み上げて一度止める

    ## ❓ 確認したいこと
    **今日ぜひお答えいただきたいもの**
    - [ ] 確認表はどこまで進んでいますか。今日「合格」と言えますか
    - [ ] ご請求書の宛名はどちらにしますか

見出しは「アジェンダ / agenda / 進行」「確認したいこと / 確認事項 / questions」を
含むものを拾う(絵文字・括弧つきでよい)。各項目の書式:

    - [ ] **<番号>. <題>（<分>分）** — <取る答え>

題・分・取る答えのどれが欠けても落ちない(分はあとで按分、取る答えは題で代用)。

--- 機械では決められないところ (注記で足す) ---
Markdown のコメントは Notion に貼っても表示されないので、**同じ1枚**に紛れ込ませられる。
項目の行末か次の行に置く:

    <!-- kw: この段で必ず口にする語|別の言い方 -->   段の検知キーワードを足す
    <!-- say: ここで言うキメ台詞 -->                言い方の例を上書き
    <!-- ask: 抜けたときに出す問い -->              その段の問いを上書き
    <!-- must: 取るものの名前 | 検知語1|検知語2 -->  必須取得物(複数行書ける)

--- 出力 ---
agenda_steps.json … 番人(copilot.py)と画面(viewer2.py)が読む段取りの正本。
                    各段に「取る答え」「言い方の例」「抜けたら出す問い」を持つ。
talk_script.md    … カンペ。段ごとに**3行だけ**:
                      取る答え: …      (小さく・注記)
                      **…**            (言い方の例・大きく。answers_only では隠れる)
                      **抜けたら: …**  (取れていないときに出す問い)

🔴 埋められない欄に文章を発明しない。作れなかったところは「（要記入）」と書いて出す。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import unicodedata

# 見出しの当たり(部分一致・小文字化して比較)
AGENDA_HEADS = ("アジェンダ", "agenda", "進行表", "進行", "次第")
ASK_HEADS = ("確認したいこと", "確認事項", "伺いたい", "質問", "questions", "asks")

CHECK_RE = re.compile(r"^\s*[-*+]\s*\[[ xX]\]\s*(.*)$")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
NOTE_RE = re.compile(r"<!--\s*(kw|say|ask|must)\s*:\s*(.*?)\s*-->", re.I)
MIN_RE = re.compile(r"[（(]\s*(?:およそ|約)?\s*(\d+)\s*分\s*[)）]")
NUM_RE = re.compile(r"^\s*(\d+)\s*[.．、)）:：]\s*")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

TODO = "（要記入）"


# ---------------------------------------------------------------- 文字の始末

def strip_md(s: str) -> str:
    """強調・コード・チェックボックス・コメントを落として素の文にする。"""
    s = NOTE_RE.sub("", s or "")
    s = re.sub(r"`+", "", s)
    s = re.sub(r"\*\*|__|\*|_", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)     # [文言](url) → 文言
    s = re.sub(r"<[^>]{1,80}>", "", s)
    return s.strip()


def tidy(s: str, n: int = 0) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip(" 　:：-—–・")
    if n and len(s) > n:
        s = s[: n - 1] + "…"
    return s


def head_text(line: str) -> str | None:
    m = HEAD_RE.match(line.strip())
    return strip_md(m.group(2)) if m else None


def head_is(text: str, words) -> bool:
    t = (text or "").lower()
    return any(w.lower() in t for w in words)


def notes_of(text: str) -> dict:
    """1行に埋まっている <!-- kw: … --> 等をまとめて取り出す。"""
    out: dict = {"kw": [], "say": "", "ask": "", "must": []}
    for kind, body in NOTE_RE.findall(text or ""):
        kind = kind.lower()
        body = body.strip()
        if not body:
            continue
        if kind == "kw":
            out["kw"] += [x.strip() for x in body.split("|") if x.strip()]
        elif kind == "say":
            out["say"] = body
        elif kind == "ask":
            out["ask"] = body
        elif kind == "must":
            name, _, kws = body.partition("|")
            name = name.strip()
            if name:
                out["must"].append(
                    {"名前": name,
                     "検知キーワード": [x.strip() for x in kws.split("|") if x.strip()] or [name]}
                )
    return out


# ---------------------------------------------------------------- 読み取り

def split_sections(text: str) -> list[dict]:
    """見出しごとに {title, lines} へ割る。見出しの前の本文は title="" に入る。"""
    secs = [{"title": "", "lines": []}]
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        h = head_text(raw)
        if h is not None:
            secs.append({"title": h, "lines": []})
            continue
        secs[-1]["lines"].append(raw)
    return secs


def collect_items(lines) -> list[dict]:
    """チェックリスト項目を拾う。直後の行にだけ書かれた注記も同じ項目へ畳む。

    項目の前に出てくる太字だけの行は「小見出し」として group に控える
    (「今日ぜひお答えいただきたいもの」「時間があれば」の区別に使う)。
    """
    items: list[dict] = []
    group = ""
    for raw in lines:
        line = raw.rstrip()
        st = line.strip()
        m = CHECK_RE.match(line)
        if m:
            items.append({"raw": m.group(1), "group": group})
            continue
        if not st:
            continue
        if items and NOTE_RE.search(st) and not CHECK_RE.match(line):
            items[-1]["raw"] += " " + st        # 次の行に置いた注記を畳む
            continue
        mb = re.match(r"^\*\*(.+?)\*\*[:：]?\s*$", st)
        if mb:
            group = strip_md(mb.group(1))
    return items


def parse_step(item: dict, order: int) -> dict:
    """アジェンダ1項目 → 段1つ。"""
    raw = item["raw"]
    note = notes_of(raw)
    body = strip_md(raw)

    minutes = 0.0
    mm = MIN_RE.search(body)
    if mm:
        minutes = float(mm.group(1))
        body = MIN_RE.sub("", body, count=1)

    # 「— 取る答え」「- 取る答え」「： 取る答え」で題と中身を割る
    title, answer = body, ""
    m = re.split(r"\s*(?:—|――|–|―|:|：|\s-\s)\s*", body, maxsplit=1)
    if len(m) == 2 and m[0].strip():
        title, answer = m[0], m[1]

    title = tidy(title)
    title = NUM_RE.sub("", title) or f"ステップ{order}"
    answer = tidy(answer) or title

    say = note["say"] or f"では、{title}に入らせてください。"
    ask = note["ask"]

    # 段の検知キーワード: 言い方の例の中に**文字どおり**含まれる語にする。
    # そうしておくと「キメ台詞を読んだら段が進む」が成り立つ(実走で壊れていたのがここ)。
    kws = list(note["kw"])
    core = keyword_of(title)
    if core and core in say and core not in kws:
        kws.insert(0, core)
    if not kws:
        kws = [title[:12]] if title else []

    return {
        "id": f"s{order}",
        "title": f"{circled(order)} {title}",
        "目安分": minutes,
        "検知キーワード": kws,
        "必須取得物": note["must"],
        "取る答え": answer,
        "言い方の例": say,
        "抜けたら出す問い": ask,
        "nudge": answer,
        "台本": [say],
    }


def circled(n: int) -> str:
    return CIRCLED[n - 1] if 1 <= n <= len(CIRCLED) else f"{n}."


def keyword_of(title: str) -> str:
    """段の題から、検知に使う核の語を1つだけ取る。

    記号・丸数字・括弧の中を落とし、助詞で切って**いちばん長い塊**を採る。
    短すぎる語(2字未満)は誤爆するので使わない。
    """
    t = re.sub(r"[（(].*?[)）]", "", title or "")
    t = re.sub(r"^[0-9０-９" + CIRCLED + r"\s.．、)）:：]+", "", t).strip()
    parts = _WORD_RE.findall(t)
    if not parts:
        return t[:12]
    return max(parts, key=len)[:12]


# ---------------------------------------------------------------- 割り付け

def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).lower()


_WORD_RE = re.compile(r"[一-鿿]{2,}|[ァ-ヶー]{2,}|[0-9a-z]{2,}")


def nouns(s: str) -> set:
    """照合用の語の集合。

    日本語は分かち書きしないので、**ひらがなを区切りとみなして**漢字・カタカナ・
    英数字の連なりだけを拾う(助詞で割ると「担当さ」のような欠けた塊が出て、
    同じ語どうしが一致しなくなる)。外部ライブラリは使わない。
    """
    return set(_WORD_RE.findall(norm(re.sub(r"[（(].*?[)）]", " ", s or ""))))


def assign_asks(steps: list[dict], asks: list[dict]) -> list[dict]:
    """「確認したいこと」を段へ割り付ける。**決め方を1つに固定する**:

      1. 段の題+取る答えと**重なった語の長さの合計**を、その段の語数で割った値が
         いちばん大きい段。
         · 件数で数えると「データ」と「移行」が同じ1点になり、先に書いた段が総取りする
           ⇒ 長い語ほど効かせる
         · 「今日決めたいこと」のように**他の段の話題を全部並べる段**は、
           どの問いにも当たってしまい、ぜんぶ吸い込む
           ⇒ 語数で割って「その問いの話が主題になっている段」を勝たせる
      2. どこにも重ならなければ「先に伺う」性格の段(題に 伺/確認/質問 を含む)
      3. それも無ければ先頭の段
    同点は前の段が勝つ(並びが変わらない＝作り直しても結果が動かない)。

    割り付いた問いは、その段の「抜けたら出す問い」と必須取得物になる。
    推測で文を作らない——問いは進行表に書いてある文そのまま。
    """
    if not steps:
        return []
    bags = [nouns(s["title"]) | nouns(s.get("取る答え", "")) for s in steps]
    fallback = next((i for i, s in enumerate(steps)
                     if re.search(r"(伺|確認|質問)", s["title"])), 0)

    for a in asks:
        text = a["text"]
        bag = nouns(text)
        best, score = None, 0.0
        for i, b in enumerate(bags):
            n = float(sum(len(w) for w in (bag & b)))
            # 片方がもう片方を含むだけ(移行 ⊂ 移行範囲)は半分の重み
            n += 0.5 * sum(len(w) for w in bag - b
                           if any(w in x or x in w for x in b))
            n /= max(1.0, len(b)) ** 0.5     # 話題を並べただけの段に総取りさせない
            if n > score:
                best, score = i, n
        i = best if best is not None else fallback
        s = steps[i]
        a["step"] = i
        if not s["抜けたら出す問い"]:
            s["抜けたら出す問い"] = tidy(text, 60)
        # 必須取得物: 問いの中の語を検知キーワードにする(長いものから3つ)。
        # 語の集合は順序を持たないので、長さが同じものは文字順で割り、
        # **同じ進行表からは必ず同じ JSON が出る**ようにする(差分が毎回出ない)。
        kws = sorted((w for w in bag if len(w) >= 3), key=lambda w: (-len(w), w))[:3]
        s["必須取得物"].append({
            "名前": tidy(text, 28),
            "検知キーワード": kws or [tidy(text, 10)],
            "問い": tidy(text, 60),
            "重み": a.get("group", ""),
        })
    for s in steps:
        if not s["抜けたら出す問い"]:
            s["抜けたら出す問い"] = TODO
    return asks


def spread_minutes(steps: list[dict], total: float) -> None:
    """分が書いていない段に、残り時間を等分で置く。全部書いてあれば触らない。"""
    known = sum(s["目安分"] for s in steps)
    blanks = [s for s in steps if not s["目安分"]]
    if not blanks:
        return
    rest = max(0.0, (total or 0.0) - known)
    each = round(rest / len(blanks), 1) if rest else 0.0
    for s in blanks:
        s["目安分"] = each


# ---------------------------------------------------------------- 書き出し

def build(text: str, total_min: float = 0.0, title: str = "") -> dict:
    secs = split_sections(text)
    # 表題にも「進行表」が入ることがあるので、**チェックリストが実際にある節**だけを
    # 候補にする(見出しの語だけで決めると、文書のタイトルを掴んで空振りする)。
    ag_lines, ask_lines, ag_head = [], [], ""
    for sec in secs:
        if not any(CHECK_RE.match(l) for l in sec["lines"]):
            continue
        if head_is(sec["title"], AGENDA_HEADS) and not ag_lines:
            ag_lines, ag_head = sec["lines"], sec["title"]
        elif head_is(sec["title"], ASK_HEADS) and not ask_lines:
            ask_lines = sec["lines"]

    if not ag_lines:
        raise SystemExit(
            "[build_agenda] アジェンダの節が見つかりません。\n"
            "  見出しに「アジェンダ」「進行」「次第」「agenda」のどれかを入れ、\n"
            "  その下に `- [ ] **1. 題（5分）** — 取る答え` の形で並べてください。"
        )

    items = collect_items(ag_lines)
    if not items:
        raise SystemExit(
            f"[build_agenda] 「{ag_head}」の下にチェックリスト項目がありません。\n"
            "  `- [ ] …` の形の行が1つも無い状態です。"
        )
    steps = [parse_step(it, i + 1) for i, it in enumerate(items)]

    asks = [{"text": strip_md(it["raw"]), "group": it["group"]}
            for it in collect_items(ask_lines) if strip_md(it["raw"])]
    assign_asks(steps, asks)

    if not total_min:
        mm = MIN_RE.search(ag_head)
        total_min = float(mm.group(1)) if mm else 0.0
    spread_minutes(steps, total_min)
    total = total_min or sum(s["目安分"] for s in steps) or 60.0

    return {"title": title, "steps": steps, "asks": asks, "total_min": total}


def to_agenda_json(built: dict, src_name: str) -> dict:
    steps = []
    for s in built["steps"]:
        d = {k: v for k, v in s.items() if k != "nudge"}
        d["nudge"] = s["nudge"]
        steps.append(d)
    return {
        "_comment": [
            f"build_agenda.py が {src_name} から生成しました。手で直してもよいですが、",
            "元の進行表を直して作り直すほうが、相手に渡す1枚と食い違いません。",
            "各段の「取る答え」「言い方の例」「抜けたら出す問い」がカードの3要素になります。",
            "検知キーワードは『言い方の例』に文字どおり含まれる語です(読めば段が進む)。",
        ],
        "会議分": built["total_min"],
        "警報分": 10,
        "steps": steps,
    }


def to_talk_script(built: dict, src_name: str) -> str:
    out = [f"# 台本（{src_name} から生成・段ごとに3行）", ""]
    out += [
        "各段は3行だけです。",
        "",
        "| 行 | 中身 | 画面 |",
        "|---|---|---|",
        "| `取る答え: …` | この段で必ず取るもの | 小さく（常に出る） |",
        "| `**…**` | 言い方の例（短いキメ台詞） | 大きく（`script_mode: answers_only` で隠れる） |",
        "| `**抜けたら: …**` | 取れていないときに出す問い | 大きく（常に出る） |",
        "",
        "文言を変えるときは、元の進行表を直して作り直してください"
        "（相手に渡す1枚とカンペが1本のままになります）。",
        "",
        "---",
        "",
    ]
    for i, s in enumerate(built["steps"], 1):
        out.append(f"## 【{i}】 {s['title']}")
        out.append("")
        out.append(f"取る答え: {s['取る答え']}")
        out.append("")
        out.append(f"**{s['言い方の例']}**")
        out.append("")
        out.append(f"**抜けたら: {s['抜けたら出す問い']}**")
        out.append("")
        out.append("---")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def check(built: dict) -> list[str]:
    """出す前の点検。作れなかった欄と、段が進まない形を名指しで返す。"""
    bad = []
    for i, s in enumerate(built["steps"], 1):
        if s["抜けたら出す問い"] == TODO:
            bad.append(f"【{i}】{s['title']}: 抜けたら出す問いが空（<!-- ask: … --> か "
                       f"「確認したいこと」に項目を足す）")
        if not s["検知キーワード"]:
            bad.append(f"【{i}】{s['title']}: 検知キーワードが空（段が自動で進まない）")
        else:
            miss = [k for k in s["検知キーワード"] if k not in s["言い方の例"]]
            if len(miss) == len(s["検知キーワード"]):
                bad.append(f"【{i}】{s['title']}: 検知キーワードが言い方の例に無い"
                           f"（読んでも段が進まない）: {'/'.join(miss)}")
        if not s["必須取得物"]:
            bad.append(f"【{i}】{s['title']}: 必須取得物が空（取り漏れの催促が出ない）")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(
        description="進行表1枚から agenda_steps.json と talk_script.md を作る")
    ap.add_argument("sheet", help="進行表の Markdown (Notion に貼るものと同じ1枚)")
    ap.add_argument("--out", default="", help="書き出し先ディレクトリ（会議フォルダ）")
    ap.add_argument("--total-min", type=float, default=0.0, help="会議の長さ(分)")
    ap.add_argument("--title", default="", help="会議の名前（省略時は進行表の1行目）")
    ap.add_argument("--check", action="store_true",
                    help="埋まらなかった欄があれば終了コード1で知らせる")
    ap.add_argument("--print", dest="show", action="store_true",
                    help="ファイルに書かず、標準出力へ台本だけ出す")
    a = ap.parse_args()

    src = pathlib.Path(a.sheet).expanduser()
    if not src.exists():
        print(f"[build_agenda] 進行表がありません: {src}", file=sys.stderr)
        return 2
    text = src.read_text(encoding="utf-8")
    title = a.title or next((h for h in (head_text(l) for l in text.splitlines())
                             if h), src.stem)
    built = build(text, a.total_min, title)

    script = to_talk_script(built, src.name)
    if a.show:
        print(script)
        return 0

    outdir = pathlib.Path(a.out).expanduser() if a.out else src.parent
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "agenda_steps.json").write_text(
        json.dumps(to_agenda_json(built, src.name), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (outdir / "talk_script.md").write_text(script, encoding="utf-8")

    n_ask = sum(len(s["必須取得物"]) for s in built["steps"])
    print(f"進行表: {src}")
    print(f"会議: {title} / {len(built['steps'])}段 / {built['total_min']:.0f}分 "
          f"/ 確認したいこと {n_ask}件")
    print(f"→ {outdir/'agenda_steps.json'}")
    print(f"→ {outdir/'talk_script.md'}")
    bad = check(built)
    if bad:
        print("\n埋まらなかったところ（手で足すか、進行表に注記を書く）:")
        for b in bad:
            print(f"  · {b}")
        if a.check:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
