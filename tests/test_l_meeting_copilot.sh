#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# L. meeting-copilot — the live-meeting monitor ships generic.
#
# This skill is the one that gets edited DURING a real meeting, inside a real
# meeting folder, at 8 in the morning. That is exactly how a client's name, a
# machine's tailscale address or a share-token URL rides back into the kit. So
# the gate here is two-sided:
#
#   · shape   — the pieces a stranger needs are all shipped (config examples,
#               a demo meeting folder that actually runs, the unit tests)
#   · content — no case-specific value is left in the code: the scripts read
#               their settings from meetlive_config, and the only place a URL,
#               a path or a person's name may live is the meeting folder.
#
# The skill's own unit tests run here too (stdlib only, 127.0.0.1 only, all
# writes under $TMPDIR) — a suite that never runs in CI is not a gate.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "L. meeting-copilot (generic by construction)"

L_SKILL="$REPO_ROOT/templates/skills/meeting-copilot"
L_SCRIPTS="$L_SKILL/scripts"
L_CONFIG="$L_SKILL/config"
L_TESTS="$L_SKILL/tests"
L_DEMO="$L_CONFIG/example_meeting"

# ── L1. shape: what a stranger receives ────────────────────────────────────
assert_dir  "L1: skill ships"                      "$L_SKILL"
assert_file "L1: meetlive_config.py ships"         "$L_SCRIPTS/meetlive_config.py"
assert_file "L1: mode_signal.py ships"             "$L_SCRIPTS/mode_signal.py"
assert_file "L1: viewer2.py ships"                 "$L_SCRIPTS/viewer2.py"
assert_file "L1: receiver.py ships"                "$L_SCRIPTS/receiver.py"
assert_file "L1: meeting.example.json ships"       "$L_CONFIG/meeting.example.json"
assert_file "L1: unit tests ship (viewer state)"   "$L_TESTS/test_viewer_state.py"
assert_file "L1: unit tests ship (mode signal)"    "$L_TESTS/test_mode_signal.py"

# the demo meeting folder is the "does it run at all" answer for a new user
for f in meeting.json agenda_steps.json talk_script.md phrasebook.json \
         stage_resources.json bank.json; do
  assert_file "L1: demo meeting folder has $f" "$L_DEMO/$f"
done
assert_dir "L1: demo meeting folder has docs/" "$L_DEMO/docs"
assert_dir "L1: demo meeting folder has kb/"   "$L_DEMO/kb"

l_docs="$(find "$L_DEMO/docs" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')"
assert_ge "L1: demo doc shelf is not empty ($l_docs files)" "$l_docs" 2

# every shipped JSON must parse — a demo that dies on a comma is worse than none
while IFS= read -r f; do
  assert_ok "L1: valid JSON $(basename "$(dirname "$f")")/$(basename "$f")" \
    python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$f"
done < <(find "$L_CONFIG" -name '*.json' | sort)

# ── L2. content: no case-specific value left in the code ───────────────────
# The privacy guard (group C) already scans every tracked file for the known
# identifiers. This is the other half: the SHAPES that carry a case — an
# absolute home path, a hard-coded host, a share-token URL — none of which a
# generic tool has any reason to contain.
L_CODE=()
while IFS= read -r f; do L_CODE+=("$REPO_ROOT/$f"); done \
  < <(git -C "$REPO_ROOT" ls-files 'templates/skills/meeting-copilot/scripts/*.py')
assert_ge "L2: skill python files found" "${#L_CODE[@]}" 6

assert_empty_str "L2: no absolute home path in the scripts" \
  "$(grep -nE '/(home|Users)/[a-z]' "${L_CODE[@]}" 2>/dev/null)"
assert_empty_str "L2: no hard-coded http(s) host in the scripts" \
  "$(grep -nE 'https?://(?!example\.com)[A-Za-z0-9.]' -P "${L_CODE[@]}" 2>/dev/null \
     | grep -v 'example\.com')"
