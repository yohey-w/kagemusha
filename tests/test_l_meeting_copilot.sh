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
assert_file "L1: responder.py ships"               "$L_SCRIPTS/responder.py"
assert_file "L1: unit tests ship (responder)"      "$L_TESTS/test_responder.py"
assert_file "L1: run.sh ships"                     "$L_SCRIPTS/run.sh"
assert_file "L1: stop.sh ships"                    "$L_SCRIPTS/stop.sh"
assert_file "L1: decision_engine.py ships"         "$L_SCRIPTS/decision_engine.py"
assert_file "L1: replay_eval.py ships"             "$L_SCRIPTS/replay_eval.py"
assert_file "L1: unit tests ship (decision layer)" "$L_TESTS/test_decision_engine.py"
assert_file "L1: decisions.example.yaml ships"     "$L_CONFIG/decisions.example.yaml"

# the demo meeting folder is the "does it run at all" answer for a new user
for f in meeting.json agenda_steps.json talk_script.md phrasebook.json \
         stage_resources.json bank.json decisions.yaml roster.txt; do
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
# plain ERE on purpose: -E together with -P is a matcher conflict on some greps,
# and a check that errors out reads as "clean" once stderr is discarded. The
# probe below proves this one still detects.
assert_empty_str "L2: no hard-coded http(s) host in the scripts" \
  "$(grep -nE 'https?://[A-Za-z0-9.-]+' "${L_CODE[@]}" 2>/dev/null \
     | grep -v 'example\.com')"
# ...and the detector is shown detecting (a guard nobody has watched fire is not evidence)
L_PROBE="$TEST_TMP/l_probe.py"
printf 'BASE = "https://%s.example.net/admin"\n' "internal-host" > "$L_PROBE"
assert_nonempty_str "L2: the host detector actually detects" \
  "$(grep -nE 'https?://[A-Za-z0-9.-]+' "$L_PROBE" | grep -v 'example\.com')"
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

# ── L5. run.sh — the launcher a stranger actually types ────────────────────
# A launcher is trustworthy only if you can see what it will do BEFORE the
# meeting starts, and if it stops each daemon the way that daemon says it stops.
L_RUN="$L_FX/templates/skills/meeting-copilot/scripts/run.sh"
L_DRY_STATE="$TEST_TMP/l_dry_state"
L_DRY_OUT="$TEST_TMP/l_dry.txt"

env -u MEETLIVE_CREDS_FILE \
  MEETLIVE_MEETING="$L_FX/templates/skills/meeting-copilot/config/example_meeting" \
  MEETLIVE_DIR="$L_DRY_STATE" \
  bash "$L_RUN" --dry-run --port 47399 > "$L_DRY_OUT" 2>&1
assert_grep "L5: --dry-run names the meeting from meeting.json" "Acme" "$L_DRY_OUT"
assert_grep "L5: --dry-run shows the viewer command"            "viewer2.py" "$L_DRY_OUT"
assert_grep "L5: --dry-run honours features (demo runs copilot)" "copilot.py" "$L_DRY_OUT"
assert_no_grep "L5: --dry-run omits the layer features turned off" \
  "responder.py" "$L_DRY_OUT"
# premise_watch is NOT a daemon (copilot spawns it per utterance). Saying so out
# loud is the point: premise_watch=true in a folder with copilot=false means no
# premise watching at all, and that must not be discovered at 8 in the morning.
assert_grep "L5: --dry-run explains that premise_watch is not a daemon" \
  "常駐しない" "$L_DRY_OUT"
# and it really is dry — nothing launched, no log directory made
assert_absent "L5: --dry-run creates no log directory" "$L_DRY_STATE/logs"

assert_exit "L5: run.sh without MEETLIVE_MEETING refuses (exit 2)" 2 \
  env -u MEETLIVE_MEETING -u MEETLIVE_DIR bash "$L_RUN" --dry-run

# the stop discipline: every stop path belongs to the daemon itself. kill/pkill
# would take out whatever else is running on the machine, mid-meeting.
# (the comment lines that SAY "kill is not used" are dropped first, so the
#  guard reads the code and not the promise about the code)
assert_empty_str "L5: run.sh / stop.sh never reach for kill or pkill" \
  "$(grep -vE '^[[:space:]]*#' "$L_SCRIPTS/run.sh" "$L_SCRIPTS/stop.sh" 2>/dev/null \
     | grep -nE '(^|[^a-z_])p?kill([^a-z_]|$)')"
assert_grep "L5: stop.sh uses the viewer's own /quit"        "/quit"          "$L_SCRIPTS/stop.sh"
assert_grep "L5: stop.sh uses the responder's own stop file" "responder.stop" "$L_SCRIPTS/stop.sh"
# 2026-09-20: every layer now has a stop path — one shared file each of them polls.
# The failure this closes: after the 9/19 meeting, receiver and copilot had NO stop
# path at all, so three processes ran on for ~12 hours drawing 903 cards nobody saw.
assert_grep "L5: stop.sh places the one stop file every layer watches" \
  "meetlive.stop" "$L_SCRIPTS/stop.sh"
