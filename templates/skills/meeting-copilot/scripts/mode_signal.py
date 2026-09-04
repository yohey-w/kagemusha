#!/usr/bin/env python3
"""meetlive 「同席開始」合図のあいまい判定 — 書く側と読む側で共有する1本。

開始の合図は音声認識で別の語に化ける。実測(逐語から採取・日本語の例):
  「同席開始」→「透析開始。」「秘書開始。」「秘書開始してほしいな。」

この判定は、かつて **番人(copilot.py) と表示(viewer2.py) にそれぞれ独立にコピペ**
されていた。書く側(receiver.py)だけが完全一致でしか検知しておらず、その非対称のせいで
実際の会議で画面が自動で切り替わらなかった(手で切り替える実害)。
⇒ ここへ1本化し、**receiver.py(書く側)と viewer2.py(読む側)の両方から呼ぶ**。
   テスト(tests/test_mode_signal.py)が「書く側と読む側が同じ入力集合を受理する」ことを
   毎回確かめる。判定を増やすときは、必ずこのファイルを直すこと。

--- 拾う条件（狭く保つ） ---
開始の主手段は**ボタン**(viewer2 の /mode/start)。音声の吸収は従(バックアップ)なので、
拾いすぎない側に倒してある:

  1. 開始語そのもの(既定「同席開始」)を含む            → 合図
  2. アンカー語(「開始」「スタート」)を含み、かつ
     呼びかけ語 / 化けた綴り / 開始語の語幹 を含む     → 合図
  3. それ以外は拾わない

アンカー語を必須にしているのは、ふつうの会話で「同席」「同時」を言うだけで誤爆するため
(実測: 「うちのAIを同席させてまして」「同時に一つの入力で三つできる」)。
化けた綴りは想像で足さない。**実際に化けたものだけ**を
meeting.json の ``start_homophones`` / ``MEETLIVE_START_HOMOPHONES`` に足す。
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import meetlive_config as cfgmod  # noqa: E402

# 「これから始める」を表す語。日本語以外で使うときはここを差し替える。
ANCHOR_WORDS = ("開始", "スタート")


def _stem(start_word: str) -> tuple[str, ...]:
    """開始語からアンカー語を取り除いた語幹。「同席開始」→「同席」。

    語幹だけでは合図にしない(アンカー語との組でのみ効く)。2文字未満は雑音なので捨てる。
    """
    out = []
    for a in ANCHOR_WORDS:
        if start_word.endswith(a):
            s = start_word[: -len(a)].strip()
            if len(s) >= 2:
                out.append(s)
    return tuple(out)


def vocabulary(call_words=None, start_word=None, homophones=None) -> tuple[str, tuple[str, ...]]:
    """(開始語, あいまい判定に使う語の集合)。未指定のものは設定から取る。

    書く側と読む側が**同じ語彙**で判定するための唯一の入口。
    """
    if start_word is None or call_words is None or homophones is None:
        cw = cfgmod.call_words()
        sw, _end, hp = cfgmod.mode_words()
        call_words = cw if call_words is None else call_words
        start_word = sw if start_word is None else start_word
        homophones = hp if homophones is None else homophones
    fuzzy = tuple(w for w in tuple(call_words) + tuple(homophones) + _stem(start_word) if w)
    return start_word, fuzzy


def is_start_signal(text: str, *, call_words=None, start_word=None, homophones=None) -> bool:
    """発話1本が「同席開始」の合図(完全一致 or 実測済みの聞き取り揺れ)かどうか。

    開始語そのものもこの条件を満たすので、呼び出し側で別に完全一致判定を持つ必要は無い
    ── ただし receiver.py は「完全一致は常時発火・あいまい判定は開始前の1回きり」という
    非対称なガードを**呼び出し側で**行っている(誤爆したときの被害が違うため)。
    詳細は receiver.py の呼び出し箇所のコメントを見ること。
    """
    if not text:
        return False
    sw, fuzzy = vocabulary(call_words, start_word, homophones)
    if sw and sw in text:
        return True
    if not any(a in text for a in ANCHOR_WORDS):
        return False
    return any(w in text for w in fuzzy)
