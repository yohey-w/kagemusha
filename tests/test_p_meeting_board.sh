#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# P. meeting-board — Meet's live captions → a local board, and nothing else.
#
# The skill is a browser extension plus a small helper that a stranger drops
# onto a work PC. What makes it safe to hand over is not a promise but a few
# structural facts, and this group measures them:
#
#   · shape    — every piece ships (extension, helper, board, launchers, samples,
#                tests), the manifest asks for one host and no permission
#   · local    — the helper binds 127.0.0.1 only, no module that can reach
#                another host is loaded, the board renders data with textContent,
#                the extension talks to one loopback address
#   · privacy  — data/ (real meetings' verbatim) cannot be committed
#   · tests    — the skill's own node:test suite runs for real, with a stub in
#                place of the claude CLI (this suite never invokes an AI CLI)
#
# Node only, no npm. Everything the unit tests write goes under $TMPDIR.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "P. meeting-board (local-only by construction)"

P_REL="templates/skills/meeting-board"
P_SKILL="$REPO_ROOT/$P_REL"

# ── P1. shape: what a stranger receives ────────────────────────────────────
for p_f in SKILL.md README.md start.cmd start.sh .gitattributes data/.gitignore \
           extension/manifest.json extension/captions-core.js extension/content.js extension/background.js \
           helper/server.js helper/board.html helper/board-core.js helper/prompt.md helper/prompt_patch.md \
           helper/messages/no-node.txt helper/messages/old-node.txt helper/messages/failed.txt \
           helper/lib/app.js helper/lib/args.js helper/lib/claude.js helper/lib/diag.js \
           helper/lib/extract.js helper/lib/httpserver.js helper/lib/prompt.js helper/lib/replay.js \
           helper/lib/store.js helper/lib/transcript.js helper/lib/util.js \
           helper/lib/board.js helper/lib/minutes.js helper/lib/notes.js helper/lib/importers.js \
           sample/sample_transcript.txt sample/sample_notes.md \
           tests/fixtures/claude_stub.js tests/fixtures/support.js \
           tests/run.js tests/e2e/meet_fixture.html tests/e2e/run_e2e.js tests/eval/score_board.js; do
  assert_file "P1: $p_f ships" "$P_SKILL/$p_f"
done
p_ntests="$(find "$P_SKILL/tests" -maxdepth 1 -name '*.test.js' | wc -l | tr -d ' ')"
assert_ge "P1: unit test files ship ($p_ntests found)" "$p_ntests" 6

# the instruction prompt is used verbatim: the four input sections the helper fills in must be in it
for p_sec in '【事前メモ】' '【前回までの整理】' '【字幕の範囲】' '【字幕】'; do
  assert_grep "P1: prompt.md names the input section $p_sec" "$p_sec" "$P_SKILL/helper/prompt.md"
done

# SKILL.md frontmatter (the file is symlinked into ~/.claude/skills and ~/.codex/skills by setup.sh --link-skills)
assert_eq "P1: SKILL.md opens with a frontmatter fence" "---" "$(head -n 1 "$P_SKILL/SKILL.md")"
assert_grep "P1: SKILL.md names the skill" "name: meeting-board" "$P_SKILL/SKILL.md"
assert_grep "P1: SKILL.md carries a description" "description:" "$P_SKILL/SKILL.md"

# ── P2. the manifest asks for as little as possible ────────────────────────
assert_ok "P2: manifest.json is MV3, one loopback host, no permissions, Meet only, one worker" \
  python3 -c '
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
assert m["manifest_version"] == 3, m["manifest_version"]
assert m["host_permissions"] == ["http://127.0.0.1:47431/*"], m["host_permissions"]
assert "permissions" not in m and "optional_permissions" not in m, "no permissions"
assert [c["matches"] for c in m["content_scripts"]] == [["https://meet.google.com/*"]], m["content_scripts"]
assert m["content_scripts"][0]["run_at"] == "document_idle"
assert m["content_scripts"][0]["js"] == ["captions-core.js", "content.js"]
assert m["background"]["service_worker"] == "background.js"
import re
assert re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", m["version"]) and m["name"]
' "$P_SKILL/extension/manifest.json"

# ── P3. syntax: every shipped script parses ────────────────────────────────
while IFS= read -r p_js; do
  assert_ok "P3: node --check $p_js" node --check "$REPO_ROOT/$p_js"