for l_layer in copilot receiver viewer2 responder; do
  assert_grep "L5: $l_layer watches the shared stop file" \
    "stop_file()" "$L_SCRIPTS/$l_layer.py"
done
# ...and the launcher clears a stale one, or the next meeting dies on startup
assert_grep "L5: run.sh clears a stale stop file before starting" \
  "meetlive.stop" "$L_SCRIPTS/run.sh"
assert_grep "L5: SKILL.md documents the one stop path" \
  "meetlive.stop" "$L_SKILL/SKILL.md"

# ── L6. the responder feeds the model EVERYTHING ───────────────────────────
# 2026-09-03, measured: truncating the material does not make the answer say
# "I don't have that" — it makes it confidently say the OPPOSITE of the script.
# So the responder must not go near the character limits the (differently
# shaped) answerer obeys.
assert_no_grep "L6: responder does not apply the truncation limits" \
  "cfgmod.knowledge_limits" "$L_SCRIPTS/responder.py"
assert_no_grep "L6: responder does not read the per-file limit either" \
  "MEETLIVE_KNOWLEDGE_PER_FILE" "$L_SCRIPTS/responder.py"
assert_grep "L6: responder reads the material shelf through the config" \
  "knowledge_dir" "$L_SCRIPTS/responder.py"
assert_grep "L6: responder writes the heartbeat the viewer reads" \
  '"role": "responder"' "$L_SCRIPTS/responder.py"

# ── L7. the launcher refuses a port that already has a tenant ──────────────
# The failure this prevents is the quietest one in the whole kit: the previous
# meeting's receiver is still bound, the child machine connects to IT, the
# transcript lands in the OLD state directory — and the screen comes up fine,
# heartbeat green, "受信 —" forever. So run.sh must look before it leaps, and
# the guard has to be watched firing, not merely present in the source.
L_HOLD="$TEST_TMP/l_hold.py"
cat > "$L_HOLD" <<'PYEOF'
import socket
import sys
import time

s = socket.socket()
s.bind(("127.0.0.1", 0))
s.listen(1)
with open(sys.argv[1], "w", encoding="utf-8") as f:
    f.write(str(s.getsockname()[1]))
time.sleep(20)          # 自分で終わる（後片付けに kill を要らなくするため）
PYEOF
python3 "$L_HOLD" "$TEST_TMP/l_port" &
for _ in $(seq 1 50); do [[ -s "$TEST_TMP/l_port" ]] && break; sleep 0.1; done

if [[ -s "$TEST_TMP/l_port" ]]; then
  l_taken="$(cat "$TEST_TMP/l_port")"
  assert_exit "L7: run.sh refuses a viewer port that is already listening (exit 3)" 3 \
    env -u MEETLIVE_CREDS_FILE \
        MEETLIVE_MEETING="$L_FX/templates/skills/meeting-copilot/config/example_meeting" \
        MEETLIVE_DIR="$TEST_TMP/l_busy_state" \
    bash "$L_RUN" --port "$l_taken" --no-receiver
  # ...and a free port is not refused (the guard must not block every start)
  assert_ok "L7: a free port still starts (dry-run)" \
    env -u MEETLIVE_CREDS_FILE \
        MEETLIVE_MEETING="$L_FX/templates/skills/meeting-copilot/config/example_meeting" \
        MEETLIVE_DIR="$TEST_TMP/l_free_state" \
    bash "$L_RUN" --dry-run --port "$((l_taken + 1))" --no-receiver
else
  fail "L7: could not hold a port to test the guard with" \
    "the helper never wrote its port number"
fi

# ── L8. the decision layer ships pointed at nothing ────────────────────────
# The layer sends utterances to an outside judge. Two things must therefore be
# true of what a stranger unpacks: the destination is NOT in the code (L2's URL
# scan covers the scripts), and the default is inward — a meeting folder that
# says nothing about it runs on the local rules and draws no card. The failure
# this closes is the one nobody would see: a kit that starts shipping a
# client's words to a third party because a default was set the other way.
assert_ok "L8: the decision layer defaults inward (rules, no cards)" \
  env -u MEETLIVE_AGENDA -u MEETLIVE_SCRIPT -u MEETLIVE_STAGE -u MEETLIVE_CREDS_FILE \
      MEETLIVE_MEETING="$L_FX/templates/skills/meeting-copilot/config/example_meeting" \
      MEETLIVE_DIR="$L_STATE" \
  python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
import meetlive_config as c
# the demo folder says nothing about the decision layer — so these are the
# defaults a stranger gets, not values someone wrote down
assert c.decision_backend() == "rules", c.decision_backend()
assert c.show_decision_cards() is False, c.show_decision_cards()
' "$L_FX/templates/skills/meeting-copilot/scripts"

