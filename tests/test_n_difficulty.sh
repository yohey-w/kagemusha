#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# N. parent-selected difficulty profiles.
#
# The adapter maps a CLOSED label to provider-specific model/effort settings.
# It does not inspect the prompt, auto-upgrade, or change the old resolution
# path when no label is supplied. Shims pin the exact argv without starting an
# AI, including the failure path for malformed labels.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "N. difficulty routing (explicit, provider-specific, backward compatible)"

N_LIB="$REPO_ROOT/scripts/lib/agent_cli.sh"
N_BIN="$TEST_TMP/n_bin"
N_ARGS="$TEST_TMP/n_argv.txt"
N_CALLS="$TEST_TMP/n_calls.txt"
N_CFG="$TEST_TMP/n_config.env"
N_HOST_PATH="$PATH"
mkdir -p "$N_BIN"

cat > "$N_BIN/codex" <<'SHIM'
#!/usr/bin/env bash
printf 'called\n' >> "$N_CALLS"
: > "$N_ARGS"
out=""; prev=""
for arg in "$@"; do
  printf '%s\n' "$arg" >> "$N_ARGS"
  [[ "$prev" == "-o" ]] && out="$arg"
  prev="$arg"
done
[[ -n "$out" ]] && printf 'N-ANSWER\n' > "$out"
SHIM

cat > "$N_BIN/claude" <<'SHIM'
#!/usr/bin/env bash
printf 'called\n' >> "$N_CALLS"
: > "$N_ARGS"
for arg in "$@"; do printf '%s\n' "$arg" >> "$N_ARGS"; done
printf 'N-ANSWER\n'
SHIM
chmod +x "$N_BIN/codex" "$N_BIN/claude"

cat > "$N_CFG" <<'CFG'
AGENT_CLI="codex"
AGENT_CMD=""
AGENT_MODEL_CODEX="cfg-base-model"
AGENT_EFFORT_CODEX="cfg-provider-effort"
AGENT_EFFORT="cfg-shared-effort"
AGENT_DIFFICULTY=""
AGENT_MODEL_CODEX_SIMPLE="cfg-simple-model"
AGENT_EFFORT_CODEX_SIMPLE="cfg-simple-effort"
AGENT_MODEL_CODEX_STANDARD="cfg-standard-model"
AGENT_EFFORT_CODEX_STANDARD="cfg-standard-effort"
AGENT_MODEL_CODEX_COMPLEX="cfg-complex-model"
AGENT_EFFORT_CODEX_COMPLEX="cfg-complex-effort"
AGENT_MODEL_CLAUDE_STANDARD="cfg-claude-standard"
AGENT_EFFORT_CLAUDE_STANDARD="cfg-claude-effort"
CFG

n_show() { # n_show DIALECT [agent_cli_show options]
  local dialect="$1"; shift
  env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" AGENT_CLI="$dialect" \
    bash -c 'source "$1"; source "$2"; shift 2; agent_cli_show "$@" -- P' \
    _ "$N_LIB" "$N_CFG" "$@"
}

N_GOT="$(n_show codex --difficulty simple)"
assert_grep_str "N1: simple resolves the Codex profile model" \
  "-m cfg-simple-model" "$N_GOT"
assert_grep_str "N1: simple resolves the Codex profile effort" \
  "model_reasoning_effort=cfg-simple-effort" "$N_GOT"
assert_grep_str "N1: the resolved label is visible in dry-run output" \
  "difficulty=simple" "$N_GOT"

N_GOT="$(n_show claude --difficulty standard)"
assert_grep_str "N2: the same label uses the Claude-specific model" \
  "--model cfg-claude-standard" "$N_GOT"
assert_grep_str "N2: the same label uses the Claude-specific effort" \
  "--effort cfg-claude-effort" "$N_GOT"

N_GOT="$(n_show codex --difficulty complex --model call-model --effort call-effort)"
assert_grep_str "N3: explicit --model beats a selected profile" "-m call-model" "$N_GOT"
assert_grep_str "N3: explicit --effort beats a selected profile" \
  "model_reasoning_effort=call-effort" "$N_GOT"
assert_no_grep_str "N3: the displaced profile model is absent" "cfg-complex-model" "$N_GOT"

# Exported profile > exported base > config profile > config base. These calls
# source the config only AFTER the library has frozen the exported layer.
N_GOT="$(env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
  AGENT_CLI=codex AGENT_MODEL_CODEX_SIMPLE=env-profile AGENT_MODEL_CODEX=env-base \
  bash -c 'source "$1"; source "$2"; agent_cli_show --difficulty simple -- P' \
  _ "$N_LIB" "$N_CFG")"
assert_grep_str "N4: an exported profile beats an exported base" "-m env-profile" "$N_GOT"

N_GOT="$(env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
  AGENT_CLI=codex AGENT_MODEL_CODEX=env-base \
  bash -c 'source "$1"; source "$2"; agent_cli_show --difficulty simple -- P' \
  _ "$N_LIB" "$N_CFG")"
assert_grep_str "N4: an exported base beats a profile found only in config" \
  "-m env-base" "$N_GOT"