done < <(git -C "$REPO_ROOT" ls-files "$P_REL/*.js" | sort)

# ── P4. launchers ──────────────────────────────────────────────────────────
assert_eq "P4: start.sh is executable in the git index" "100755" \
  "$(git -C "$REPO_ROOT" ls-files -s -- "$P_REL/start.sh" | awk '{print $1}')"
assert_eq "P4: start.cmd keeps its CRLF line endings (git must not normalise them)" "0" \
  "$(awk 'BEGIN{n=0} !/\r$/{n++} END{print n}' "$P_SKILL/start.cmd")"
assert_eq "P4: start.cmd has no BOM and opens with @echo off" "@echo off" \
  "$(head -n 1 "$P_SKILL/start.cmd" | tr -d '\r')"
assert_grep "P4: .gitattributes pins start.cmd (-text)" "start.cmd -text" "$P_SKILL/.gitattributes"
# the work PC may have no Node installed: node\node.exe next to start.cmd, then node.exe, then PATH
assert_grep "P4: start.cmd looks for a bundled node\\node.exe first" 'if exist "%HERE%node\node.exe"' "$P_SKILL/start.cmd"
assert_grep "P4: …then a node.exe next to it" 'if exist "%HERE%node.exe"' "$P_SKILL/start.cmd"
assert_grep "P4: …then node on PATH" 'where node' "$P_SKILL/start.cmd"
# start.cmd is pure ASCII: every Japanese message is shown by "type" from a UTF-8 file after chcp 65001,
# so no console code page (932 on a Japanese Windows) can garble the script or swallow a line break
assert_eq "P4: start.cmd contains no byte outside ASCII" "0" \
  "$(LC_ALL=C tr -d '\000-\177' < "$P_SKILL/start.cmd" | wc -c | tr -d ' ')"
assert_grep "P4: start.cmd shows the no-Node message from a file" 'type "%HERE%helper\messages\no-node.txt"' "$P_SKILL/start.cmd"
assert_grep "P4: …after switching the console to UTF-8" 'chcp 65001' "$P_SKILL/start.cmd"
assert_grep "P4: the no-Node message says where to get a no-install Node" "Windows Binary (.zip)" "$P_SKILL/helper/messages/no-node.txt"
assert_grep "P4: …and that no install or admin right is needed" "インストールは要らず、管理者権限も要りません" "$P_SKILL/helper/messages/no-node.txt"
assert_grep "P4: …and where to put the folder" "「node」に変えて、この start.cmd の隣に置きます" "$P_SKILL/helper/messages/no-node.txt"
for p_msg in no-node old-node failed; do
  assert_eq "P4: helper/messages/$p_msg.txt keeps CRLF" "0" \
    "$(awk 'BEGIN{n=0} !/\r$/{n++} END{print n}' "$P_SKILL/helper/messages/$p_msg.txt")"
  assert_ne "P4: helper/messages/$p_msg.txt has no BOM (a BOM prints as garbage)" "efbbbf" \
    "$(head -c 3 "$P_SKILL/helper/messages/$p_msg.txt" | od -An -tx1 | tr -d ' \n')"
done
assert_grep "P4: .gitattributes pins the messages (-text)" "helper/messages/*.txt -text" "$P_SKILL/.gitattributes"
assert_grep "P4: start.cmd passes extra arguments through" '--open %*' "$P_SKILL/start.cmd"
assert_grep "P4: start.sh passes extra arguments through" '--open "$@"' "$P_SKILL/start.sh"

# ── P5. local by construction ──────────────────────────────────────────────
P_CODE=()
while IFS= read -r p_f; do P_CODE+=("$REPO_ROOT/$p_f"); done \
  < <(git -C "$REPO_ROOT" ls-files "$P_REL" | grep -E '\.(js|html|json|cmd|sh|md|txt)$')
assert_ge "P5: skill files to scan" "${#P_CODE[@]}" 25

