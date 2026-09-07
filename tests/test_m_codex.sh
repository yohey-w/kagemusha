#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# M. two CLIs, one loop — Claude Code and Codex CLI.
#
# The claim this group holds up is narrow and testable: SWITCHING THE CLI MUST
# CHANGE THE CALL AND NOTHING ELSE. Same prompt, same SSOT, same instructions
# file, same scaffolding — a different command line, and that is all.
#
#   M1  the scaffolder's asymmetric instructions rule, all three cases
#   M2  the opt-in flags (--codex, --link-skills) and what they refuse to do
#   M3  agent_cli.sh dispatch, argv shape asserted per CLI with fake binaries
#   M3c precedence: an explicit environment variable beats config.env
#   M4  the same prompt reaches both CLIs — proved by running the real
#       morning_brief.sh twice against shims and diffing what arrived
#   M5  no executable in the kit starts an AI CLI outside the two aggregators
#   M6  no mechanism file names one CLI's private paths or tool namespace
#   M7  the Codex conversation-log adapter's own unit tests (band B), when
#       that file is present in the tree
#
# NO AI CLI IS CALLED. Every invocation here lands on a shim in a throwaway
# directory, and the tests assert argv — never model output.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash
# shellcheck disable=SC2154  # globals come from scripts/test.sh

group "M. two CLIs, one loop (Claude Code · Codex)"

M_KIT="$TEST_TMP/m_kit"; kit_copy "$M_KIT"

# ─── M1. one instructions file, two names, asymmetric on purpose ───────────
# The failure this rule exists to prevent is TWO instruction files with
# different contents. Adding a pointer beside your file cannot cause it; and
# generating a second file from a template beside your own is exactly it.
m_scaffold() {  # m_scaffold <fixture-name> [preexisting file=content ...]
  local fx="$TEST_TMP/m_$1"; shift
  kit_copy "$fx"
  local kv
  for kv in "$@"; do printf '%s\n' "${kv#*=}" > "$fx/${kv%%=*}"; done
  "$fx/scripts/setup.sh" > "$fx/.setup.log" 2>&1
  printf '%s' "$fx"
}

M_FRESH="$(m_scaffold fresh)"
assert_file "M1: neither present → AGENTS.md is written" "$M_FRESH/AGENTS.md"
assert_same "M1: …from templates/agent_instructions.md, byte for byte" \
  "$M_FRESH/AGENTS.md" "$M_FRESH/templates/agent_instructions.md"
assert_eq "M1: …and CLAUDE.md is the one-line import, nothing more" \
  "@AGENTS.md" "$(cat "$M_FRESH/CLAUDE.md")"

M_AONLY="$(m_scaffold aonly "AGENTS.md=# mine, for codex")"
assert_grep "M1: AGENTS.md only → the file itself is untouched" \
  "mine, for codex" "$M_AONLY/AGENTS.md"
assert_eq "M1: …and the missing pointer is supplied" \
  "@AGENTS.md" "$(cat "$M_AONLY/CLAUDE.md")"

M_CONLY="$(m_scaffold conly "CLAUDE.md=# mine, for claude")"
assert_absent "M1: CLAUDE.md only → NO AGENTS.md is generated beside it" "$M_CONLY/AGENTS.md"
assert_grep "M1: …the file itself is untouched" "mine, for claude" "$M_CONLY/CLAUDE.md"
assert_grep "M1: …and the migration is printed, not performed" \
  "mv $M_CONLY/CLAUDE.md $M_CONLY/AGENTS.md" "$M_CONLY/.setup.log"

# the pointer is a POINTER: it must never become a second copy of the rules
assert_ne "M1: the pointer is not a second copy of the instructions" \
  "$(cat "$M_FRESH/templates/agent_instructions.md")" "$(cat "$M_FRESH/CLAUDE.md")"
assert_eq "M1: …and it is exactly one line" "1" "$(wc -l < "$M_FRESH/CLAUDE.md")"

# ─── M2. the opt-in flags ──────────────────────────────────────────────────
# .codex/config.toml is NOT part of the default scaffold. It names an absolute
# path only your machine knows and it does nothing until the project is also
# trusted in ~/.codex/config.toml, so shipping it by default would ship a file
# that silently has no effect.
assert_absent "M2: a default scaffold writes no .codex/config.toml" "$M_FRESH/.codex/config.toml"
M_CX="$TEST_TMP/m_codexflag"; kit_copy "$M_CX"
"$M_CX/scripts/setup.sh" --codex > "$M_CX/.setup.log" 2>&1
assert_eq "M2: setup.sh --codex exits 0" "0" "$?"
assert_file "M2: --codex writes .codex/config.toml" "$M_CX/.codex/config.toml"
assert_same "M2: …from templates/codex/config.toml.example" \
  "$M_CX/.codex/config.toml" "$M_CX/templates/codex/config.toml.example"
assert_grep "M2: …and the run says it is inert until the project is trusted" \
  "trust_level" "$M_CX/.setup.log"
# the template has to carry the two things that make it work at all
assert_grep "M2: the Codex template configures the date-stamp hook" \
  "hooks.UserPromptSubmit" "$M_KIT/templates/codex/config.toml.example"
assert_grep "M2: …and the Claude template configures the same thing" \
  "UserPromptSubmit" "$M_KIT/templates/claude/settings.json.example"
assert_ok "M2: the Claude settings template is valid JSON" \
  python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$M_KIT/templates/claude/settings.json.example"
