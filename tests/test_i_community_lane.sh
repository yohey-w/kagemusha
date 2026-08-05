#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# I. the community lane's path gate — measured on the SHIPPED workflow.
#
# The two community workflows decide, from a path string, whether a change is
# auto-merged with nobody reading it. That decision moved house
# (`community/` → `cookbook/community/`), and the failure mode of such a move
# is not "it breaks loudly": it is a gate that still says yes, on the wrong
# prefix, in silence.
#
# So this group does NOT restate the rule. It reads `COMMUNITY_ROOT`, the
# `SAFE_PATH` expression, and the removal workflow's `shelfSegment()` OUT OF
# the YAML that GitHub actually runs, evaluates them in node (the same engine
# actions/github-script uses), and drives a table through them. Re-typing the
# regex here would let the test go green while the workflow is wrong — which is
# precisely the class of bug this group exists for.
#
# What it CANNOT prove: that a real fork PR merges, that a symlink really lands
# in the adjudication lane, that the kill switch really stops a live run. Those
# need a live PR against the repository. This is the statically decidable half.
#
#   I1  the constants are single-sourced in the workflow (no second literal)
#   I2  the shipped SAFE_PATH + prefix rule accepts/rejects the right paths
#   I3  the removal workflow reads BOTH roots (migration window) and its
#       shelf-name extraction is not fooled by the new prefix
#   I4  the docs that tell people where to post agree with the workflow
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "I. community lane (path gate, read out of the shipped workflow)"

I_MERGE="$REPO_ROOT/.github/workflows/community-automerge.yml"
I_REMOVE="$REPO_ROOT/.github/workflows/community-remove.yml"

assert_file "I1: community-automerge.yml exists" "$I_MERGE"
assert_file "I1: community-remove.yml exists"    "$I_REMOVE"

# ─── I1. single source for the lane's location ─────────────────────────────
i_root_defs="$(grep -c "const COMMUNITY_ROOT = 'cookbook/community';" "$I_MERGE" || :)"
assert_eq "I1: automerge defines COMMUNITY_ROOT exactly once" 1 "$i_root_defs"

# the prefix and the shape check must both be BUILT from the constant, never
# re-typed — a second literal is how the two halves drift apart
assert_grep "I1: the prefix is built from COMMUNITY_ROOT" \
  'const prefix = `${COMMUNITY_ROOT}/${login.toLowerCase()}/`;' "$I_MERGE"
assert_grep "I1: SAFE_PATH is built from COMMUNITY_ROOT" \
  'const SAFE_PATH = new RegExp(' "$I_MERGE"
assert_no_grep "I1: no leftover hard-coded ^community/ regex in automerge" \
  '^community\/' "$I_MERGE"

# ─── I2. the shipped gate, driven through a table ──────────────────────────
# node, not a re-implementation: actions/github-script runs this same engine.
I_CASES="$TEST_TMP/i_cases.tsv"
node - "$I_MERGE" > "$I_CASES" <<'NODE'
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

const rootM = src.match(/const COMMUNITY_ROOT = '([^']+)';/);
const safeM = src.match(/const SAFE_PATH = new RegExp\(\s*([\s\S]*?)\);/);
if (!rootM || !safeM) {
  console.log('extract\tfail');
  process.exit(0);
}
console.log('extract\tok');
const COMMUNITY_ROOT = rootM[1];
const SAFE_PATH = new Function('COMMUNITY_ROOT', `return new RegExp(${safeM[1]});`)(COMMUNITY_ROOT);

// the three checks the workflow applies, in its order. The unsafe-path and
// prefix lines are stable one-liners; the two things that MOVED (the root and
// the shape) are the ones read out of the file above.
function inLane(p, login) {
  if (p.includes('..') || p.includes('\\') || p.startsWith('/')) return false;
  if (!SAFE_PATH.test(p)) return false;
  return p.toLowerCase().startsWith(`${COMMUNITY_ROOT}/${login.toLowerCase()}/`);
}

const table = [
  ['own shelf is in the lane',                 'cookbook/community/octocat/disciplines.md', 'octocat', true],
  ['login case is folded, not compared raw',   'cookbook/community/OctoCat/d.md',           'octocat', true],
  ["another person's shelf is out",            'cookbook/community/someone/d.md',           'octocat', false],
  ['the pre-split root community/ is OUT',     'community/octocat/d.md',                    'octocat', false],
  ['a nested subdirectory is out',             'cookbook/community/octocat/sub/d.md',       'octocat', false],
  ['a non-.md file is out',                    'cookbook/community/octocat/d.txt',          'octocat', false],
  ['a traversal segment is out',               'cookbook/community/octocat/../../x.md',     'octocat', false],
  ['a backslash path is out',                  'cookbook\\community\\octocat\\d.md',        'octocat', false],
  ['an absolute path is out',                  '/cookbook/community/octocat/d.md',          'octocat', false],
  ['the kit itself is out',                    'templates/starter-disciplines.md',          'octocat', false],
  ["the shelf's own README is out",            'cookbook/community/README.md',              'octocat', false],
  ['a lookalike root is out',                  'cookbook/community2/octocat/d.md',          'octocat', false],
];
for (const [name, path, login, want] of table) {
  console.log(`${name}\t${inLane(path, login) === want ? 'ok' : 'fail'}`);
}
NODE

