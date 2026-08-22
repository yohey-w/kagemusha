# meetlive 子機・自分の声(マイク)専用の最小版。
# デバイス名の列挙・ループバック・二重起動チェックをしない(Bluetooth 環境でのネイティブ
# クラッシュを避けるため、余計なことを一切しない)。落ちたらランチャ側が開き直す。
#
# 送るもの: ch="T" = こちら側のマイク。親機では speaker="host" として記録される。
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
from agent_common import load_cfg, pick_microphone  # noqa: E402

host, port, token, rate, mic_match = load_cfg()
HDR = struct.Struct("<dI")
chunk = rate // 10

print(f"[mic-only] 親機 {host}:{port} rate={rate}", flush=True)
m = pick_microphone(sc, mic_match)
print(f"[mic-only] マイク: {m}", flush=True)
backoff = 1
while True:
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=10)
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.sendall((json.dumps({"ch": "T", "rate": rate, "token": token}) + "\n").encode())
        print("[mic-only] 接続OK -> 送信中 (Ctrl+C で停止)", flush=True)
        backoff = 1
        with m.recorder(samplerate=rate, channels=1, blocksize=chunk // 4) as rec:
            t0 = time.monotonic()
            sent = 0
            while True:
                d = rec.record(numframes=chunk)
                mono = d[:, 0] if d.ndim > 1 else d
                pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
                sock.sendall(HDR.pack(time.time(), len(pcm)) + pcm)
                sent += len(pcm) // 2
                # 実時間より送ったサンプル数が足りなければ無音で埋める。
                # 親機は「受け取ったサンプル数」で時計を進めるので、埋めないと
                # このチャンネルの時刻だけが実時間から遅れていく。
                gap = int((time.monotonic() - t0) * rate) - sent
                if gap >= chunk:
                    pad = min(gap, rate * 5)
                    z = b"\x00\x00" * pad
                    sock.sendall(HDR.pack(time.time(), len(z)) + z)
                    sent += pad
    except KeyboardInterrupt:
        print("[mic-only] 停止", flush=True)
        break
    except Exception as exc:  # noqa: BLE001
        backoff = min(30, backoff * 2)
        print(f"[mic-only] {type(exc).__name__}: {exc} -- {backoff}秒後に繋ぎ直す", flush=True)
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    time.sleep(backoff)