assert_ok "M2: the Codex config template is valid TOML" \
  python3 -c "import tomllib,sys;tomllib.load(open(sys.argv[1],'rb'))" "$M_KIT/templates/codex/config.toml.example"

assert_exit "M2: an unknown flag is refused, not silently ignored" 2 \
  "$M_KIT/scripts/setup.sh" --no-such-flag

# --link-skills, against a fake HOME with only ONE of the two CLIs installed
M_SKHOME="$TEST_TMP/m_skillhome"
mkdir -p "$M_SKHOME/.codex/skills"          # codex present, claude absent
printf 'not ours\n' > "$M_SKHOME/.codex/skills/OCCUPIED"
M_SK="$TEST_TMP/m_skills"; kit_copy "$M_SK"
mkdir -p "$M_SK/templates/skills/OCCUPIED"
HOME="$M_SKHOME" "$M_SK/scripts/setup.sh" --link-skills > "$M_SK/.setup.log" 2>&1
assert_eq "M2: setup.sh --link-skills exits 0" "0" "$?"
assert_eq "M2: an existing skill entry is never replaced" \
  "not ours" "$(cat "$M_SKHOME/.codex/skills/OCCUPIED")"
assert_grep "M2: …and the run says it skipped it" "skip (exists)" "$M_SK/.setup.log"
if [[ -L "$M_SKHOME/.codex/skills/meeting-copilot" ]]; then
  pass "M2: a shipped skill is symlinked (not copied) into the CLI that IS installed"
else
  fail "M2: a shipped skill is symlinked (not copied) into the CLI that IS installed" \
    "$(ls -la "$M_SKHOME/.codex/skills" 2>&1)"
fi
assert_absent "M2: nothing is created for the CLI that is not installed" "$M_SKHOME/.claude"

# ─── M3. dispatch: the argv each CLI actually receives ─────────────────────
# The old design was a comment telling you to edit one of three invocation
# lines, in four files. Nothing checked that you edited them consistently.
# Here the command line is built in one function and asserted here.
M_BIN="$TEST_TMP/m_bin"; mkdir -p "$M_BIN"
M_ARGS="$TEST_TMP/m_argv.txt"
# The prompt is recorded on its own, in $SHIM_ARGS.prompt: a prompt is many
# lines long, so a line-per-argument dump cannot be split back into arguments.
cat > "$M_BIN/claude" <<'SHIM'
#!/usr/bin/env bash
: > "$SHIM_ARGS"; for a in "$@"; do printf '%s\n' "$a" >> "$SHIM_ARGS"; done
# WHICH binary ran, recorded on its own: argv cannot say, and the bug M3c
# pins was codex's argv handed to the claude binary.
basename "$0" > "$SHIM_ARGS.bin"
prev=""; for a in "$@"; do [[ "$prev" == "-p" ]] && printf '%s' "$a" > "$SHIM_ARGS.prompt"; prev="$a"; done
cat > "$SHIM_ARGS.stdin"
printf 'CLAUDE-ANSWER\n'
SHIM
cat > "$M_BIN/codex" <<'SHIM'
#!/usr/bin/env bash
: > "$SHIM_ARGS"; for a in "$@"; do printf '%s\n' "$a" >> "$SHIM_ARGS"; done
# WHICH binary ran, recorded on its own: argv cannot say, and the bug M3c
# pins was codex's argv handed to the claude binary.
basename "$0" > "$SHIM_ARGS.bin"
# codex takes the prompt as the last positional and writes its final message to
# the file named by -o, and only there — stdout is the session banner.
out=""; prev=""; last=""
for a in "$@"; do [[ "$prev" == "-o" ]] && out="$a"; prev="$a"; last="$a"; done
printf '%s' "$last" > "$SHIM_ARGS.prompt"
# whatever arrives on stdin, recorded — `codex exec` treats stdin as EXTRA
# input, so the caller has to close it or a cron run waits for a terminal
cat > "$SHIM_ARGS.stdin"
[[ -n "$out" ]] && printf 'CODEX-ANSWER\n' > "$out"
printf 'banner: this is the session log, not the answer\n'
SHIM
chmod +x "$M_BIN/claude" "$M_BIN/codex"

m_run() {  # m_run <AGENT_CLI> [extra agent_run args...] — echo the answer
  local cli="$1"; shift
  env PATH="$M_BIN:/usr/bin:/bin" SHIM_ARGS="$M_ARGS" AGENT_CLI="$cli" \
      AGENT_CMD="" AGENT_MODEL="" AGENT_MODEL_CLAUDE="" AGENT_MODEL_CODEX="" \
      AGENT_EFFORT="" AGENT_EFFORT_CLAUDE="" AGENT_EFFORT_CODEX="" \
      AGENT_FLAGS="" CODEX_FLAGS="" PROJECT_ROOT="$TEST_TMP/m_root" \
      bash -c 'source "$1/scripts/lib/agent_cli.sh"; shift; agent_run "$@"' _ "$M_KIT" "$@"
}
m_argv() { tr '\n' '|' < "$M_ARGS"; }

assert_eq "M3: claude — the answer comes back on stdout" \
  "CLAUDE-ANSWER" "$(m_run claude --model m1 --effort e1 -- "THE PROMPT")"
assert_eq "M3: claude — argv is -p <prompt> --model --effort" \
  "-p|THE PROMPT|--model|m1|--effort|e1|" "$(m_argv)"

