#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# stop.sh — run.sh で起こしたものを、**それぞれが持っている停止の口**から畳む。
#
#   MEETLIVE_MEETING=... MEETLIVE_DIR=... ./stop.sh --port 47323
#
# 🔴 kill / pkill は使わない。会議中に走っている別の python を巻き込むし、
#    畳んでいる途中のファイル（逐語・カード）を壊す。
#
# 停止の口は**全層で1つ**: <状態Dir>/meetlive.stop を置くだけ。
# 各層が自分でそれを見に行き、自分で終わる（2026-09-19 改修）。
#
#   copilot   … tail の周回で見る（終話を検知したときは自分でこれを置く）
#   receiver  … 2秒ごとに見て、自分の待ち受けを畳む
#   viewer2   … 2秒ごとに見て降板する（従来どおり HTTP /quit でも降りる）
#   responder … 自分あての responder.stop でも、この共通ファイルでも終わる
#
# 🔴 なぜこれが要ったか: 2026-09-19 の実走で、会議のあと3つのプロセスが12時間近く
#    残り、誰も見ていない画面に同じカードを903件描き続けた。receiver と copilot には
#    停止の口が無く、手で Ctrl-C するしかなかった（そして忘れた）。
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${MEETLIVE_PYTHON:-python3}"
PORT="47323"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift ;;
    -h|--help) sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'stop.sh: 知らないオプション: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

STATE="$("$PY" - "$HERE" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import meetlive_config as c
print(c.state_dir(create=False))
PYEOF
)"

printf '状態ディレクトリ: %s\n' "$STATE"

# ── 全層に効く停止ファイル ──────────────────────────────────────────────
if [[ -d "$STATE" ]]; then
  printf '{"ts":"%s","by":"stop.sh"}\n' "$(date -Iseconds)" > "$STATE/meetlive.stop"
  printf '停止 共通        %s を置きました（各層が次の周回で自分で終わります）\n' \
    "$STATE/meetlive.stop"
  : > "$STATE/responder.stop"    # 返し役は自分あての口も持っている（先に効く）
else
  printf '        共通        状態ディレクトリが無いので何もしません: %s\n' "$STATE"
fi

# ── viewer2: HTTP でも降ろす（停止ファイルより速い） ────────────────────
if curl -sS --max-time 5 "http://127.0.0.1:$PORT/quit" >/dev/null 2>&1; then
  printf '停止 viewer2    /quit を受理（ポート %s）\n' "$PORT"
else
  printf '        viewer2    ポート %s に応答なし（すでに降りている）\n' "$PORT"
fi

printf '\n各層の pid（残っていないか確かめる材料。このスクリプトは触りません）:\n'
for name in receiver copilot viewer2 responder; do
  pidfile="$STATE/logs/$name.pid"
  if [[ -f "$pidfile" ]]; then
    printf '  %-9s pid=%s\n' "$name" "$(cat "$pidfile")"
  else
    printf '  %-9s 起動記録なし\n' "$name"
  fi
done
printf '\n次の会議は run.sh が停止ファイルを片付けてから起こします。\n'
