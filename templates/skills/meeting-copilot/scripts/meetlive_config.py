#!/usr/bin/env python3
"""meetlive — 置き場と設定の解決を1箇所に集める。

**この道具の安全規律**: 環境変数が未設定のとき、この機体のどこかにある実在の案件データへ
静かに落ちてはならない。未設定時の既定は次の2つしか無い。

  - 状態ディレクトリ … カレントディレクトリ配下の ``./meetlive_state``
                       (絶対パスの既定を持たない。案件ごとに必ず別のディレクトリを渡す)
  - 入力ファイル     … このスキル同梱の ``config/*.example`` (中身は架空の例)

環境変数で指し示したファイルが存在しない場合は、黙って例へ落ちずに ``SystemExit`` で止まる。
「動いているように見えて、実は前の案件の台帳を読んでいた」を構造的に起こさないための作り。

環境変数の一覧は SKILL.md の「環境変数リファレンス」を正とする。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CONFIG_DIR = HERE.parent / "config"

# ---------------------------------------------------------------- 置き場


def state_dir(create: bool = True) -> pathlib.Path:
    """会議1回ぶんの状態(逐語・カード・ログ)の置き場。

    案件をまたいで同じディレクトリを使うと、過去の逐語が段の判定に混ざって
    「前の会議の発話で段が進む」事故が起きる。会議ごと・案件ごとに必ず分けること。
    """
    p = pathlib.Path(os.environ.get("MEETLIVE_DIR") or (pathlib.Path.cwd() / "meetlive_state"))
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def input_path(env_name: str, example_name: str, *, required: bool = False) -> pathlib.Path:
    """入力ファイルの解決。env が指す先が無ければ止まる。env 未設定なら同梱の例。

    required=True の入力について env が未設定のときは、例を使ったことを stderr に大きく残す
    (本番の会議で例のまま走っているのに気づかない、を防ぐ)。
    """
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
            f"[meetlive] ⚠ {env_name} が未設定です。同梱の例 {p.name} を読みます"
            f"（架空の内容です。本番の会議では必ず {env_name} を設定してください）",
            file=sys.stderr,
            flush=True,
        )
    return p


# ---------------------------------------------------------------- 呼びかけ・役割


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    out = tuple(x.strip() for x in raw.split(",") if x.strip())
    return out or default


def call_words() -> tuple[str, ...]:
    """進行役がモニタを呼ぶ合図。

    STT の誤変換に負けるので、実際の会議で聞き取られた**言い間違い・誤変換の綴りも
    そのまま並べる**こと(例: 「秘書」が「披書」になる、等)。ここが薄いと呼んでも反応しない。
    """
    return _csv_env("MEETLIVE_CALL_WORDS", ("コパイロット", "こぱいろっと", "秘書", "ひしょ"))


def counterpart() -> str:
    """相手の呼び方(プロンプトの中で使う)。例: 「〇〇さん」。"""
    return os.environ.get("MEETLIVE_COUNTERPART", "相手")


def host_label() -> str:
    """こちら側の話し手の呼び方(プロンプトの中で使う)。"""
    return os.environ.get("MEETLIVE_HOST_LABEL", "進行役")


def mode_words() -> tuple[str, str, tuple[str, ...]]:
    """同席の開始/終了の合図と、その誤変換の別綴り。

    開始合図は STT に化けることがある(実測あり)。化けた綴りを
    MEETLIVE_START_HOMOPHONES に足すと、その綴りでも開始として扱う。
    """
    start = os.environ.get("MEETLIVE_MODE_START_WORD", "同席開始")
    end = os.environ.get("MEETLIVE_MODE_END_WORD", "同席終了")
    homophones = _csv_env("MEETLIVE_START_HOMOPHONES", ())
    return start, end, homophones


# ---------------------------------------------------------------- モデル


def model(kind: str) -> tuple[str, str, str, str]:
    """(既定モデル, 既定effort, フォールバックモデル, フォールバックeffort)。

    kind="premise" … 発話ごとに毎回叩く**量産呼び出し**。安いモデルを既定に置く。
    kind="answer"  … 台本外の質問にだけ叩く**一発呼び出し**。上位モデルを置いてよい。
    """
    if kind == "premise":
        return (
            os.environ.get("MEETLIVE_MODEL_PREMISE", "claude-sonnet-5"),
            os.environ.get("MEETLIVE_EFFORT_PREMISE", "medium"),
            os.environ.get("MEETLIVE_MODEL_PREMISE_FALLBACK", "claude-opus-5"),
            os.environ.get("MEETLIVE_EFFORT_PREMISE_FALLBACK", "medium"),
        )
    return (
        os.environ.get("MEETLIVE_MODEL_ANSWER", "claude-opus-5"),
        os.environ.get("MEETLIVE_EFFORT_ANSWER", "low"),
        os.environ.get("MEETLIVE_MODEL_ANSWER_FALLBACK", "claude-sonnet-5"),
        os.environ.get("MEETLIVE_EFFORT_ANSWER_FALLBACK", "low"),
    )


# ---------------------------------------------------------------- JSON設定


def _load_json(path: pathlib.Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"[meetlive] {path} を読めません: {e!r}")
    if not isinstance(raw, dict):
        raise SystemExit(f"[meetlive] {path} の中身がオブジェクトではありません")
    return raw


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
    """資源表に書かれた画像パスを解決する。相対パスは config/ からの相対とみなす。"""
    if not entry_img:
        return None
    p = pathlib.Path(entry_img).expanduser()
    if not p.is_absolute():
        p = (CONFIG_DIR / p).resolve()
    return p
