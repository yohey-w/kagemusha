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
#   I5  the guards on WHAT is readable at all: the credential/NFKC/control
#       rules are extracted and executed; the structural ones (file mode via
#       the tree API, UTF-8 round trip, kill switch) can only be asserted as
#       present, and are labelled that way rather than implied to be exercised
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

# ─── I6. how the take-down lane is woken, and once ─────────────────────────
# Three defects found by driving a real removal issue through the shipped
# workflow (2026-08-05, issue #4 / PRs #5 and #6 on this repository). All three
# are trigger-and-idempotence properties, none of which the path tables above
# can see.

# (a) the lane must not depend on a repository object a fork does not have.
# A label is not carried by a clone or a fork, and an issue template cannot
# apply a label that does not exist — so a label-only trigger is a dead lane in
# every fork. The second door is a marker that travels inside the template file.
assert_grep "I6: the trigger admits the template's body marker" \
  "contains(github.event.issue.body, 'kagemusha:community-removal')" "$I_REMOVE"
assert_grep "I6: the issue template carries that marker" \
  "kagemusha:community-removal" "$REPO_ROOT/.github/ISSUE_TEMPLATE/community-removal.md"
# …and the label door still works when a maintainer adds the label LATER
assert_grep "I6: a later label still starts the lane" \
  "github.event.label.name == 'community-removal'" "$I_REMOVE"
assert_grep "I6: the template still asks for the label up front" \
  "labels: community-removal" "$REPO_ROOT/.github/ISSUE_TEMPLATE/community-removal.md"
# the label is made to exist rather than assumed to (issues: write is held here)
assert_grep "I6: the workflow creates the label when it is missing" \
  "await github.rest.issues.createLabel({" "$I_REMOVE"
assert_grep "I6: …and it holds the scope that allows it" "issues: write" "$I_REMOVE"

# (b) one filing raises `opened` AND `labeled`. Serialising them is not enough:
# for an `issues` event `github.sha` is the default branch AS OF THE EVENT, so
# the second run checked out a tree still containing the shelf and opened a
# second deletion PR from the same branch name.
assert_grep "I6: the checkout takes the live tip, not the event's SHA" \
  'ref: ${{ github.event.repository.default_branch }}' "$I_REMOVE"
assert_grep "I6: a prior PR from this issue's branch makes the run a no-op" \
  'gh pr list --state all --head "$branch"' "$I_REMOVE"
assert_grep "I6: …and the query fails CLOSED if it cannot be answered" \
  'refusing to act without knowing' "$I_REMOVE"
# the guard has to sit BEFORE the "nothing found" exit, or the echo run leaves
# through that door instead and the guard never runs
i_branch_line="$(grep -n 'branch="community-removal' "$I_REMOVE" | head -n 1 | cut -d: -f1)"
i_absent_line="$(grep -n 'state=absent' "$I_REMOVE" | head -n 1 | cut -d: -f1)"
i_guard_line="$(grep -n 'state=duplicate' "$I_REMOVE" | head -n 1 | cut -d: -f1)"
i_before() {  # i_before NAME EARLIER LATER — both must exist and be ordered
  if [[ -n "$2" && -n "$3" && "$2" -lt "$3" ]]; then
    assert_eq "$1" "ok" "ok"
  else
    assert_eq "$1" "ok" "line ${2:-?} is not before line ${3:-?}"
  fi
}
i_before "I6: the branch name is computed before the absent exit" \
  "$i_branch_line" "$i_absent_line"
i_before "I6: the duplicate guard runs before the absent exit" \
  "$i_guard_line" "$i_absent_line"
# and the echo run must not speak: reporting "nothing was removed" would close
# the issue as not_planned over the completed the real run had just set
assert_grep "I6: the duplicate run posts no comment and closes nothing" \
  "steps.rm.outputs.state != 'duplicate'" "$I_REMOVE"

# (c) the shipped template, driven through the shipped claim parser. The
# template used to print `cookbook/community/octocat/` as a worked example;
# the workflow reads the body RAW (an HTML comment is not a hiding place), so
# that example is claimed as a shelf, fails the ownership check, and closes a
# CORRECT request as not_planned. The rule is therefore mechanical: the
# template must yield ZERO login-shaped shelf claims.
I_TMPL="$TEST_TMP/i_tmpl.tsv"
node - "$I_REMOVE" "$REPO_ROOT/.github/ISSUE_TEMPLATE/community-removal.md" > "$I_TMPL" <<'NODE'
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const body = fs.readFileSync(process.argv[3], 'utf8');

