#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# G. distillation courier — scripts/correction_scan.py + scripts/distill.sh.
#
# The courier's whole value is a decision it makes without a human present:
# is there enough material to be worth firing a model at? Four ways that
# decision can silently go wrong are pinned here:
#   · counting repetitions as evidence (one point said four ways must be ONE
#     event, or a single complaint fires the threshold by itself and then
#     arrives at the reviewer looking like four witnesses);
#   · harvesting a subagent's turn as if it were the human's;
#   · a failed run counting as "distilled" — which drops the material on the
#     floor while the board still looks healthy;
#   · an exit code of 0 taken as proof the write happened.
#
# NO REAL AI CLI IS CALLED. AGENT_CMD points at a stub written here, or at
# `false`. Fixtures are synthetic JSONL written from fixed strings.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "G. distillation courier (harvest, threshold, ratchet)"

G_KIT="$TEST_TMP/g_kit"; kit_copy "$G_KIT"
G_SCAN="$G_KIT/scripts/correction_scan.py"
G_DISTILL="$G_KIT/scripts/distill.sh"
G_DATA="$TEST_TMP/g_data"
G_LOGS="$TEST_TMP/g_logs"          # fake session-log dir
G_EMPTY="$TEST_TMP/g_empty"        # log dir that exists but holds nothing
mkdir -p "$G_DATA" "$G_LOGS" "$G_EMPTY"

G_MATERIAL="$G_DATA/material.md"
G_STATE="$G_DATA/state.json"
G_QUEUE="$G_DATA/promotion_queue.md"
G_PATTERNS="$G_DATA/patterns.txt"

assert_file "G: scripts/correction_scan.py ships" "$G_SCAN"
assert_file "G: scripts/distill.sh ships" "$G_DISTILL"
assert_file "G: templates/distill-prompt.md ships" "$G_KIT/templates/distill-prompt.md"
assert_file "G: templates/promotion_queue.md ships" "$G_KIT/templates/promotion_queue.md"
assert_file "G: templates/correction_patterns.example.txt ships" \
  "$G_KIT/templates/correction_patterns.example.txt"
assert_file "G: docs/distillation-loop.md ships" "$G_KIT/docs/distillation-loop.md"

printf '%s\n' 'そうじゃなく' "\\bnot what i\\b" 'やめて' > "$G_PATTERNS"

# ── fixture: two sessions. Session one holds ONE correction said three ways
# inside a single time bucket; session two holds one more. A sidechain turn and
# a tool result carry the "user" role and must be ignored. ───────────────────
python3 - "$G_LOGS" <<'PY'
import json, os, sys, time
d = sys.argv[1]
base = (int(time.time()) - 3600) // 1200 * 1200        # 20-min bucket boundary
def ts(off): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(base + off))
def user(t, off, **kw):
    r = {"type": "user", "timestamp": ts(off), "message": {"content": t}}
    r.update(kw); return json.dumps(r, ensure_ascii=False)
def asst(t, off):
    return json.dumps({"type": "assistant", "timestamp": ts(off),
                       "message": {"content": [{"type": "text", "text": t}]}},
                      ensure_ascii=False)
with open(os.path.join(d, "aaaaaaaa-one.jsonl"), "w", encoding="utf-8") as f:
    f.write(asst("先方へメールを送信しました", 30) + "\n")
    f.write(user("そうじゃなくて、送る前に見せてほしい", 60) + "\n")
    f.write(user("やめて。送信は勝手にやらないで", 180) + "\n")
    f.write(user("そうじゃなくて、下書きで止めるってこと", 420) + "\n")
    f.write(user("SIDECHAIN そうじゃなくて別エージェントの発話", 300, isSidechain=True) + "\n")
    f.write(user("TOOLRESULT そうじゃなくて道具の出力", 300, toolUseResult={"x": 1}) + "\n")
    f.write(user("ありがとう、それでいい", 500) + "\n")
with open(os.path.join(d, "bbbbbbbb-two.jsonl"), "w", encoding="utf-8") as f:
    f.write(asst("I picked the second option because it is faster", 2900) + "\n")
    f.write(user("not what I asked for, I wanted the cheaper one", 3000) + "\n")
