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
AGENTS.md
CLAUDE.md
approval_queue.md
config.env
judgment/correction_patterns.txt
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
# CHANGED (Codex support): the instructions file is AGENTS.md, because that is
# the name Codex reads. CLAUDE.md is no longer a copy of anything — see below.
assert_same "B: AGENTS.md comes from templates/agent_instructions.md" \
  "$B_FX/AGENTS.md" "$B_FX/templates/agent_instructions.md"
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

# ── ONE instructions file, under two names ─────────────────────────────────
# CHANGED, deliberately. The old rule was "CLAUDE.md is written; a Codex user
# renames it by hand", asserted here as `AGENTS.md is not created`. A rename you
# have to remember is a rename half the users will not do, and the kit then
# ships instructions Codex never reads. So: AGENTS.md is the file, and CLAUDE.md
# is the single line `@AGENTS.md` — Claude Code's import, measured on 2.1.261
# (a marker put in AGENTS.md came back in the reply through that one line).
# Two files, one text, no fork.
assert_file "B: CLAUDE.md is created too" "$B_FX/CLAUDE.md"
assert_eq "B: …and it is exactly the one-line import of AGENTS.md" \
  "@AGENTS.md" "$(cat "$B_FX/CLAUDE.md")"
assert_ne "B: …so it is NOT a second copy of the instructions" \
  "$(cat "$B_FX/templates/agent_instructions.md")" "$(cat "$B_FX/CLAUDE.md")"

# ── every scaffolded file is EMPTY FORM, not somebody's content ────────────
# This is the property the two-layer split exists to guarantee, checked here on
# the actual output of the actual run rather than on the templates (H3 does the
# templates). A filled-in judgment arriving under the name of a scaffold is the
# failure; it would be adopted by default, by everyone, without anyone choosing.
assert_eq "B: the scaffolded judgment model has zero principles" \
  "0" "$(grep -cE '^[0-9]+\. \*\*' "$B_FX/judgment/judgment_model.md" || true)"
assert_eq "B: the scaffolded journal has zero dated events" \
  "0" "$(grep -cE '^### D-[0-9]{4}-' "$B_FX/judgment/decisions_journal.md" || true)"
assert_eq "B: the scaffolded approval queue has zero pending items" \
  "0" "$(grep -cE '^## Q-[0-9]{4}-' "$B_FX/approval_queue.md" || true)"
assert_eq "B: the scaffolded decisions SSOT has zero decisions" \
  "0" "$(grep -cE '^### D-[0-9]{4}-' "$B_FX/ssot/decisions.md" || true)"
assert_eq "B: the scaffolded verifiers has zero machine-layer rows" \
  "0" "$(grep -cE '^\| \*\*' "$B_FX/verifiers.md" || true)"
assert_eq "B: the scaffolded system map has zero project cards" \
  "0" "$(grep -cE '^### ' "$B_FX/system_map.md" || true)"

# The correction vocabulary is created, and created EMPTY. Shipping a list of
# phrases would make it everyone's correction vocabulary without anyone having
# chosen it, and the scanner would harvest on words the user never types. So the
# file exists (there is somewhere to write) with comments only, and the scanner
# refuses to run until the user fills it — the refusal is the forcing function.
assert_file "B: a correction-pattern file is created for you to fill in" \
  "$B_FX/judgment/correction_patterns.txt"
assert_eq "B: …containing ZERO patterns (comments only)" \
  "0" "$(grep -vcE '^[[:space:]]*(#|$)' "$B_FX/judgment/correction_patterns.txt" || true)"
assert_grep "B: …and saying why it is empty" \
  "NO PATTERNS" "$B_FX/judgment/correction_patterns.txt"
assert_absent "B: …and nothing is dropped at the repo root instead" \
  "$B_FX/correction_patterns.txt"
assert_grep "B: the run says so out loud" "write your own before the scanner runs" "$B_LOG1"
# the run must state, in its own words, that nothing from the sample shelf ran
assert_grep "B: the run declares that nothing from the sample shelf was used" \
  "was copied or activated" "$B_LOG1"
# and the cron line it prints must carry --dir: cron's CWD is $HOME, so a line
# without it silently harvests the wrong project's logs (or none at all).
assert_grep "B: the printed scanner cron line names the log directory" \
  "--dir $HOME/.claude/projects/" "$B_LOG1"
assert_grep "B: first run reports creations" "create:" "$B_LOG1"

# ── 2. idempotency: your filled-in files survive a re-run ──────────────────
printf '\n<!-- SENTINEL: edited by the operator -->\n' >> "$B_FX/CLAUDE.md"
printf '\n- [ ] SENTINEL task\n' >> "$B_FX/ssot/tasks.md"
printf '\nSENTINEL_KEY=value\n' >> "$B_FX/config.env"
printf '\nSENTINEL_PATTERN\n' >> "$B_FX/judgment/correction_patterns.txt"

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
assert_grep "B: the correction phrases you wrote survive a re-run" \
  "SENTINEL_PATTERN" "$B_FX/judgment/correction_patterns.txt"

