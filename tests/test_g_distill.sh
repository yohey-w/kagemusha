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
#   · an exit code of 0 taken as proof the report is usable.
#
# Five more, added after an outside review. Every one of them loses a real
# correction SILENTLY — the board keeps looking healthy while the evidence goes
# on the floor, which is the failure this whole lane exists to prevent:
#   · dedup keyed on the WORDS instead of the log record, so the same short
#     correction said twice in one session is counted once;
#   · a batch trimmed to a line cap and then marked distilled in full, so the
#     OLDEST events are cut off the front and retired unread;
#   · an event harvested WHILE the model runs being retired by that run;
#   · the model holding write permission, which makes "only write the queue" a
#     request in a prompt rather than a boundary around it;
#   · a cron line with no --dir, harvesting a guessed directory forever.
#
# NO REAL AI CLI IS CALLED. AGENT_CMD points at a stub written here, or at
# `false`. Fixtures are synthetic JSONL written from fixed strings.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "G. distillation courier (harvest, threshold, batch, ratchet)"

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
python3 - "$G_LOGS" <<'PYFIX1'
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
PYFIX1

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
# A v1 state counted pending work as an integer, which cannot name the events a
# run actually read. Migrating it by guessing the ids is the bug, so it stops.
printf '{"version":1,"harvested":3,"distilled":0,"seen":[],"events":[]}\n' \
  > "$TEST_TMP/g_v1_state.json"
assert_exit "G4: an old-format state file stops the run instead of guessing ids" 2 \
  python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_MATERIAL" \
    --state "$TEST_TMP/g_v1_state.json" --dir "$G_LOGS"

# A quiet day is NOT an error here (unlike the discipline scanner, whose empty
# report would read as "every discipline is dead"). Nothing to harvest is a
# normal Sunday; the pending count simply does not move.
assert_ok "G5: a quiet day (dirs exist, nothing recent) exits 0" \
  python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$TEST_TMP/g_quiet.md" \
    --state "$TEST_TMP/g_quiet.json" --dir "$G_EMPTY"
assert_eq "G5: …and harvests nothing" "0" \
  "$(python3 "$G_SCAN" --state "$TEST_TMP/g_quiet.json" --status | sed -n 's/^pending=//p')"

# ── G5b. identity: a correction is a LOG RECORD, not a string ──────────────
# The same short correction ("やめて") said twice on different days inside one
# long-running session used to hash to one key, and the second one vanished. A
# dedup that eats real corrections is worse than no dedup, because it is silent.
G_ID_LOGS="$TEST_TMP/g_id_logs"; mkdir -p "$G_ID_LOGS"
python3 - "$G_ID_LOGS" <<'PYFIX2'
import json, os, sys, time
d = sys.argv[1]
base = (int(time.time()) - 10800) // 1200 * 1200
def ts(off): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(base + off))
def rec(kind, text, off):
    body = text if kind == "user" else [{"type": "text", "text": text}]
    return json.dumps({"type": kind, "timestamp": ts(off), "message": {"content": body}},
                      ensure_ascii=False)
# ONE session file, the SAME sentence, two hours apart: two corrections.
with open(os.path.join(d, "dddddddd-same.jsonl"), "w", encoding="utf-8") as f:
    f.write(rec("assistant", "案Aで進めます", 0) + "\n")
    f.write(rec("user", "やめて", 60) + "\n")
    f.write(rec("assistant", "案Bで進めます", 7200) + "\n")
    f.write(rec("user", "やめて", 7260) + "\n")