assert_eq "M3: codex — the answer comes from -o, not from stdout" \
  "CODEX-ANSWER" "$(m_run codex --model m1 --effort e1 --no-preamble -- "THE PROMPT")"
M_CODEX_ARGV="$(m_argv)"
for m_want in "exec|" "-m|m1|" "-c|model_reasoning_effort=e1|" "--ephemeral|" "-s|read-only|" "-o|"; do
  case "$M_CODEX_ARGV" in
    *"$m_want"*) pass "M3: codex argv carries: ${m_want//|/ }" ;;
    *) fail "M3: codex argv carries: ${m_want//|/ }" "got: $M_CODEX_ARGV" ;;
  esac
done
assert_eq "M3: codex — the prompt is the LAST argument (a positional, not a flag)" \
  "THE PROMPT" "$(tail -n 1 "$M_ARGS")"

# --write is the only thing that opens the sandbox, and it is per call
m_run codex --write --no-preamble -- "W" > /dev/null
assert_grep "M3: --write selects workspace-write" "workspace-write" "$M_ARGS"
m_run codex --no-preamble -- "R" > /dev/null
assert_no_grep "M3: …and without it the run cannot write" "workspace-write" "$M_ARGS"

# the working root is named, because cron's working directory is $HOME
assert_grep "M3: codex is given an explicit working root (cron's cwd is \$HOME)" \
  "$TEST_TMP/m_root" "$M_ARGS"

# stdin is closed. Under cron there is no terminal, and `codex exec` reads
# stdin as additional input: leave it open and the run waits, then dies on the
# timeout with nothing in the log that says why.
env PATH="$M_BIN:/usr/bin:/bin" SHIM_ARGS="$M_ARGS" AGENT_CLI=codex AGENT_CMD="" \
  bash -c 'source "$1/scripts/lib/agent_cli.sh"; agent_run --no-preamble -- P' _ "$M_KIT" \
  <<< "STDIN-MUST-NOT-REACH-THE-CLI" > /dev/null 2>&1
assert_file "M3: the codex shim recorded what arrived on stdin" "$M_ARGS.stdin"
assert_eq "M3: …and nothing did — stdin is closed for the CLI" \
  "" "$(cat "$M_ARGS.stdin")"

# --ephemeral by default: ~/.codex/sessions is the corpus the distillation lane
# mines, and the machinery's own prompts are not the operator's judgment.
m_run codex --no-preamble -- "E" > /dev/null
assert_grep "M3: codex runs are ephemeral by default (not harvested as yours)" \
  "--ephemeral" "$M_ARGS"
env PATH="$M_BIN:/usr/bin:/bin" SHIM_ARGS="$M_ARGS" AGENT_CLI=codex AGENT_CMD="" \
  AGENT_CLI_RECORD=1 \
  bash -c 'source "$1/scripts/lib/agent_cli.sh"; agent_run --no-preamble -- P' _ "$M_KIT" \
  > /dev/null 2>&1
assert_no_grep "M3: …and AGENT_CLI_RECORD=1 is the way back for debugging" \
  "--ephemeral" "$M_ARGS"

# the read-only preamble: codex exec is agentic unless told otherwise
m_run codex -- "ASK" > /dev/null
assert_grep "M3: a read-only codex call is told not to use tools" "Do not use any tool" "$M_ARGS"
m_run codex --write -- "ASK" > /dev/null
assert_no_grep "M3: …and a --write call is NOT (it has files to touch)" \
  "Do not use any tool" "$M_ARGS"
m_run claude -- "ASK" > /dev/null
assert_no_grep "M3: …and claude never gets the preamble" "Do not use any tool" "$M_ARGS"

# `--flags ""` means no flags. It is not the same as leaving it out — distill.sh
# passes an empty string precisely to keep --dangerously-skip-permissions out.
M_FLAGGED="$(env PATH="$M_BIN:/usr/bin:/bin" SHIM_ARGS="$M_ARGS" AGENT_CLI=claude \
  AGENT_FLAGS="--dangerously-skip-permissions" \
  bash -c 'source "$1/scripts/lib/agent_cli.sh"; agent_run --flags "" -- P >/dev/null; tr "\n" "|" < "$SHIM_ARGS"' _ "$M_KIT")"
assert_no_grep_str "M3: --flags '' keeps the permission flag OUT" \
  "dangerously" "$M_FLAGGED"
M_DEFAULTED="$(env PATH="$M_BIN:/usr/bin:/bin" SHIM_ARGS="$M_ARGS" AGENT_CLI=claude \
  AGENT_FLAGS="--dangerously-skip-permissions" \
  bash -c 'source "$1/scripts/lib/agent_cli.sh"; agent_run -- P >/dev/null; tr "\n" "|" < "$SHIM_ARGS"' _ "$M_KIT")"
case "$M_DEFAULTED" in
  *dangerously*) pass "M3: …while omitting --flags DOES inherit AGENT_FLAGS" ;;
  *) fail "M3: …while omitting --flags DOES inherit AGENT_FLAGS" "got: $M_DEFAULTED" ;;
esac

# detection never starts a CLI, and says so plainly when there is nothing to run
# PATH is emptied INSIDE the shell, not around it: with an empty PATH outside,
# `env` cannot find bash and the check would pass on the wrong error.
M_NOCLI="$(AGENT_CLI=auto AGENT_CMD="" bash -c \
  'export PATH=/nonexistent; source "$1/scripts/lib/agent_cli.sh"; agent_cli_which' _ "$M_KIT" 2>&1)"