# the patterns live in variables so the real scan and its detector probe cannot drift apart
P_RE_HOME='/(home|Users)/[A-Za-z]|[A-Za-z]:\\+Users'
P_RE_HOST='https?://[A-Za-z0-9.-]+'
P_HOST_OK='://(meet\.google\.com|127\.0\.0\.1|localhost|nodejs\.org|github\.com|example\.com)$'
P_RE_IPV4='[0-9]{1,3}(\.[0-9]{1,3}){3}'
P_IPV4_OK='127\.0\.0\.1|0\.0\.0\.0'
P_RE_HTML='innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function'
P_RE_BIND="0\.0\.0\.0|listen\([^)]*'::'"

assert_empty_str "P5: no absolute home path in the skill" \
  "$(grep -nE "$P_RE_HOME" "${P_CODE[@]}" 2>/dev/null)"
assert_empty_str "P5: no host other than Meet / loopback / the Node download / GitHub / example.com" \
  "$(grep -noE "$P_RE_HOST" "${P_CODE[@]}" 2>/dev/null | grep -vE "$P_HOST_OK")"
assert_empty_str "P5: no bare IPv4 address except loopback" \
  "$(grep -nE "$P_RE_IPV4" "${P_CODE[@]}" 2>/dev/null | grep -vE "$P_IPV4_OK")"

# ...and the detectors are shown detecting (a guard nobody has watched fire is not evidence)
P_PROBE="$TEST_TMP/p_probe.txt"
{
  echo "path: /ho""me/someone/x"
  echo "path: C:\\Us""ers\\someone\\x"
  echo "url: https://tracker.example.net/collect"
  echo "ip: 203.0.113.7"
  echo "el.inner""HTML = data;"
  echo "server.listen(port, '0.0.""0.0')"
  echo "server.listen(port, '::')"
} > "$P_PROBE"
assert_eq "P5: the home-path detector catches both a Unix and a Windows path" "2" \
  "$(grep -cE "$P_RE_HOME" "$P_PROBE")"
assert_nonempty_str "P5: the host detector flags an unknown host" \
  "$(grep -noE "$P_RE_HOST" "$P_PROBE" | grep -vE "$P_HOST_OK")"
assert_nonempty_str "P5: the IPv4 detector flags a public address" \
  "$(grep -nE "$P_RE_IPV4" "$P_PROBE" | grep -vE "$P_IPV4_OK")"
assert_nonempty_str "P5: the markup detector flags innerHTML" "$(grep -nE "$P_RE_HTML" "$P_PROBE")"
assert_eq "P5: the bind detector flags 0.0.0.0 and ::" "2" "$(grep -cE "$P_RE_BIND" "$P_PROBE")"
printf 'see https://meet.google.com/x and http://127.0.0.1:47431/ and https://nodejs.org/ja/download\n' > "$TEST_TMP/p_probe_ok.txt"
assert_empty_str "P5: …and stays quiet on the hosts the skill is allowed to name" \
  "$(grep -noE "$P_RE_HOST" "$TEST_TMP/p_probe_ok.txt" | grep -vE "$P_HOST_OK")"

# the helper binds loopback, and nothing in it can talk to another host
P_HELPER=()
while IFS= read -r p_f; do P_HELPER+=("$REPO_ROOT/$p_f"); done < <(git -C "$REPO_ROOT" ls-files "$P_REL/helper" | grep -E '\.js$')
assert_grep "P5: the server listens on 127.0.0.1 only" "server.listen(port, '127.0.0.1'" "$P_SKILL/helper/lib/httpserver.js"
assert_empty_str "P5: the helper never binds 0.0.0.0 or ::" \
  "$(grep -nE "$P_RE_BIND" "${P_HELPER[@]}" 2>/dev/null)"
