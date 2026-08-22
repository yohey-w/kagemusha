"""
STT アダプタ層。

受信側 (receiver.py) は「音を投げると、確定/暫定テキストがコールバックで返る」
という 1 つの型しか知らない。どの STT サービスを使うかはここだけを差し替える。

    sess = make_session(backend, speaker, on_text, sample_rate)
    sess.feed(pcm16_bytes, capture_ts)   # 16bit LE mono
    sess.close()

on_text(text: str, is_final: bool, capture_ts: float, end_ts: float | None = None)
  capture_ts = その発話が「始まった録音時刻」(書き込み時刻ではない)。単位は time.monotonic()。
  2 チャンネルで STT の返る遅さが違うので、書き込み順で並べると時系列が壊れる。
  end_ts     = その発話が「終わった録音時刻」。合格条件の「数秒遅れ」は
               喋り終わってから画面に出るまでの時間なので、これが無いと測れない。
"""
from __future__ import annotations

import json
import math
import os
import queue
import struct
import threading
import time

import numpy as np

# queue.get がタイムアウトしたことを None (=終了合図) と区別するための番兵。
_EMPTY = object()

# ---------------------------------------------------------------- 基底


class SttSession:
    def __init__(self, speaker, on_text, sample_rate):
        self.speaker = speaker
        self.on_text = on_text
        self.sample_rate = sample_rate

    def feed(self, pcm16: bytes, capture_ts: float):
        raise NotImplementedError

    def close(self):
        pass


# ---------------------------------------------------------------- 共通 VAD


class _Vad:
    """RMS しきい値の素朴な VAD。発話の開始/終了だけ判る程度でよい。"""

    def __init__(self, sample_rate, threshold=0.012, hang_ms=700, min_ms=300):
        self.sr = sample_rate
        self.threshold = threshold
        self.hang = hang_ms / 1000.0
        self.min = min_ms / 1000.0
        self.active = False
        self.start_ts = 0.0
        self.last_voice = 0.0
        self.dur = 0.0

    def push(self, pcm16: bytes, capture_ts: float):
        """(event, start_ts, duration) を返す。event は None / 'start' / 'end'。"""
        a = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
        if a.size == 0:
            return None, 0.0, 0.0
        rms = float(np.sqrt(np.mean(a * a)))
        span = a.size / self.sr
        end_ts = capture_ts + span
        voiced = rms >= self.threshold
        ev = None
        if voiced:
            if not self.active:
                self.active = True
                self.start_ts = capture_ts
                self.dur = 0.0
                ev = "start"
            self.last_voice = end_ts
        if self.active:
            self.dur = end_ts - self.start_ts
            if not voiced and (end_ts - self.last_voice) >= self.hang:
                self.active = False
                d = self.last_voice - self.start_ts
                if d >= self.min:
                    return "end", self.start_ts, d
                return None, 0.0, 0.0
        return ev, self.start_ts, self.dur


# ---------------------------------------------------------------- stub


class StubSession(SttSession):
    """
    API キー無しで配管全体を検証するためのダミー。
    実際に喋った区間を VAD で拾い、テキストの代わりに秒数を書く。
    話者ラベル・時刻・遅延・jsonl 形式は本番と完全に同じ経路を通る。
    """

    def __init__(self, speaker, on_text, sample_rate, **kw):
        super().__init__(speaker, on_text, sample_rate)
        self.vad = _Vad(sample_rate, threshold=float(kw.get("vad_threshold", 0.012)))

    def feed(self, pcm16: bytes, capture_ts: float):
        ev, start_ts, dur = self.vad.push(pcm16, capture_ts)
        if ev == "start":
            self.on_text("(発話中…)", False, start_ts)
        elif ev == "end":
            self.on_text(f"[STUB] {self.speaker} の発話 {dur:.1f}秒", True, start_ts, start_ts + dur)


# ---------------------------------------------------------------- OpenAI Realtime