const claimM = src.match(/const CLAIM_RE = (\/.*\/g);/);
const loginM = src.match(/const LOGIN_RE = (\/.*\/);/);
const fnM = src.match(/function shelfSegment\(p\) \{[\s\S]*?\n {12}\}/);
const newM = src.match(/const COMMUNITY_ROOT = '([^']+)';/);
const oldM = src.match(/const LEGACY_ROOT = '([^']+)';/);
if (!claimM || !loginM || !fnM || !newM || !oldM) { console.log('extract\tfail'); process.exit(0); }
console.log('extract\tok');
const CLAIM_RE = new Function(`return ${claimM[1]};`)();
const LOGIN_RE = new Function(`return ${loginM[1]};`)();
const shelfSegment = new Function(
  'COMMUNITY_ROOT', 'LEGACY_ROOT',
  `${fnM[0]}\nreturn shelfSegment;`)(newM[1], oldM[1]);

const segments = [...body.matchAll(CLAIM_RE)].map((m) => shelfSegment(m[0]));
const shelves = segments.filter((s) => LOGIN_RE.test(s));

console.log(`the template claims at least one path\t${segments.length > 0 ? 'ok' : 'fail'}`);
console.log(`no claimed path is a login-shaped shelf\t${shelves.length === 0 ? 'ok' : `fail (${shelves.join(',')})`}`);
// the marker must survive the same parser: a marker that looked like a path
// would be the very bug this test exists for
console.log(`the wake-up marker is not itself a claim\t${
  [...'kagemusha:community-removal'.matchAll(CLAIM_RE)].length === 0 ? 'ok' : 'fail'}`);
// the placeholder is still THERE — "zero claims" must not be reached by
// deleting the instructions that tell the filer what to write
console.log(`the placeholder line is still present\t${
  body.includes('cookbook/community/<your-login>/') ? 'ok' : 'fail'}`);
// a filer who does replace it produces exactly one shelf, their own
const filled = body.replace(/<your-login>/g, 'octocat');
const filledShelves = [...filled.matchAll(CLAIM_RE)]
  .map((m) => shelfSegment(m[0])).filter((s) => LOGIN_RE.test(s));
console.log(`a filled-in template yields exactly one shelf\t${
  new Set(filledShelves).size === 1 && filledShelves[0] === 'octocat' ? 'ok' : 'fail'}`);
NODE

i_t=0
while IFS=$'\t' read -r i_name i_res; do
  [[ -n "$i_name" ]] || continue
  i_t=$((i_t + 1))
  assert_eq "I6: $i_name" "ok" "$i_res"
done < "$I_TMPL"
assert_ge "I6: the template table ran" "$i_t" 6

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

# ─── I5. the guards that decide what is even readable ──────────────────────
# Same principle as I2: the rule table is EXTRACTED and executed, not restated.
# The structural guards (mode, UTF-8, kill switch) cannot be executed without a
# live PR, so those are asserted as present-and-in-the-right-order instead —
# and this file says so out loud rather than implying they were exercised.
assert_grep "I5: the kill switch is wired to a repository variable" \
  'COMMUNITY_AUTOMERGE_ENABLED: ${{ vars.COMMUNITY_AUTOMERGE_ENABLED }}' "$I_MERGE"
assert_grep "I5: …and off is the default (anything but \"true\" stops the lane)" \
  "if (process.env.COMMUNITY_AUTOMERGE_ENABLED !== 'true') {" "$I_MERGE"
assert_grep "I5: symlink mode is refused" "e.mode === '120000'" "$I_MERGE"
assert_grep "I5: submodule mode/type is refused" \
  "e.mode === '160000' || e.type === 'commit'" "$I_MERGE"
assert_grep "I5: modes come from the tree API, not a checkout" \
  "github.rest.git.getTree({ owner: root.owner, repo: root.repo, tree_sha: sha })" "$I_MERGE"
assert_no_grep "I5: the mode read never uses a truncatable recursive tree" \
  "recursive: true" "$I_MERGE"