PY

g_scan() { python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_MATERIAL" \
             --state "$G_STATE" --dir "$G_LOGS" --since 7d "$@"; }
g_pending() { python3 "$G_SCAN" --state "$G_STATE" --status | sed -n 's/^pending=//p'; }

assert_ok "G1: the daily harvest runs" g_scan
assert_grep "G1: the correction text is in the material" 'そうじゃなくて、送る前に見せて' "$G_MATERIAL"
assert_grep "G1: …with what it was replying to (the rejected artifact)" \
  "in reply to:" "$G_MATERIAL"
assert_grep "G1: …and the English one from the other session" "not what I asked for" "$G_MATERIAL"
assert_grep "G1: the material says candidates are unjudged" "UNJUDGED" "$G_MATERIAL"

# THE COUNT: 4 matching human turns, but only 2 events (3 of them are one point
# restated inside one bucket). Counting 4 here is the pseudo-repetition bug.
assert_eq "G1: repetitions collapse into events (4 hits -> 2 events)" "2" "$(g_pending)"
assert_grep "G1: the folded turns are still all quoted, under one event" \
  '下書きで止める' "$G_MATERIAL"

assert_no_grep "G2: a subagent turn is not harvested as yours" "SIDECHAIN" "$G_MATERIAL"
assert_no_grep "G2: a tool result wearing the user role is not harvested" \
  "TOOLRESULT" "$G_MATERIAL"

assert_ok "G3: re-running the same day is harmless" g_scan
assert_eq "G3: …and does not double-count" "2" "$(g_pending)"

# ── the loud failures ──────────────────────────────────────────────────────
assert_exit "G4: no --patterns is an error (no built-in vocabulary)" 2 \
  python3 "$G_SCAN" --material "$G_MATERIAL" --state "$G_STATE" --dir "$G_LOGS"
: > "$TEST_TMP/g_empty_patterns.txt"
assert_exit "G4: an empty patterns file is an error, not a quiet week" 2 \
  python3 "$G_SCAN" --patterns "$TEST_TMP/g_empty_patterns.txt" --material "$G_MATERIAL" \
    --state "$G_STATE" --dir "$G_LOGS"
assert_exit "G4: a nonexistent log dir is an error" 2 \
  python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_MATERIAL" \
    --state "$G_STATE" --dir "$TEST_TMP/g_no_such_dir"
printf 'not json at all\n' > "$TEST_TMP/g_bad_state.json"
assert_exit "G4: a corrupt state file stops the run (never restarts at zero)" 2 \
  python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_MATERIAL" \
    --state "$TEST_TMP/g_bad_state.json" --dir "$G_LOGS"

# A quiet day is NOT an error here (unlike the discipline scanner, whose empty
# report would read as "every discipline is dead"). Nothing to harvest is a
# normal Sunday; the pending count simply does not move.
assert_ok "G5: a quiet day (dirs exist, nothing recent) exits 0" \
  python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$TEST_TMP/g_quiet.md" \
    --state "$TEST_TMP/g_quiet.json" --dir "$G_EMPTY"
assert_eq "G5: …and harvests nothing" "0" \
  "$(python3 "$G_SCAN" --state "$TEST_TMP/g_quiet.json" --status | sed -n 's/^pending=//p')"

# ── the trigger ────────────────────────────────────────────────────────────
G_CFG="$TEST_TMP/g_config.env"

write_g_cfg() {  # write_g_cfg <agent_cmd> <threshold> <fallback_days> [state] [principles]
  cat > "$G_CFG" <<CFG
PROJECT_ROOT="$G_DATA"
LOG_DIR="$G_LOGS_OUT"
AGENT_CMD="$1"
AGENT_MODEL=""
AGENT_FLAGS=""
AGENT_TIMEOUT=60
NTFY_ENABLED=0
NTFY_TOPIC=""
DISTILL_MATERIAL_FILE="$G_MATERIAL"
DISTILL_STATE_FILE="${4:-$G_STATE}"
DISTILL_QUEUE_FILE="$G_QUEUE"
DISTILL_THRESHOLD=$2
DISTILL_FALLBACK_DAYS=$3
DISTILL_RULES_FILE="$G_DATA/CLAUDE.md"
DISTILL_PRINCIPLES_FILE="${5:-}"
CFG
}
G_LOGS_OUT="$TEST_TMP/g_runlogs"
mkdir -p "$G_LOGS_OUT"
G_CRONLOG="$G_LOGS_OUT/distill_cron.log"

# the stub agent: records argv, appends to the promotion queue like the prompt says
G_STUB="$TEST_TMP/g_agent_stub.sh"
cat > "$G_STUB" <<'STUB'
#!/usr/bin/env bash
: > "$STUB_ARGS"
for a in "$@"; do printf '%s\n' "$a" >> "$STUB_ARGS"; done
if [[ "${STUB_WRITE:-1}" == "1" ]]; then
  printf '## stub run — 1 candidate\n' >> "$STUB_QUEUE"
fi
exit "${STUB_EXIT:-0}"
STUB
chmod +x "$G_STUB"

g_run() {  # g_run [env assignments...] — invoke the shipped script
  env LOOP_CONFIG="$G_CFG" STUB_ARGS="$G_ARGS" STUB_QUEUE="$G_QUEUE" \
      STUB_WRITE="${G_STUB_WRITE:-1}" STUB_EXIT="${G_STUB_EXIT:-0}" \
      DISTILL_DRYRUN="${G_DRYRUN:-0}" \
      http_proxy="http://127.0.0.1:1" https_proxy="http://127.0.0.1:1" \
      "$G_DISTILL"
}

# ── case 1: below threshold → SKIPPED, silently, and no agent is invoked ────
G_ARGS="$TEST_TMP/g_args1.txt"
write_g_cfg "$G_STUB" 5 7
g_run > "$TEST_TMP/g_run1.out" 2>&1; g_rc1=$?
assert_eq "G6: below the threshold exits 0" "0" "$g_rc1"
assert_grep "G6: …and says SKIPPED" "SKIPPED" "$TEST_TMP/g_run1.out"
assert_grep "G6: …in the cron log too (a silent run still gets a line)" \
  "distill SKIPPED" "$G_CRONLOG"
assert_absent "G6: the model is never invoked below the threshold" "$TEST_TMP/g_args1.txt"
assert_eq "G6: pending is untouched" "2" "$(g_pending)"

# ── case 2: dry run past the threshold → the decision and the assembled prompt ─
G_ARGS="$TEST_TMP/g_args2.txt"; G_DRYRUN=1
write_g_cfg "$G_STUB" 2 7
g_run > "$TEST_TMP/g_run2.out" 2>&1; g_rc2=$?
G_DRYRUN=0
assert_eq "G7: a dry run exits 0" "0" "$g_rc2"
assert_grep "G7: the decision is FIRE, with the reason" "decision : FIRE — threshold" \
  "$TEST_TMP/g_run2.out"
assert_grep "G7: the command is assembled but not run" "command  : $G_STUB -p <prompt>" \
  "$TEST_TMP/g_run2.out"
assert_absent "G7: …and the model really was not invoked" "$TEST_TMP/g_args2.txt"
assert_grep "G7: the prompt carries the harvested material" 'そうじゃなくて、送る前に見せて' \
  "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt names the queue as the only writable file" "$G_QUEUE" \
  "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt forbids editing the rules file" "$G_DATA/CLAUDE.md" \
  "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt bans inventing reasons" "Do not invent reasons" \
  "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt keeps repetitions from becoming witnesses" \
  "Count events, not repetitions" "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt demands verbatim evidence" "Never paraphrase" \
  "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt demands the counter-evidence field" "counter-evidence" \
  "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt demands a freshness date" "freshness" "$TEST_TMP/g_run2.out"
assert_grep "G7: conflicts are held, not resolved" "conflicts — held" "$TEST_TMP/g_run2.out"
assert_grep "G7: an unset principles file is declared, not silently skipped" \
  "no existing-principles file is configured" "$TEST_TMP/g_run2.out"

# with a principles file configured, its text rides along for the conflict check
printf 'P1. Never send anything outward without asking.\n' > "$G_DATA/principles.md"
G_ARGS="$TEST_TMP/g_args2b.txt"; G_DRYRUN=1
write_g_cfg "$G_STUB" 2 7 "$G_STATE" "$G_DATA/principles.md"
g_run > "$TEST_TMP/g_run2b.out" 2>&1
G_DRYRUN=0
assert_grep "G7: configured principles are pasted in for the conflict check" \
  "Never send anything outward without asking" "$TEST_TMP/g_run2b.out"

# ── case 3: the run fails → FAILED, and the material stays pending ──────────
G_ARGS="$TEST_TMP/g_args3.txt"; G_STUB_EXIT=9
write_g_cfg "$G_STUB" 2 7
g_run > "$TEST_TMP/g_run3.out" 2>&1; g_rc3=$?
G_STUB_EXIT=0
assert_eq "G8: a failing run propagates its exit code" "9" "$g_rc3"
assert_grep "G8: …is logged as FAILED, not as a quiet success" "distill FAILED" "$G_CRONLOG"
assert_grep "G8: …and says the ratchet did not advance" "ratchet NOT advanced" "$G_CRONLOG"
assert_eq "G8: the material is still pending after a failure" "2" "$(g_pending)"

# ── case 4: exit 0 but nothing written → still FAILED (read back the write) ──
G_ARGS="$TEST_TMP/g_args4.txt"; G_STUB_WRITE=0
g_run > "$TEST_TMP/g_run4.out" 2>&1; g_rc4=$?
G_STUB_WRITE=1
assert_ne "G9: exit 0 with no write does not count as success" "0" "$g_rc4"
assert_grep "G9: …the queue is read back and the miss is named" "did not grow" "$G_CRONLOG"
assert_eq "G9: pending survives a write that never happened" "2" "$(g_pending)"

# ── case 5: a real (stubbed) success → FIRED, ratchet advances exactly once ──
G_ARGS="$TEST_TMP/g_args5.txt"
g_run > "$TEST_TMP/g_run5.out" 2>&1; g_rc5=$?
assert_eq "G10: a successful run exits 0" "0" "$g_rc5"
assert_grep "G10: …is logged as FIRED" "distill FIRED" "$G_CRONLOG"
assert_file "G10: the model was invoked this time" "$TEST_TMP/g_args5.txt"
assert_eq "G10: …as: <cmd> -p <prompt>" "-p" "$(head -n 1 "$TEST_TMP/g_args5.txt" 2>/dev/null)"
assert_grep "G10: the candidate landed in the promotion queue" "stub run" "$G_QUEUE"
assert_eq "G10: pending resets only after a verified success" "0" "$(g_pending)"
assert_grep "G10: the material file records the distillation boundary" \
  "<!-- distilled through" "$G_MATERIAL"

# the next run has nothing left and must go quiet again
G_ARGS="$TEST_TMP/g_args6.txt"
g_run > "$TEST_TMP/g_run6.out" 2>&1
assert_grep "G10: with nothing pending it goes back to SKIPPED" "SKIPPED" "$TEST_TMP/g_run6.out"
assert_absent "G10: …and does not invoke the model" "$TEST_TMP/g_args6.txt"

# ── case 5b: the next batch carries only what came AFTER the marker ─────────
# Without this, every run would re-send material already distilled: the reviewer
# would see the same correction proposed week after week, and its "confidence"
# would climb on nothing but re-reading.
python3 - "$G_LOGS" <<'PY'
import json, os, sys, time
d = sys.argv[1]
now = int(time.time()) - 300
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
with open(os.path.join(d, "cccccccc-three.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"type": "assistant", "timestamp": ts,
                        "message": {"content": [{"type": "text", "text": "FRESHREPLY を書きました"}]}},
                       ensure_ascii=False) + "\n")
    f.write(json.dumps({"type": "user", "timestamp": ts,
                        "message": {"content": "そうじゃなくて FRESHBATCH のほうを直して"}},
                       ensure_ascii=False) + "\n")