# Backward-compatibility counterexample: before difficulty existed, the provider
# config effort beat an exported SHARED effort. Omitting the label must retain
# that exact order; selecting a profile enters the new order deliberately.
N_OLD="$(env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
  AGENT_CLI=codex AGENT_EFFORT=env-shared \
  bash -c 'source "$1"; source "$2"; agent_cli_show -- P' _ "$N_LIB" "$N_CFG")"
assert_grep_str "N5: omitted difficulty preserves provider-config over shared-export" \
  "effort=cfg-provider-effort difficulty=-" "$N_OLD"
N_PROFILED="$(env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
  AGENT_CLI=codex AGENT_EFFORT=env-shared \
  bash -c 'source "$1"; source "$2"; agent_cli_show --difficulty simple -- P' \
  _ "$N_LIB" "$N_CFG")"
assert_grep_str "N5: a selected profile uses the documented exported-base layer" \
  "effort=env-shared difficulty=simple" "$N_PROFILED"

# Difficulty itself: per-call > export > config.
N_GOT="$(env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
  AGENT_CLI=codex AGENT_DIFFICULTY=standard \
  bash -c 'source "$1"; source "$2"; AGENT_DIFFICULTY=complex; agent_cli_show --difficulty simple -- P' \
  _ "$N_LIB" "$N_CFG")"
assert_grep_str "N6: --difficulty beats both environment and config" "difficulty=simple" "$N_GOT"
N_GOT="$(env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
  AGENT_CLI=codex AGENT_DIFFICULTY=standard \
  bash -c 'source "$1"; source "$2"; AGENT_DIFFICULTY=complex; agent_cli_show -- P' \
  _ "$N_LIB" "$N_CFG")"
assert_grep_str "N6: exported AGENT_DIFFICULTY beats the file" "difficulty=standard" "$N_GOT"

# A real stub run pins the argv, not merely the published resolution variables.
rm -f "$N_CALLS" "$N_ARGS"
N_ANSWER="$(env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
  N_CALLS="$N_CALLS" N_ARGS="$N_ARGS" AGENT_CLI=codex AGENT_CMD="$N_BIN/codex" \
  bash -c 'source "$1"; source "$2"; agent_run --difficulty simple --no-preamble -- P' \
  _ "$N_LIB" "$N_CFG")"
assert_eq "N7: the Codex stub returns its answer" "N-ANSWER" "$N_ANSWER"
assert_grep "N7: stub argv carries the profile model" "cfg-simple-model" "$N_ARGS"
assert_grep "N7: stub argv carries the profile effort" \
  "model_reasoning_effort=cfg-simple-effort" "$N_ARGS"

rm -f "$N_CALLS" "$N_ARGS"
N_ANSWER="$(env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
  N_CALLS="$N_CALLS" N_ARGS="$N_ARGS" AGENT_CLI=claude AGENT_CMD="$N_BIN/claude" \
  bash -c 'source "$1"; source "$2"; agent_run --difficulty standard -- P' \
  _ "$N_LIB" "$N_CFG")"
assert_eq "N7: the Claude stub returns its answer" "N-ANSWER" "$N_ANSWER"
assert_grep "N7: Claude stub argv carries its profile model" \
  "cfg-claude-standard" "$N_ARGS"
assert_grep "N7: Claude stub argv carries its profile effort" \
  "cfg-claude-effort" "$N_ARGS"

# Every malformed value fails before the shim starts. `timeout` also proves the
# missing-value parser cannot sit in a shift/while loop.
n_bad() {
  rm -f "$N_CALLS" "$N_ARGS"
  timeout 3 env -i HOME="$TEST_TMP/n_home" PATH="$N_BIN:$N_HOST_PATH" \
    N_CALLS="$N_CALLS" N_ARGS="$N_ARGS" AGENT_CLI=codex AGENT_CMD="$N_BIN/codex" \
    bash -c 'source "$1"; shift; agent_run "$@"' _ "$N_LIB" "$@"
}
assert_exit "N8: an unknown difficulty exits 2" 2 n_bad --difficulty impossible -- P
assert_absent "N8: unknown difficulty starts no AI CLI" "$N_CALLS"
assert_exit "N8: a missing difficulty value exits 2 (not a loop)" 2 n_bad --difficulty
assert_absent "N8: missing value starts no AI CLI" "$N_CALLS"
assert_exit "N8: an explicitly empty difficulty exits 2" 2 n_bad --difficulty "" -- P
assert_absent "N8: empty value starts no AI CLI" "$N_CALLS"

assert_grep "N9: config documents all three labels" \
  "AGENT_MODEL_CODEX_COMPLEX" "$REPO_ROOT/config.env.example"
assert_grep "N9: distributed instructions assign the parent, not the wrapper" \
  "親エージェントが作業を分ける" "$REPO_ROOT/templates/agent_instructions.md"
assert_grep "N9: distributed instructions reject blanket xhigh" \
  "xhigh を一律の既定にしない" "$REPO_ROOT/templates/agent_instructions.md"
assert_grep "N9: English README documents the callable option" \
  "agent_run --difficulty" "$REPO_ROOT/README.md"
assert_grep "N9: English README distinguishes native sub-agent calls" \
  "native sub-agent API" "$REPO_ROOT/README.md"
assert_grep "N9: Japanese README documents the callable option" \
  "agent_run --difficulty" "$REPO_ROOT/README_ja.md"