PYFIX2
G_ID_MAT="$TEST_TMP/g_id_material.md"; G_ID_STATE="$TEST_TMP/g_id_state.json"
g_id_scan() { python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_ID_MAT" \
                --state "$G_ID_STATE" --dir "$G_ID_LOGS" --since 7d; }
assert_ok "G5b: harvest a session that says the same short thing twice" g_id_scan
assert_eq "G5b: the same words on two different log records are TWO events" "2" \
  "$(python3 "$G_SCAN" --state "$G_ID_STATE" --status | sed -n 's/^pending=//p')"
assert_eq "G5b: …and both turns are quoted, not just the first" "2" \
  "$(grep -c '): やめて' "$G_ID_MAT")"
assert_ok "G5b: re-harvesting them is still idempotent" g_id_scan
assert_eq "G5b: …still two, not four" "2" \
  "$(python3 "$G_SCAN" --state "$G_ID_STATE" --status | sed -n 's/^pending=//p')"

# ── G5c. provenance: every quote can be reopened ───────────────────────────
# A 300-character quote attributed to "session a1b2c3d4" at minute resolution
# cannot be found again — and review is exactly where the surrounding turns are
# what decide whether a correction meant what it looks like it meant.
assert_file "G5c: a provenance index is written beside the material" \
  "$G_ID_MAT.index.jsonl"
assert_grep "G5c: …carrying the FULL session id, not an 8-char prefix" \
  "dddddddd-same" "$G_ID_MAT.index.jsonl"
assert_grep "G5c: …the line number inside the log file" '"line":' "$G_ID_MAT.index.jsonl"
assert_grep "G5c: …and a sha256 of the untruncated turn" '"sha256":' "$G_ID_MAT.index.jsonl"
assert_grep "G5c: the material tells the reader how to reopen an event" \
  "--show-event" "$G_ID_MAT"
g_evid="$(grep -oE 'E-[0-9a-f]{10}' "$G_ID_MAT" | tail -n 1)"
assert_nonempty_str "G5c: events carry a quotable id" "$g_evid"
python3 "$G_SCAN" --material "$G_ID_MAT" --show-event "$g_evid" --context 3 \
  > "$TEST_TMP/g_show.txt" 2>&1
g_show_rc=$?
assert_eq "G5c: --show-event exits 0" "0" "$g_show_rc"
assert_grep "G5c: …names the original log file and line" "dddddddd-same.jsonl:" \
  "$TEST_TMP/g_show.txt"
assert_grep "G5c: …prints the correction in full" "やめて" "$TEST_TMP/g_show.txt"
assert_grep "G5c: …and the turns around it, so the reason is recoverable" \
  "案B" "$TEST_TMP/g_show.txt"
assert_exit "G5c: an unknown event id is an error, not an empty page" 2 \
  python3 "$G_SCAN" --material "$G_ID_MAT" --show-event "E-0000000000"

# ── G5d. the log directory is never guessed silently ───────────────────────
# cron's working directory is $HOME, so a scanner that derives the log path from
# the CWD harvests another project — or nothing — forever, without a word.
python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$TEST_TMP/g_guess.md" \
  --state "$TEST_TMP/g_guess.json" > "$TEST_TMP/g_guess.out" 2>&1
assert_grep "G5d: with no --dir and no DISTILL_LOG_DIRS, the guess announces itself" \
  "GUESSING" "$TEST_TMP/g_guess.out"
env DISTILL_LOG_DIRS="$G_ID_LOGS" python3 "$G_SCAN" --patterns "$G_PATTERNS" \
  --material "$TEST_TMP/g_env.md" --state "$TEST_TMP/g_env.json" --since 7d \
  > "$TEST_TMP/g_env.out" 2>&1
assert_no_grep "G5d: DISTILL_LOG_DIRS is used instead of guessing" \
  "GUESSING" "$TEST_TMP/g_env.out"
assert_eq "G5d: …and the harvest really came from there" "2" \
  "$(python3 "$G_SCAN" --state "$TEST_TMP/g_env.json" --status | sed -n 's/^pending=//p')"

# ── the trigger ────────────────────────────────────────────────────────────
G_CFG="$TEST_TMP/g_config.env"

# write_g_cfg <agent_cmd> <threshold> <fallback_days>. The material/state pair,
# the principles file and the line cap come from G_CFG_* so a case can point the
# courier at its own fixture without a six-argument call. State and material
# always move TOGETHER: the state names event ids and the material's index is
# where those ids are rendered from, so a config that mixes one case's state
# with another's material describes a courier that cannot exist.
G_CFG_MATERIAL=""; G_CFG_STATE=""; G_CFG_PRINCIPLES=""; G_CFG_MAXLINES=""
write_g_cfg() {
  cat > "$G_CFG" <<CFG
PROJECT_ROOT="$G_DATA"
LOG_DIR="$G_LOGS_OUT"
AGENT_CMD="$1"
AGENT_MODEL=""
AGENT_FLAGS="--dangerously-skip-permissions"
AGENT_TIMEOUT=60
NTFY_ENABLED=0
NTFY_TOPIC=""
DISTILL_MATERIAL_FILE="${G_CFG_MATERIAL:-$G_MATERIAL}"
DISTILL_STATE_FILE="${G_CFG_STATE:-$G_STATE}"
DISTILL_QUEUE_FILE="$G_QUEUE"
DISTILL_BATCH_DIR="$G_BATCHES"
DISTILL_THRESHOLD=$2
DISTILL_FALLBACK_DAYS=$3
DISTILL_MAX_MATERIAL_LINES=${G_CFG_MAXLINES:-400}
DISTILL_RULES_FILE="$G_DATA/CLAUDE.md"
DISTILL_PRINCIPLES_FILE="$G_CFG_PRINCIPLES"
CFG
}
G_LOGS_OUT="$TEST_TMP/g_runlogs"
G_BATCHES="$TEST_TMP/g_batches"
mkdir -p "$G_LOGS_OUT" "$G_BATCHES"
G_CRONLOG="$G_LOGS_OUT/distill_cron.log"

# The stub agent. It has NO file tools in real life either — its whole output is
# stdout — so here it records argv, reads the event ids out of the prompt it was
# handed, and prints the two fenced blocks the wrapper parses.
G_STUB="$TEST_TMP/g_agent_stub.sh"
cat > "$G_STUB" <<'STUB'
#!/usr/bin/env bash
: > "$STUB_ARGS"
for a in "$@"; do printf '%s\n' "$a" >> "$STUB_ARGS"; done
ids="$(grep -oE 'E-[0-9a-f]{10}' "$STUB_ARGS" | sort -u | tr '\n' ' ')"
case "${STUB_MODE:-good}" in
  silent) ;;                                  # exits 0 having said nothing
  prose)  echo "I had a look and there was not much to say." ;;
  partial) first="$(printf '%s' "$ids" | tr ' ' '\n' | head -n 1)"
           printf '<<<QUEUE-SECTION>>>\n## stub run — 1 candidate\n<<<END-QUEUE-SECTION>>>\n'
           printf '<<<EVENT-DISPOSITION>>>\nprocessed: %s\nno_reason:\nrejected:\n<<<END-EVENT-DISPOSITION>>>\n' "$first" ;;
  invented)
           printf '<<<QUEUE-SECTION>>>\n## stub run — 1 candidate\n<<<END-QUEUE-SECTION>>>\n'
           printf '<<<EVENT-DISPOSITION>>>\nprocessed: %s E-ffffffffff\nno_reason:\nrejected:\n<<<END-EVENT-DISPOSITION>>>\n' "$ids" ;;
  midrun) # a new correction lands while this run is still going
           if [[ -n "${STUB_MIDRUN_CMD:-}" ]]; then eval "$STUB_MIDRUN_CMD" >/dev/null 2>&1; fi
           printf '<<<QUEUE-SECTION>>>\n## stub run — 1 candidate\n<<<END-QUEUE-SECTION>>>\n'
           printf '<<<EVENT-DISPOSITION>>>\nprocessed: %s\nno_reason:\nrejected:\n<<<END-EVENT-DISPOSITION>>>\n' "$ids" ;;
  *)       printf '<<<QUEUE-SECTION>>>\n## stub run — 1 candidate\n<<<END-QUEUE-SECTION>>>\n'
           printf '<<<EVENT-DISPOSITION>>>\nprocessed: %s\nno_reason:\nrejected:\n<<<END-EVENT-DISPOSITION>>>\n' "$ids" ;;
