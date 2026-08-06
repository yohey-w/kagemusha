#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# demo-distillation.sh — the first ten minutes. One full turn of the judgment
# loop (correction → harvest → distil → review → promote → audit) with NO API
# billing, NO real session logs, and NOT ONE BYTE written outside a temporary
# sandbox.
#
# 「読んで終わり」を「触って分かる」に変えるための最初の10分。
#
# WHAT IS REAL HERE AND WHAT IS NOT. The scripts are the shipped ones —
# correction_scan.py harvests, distill.sh makes the firing decision, the batch
# is frozen and validated, discipline_scan.py audits. What is fake is (a) the
# session logs, which are obviously-invented synthetic transcripts generated
# here from fixed strings, and (b) the distilling model, which is a stub that
# prints a fixed, correct eight-field report instead of costing you money.
# The stub is wired in the ONLY way a model is ever wired in this kit — as
# AGENT_CMD in a config.env — so nothing in the shipped scripts is modified,
# monkey-patched, or given a demo-only branch. If the demo passes, the same
# path passes with a real CLI in that slot.
#
# WHAT IT WILL NOT DO. It never calls an AI CLI, never touches the network
# (ntfy is off), never reads your real logs, and never writes to this
# repository or to your home directory. Everything lands in a `mktemp -d`
# sandbox that is deleted on exit (DEMO_KEEP=1 keeps it for poking at).
#
#   ./scripts/demo-distillation.sh              # read along, ~10 minutes
#   DEMO_FAST=1 ./scripts/demo-distillation.sh  # no pauses, ~seconds (CI)
#   DEMO_KEEP=1 ./scripts/demo-distillation.sh  # keep the sandbox afterwards
#
# Pinned by test group J (tests/test_j_demo.sh), which runs it with DEMO_FAST=1
# and asserts, among other things, that the repository tree is byte-identical
# before and after.
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── preflight ─────────────────────────────────────────────────────────────
for t in python3 diff grep sed; do
  command -v "$t" >/dev/null 2>&1 || {
    printf 'demo: required tool not found: %s\n' "$t" >&2; exit 2; }
done
for f in correction_scan.py distill.sh discipline_scan.py; do
  [[ -f "$SCRIPT_DIR/$f" ]] || {
    printf 'demo: missing %s — run this from a full checkout of the kit\n' "$f" >&2
    exit 2; }
done

# ─── the sandbox ───────────────────────────────────────────────────────────
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/kagemusha-demo.XXXXXX")" || {
  printf 'demo: could not create a sandbox directory\n' >&2; exit 2; }
cleanup() {
  [[ "${DEMO_KEEP:-0}" = "1" ]] && return 0
  # only ever our own mktemp directory, matched by pattern, never a variable
  # someone else could have set.
  case "$SANDBOX" in
    */kagemusha-demo.??????) rm -rf "$SANDBOX" ;;
  esac
}
trap cleanup EXIT

LOGS_BEFORE="$SANDBOX/sessions"        # synthetic "your session logs"
LOGS_AFTER="$SANDBOX/sessions-later"   # synthetic logs from AFTER the promotion
DATA="$SANDBOX/data"
RUNLOGS="$SANDBOX/runlogs"
BATCHES="$SANDBOX/batches"
mkdir -p "$LOGS_BEFORE" "$LOGS_AFTER" "$DATA" "$RUNLOGS" "$BATCHES"

MATERIAL="$DATA/corrections.md"
STATE="$DATA/corrections_state.json"
QUEUE="$DATA/promotion_queue.md"
PATTERNS="$DATA/correction_patterns.txt"
RULES="$DATA/CLAUDE.md"
PROPOSED="$DATA/CLAUDE.md.proposed"
CATALOG="$DATA/discipline_catalog.yaml"
AUDIT="$DATA/discipline_audit.md"
CONFIG="$SANDBOX/config.env"
STUB="$SANDBOX/stub-distiller.sh"
TODAY="$(date +%F)"

# ─── narration ─────────────────────────────────────────────────────────────
_b=''; _d=''; _y=''; _r=''
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  _b=$'\033[1m'; _d=$'\033[2m'; _y=$'\033[33m'; _r=$'\033[0m'
fi
step() { printf '\n%s━━━ %s%s\n' "$_b" "$1" "$_r"; }
ja()   { printf '  %s\n' "$1"; }
en()   { printf '  %s%s%s\n' "$_d" "$1" "$_r"; }
canon(){ printf '  %s“%s”%s\n' "$_y" "$1" "$_r"; }
out()  { sed 's/^/    │ /'; }