assert_nonempty_str "M3: with no CLI on PATH the failure names the keys to set" \
  "$(printf '%s' "$M_NOCLI" | grep -F 'AGENT_CLI' || true)"

# ─── M3b. a prompt too big for argv goes in on stdin ───────────────────────
# Linux caps ONE argv entry at 128 KB. Japanese is 3 bytes a character, and this
# kit builds prompts out of your own material — a live meeting folder measured
# 683 KB, five times the cap. Past it exec fails outright ("Argument list too
# long"), which in a scheduled run is a silent morning with nothing in the log.
# So the switch is automatic and asserted in both directions.
M_BIG="$TEST_TMP/m_big.txt"
python3 -c "import sys;sys.stdout.write('x'*200000)" > "$M_BIG"
m_big_run() {  # m_big_run <cli> — run agent_run with a 200 KB prompt
  env PATH="$M_BIN:/usr/bin:/bin" SHIM_ARGS="$M_ARGS" AGENT_CLI="$1" AGENT_CMD="" \
      AGENT_MODEL="" AGENT_FLAGS="" CODEX_FLAGS="" \
      bash -c 'source "$1/scripts/lib/agent_cli.sh"
               agent_run --no-preamble -- "$(cat "$2")" >/dev/null 2>&1' _ "$M_KIT" "$M_BIG"
}
m_big_run claude
assert_eq "M3b: claude — a 200 KB prompt is NOT in argv" \
  "-p" "$(tr -d '\n' < "$M_ARGS")"
assert_eq "M3b: …it arrived on stdin, whole" "200000" "$(wc -c < "$M_ARGS.stdin" 2>/dev/null || echo 0)"

m_big_run codex
assert_eq "M3b: codex — the positional is the read-from-stdin marker" "-" "$(tail -n 1 "$M_ARGS")"
assert_eq "M3b: …and the prompt arrived on stdin, whole" "200000" "$(wc -c < "$M_ARGS.stdin")"

# and the small case still rides on argv, so the dry runs stay readable
m_run codex --no-preamble -- "SMALL" > /dev/null
assert_eq "M3b: a small prompt still goes in argv" "SMALL" "$(tail -n 1 "$M_ARGS")"
assert_eq "M3b: …with stdin closed" "" "$(cat "$M_ARGS.stdin")"

# the python aggregator draws the same line, for the same reason
M_PY_SCRIPTS="$REPO_ROOT/templates/skills/meeting-copilot/scripts"
assert_ok "M3b: python — a prompt over the cap is routed to stdin" \
  env PYTHONPATH="$M_PY_SCRIPTS" python3 -c "
import sys; sys.path.insert(0, sys.argv[1])
import agent_cli
big = 'x' * 200000
small = 'x' * 100
assert agent_cli.via_stdin(big), 'a 200KB prompt must not go in argv'
assert not agent_cli.via_stdin(small), 'a small prompt should stay in argv'
assert big not in agent_cli.build(big, cli='claude'), 'claude argv still carries it'
assert agent_cli.build(big, cli='codex')[-1] == '-', 'codex needs the - marker'
assert agent_cli.build(small, cli='codex')[-1].endswith(small), 'small prompts stay positional'
" "$M_PY_SCRIPTS"

# ─── M3c. precedence: the environment beats config.env ─────────────────────
# MEASURED ON A REAL INSTALLATION. config.env still held the kit's original keys
# (AGENT_CMD="claude", AGENT_MODEL="claude-opus-4-8"); the operator ran
# `AGENT_CLI=codex ./scripts/morning_brief.sh`; the loop built
#   claude exec -m claude-opus-4-8 …
# — a command line that belongs to no CLI: codex's subcommand, handed to the
# claude binary, carrying a Claude model id. Two causes, both fixed here:
#   · every script does `source config.env` AFTER sourcing the library, and a
#     plain assignment in a config file overwrites what you exported;
#   · AGENT_CMD was treated as "the binary", full stop, so a type it disagreed
#     with produced a mongrel instead of an error.
M_CFG_OLD="$TEST_TMP/m_cfg_old.env"       # the shape that broke: pre-AGENT_CLI keys
cat > "$M_CFG_OLD" <<'CFG'
AGENT_CMD="claude"
AGENT_MODEL="claude-opus-4-8"
AGENT_FLAGS="--dangerously-skip-permissions"
CFG
M_CFG_AUTO="$TEST_TMP/m_cfg_auto.env"     # what config.env.example ships, plus an old CMD
cat > "$M_CFG_AUTO" <<'CFG'
AGENT_CLI="auto"
AGENT_CMD="claude"
CFG
M_CFG_CLAUDE="$TEST_TMP/m_cfg_claude.env" # the type named in the file, not just implied
cat > "$M_CFG_CLAUDE" <<'CFG'
AGENT_CLI="claude"
AGENT_CMD=""
AGENT_MODEL="claude-opus-4-8"
CFG

M_PREC_ERR="$TEST_TMP/m_prec.err"
m_prec() {  # m_prec <config file> [VAR=VAL ...] — the resolved command line
  local cfg="$1"; shift
  env PATH="$M_BIN:/usr/bin:/bin" PROJECT_ROOT="$TEST_TMP/m_root" "$@" \
    bash -c 'source "$1/scripts/lib/agent_cli.sh"; source "$2"
             agent_cli_show --no-preamble -- "<prompt>"' _ "$M_KIT" "$cfg" 2>"$M_PREC_ERR"
}

