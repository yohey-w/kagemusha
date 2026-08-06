#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# J. the first ten minutes — scripts/demo-distillation.sh.
#
# The demo's entire promise is "no billing, no real logs, nothing dirtied", and
# a promise like that is worth exactly as much as the assertion behind it. So
# this group runs the shipped demo against a THROWAWAY CHECKOUT and pins four
# things a reader has to be able to trust without reading the script:
#   · the checkout it lives in is byte-identical before and after (it writes
#     only into its own mktemp sandbox);
#   · $HOME is untouched (no state, no cache, no config written behind you);
#   · no AI CLI is invoked — a fake `claude` / `codex` / `gemini` sits first on
#     PATH and records any call. Zero calls, or this group is red;
#   · it cannot hang: with no tty and no DEMO_FAST it still completes.
#
# And four things about the LOOP the demo claims to show, because a demo that
# narrates a loop it did not actually run is the exact failure this kit exists
# to prevent: the threshold really goes SKIPPED first, the courier really FIRES
# past it, the promoted rule really is NOT applied to CLAUDE.md, and the audit
# really finds the trace in the synthetic log.
#
# NO REAL AI CLI IS CALLED, here or by the demo. The demo's distiller is a stub
# wired in at AGENT_CMD — the same slot a real CLI sits in — so this group also
# asserts that nothing under scripts/ was patched to make the demo work.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "J. the first ten minutes (demo-distillation.sh)"

assert_file "J: scripts/demo-distillation.sh ships" "$REPO_ROOT/scripts/demo-distillation.sh"

# The demo runs against a throwaway copy of the tracked files, so "did it write
# to the repo" is measurable directly instead of by inspection.
J_KIT="$TEST_TMP/j_kit"; kit_copy "$J_KIT"
J_DEMO="$J_KIT/scripts/demo-distillation.sh"
J_HOME="$TEST_TMP/j_home"; mkdir -p "$J_HOME"
J_BIN="$TEST_TMP/j_bin";  mkdir -p "$J_BIN"
J_CALLED="$TEST_TMP/j_ai_cli_calls.txt"

# A fake AI CLI under every name this kit's docs suggest for AGENT_CMD. If the
# demo ever reaches for a model, the call lands here and leaves a file.
for j_cli in claude codex gemini llm; do
  cat > "$J_BIN/$j_cli" <<'JCLI'
#!/usr/bin/env bash
printf '%s %s\n' "$0" "$*" >> "$AI_CLI_CALLS"
exit 1
JCLI
  chmod +x "$J_BIN/$j_cli"
done

j_demo_run() {  # j_demo_run OUTFILE [extra env assignments...]
  local out="$1"; shift
  env HOME="$J_HOME" PATH="$J_BIN:$PATH" AI_CLI_CALLS="$J_CALLED" \
      NO_COLOR=1 TMPDIR="$TEST_TMP" \
      http_proxy="http://127.0.0.1:1" https_proxy="http://127.0.0.1:1" \
      "$@" timeout 180 "$J_DEMO" > "$out" 2>&1 < /dev/null
}

J_TREE_BEFORE="$TEST_TMP/j_tree_before.txt"
J_TREE_AFTER="$TEST_TMP/j_tree_after.txt"
tree_hashes "$J_KIT" > "$J_TREE_BEFORE"

J_OUT="$TEST_TMP/j_run.out"
j_demo_run "$J_OUT" DEMO_FAST=1 DEMO_KEEP=1; J_RC=$?
tree_hashes "$J_KIT" > "$J_TREE_AFTER"

assert_eq "J1: DEMO_FAST=1 runs start to finish and exits 0" "0" "$J_RC"

# ─── J2. the promise: nothing outside the sandbox ──────────────────────────
assert_same "J2: the checkout it lives in is byte-identical afterwards" \
  "$J_TREE_BEFORE" "$J_TREE_AFTER"
assert_empty_str "J2: \$HOME is untouched (no state, cache or config written)" \
  "$(find "$J_HOME" -mindepth 1 2>/dev/null)"
assert_absent "J2: no AI CLI is invoked — the run costs nothing" "$J_CALLED"

J_SANDBOX="$(sed -n 's/^ *作業場 \/ sandbox : //p' "$J_OUT" | head -n 1)"
assert_nonempty_str "J2: the sandbox path is announced up front" "$J_SANDBOX"
assert_dir "J2: …and DEMO_KEEP=1 leaves it there to poke at" "$J_SANDBOX"

# ─── J3. the threshold really is a threshold ───────────────────────────────
assert_grep "J3: the harvest folds restatements into events" "new_events=3" "$J_OUT"
assert_grep "J3: below the threshold the courier goes SKIPPED" \
  "distill: SKIPPED" "$J_OUT"
