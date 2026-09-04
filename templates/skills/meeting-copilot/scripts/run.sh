#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# run.sh — 会議フォルダ1つを渡して、その会議に必要な層だけを起こす。
#
#   MEETLIVE_MEETING=~/meetings/2026-01-20-acme \
#   MEETLIVE_DIR=~/meetlive_state/2026-01-20-acme \
#   MEETLIVE_CREDS_FILE=~/secrets/acme_logins.md \
#   ./run.sh --port 47323 --backend deepgram
#
#   ./run.sh --dry-run          # 何をどう起こすかを表示するだけ（会議の前夜に見る）
#
# 起こす層は meeting.json の features が決める:
#   receiver … 子機からの音を受けて逐語にする（features.receiver・既定 true）
#   viewer2  … カンペ画面と舞台窓を配る（常に起こす。これが無いと何も見えない）
#   copilot / responder … 構えが違う2つの層。**同時には起こさない**
#                         copilot=進行の番人（ルールのみ）/ responder=そのまま言える返し
#   premise_watch … 常駐ではない。copilot が発話ごとに1回ずつ起こす子プロセスなので、
#                   ここでは起こせない（copilot=false なら前提監視も動かない）
#
# 🔴 止め方は stop.sh。kill / pkill は使わない
#   （viewer2 は HTTP /quit、responder は停止ファイル。receiver と copilot には
#     停止の口が無いので、その2つだけは手で畳む — 詳しくは stop.sh と SKILL.md）
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${MEETLIVE_PYTHON:-python3}"

DRY=0
PORT="47323"
HOST="127.0.0.1"
BACKEND="stub"
KEYWORDS=""
START=""
TOTAL_MIN=""
FRESH=0

usage() {
  sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

オプション:
  --dry-run           起動コマンドを表示するだけ（何も起こさない）
  --port N            カンペ画面のポート (既定 47323)
  --host ADDR         画面を配る宛先 (既定 127.0.0.1・別端末から見るなら 0.0.0.0)
  --backend NAME      receiver の音声認識バックエンド (既定 stub)
  --keywords "a,b"    receiver へ渡す固有名詞（必ずダブルクォートで囲む）
  --start ISO8601     会議開始時刻 (省略時は meeting.json の start)
  --total-min N       会議の長さ（分・省略時は meeting.json / 段取りJSON）
  --fresh             receiver の逐語を作り直す
  --python PATH       使う python (既定 $MEETLIVE_PYTHON / python3)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --port) PORT="$2"; shift ;;
    --host) HOST="$2"; shift ;;
    --backend) BACKEND="$2"; shift ;;
    --keywords) KEYWORDS="$2"; shift ;;
    --start) START="$2"; shift ;;
    --total-min) TOTAL_MIN="$2"; shift ;;
    --fresh) FRESH=1 ;;
    --python) PY="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'run.sh: 知らないオプション: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# ─── 会議フォルダと状態ディレクトリ ─────────────────────────────────────
# 解決の規則は meetlive_config の1箇所にしか無い。ここでは読み返すだけ。
if [[ -z "${MEETLIVE_MEETING:-}" ]]; then
  cat >&2 <<'EOF'
run.sh: MEETLIVE_MEETING が未設定です。
        会議フォルダ（meeting.json のあるディレクトリ）を指してください。
        手近な1つ: config/example_meeting （架空のデモ会議）
EOF
  exit 2
fi

read -r STATE FEAT_RECEIVER FEAT_COPILOT FEAT_RESPONDER FEAT_PREMISE TITLE <<EOF
$("$PY" - "$HERE" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import meetlive_config as c
f = c.features()
m = c.load_meeting()


def b(key, default=True):
    return "yes" if f.get(key, default) else "no"


print(c.state_dir(), b("receiver"), b("copilot"), b("responder"),
      b("premise_watch"), (m.get("title") or "(無題)").replace(" ", "_"))
PYEOF
)
EOF

LOGS="$STATE/logs"
[[ "$DRY" -eq 1 ]] || mkdir -p "$LOGS"