# a misspelt backend must fall back to rules, not to "whatever was typed"
assert_ok "L8: an unknown backend name falls back to rules" \
  env -u MEETLIVE_AGENDA -u MEETLIVE_SCRIPT -u MEETLIVE_STAGE -u MEETLIVE_CREDS_FILE \
      MEETLIVE_DIR="$L_STATE" \
  python3 -c '
import json, pathlib, os, sys, tempfile
scripts = sys.argv[1]
src = pathlib.Path(sys.argv[2])
with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    m = json.loads((src / "meeting.json").read_text(encoding="utf-8"))
    m["decision_backend"] = "jevv"
    (d / "meeting.json").write_text(json.dumps(m), encoding="utf-8")
    os.environ["MEETLIVE_MEETING"] = str(d)
    sys.path.insert(0, scripts)
    import meetlive_config as c
    assert c.decision_backend() == "rules", c.decision_backend()
' "$L_FX/templates/skills/meeting-copilot/scripts" \
  "$L_FX/templates/skills/meeting-copilot/config/example_meeting"

# the shipped question bundle names the ENV VAR that holds the key — never a key
assert_grep "L8: the example bundle names an env var for the key" \
  "key_env:" "$L_CONFIG/decisions.example.yaml"
assert_empty_str "L8: no api key literal in the shipped bundles" \
  "$(grep -nEi '(api[_-]?key|bearer|secret)[[:space:]]*[:=][[:space:]]*[A-Za-z0-9_-]{16,}' \
     "$L_CONFIG/decisions.example.yaml" "$L_DEMO/decisions.yaml" 2>/dev/null)"
# ...and that detector is shown detecting
L_KPROBE="$TEST_TMP/l_key_probe.yaml"
printf 'api_key: %s\n' "abcdefghijklmnopqrstuvwx" > "$L_KPROBE"
assert_nonempty_str "L8: the key detector actually detects" \
  "$(grep -nEi '(api[_-]?key|bearer|secret)[[:space:]]*[:=][[:space:]]*[A-Za-z0-9_-]{16,}' \
     "$L_KPROBE")"

# the replay harness runs the demo folder end to end with no key and no network
L_REPLAY_DIR="$TEST_TMP/l_replay"
mkdir -p "$L_REPLAY_DIR"
cat > "$L_REPLAY_DIR/t.jsonl" <<'JSONL'
{"ts": "2026-01-01T10:00:00", "speaker": "guest", "text": "よろしくお願いします。"}
{"ts": "2026-01-01T10:00:10", "speaker": "host", "text": "今日決めたいことは3つです。"}
{"ts": "2026-01-01T10:01:00", "speaker": "host", "text": "ちょっとお待ちください。確認します。"}
JSONL
assert_ok "L8: replay_eval runs the demo folder with no key (backend rules)" \
  env -u MEETLIVE_MEETING -u MEETLIVE_DIR \
  timeout 120 python3 "$L_FX/templates/skills/meeting-copilot/scripts/replay_eval.py" \
    --transcript "$L_REPLAY_DIR/t.jsonl" \
    --meeting "$L_FX/templates/skills/meeting-copilot/config/example_meeting" \
    --backend rules --out "$L_REPLAY_DIR/decisions.jsonl"
assert_file "L8: the replay left a decision log" "$L_REPLAY_DIR/decisions.jsonl"
l_recs="$(wc -l < "$L_REPLAY_DIR/decisions.jsonl" | tr -d ' ')"
assert_eq "L8: one record per utterance" "3" "$l_recs"

# ── L9. the decision layer's live wiring stays inward by default ───────────
# The layer now draws cards during a real meeting. Two invariants a stranger
# must get for free: it does not run at all unless the meeting folder asks for
# it, and it never takes over the step machinery (a wrong step throws the
# teleprompter away, which is worse than no hint at all).
assert_file "L9: live-wiring unit tests ship" "$L_TESTS/test_decision_live.py"
assert_grep "L9: the watchdog runs the judge off the main loop" \
  "threading.Thread" "$L_SCRIPTS/copilot.py"
assert_grep "L9: …and skips while one is already running" \
  "判定層は走行中なので見送り" "$L_SCRIPTS/copilot.py"
assert_grep "L9: the viewer only shows a fresh step hint" \
  "DECISION_HINT_MAX_AGE" "$L_SCRIPTS/viewer2.py"
# the step high-water mark is moved by the keyword rule ONLY
assert_empty_str "L9: the decision layer never writes the step high-water mark" \
  "$(grep -nE 'self\.auto_hi[[:space:]]*=' "$L_SCRIPTS/copilot.py" \
     | grep -v 'step_detect' | grep -v 'self\.auto_hi = 0')"
