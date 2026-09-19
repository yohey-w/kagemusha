#!/usr/bin/env python3
"""step_detect.py — 「いまどの段か」の判定を1本に束ねる述語。

番人(copilot.py)と画面(viewer2.py)は**それぞれ独立に**現在地を計算する。
同じ規則を2箇所に書いていたので、片方だけ直すとテレプロンプターとカードが
別の段を指す。ここに1本化して、両方から呼ぶ。

--- なぜ単純なキーワード一致では駄目だったか (2026-09-19 実走) ---
旧実装は「同席開始からの**こちら側の全発話を連結した文字列**」に段の検知
キーワードを当てていた。連結文字列は一方向にしか伸びないので、

  · 雑談の中でたまたま当たった1語で、段が4つ飛ぶ
  · 一度当たると以後ずっと当たり続ける(高水位が下がらないのではなく、
    そもそも「当たった瞬間」が分からない)

実測: 段の切替4回のうち、台本の文脈と関係のある切替は**0回**。
①→⑤(②③④を飛ばす)・⑤→⑦(⑥を飛ばす)はどちらも無関係な語の偶然一致だった。

--- ここでの規則 ---
段が進むのは「**こちら側が、相手の発話のあとに、ある程度の長さで話し始めた**
一発話の中に、その段の検知キーワードがあるとき」だけ。

  turn_open  … 直前の行が相手(または最初の発話)。話者交代＝話題の切り出し
  min_chars  … 相槌・言いさしの断片では段を動かさない

判定は**発話単位**で、当たった段番号の高水位(high water mark)を持つ。
連結文字列は使わない(必須取得物の検知は従来どおり両者の連結でよい。
あちらは「誰かの口から出たか」を見るだけで、順序の意味が無いため)。
"""
from __future__ import annotations

# 段を動かすのに必要な最小の発話長。実測の相槌(「はい」「うん、そうですね」)は
# ここで落ちる。長くしすぎると本物の切り出しまで落ちるので、控えめに置く。
MIN_CHARS = 8


def is_turn_open(prev_speaker: str | None, text: str, min_chars: int = MIN_CHARS) -> bool:
    """この発話は「段を切り出す話し始め」として扱ってよいか。

    prev_speaker … 直前の**発話**の話者 ("host"/"guest"/None=これが最初)
    """
    if len((text or "").strip()) < min_chars:
        return False
    return prev_speaker != "host"


def step_hit(step_kws, text: str, kw_hit) -> bool:
    """この一発話が、その段の検知キーワードに当たるか。"""
    return any(kw_hit(k, text) for k in (step_kws or []))


def advance(high: int, steps, speaker: str, prev_speaker: str | None, text: str,
            kw_hit, min_chars: int = MIN_CHARS) -> int:
    """一発話ぶん進めた高水位を返す。当たらなければ ``high`` をそのまま返す。

    steps … [{"kw": [...]}, ...] (copilot / viewer2 のどちらの形でも kw さえあればよい)
    kw_hit … 呼び出し側の照合関数 (正規表現として当てる実装を各自が持っている)
    """
    if speaker != "host":
        return high
    if not is_turn_open(prev_speaker, text, min_chars):
        return high
    for i, s in enumerate(steps):
        if i <= high:
            continue
        if step_hit(s.get("kw"), text, kw_hit):
            high = i
    return high


def scan(steps, records, kw_hit, min_chars: int = MIN_CHARS) -> int:
    """発話の並び(古い順)を一度に走査して高水位を出す。画面側(bulk)用。

    records … [{"speaker": ..., "text": ...}, ...]
    """
    high, prev = 0, None
    for r in records:
        text = r.get("text") or ""
        if not text:
            continue
        speaker = r.get("speaker") or "guest"
        high = advance(high, steps, speaker, prev, text, kw_hit, min_chars)
        prev = speaker
    return high