# the reported case, at the library
M_PREC="$(m_prec "$M_CFG_OLD" AGENT_CLI=codex)"
assert_grep_str "M3c: AGENT_CLI=codex in the environment beats AGENT_CMD in config.env" \
  "cli=codex bin=codex" "$M_PREC"
assert_grep_str "M3c: …so the whole command line is codex's" "codex exec" "$M_PREC"
assert_no_grep_str "M3c: …and NOT the mongrel that was measured" "claude exec" "$M_PREC"
assert_grep_str "M3c: …the model is codex's own default, not the config's Claude id" \
  "-m gpt-5.6-sol" "$M_PREC"
assert_no_grep_str "M3c: …no Claude model id crosses over" "claude-opus-4-8" "$M_PREC"
assert_no_grep_str "M3c: …and no claude-only flag does either" "dangerously" "$M_PREC"
assert_eq "M3c: the contradiction is reported in exactly ONE line, on stderr" \
  "1" "$(wc -l < "$M_PREC_ERR")"
assert_grep "M3c: …naming the key that won" "AGENT_CLI=codex" "$M_PREC_ERR"
assert_grep "M3c: …and the key that was dropped" "AGENT_CMD=claude" "$M_PREC_ERR"

# backward compatibility: the same config with nothing in the environment is the
# claude dialect it has always been, and says nothing on stderr.
M_PREC="$(m_prec "$M_CFG_OLD")"
assert_grep_str "M3c: AGENT_CMD=claude alone still means the claude dialect" \
  "cli=claude bin=claude" "$M_PREC"
assert_grep_str "M3c: …in the -p form, with the config's own model" \
  "claude -p <prompt> --model claude-opus-4-8" "$M_PREC"
assert_empty_str "M3c: …and nothing is warned about (the two keys agree)" \
  "$(cat "$M_PREC_ERR")"

# an unrecognised binary is NOT a contradiction: it is a wrapper for the type
# you named. (The demo's stub distiller is exactly this.)
M_PREC="$(m_prec "$M_CFG_OLD" AGENT_CLI=codex AGENT_CMD="$M_BIN/my-wrapper")"
assert_grep_str "M3c: a wrapper name we do not know is kept, for the type that was named" \
  "cli=codex bin=$M_BIN/my-wrapper" "$M_PREC"
assert_empty_str "M3c: …and it is not warned about" "$(cat "$M_PREC_ERR")"

# the type key itself: the environment beats config.env, both when the file says
# "auto" and when it names the other CLI outright
assert_grep_str "M3c: env AGENT_CLI beats AGENT_CLI=\"auto\" in config.env" \
  "cli=codex" "$(m_prec "$M_CFG_AUTO" AGENT_CLI=codex)"
assert_grep_str "M3c: …and beats a config.env that names the other CLI" \
  "cli=codex" "$(m_prec "$M_CFG_CLAUDE" AGENT_CLI=codex)"
assert_grep_str "M3c: config.env still decides when the environment is silent" \
  "cli=claude bin=claude model=claude-opus-4-8" "$(m_prec "$M_CFG_CLAUDE")"
assert_grep_str "M3c: …and AGENT_CLI=auto in the environment is not a choice, so it does not" \
  "cli=claude" "$(m_prec "$M_CFG_CLAUDE" AGENT_CLI=auto)"

# the dry run prints the four things that were RESOLVED, not just the argv
assert_grep_str "M3c: agent_cli_show names type, executable, model and effort" \
  "# cli=codex bin=codex model=gpt-5.6-sol effort=xhigh" \
  "$(m_prec "$M_CFG_OLD" AGENT_CLI=codex AGENT_EFFORT_CODEX=xhigh)"
assert_grep_str "M3c: …and prints '-' for what nothing set" \
  "effort=-" "$(m_prec "$M_CFG_OLD" AGENT_CLI=codex)"

# a Claude model id aimed AT codex by hand survives every fallback above, so the
# build refuses it — while the keys that set it are still on screen.
m_reject() {  # m_reject [VAR=VAL ...] -- [agent_cli_show args]
  local envs=(); while [[ "$1" != "--" ]]; do envs+=("$1"); shift; done; shift
  env PATH="$M_BIN:/usr/bin:/bin" AGENT_CLI=codex "${envs[@]}" \
    bash -c 'source "$1/scripts/lib/agent_cli.sh"; shift; agent_cli_show "$@" -- P' _ "$M_KIT" "$@"
}
assert_exit "M3c: AGENT_MODEL_CODEX=claude-… fails the build (nothing is spawned)" 2 \
  m_reject AGENT_MODEL_CODEX=claude-opus-4-8 --
assert_exit "M3c: …and so does --model claude-…" 2 \
  m_reject -- --model claude-opus-4-8
assert_grep_str "M3c: …with a message naming the id and the key to change" \
  "AGENT_MODEL_CODEX" "$(m_reject AGENT_MODEL_CODEX=claude-opus-4-8 -- 2>&1)"

