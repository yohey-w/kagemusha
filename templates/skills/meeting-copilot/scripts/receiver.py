"""
meetlive 受信サーバ

音声取り込み子機 (別マシンの capture agent) から 48kHz mono int16 PCM を TCP で受け、
リサンプルして STT へ流し、逐語を transcript.jsonl へ追記する。

  transcript.jsonl : 確定発話のみ {"ts","speaker","text"}  ts は「喋った時刻」
  partial.json     : 各話者の暫定テキスト (表示用・毎回上書き)
  latency.jsonl    : 実測レイテンシ (喋り終わってから画面に出るまで)

--- 子機との線の仕様 (capture agent はこのスキルに同梱していない。自分で書くこと) ---
接続したら、まず挨拶を JSON 1行 + "\\n" で送る:
    {"ch":"T","rate":48000,"token":"合言葉"}
      ch    … "T" = こちら側のマイク / "G" = 相手側 (スピーカーのループバック)
      rate  … 送るサンプルレート。48000 か、子機側で落として 16000
      token … --token / MEETLIVE_TOKEN と一致しなければ切断
そのあとは無限に「ヘッダ + PCM」の繰り返し:
    ヘッダ = struct "<dI" = (子機の時刻: float64, これに続く PCM のバイト数: uint32)
    PCM    = 16bit little-endian mono
子機の時刻は参考値で、こちらは使わない (下記「時間の基準」を見よ)。

--- 時間の基準 ---
時間の基準は「受け取った音のサンプル数」。OS の時計は基準に使わない。
WSL2 上では実測で両方とも信用できなかった:
  - time.time()      … ホストへの再同期で巻き戻る (30秒の間に 2.5 秒戻った)
  - time.monotonic() … 実時間より約7%速い (ホストの QPC と 48kHz の音声クロックという
                        2つの独立した基準が一致し、WSL 側だけがずれていることを確認)
音声は 48kHz の水晶で刻まれるので、サンプル数だけが正しい時間を持っている。
壁時計は表示のためだけに、time.time() との差を強く平滑化して当てる。

--- 話者の分け方 ---
話者は API の話者分離に頼らず**物理チャンネル**で確定する:
  T = こちら側のマイク            -> speaker "host"
  G = 相手側 (スピーカーのループバック) -> speaker "guest"
⚠ そのため **イヤホン/イヤモニは必須**。相手の声がスピーカーから出ると自分のマイクに
   回り込み、相手の発話が "host" として記録されて、段の進行判定も前提監視も壊れる。
   どうしてもスピーカーを使うときの保険が --xtalk-gate だが、あくまで保険。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import socketserver
import struct
import sys
import threading
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import meetlive_config as cfgmod  # noqa: E402
import stt as stt_mod  # noqa: E402

SRC_SR = 48000
HDR = struct.Struct("<dI")
CH_SPEAKER = {"T": "host", "G": "guest"}


# ---------------------------------------------------------------- リサンプラ


class Resampler:
    """48kHz -> target。整数分の1のときだけ使う (48000/16000=3, /24000=2)。"""

    def __init__(self, src, dst):
        if src % dst:
            raise SystemExit(f"resample {src}->{dst} は整数比ではない")
        self.factor = src // dst
        n = 64 * self.factor + 1
        cutoff = 0.5 / self.factor
        m = np.arange(n) - (n - 1) / 2
        h = 2 * cutoff * np.sinc(2 * cutoff * m) * np.hanning(n)
        self.h = (h / h.sum()).astype(np.float32)
        self.tail = np.zeros(n - 1, dtype=np.float32)
        self.phase = 0

    def __call__(self, pcm16: bytes) -> bytes:
        x = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
        if x.size == 0:
            return b""
        buf = np.concatenate([self.tail, x])
        y = np.convolve(buf, self.h, mode="valid")
        self.tail = buf[-(self.h.size - 1):]
        idx = np.arange(self.phase, y.size, self.factor)
        self.phase = (self.phase - y.size) % self.factor if y.size else self.phase
        out = np.clip(y[idx], -1.0, 1.0)
        return (out * 32767.0).astype("<i2").tobytes()


# ---------------------------------------------------------------- 書き出し


class Writer:
    def __init__(self, outdir: pathlib.Path, quiet=False):
        outdir.mkdir(parents=True, exist_ok=True)
        self.transcript = outdir / "transcript.jsonl"
        self.latency = outdir / "latency.jsonl"
        self.partial_path = outdir / "partial.json"
        self.partial = {}
        self.lock = threading.Lock()
        self.quiet = quiet
        self.stats = {"host": [], "guest": []}
        # 音声時間 -> 壁時計 のずれ。time.time() は飛ぶので強く平滑化して使う。
        self._off = None
        # 会議中プロトコル: 呼びかけ語と同席の開始/終了の合図
        self.call_words = cfgmod.call_words()
        self.mode_start, self.mode_end, _homophones = cfgmod.mode_words()

    def sync_wall(self, audio_now):
        off = time.time() - audio_now
        self._off = off if self._off is None else self._off * 0.98 + off * 0.02

    def _wall(self, audio_ts):
        return audio_ts + (self._off if self._off is not None else 0.0)

    def _iso(self, audio_ts):
        ts = self._wall(audio_ts)
        lt = time.localtime(ts)
        return time.strftime("%Y-%m-%dT%H:%M:%S", lt) + f".{int(ts % 1 * 1000):03d}"

    def _mode_line(self, mode, audio_ts):
        """モードの境目を transcript に残す。表示側はここでセッションを区切る。"""
        with self.transcript.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"ts": self._iso(audio_ts), "type": "mode", "mode": mode},
                    ensure_ascii=False,
                )
                + "\n"
            )
        print(f"== 同席モード: {mode} ==", flush=True)

    def emit(self, speaker, text, is_final, capture_ts, end_ts=None, audio_now=None):
        # 「いま」も音声時間で測る。OS の時計を混ぜると数%ぶん遅延が水増しされる。
        now = audio_now if audio_now is not None else (end_ts or capture_ts)
        self.sync_wall(now)
        lat = now - (end_ts if end_ts else capture_ts)  # 喋り終わってから出るまで
        with self.lock:
            if is_final:
                # --- 会議中プロトコル: こちら側の発話だけを見る ---
                call = False
                if speaker == "host":
                    if self.mode_start in text:
                        self._mode_line("start", capture_ts)
                    if self.mode_end in text:
                        self._mode_line("end", capture_ts)
                    call = any(w in text for w in self.call_words)

                rec = {"ts": self._iso(capture_ts), "speaker": speaker, "text": text}
                if call:
                    # 論点検知より優先。表示側はこの行を専用枠へ回す
                    rec["call"] = True
                with self.transcript.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if call:
                    print(f"  ★ 呼び出し検知: {text}", flush=True)
                with self.latency.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "speaker": speaker,
                                "capture_ts": round(self._wall(capture_ts), 3),
                                "end_ts": round(self._wall(end_ts), 3) if end_ts else None,
                                "write_ts": round(self._wall(now), 3),
                                "latency_s": round(lat, 3),
                                "chars": len(text),
                            }
                        )
                        + "\n"
                    )
                self.stats.setdefault(speaker, []).append(lat)
                self.partial.pop(speaker, None)
                if not self.quiet:
                    print(f"  [{speaker:5}] {text}   (+{lat:.1f}s)", flush=True)
            else:
                self.partial[speaker] = text
            tmp = self.partial_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"partial": self.partial, "updated": self._wall(now)}, ensure_ascii=False
                ),
                encoding="utf-8",
            )
            tmp.replace(self.partial_path)


# ---------------------------------------------------------------- 接続処理


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        cfg = self.server.cfg
        writer = self.server.writer
        sock = self.request
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # 挨拶は JSON 1行: {"ch":"T","rate":16000,"token":"..."}
        greet = b""
        while b"\n" not in greet and len(greet) < 512:
            d = sock.recv(1)
            if not d:
                return
            greet += d
        try:
            hello = json.loads(greet.decode().strip())
        except (json.JSONDecodeError, UnicodeDecodeError):
            print("!! 挨拶が読めない -- 切断", flush=True)
            return
        kind = hello.get("ch", "")
        src_sr = int(hello.get("rate", SRC_SR))
        speaker = CH_SPEAKER.get(kind)
        if not speaker:
            print(f"!! 未知のチャンネル {kind!r} -- 切断", flush=True)
            return
        if cfg.token and hello.get("token") != cfg.token:
            # 既定で外向きに口を開けるので、合言葉が違う子機は入れない
            print(f"!! 合言葉が違う ({self.client_address[0]}) -- 切断", flush=True)
            return
        # 同じチャンネルに二重接続したら新しい方を採る (子機の起動し直し・取り残し対策)。
        # これが無いと子機が2つ生きているとき全行が二重に出る。
        token = object()
        with self.server.active_lock:
            dup = speaker in self.server.active
            self.server.active[speaker] = token
        print(
            f"++ {speaker} 接続 ({self.client_address[0]} / {src_sr}Hz)"
            + ("  ※先の接続を打ち切って差し替え" if dup else ""),
            flush=True,
        )

        # 子機が既に目的のレートで送ってくるなら変換しない (遠隔では16kHzで送ってくる)
        rs = Resampler(src_sr, cfg.rate) if src_sr != cfg.rate else None
        kw = {"language": cfg.language, "vad_threshold": cfg.vad_threshold}
        if cfg.model:  # 空文字を渡すとアダプタ側の既定モデルが消えるので入れない
            kw["model"] = cfg.model
        if cfg.prompt:
            kw["prompt"] = cfg.prompt
        if cfg.keywords:
            kw["keywords"] = [k.strip() for k in cfg.keywords.split(",") if k.strip()]
        sess = stt_mod.make_session(
            cfg.backend,
            speaker,
            lambda t, f, ts, end=None: writer.emit(
                speaker, t, f, ts, end, self.server.pos.get(speaker)
            ),
            cfg.rate,
            **kw,
        )
        # --- 時刻の決め方 ---
        # 受け取ったサンプル数だけで時間を進める。錨は最初の1回だけ。
        # 子機側が無音を詰めて実時間と同じ速さで送ってくるので、これで実時間に一致する。
        t0 = None      # このストリームの先頭 (monotonic は速いので相対値としてのみ使う)
        nsamp = 0      # これまでに受け取ったサンプル数
        buf = b""
        try:
            while True:
                if self.server.active.get(speaker) is not token:
                    print(f"-- {speaker} 旧接続を終了", flush=True)
                    return
                while len(buf) < HDR.size:
                    d = sock.recv(65536)
                    if not d:
                        raise ConnectionError
                    buf += d
                _agent_ts, n = HDR.unpack(buf[: HDR.size])  # 子機の時刻は参考値。使わない
                buf = buf[HDR.size:]
                while len(buf) < n:
                    d = sock.recv(65536)
                    if not d:
                        raise ConnectionError
                    buf += d
                pcm, buf = buf[:n], buf[n:]

                nsamp_chunk = n // 2
                if t0 is None:
                    t0 = time.monotonic()
                ts = t0 + nsamp / src_sr          # このチャンクの先頭の時刻 (音声時間)
                nsamp += nsamp_chunk
                self.server.pos[speaker] = t0 + nsamp / src_sr

                self.server.level[speaker] = float(
                    np.sqrt(np.mean((np.frombuffer(pcm, "<i2").astype(np.float32) / 32768.0) ** 2))
                )
                if cfg.xtalk_gate and speaker == "host":
                    # スピーカー再生時にマイクが相手の声を拾う「回り込み」対策 (任意)。
                    # これは保険であって解決ではない。イヤホンを使うこと。
                    if self.server.level.get("guest", 0.0) > self.server.level["host"] * 1.5:
                        continue
                out = rs(pcm) if rs else pcm
                if out:
                    sess.feed(out, ts)
        except (ConnectionError, OSError):
            pass
        finally:
            sess.close()
            with self.server.active_lock:
                if self.server.active.get(speaker) is token:
                    del self.server.active[speaker]
            print(f"-- {speaker} 切断", flush=True)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=47311)
    ap.add_argument("--backend", default="stub", choices=list(stt_mod.BACKENDS))
    ap.add_argument("--rate", type=int, default=0, help="STT へ送るサンプルレート (0=バックエンド既定)")
    ap.add_argument("--language", default="ja")
    ap.add_argument("--model", default="")
    ap.add_argument("--prompt", default="", help="会議の状況説明 (固有名詞の認識精度が上がる)")
    ap.add_argument("--keywords", default="", help="固有名詞をカンマ区切りで")
    ap.add_argument("--vad-threshold", type=float, default=0.012)
    ap.add_argument("--token", default=os.environ.get("MEETLIVE_TOKEN", ""),
                    help="子機との合言葉 (0.0.0.0 で待つので設定推奨)")
    ap.add_argument("--xtalk-gate", action="store_true",
                    help="回り込み抑制 (イヤホン無しのときの保険。解決ではない)")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--fresh", action="store_true", help="transcript を作り直す")
    ap.add_argument("--quiet", action="store_true")
    cfg = ap.parse_args()

    if not cfg.rate:
        # OpenAI の transcription セッションは PCM 24kHz が公式例。他は 16kHz で足りる。
        cfg.rate = 24000 if cfg.backend == "openai" else 16000

    if cfg.backend != "stub":
        env = {"openai": "OPENAI_API_KEY", "deepgram": "DEEPGRAM_API_KEY"}[cfg.backend]
        if not os.environ.get(env):
            raise SystemExit(f"環境変数 {env} が未設定。export {env}=... してから起動せよ。")

    outdir = pathlib.Path(cfg.outdir) if cfg.outdir else cfgmod.state_dir()
    outdir.mkdir(parents=True, exist_ok=True)
    if cfg.fresh:
        for n in ("transcript.jsonl", "latency.jsonl", "partial.json"):
            (outdir / n).unlink(missing_ok=True)

    writer = Writer(outdir, quiet=cfg.quiet)
    srv = Server((cfg.host, cfg.port), Handler)
    srv.cfg = cfg
    srv.writer = writer
    srv.level = {}
    srv.active = {}
    srv.active_lock = threading.Lock()
    srv.pos = {}   # speaker -> いま受け取っているところの音声時間
    print(
        f"meetlive receiver: {cfg.host}:{cfg.port}  backend={cfg.backend} "
        f"rate={cfg.rate} -> {outdir}",
        flush=True,
    )
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        n = sum(len(v) for v in writer.stats.values())
        if n:
            allv = sorted(x for v in writer.stats.values() for x in v)
            print(
                f"\n発話 {n} 件 / 遅延(喋り終わり->出力) p50={allv[len(allv)//2]:.2f}s "
                f"max={allv[-1]:.2f}s",
                flush=True,
            )


if __name__ == "__main__":
    main()