assert_empty_str "P5: the helper loads no https / net-client / dns / fetch" \
  "$(grep -nE "require\(['\"](node:)?(https|dns|tls|dgram)['\"]\)|\bfetch\(|net\.connect|new WebSocket" "${P_HELPER[@]}" 2>/dev/null)"
assert_grep "P5: requests need the X-Meeting-Board header" "x-meeting-board" "$P_SKILL/helper/lib/httpserver.js"
assert_grep "P5: the Host header is checked (DNS rebinding)" "forbidden host" "$P_SKILL/helper/lib/httpserver.js"

# the extension talks to exactly one address, and only the background worker does
assert_grep "P5: background.js posts to the loopback helper" "var HELPER = 'http://127.0.0.1:47431';" "$P_SKILL/extension/background.js"
assert_empty_str "P5: no fetch / XHR / WebSocket in the content script or the core" \
  "$(grep -nE '\bfetch\(|XMLHttpRequest|WebSocket|sendBeacon' "$P_SKILL/extension/content.js" "$P_SKILL/extension/captions-core.js" 2>/dev/null)"

# the board renders everything through textContent and loads nothing from outside
assert_empty_str "P5: board.html never uses innerHTML / outerHTML / document.write / eval" \
  "$(grep -nE "$P_RE_HTML" "$P_SKILL/helper/board.html" 2>/dev/null)"
assert_empty_str "P5: board.html loads no external resource" \
  "$(grep -nE '(src|href)="https?:|@import|url\(https?:' "$P_SKILL/helper/board.html" 2>/dev/null)"

# ── P6. data/ is uncommittable (real meetings' verbatim) ───────────────────
P_FX="$TEST_TMP/p_kit"
kit_copy "$P_FX"
kit_git_init "$P_FX"
mkdir -p "$P_FX/$P_REL/data/2026-10-21_093000/sub"
for p_f in transcript.jsonl board.json notes.md sub/x.txt; do
  printf 'verbatim of a real meeting — must never reach a commit\n' > "$P_FX/$P_REL/data/2026-10-21_093000/$p_f"
done
printf '{"selfName":"x"}\n' > "$P_FX/$P_REL/data/settings.json"
mkdir -p "$P_FX/$P_REL/data/_cwd" && printf 'x\n' > "$P_FX/$P_REL/data/_cwd/y"
assert_empty_str "P6: git sees nothing to commit after a meeting's worth of data" \
  "$(git -C "$P_FX" status --porcelain)"
p_unignored=""
for p_f in "data/2026-10-21_093000/transcript.jsonl" "data/2026-10-21_093000/board.json" \
           "data/2026-10-21_093000/notes.md" "data/settings.json" "data/_cwd/y"; do
  git -C "$P_FX" check-ignore -q "$P_REL/$p_f" || p_unignored="${p_unignored}${p_f}"$'\n'
done
assert_empty_str "P6: every runtime file under data/ is individually ignored" "$p_unignored"
printf 'a kit file\n' > "$P_FX/$P_REL/helper/new_kit_file.js"
git -C "$P_FX" status --porcelain > "$TEST_TMP/p_status.txt"
assert_grep "P6: control — a new kit file next to it IS reported" "new_kit_file.js" "$TEST_TMP/p_status.txt"
rm -f "$P_FX/$P_REL/helper/new_kit_file.js"

# ── P7. the skill's own tests, for real (stub claude, 127.0.0.1 only) ──────
# A throwaway copy of the tracked files; HOME and every data dir live under
# $TMPDIR. CLAUDE_BIN points nowhere, so a test that forgot to use the stub
# fails loudly instead of reaching the real CLI.
P_RUN="$TEST_TMP/p_run"
kit_copy "$P_RUN"
P_OUT="$TEST_TMP/p_node_test.log"
(
  cd "$P_RUN/$P_REL" || exit 1
  env HOME="$TEST_TMP" TMPDIR="$TEST_TMP" CLAUDE_BIN="$TEST_TMP/no-such-claude" NO_COLOR=1 \
    timeout 420 node tests/run.js
) > "$P_OUT" 2>&1
p_rc=$?
assert_eq "P7: node --test (stub claude) exits 0" "0" "$p_rc"
[[ $p_rc -eq 0 ]] || tail -n 40 "$P_OUT" | sed 's/^/       | /'
p_pass="$(sed -n 's/^# pass //p' "$P_OUT" | tail -n 1)"
p_fail="$(sed -n 's/^# fail //p' "$P_OUT" | tail -n 1)"
p_skip="$(sed -n 's/^# skipped //p' "$P_OUT" | tail -n 1)"
assert_ge "P7: a floor on the number of node tests that passed (${p_pass:-0})" "${p_pass:-0}" 70
assert_eq "P7: no node test failed" "0" "${p_fail:-x}"
assert_eq "P7: no node test was skipped" "0" "${p_skip:-x}"
assert_empty_str "P7: the tests left nothing in the skill's data/ (only .gitignore)" \
  "$(find "$P_RUN/$P_REL/data" -mindepth 1 ! -name .gitignore 2>/dev/null)"