INTERACTIVE=1
[[ "${DEMO_FAST:-0}" = "1" ]] && INTERACTIVE=0
[[ -t 0 ]] || INTERACTIVE=0

pause() {
  [[ "$INTERACTIVE" = "1" ]] || return 0
  printf '\n  %s[Enter で次へ / Enter to continue]%s ' "$_d" "$_r"
  read -r _ || true
}

die() { printf '\n%sdemo FAILED: %s%s\n' "$_b" "$1" "$_r" >&2; exit 1; }

# ═══ 0. what you are looking at ════════════════════════════════════════════
printf '\n%s╔══════════════════════════════════════════════════════════════════╗%s\n' "$_b" "$_r"
printf '%s║  kagemusha — 判断ループを一周する10分                             ║%s\n' "$_b" "$_r"
printf '%s║  one full turn of the judgment loop, in ten minutes              ║%s\n' "$_b" "$_r"
printf '%s╚══════════════════════════════════════════════════════════════════╝%s\n' "$_b" "$_r"
ja "訂正 → 採取 → 蒸留 → 審査 → 昇格 → 監査。この6段を、いま一周します。"
en "correction → harvest → distil → review → promote → audit, start to finish."
printf '\n'
ja "課金ゼロ: モデルは呼びません（スタブが固定の報告を返します）"
ja "実ログ不要: 明らかに架空の合成セッションをこの場で作ります"
ja "何も汚さない: 全部この一時ディレクトリの中。終了時に消えます"
en "No API calls. No real logs. Nothing written outside the sandbox below."
printf '\n'
ja "  作業場 / sandbox : $SANDBOX"
ja "  使う本物の道具   : scripts/correction_scan.py · scripts/distill.sh · scripts/discipline_scan.py"
ja "  偽物はこの2つだけ: 合成セッションログ / 蒸留モデル（スタブ）"

# ═══ 1. the material: corrections you made, in an AI session ═══════════════
step "1. 材料 — あなたがAIを訂正した場面（合成・架空）"
en "STEP 1. The material: turns where a human overruled the agent (synthetic)."

python3 - "$LOGS_BEFORE" <<'PY_DAY1' || die "could not write the day-1 fixtures"
import json, os, sys, time
d = sys.argv[1]
base = (int(time.time()) - 7200) // 1200 * 1200   # aligned to a 20-min bucket
def ts(off): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(base + off))
def U(t, off): return json.dumps(
    {"type": "user", "timestamp": ts(off), "message": {"content": t}},
    ensure_ascii=False)
def A(t, off): return json.dumps(
    {"type": "assistant", "timestamp": ts(off),
     "message": {"content": [{"type": "text", "text": t}]}}, ensure_ascii=False)

# session 1 — ONE point, said three ways inside 20 minutes. This is the
# cluster-one-vote fixture: it must count as one event, never three.
with open(os.path.join(d, "1a1a1a1a-mitsumori.jsonl"), "w", encoding="utf-8") as f:
    f.write(A("見積書のドラフトを作成しました。金額は税抜98,000円です。", 0) + "\n")
    f.write(U("そうじゃなくて、金額は必ず総額で書いて。前に桁を間違えたから。", 120) + "\n")
    f.write(U("そうじゃなくて、税込の総額を先に。内訳はそのあとでいい。", 300) + "\n")
    f.write(U("そうじゃなくて、見出しの数字が総額ってこと。", 540) + "\n")

# session 2 — a correction with NO reason attached. The distiller must not
# invent one.
with open(os.path.join(d, "2b2b2b2b-nittei.jsonl"), "w", encoding="utf-8") as f:
    f.write(A("先方に日程調整のメールを送信しました。", 60) + "\n")
    f.write(U("やめて。送る前に見せて。", 180) + "\n")

# session 3 — a correction whose reason IS on record.
with open(os.path.join(d, "3c3c3c3c-tenken.jsonl"), "w", encoding="utf-8") as f:
    f.write(A("3件の記事を確認しましたが、問題は見当たりません。", 90) + "\n")
    f.write(U("そうじゃなくて、どこを見たか先に書いて。「見当たらない」だけだと確かめようがない。", 240) + "\n")

