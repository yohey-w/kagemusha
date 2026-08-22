# meetlive 子機・共通部分 (config.txt の読み込みだけ)。
# 3つの子機スクリプト(agent.py / agent_mic.py / agent_loop.py)が同じ設定を同じ規則で読む。
#
# 規律: **接続先の既定値をコードへ書かない**。config.txt が無い/書き換えられていない
#       ときは、黙ってどこかへ繋ぎに行かず、その場で止めて何をすべきか出す。
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PLACEHOLDER = "CHANGE_ME"


def load_cfg():
    """config.txt を読み、(host, port, token, rate, mic_match) を返す。

    config.txt が無い、または placeholder のままなら SystemExit で止まる。
    """
    f = HERE / "config.txt"
    if not f.exists():
        raise SystemExit(
            "config.txt がありません。\n"
            "  config.txt.example を config.txt という名前でコピーし、\n"
            "  host / port / token を親機に合わせて書き換えてから、もう一度実行してください。"
        )
    cfg = {"host": "", "port": "47311", "token": "", "rate": "16000", "mic_match": ""}
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip().lower()] = v.strip()
    if not cfg["host"] or PLACEHOLDER in cfg["host"]:
        raise SystemExit(
            "config.txt の host が未設定です。親機のアドレス"
            "(tailscale 等のプライベート網のIP)を書いてください。"
        )
    if PLACEHOLDER in cfg["token"]:
        raise SystemExit(
            "config.txt の token が例のままです。親機の receiver.py と同じ合言葉に"
            "書き換えてください。"
        )
    try:
        port, rate = int(cfg["port"]), int(cfg["rate"])
    except ValueError:
        raise SystemExit("config.txt の port / rate は数字で書いてください。")
    return cfg["host"], port, cfg["token"], rate, cfg["mic_match"]


def pick_microphone(sc, mic_match: str):
    """マイクを決める。mic_match が空なら OS の既定。

    既定のマイクが Bluetooth 機器のとき、取得時にネイティブ層ごと落ちることがある。
    その回避のために「名前の一部で内蔵マイクを指名する」逃げ道を用意してある。
    """
    if mic_match:
        try:
            for cand in sc.all_microphones(include_loopback=False):
                if mic_match.lower() in str(cand.name).lower():
                    return cand
        except Exception as e:  # noqa: BLE001
            print(f"[mic] マイク一覧の取得に失敗（既定へ落ちる）: {e}", flush=True)
        print(f"[mic] '{mic_match}' に一致するマイクが無いので既定を使います", flush=True)
    return sc.default_microphone()


if __name__ == "__main__":
    h, p, t, r, mm = load_cfg()
    print(f"host={h} port={p} rate={r} token={'(設定あり)' if t else '(空)'} mic_match={mm!r}")
    sys.exit(0)
