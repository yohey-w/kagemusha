#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# B. setup.sh smoke — run the real thing in a throwaway clone and assert the
# artifacts, not the exit code. "It didn't error" is not a green.
#
# Three properties, because these are the three ways a scaffolder hurts you:
#   1. it puts the right files in the right places (asserted as an EXACT set)
#   2. re-running it never touches a file you have already filled in
#      (proved twice over: content hashes AND mtimes)
#   3. an explicit target directory is honoured
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "B. setup.sh (real run in a throwaway clone)"

B_FX="$TEST_TMP/b_default"
kit_copy "$B_FX"

# ── 1. first run ───────────────────────────────────────────────────────────
B_LOG1="$TEST_TMP/b_run1.log"
"$B_FX/scripts/setup.sh" > "$B_LOG1" 2>&1; b_rc=$?
b_out="$(cat "$B_LOG1")"
assert_eq "B: setup.sh exits 0" "0" "$b_rc"
assert_nonempty_str "B: setup.sh prints what it did" "$b_out"

# the exact set of files that appeared, compared against a written-out manifest
b_expected="$(LC_ALL=C sort <<'MANIFEST'
CLAUDE.md
approval_queue.md
config.env
judgment/decisions_journal.md
judgment/judgment_model.md
judgment/promotion_queue.md
projects/_charter_template.md
ssot/decisions.md
ssot/glossary.md
ssot/people.md
ssot/tasks.md
system_map.md
verifiers.md
MANIFEST
)"
b_tracked="$(git -C "$REPO_ROOT" ls-files | LC_ALL=C sort)"
b_actual_all="$( (cd "$B_FX" && find . -type f | sed 's|^\./||') | LC_ALL=C sort)"
b_created="$(comm -13 <(printf '%s\n' "$b_tracked") <(printf '%s\n' "$b_actual_all"))"
assert_eq "B: exact set of files created" "$b_expected" "$b_created"

for d in ssot briefs logs local projects projects/_archive \
         judgment judgment/mining judgment/reports judgment/logs; do
  assert_dir "B: directory created: $d" "$B_FX/$d"
done

# every scaffolded file is a byte-for-byte copy of its template
assert_same "B: CLAUDE.md comes from templates/agent_instructions.md" \
  "$B_FX/CLAUDE.md" "$B_FX/templates/agent_instructions.md"
assert_same "B: ssot/decisions.md comes from templates/decisions.md" \
  "$B_FX/ssot/decisions.md" "$B_FX/templates/decisions.md"
assert_same "B: ssot/tasks.md comes from templates/tasks.md" \
  "$B_FX/ssot/tasks.md" "$B_FX/templates/tasks.md"
assert_same "B: ssot/glossary.md comes from templates/glossary.md" \
  "$B_FX/ssot/glossary.md" "$B_FX/templates/glossary.md"
assert_same "B: ssot/people.md comes from templates/people.md" \
  "$B_FX/ssot/people.md" "$B_FX/templates/people.md"
assert_same "B: approval_queue.md comes from its template" \
  "$B_FX/approval_queue.md" "$B_FX/templates/approval_queue.md"
assert_same "B: verifiers.md comes from its template" \
  "$B_FX/verifiers.md" "$B_FX/templates/verifiers.md"
assert_same "B: system_map.md comes from its template" \
  "$B_FX/system_map.md" "$B_FX/templates/system_map.md"
assert_same "B: judgment/decisions_journal.md comes from its template" \
  "$B_FX/judgment/decisions_journal.md" "$B_FX/templates/decisions_journal.md"
assert_same "B: judgment/judgment_model.md comes from its template" \
  "$B_FX/judgment/judgment_model.md" "$B_FX/templates/judgment_model.md"
assert_same "B: projects/_charter_template.md comes from templates/charter.md" \
  "$B_FX/projects/_charter_template.md" "$B_FX/templates/charter.md"
assert_same "B: config.env comes from config.env.example" \
  "$B_FX/config.env" "$B_FX/config.env.example"

# AGENTS.md is NOT created — Codex users rename CLAUDE.md themselves
assert_absent "B: AGENTS.md is not created" "$B_FX/AGENTS.md"

# The correction vocabulary is a MENU, not a default. Scaffolding it to the path
# the scanner reads would make a shipped list of phrases everyone's correction
# vocabulary without anyone having chosen it — and the scanner would start
# harvesting on words the user never uses. The exact-set manifest above already
# pins this; it is named here too because the failure it prevents is a
# behaviour, not a stray file, and a manifest line does not say why.
assert_absent "B: the correction-pattern menu is NOT activated by setup.sh" \
  "$B_FX/judgment/correction_patterns.txt"
