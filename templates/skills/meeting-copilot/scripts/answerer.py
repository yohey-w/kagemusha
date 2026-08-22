#!/usr/bin/env python3
"""meetlive 同席役・第2層 — 台本外の質問に答える。

番人(copilot.py)がルールと文字列照合だけで「手元にない」と判断した呼び出しを、
接地資料(台本+関連資料)を材料に口語3行へ畳んで返す。LLM を1回だけ叩く。

規律:
  - 材料に無いことは言わない(「手元にない・持ち帰り」を返す)
  - 金額・期限・責任は答えない(そこは番人が警報を出す領域。約束の境界)
  - 出力から英語の内心(推論の生ログ)が漏れたら捨てて日本語だけ残す
  - 「手元にない」のときはカードを出さずログにだけ残す(画面を汚さない)
  - q(質問文)をカード自身に持たせる(表示側の質問欄が古い呼び出しで固まるのを防ぐ)

--- モデル選択の規律 ---
これは**台本外の質問にだけ叩く一発呼び出し**(既定で30秒に1回まで)。
前提監視(premise_watch.py)のような量産呼び出しではないので、上位モデルを置いてよい。
"""
import json, os, re, subprocess, sys, time, pathlib, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import meetlive_config as cfgmod  # noqa: E402

STATE = cfgmod.state_dir()
LOG = STATE / "answerer_log.jsonl"

# 接地資料の置き場。未設定なら同梱の config/(架空の例)。
_kd = os.environ.get("MEETLIVE_KNOWLEDGE_DIR")
if _kd:
    K = pathlib.Path(_kd).expanduser()
    if not K.is_dir():
        raise SystemExit(f"[answerer] MEETLIVE_KNOWLEDGE_DIR={_kd} がディレクトリではありません")
else:
    K = cfgmod.CONFIG_DIR
    print(f"[answerer] ⚠ MEETLIVE_KNOWLEDGE_DIR 未設定。同梱の例 {K} を材料にします",
          file=sys.stderr, flush=True)

SCRIPT_NAME = os.environ.get("MEETLIVE_SCRIPT_NAME", "talk_script.example.md")
# 材料の総量の上限(文字)。ここを大きくすると質は上がるが、レイテンシとクォータが伸びる。
PER_FILE = int(os.environ.get("MEETLIVE_KNOWLEDGE_PER_FILE", "9000"))
TOTAL = int(os.environ.get("MEETLIVE_KNOWLEDGE_TOTAL", "40000"))


def load(p, n):
    try:
        return p.read_text(encoding="utf-8")[:n]
    except Exception:
        return ""


def build_knowledge():
    """台本を先頭に、接地資料ディレクトリの .md/.txt を名前順で足す。

    1ファイル欠けても全体は落とさない(load() は無ければ空文字を返す)。
    「どの資料を入れるか」を案件ごとにコードへ書かない——ディレクトリに置く/置かないで決める。
    """
    parts, used = [], 0
    script = K / SCRIPT_NAME
    body = load(script, PER_FILE)
    if body:
        parts.append(f"# 台本({script.name})\n{body}")
        used += len(body)
    else:
        print(f"[answerer] ⚠ 台本が読めません: {script}", file=sys.stderr, flush=True)
    for p in sorted(K.glob("*")):
        if not p.is_file() or p.name == SCRIPT_NAME:
            continue
        if p.suffix.lower() not in (".md", ".txt"):
            continue
        if used >= TOTAL:
            break
        body = load(p, min(PER_FILE, TOTAL - used))
        if body:
            parts.append(f"# {p.name}\n{body}")
            used += len(body)
    return "\n\n".join(parts)


KNOWLEDGE = build_knowledge()

HOST = cfgmod.host_label()
CALL = cfgmod.call_words()[0] if cfgmod.call_words() else "モニタ"
SYSTEM = (
    f"あなたは会議の同席役。{HOST}が『{CALL}、〜』と呼んだ質問に、下の材料だけを根拠に口語で答える。"
    f"出力は2〜3行・各行短く・{HOST}がそのまま読み上げられる言い方。"
    "材料に無いことは書かず、その場合は1行目に『手元にない。持ち帰りで。』とだけ書く。"
    "金額・単価・追加費用・納期・期限・責任・保証については答えず"
    "『それは約束の外。見積もりますねで受ける。』と返す。前置き・敬語の装飾・箇条書き記号は不要。"
    "出力は必ず日本語のみ。英語・内心の説明(The transcript is... 等)・思考過程を一切書かない。"
    "日本語の口語3行以外は出力しない。"
)

# 英語が漏れた行を捨てる判定: ASCII アルファベットが連続4文字以上、
# または典型的な内心語 (The/This/Note/I will 等) を含む行は「内心漏れ」として破棄する。
_ASCII_RUN = re.compile(r"[A-Za-z]{4,}")
_ENGLISHY = re.compile(r"\b(The|This|I will|I need|Note:|Let me|question|transcript|fragment)\b", re.I)


def is_english_leak(line: str) -> bool:
    return bool(_ASCII_RUN.search(line) or _ENGLISHY.search(line))


def _run(prompt, model, effort, timeout):
    r = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--effort", effort],
        capture_output=True, text=True, timeout=timeout,
    )
    return (r.stdout or "").strip()


def answer(question, recent=""):
    prompt = (f"{SYSTEM}\n\n{KNOWLEDGE}\n\n# 直近の会話(文字起こし)\n{recent}\n\n"
              f"# 質問\n{question}\n\n# 回答(2〜3行・日本語のみ)")
    t0 = time.time()
    m1, e1, m2, e2 = cfgmod.model("answer")
    src = f"{m1}/{e1}"
    out = ""
    try:
        out = _run(prompt, m1, e1, 40)
    except subprocess.TimeoutExpired:
        out = ""
    except Exception:
        out = ""
    if not out:
        # フォールバック: 過負荷等で既定モデルが空を返したら別モデルで1回だけ撃ち直す
        try:
            out = _run(prompt, m2, e2, 30)
            src = f"{m2}/{e2}(fallback)"
        except Exception:
            out = ""

    raw_lines = [l.strip() for l in out.splitlines() if l.strip()]
    kept = [l for l in raw_lines if not is_english_leak(l)]
    dropped = len(raw_lines) - len(kept)
    lines = kept[:3] or ["手元にない。持ち帰りで。"]
    conf = "none" if lines[0].startswith("手元にない") else "high"

    rec = {
        "ts": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000"),
        "kind": "call", "lines": lines, "confidence": conf, "ttl": 60,
        "src": src, "latency_s": round(time.time() - t0, 1),
        "q": question[:60], "dropped_english_lines": dropped,
    }
    # ログには常に残す(「手元にない」も含め全件。何に答えたかが消えると後で検証できない)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass

    # 画面を汚さないため、中身の無い「手元にない」はカードを出さない(ログのみ)。
    if conf != "none":
        with open(STATE / "cards.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "テスト: いまの案はどれだっけ？"
    print(json.dumps(answer(q), ensure_ascii=False))