PY
assert_ok "G10b: a new correction is harvested after the marker" g_scan
assert_eq "G10b: …and is the only thing pending" "1" "$(g_pending)"
G_ARGS="$TEST_TMP/g_args6b.txt"; G_DRYRUN=1
write_g_cfg "$G_STUB" 1 7
g_run > "$TEST_TMP/g_run6b.out" 2>&1
G_DRYRUN=0
assert_grep "G10b: the next prompt carries the new material" "FRESHBATCH" "$TEST_TMP/g_run6b.out"
assert_no_grep "G10b: …and not what was already distilled before the marker" \
  'そうじゃなくて、送る前に見せて' "$TEST_TMP/g_run6b.out"

# ── case 6: the weekly fallback — fires on a light week, never on an empty one ─
# A clock that started 9 days ago and has never fired, with 1 pending: due.
# (Note what is NOT here: a brand-new state whose clock has not started. "Never
# distilled" is not "overdue", and treating it as overdue made the fallback fire
# on day one of a fresh install — cancelling the threshold it exists to back up.)
G_FB_STATE="$TEST_TMP/g_fallback.json"
g_iso_days_ago() { python3 -c "import datetime,sys;print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=int(sys.argv[1]))).isoformat(timespec='seconds'))" "$1"; }
printf '{"version":1,"harvested":1,"distilled":0,"first_scan":"%s","last_scan":null,"last_distill":null,"seen":[],"events":[]}\n' \
  "$(g_iso_days_ago 9)" > "$G_FB_STATE"