assert_empty_str "L2: no bare IPv4 address in the scripts" \
  "$(grep -nE '[0-9]{1,3}(\.[0-9]{1,3}){3}' "${L_CODE[@]}" 2>/dev/null \
     | grep -vE '127\.0\.0\.1|0\.0\.0\.0')"   # loopback and bind-all are not a case

# every MEETLIVE_* setting resolves in ONE place. A raw os.environ.get outside
# meetlive_config is how "the viewer reads it, the watchdog doesn't" starts.
assert_empty_str "L2: MEETLIVE_* is only read inside meetlive_config.py" \
  "$(grep -n 'os\.environ\.get("MEETLIVE' "${L_CODE[@]}" 2>/dev/null \
     | grep -v '/meetlive_config\.py:')"

# the start signal has exactly one predicate (the T-0019 asymmetry: the writer
# matched exactly, the readers absorbed mishearings, so voice never worked)
assert_grep "L2: receiver uses mode_signal (the writer side)" \
  "mode_signal.is_start_signal" "$L_SCRIPTS/receiver.py"
assert_grep "L2: viewer2 uses mode_signal (the reader side)" \
  "mode_signal.is_start_signal" "$L_SCRIPTS/viewer2.py"
assert_grep "L2: copilot uses mode_signal (the watchdog side)" \
  "mode_signal.is_start_signal" "$L_SCRIPTS/copilot.py"

# ── L3. the skill's own unit tests, for real ───────────────────────────────
# Run against a throwaway copy of the tracked files, with HOME and the state
# directory inside $TMPDIR, so nothing touches the repo you are sitting in.
L_FX="$TEST_TMP/l_kit"
kit_copy "$L_FX"
L_STATE="$TEST_TMP/l_state"
mkdir -p "$L_STATE"
assert_ok "L3: skill unit tests pass (stdlib only, 127.0.0.1 only)" \
  env -u MEETLIVE_MEETING -u MEETLIVE_DIR -u MEETLIVE_AGENDA -u MEETLIVE_SCRIPT \
      -u MEETLIVE_STAGE -u MEETLIVE_CREDS_FILE -u MEETLIVE_PHRASEBOOK \
      HOME="$TEST_TMP" MEETLIVE_DIR="$L_STATE" \
  timeout 180 python3 -m unittest discover \
    -s "$L_FX/templates/skills/meeting-copilot/tests" -q

# and the repo it ran in is still clean (the suite must never write to itself)
assert_absent "L3: no state directory left in the skill" "$L_SCRIPTS/meetlive_state"
assert_absent "L3: no state directory left at the repo root" "$REPO_ROOT/meetlive_state"

# ── L4. the demo really boots ──────────────────────────────────────────────
# A config example nobody has watched start is a promise, not a fact. Load the
# demo meeting folder through the real resolution path and read the values back.
assert_ok "L4: demo meeting folder resolves through meetlive_config" \
  env -u MEETLIVE_AGENDA -u MEETLIVE_SCRIPT -u MEETLIVE_STAGE -u MEETLIVE_CREDS_FILE \
      MEETLIVE_MEETING="$L_FX/templates/skills/meeting-copilot/config/example_meeting" \
      MEETLIVE_DIR="$L_STATE" \
  python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
import meetlive_config as c
m = c.load_meeting()
assert m["layout"] == "columns", m["layout"]
assert c.stage_setinfo()["order"], "stage.order is empty"
assert c.card_policy()["auto_dismiss_kinds"] == ("warn", "premise_warn")
assert c.docs_dir().is_dir(), c.docs_dir()
assert c.input_path("MEETLIVE_AGENDA", "agenda_steps.example.json").name \
    == "agenda_steps.json"
assert c.creds_file() is None, "secrets must not live in the meeting folder"
' "$L_FX/templates/skills/meeting-copilot/scripts"