esac
exit "${STUB_EXIT:-0}"
STUB
chmod +x "$G_STUB"

g_run() {  # invoke the shipped script
  env LOOP_CONFIG="$G_CFG" STUB_ARGS="$G_ARGS" STUB_QUEUE="$G_QUEUE" \
      STUB_MODE="${G_STUB_MODE:-good}" STUB_EXIT="${G_STUB_EXIT:-0}" \
      STUB_MIDRUN_CMD="${G_MIDRUN_CMD:-}" \
      DISTILL_DRYRUN="${G_DRYRUN:-0}" \
      http_proxy="http://127.0.0.1:1" https_proxy="http://127.0.0.1:1" \
      "$G_DISTILL"
}

# ── case 1: below threshold → SKIPPED, silently, and no agent is invoked ────
G_ARGS="$TEST_TMP/g_args1.txt"
write_g_cfg "$G_STUB" 5 0
g_run > "$TEST_TMP/g_run1.out" 2>&1; g_rc1=$?
assert_eq "G6: below the threshold exits 0" "0" "$g_rc1"
assert_grep "G6: …and says SKIPPED" "SKIPPED" "$TEST_TMP/g_run1.out"
assert_grep "G6: …in the cron log too (a silent run still gets a line)" \
  "distill SKIPPED" "$G_CRONLOG"
assert_absent "G6: the model is never invoked below the threshold" "$TEST_TMP/g_args1.txt"
assert_eq "G6: pending is untouched" "2" "$(g_pending)"

