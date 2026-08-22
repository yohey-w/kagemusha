# meetlive child / guest side (WASAPI loopback) -- v10.
# ASCII only on purpose: the Windows console is cp932 and this window must stay readable.
#
# Sends ch="G" = the other side's voice, captured as a loopback of the default speaker.
# The parent records it as speaker="guest".
#
# Why v10 exists:
#   soundcard's rec.record() on a WASAPI loopback device BLOCKS while nothing is
#   being played back. During a silent stretch v9 therefore sent no bytes at all,
#   the STT provider saw a dead socket and closed the guest stream with
#   1011 "did not receive audio data ... within the timeout window".
#   The receiver also advances its clock purely by received sample count, so the
#   missing samples pushed every guest timestamp further and further behind.
#
# v10 splits the work in two:
#   - a recorder THREAD owns the device and pushes 16k mono PCM into a queue;
#   - the MAIN loop sends whatever the queue has, and when nothing arrives within
#     0.25 s it emits real-time-worth of digital silence so the byte stream keeps
#     running at exactly `rate` samples/second of wall clock.
# If the recorder thread dies the process exits non-zero; start_all.ps1 / agent_loop.cmd
# restart it (both loop on any exit code).
import json
import os
import pathlib
import queue
import socket
import struct
import sys
import threading
import time
import warnings

warnings.filterwarnings("ignore")  # hide harmless "data discontinuity" notices
import numpy as np  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from agent_common import load_cfg  # noqa: E402

HDR = struct.Struct("<dI")
REC_RATE, REC_CH = 48000, 2
IDLE_WAIT = 0.25       # seconds to wait for real audio before padding
QUEUE_MAX = 100        # ~10 s of 100 ms chunks; oldest is dropped when full


def recorder_thread(mic, rate, q, err_box, stop_ev):
    """Own the loopback device. Push 16k mono PCM bytes into q. Never send here."""
    step = REC_RATE // rate
    rec_chunk = REC_RATE // 10
    dropped = 0
    try:
        with mic.recorder(samplerate=REC_RATE, channels=REC_CH, blocksize=rec_chunk // 4) as rec:
            while not stop_ev.is_set():
                d = rec.record(numframes=rec_chunk)
                if d is None or len(d) == 0:
                    time.sleep(0.01)   # never spin if the device returns nothing
                    continue
                mono = d.mean(axis=1) if d.ndim > 1 else d
                mono = mono.reshape(-1, step).mean(axis=1) if len(mono) % step == 0 else mono[::step]
                pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
                try:
                    q.put_nowait(pcm)
                except queue.Full:
                    try:
                        q.get_nowait()          # drop the OLDEST chunk
                    except queue.Empty:
                        pass
                    try:
                        q.put_nowait(pcm)
                    except queue.Full:
                        pass
                    dropped += 1
                    if dropped % 10 == 1:
                        print(f"[loop] send is behind: dropped {dropped} chunks", flush=True)
    except BaseException as exc:  # noqa: BLE001  -- report anything, including native aborts
        err_box.append(exc)


def pump(sock, q, err_box, rate, t0=None):
    """Send real audio when it arrives, otherwise pad with silence up to wall clock.

    Returns when the recorder thread reported an error (err_box non-empty);
    a dead socket raises out of here and is handled by main().
    Padding never goes past the wall clock, so it can never create a surplus, and
    real audio is NEVER dropped to catch down.
    """
    chunk = rate // 10
    if t0 is None:
        t0 = time.monotonic()
    sent = 0                       # samples handed to the socket so far
    while True:
        if err_box:
            return sent
        try:
            pcm = q.get(timeout=IDLE_WAIT)
        except queue.Empty:
            pcm = None
        if pcm:
            sock.sendall(HDR.pack(time.time(), len(pcm)) + pcm)
            sent += len(pcm) // 2
        gap = int((time.monotonic() - t0) * rate) - sent
        if gap >= chunk:
            pad = min(gap, rate * 5)
            z = b"\x00\x00" * pad
            sock.sendall(HDR.pack(time.time(), len(z)) + z)
            sent += pad


def main():
    import soundcard as sc   # imported here so this file stays importable off Windows

    host, port, token, rate, _mic_match = load_cfg()
    print(f"[loop-only] host {host}:{port} send rate={rate} capture={REC_RATE}Hz/{REC_CH}ch",
          flush=True)
    sp = sc.default_speaker()
    print(f"[loop-only] default speaker: {sp}", flush=True)
    mic = sc.get_microphone(id=str(sp.id), include_loopback=True)  # may crash: launcher retries
    print(f"[loop-only] loopback OK: {mic}", flush=True)

    sock = socket.create_connection((host, port), timeout=10)
    sock.settimeout(None)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.sendall((json.dumps({"ch": "G", "rate": rate, "token": token}) + "\n").encode())
    print("[loop-only] connected OK -> sending (close this window to stop)", flush=True)

    q = queue.Queue(maxsize=QUEUE_MAX)
    err_box = []
    stop_ev = threading.Event()
    th = threading.Thread(
        target=recorder_thread, args=(mic, rate, q, err_box, stop_ev), daemon=True
    )
    th.start()
    try:
        pump(sock, q, err_box, rate)
    except KeyboardInterrupt:
        print("[loop-only] stopped", flush=True)
        stop_ev.set()
        try:
            sock.close()
        except Exception:
            pass
        return 0
    except Exception as exc:  # noqa: BLE001  -- socket died
        print(f"[loop-only] send failed: {type(exc).__name__}: {exc}", flush=True)
        stop_ev.set()
        try:
            sock.close()
        except Exception:
            pass
        sys.stdout.flush()
        os._exit(1)
    # pump only returns when the recorder thread reported an error
    exc = err_box[0] if err_box else RuntimeError("recorder thread ended")
    print(f"[loop-only] recorder died: {type(exc).__name__}: {exc} -- restarting", flush=True)
    stop_ev.set()
    try:
        sock.close()
    except Exception:
        pass
    sys.stdout.flush()
    os._exit(1)   # the recorder thread may be stuck in native code; do not wait for it


if __name__ == "__main__":
    sys.exit(main() or 0)