# the freeze reads the environment at SOURCE time, so it only works while every
# script sources the library BEFORE config.env. Pin the order; do not trust it.
M_ORDER=""; M_ORDER_N=0
while IFS= read -r m_f; do
  m_lib="$(grep -n 'source .*lib/agent_cli\.sh' "$REPO_ROOT/$m_f" | grep -v '^[0-9]*:#' | head -n1 | cut -d: -f1)"
  m_cfg="$(grep -n 'source "\$CONFIG"' "$REPO_ROOT/$m_f" | head -n1 | cut -d: -f1)"
  [[ -n "$m_lib" && -n "$m_cfg" ]] || continue
  M_ORDER_N=$((M_ORDER_N + 1))
  [[ "$m_lib" -lt "$m_cfg" ]] || M_ORDER="${M_ORDER}${m_f}: library at line $m_lib, config at line $m_cfg"$'\n'
done < <(git -C "$REPO_ROOT" ls-files 'scripts/*.sh')
assert_ge "M3c: the order check found the scripts that do both" "$M_ORDER_N" 2
assert_empty_str "M3c: every one sources the library BEFORE config.env" "$M_ORDER"

# ─── M3d. the reported failure, end to end through the shipped script ──────
# The library-level tests above cannot see WHICH BINARY ran — the bug fed
# codex's argv to the claude binary, and an argv dump looks the same either way.
# So this one runs the real morning_brief.sh against the shims, with the exact
# config.env shape that broke, and reads the binary's own name back.
M_PLOOP="$TEST_TMP/m_prec_loop"; mkdir -p "$M_PLOOP/ssot" "$M_PLOOP/briefs" "$M_PLOOP/logs"
M_PCFG="$TEST_TMP/m_prec_config.env"
cat > "$M_PCFG" <<CFG
PROJECT_ROOT="$M_PLOOP"
SSOT_DIR="\$PROJECT_ROOT/ssot"
BRIEF_DIR="\$PROJECT_ROOT/briefs"
LOG_DIR="\$PROJECT_ROOT/logs"
QUEUE_FILE="\$PROJECT_ROOT/approval_queue.md"
AGENT_CMD="claude"
AGENT_MODEL="claude-opus-4-8"
AGENT_FLAGS="--dangerously-skip-permissions"
AGENT_TIMEOUT=60
NTFY_ENABLED=0
NTFY_TOPIC=""
CFG
M_PARGS="$TEST_TMP/m_prec_brief.txt"
env -i HOME="$TEST_TMP/m_fakehome" PATH="$M_BIN:/usr/bin:/bin" AGENT_CLI=codex \
    LOOP_CONFIG="$M_PCFG" SHIM_ARGS="$M_PARGS" "$M_KIT/scripts/morning_brief.sh" >/dev/null 2>&1
assert_eq "M3d: the CODEX binary is the one that ran, not the config's claude" \
  "codex" "$(cat "$M_PARGS.bin" 2>/dev/null)"
assert_grep "M3d: …with codex's default model" "gpt-5.6-sol" "$M_PARGS"
assert_no_grep "M3d: …and the config's Claude model id never reaches it" \
  "claude-opus-4-8" "$M_PARGS"
assert_no_grep "M3d: …nor the claude-only permission flag" "dangerously" "$M_PARGS"
M_PLOG="$(ls "$M_PLOOP"/logs/morning_brief_2*.log 2>/dev/null | head -n1)"
assert_grep "M3d: …and the dropped key is on the record, in the run's own log" \
  "AGENT_CMD=claude" "${M_PLOG:-/nonexistent}"

# the control: the same config with no AGENT_CLI in the environment is the
# claude run it has always been. Fixing the crossing must not move the default.
M_PARGS2="$TEST_TMP/m_prec_brief_claude.txt"
env -i HOME="$TEST_TMP/m_fakehome" PATH="$M_BIN:/usr/bin:/bin" \
    LOOP_CONFIG="$M_PCFG" SHIM_ARGS="$M_PARGS2" "$M_KIT/scripts/morning_brief.sh" >/dev/null 2>&1
assert_eq "M3d: control — with no AGENT_CLI the same config still runs claude" \
  "claude" "$(cat "$M_PARGS2.bin" 2>/dev/null)"
assert_grep "M3d: …with its own model id" "claude-opus-4-8" "$M_PARGS2"

# ─── M4. the same prompt reaches both CLIs ─────────────────────────────────
# This is the whole claim, run end to end through the shipped morning_brief.sh:
# swap the CLI and the COMMAND changes while the PROMPT does not.
M_LOOP="$TEST_TMP/m_loop"; mkdir -p "$M_LOOP/ssot" "$M_LOOP/briefs" "$M_LOOP/logs"
M_CFG="$TEST_TMP/m_config.env"
m_brief() {  # m_brief <AGENT_CLI> <argv-file> — run the real script with shims
  cat > "$M_CFG" <<CFG
PROJECT_ROOT="$M_LOOP"
SSOT_DIR="\$PROJECT_ROOT/ssot"
BRIEF_DIR="\$PROJECT_ROOT/briefs"
LOG_DIR="\$PROJECT_ROOT/logs"
QUEUE_FILE="\$PROJECT_ROOT/approval_queue.md"
AGENT_CLI="$1"
AGENT_CMD=""
AGENT_MODEL=""
AGENT_FLAGS=""
CODEX_FLAGS=""
AGENT_TIMEOUT=60
NTFY_ENABLED=0
NTFY_TOPIC=""
CFG
  env -i HOME="$TEST_TMP/m_fakehome" PATH="$M_BIN:/usr/bin:/bin" \
      LOOP_CONFIG="$M_CFG" SHIM_ARGS="$2" "$M_KIT/scripts/morning_brief.sh" >/dev/null 2>&1
}
M_A_CLAUDE="$TEST_TMP/m_brief_claude.txt"
M_A_CODEX="$TEST_TMP/m_brief_codex.txt"
m_brief claude "$M_A_CLAUDE"
m_brief codex  "$M_A_CODEX"
assert_file "M4: the claude run reached a CLI" "$M_A_CLAUDE"
assert_file "M4: the codex run reached a CLI" "$M_A_CODEX"
assert_file "M4: …and the claude prompt was captured whole" "$M_A_CLAUDE.prompt"
assert_file "M4: …and the codex prompt was captured whole" "$M_A_CODEX.prompt"

