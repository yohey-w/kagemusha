"""
meetlive 音声子機 (Windows) — 1プロセスで2系統を送る旧来版
==========================================================
音を録って親機へ流すだけ。STT も API キーも持たない。

  ch T = マイク入力                    -> こちら側の声 (親機では speaker="host")
  ch G = 既定スピーカーのループバック  -> 相手の声     (親機では speaker="guest")

⚠ どちらを使うか
   このファイルは2系統を1プロセスで扱う。片方のデバイスが native層ごと落ちると
   両方まとめて死ぬので、**実運用では START.bat (= agent_mic.py と agent_loop.py を
   別々の窓で動かす) を推奨**する。こちらは1窓で済ませたいときの簡易版。

親機へ TCP 接続する。帯域を細くするため既定で 16kHz mono int16 = 256kbps/ch
(2ch で約512kbps)。接続先は config.txt で決める(コードに既定値は持たない)。

  setup.cmd  … 初回だけ (Python と部品を入れる)
  start.cmd  … このファイルを起動する
  stop.cmd   … 止める

フレーム形式 (little endian):
  接続直後に JSON 1行 + "\\n":  {"ch":"T","rate":16000,"token":"..."}
  以降くり返し: double 送信時刻(8B) | uint32 バイト数(4B) | PCM int16 mono
"""
import argparse
import json
import os
import pathlib
import socket
import struct
import sys
import threading
import time
import warnings

import numpy as np
import soundcard as sc

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from agent_common import load_cfg, pick_microphone  # noqa: E402

warnings.filterwarnings("ignore")

HDR = struct.Struct("<dI")

_print_lock = threading.Lock()
_singleton = None


def log(msg):
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def resolve(kind, mic_match=""):
    """役割からデバイスを毎回解決する (ID をハードコードしない)。
    リモートデスクトップ越しでは「リモート オーディオ」、ノートPCでは実機名になるため。

    Bluetooth 再生デバイスの WASAPI ループバックは 16000Hz/mono で開くとネイティブ層ごと
    落ちることがある。ループバックは 48000Hz/2ch で開き、子機側で落として送る。
    """
    if kind == "G":
        sp = sc.default_speaker()
        return (sc.get_microphone(id=str(sp.id), include_loopback=True),
                f"ループバック<{sp.name}>", 48000, 2)
    mi = pick_microphone(sc, mic_match)
    return (sc.get_microphone(id=str(mi.id), include_loopback=False),
            f"マイク<{mi.name}>", None, 1)


def stream(kind, host, port, rate, token, gain, mic_match=""):
    label = {"T": "こちら/マイク", "G": "相手/ループバック"}[kind]
    chunk = rate // 10  # 100ms
    backoff = 1
    while True:
        sock = None
        try:
            dev, name, open_rate, open_ch = resolve(kind, mic_match)
            sock = socket.create_connection((host, port), timeout=10)
            sock.settimeout(None)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.sendall(
                (json.dumps({"ch": kind, "rate": rate, "token": token}) + "\n").encode()
            )
            backoff = 1
            log(f"{label}: 接続 -> {name}  ({host}:{port} / {rate}Hz)")
            rec_rate = open_rate or rate
            rec_chunk = rec_rate // 10
            with dev.recorder(samplerate=rec_rate, channels=open_ch,
                              blocksize=rec_chunk // 4) as rec:
                # WASAPI のループバックは再生が鳴っていない間パケットを出さない。
                # そのままだと音の時間軸が実時間より遅れていくので、足りない分を無音で埋める。
                t_start = time.monotonic()
                sent = 0
                while True:
                    data = rec.record(numframes=rec_chunk)
                    mono = data.mean(axis=1) if data.ndim > 1 else data
                    if rec_rate != rate:
                        step = rec_rate // rate  # 48000->16000 は 3:1 の整数間引き
                        mono = (mono.reshape(-1, step).mean(axis=1)
                                if len(mono) % step == 0 else mono[::step])
                    if gain != 1.0:
                        mono = mono * gain
                    pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
                    sock.sendall(HDR.pack(time.time(), len(pcm)) + pcm)
                    sent += len(pcm) // 2

                    gap = int((time.monotonic() - t_start) * rate) - sent
                    if gap >= chunk:
                        pad = min(gap, rate * 5)
                        z = b"\x00\x00" * pad
                        sock.sendall(HDR.pack(time.time(), len(z)) + z)
                        sent += pad
        except Exception as exc:  # noqa: BLE001
            backoff = min(30, backoff * 2)
            log(f"{label}: {type(exc).__name__}: {exc} -- {backoff}秒後に繋ぎ直す")
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:  # noqa: BLE001
                    pass
        time.sleep(backoff)


def main():
    cfg_host, cfg_port, cfg_token, cfg_rate, cfg_mic = load_cfg()
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=cfg_host)
    ap.add_argument("--port", type=int, default=cfg_port)
    ap.add_argument("--rate", type=int, default=cfg_rate)
    ap.add_argument("--token", default=cfg_token)
    ap.add_argument("--mic-match", default=cfg_mic)
    ap.add_argument("--mic-gain", type=float, default=1.0)
    ap.add_argument("--loopback-gain", type=float, default=1.0)
    ap.add_argument("--only", choices=["T", "G"])
    args = ap.parse_args()

    # 二重起動の禁止。取り残しが1つでも生きていると親機側で奪い合いになり逐語が二重に出る。
    global _singleton
    _singleton = socket.socket()
    try:
        _singleton.bind(("127.0.0.1", 47399))
        _singleton.listen(1)
    except OSError:
        log("すでに動いている。stop.cmd で止めてから起動せよ。")
        sys.exit(1)

    log(f"meetlive 子機 起動  session={os.environ.get('SESSIONNAME', '?')}")
    log(f"  親機: {args.host}:{args.port}   音質: {args.rate}Hz mono")
    for k in ([args.only] if args.only else ["T", "G"]):
        try:
            log(f"  {k} -> {resolve(k, args.mic_match)[1]}")
        except Exception as exc:  # noqa: BLE001
            log(f"  {k} -> デバイス解決に失敗: {exc}")
    log("  ※イヤホン/イヤモニは『この画面を出す前に』挿すこと")

    gains = {"T": args.mic_gain, "G": args.loopback_gain}
    for k in [args.only] if args.only else ["T", "G"]:
        threading.Thread(
            target=stream,
            args=(k, args.host, args.port, args.rate, args.token, gains[k], args.mic_match),
            daemon=True,
        ).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("停止")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"\n!! 子機が異常終了: {type(exc).__name__}: {exc}", flush=True)
        raise
