#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# stop.sh — run.sh で起こしたものを、**それぞれが持っている停止の口**から畳む。
#
#   MEETLIVE_MEETING=... MEETLIVE_DIR=... ./stop.sh --port 47323
#
# 🔴 kill / pkill は使わない。会議中に走っている別の python を巻き込むし、
#    畳んでいる途中のファイル（逐語・カード）を壊す。
#
# 停止の口は層ごとに違い、**無い層もある**（無いものを発明しない）:
#
#   viewer2   … HTTP GET /quit（localhost からのみ。自分で降板する）
#   responder … 停止ファイル <状態Dir>/responder.stop を置くと次の周回で終わる
#   receiver  … 停止の口が無い。起動した端末で Ctrl-C（= 手動）
#   copilot   … 停止の口が無い。起動した端末で Ctrl-C（= 手動）
#
# receiver / copilot を nohup で後ろに回した場合、この2つは手で畳むしかない。
# pid は run.sh が <状態Dir>/logs/<名前>.pid に控えてあるので、最後の手段として
# 人が見て判断する材料にはなる（このスクリプトは触らない）。
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

# ── viewer2: 自分で降板してもらう ───────────────────────────────────────
if curl -sS --max-time 5 "http://127.0.0.1:$PORT/quit" >/dev/null 2>&1; then
  printf '停止 viewer2    /quit を受理（ポート %s）\n' "$PORT"
else
  printf '        viewer2    ポート %s に応答なし（すでに降りている）\n' "$PORT"
fi

# ── responder: 停止ファイルを置く ───────────────────────────────────────
if [[ -d "$STATE" ]]; then
  : > "$STATE/responder.stop"
  printf '停止 responder  停止ファイルを置きました（次の周回で自分で終わります）\n'
else
  printf '        responder  状態ディレクトリが無いので何もしません\n'
fi

# ── receiver / copilot: 停止の口が無い ──────────────────────────────────
printf '\n手動で畳むもの（停止の口を持っていない層）:\n'
for name in receiver copilot; do
  pidfile="$STATE/logs/$name.pid"
  if [[ -f "$pidfile" ]]; then
    printf '  %-9s pid=%s（起動した端末で Ctrl-C。%s）\n' \
      "$name" "$(cat "$pidfile")" "$pidfile"
  else
    printf '  %-9s 起動記録なし\n' "$name"
  fi
done