class OpenAIRealtimeSession(SttSession):
    """
    OpenAI Realtime API の transcription セッション (WebSocket)。GA 仕様 (2026-07-28 世代)。

    - 既定モデル gpt-live-transcribe (ライブ用・$0.017/分)
    - 音声は PCM16 24kHz mono を base64 で input_audio_buffer.append
    - OpenAI-Beta ヘッダは付けない (beta は 2026-05-12 に停止済み)
    - 公式が「発話ターン間で completed の順序は保証しない・item_id で突合せよ」と
      明記しているので、item_id -> 発話開始時刻 の対応表を持つ
    """

    BASE = "wss://api.openai.com/v1/realtime"

    def __init__(self, speaker, on_text, sample_rate, **kw):
        super().__init__(speaker, on_text, sample_rate)
        self.model = kw.get("model") or "gpt-live-transcribe"
        self.language = kw.get("language", "ja")
        self.prompt = kw.get("prompt") or ""
        self.keywords = kw.get("keywords") or []
        self.delay = kw.get("delay", "low")
        self.api_key = kw.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        self.q: queue.Queue = queue.Queue(maxsize=200)
        self._lock = threading.Lock()
        self._base_ts = None       # 最初に送ったチャンクの録音時刻
        self._sent_sec = 0.0       # これまで送った音声の総秒数
        self._item_ts: dict = {}   # item_id -> 発話開始の録音時刻
        self._fifo: list = []      # item_id が無いイベント用の予備
        self._last_end = None      # 直近の発話終了の録音時刻
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def feed(self, pcm16: bytes, capture_ts: float):
        try:
            self.q.put_nowait((pcm16, capture_ts))
        except queue.Full:
            pass  # 詰まったら捨てる (リアルタイム優先)

    def close(self):
        self._stop.set()
        try:
            self.q.put_nowait(None)
        except queue.Full:
            pass

    # --- 発話の「録音時刻」の解決 ---
    def _mark_start(self, ev):
        """speech_started で発話開始の録音時刻を確定させる。"""
        with self._lock:
            base = self._base_ts if self._base_ts is not None else time.monotonic()
            ms = ev.get("audio_start_ms")
            ts = base + (ms / 1000.0) if ms is not None else base + self._sent_sec
            item = ev.get("item_id")
            if item:
                self._item_ts[item] = ts
            else:
                self._fifo.append(ts)

    def _ts_for(self, ev, pop):
        with self._lock:
            item = ev.get("item_id")
            if item and item in self._item_ts:
                return self._item_ts.pop(item) if pop else self._item_ts[item]
            if self._fifo:
                return self._fifo.pop(0) if pop else self._fifo[0]
            base = self._base_ts if self._base_ts is not None else time.monotonic()
            return base + self._sent_sec

    def _run(self):
        # 会議の途中で WebSocket が切れても、黙って片チャンネルが死なないように
        # 繋ぎ直す。切れっぱなしだと残り40分ぶんの相手の声が丸ごと落ちる。
        import asyncio

        backoff = 1
        while not self._stop.is_set():
            try:
                asyncio.run(self._amain())
                if self._stop.is_set():
                    return
                self.on_text("[STT切断: 繋ぎ直す]", True, time.monotonic())
            except Exception as exc:  # noqa: BLE001
                if self._stop.is_set():
                    return
                self.on_text(
                    f"[STT接続エラー: {type(exc).__name__}: {exc} -- {backoff}秒後に再接続]",
                    True,
                    time.monotonic(),
                )
            time.sleep(backoff)
            backoff = min(15, backoff * 2)

    async def _amain(self):
        import asyncio
        import base64

        import websockets

        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.BASE}?model={self.model}"
        transcription = {"model": self.model, "languages": [self.language], "delay": self.delay}
        if self.prompt:
            transcription["prompt"] = self.prompt
        if self.keywords:
            transcription["keywords"] = list(self.keywords)

        async with websockets.connect(
            url, additional_headers=headers, max_size=None, ping_interval=20
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "transcription",
                            "audio": {
                                "input": {
                                    "format": {"type": "audio/pcm", "rate": self.sample_rate},
                                    "transcription": transcription,
                                    "turn_detection": {
                                        "type": "server_vad",
                                        "threshold": 0.5,
                                        "prefix_padding_ms": 300,
                                        "silence_duration_ms": 600,
                                    },
                                }
                            },
                        },
                    }
                )
            )

            async def send_loop():
                loop = asyncio.get_running_loop()
                while not self._stop.is_set():
                    item = await loop.run_in_executor(None, self.q.get)
                    if item is None:
                        break
                    pcm, ts = item
                    with self._lock:
                        if self._base_ts is None:
                            self._base_ts = ts
                        self._sent_sec += len(pcm) / 2 / self.sample_rate
                    await ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": base64.b64encode(pcm).decode(),
                            }
                        )
                    )

            async def recv_loop():
                async for raw in ws:
                    ev = json.loads(raw)
                    t = ev.get("type", "")
                    if t == "input_audio_buffer.speech_started":
                        self._mark_start(ev)
                    elif t == "input_audio_buffer.speech_stopped":
                        with self._lock:
                            base = self._base_ts if self._base_ts is not None else time.monotonic()
                            ms = ev.get("audio_end_ms")
                            self._last_end = (
                                base + ms / 1000.0 if ms is not None else base + self._sent_sec
                            )
                    elif t.endswith("input_audio_transcription.delta"):
                        d = ev.get("delta", "")
                        if d:
                            self.on_text(d, False, self._ts_for(ev, False))
                    elif t.endswith("input_audio_transcription.completed"):
                        txt = (ev.get("transcript") or "").strip()
                        if txt:
                            self.on_text(txt, True, self._ts_for(ev, True), self._last_end)
                    elif t == "error":
                        self.on_text(
                            f"[STTエラー: {json.dumps(ev.get('error', {}), ensure_ascii=False)}]",
                            True,
                            time.monotonic(),
                        )

            await asyncio.gather(send_loop(), recv_loop())


# ---------------------------------------------------------------- Deepgram