i_n=0
while IFS=$'\t' read -r i_name i_res; do
  [[ -n "$i_name" ]] || continue
  i_n=$((i_n + 1))
  assert_eq "I2: $i_name" "ok" "$i_res"
done < "$I_CASES"
# the table must have actually run — an empty node output would otherwise be
# a silent zero-assertion pass
assert_ge "I2: the path table ran" "$i_n" 13

# ─── I3. the removal workflow: both roots, and the segment extraction ──────
assert_grep "I3: remove.yml names the live root" \
  "const COMMUNITY_ROOT = 'cookbook/community';" "$I_REMOVE"
assert_grep "I3: remove.yml names the pre-split root (migration window)" \
  "const LEGACY_ROOT = 'community';" "$I_REMOVE"
assert_grep "I3: the shell step searches both roots, hard-coded" \
  "for root in cookbook/community community; do" "$I_REMOVE"
assert_grep "I3: the shell step keeps the one-level search" \
  '-mindepth 1 -maxdepth 1' "$I_REMOVE"

I_SEG="$TEST_TMP/i_seg.tsv"
node - "$I_REMOVE" > "$I_SEG" <<'NODE'
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const fnM = src.match(/function shelfSegment\(p\) \{[\s\S]*?\n {12}\}/);
const newM = src.match(/const COMMUNITY_ROOT = '([^']+)';/);
const oldM = src.match(/const LEGACY_ROOT = '([^']+)';/);
if (!fnM || !newM || !oldM) {
  console.log('extract\tfail');
  process.exit(0);
}
console.log('extract\tok');
const shelfSegment = new Function(
  'COMMUNITY_ROOT', 'LEGACY_ROOT',
  `${fnM[0]}\nreturn shelfSegment;`)(newM[1], oldM[1]);

// The bug this table exists for: taking split('/')[1] BEFORE stripping the
// root reads 'community' as the shelf name of `cookbook/community/foo`, and a
// correct removal request is refused and closed as not_planned.
const table = [
  ['new form yields the login',        'cookbook/community/foo',        'foo'],
  ['new form never yields "community"','cookbook/community/foo',        'foo'],
  ['legacy form still works',          'community/foo',                 'foo'],
  ['new form with a trailing file',    'cookbook/community/foo/d.md',   'foo'],
  ['new-root placeholder is empty',    'cookbook/community/',           ''],
  ['legacy placeholder is empty',      'community/',                    ''],
  ['bare new root is empty',           'cookbook/community',            ''],
  ['bare legacy root is empty',        'community',                     ''],
  ['a README mention is not a shelf',  'cookbook/community/README.md',  'README.md'],
];
for (const [name, path, want] of table) {
  console.log(`${name}\t${shelfSegment(path) === want ? 'ok' : 'fail'}`);
}
NODE

i_m=0
while IFS=$'\t' read -r i_name i_res; do
  [[ -n "$i_name" ]] || continue
  i_m=$((i_m + 1))
  assert_eq "I3: $i_name" "ok" "$i_res"
done < "$I_SEG"
assert_ge "I3: the shelf-name table ran" "$i_m" 10

# ─── I4. the docs point at the same place the workflow does ────────────────
assert_grep "I4: the shelf README states it IS the submission path" \
  "ここが投稿先です" "$REPO_ROOT/cookbook/community/README.md"
assert_no_grep "I4: …and no longer says it is not yet live" \
  "まだ投稿先ではありません" "$REPO_ROOT/cookbook/community/README.md"
assert_grep "I4: the shelf README gives the new path in the fenced example" \
  "cookbook/community/<your GitHub login>/disciplines.md" \
  "$REPO_ROOT/cookbook/community/README.md"
assert_grep "I4: CONTRIBUTING names three places" \
  "three places, two kinds of review" "$REPO_ROOT/.github/CONTRIBUTING.md"
assert_grep "I4: CONTRIBUTING names three places (JA)" \
  "3つの置き場所・2つの審査" "$REPO_ROOT/.github/CONTRIBUTING.md"
assert_grep "I4: CONTRIBUTING's auto lane is the cookbook one" \
  "cookbook/community/<the PR author's own login>/<name>.md" \
  "$REPO_ROOT/.github/CONTRIBUTING.md"
assert_grep "I4: the PR template offers the cookbook/community box" \
  'cookbook/community/<my GitHub login>/*.md' \
  "$REPO_ROOT/.github/PULL_REQUEST_TEMPLATE.md"
assert_grep "I4: the removal issue template asks for the new path" \
  "cookbook/community/<your-login>/" \
  "$REPO_ROOT/.github/ISSUE_TEMPLATE/community-removal.md"