# ── case 2: dry run past the threshold → the decision and the assembled prompt ─
G_ARGS="$TEST_TMP/g_args2.txt"; G_DRYRUN=1
write_g_cfg "$G_STUB" 2 0
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
assert_grep "G7: the batch is frozen and named before anything is sent" \
  "batch    : B-" "$TEST_TMP/g_run2.out"
assert_grep "G7: the queue is named as the wrapper's job, not the model's" \
  "written by THIS script" "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt tells the model it writes no files" "Write no files" \
  "$TEST_TMP/g_run2.out"
assert_grep "G7: the prompt names the rules file among what it cannot touch" \
  "$G_DATA/CLAUDE.md" "$TEST_TMP/g_run2.out"
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
assert_grep "G7: the prompt demands a receipt for every event in the batch" \
  "EVENT-DISPOSITION" "$TEST_TMP/g_run2.out"
assert_grep "G7: …and says the material is untrusted input, not instructions" \
  "untrusted input" "$TEST_TMP/g_run2.out"

# with a principles file configured, its text rides along for the conflict check
printf 'P1. Never send anything outward without asking.\n' > "$G_DATA/principles.md"
G_ARGS="$TEST_TMP/g_args2b.txt"; G_DRYRUN=1
G_CFG_PRINCIPLES="$G_DATA/principles.md"; write_g_cfg "$G_STUB" 2 0; G_CFG_PRINCIPLES=""
g_run > "$TEST_TMP/g_run2b.out" 2>&1
G_DRYRUN=0
assert_grep "G7: configured principles are pasted in for the conflict check" \
  "Never send anything outward without asking" "$TEST_TMP/g_run2b.out"

# ── case 3: the run fails → FAILED, and the material stays pending ──────────
G_ARGS="$TEST_TMP/g_args3.txt"; G_STUB_EXIT=9
write_g_cfg "$G_STUB" 2 0
g_run > "$TEST_TMP/g_run3.out" 2>&1; g_rc3=$?
G_STUB_EXIT=0
assert_eq "G8: a failing run propagates its exit code" "9" "$g_rc3"
assert_grep "G8: …is logged as FAILED, not as a quiet success" "distill FAILED" "$G_CRONLOG"
assert_grep "G8: …and says the ratchet did not advance" "ratchet NOT advanced" "$G_CRONLOG"
assert_eq "G8: the material is still pending after a failure" "2" "$(g_pending)"

# ── case 4: exit 0 but no usable report → still FAILED ─────────────────────
# The read-back moved: the model no longer writes anything, so "did the queue
# grow" would now only be checking our own append. What has to be checked is the
# REPORT — an exit code of 0 proves a process ended, nothing more.
for g_mode in silent prose; do
  G_ARGS="$TEST_TMP/g_args4_$g_mode.txt"; G_STUB_MODE="$g_mode"
  g_queue_before="$(wc -c < "$G_QUEUE" 2>/dev/null || echo 0)"
  g_run > "$TEST_TMP/g_run4_$g_mode.out" 2>&1; g_rc4=$?
  G_STUB_MODE=good
  assert_ne "G9[$g_mode]: exit 0 with no usable report is not a success" "0" "$g_rc4"
  assert_eq "G9[$g_mode]: …nothing was appended to the queue" \
    "$g_queue_before" "$(wc -c < "$G_QUEUE" 2>/dev/null || echo 0)"
  assert_eq "G9[$g_mode]: …and the material survives" "2" "$(g_pending)"
done
assert_grep "G9: the cron log names the validation failure" \
  "failed validation" "$G_CRONLOG"

# a report that covers only some of the batch, or names events that were never
# in it, is the same failure: the run cannot say it read what it was sent.
for g_mode in partial invented; do
  G_ARGS="$TEST_TMP/g_args4b_$g_mode.txt"; G_STUB_MODE="$g_mode"
  g_queue_before="$(wc -c < "$G_QUEUE" 2>/dev/null || echo 0)"
  g_run > "$TEST_TMP/g_run4b_$g_mode.out" 2>&1; g_rc4b=$?
  G_STUB_MODE=good
  assert_ne "G9b[$g_mode]: an unaccounted-for batch is not a success" "0" "$g_rc4b"
  assert_eq "G9b[$g_mode]: …the queue is untouched" \
    "$g_queue_before" "$(wc -c < "$G_QUEUE" 2>/dev/null || echo 0)"
  assert_eq "G9b[$g_mode]: …and no event is retired" "2" "$(g_pending)"
done