# morning_brief writes files, so it calls --write — which is also why the codex
# side carries no read-only preamble and the two prompts can be compared raw.
assert_eq "M4: BOTH CLIs receive the byte-identical prompt" \
  "$(cat "$M_A_CLAUDE.prompt")" "$(cat "$M_A_CODEX.prompt")"
assert_grep "M4: …and it really is the morning board's prompt" \
  "approval queue" "$M_A_CLAUDE.prompt"
assert_ge "M4: …and it is a whole prompt, not a fragment" \
  "$(wc -l < "$M_A_CLAUDE.prompt")" 15

# what DOES differ is the command line around it
assert_grep "M4: the claude run uses the -p form" "-p" "$M_A_CLAUDE"
assert_no_grep "M4: …and never the exec subcommand" "exec" "$M_A_CLAUDE"
assert_grep "M4: the codex run uses exec" "exec" "$M_A_CODEX"
assert_grep "M4: …with the sandbox opened for the two files it must write" \
  "workspace-write" "$M_A_CODEX"
assert_grep "M4: …and an explicit working root, not cron's \$HOME" \
  "$M_LOOP" "$M_A_CODEX"

# ─── M5. one aggregator per language, and no CLI started outside it ────────
# The old CLI-SWAP comments are gone; this is what keeps them from growing back.
M_AGG_SH="scripts/lib/agent_cli.sh"
M_AGG_PY="templates/skills/meeting-copilot/scripts/agent_cli.py"
assert_file "M5: the bash aggregator exists" "$M_KIT/$M_AGG_SH"
assert_file "M5: the python aggregator exists" "$M_KIT/$M_AGG_PY"

# executables only, comments stripped: a line DESCRIBING the two dialects is
# documentation; a line STARTING one is the thing being banned.
M_STRAY=""
while IFS= read -r m_f; do
  case "$m_f" in "$M_AGG_SH"|"$M_AGG_PY") continue ;; esac
  m_hit="$(sed -e 's/^[[:space:]]*#.*$//' "$REPO_ROOT/$m_f" \
           | grep -nE '(^|[^_[:alnum:]])claude("|'"'"')?[[:space:],]+("|'"'"')?-p([^[:alnum:]]|$)' || true)"
  [[ -n "$m_hit" ]] && M_STRAY="${M_STRAY}${m_f}: ${m_hit}"$'\n'
done < <(git -C "$REPO_ROOT" ls-files 'scripts/*.sh' 'scripts/*.example' \
           'templates/*.py' 'templates/*.sh' '*.example')
assert_empty_str "M5: no executable starts an AI CLI outside the two aggregators" "$M_STRAY"
# control: the detector can see one
M_PROBE="$TEST_TMP/m_probe.sh"
printf '#!/usr/bin/env bash\nclaude -p "$PROMPT" --model x\n' > "$M_PROBE"
assert_nonempty_str "M5: control — a direct invocation IS detected" \
  "$(sed -e 's/^[[:space:]]*#.*$//' "$M_PROBE" \
     | grep -nE '(^|[^_[:alnum:]])claude("|'"'"')?[[:space:],]+("|'"'"')?-p([^[:alnum:]]|$)' || true)"

# ─── M6. the mechanism names no CLI's private paths ────────────────────────
# Scope is deliberate and narrow: the SSOT/judgment/queue FORMS and the scaffold
# manifest. Those are what a user fills in and what a second CLI has to read, so
# a home path or a tool namespace in them makes the loop CLI-shaped. The scripts
# are NOT in scope for paths (they legitimately name both CLIs' config files),
# only for the connector namespace, which is one vendor's wire format.
M_FORMS=(templates/decisions.md templates/tasks.md templates/glossary.md
         templates/people.md templates/approval_queue.md templates/verifiers.md
         templates/system_map.md templates/decisions_journal.md
         templates/judgment_model.md templates/promotion_queue.md
         templates/charter.md templates/agent_instructions.md
         manifests/scaffold.tsv ssot/README.md)
M_LEAK=""
for m_f in "${M_FORMS[@]}"; do
  assert_file "M6: form present: $m_f" "$REPO_ROOT/$m_f"
  # shellcheck disable=SC2088  # the tilde is the STRING being searched for, not a path to expand
  m_hit="$(grep -nE '~/\.claude|\.claude/projects|\.codex/|mcp__' "$REPO_ROOT/$m_f" || true)"
  [[ -n "$m_hit" ]] && M_LEAK="${M_LEAK}${m_f}: ${m_hit}"$'\n'
done
assert_empty_str "M6: no form names one CLI's home paths or tool namespace" "$M_LEAK"
M_MCP=""
while IFS= read -r m_f; do
  m_hit="$(grep -n 'mcp__' "$REPO_ROOT/$m_f" || true)"
  [[ -n "$m_hit" ]] && M_MCP="${M_MCP}${m_f}: ${m_hit}"$'\n'
