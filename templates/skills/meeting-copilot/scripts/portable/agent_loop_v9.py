# meetlive 子機・相手側(ループバック)専用の最小版 (v9)。
#
# ⚠ 通常は agent_loop.py (v10) を使うこと。こちらは v10 の比較用に残してある最小実装で、
#   **無音が続くと1バイトも送らない**。STT 側がソケットを死んだとみなして 1011 で切り、
#   相手チャンネルだけが丸ごと落ちる。v10 はこれを無音パディングで直したもの。
#   デバイスが開けるかどうかの切り分けにだけ使う。
#
# Bluetooth 再生デバイスの WASAPI ループバックは取得時にネイティブ層ごと落ちることがある。
# 開けたときは 48000Hz/2ch でしか安定しないので、その形で開き 16000Hz/mono に落として送る。
# 落ちたら agent_loop.cmd 側のループで即再起動する(このファイル自身は1回だけ試す)。
import json
import pathlib
import socket
import struct
import sys
import time
import warnings

warnings.filterwarnings("ignore")  # data discontinuity 等の無害な注意表示を消す
import numpy as np  # noqa: E402
import soundcard as sc  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from agent_common import load_cfg  # noqa: E402

host, port, token, rate, _mic_match = load_cfg()
HDR = struct.Struct("<dI")
REC_RATE, REC_CH = 48000, 2
step = REC_RATE // rate
rec_chunk = REC_RATE // 10
chunk = rate // 10

print(f"[loop-only] 親機 {host}:{port} 送信rate={rate} 取込={REC_RATE}Hz/{REC_CH}ch", flush=True)
sp = sc.default_speaker()
print(f"[loop-only] 既定スピーカー: {sp}", flush=True)
m = sc.get_microphone(id=str(sp.id), include_loopback=True)   # ← ここで落ちることがある
print(f"[loop-only] ループバック取得OK: {m}", flush=True)

sock = socket.create_connection((host, port), timeout=10)
sock.settimeout(None)
sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
sock.sendall((json.dumps({"ch": "G", "rate": rate, "token": token}) + "\n").encode())
print("[loop-only] 接続OK -> 送信中 (Ctrl+C で停止)", flush=True)
try:
    with m.recorder(samplerate=REC_RATE, channels=REC_CH, blocksize=rec_chunk // 4) as rec:
        t0 = time.monotonic()
        sent = 0
        while True:
            d = rec.record(numframes=rec_chunk)
            mono = d.mean(axis=1) if d.ndim > 1 else d
            mono = mono.reshape(-1, step).mean(axis=1) if len(mono) % step == 0 else mono[::step]
            pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
            sock.sendall(HDR.pack(time.time(), len(pcm)) + pcm)
            sent += len(pcm) // 2
            gap = int((time.monotonic() - t0) * rate) - sent
            if gap >= chunk:
                pad = min(gap, rate * 5)
                z = b"\x00\x00" * pad
                sock.sendall(HDR.pack(time.time(), len(z)) + z)
                sent += pad
except KeyboardInterrupt:
    print("[loop-only] 停止", flush=True)
finally:
    try:
        sock.close()
    except Exception:
        pass