# ── case 4c: the model has no hands ────────────────────────────────────────
# The permission boundary is not the sentence in the prompt; it is the flags.
# AGENT_FLAGS (which carries --dangerously-skip-permissions for the scripts that
# need an agent with hands) must not reach this call. Its own fixture pair,
# because this case succeeds and would otherwise eat the material case 5 needs.
G_HANDS_LOGS="$TEST_TMP/g_hands_logs"; mkdir -p "$G_HANDS_LOGS"
python3 - "$G_HANDS_LOGS" <<'PYHANDS'
import json, os, sys, time
d = sys.argv[1]
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(time.time()) - 900))
with open(os.path.join(d, "hands0-session.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"type": "assistant", "timestamp": ts,
                        "message": {"content": [{"type": "text", "text": "案を出しました"}]}},
                       ensure_ascii=False) + "\n")
    f.write(json.dumps({"type": "user", "timestamp": ts,
                        "message": {"content": "そうじゃなくて HANDSEVENT を直して"}},
                       ensure_ascii=False) + "\n")
PYHANDS
G_HANDS_MAT="$G_DATA/hands_material.md"; G_HANDS_STATE="$G_DATA/hands_state.json"
assert_ok "G9c: harvest a fixture for the permission check" \
  python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_HANDS_MAT" \
    --state "$G_HANDS_STATE" --dir "$G_HANDS_LOGS" --since 7d
G_ARGS="$TEST_TMP/g_args4c.txt"; G_STUB_MODE=grabby
G_CFG_MATERIAL="$G_HANDS_MAT"; G_CFG_STATE="$G_HANDS_STATE"
write_g_cfg "$G_STUB" 1 0
g_run > "$TEST_TMP/g_run4c.out" 2>&1
G_STUB_MODE=good; G_CFG_MATERIAL=""; G_CFG_STATE=""
# The config it was given DOES carry the permission-skipping flag under
# AGENT_FLAGS — that is the point. What must never happen is that key reaching
# this invocation. (There is no assertion here about a model that writes anyway:
# a stub appending with a shell redirect proves nothing about CLI permissions,
# and pinning "the model wrote the queue" as an expected artefact would read to
# a future maintainer as an accepted outcome. The argv IS the boundary check.)
assert_grep "G9c: the config under test really does define the dangerous flag" \
  "AGENT_FLAGS=\"--dangerously-skip-permissions\"" "$G_CFG"
assert_no_grep "G9c: …and it never reaches the distilling call" \
  "dangerously-skip-permissions" "$TEST_TMP/g_args4c.txt"
assert_grep "G9c: what lands in the queue is the wrapper's validated append, with a batch id" \
  "batch B-" "$G_QUEUE"

# ── case 5: a real (stubbed) success → FIRED, ratchet advances exactly once ──
G_CFG_MATERIAL=""; G_CFG_STATE=""; G_CFG_MAXLINES=""
write_g_cfg "$G_STUB" 2 0
G_ARGS="$TEST_TMP/g_args5.txt"
g_run > "$TEST_TMP/g_run5.out" 2>&1; g_rc5=$?
assert_eq "G10: a successful run exits 0" "0" "$g_rc5"
assert_grep "G10: …is logged as FIRED" "distill FIRED" "$G_CRONLOG"
assert_file "G10: the model was invoked this time" "$TEST_TMP/g_args5.txt"
assert_eq "G10: …as: <cmd> -p <prompt>" "-p" "$(head -n 1 "$TEST_TMP/g_args5.txt" 2>/dev/null)"
assert_grep "G10: the candidate landed in the promotion queue" "stub run" "$G_QUEUE"
assert_eq "G10: pending resets only after a validated success" "0" "$(g_pending)"
assert_grep "G10: the material file records the distillation boundary" \
  "<!-- distilled through" "$G_MATERIAL"
assert_grep "G10: …naming the exact events that were retired" \
  "event(s): E-" "$G_MATERIAL"
assert_nonempty_str "G10: the batch manifest is kept as evidence of what was sent" \
  "$(find "$G_BATCHES" -name 'B-*.json' 2>/dev/null | head -n 1)"

# the next run has nothing left and must go quiet again
G_ARGS="$TEST_TMP/g_args6.txt"
g_run > "$TEST_TMP/g_run6.out" 2>&1
assert_grep "G10: with nothing pending it goes back to SKIPPED" "SKIPPED" "$TEST_TMP/g_run6.out"
assert_absent "G10: …and does not invoke the model" "$TEST_TMP/g_args6.txt"