# ── the rule is ASYMMETRIC, and both halves are checked ────────────────────
# CHANGED (Codex support). The asymmetry is the whole design: adding a pointer
# beside your file is safe, generating a second instructions file beside it is
# not. So AGENTS.md-only gets the pointer written for it, and CLAUDE.md-only
# gets nothing but a hint — because whatever is in that file is YOURS, and a
# template-generated AGENTS.md next to it would be a silent fork of your rules.

# (a) AGENTS.md only → the pointer is added, the file itself untouched
B_FX2="$TEST_TMP/b_agents"
kit_copy "$B_FX2"
printf 'my own codex instructions\n' > "$B_FX2/AGENTS.md"
"$B_FX2/scripts/setup.sh" > "$TEST_TMP/b_run3.log" 2>&1; b_rc3=$?
assert_eq "B: setup with pre-existing AGENTS.md exits 0" "0" "$b_rc3"
assert_grep "B: existing AGENTS.md left untouched" "my own codex instructions" "$B_FX2/AGENTS.md"
assert_eq "B: CLAUDE.md is created as the import when only AGENTS.md existed" \
  "@AGENTS.md" "$(cat "$B_FX2/CLAUDE.md")"

# (b) CLAUDE.md only → NOTHING is written, and the migration is printed
B_FX2B="$TEST_TMP/b_claude_only"
kit_copy "$B_FX2B"
printf 'my own claude instructions\n' > "$B_FX2B/CLAUDE.md"
"$B_FX2B/scripts/setup.sh" > "$TEST_TMP/b_run3b.log" 2>&1; b_rc3b=$?
assert_eq "B: setup with pre-existing CLAUDE.md exits 0" "0" "$b_rc3b"
assert_absent "B: AGENTS.md is NOT generated beside an existing CLAUDE.md" "$B_FX2B/AGENTS.md"
assert_grep "B: existing CLAUDE.md left untouched" "my own claude instructions" "$B_FX2B/CLAUDE.md"
assert_grep "B: …and the one-line migration is printed instead" \
  "mv $B_FX2B/CLAUDE.md $B_FX2B/AGENTS.md" "$TEST_TMP/b_run3b.log"

# (c) both present → neither is touched, nothing is created
B_FX2C="$TEST_TMP/b_both"
kit_copy "$B_FX2C"
printf 'mine\n' > "$B_FX2C/AGENTS.md"; printf 'also mine\n' > "$B_FX2C/CLAUDE.md"
"$B_FX2C/scripts/setup.sh" > "$TEST_TMP/b_run3c.log" 2>&1
assert_grep "B: both files present → AGENTS.md untouched" "mine" "$B_FX2C/AGENTS.md"
assert_grep "B: both files present → CLAUDE.md untouched" "also mine" "$B_FX2C/CLAUDE.md"

# ── 3. explicit target directory ───────────────────────────────────────────
B_FX3="$TEST_TMP/b_kit"
B_TARGET="$TEST_TMP/b_elsewhere/work-loop"
kit_copy "$B_FX3"
B_LOG4="$TEST_TMP/b_run4.log"
"$B_FX3/scripts/setup.sh" "$B_TARGET" > "$B_LOG4" 2>&1; b_rc4=$?
assert_eq "B: setup.sh <target> exits 0" "0" "$b_rc4"
assert_file "B: <target>/ssot/decisions.md created" "$B_TARGET/ssot/decisions.md"
assert_file "B: <target>/AGENTS.md created" "$B_TARGET/AGENTS.md"
assert_file "B: <target>/CLAUDE.md created" "$B_TARGET/CLAUDE.md"
assert_file "B: <target>/system_map.md created" "$B_TARGET/system_map.md"
assert_dir  "B: <target>/judgment/mining created" "$B_TARGET/judgment/mining"
# the kit itself ships ssot/norms/ (the norms shelf's SHAPE — README + the
# empty .example), so the directory existing at the kit root is no longer
# evidence that the scaffolder wrote there. The scaffolded FILES are.
assert_absent "B: kit root NOT scaffolded when a target is given" "$B_FX3/ssot/decisions.md"
assert_absent "B: …and no judgment/ tree at the kit root either" "$B_FX3/judgment"
assert_file "B: …while the shipped norms shelf is left untouched" "$B_FX3/ssot/norms/README.md"
assert_absent "B: kit root gets no CLAUDE.md when a target is given" "$B_FX3/CLAUDE.md"
assert_absent "B: kit root gets no AGENTS.md when a target is given" "$B_FX3/AGENTS.md"
# config.env is the one exception: it lives next to the scripts that source it
assert_file "B: config.env still lands next to the scripts" "$B_FX3/config.env"
assert_grep "B: output names the target directory" "$B_TARGET" "$B_LOG4"