# a subagent turn and a tool result both wear the "user" role. Neither is you.
with open(os.path.join(d, "4d4d4d4d-noise.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"type": "user", "timestamp": ts(150), "isSidechain": True,
                        "message": {"content": "そうじゃなくて（これは別エージェントの発話）"}},
                       ensure_ascii=False) + "\n")
    f.write(json.dumps({"type": "user", "timestamp": ts(150),
                        "toolUseResult": {"ok": 1},
                        "message": {"content": "やめて（これは道具の出力）"}},
                       ensure_ascii=False) + "\n")
PY_DAY1

printf '%s\n' 'そうじゃなく' 'やめて' '違う、' > "$PATTERNS"

ja "1日目のセッションを4本置きました。中身はこういう訂正です:"
en "Four synthetic sessions. The corrections in them:"
printf '\n'
ja "  ①「そうじゃなくて、金額は必ず総額で書いて。前に桁を間違えたから。」"
ja "     …同じ話を20分の間に3回言い直しています（理由あり・言い直しあり）"
ja "  ②「やめて。送る前に見せて。」          …理由の断片なし"
ja "  ③「そうじゃなくて、どこを見たか先に書いて。」…理由あり"
ja "  ④ サブエージェントの発話と道具の出力（どちらも user ロールを着ている偽物）"
printf '\n'
ja "採取の語彙はこの3語だけ。組み込みの語彙は持ちません（自分の言い回しを書く）:"
en "The vocabulary is yours — the scanner ships with none."
printf '    %s\n' "$(tr '\n' ' ' < "$PATTERNS")"

# ═══ 2. harvest — no LLM, therefore free ═══════════════════════════════════
step "2. 採取 — correction_scan.py（LLMを呼ばない＝無料）"
en "STEP 2. Harvest. No model is involved, so this costs nothing."

harvest() {
  python3 "$SCRIPT_DIR/correction_scan.py" \
    --patterns "$PATTERNS" --material "$MATERIAL" --state "$STATE" \
    --dir "$LOGS_BEFORE" --since 7d
}
harvest 2>&1 | out || die "the harvest failed"

pending() {
  python3 "$SCRIPT_DIR/correction_scan.py" --state "$STATE" --status \
    | sed -n 's/^pending=//p'
}
P1="$(pending)"
printf '\n'
ja "採取された材料（先頭を抜粋）:"
sed -n '1,16p' "$MATERIAL" | out
ja "  （このあとに②③のイベントが続きます）"
printf '\n'
ja "一致した「あなたの発言」は5つ。しかし未蒸留イベントは ${P1} 件です。"
en "Five matching turns — but ${P1} pending EVENTS."
ja "  ・①の3回の言い直しは 1イベント に畳まれました（同一セッション＋同一時間バケツ）"
ja "  ・④のサブエージェント発話と道具出力は、そもそも採取されていません"
canon "一つのことを何通りに言い直しても、証人は一人だ（cluster-one-vote）"
en "One point restated four times is one witness, never four."
[[ "$P1" = "3" ]] || die "expected 3 pending events, got '$P1'"

# ═══ 3. the firing decision — and the silence ══════════════════════════════
step "3. 発火判定 — distill.sh は、ほとんどの日なにもしない"
en "STEP 3. The firing decision. On most days it does nothing, on purpose."

cat > "$CONFIG" <<CFG
# generated by scripts/demo-distillation.sh — sandbox only
PROJECT_ROOT="$DATA"
LOG_DIR="$RUNLOGS"
AGENT_CMD="$STUB"
AGENT_MODEL=""
AGENT_FLAGS="--dangerously-skip-permissions"
AGENT_TIMEOUT=60
NTFY_ENABLED=0
NTFY_TOPIC=""
DISTILL_MATERIAL_FILE="$MATERIAL"
DISTILL_STATE_FILE="$STATE"
DISTILL_QUEUE_FILE="$QUEUE"
DISTILL_BATCH_DIR="$BATCHES"
DISTILL_THRESHOLD=5
DISTILL_FALLBACK_DAYS=0
DISTILL_RULES_FILE="$RULES"
CFG