class DeepgramSession(SttSession):
    """Deepgram の live streaming (WebSocket)。"""

    def __init__(self, speaker, on_text, sample_rate, **kw):
        super().__init__(speaker, on_text, sample_rate)
        self.model = kw.get("model") or "nova-3"
        self.language = kw.get("language", "ja")
        # 案件用語のブースト。nova-3 は keyterm、それ以前は keywords:boost。
        self.keyterms = list(kw.get("keywords") or [])
        self.api_key = kw.get("api_key") or os.environ.get("DEEPGRAM_API_KEY", "")
        self.q: queue.Queue = queue.Queue(maxsize=200)
        self._stop = threading.Event()
        self._t0: dict = {}
        self._base_ts = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def feed(self, pcm16: bytes, capture_ts: float):
        if self._base_ts is None:
            self._base_ts = capture_ts
        try:
            self.q.put_nowait(pcm16)
        except queue.Full:
            pass

    def close(self):
        self._stop.set()
        try:
            self.q.put_nowait(None)
        except queue.Full:
            pass

    def _run(self):
        # 会議の途中で WebSocket が切れても、黙って片チャンネルが死なないように
        # 繋ぎ直す。切れっぱなしだと残り40分ぶんの相手の声が丸ごと落ちる。
        import asyncio

        backoff = 1
        while not self._stop.is_set():
            started = time.monotonic()
            err = None
            try:
                asyncio.run(self._amain())
                if self._stop.is_set():
                    return
            except Exception as exc:  # noqa: BLE001
                if self._stop.is_set():
                    return
                err = exc
            # 一度でも 30 秒以上つながっていたなら「壊れっぱなし」ではないので待ち時間を戻す。
            # これが無いと切断のたびに 1→2→4→8→15 と伸びて 15 秒に張り付き、
            # 会議の後半ほど相手の声が長く欠ける (実会議で 1011 が連発したときの実害)。
            if time.monotonic() - started >= 30:
                backoff = 1
            if err is None:
                self.on_text("[STT切断: 繋ぎ直す]", True, time.monotonic())
            else:
                self.on_text(
                    f"[STT接続エラー: {type(err).__name__}: {err} -- {backoff}秒後に再接続]",
                    True,
                    time.monotonic(),
                )
            time.sleep(backoff)
            backoff = min(15, backoff * 2)

    async def _amain(self):
        import asyncio
        import urllib.parse

        import websockets

        params = {
            "model": self.model,
            "language": self.language,
            "encoding": "linear16",
            "sample_rate": str(self.sample_rate),
            "channels": "1",
            "interim_results": "true",
            "punctuate": "true",
            "endpointing": "500",
        }
        if self.keyterms:
            if self.model.startswith("nova-3"):
                params["keyterm"] = self.keyterms
            else:
                params["keywords"] = [f"{k}:2" for k in self.keyterms]
        url = "wss://api.deepgram.com/v1/listen?" + urllib.parse.urlencode(
            params, doseq=True
        )
        async with websockets.connect(
            url, additional_headers={"Authorization": f"Token {self.api_key}"}, max_size=None
        ) as ws:

            async def send_loop():
                # 5 秒たっても送る音が無いときは KeepAlive を投げる。
                # Deepgram は一定時間 1 バイトも来ないと 1011 でこちらを切る
                # (dpgr.am/net0001)。子機が無音で止まっている間に切られると、
                # 相手側チャンネルだけが丸ごと落ちる (1回の会議で 5 回発生した)。
                loop = asyncio.get_running_loop()

                def _get():
                    try:
                        return self.q.get(timeout=5)
                    except queue.Empty:
                        return _EMPTY

                while not self._stop.is_set():
                    chunk = await loop.run_in_executor(None, _get)
                    if chunk is _EMPTY:
                        await ws.send(json.dumps({"type": "KeepAlive"}))
                        continue
                    if chunk is None:
                        break
                    await ws.send(chunk)
                await ws.send(json.dumps({"type": "CloseStream"}))

            async def recv_loop():
                async for raw in ws:
                    ev = json.loads(raw)
                    if ev.get("type") != "Results":
                        continue
                    alts = ev.get("channel", {}).get("alternatives", [])
                    if not alts:
                        continue
                    txt = (alts[0].get("transcript") or "").strip()
                    if not txt:
                        continue
                    base = self._base_ts or time.monotonic()
                    ts = base + float(ev.get("start", 0.0))
                    end = ts + float(ev.get("duration", 0.0))
                    self.on_text(txt, bool(ev.get("is_final")), ts, end)

            await asyncio.gather(send_loop(), recv_loop())


# ---------------------------------------------------------------- factory

BACKENDS = {
    "stub": StubSession,
    "openai": OpenAIRealtimeSession,
    "deepgram": DeepgramSession,
}


def make_session(backend, speaker, on_text, sample_rate, **kw) -> SttSession:
    if backend not in BACKENDS:
        raise SystemExit(f"unknown stt backend: {backend} (choices: {', '.join(BACKENDS)})")
    return BACKENDS[backend](speaker, on_text, sample_rate, **kw)
