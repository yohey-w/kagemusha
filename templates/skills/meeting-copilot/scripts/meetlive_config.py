#!/usr/bin/env python3
"""meetlive — 置き場と設定の解決を1箇所に集める。

**この道具の安全規律**: 環境変数が未設定のとき、この機体のどこかにある実在の案件データへ
静かに落ちてはならない。未設定時の既定は次の2つしか無い。

  - 状態ディレクトリ … カレントディレクトリ配下の ``./meetlive_state``
                       (絶対パスの既定を持たない。案件ごとに必ず別のディレクトリを渡す)
  - 入力ファイル     … このスキル同梱の ``config/*.example`` (中身は架空の例)

環境変数で指し示したファイルが存在しない場合は、黙って例へ落ちずに ``SystemExit`` で止まる。
「動いているように見えて、実は前の案件の台帳を読んでいた」を構造的に起こさないための作り。

--- 会議フォルダ (MEETLIVE_MEETING) ---
案件固有のものは**会議フォルダ1つ**に集める。``MEETLIVE_MEETING=<会議フォルダ>`` を
1つ渡せば、その中のファイルが全部の入力になる:

    <meeting>/
      meeting.json            構え(題・開始時刻・呼び方・レイアウト・舞台セット…)
      agenda_steps.json       段と必須取得物
      talk_script.md          台本
      phrasebook.json         定型文言
      stage_resources.json    舞台に出せるもの
      ledger.yaml             事実台帳(前提監視・任意)
      bank.json               先読み回答(任意)
      kb/                     返し役の材料
      docs/                   資料棚(会議中に開く手元資料)

解決順は **会議フォルダ → 個別env(後方互換) → 同梱の例**。
古い個別env が前の案件のまま残っていても、会議フォルダが勝つので事故らない。
**秘密(合言葉・管理画面のログイン)は会議フォルダに置かない** —
``MEETLIVE_CREDS_FILE`` で会議フォルダの外を指す(git に載る場所へ置かないため)。

環境変数の一覧は SKILL.md の「環境変数リファレンス」を正とする。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CONFIG_DIR = HERE.parent / "config"

# 会議フォルダの中のファイル名は「同梱の例から .example を抜いた名前」と決めてある。
#   agenda_steps.example.json -> agenda_steps.json / ledger.yaml.example -> ledger.yaml
MEETING_JSON = "meeting.json"

# meeting.json の既定値。ここに無いキーは meeting.json に書いても素通しで持ち回る
# (班ごとの拡張を config 側の改修なしで通すため)。
MEETING_DEFAULTS: dict = {
    "title": "",
    "start": "",                 # "HH:MM" (その日の時刻として解釈する)
    "total_min": 0,              # 0 なら段取りJSONの「会議分」を使う
    "host_label": "",            # 空なら MEETLIVE_HOST_LABEL / 既定「進行役」
    "counterpart": "",           # 空なら MEETLIVE_COUNTERPART / 既定「相手」
    "share": "host",             # "host" | "guest" | "none" (画面共有の構え)
    "layout": "auto",            # "columns" | "rows" | "auto"
    "features": {"copilot": True, "responder": True,
                 "premise_watch": True, "stage": True},
    "stage": {"set_label": "", "order": []},
    "card_policy": {"auto_dismiss_kinds": ["warn", "premise_warn"]},
    "call_words": [],
    "start_homophones": [],
    "creds_label": "",           # 鍵パネルのボタン名(既定は「🔑 合言葉」)
}


# ---------------------------------------------------------------- 置き場


def meeting_dir() -> pathlib.Path | None:
    """会議フォルダ。未設定なら None。指した先が無ければ止まる(例へ落ちない)。"""
    raw = os.environ.get("MEETLIVE_MEETING")
    if not raw:
        return None
    p = pathlib.Path(raw).expanduser()
    if not p.is_dir():
        raise SystemExit(
            f"[meetlive] MEETLIVE_MEETING={raw} が(ディレクトリとして)見つかりません。\n"
            f"           会議フォルダを指すか、変数を外して個別の MEETLIVE_* / 同梱の例で試してください。"
        )
    return p


def state_dir(create: bool = True) -> pathlib.Path:
    """会議1回ぶんの状態(逐語・カード・ログ)の置き場。

    案件をまたいで同じディレクトリを使うと、過去の逐語が段の判定に混ざって
    「前の会議の発話で段が進む」事故が起きる。会議ごと・案件ごとに必ず分けること。
    MEETLIVE_MEETING があるときの既定は ``./meetlive_state/<会議フォルダ名>``
    (会議フォルダを変えれば状態も自動で分かれる)。
    """
    raw = os.environ.get("MEETLIVE_DIR")
    if raw:
        p = pathlib.Path(raw).expanduser()
    else:
        md = meeting_dir()
        base = pathlib.Path.cwd() / "meetlive_state"
        p = (base / md.name) if md is not None else base
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def meeting_file(name: str) -> pathlib.Path | None:
    """会議フォルダ直下の1ファイル。無ければ None (env や例へ落ちる)。"""
    md = meeting_dir()
    if md is None:
        return None
    p = md / name
    return p if p.exists() else None


def input_path(env_name: str, example_name: str, *, required: bool = False) -> pathlib.Path:
    """入力ファイルの解決。**会議フォルダ → 個別env → 同梱の例** の順。

    env が指す先が無ければ止まる(例へ静かに落ちない)。required=True の入力について
    どこにも実物が無く例を使ったときは、stderr に大きく残す
    (本番の会議で例のまま走っているのに気づかない、を防ぐ)。
    """
    p = meeting_file(example_name.replace(".example", "", 1))
    if p is not None:
        return p
    raw = os.environ.get(env_name)
    if raw:
        p = pathlib.Path(raw).expanduser()
        if not p.exists():
            raise SystemExit(
                f"[meetlive] {env_name}={raw} が見つかりません。\n"
                f"           案件のファイルを指すか、環境変数を外して同梱の例"
                f" ({CONFIG_DIR / example_name}) で試してください。"
            )
        return p
    p = CONFIG_DIR / example_name
    if not p.exists():
        raise SystemExit(f"[meetlive] 同梱の例が見つかりません: {p}")
    if required:
        print(
            f"[meetlive] ⚠ {env_name} も MEETLIVE_MEETING も未設定です。同梱の例 {p.name} を読みます"
            f"（架空の内容です。本番の会議では必ず会議フォルダを渡してください）",
            file=sys.stderr,
            flush=True,
        )
    return p


def docs_dir() -> pathlib.Path | None:
    """資料棚。会議フォルダがあれば ``<meeting>/docs``、無ければ ``<state>/docs``。

    「ここに置いたものが会議中にボタンで開ける」だけの棚。中身の用意は運用側の仕事。
    """
    raw = os.environ.get("MEETLIVE_DOCS")
    if raw:
        return pathlib.Path(raw).expanduser()
    md = meeting_dir()
    if md is not None:
        return md / "docs"
    return state_dir(create=False) / "docs"


def creds_file() -> pathlib.Path | None:
    """合言葉(鍵パネル)の md。**会議フォルダには置かない** ので env だけで指す。"""
    raw = os.environ.get("MEETLIVE_CREDS_FILE")
    return pathlib.Path(raw).expanduser() if raw else None


def knowledge_dir() -> pathlib.Path:
    """接地資料(answerer/responder が逐語でLLMへ送る材料)の置き場。

    🔴 この直下に置いたものは**そのまま送られる**。案件フォルダを丸ごと指さないこと。
    """
    raw = os.environ.get("MEETLIVE_KNOWLEDGE_DIR")
    if raw:
        return pathlib.Path(raw).expanduser()
    md = meeting_dir()
    if md is not None and (md / "kb").is_dir():
        return md / "kb"
    return CONFIG_DIR


def knowledge_script_name() -> str:
    """接地資料のうち先頭に置く台本のファイル名。"""
    d = os.environ.get("MEETLIVE_SCRIPT_NAME")
    if d:
        return d
    return "talk_script.md" if meeting_dir() is not None else "talk_script.example.md"


def knowledge_limits() -> tuple[int, int]:
    """(1ファイルあたりの文字数上限, 合計の文字数上限)。0 は「切り詰めない」。"""
    return (_int_env("MEETLIVE_KNOWLEDGE_PER_FILE", 9000),
            _int_env("MEETLIVE_KNOWLEDGE_TOTAL", 40000))


def bank_path() -> pathlib.Path | None:
    """先読み回答バンク(任意)。無ければ None。"""
    raw = os.environ.get("MEETLIVE_BANK")
    if raw:
        p = pathlib.Path(raw).expanduser()
        if not p.exists():
            raise SystemExit(f"[meetlive] MEETLIVE_BANK={raw} が見つかりません。")
        return p
    return meeting_file("bank.json")


def heartbeat_path() -> pathlib.Path:
    """返し役/番人が「生きている」と書く心拍ファイル(状態Dir直下)。"""
    return state_dir(create=False) / "heartbeat.json"


def heartbeat_stale_sec() -> float:
    """これより古い心拍は「心拍なし」と表示する。"""
    return _float_env("MEETLIVE_HEARTBEAT_STALE_SEC", 60.0)


def token() -> str:
    """子機との合言葉(receiver)。"""
    return os.environ.get("MEETLIVE_TOKEN", "")


# ---------------------------------------------------------------- env の型


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    out = tuple(x.strip() for x in raw.split(",") if x.strip())
    return out or default


# ---------------------------------------------------------------- meeting.json


def _load_json(path: pathlib.Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"[meetlive] {path} を読めません: {e!r}")
    if not isinstance(raw, dict):
        raise SystemExit(f"[meetlive] {path} の中身がオブジェクトではありません")
    return raw


_MEETING_CACHE: dict = {}


def load_meeting(refresh: bool = False) -> dict:
    """``<meeting>/meeting.json`` を既定値の上に載せて返す。

    会議フォルダが無い / meeting.json が無い場合も、**既定値だけの辞書**を返す
    (呼ぶ側が毎回 None を気にしなくてよいように)。``_comment`` は落とす。
    """
    if _MEETING_CACHE and not refresh:
        return _MEETING_CACHE
    out = json.loads(json.dumps(MEETING_DEFAULTS))     # deep copy
    p = meeting_file(MEETING_JSON)
    if p is not None:
        raw = _load_json(p)
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
    _MEETING_CACHE.clear()
    _MEETING_CACHE.update(out)
    return out


def _meeting_str(key: str) -> str:
    v = load_meeting().get(key)
    return v.strip() if isinstance(v, str) else ""


def _meeting_list(key: str) -> tuple[str, ...]:
    v = load_meeting().get(key)
    if not isinstance(v, list):
        return ()
    return tuple(str(x).strip() for x in v if str(x).strip())


# ---------------------------------------------------------------- 呼びかけ・役割


def call_words() -> tuple[str, ...]:
    """進行役がモニタを呼ぶ合図。

    STT の誤変換に負けるので、実際の会議で聞き取られた**言い間違い・誤変換の綴りも
    そのまま並べる**こと(例: 「秘書」が「披書」になる、等)。ここが薄いと呼んでも反応しない。
    解決順は 会議フォルダ(meeting.json の call_words) → MEETLIVE_CALL_WORDS → 既定。
    """
    from_meeting = _meeting_list("call_words")
    if from_meeting:
        return from_meeting
    return _csv_env("MEETLIVE_CALL_WORDS", ("コパイロット", "こぱいろっと", "秘書", "ひしょ"))


def counterpart() -> str:
    """相手の呼び方(プロンプトの中で使う)。例: 「〇〇さん」。"""
    return _meeting_str("counterpart") or os.environ.get("MEETLIVE_COUNTERPART", "相手")


def host_label() -> str:
    """こちら側の話し手の呼び方(プロンプトの中で使う)。"""
    return _meeting_str("host_label") or os.environ.get("MEETLIVE_HOST_LABEL", "進行役")


def mode_words() -> tuple[str, str, tuple[str, ...]]:
    """同席の開始/終了の合図と、その誤変換の別綴り。

    開始合図は STT に化けることがある(実測あり)。化けた綴りを meeting.json の
    ``start_homophones`` / ``MEETLIVE_START_HOMOPHONES`` に足すと、その綴りでも
    開始として扱う。判定そのものは mode_signal.py が正本。
    """
    start = os.environ.get("MEETLIVE_MODE_START_WORD", "同席開始")
    end = os.environ.get("MEETLIVE_MODE_END_WORD", "同席終了")
    homophones = _meeting_list("start_homophones") or _csv_env("MEETLIVE_START_HOMOPHONES", ())
    return start, end, homophones


# ---------------------------------------------------------------- 画面の構え


def layout() -> str:
    """カンペ画面の並べ方。columns=左右2列 / rows=上下 / auto=画面の向きで切替。"""
    v = (_meeting_str("layout") or os.environ.get("MEETLIVE_LAYOUT") or "auto").lower()
    return v if v in ("columns", "rows", "auto") else "auto"


def card_policy() -> dict:
    """カードの消え方。既定は「警報だけ自動で消える・他は手で『済』を押すまで残る」。

    2026-09-04 の実機確認で決まった既定値をそのまま持つ
    (「アドバイスが一定時間で消えてしまう…人間が手動で消すのがいい」)。
    """
    raw = load_meeting().get("card_policy")
    raw = raw if isinstance(raw, dict) else {}
    kinds = raw.get("auto_dismiss_kinds")
    if not isinstance(kinds, list):
        kinds = list(MEETING_DEFAULTS["card_policy"]["auto_dismiss_kinds"])
    return {
        "auto_dismiss_kinds": tuple(str(k) for k in kinds if str(k).strip()),
        "ttl_sec": float(raw.get("ttl_sec", 120.0) or 120.0),
        "max_turns": int(raw.get("max_turns", 8) or 8),
        "min_show_sec": float(raw.get("min_show_sec", 40.0) or 40.0),
        "stack_max": int(raw.get("stack_max", 60) or 60),
        "history_max": int(raw.get("history_max", 30) or 30),
    }


def features() -> dict:
    """どの層を起動するか(run.sh が読む)。既定は全部 True。"""
    raw = load_meeting().get("features")
    out = dict(MEETING_DEFAULTS["features"])
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k)] = bool(v)
    return out


def stage_setinfo() -> dict:
    """今回の舞台セット(meeting.json の stage)。

    **優先順位はキー単位**: set_label / order は meeting.json(静的な構え)、
    個々の URL は走行中に外から書ける ``<state>/stage_urls.json`` が勝つ。
    """
    raw = load_meeting().get("stage")
    raw = raw if isinstance(raw, dict) else {}
    label = raw.get("set_label")
    label = label.strip()[:60] if isinstance(label, str) else ""
    order = raw.get("order")
    order = [str(x) for x in order if str(x).strip()] if isinstance(order, list) else []
    return {"label": label, "order": order}


def meeting_start_iso(default: str = "") -> str:
    """meeting.json の ``start`` ("HH:MM") を「今日の日付 + その時刻」に直す。

    ``--start`` を渡さずに起動したときの既定値。日付は起動した日。
    """
    hhmm = _meeting_str("start")
    if not hhmm:
        return default
    parts = hhmm.split(":")
    try:
        h, m = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return default
    from datetime import datetime
    return datetime.now().replace(hour=h, minute=m, second=0,
                                  microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def total_min(default: float = 0.0) -> float:
    try:
        return float(load_meeting().get("total_min") or default)
    except (TypeError, ValueError):
        return default


def creds_label() -> str:
    return _meeting_str("creds_label") or "🔑 合言葉"


# ---------------------------------------------------------------- 前提監視


def premise_ids() -> tuple[str, ...]:
    return _csv_env("MEETLIVE_PREMISE_IDS", ())


def premise_max() -> int:
    return _int_env("MEETLIVE_PREMISE_MAX", 16)


def premise_cooldown() -> float:
    return _float_env("MEETLIVE_PREMISE_COOLDOWN", 45.0)


# ---------------------------------------------------------------- モデル


# CLI ごとの既定モデル表。**モデルidはCLIをまたいで通用しない**ので、1つの
# キーに両方を詰め込まず、使う CLI の側だけを既定にする。
# MEETLIVE_MODEL_* を明示すればどちらの CLI でもそれが勝つ。
#
# codex の effort は**実測**で決めてある（gpt-5.6-sol・短いプロンプト1往復・
# 2026-09-06 このマシン）: low 8.8秒 / medium 7.3秒 / xhigh 17.3秒。
# premise は発話ごとに叩き、呼び出し側の制限が20秒なので xhigh は入らない
# ——ここだけ低くしてあるのは節約ではなく、**間に合わないと沈黙するから**。
_MODEL_DEFAULTS = {
    "claude": {
        "premise": ("claude-sonnet-5", "medium", "claude-opus-5", "medium"),
        "answer": ("claude-opus-5", "low", "claude-sonnet-5", "low"),
    },
    "codex": {
        "premise": ("gpt-5.6-sol", "low", "gpt-5.6-sol", "medium"),
        "answer": ("gpt-5.6-sol", "xhigh", "gpt-5.6-sol", "low"),
    },
}


def agent_cli_name() -> str:
    """いま使う CLI 名: "claude" | "codex"。

    ``MEETLIVE_AGENT_CLI`` を読むのはここ**だけ**（設定の解決は全部このファイル
    の仕事）。未指定なら ``agent_cli.which()`` に PATH から選ばせ、それも決めら
    れなければ従来どおり claude。
    """
    want = os.environ.get("MEETLIVE_AGENT_CLI", "").strip().lower()
    if want in ("claude", "codex"):
        return want
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import agent_cli  # noqa: PLC0415
        return agent_cli.which()
    except Exception:
        return "claude"


def model(kind: str) -> tuple[str, str, str, str]:
    """(既定モデル, 既定effort, フォールバックモデル, フォールバックeffort)。

    kind="premise" … 発話ごとに毎回叩く**量産呼び出し**。安いモデルを既定に置く。
    kind="answer"  … 台本外の質問にだけ叩く**一発呼び出し**。上位モデルを置いてよい。
    """
    d = _MODEL_DEFAULTS.get(agent_cli_name(), _MODEL_DEFAULTS["claude"])
    if kind == "premise":
        m1, e1, m2, e2 = d["premise"]
        return (
            os.environ.get("MEETLIVE_MODEL_PREMISE", m1),
            os.environ.get("MEETLIVE_EFFORT_PREMISE", e1),
            os.environ.get("MEETLIVE_MODEL_PREMISE_FALLBACK", m2),
            os.environ.get("MEETLIVE_EFFORT_PREMISE_FALLBACK", e2),
        )
    m1, e1, m2, e2 = d["answer"]
    return (
        os.environ.get("MEETLIVE_MODEL_ANSWER", m1),
        os.environ.get("MEETLIVE_EFFORT_ANSWER", e1),
        os.environ.get("MEETLIVE_MODEL_ANSWER_FALLBACK", m2),
        os.environ.get("MEETLIVE_EFFORT_ANSWER_FALLBACK", e2),
    )


# ---------------------------------------------------------------- JSON設定


def load_phrasebook() -> dict:
    """定型回答・約束の境界(金額/期限/責任)の警報文などの語彙集。"""
    return _load_json(input_path("MEETLIVE_PHRASEBOOK", "phrasebook.example.json"))


def load_stage() -> dict:
    """舞台(相手に見せる別窓)の資源表。URL・画像・音声での呼び出し語をここだけで持つ。

    戻り値: {"resources": [ {res,label,btn,url,img,match}, ... ],
             "auto": {段番号(1始まりの文字列): res}}
    """
    raw = _load_json(input_path("MEETLIVE_STAGE", "stage_resources.example.json"))
    res_list = []
    seen = set()
    for r in raw.get("resources") or []:
        if not isinstance(r, dict):
            continue
        key = str(r.get("res") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        res_list.append({
            "res": key,
            "label": str(r.get("label") or key),
            "btn": str(r.get("btn") or key),
            "url": str(r.get("url") or ""),
            "img": str(r.get("img") or ""),
            "match": str(r.get("match") or ""),
        })
    if not any(r["res"] == "blank" for r in res_list):
        # 「舞台を消す」は必ず要る(相手に見せっぱなしを止める手段)。
        res_list.insert(0, {"res": "blank", "label": "打合せ中", "btn": "消す",
                            "url": "/stage/blank", "img": "", "match": ""})
    auto = {}
    for k, v in (raw.get("auto") or {}).items():
        try:
            auto[int(k)] = str(v)
        except (TypeError, ValueError):
            continue
    return {"resources": res_list, "auto": auto}


def resolve_img(entry_img: str) -> pathlib.Path | None:
    """資源表に書かれた画像パスを解決する。相対パスは資源表と同じディレクトリからの相対。"""
    if not entry_img:
        return None
    p = pathlib.Path(entry_img).expanduser()
    if not p.is_absolute():
        base = meeting_dir() or CONFIG_DIR
        p = (base / p).resolve()
    return p