# The stub distiller. It is wired in exactly where a real CLI goes (AGENT_CMD),
# is invoked exactly as a real CLI is (`-p <prompt>`), and — like the real one —
# has no file tools: its entire output is stdout, which the wrapper validates
# against the frozen batch manifest before anything reaches the queue.
cat > "$STUB" <<'STUB_EOF'
#!/usr/bin/env bash
# stub-distiller.sh — stands in for the distilling model so the demo costs $0.
# Prints a fixed, correct eight-field report; picks its event ids OUT OF THE
# PROMPT it was handed, by the quote it is about — so the ids in the report are
# the real ones from this run's frozen batch, not decoration.
set -uo pipefail
prompt=""
while [[ $# -gt 0 ]]; do
  case "$1" in -p) shift; prompt="${1:-}" ;; esac
  shift || break
done
today="$(date +%F)"

id_for() {  # id_for PHRASE — the event id of the event block quoting PHRASE
  printf '%s\n' "$prompt" | awk -v pat="$1" '
    /^- event E-/ { id = $3 }
    index($0, pat) && id != "" { print id; exit }'
}
E_TOTAL_A="$(id_for '金額は必ず総額で書いて')"
E_TOTAL_B="$(id_for 'そこも税込の総額')"
E_SCOPE_A="$(id_for 'どこを見たか先に書いて')"
E_SCOPE_B="$(id_for '確認していないものは')"

processed=""
for e in "$E_TOTAL_A" "$E_TOTAL_B" "$E_SCOPE_A" "$E_SCOPE_B"; do
  [[ -n "$e" ]] && processed="${processed}${e} "
done
# Anything in the batch this stub did not file under a candidate is filed as
# "no reason on record". Every event in the batch must be accounted for — the
# wrapper rejects the run otherwise, and that rejection is the point.
no_reason=""
while read -r e; do
  [[ -n "$e" ]] || continue
  case " $processed " in *" $e "*) continue ;; esac
  case " $no_reason " in *" $e "*) continue ;; esac
  no_reason="${no_reason}${e} "
done < <(printf '%s\n' "$prompt" | grep -oE 'E-[0-9a-f]{10}' | awk '!seen[$0]++')

cat <<REPORT
<<<QUEUE-SECTION>>>
### C-${today}-1 · 金額を出すときは、税込の総額を先に書く（内訳はそのあと）
- **type:** trace
- **evidence:** 「そうじゃなくて、金額は必ず総額で書いて。前に桁を間違えたから。」(${E_TOTAL_A:-—}) ／「違う、そこも税込の総額で。」(${E_TOTAL_B:-—})
- **scope:** 見積・請求・料金など、相手が金額を読む文書すべて
- **exception:** none on record
- **confidence:** 2 event(s) in this batch（別々のセッション＝独立2票。言い直しは畳んである）
- **counter-evidence:** none found
- **destination:** verifier checklist（機械層——「円」を含む行の前に総額が来ているかは正規表現で見られる）
- **freshness:** ${today} — re-check when the pricing format changes, or in 90 days

### C-${today}-2 · 断定を書く前に、どこをどこまで見たかを1行書く
- **type:** trace（原文は「断定するな」という禁止形。遵守が観測できないので痕跡形に置き換えた）
- **evidence:** 「そうじゃなくて、どこを見たか先に書いて。「見当たらない」だけだと確かめようがない。」(${E_SCOPE_A:-—}) ／「そうじゃなくて、確認していないものは確認していないと書いて。断定するな。」(${E_SCOPE_B:-—})
- **scope:** 「無い」「問題ない」「全部〜した」など、不在や網羅を主張する文
- **exception:** 依頼側が射程を指定した場合は、その射程をそのまま引く
- **counter-evidence:** none found
- **confidence:** 2 event(s) in this batch
- **destination:** agent instructions（射程の書き方は人間が頭に持つ必要がある）
- **freshness:** ${today} — re-check in 90 days