assert_grep "I5: an unreadable head tree fails CLOSED (to the maintainer)" \
  "await adminLane('could not read the head tree" "$I_MERGE"
assert_grep "I5: UTF-8 is decided by a byte round trip" \
  "Buffer.compare(Buffer.from(content, 'utf8'), raw) !== 0" "$I_MERGE"
assert_grep "I5: every text rule is re-run on the NFKC normalisation" \
  "const norm = lines.map((t) => t.normalize('NFKC'));" "$I_MERGE"
# the PR's own code is still never checked out — the property the whole
# pull_request_target design rests on. Asserted as "there is exactly one
# checkout and it takes no ref", not as "this one spelling is absent": under
# pull_request_target the default ref IS the base branch, so any `ref:` input
# at all is the thing to notice.
assert_no_grep "I5: the workflow never checks out the PR head" \
  "ref: \${{ github.event.pull_request.head" "$I_MERGE"
i_checkouts="$(grep -c 'uses: actions/checkout' "$I_MERGE" || :)"
assert_eq "I5: exactly one checkout step" 1 "$i_checkouts"
i_refs="$(grep -c '^ *ref:' "$I_MERGE" || :)"
assert_eq "I5: …and it passes no ref (the default is the base branch)" 0 "$i_refs"

I_RULES="$TEST_TMP/i_rules.tsv"
node - "$I_MERGE" > "$I_RULES" <<'NODE'
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const rulesM = src.match(/const RULES = \[[\s\S]*?\n {12}\];/);
const ctrlM = src.match(/const CONTROL_RE = (\/.*\/);/);
if (!rulesM || !ctrlM) { console.log('extract\tfail'); process.exit(0); }
console.log('extract\tok');
const RULES = new Function(`${rulesM[0]}\nreturn RULES;`)();
const CONTROL_RE = new Function(`return ${ctrlM[1]};`)();

const hits = (s) => RULES.filter((r) => r.re.test(s)).map((r) => r.rule);
const hitsNFKC = (s) => RULES.filter((r) => r.re.test(s.normalize('NFKC'))).map((r) => r.rule);

const table = [
  ['a private-key block is caught', hits('-----BEGIN RSA PRIVATE KEY-----').length > 0],
  ['a GitHub token shape is caught', hits('ghp_' + 'a'.repeat(36)).length > 0],
  ['a GitHub fine-grained PAT is caught', hits('github_pat_' + 'A1b2'.repeat(8)).length > 0],
  ['an sk- key shape is caught', hits('sk-' + 'x'.repeat(32)).length > 0],
  ['an AWS access key id is caught', hits('AKIA' + 'ABCDEFGH12345678').length > 0],
  ['a Slack token shape is caught', hits('xoxb-1234567890-abcdefghij').length > 0],
  // the reason the credential rules are shaped and not "long random string":
  // a corpus full of hashes and dates must not be a wall of false positives
  ['a plain sentence trips nothing', hits('The scope is written before the negation.').length === 0],
  ['a commit sha trips nothing', hits('see commit a4af8a6c1d2e3f405162738495a6b7c8d9e0f112').length === 0],
  ['a date trips nothing', hits('2026-08-05 の裁定').length === 0],
  // NFKC: same string to a reader, different string to a regex
  ['a full-width email slips the raw pattern', hits('ａｂｃ＠ｅｘａｍｐｌｅ．ｃｏｍ').length === 0],
  ['…and is caught after NFKC', hitsNFKC('ａｂｃ＠ｅｘａｍｐｌｅ．ｃｏｍ').length > 0],
  ['a compatibility ㈱ is caught after NFKC', hitsNFKC('㈱の話').length > 0],
  // control characters
  ['a NUL is a control character', CONTROL_RE.test('a\u0000b')],
  ['an escape byte is a control character', CONTROL_RE.test('a\u001Bb')],
  ['tab and CR are NOT control characters', !CONTROL_RE.test('a\tb\r')],
];
for (const [name, ok] of table) console.log(`${name}\t${ok ? 'ok' : 'fail'}`);
NODE

i_k=0
while IFS=$'\t' read -r i_name i_res; do
  [[ -n "$i_name" ]] || continue
  i_k=$((i_k + 1))
  assert_eq "I5: $i_name" "ok" "$i_res"
done < "$I_RULES"
assert_ge "I5: the rule table ran" "$i_k" 16