G_ARGS="$TEST_TMP/g_args7.txt"; G_DRYRUN=1
write_g_cfg "$G_STUB" 99 7 "$G_FB_STATE"
g_run > "$TEST_TMP/g_run7.out" 2>&1
assert_grep "G11: a light week still fires via the fallback" "decision : FIRE — fallback" \
  "$TEST_TMP/g_run7.out"

# same overdue clock, zero pending: burning a model on an empty file is exactly
# what the threshold exists to prevent, so the fallback must NOT fire.
G_EMPTY_STATE="$TEST_TMP/g_empty_state.json"
printf '{"version":1,"harvested":0,"distilled":0,"first_scan":"%s","last_scan":null,"last_distill":null,"seen":[],"events":[]}\n' \
  "$(g_iso_days_ago 9)" > "$G_EMPTY_STATE"
G_ARGS="$TEST_TMP/g_args8.txt"
write_g_cfg "$G_STUB" 99 7 "$G_EMPTY_STATE"
g_run > "$TEST_TMP/g_run8.out" 2>&1; g_rc8=$?
G_DRYRUN=0
assert_eq "G11: an empty week exits 0" "0" "$g_rc8"
assert_grep "G11: …and never fires on no material" "SKIPPED" "$TEST_TMP/g_run8.out"