**候補にしなかったもの:** ${no_reason:-（なし）} は「やめて」だけで、理由の断片が材料に無い。
理由を推測して書けば、それは材料ではなく作文になる。no_reason として処分を記録した
（原文は材料ファイルに残り \`--show-event\` で開ける）。
<<<END-QUEUE-SECTION>>>
<<<EVENT-DISPOSITION>>>
processed: ${processed}
no_reason: ${no_reason}
rejected:
<<<END-EVENT-DISPOSITION>>>
REPORT
STUB_EOF
chmod +x "$STUB"

ja "しきい値は5イベント。いまは ${P1} 件しかありません。走らせてみます:"
en "The threshold is 5 events; there are ${P1}. Watch what it does."
printf '\n'
env LOOP_CONFIG="$CONFIG" "$SCRIPT_DIR/distill.sh" 2>&1 | out
printf '\n'
ja "SKIPPED。モデルは呼ばれず、キューには何も載らず、費用はゼロです。"
en "SKIPPED — no model was invoked, nothing was queued, nothing was spent."
ja "これは節約ではありません。薄い材料から原則を作れと言われたモデルは"
ja "「足りません」とは言わず、薄い原則を作ります。しきい値は出力の正直さを守る装置です。"
en "Not a cost saving: a model asked to distil two thin corrections will not say"
en "\"not enough\" — it will produce two thin principles. The threshold is the honesty."
[[ -f "$QUEUE" ]] && die "the queue must not exist after a SKIPPED run"

pause

# ═══ 4. more material arrives ══════════════════════════════════════════════
step "4. 数日後 — 材料が溜まる"
en "STEP 4. A few days later: more corrections land."

python3 - "$LOGS_BEFORE" <<'PY_DAY2' || die "could not write the day-2 fixtures"
import json, os, sys, time
d = sys.argv[1]
base = (int(time.time()) - 2400) // 1200 * 1200
def ts(off): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(base + off))
def U(t, off): return json.dumps(
    {"type": "user", "timestamp": ts(off), "message": {"content": t}},
    ensure_ascii=False)
def A(t, off): return json.dumps(
    {"type": "assistant", "timestamp": ts(off),
     "message": {"content": [{"type": "text", "text": t}]}}, ensure_ascii=False)

with open(os.path.join(d, "5e5e5e5e-tsuika.jsonl"), "w", encoding="utf-8") as f:
    f.write(A("追加分の見積は60,000円です。", 0) + "\n")
    f.write(U("違う、そこも税込の総額で。", 120) + "\n")

with open(os.path.join(d, "6f6f6f6f-kokai.jsonl"), "w", encoding="utf-8") as f:
    f.write(A("記事の下書きを公開しました。", 60) + "\n")
    f.write(U("やめて。公開はこっちが押す。", 240) + "\n")

with open(os.path.join(d, "7a7a7a7a-matome.jsonl"), "w", encoding="utf-8") as f:
    f.write(A("全部確認済みです。問題ありません。", 90) + "\n")
    f.write(U("そうじゃなくて、確認していないものは確認していないと書いて。断定するな。", 300) + "\n")
PY_DAY2

ja "3件の訂正が増えました（税込の総額をもう一度／公開を止めろ／断定するな）。もう一度採取:"
en "Three more corrections. Harvest again — already-seen turns are not re-counted."
printf '\n'
harvest 2>&1 | out || die "the second harvest failed"
P2="$(pending)"
printf '\n'
ja "未蒸留イベント: ${P1} → ${P2} 件。重複採取は起きていません（内容ではなくログ記録で同定）。"
en "Pending events: ${P1} → ${P2}. Re-running the harvest is harmless."
[[ "$P2" = "6" ]] || die "expected 6 pending events, got '$P2'"

# ═══ 5. it fires ═══════════════════════════════════════════════════════════
step "5. 発火 — しきい値を超えた"
en "STEP 5. Past the threshold: the courier fires."
ja "ここでモデルが呼ばれます。ただしこのデモではスタブです（固定の正しい報告を返す）。"
en "This is where a model runs. Here it is a stub returning a fixed, correct report."
ja "スタブの差し込み口は config.env の AGENT_CMD ——本物のCLIと同じ穴です。"
en "The stub sits in AGENT_CMD, the same slot a real CLI sits in. No script was patched."
printf '\n'
env LOOP_CONFIG="$CONFIG" "$SCRIPT_DIR/distill.sh" 2>&1 | out
DRC=$?
[[ "$DRC" -eq 0 ]] || die "the distillation run did not succeed (exit $DRC)"
printf '\n'
ja "起きたことを順に:"
en "What just happened, in order:"
ja "  ① バッチを凍結（イベントidと本文のsha256をファイルに固定）してから送った"
ja "  ② モデルは1バイトも書いていない。書く道具を渡していない（stdoutだけ）"
ja "  ③ その報告をバッチ台帳と突き合わせ、6イベント全部の処分が揃って初めて"
ja "  ④ このスクリプトがキューへ追記し、そのあとで未蒸留カウンタを進めた"
canon "終了コード0は、プロセスが終わったことしか証明しない"
en "An exit code of 0 proves only that a process ended — hence the validation gate."
printf '\n'
ja "  凍結されたバッチ台帳 / frozen batch manifest:"
find "$BATCHES" -name 'B-*.json' | sed 's/^/    │ /'

# ═══ 6. the review queue ═══════════════════════════════════════════════════
step "6. 審査キュー — 人間の前に置かれるもの"
en "STEP 6. The promotion queue: what is placed in front of a person."
printf '\n'
out < "$QUEUE"
printf '\n'
ja "候補は2本。1行の規律ではなく、8欄そろって出てきます。"
en "Two candidates — never a bare rule line, always the eight review fields."
ja "  ・evidence が本体です。規律の文は蒸留器の作文、引用は実際に起きたこと。"
ja "  ・confidence は「イベント数」。言い直しは票にならない。"
ja "  ・freshness が無い規律は、二度と再検討されません。"
ja "  ・理由の断片が無かった2件は候補にせず、no_reason として処分を記録しました。"
en "Evidence outranks the rule line. Repetitions are not votes. No expiry, no re-examination."
P3="$(pending)"
ja "未蒸留イベント: ${P2} → ${P3} 件（このバッチは処理済み）。"

pause

# ═══ 7. the gate — you ═════════════════════════════════════════════════════
step "7. 関門 — ここだけは人間"
en "STEP 7. The gate. This step is a person, and only a person."
canon "移動には関門は要らない。昇格には要る。"
en "Moving text needs no gate. Promoting a correction into a rule does."
printf '\n'
ja "候補 C-${TODAY}-1 「金額を出すときは、税込の総額を先に書く」を昇格させますか?"
en "Promote candidate C-${TODAY}-1 into your standing instructions?"
printf '\n'
ANS="p"
if [[ "$INTERACTIVE" = "1" ]]; then
  read -r -p "  [p] 昇格させる / promote   [s] 見送る / skip  > " ANS || ANS="p"
  ANS="${ANS:-p}"
else
  ja "  [DEMO_FAST] 自動で p（昇格）を選びました / auto-answered: p"
fi

cat > "$RULES" <<RULES_EOF
# CLAUDE.md — agent instructions (demo sandbox)

## 規律 / standing rules

- 外へ出るものは、送る前に必ず下書きを見せて止まる。
RULES_EOF

case "${ANS}" in
  [sS]*)
    ja ""
    ja "見送りました。候補はキューに残り、材料も台帳も消えません。"
    en "Skipped. The candidate stays in the queue; nothing is lost."
    ja "（見送りも判断です。デモの残りは昇格した場合を見せます。）"
    en "(Declining is a decision too. The rest of the demo shows the promote path.)"
    ;;
esac

# ═══ 8. the diff — machine writes it, human applies it ═════════════════════
step "8. 差分までは機械・適用は人間"
en "STEP 8. The machine writes the diff. A human applies it — or does not."

cp "$RULES" "$PROPOSED"
cat >> "$PROPOSED" <<PROPOSED_EOF
- 金額を出すときは、税込の総額を先に書く。内訳はそのあと。
  〔昇格: C-${TODAY}-1 · 2 event(s) · 再確認: 料金表の書式が変わったとき、または90日後〕
PROPOSED_EOF

printf '\n'
diff -u "$RULES" "$PROPOSED" | out || true
printf '\n'
ja "これは提案（CLAUDE.md.proposed）です。CLAUDE.md 本体は1文字も変わっていません。"
en "This is CLAUDE.md.proposed. Your CLAUDE.md itself is untouched — by design."
ja "適用する動作は、このキットのどのスクリプトにも実装されていません。"
en "No script in this kit applies it. The last inch is yours, always."
ja "昇格した行が候補id・イベント数・再確認条件を連れているのを見てください。"
en "Note what the promoted line carries with it: candidate id, event count, expiry."
ja "  出所を失った規律は、あとから疑うことができません。"

pause

# ═══ 9. audit — is the rule doing anything? ════════════════════════════════
step "9. 監査 — 昇格した規律は、実際に動いているか"
en "STEP 9. The audit: after promotion, does the rule actually do anything?"

cat > "$CATALOG" <<CATALOG_EOF
disciplines:
  - id: D1
    type: trace
    name: 金額を出すときは税込の総額を先に書く
    origin: C-${TODAY}-1（このデモで昇格した規律）
    role: assistant
    fire: '税込総額'
    breach: '税抜'
    note: 昇格した規律が発火しているか——痕跡形なので数えられる
  - id: D2
    type: prohibition
    name: 確認していないことを断定しない
    origin: C-${TODAY}-2 の原文（禁止形。痕跡形に置き換える前）
    breach: '問題は見当たりません|全部確認済み'
    note: 禁止の遵守は観測できない。ゼロ件は何の証拠でもない
CATALOG_EOF

python3 - "$LOGS_AFTER" <<'PY_AFTER' || die "could not write the post-promotion fixture"
import json, os, sys, time
d = sys.argv[1]
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(time.time()) - 300))
def A(t): return json.dumps(
    {"type": "assistant", "timestamp": ts,
     "message": {"content": [{"type": "text", "text": t}]}}, ensure_ascii=False)
with open(os.path.join(d, "8b8b8b8b-ato.jsonl"), "w", encoding="utf-8") as f:
    f.write(A("見積のドラフトです。税込総額 143,000円（内訳は下記）。") + "\n")
PY_AFTER

ja "昇格の「あと」のセッションを1本足しました（規律に従って書かれたもの）。"
en "One post-promotion session added — written the way the rule asks."
ja "監査は、昇格前のログと昇格後のログの両方を走査します:"
printf '\n'
python3 "$SCRIPT_DIR/discipline_scan.py" --catalog "$CATALOG" \
  --dir "$LOGS_BEFORE" --dir "$LOGS_AFTER" --since 7d --out "$AUDIT" 2>&1 | out \
  || die "the discipline audit failed"
grep -E '^## |^  - \[(FIRE|BREACH)\]|^Trace disciplines with' "$AUDIT" | out
printf '\n'
ja "D1（痕跡形）: 昇格前のログに breach、昇格後のログに fire。輪が閉じました。"
en "D1 (trace): a breach before the promotion, a firing after it. The loop closed."
ja "D2（禁止形）: breach だけが見えます。守れた回数はどのログにも存在しません。"
en "D2 (prohibition): only breaches are observable. Compliance is the sentence nobody wrote."
canon "禁止のゼロ件は、死んだ規律の証拠ではない"
en "Zero hits on a prohibition is never a dead-letter signal — the scanner refuses to call it one."
printf '\n'
ja "そしてこの出力も判定ではありません。正規表現が引用しただけの「候補」です。"
en "And this output is candidates, not findings. Sorting them is the reviewer's job."

# ═══ 10. your turn ═════════════════════════════════════════════════════════
step "10. 次はあなたの実ログで"
en "STEP 10. Now run it on your own logs."
printf '\n'
ja "デモで見た3段は、そのまま3コマンドです:"
en "The three stages you just watched are three commands:"
printf '\n'
cat <<'NEXT'
    # 1) 採取の語彙を、自分が実際に使う言い回しに削る
    cp templates/correction_patterns.example.txt judgment/correction_patterns.txt

    # 2) 毎日の採取（LLMなし・無料）。--dir は省略するな（cronのcwdは$HOME）
    scripts/correction_scan.py \
      --patterns judgment/correction_patterns.txt \
      --material judgment/corrections.md \
      --state    judgment/corrections_state.json \
      --since 1d --dir ~/.claude/projects/<your-project-slug>

    # 3) 発火判定。しきい値を超えた日だけ、モデルに火が入る
    scripts/distill.sh
NEXT
printf '\n'
ja "  用語の正典（訂正の昇格・人間定置網・判断ループ）: README.md の「訂正の昇格」節"
en "  Canonical definitions: the \"訂正の昇格 / Promotion of Corrections\" section of README.md"
ja "  この軽量レーンの設計       : docs/distillation-loop.md"
ja "  昇格したあとの監査         : docs/discipline-audit.md"
ja "  蒸留の全体機構             : docs/judgment-distillation.md"
printf '\n'

if [[ "${DEMO_KEEP:-0}" = "1" ]]; then
  ja "サンドボックスは残しました（DEMO_KEEP=1）。中を覗いてください:"
  en "Sandbox kept (DEMO_KEEP=1). Everything the demo made is in here:"
  ja "  $SANDBOX"
else
  ja "サンドボックスはこの行の直後に消えます。あなたのディスクは1バイトも変わっていません。"
  en "The sandbox is deleted on exit. Not one byte of your disk changed."
  ja "  中を見たいときは: DEMO_KEEP=1 ./scripts/demo-distillation.sh"
fi
printf '\n'
exit 0