done < <(git -C "$REPO_ROOT" ls-files 'scripts/*.sh' 'scripts/*.py')
assert_empty_str "M6: no script hard-codes one vendor's connector namespace" "$M_MCP"
assert_nonempty_str "M6: control — the leak detector detects" \
  "$(printf 'x mcp__vendor_tool y\n' | grep -n 'mcp__' || true)"

# the two claims the forms have to make out loud, since M6 only proves absence
assert_grep "M6: the instructions template says plain files are the only canon" \
  "キャッシュ" "$REPO_ROOT/templates/agent_instructions.md"
assert_grep "M6: …and that the steps are the same on either CLI" \
  "手順は CLI で変わらない" "$REPO_ROOT/templates/agent_instructions.md"
assert_grep "M6: ssot/README.md says the same, at the shelf" \
  "キャッシュ" "$REPO_ROOT/ssot/README.md"
assert_grep "M6: …and names git as what arbitrates two live CLIs" \
  "git" "$REPO_ROOT/ssot/README.md"

# ─── M7. the Codex conversation-log adapter's own tests ────────────────────
# Owned by the log-adapter lane. Run them if they are here; say plainly that
# they are not, rather than reporting a green that covered nothing.
assert_file "M7: the Codex log adapter's tests are in the tree" "$REPO_ROOT/tests/unit_codex_logs.py"
assert_ok "M7: the Codex log adapter's unit tests pass" \
  env -C "$REPO_ROOT" python3 -m unittest tests.unit_codex_logs

# ─── M8. the Codex date stamp must leave the hook as JSON ──────────────────
# The two CLIs read the same event and disagree about the wire. Claude Code
# prepends the hook's raw stdout to the turn; Codex parses stdout against a
# schema (`user-prompt-submit.command.output`, embedded in the codex binary,
# `additionalProperties: false`) and refuses anything else. Plain text gets
# "Hook failed: hook returned invalid user prompt submit JSON output" in the
# TUI — and NOTHING in `codex exec`, which drops the output in silence. That
# silence is the reason this test exists: the lane the kit actually automates
# is the one where a broken stamp has no symptom, until a deadline is written
# on the wrong weekday. Measured 2026-09-07 on codex-cli 0.153.4.
#
# The command is RUN, not pattern-matched. A shape assertion on the string
# would pass on a command whose shell quoting is broken, which is precisely
# the failure that is easy to introduce here — the value nests JSON double
# quotes inside a shell single-quoted printf inside a TOML literal.
M_HOOK_CMD="$(python3 -c '
import tomllib, sys
d = tomllib.load(open(sys.argv[1], "rb"))
print(d["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"], end="")
' "$REPO_ROOT/templates/codex/config.toml.example" 2>/dev/null || true)"
assert_nonempty_str "M8: the Codex template parses as TOML and declares a hook command" \
  "$M_HOOK_CMD"
assert_grep_str "M8: …and it is the JSON envelope form, not a bare date" \
  "hookSpecificOutput" "$M_HOOK_CMD"

M_HOOK_OUT="$(bash -c "$M_HOOK_CMD" 2>/dev/null || true)"
assert_nonempty_str "M8: the hook command runs and writes to stdout" "$M_HOOK_OUT"
assert_ok "M8: …and that stdout is valid JSON" \
  env M_HOOK_JSON="$M_HOOK_OUT" python3 -c 'import json, os; json.loads(os.environ["M_HOOK_JSON"])'

M_HOOK_EVT="$(printf '%s' "$M_HOOK_OUT" | python3 -c '
import json, sys
print(json.load(sys.stdin)["hookSpecificOutput"]["hookEventName"], end="")' 2>/dev/null || true)"
assert_eq "M8: …carrying the event name Codex requires" "UserPromptSubmit" "$M_HOOK_EVT"

M_HOOK_CTX="$(printf '%s' "$M_HOOK_OUT" | python3 -c '
import json, sys
print(json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"], end="")' 2>/dev/null || true)"
assert_grep_str "M8: …and the stamp itself, inside additionalContext" "[now] " "$M_HOOK_CTX"
# the substitution really happened: a literal %Y would mean printf swallowed
# the date and shipped the format string to the model.
assert_no_grep_str "M8: …with the date substituted, not the format string" "%Y" "$M_HOOK_CTX"

# control — the form 殿 hit on 2026-09-07: bare `date` output is not JSON, so
# the check above is capable of failing.
assert_nonempty_str "M8: control — the JSON check rejects the plain-text form" \
  "$(bash -c "date '+[now] %Y-%m-%d (%a) %H:%M %Z'" | python3 -c '
import json, sys
try:
    json.load(sys.stdin)
except Exception:
    print("rejected", end="")' 2>/dev/null || true)"

# the asymmetry is deliberate: Claude Code wants the raw text, so nobody
# should "fix" that half by copying the envelope across.
M_CLAUDE_HOOK="$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
print(d["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"], end="")
' "$REPO_ROOT/templates/claude/settings.json.example" 2>/dev/null || true)"
assert_grep_str "M8: the Claude half still emits the stamp as plain text" \
  "date " "$M_CLAUDE_HOOK"
assert_no_grep_str "M8: …and does NOT carry Codex's JSON envelope" \
  "hookSpecificOutput" "$M_CLAUDE_HOOK"