# ── the standing guarantees ────────────────────────────────────────────────
assert_exit "G12: a missing config.env is a loud failure" 1 \
  env LOOP_CONFIG="$TEST_TMP/g_no_such.env" "$G_DISTILL"
g_all_args="$(cat "$TEST_TMP"/g_args*.txt 2>/dev/null || true)"
assert_empty_str "G12: the model was never asked to send, publish or push" \
  "$(printf '%s' "$g_all_args" | grep -iE 'curl |git push|ntfy\.sh' || true)"
assert_grep "G12: the shipped prompt refuses to promote anything itself" \
  "a review is a person" "$G_KIT/templates/distill-prompt.md"

# The prompt is meant to be rewritten by its owner ("edit it; it is yours"), so
# the queue has to carry the shape too — otherwise the format survives only in
# the file users are invited to change. Both must name the same fields.
for g_field in type evidence scope exception confidence counter-evidence destination freshness; do
  assert_grep "G13: the prompt names the field '$g_field'" \
    "**$g_field:**" "$G_KIT/templates/distill-prompt.md"
  assert_grep "G13: the queue template shows the field '$g_field'" \
    "**$g_field:**" "$G_KIT/templates/promotion_queue.md"
done
assert_no_grep "G12: no correction vocabulary is baked into the scanner" \
  'そうじゃなく' "$G_SCAN"