# ── case 5b: the next batch carries only what came AFTER the last one ───────
# Without this, every run would re-send material already distilled: the reviewer
# would see the same correction proposed week after week, and its "confidence"
# would climb on nothing but re-reading.
python3 - "$G_LOGS" <<'PYFIX3'
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
PYFIX3
assert_ok "G10b: a new correction is harvested after the marker" g_scan
assert_eq "G10b: …and is the only thing pending" "1" "$(g_pending)"
G_ARGS="$TEST_TMP/g_args6b.txt"; G_DRYRUN=1
write_g_cfg "$G_STUB" 1 0
g_run > "$TEST_TMP/g_run6b.out" 2>&1
G_DRYRUN=0
assert_grep "G10b: the next prompt carries the new material" "FRESHBATCH" "$TEST_TMP/g_run6b.out"
assert_no_grep "G10b: …and not what was already distilled" \
  'そうじゃなくて、送る前に見せて' "$TEST_TMP/g_run6b.out"

# ── case 5c: the line cap DEFERS, it does not discard ──────────────────────
# The old build took the tail of the material file and then marked everything
# distilled. That retires exactly the events the cap cut off the FRONT — the
# ones that have been waiting longest — without them ever reaching a prompt.
G_CAP_LOGS="$TEST_TMP/g_cap_logs"; mkdir -p "$G_CAP_LOGS"
python3 - "$G_CAP_LOGS" <<'PYFIX4'
import json, os, sys, time
d = sys.argv[1]
base = (int(time.time()) - 86000) // 1200 * 1200
def ts(off): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(base + off))
# six separate sessions, one correction each = six events, oldest first
for i in range(6):
    with open(os.path.join(d, "cap%d-session.jsonl" % i), "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "assistant", "timestamp": ts(i * 3600),
                            "message": {"content": [{"type": "text", "text": "案 %d を出しました" % i}]}},
                           ensure_ascii=False) + "\n")
        f.write(json.dumps({"type": "user", "timestamp": ts(i * 3600 + 60),
                            "message": {"content": "そうじゃなくて CAPEVENT%d を直して" % i}},
                           ensure_ascii=False) + "\n")
PYFIX4
G_CAP_MAT="$G_DATA/cap_material.md"; G_CAP_STATE="$G_DATA/cap_state.json"
assert_ok "G10c: harvest six separate events" \
  python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_CAP_MAT" \
    --state "$G_CAP_STATE" --dir "$G_CAP_LOGS" --since 7d
assert_eq "G10c: …six pending" "6" \
  "$(python3 "$G_SCAN" --state "$G_CAP_STATE" --status | sed -n 's/^pending=//p')"
G_ARGS="$TEST_TMP/g_args6c.txt"
# a cap of 7 lines fits two three-line events, not six
G_CFG_MATERIAL="$G_CAP_MAT"; G_CFG_STATE="$G_CAP_STATE"; G_CFG_MAXLINES=7
write_g_cfg "$G_STUB" 1 0
g_run > "$TEST_TMP/g_run6c.out" 2>&1; g_rc6c=$?
assert_eq "G10c: the capped run succeeds" "0" "$g_rc6c"
assert_grep "G10c: …and says how many it deferred" "deferred" "$TEST_TMP/g_run6c.out"
g_cap_left="$(python3 "$G_SCAN" --state "$G_CAP_STATE" --status | sed -n 's/^pending=//p')"
assert_ne "G10c: the events that did not fit are NOT retired" "0" "$g_cap_left"
assert_grep "G10c: the OLDEST event is the one that went in (not the newest)" \
  "CAPEVENT0" "$TEST_TMP/g_args6c.txt"
assert_no_grep "G10c: …and the last one was left for next time" \
  "CAPEVENT5" "$TEST_TMP/g_args6c.txt"
# and the deferred ones do go out on the following run
G_ARGS="$TEST_TMP/g_args6c2.txt"
g_run > "$TEST_TMP/g_run6c2.out" 2>&1
assert_grep "G10c: the next run picks up where the cap stopped" \
  "CAPEVENT" "$TEST_TMP/g_args6c2.txt"

# ── case 5d: material harvested MID-RUN is not retired by that run ──────────
# The daily harvest and the distillation are two cron entries; they overlap. A
# ratchet that advances to "everything harvested" retires whatever landed while
# the model was thinking — a correction nobody has ever read, marked as read.
G_MID_LOGS="$TEST_TMP/g_mid_logs"; mkdir -p "$G_MID_LOGS"
python3 - "$G_MID_LOGS" <<'PYFIX5'
import json, os, sys, time
d = sys.argv[1]
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(time.time()) - 600))
with open(os.path.join(d, "mid0-session.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"type": "assistant", "timestamp": ts,
                        "message": {"content": [{"type": "text", "text": "最初の案です"}]}},
                       ensure_ascii=False) + "\n")
    f.write(json.dumps({"type": "user", "timestamp": ts,
                        "message": {"content": "そうじゃなくて FIRSTEVENT を直して"}},
                       ensure_ascii=False) + "\n")
