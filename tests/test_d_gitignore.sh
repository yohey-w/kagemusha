#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# D. allowlist .gitignore — your instance data must be UNCOMMITTABLE, not
# merely "please remember not to commit it".
#
# The claim in the README is structural ("by construction"), so the test is
# structural: build a real repo from the kit, fill it with the exact files a
# live loop produces — SSOT, journal, briefs, secrets, the agent instructions
# — and assert git cannot see any of them. With a positive control, because a
# `git status` that reports nothing is also what a broken test looks like.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "D. allowlist .gitignore (instance data is uncommittable)"

D_FX="$TEST_TMP/d_clone"
kit_copy "$D_FX"
kit_git_init "$D_FX"

# the committed tree is exactly the kit — nothing more, nothing less
assert_eq "D: committed tree == the kit's tracked file list" \
  "$(git -C "$REPO_ROOT" ls-files | LC_ALL=C sort)" \
  "$(git -C "$D_FX" ls-files | LC_ALL=C sort)"
assert_empty_str "D: fresh clone is clean" "$(git -C "$D_FX" status --porcelain)"

# ── scaffold + a realistic day of instance data ────────────────────────────
"$D_FX/scripts/setup.sh" > "$TEST_TMP/d_setup.log" 2>&1
d_rc=$?
assert_eq "D: setup.sh inside the git clone exits 0" "0" "$d_rc"

D_INSTANCE=(
  "CLAUDE.md"
  "AGENTS.md"
  "system_map.md"
  "approval_queue.md"
  "verifiers.md"
  "config.env"
  "ssot/decisions.md"
  "ssot/tasks.md"
  "ssot/private_notes.md"
  "ssot/norms/writing.md"
  "ssot/norms/proposal.md"
  "judgment/decisions_journal.md"
  "judgment/judgment_model.md"
  "judgment/mining/lord_corpus.txt"
  "projects/acme/charter.md"
  "projects/_archive/old/charter.md"
  "briefs/2026-01-02.md"
  "briefs/2026-01-02.notify.txt"
  "logs/morning_brief_cron.log"
  "local/secrets/api_token"
  "local/scripts/watch.sh"
  "local/state/inbox.yaml"
  "scripts/weekly_distill.sh"
  "scripts/inbound_watch.sh"
)
for p in "${D_INSTANCE[@]}"; do
  mkdir -p "$(dirname "$D_FX/$p")"
  printf 'instance data — must never reach a commit\n' >> "$D_FX/$p"
done
# editor / python cruft inside the TRACKED directories
mkdir -p "$D_FX/scripts/__pycache__"
printf 'x' > "$D_FX/scripts/__pycache__/mine_conversations.cpython-312.pyc"
printf 'x' > "$D_FX/scripts/setup.sh.swp"
printf 'x' > "$D_FX/templates/charter.md~"
printf 'x' > "$D_FX/.DS_Store"

assert_empty_str "D: git sees NOTHING to commit after a full day of instance data" \
  "$(git -C "$D_FX" status --porcelain)"

# each file individually confirmed ignored — proves they exist and are ignored,
# rather than the loop above having quietly written nothing
d_unignored=""
for p in "${D_INSTANCE[@]}"; do
  [[ -f "$D_FX/$p" ]] || { d_unignored="${d_unignored}${p} (was never created!)"$'\n'; continue; }
  git -C "$D_FX" check-ignore -q "$p" || d_unignored="${d_unignored}${p}"$'\n'
done
assert_empty_str "D: every instance path is individually ignored" "$d_unignored"

# even with -A, and even forced onto the index, the working tree stays kit-only
assert_ok "D: git add -A succeeds" git -C "$D_FX" add -A
assert_eq "D: git add -A stages nothing new" \
  "$(git -C "$REPO_ROOT" ls-files | LC_ALL=C sort)" \
  "$(git -C "$D_FX" ls-files | LC_ALL=C sort)"

# ── positive control: the test CAN see a change when there is one ──────────
printf '\n<!-- ci positive control -->\n' >> "$D_FX/README.md"
printf 'new kit file\n' > "$D_FX/docs/newdoc.md"
# the cookbook shelf and the manifests dir are KIT, not instance data: the
# allowlist must let them through, or the two-layer split would be
# uncommittable by the same construction that protects ssot/ and judgment/.
mkdir -p "$D_FX/cookbook/author" "$D_FX/manifests"
printf 'a sample, deliberately tracked\n' > "$D_FX/cookbook/author/newsample.md"
printf 'templates/x.md\tx.md\tskip-if-exists\n' > "$D_FX/manifests/newmanifest.tsv"
# the norms shelf is the one hole in the allowlist, and it is exactly two files
# wide: the SHAPE (its README and the empty .example) is kit and must be
# committable; the ENTRIES — writing.md and any domain file a user adds — are
# instance data and were asserted invisible above. A hole nobody measured is a
# hole that widens, so both directions are asserted here.
printf '\n<!-- ci positive control -->\n' >> "$D_FX/ssot/norms/README.md"
git -C "$D_FX" status --porcelain > "$TEST_TMP/d_status.txt"
assert_grep "D: control — an edit to a tracked kit file IS reported" "README.md" "$TEST_TMP/d_status.txt"
assert_grep "D: control — a NEW file under docs/ IS reported" "docs/newdoc.md" "$TEST_TMP/d_status.txt"
assert_grep "D: a NEW file under cookbook/ IS committable (kit, not instance data)" \
  "cookbook/author/newsample.md" "$TEST_TMP/d_status.txt"
assert_grep "D: a NEW file under manifests/ IS committable" \
  "manifests/newmanifest.tsv" "$TEST_TMP/d_status.txt"
assert_grep "D: an edit to the tracked norms README IS reported (the shelf's shape is kit)" \
  "ssot/norms/README.md" "$TEST_TMP/d_status.txt"
assert_no_grep "D: a NEW domain file under ssot/norms/ is NOT committable (entries are instance data)" \
  "ssot/norms/proposal.md" "$TEST_TMP/d_status.txt"
assert_no_grep "D: the live norms entries are NOT committable" \
  "ssot/norms/writing.md" "$TEST_TMP/d_status.txt"
# and the shape really is tracked, rather than merely un-ignored
d_norms_untracked=""
for p in ssot/norms/README.md ssot/norms/writing.md.example; do
  git -C "$D_FX" ls-files --error-unmatch -- "$p" >/dev/null 2>&1 \
    || d_norms_untracked="${d_norms_untracked}${p}"$'\n'
done
assert_empty_str "D: the norms shelf's shape (README + .example) is tracked by git" "$d_norms_untracked"