if [[ "$FEAT_COPILOT" == "yes" && "$FEAT_RESPONDER" == "yes" ]]; then
  cat >&2 <<'EOF'
run.sh: features の copilot と responder が両方 true です。
        2つは同じ cards.jsonl に書くので、片方のカードがもう片方を押し出します。
        meeting.json でどちらか一方を false にしてください。
EOF
  exit 2
fi
if [[ "$FEAT_COPILOT" == "no" && "$FEAT_PREMISE" == "yes" ]]; then
  cat >&2 <<'EOF'
run.sh: ⚠ features.premise_watch=true ですが copilot=false です。
        前提監視は常駐ではなく copilot が発話ごとに起こす子プロセスなので、
        この構えでは**前提監視は動きません**（起動そのものは続けます）。
EOF
fi

# ─── 起こすものを組み立てる ─────────────────────────────────────────────
NAMES=()
CMDS=()

add() {   # add <名前> <コマンド…>
  local name="$1"; shift
  NAMES+=("$name")
  CMDS+=("$(printf '%q ' "$@")")
}

if [[ "$FEAT_RECEIVER" == "yes" ]]; then
  RECV=("$PY" "$HERE/receiver.py" --backend "$BACKEND" --host 0.0.0.0)
  [[ -n "$KEYWORDS" ]] && RECV+=(--keywords "$KEYWORDS")
  [[ "$FRESH" -eq 1 ]] && RECV+=(--fresh)
  add receiver "${RECV[@]}"
fi

VIEW=("$PY" "$HERE/viewer2.py" --host "$HOST" --port "$PORT")
[[ -n "$START" ]] && VIEW+=(--start "$START")
[[ -n "$TOTAL_MIN" ]] && VIEW+=(--total-min "$TOTAL_MIN")
add viewer2 "${VIEW[@]}"

if [[ "$FEAT_RESPONDER" == "yes" ]]; then
  add responder "$PY" "$HERE/responder.py" --watch
fi
if [[ "$FEAT_COPILOT" == "yes" ]]; then
  COP=("$PY" "$HERE/copilot.py")
  [[ -n "$START" ]] && COP+=(--start "$START")
  add copilot "${COP[@]}"
fi

# ─── 表示 or 起動 ───────────────────────────────────────────────────────
printf '会議: %s\n' "${TITLE//_/ }"
printf '会議フォルダ: %s\n' "$MEETLIVE_MEETING"
printf '状態ディレクトリ: %s\n' "$STATE"
printf '合言葉ファイル: %s\n' "${MEETLIVE_CREDS_FILE:-(未設定・鍵パネルは出ません)}"
printf '起こす層: %s\n' "${NAMES[*]}"
if [[ "$FEAT_PREMISE" == "yes" ]]; then
  printf '前提監視: copilot が発話ごとに起こします（常駐しないのでここでは起こしません）\n'
fi

if [[ "$DRY" -eq 1 ]]; then
  printf '\n--- dry-run: 実際に叩かれるのは次の %d 本です ---\n' "${#NAMES[@]}"
  for i in "${!NAMES[@]}"; do
    printf '[%s]\n  %s\n  >> %s\n' "${NAMES[$i]}" "${CMDS[$i]}" "$LOGS/${NAMES[$i]}.log"
  done
  printf '\n画面: http://%s:%s\n' "$HOST" "$PORT"
  printf '止める: %s --port %s\n' "$HERE/stop.sh" "$PORT"
  exit 0
fi

for i in "${!NAMES[@]}"; do
  name="${NAMES[$i]}"
  # shellcheck disable=SC2086  # CMDS の中身は printf %q 済み（意図的に語分割する）
  eval "nohup ${CMDS[$i]} >> '$LOGS/$name.log' 2>&1 &"
  printf '%s\n' "$!" > "$LOGS/$name.pid"
  printf '起動 %-10s pid=%-8s log=%s\n' "$name" "$!" "$LOGS/$name.log"
  sleep 1
done

printf '\n画面: http://%s:%s\n' "$HOST" "$PORT"
printf '止める: %s --port %s\n' "$HERE/stop.sh" "$PORT"