PYFIX5
G_MID_MAT="$G_DATA/mid_material.md"; G_MID_STATE="$G_DATA/mid_state.json"
g_mid_scan() { python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_MID_MAT" \
                 --state "$G_MID_STATE" --dir "$G_MID_LOGS" --since 7d; }
assert_ok "G10d: one event is pending when the distillation starts" g_mid_scan
# the stub will harvest a SECOND event while it is "thinking"
cat > "$TEST_TMP/g_midrun_new.py" <<'PYFIX6'
import json, os, sys, time
d = sys.argv[1]
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(time.time()) - 60))
with open(os.path.join(d, "mid1-session.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"type": "assistant", "timestamp": ts,
                        "message": {"content": [{"type": "text", "text": "二番目の案です"}]}},
                       ensure_ascii=False) + "\n")
    f.write(json.dumps({"type": "user", "timestamp": ts,
                        "message": {"content": "そうじゃなくて LATEEVENT を直して"}},
                       ensure_ascii=False) + "\n")
PYFIX6
G_ARGS="$TEST_TMP/g_args6d.txt"; G_STUB_MODE=midrun
G_MIDRUN_CMD="python3 '$TEST_TMP/g_midrun_new.py' '$G_MID_LOGS' && python3 '$G_SCAN' --patterns '$G_PATTERNS' --material '$G_MID_MAT' --state '$G_MID_STATE' --dir '$G_MID_LOGS' --since 7d"
G_CFG_MATERIAL="$G_MID_MAT"; G_CFG_STATE="$G_MID_STATE"; G_CFG_MAXLINES=""
write_g_cfg "$G_STUB" 1 0
g_run > "$TEST_TMP/g_run6d.out" 2>&1; g_rc6d=$?
G_STUB_MODE=good; G_MIDRUN_CMD=""
assert_eq "G10d: the run succeeds" "0" "$g_rc6d"
assert_grep "G10d: the batch contained the event that was pending at freeze time" \
  "FIRSTEVENT" "$TEST_TMP/g_args6d.txt"
assert_no_grep "G10d: …and not the one that arrived mid-flight" \
  "LATEEVENT" "$TEST_TMP/g_args6d.txt"
assert_eq "G10d: the mid-flight correction is STILL pending, not silently retired" "1" \
  "$(python3 "$G_SCAN" --state "$G_MID_STATE" --status | sed -n 's/^pending=//p')"

# ── case 6: the time-based fallback is OFF unless you turned it on ──────────
# Firing because a week elapsed, on a single thin correction, is the exact
# failure the threshold exists to prevent — put on a timer. So: off by default,
# and a slow week gets NAMED rather than distilled.
# A real harvest, then its clock wound back nine days: the fallback is about
# elapsed time, and everything else about the fixture has to stay true.
G_FB_LOGS="$TEST_TMP/g_fb_logs"; mkdir -p "$G_FB_LOGS"
python3 - "$G_FB_LOGS" <<'PYFB'
import json, os, sys, time
d = sys.argv[1]
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(time.time()) - 1200))
with open(os.path.join(d, "fb0-session.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"type": "assistant", "timestamp": ts,
                        "message": {"content": [{"type": "text", "text": "案を出しました"}]}},
                       ensure_ascii=False) + "\n")
    f.write(json.dumps({"type": "user", "timestamp": ts,
                        "message": {"content": "そうじゃなくて SLOWWEEK を直して"}},
                       ensure_ascii=False) + "\n")
PYFB
G_FB_MAT="$G_DATA/fb_material.md"; G_FB_STATE="$G_DATA/fb_state.json"
assert_ok "G11: one lonely correction, harvested for real" \
  python3 "$G_SCAN" --patterns "$G_PATTERNS" --material "$G_FB_MAT" \
    --state "$G_FB_STATE" --dir "$G_FB_LOGS" --since 7d