assert_grep "J3: …and says what it was waiting for" "threshold 5" "$J_OUT"
assert_grep "J4: past the threshold it FIRES" "distill: FIRED" "$J_OUT"
assert_grep "J4: …on the material, naming the count" "6 >= 5" "$J_OUT"
assert_nonempty_str "J4: the batch was frozen before the call" \
  "$(find "$J_SANDBOX/batches" -name 'B-*.json' 2>/dev/null | head -n 1)"

# ─── J5. what reaches the reviewer ─────────────────────────────────────────
J_QUEUE="$J_SANDBOX/data/promotion_queue.md"
assert_file "J5: a promotion queue is written (by the wrapper, not the model)" "$J_QUEUE"
assert_grep "J5: it carries a promotion candidate" "### C-" "$J_QUEUE"
assert_grep "J5: …stamped with the batch it came from" "batch B-" "$J_QUEUE"
assert_grep "J5: …with verbatim evidence, not a bare rule line" "**evidence:**" "$J_QUEUE"
assert_grep "J5: …with counter-evidence" "**counter-evidence:**" "$J_QUEUE"
assert_grep "J5: …with an expiry" "**freshness:**" "$J_QUEUE"
assert_grep "J5: an event with no reason on record is parked, not invented" \
  "no_reason として処分を記録した" "$J_QUEUE"

# ─── J6. diff by machine, application by human ─────────────────────────────
J_RULES="$J_SANDBOX/data/CLAUDE.md"
J_PROPOSED="$J_SANDBOX/data/CLAUDE.md.proposed"
assert_file "J6: the proposal file is generated" "$J_PROPOSED"
assert_grep "J6: the promoted rule is IN the proposal" \
  "金額を出すときは、税込の総額を先に書く" "$J_PROPOSED"
assert_no_grep "J6: …and is NOT applied to the instructions file" \
  "金額を出すときは、税込の総額を先に書く" "$J_RULES"
assert_grep "J6: the diff is shown on screen as an addition" \
  "+- 金額を出すときは、税込の総額を先に書く" "$J_OUT"
assert_grep "J6: the promoted line carries its provenance and expiry" \
  "〔昇格: C-" "$J_PROPOSED"
assert_grep "J6: the gate is named in the canon's own words" \
  "移動には関門は要らない。昇格には要る。" "$J_OUT"

# ─── J7. the circle closes: the audit finds the trace ──────────────────────
assert_grep "J7: the audit finds the promoted rule firing after promotion" \
  "[FIRE]" "$J_OUT"
assert_grep "J7: …and the breach from before it" "[BREACH]" "$J_OUT"
assert_grep "J7: a prohibition is never called a dead letter" \
  "Trace disciplines with zero firing candidates: none" "$J_OUT"

# ─── J8. the handover to the reader's own logs ─────────────────────────────
assert_grep "J8: the next step names the harvester" "correction_scan.py" "$J_OUT"
assert_grep "J8: …the courier" "scripts/distill.sh" "$J_OUT"
assert_grep "J8: …and where the vocabulary comes from" \
  "templates/correction_patterns.example.txt" "$J_OUT"
assert_grep "J8: …and points at the canonical definitions" "訂正の昇格" "$J_OUT"

# ─── J9. the stub sits where a real CLI sits — no script was patched ───────
assert_grep "J9: the stub distiller is wired in at AGENT_CMD" \
  "AGENT_CMD=\"$J_SANDBOX/stub-distiller.sh\"" "$J_SANDBOX/config.env"
assert_grep "J9: …with notifications off, so the run touches no network" \
  "NTFY_ENABLED=0" "$J_SANDBOX/config.env"

# ─── J10. it cleans up, and it cannot hang ─────────────────────────────────
J_OUT2="$TEST_TMP/j_run2.out"
j_demo_run "$J_OUT2" DEMO_FAST=1; J_RC2=$?
J_SANDBOX2="$(sed -n 's/^ *作業場 \/ sandbox : //p' "$J_OUT2" | head -n 1)"
assert_eq "J10: a second run (no DEMO_KEEP) exits 0" "0" "$J_RC2"
assert_nonempty_str "J10: …announced its own fresh sandbox" "$J_SANDBOX2"
assert_absent "J10: …and deleted it on the way out" "$J_SANDBOX2"

# No DEMO_FAST, no tty: the read prompts must not be reached, or an unattended
# run (CI, a pipe, a cron) blocks forever and looks like a hung test.
J_OUT3="$TEST_TMP/j_run3.out"
j_demo_run "$J_OUT3"; J_RC3=$?
assert_eq "J10: with no tty and no DEMO_FAST it still completes (never blocks)" \
  "0" "$J_RC3"
assert_grep "J10: …and still reached the end" "次はあなたの実ログで" "$J_OUT3"