assert_absent "B: …not under any other name either" "$B_FX/correction_patterns.txt"
assert_grep "B: instead setup.sh tells you to copy it and cut it down" \
  "correction_patterns.example.txt" "$B_LOG1"
# and the cron line it prints must carry --dir: cron's CWD is $HOME, so a line
# without it silently harvests the wrong project's logs (or none at all).
assert_grep "B: the printed scanner cron line names the log directory" \
  "--dir $HOME/.claude/projects/" "$B_LOG1"
assert_grep "B: first run reports creations" "create:" "$B_LOG1"

# ── 2. idempotency: your filled-in files survive a re-run ──────────────────
printf '\n<!-- SENTINEL: edited by the operator -->\n' >> "$B_FX/CLAUDE.md"
printf '\n- [ ] SENTINEL task\n' >> "$B_FX/ssot/tasks.md"
printf '\nSENTINEL_KEY=value\n' >> "$B_FX/config.env"

b_hashes_before="$(tree_hashes "$B_FX")"
b_mtimes_before="$(tree_mtimes "$B_FX")"
assert_nonempty_str "B: content snapshot taken (sha256 of every file)" "$b_hashes_before"
assert_nonempty_str "B: mtime snapshot taken (find -printf available)" "$b_mtimes_before"

sleep 1   # so that ANY rewrite would move the mtime into a different second

B_LOG2="$TEST_TMP/b_run2.log"
"$B_FX/scripts/setup.sh" > "$B_LOG2" 2>&1; b_rc2=$?
assert_eq "B: second run exits 0" "0" "$b_rc2"
assert_grep "B: second run says it skipped existing files" "skip (exists)" "$B_LOG2"
assert_no_grep "B: second run creates nothing" "create:" "$B_LOG2"

assert_eq "B: idempotent — no file content changed (sha256)" \
  "$b_hashes_before" "$(tree_hashes "$B_FX")"
assert_eq "B: idempotent — no file was rewritten (mtime)" \
  "$b_mtimes_before" "$(tree_mtimes "$B_FX")"
assert_grep "B: operator edit to CLAUDE.md survives" "SENTINEL: edited by the operator" "$B_FX/CLAUDE.md"
assert_grep "B: operator edit to ssot/tasks.md survives" "SENTINEL task" "$B_FX/ssot/tasks.md"
assert_grep "B: operator edit to config.env survives" "SENTINEL_KEY=value" "$B_FX/config.env"

# a pre-existing AGENTS.md must block CLAUDE.md creation (Codex users)
B_FX2="$TEST_TMP/b_agents"
kit_copy "$B_FX2"
printf 'my own codex instructions\n' > "$B_FX2/AGENTS.md"
"$B_FX2/scripts/setup.sh" > "$TEST_TMP/b_run3.log" 2>&1; b_rc3=$?
assert_eq "B: setup with pre-existing AGENTS.md exits 0" "0" "$b_rc3"
assert_absent "B: CLAUDE.md not created when AGENTS.md exists" "$B_FX2/CLAUDE.md"
assert_grep "B: existing AGENTS.md left untouched" "my own codex instructions" "$B_FX2/AGENTS.md"

# ── 3. explicit target directory ───────────────────────────────────────────
B_FX3="$TEST_TMP/b_kit"
B_TARGET="$TEST_TMP/b_elsewhere/work-loop"
kit_copy "$B_FX3"
B_LOG4="$TEST_TMP/b_run4.log"
"$B_FX3/scripts/setup.sh" "$B_TARGET" > "$B_LOG4" 2>&1; b_rc4=$?
assert_eq "B: setup.sh <target> exits 0" "0" "$b_rc4"
assert_file "B: <target>/ssot/decisions.md created" "$B_TARGET/ssot/decisions.md"
assert_file "B: <target>/CLAUDE.md created" "$B_TARGET/CLAUDE.md"
assert_file "B: <target>/system_map.md created" "$B_TARGET/system_map.md"
assert_dir  "B: <target>/judgment/mining created" "$B_TARGET/judgment/mining"
assert_absent "B: kit root NOT scaffolded when a target is given" "$B_FX3/ssot"
assert_absent "B: kit root gets no CLAUDE.md when a target is given" "$B_FX3/CLAUDE.md"
# config.env is the one exception: it lives next to the scripts that source it
assert_file "B: config.env still lands next to the scripts" "$B_FX3/config.env"
assert_grep "B: output names the target directory" "$B_TARGET" "$B_LOG4"