g_age_state() {  # g_age_state <file> <days> — wind the clock back, keep the ids
  python3 -c "
import json,sys,datetime
p=sys.argv[1]; days=int(sys.argv[2])
st=json.load(open(p))
st['first_scan']=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=days)).isoformat(timespec='seconds')
st['last_distill']=None
json.dump(st, open(p,'w'))
" "$1" "$2"
}
g_age_state "$G_FB_STATE" 9
G_ARGS="$TEST_TMP/g_args7.txt"
G_CFG_MATERIAL="$G_FB_MAT"; G_CFG_STATE="$G_FB_STATE"
write_g_cfg "$G_STUB" 99 0      # fallback days = 0 = off (the default)
g_run > "$TEST_TMP/g_run7.out" 2>&1; g_rc7=$?
assert_eq "G11: an overdue light week with the fallback off exits 0" "0" "$g_rc7"
assert_grep "G11: …and is SKIPPED, not distilled on one thin correction" \
  "SKIPPED" "$TEST_TMP/g_run7.out"
assert_absent "G11: …the model is not fired" "$TEST_TMP/g_args7.txt"
assert_grep "G11: …but the waiting material is NAMED, not forgotten" \
  "have been waiting" "$TEST_TMP/g_run7.out"
assert_grep "G11: …and the cron log marks it stale" "STALE" "$G_CRONLOG"

# …and that reminder is configurable, not decorative. Same 9-day fixture, a
# 30-day bar: nothing has been waiting long enough to be worth mentioning.
G_ARGS="$TEST_TMP/g_args7s.txt"
write_g_cfg "$G_STUB" 99 0
printf 'DISTILL_STALE_DAYS=30\n' >> "$G_CFG"
g_run > "$TEST_TMP/g_run7s.out" 2>&1
assert_grep "G11: DISTILL_STALE_DAYS raises the bar — still skipped" \
  "SKIPPED" "$TEST_TMP/g_run7s.out"
assert_no_grep "G11: …and below the bar the reminder stays quiet (the key is read)" \
  "have been waiting" "$TEST_TMP/g_run7s.out"

# turned on explicitly, it still works exactly as before
G_ARGS="$TEST_TMP/g_args7b.txt"; G_DRYRUN=1
write_g_cfg "$G_STUB" 99 7
g_run > "$TEST_TMP/g_run7b.out" 2>&1
G_DRYRUN=0
assert_grep "G11: DISTILL_FALLBACK_DAYS=7 opts back in to firing on time" \
  "decision : FIRE — fallback" "$TEST_TMP/g_run7b.out"

# same overdue clock, zero pending: burning a model on an empty file is exactly
# what the threshold exists to prevent, so the fallback must NOT fire.
G_EMPTY_STATE="$TEST_TMP/g_empty_state.json"
python3 -c "
import json,sys,datetime
first=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=9)).isoformat(timespec='seconds')
json.dump({'version':2,'harvested':0,'distilled':0,'first_scan':first,'last_scan':None,
           'last_distill':None,'seen':[],'events':[],'pending_ids':[]}, open(sys.argv[1],'w'))
" "$G_EMPTY_STATE"
G_ARGS="$TEST_TMP/g_args8.txt"
G_CFG_STATE="$G_EMPTY_STATE"
write_g_cfg "$G_STUB" 99 7
g_run > "$TEST_TMP/g_run8.out" 2>&1; g_rc8=$?
assert_eq "G11: an empty week exits 0" "0" "$g_rc8"
assert_grep "G11: …and never fires on no material" "SKIPPED" "$TEST_TMP/g_run8.out"
assert_absent "G11: …with the model untouched" "$TEST_TMP/g_args8.txt"

# ── the standing guarantees ────────────────────────────────────────────────
assert_exit "G12: a missing config.env is a loud failure" 1 \
  env LOOP_CONFIG="$TEST_TMP/g_no_such.env" "$G_DISTILL"
g_all_args="$(cat "$TEST_TMP"/g_args*.txt 2>/dev/null || true)"
assert_empty_str "G12: the model was never asked to send, publish or push" \
  "$(printf '%s' "$g_all_args" | grep -iE 'curl |git push|ntfy\.sh' || true)"
assert_empty_str "G12: …and was never handed permission-skipping flags" \
  "$(printf '%s' "$g_all_args" | grep -iE 'dangerously-skip-permissions' || true)"
assert_grep "G12: the shipped prompt refuses to promote anything itself" \
  "a review is a person" "$G_KIT/templates/distill-prompt.md"
assert_grep "G12: …and refuses to write any file at all" \
  "Write no files" "$G_KIT/templates/distill-prompt.md"
assert_grep "G12: --mark-distilled cannot retire more than a named batch" \
  "requires --batch" "$G_KIT/scripts/correction_scan.py"

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
