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
# The generated file is the template with ONE substitution: the hook path has
# to be absolute (a relative one resolves against wherever codex was started),
# and only the installing machine knows what it is. So the contract is not
# "identical" but "identical once the path is put back" — asserted by undoing
# the substitution, which also proves nothing ELSE was rewritten on the way.
M_CX_UNSUB="$TEST_TMP/m_codexflag_unsub.toml"
sed "s|$M_CX|__PROJECT_ROOT__|g" "$M_CX/.codex/config.toml" > "$M_CX_UNSUB"
assert_same "M2: …from templates/codex/config.toml.example, bar the path substitution" \
  "$M_CX_UNSUB" "$M_CX/templates/codex/config.toml.example"
assert_no_grep "M2: …with no placeholder left behind" \
  "__PROJECT_ROOT__" "$M_CX/.codex/config.toml"
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

# ─── M9. the outbound guard: the rule that has to be a control ─────────────
# THE FAILURE THIS GROUP EXISTS FOR IS SILENCE. Measured 2026-09-07 on
# codex-cli 0.153.4: with "outward = ask first" in AGENTS.md and the strictest
# sandbox, `codex exec -s read-only "email the customer …"` called gmail's send
# tool unasked, and when the approval policy refused it, created a draft to the
# real customer instead. The hook below is the machine's "no". But the host
# FAILS OPEN — a hook that is missing, unexecutable, or prints anything the
# schema rejects lets the call through and says nothing — so a broken guard and
# an absent guard look identical from outside. These assertions are the only
# thing that can tell them apart, and they run the script rather than reading
# it, because the failure that is easy to introduce here is a typo in a printf.
M_GUARD_TEMPLATE="$REPO_ROOT/templates/codex/hooks/outbound_guard.sh"
M_PERMIT_TEMPLATE="$REPO_ROOT/templates/codex/hooks/outbound_permit.py"
assert_file "M9: the outbound guard ships in the kit" "$M_GUARD_TEMPLATE"
assert_ok "M9: …and is syntactically valid bash" bash -n "$M_GUARD_TEMPLATE"
assert_ok "M9: …and is executable in the tree" test -x "$M_GUARD_TEMPLATE"
assert_file "M9: the explicit one-shot permit helper ships beside it" "$M_PERMIT_TEMPLATE"
assert_ok "M9: …and its Python is syntactically valid" \
  env PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile "$M_PERMIT_TEMPLATE"

# Run the hook from the same .codex/hooks layout used in a real project. Its
# project binding is deliberately derived from that location, not caller input.
M_PERMIT_ROOT="$TEST_TMP/m_permit_project"
mkdir -p "$M_PERMIT_ROOT/.codex/hooks"
cp "$M_GUARD_TEMPLATE" "$M_PERMIT_TEMPLATE" "$M_PERMIT_ROOT/.codex/hooks/"
chmod +x "$M_PERMIT_ROOT/.codex/hooks/outbound_guard.sh" \
         "$M_PERMIT_ROOT/.codex/hooks/outbound_permit.py"
M_GUARD="$M_PERMIT_ROOT/.codex/hooks/outbound_guard.sh"
M_PERMIT="$M_PERMIT_ROOT/.codex/hooks/outbound_permit.py"

# m_guard PAYLOAD → the hook's stdout for that PreToolUse input
m_guard() { printf '%s' "$1" | bash "$M_GUARD" 2>/dev/null; }
m_output_decision() {  # hook stdout → allow | deny | INVALID
  M_G_OUT="$1" M_G_PY='
import json, os, sys
try: d = json.loads(os.environ["M_G_OUT"])
except Exception: print("INVALID"); sys.exit()
h = d.get("hookSpecificOutput") or {}
print(h.get("permissionDecision") or ("allow" if not h else "INVALID"))
' python3 -c 'import os;exec(os.environ["M_G_PY"])'
}
m_decision() { m_output_decision "$(m_guard "$1")"; }

# the incident itself, and its neighbours
for m_verb in send_email create_draft update_draft reply forward delete_email; do
  assert_eq "M9: gmail.$m_verb is denied" "deny" \
    "$(m_decision "{\"tool_name\":\"mcp__codex_apps__gmail__${m_verb}\",\"tool_input\":{}}")"
done
assert_eq "M9: slack post_message is denied" "deny" \
  "$(m_decision '{"tool_name":"mcp__codex_apps__slack__post_message","tool_input":{}}')"
for m_slack_write in slack_add_reaction slack_complete_file_upload slack_create_canvas \
                     slack_create_conversation slack_create_reminder slack_delete_message \
                     slack_edit_message slack_get_file_upload_url slack_invite_to_conversation \
                     slack_join_conversation slack_leave_conversation slack_schedule_message \
                     slack_send_message_draft slack_update_canvas slack_update_user_profile; do
  assert_eq "M9: Slack $m_slack_write is denied by the closed namespace" "deny" \
    "$(m_decision "{\"tool_name\":\"mcp__codex_apps__slack__${m_slack_write}\",\"tool_input\":{}}")"
done
assert_eq "M9: an unknown Slack operation fails closed" "deny" \
  "$(m_decision '{"tool_name":"mcp__codex_apps__slack__slack_future_operation","tool_input":{}}')"
assert_eq "M9: a connector publish operation is denied" "deny" \
  "$(m_decision '{"tool_name":"mcp__example__publish_page","tool_input":{}}')"

# reading is not sending. A guard that also blocks the sweep gets switched off,
# and a guard that is switched off protects nothing.
assert_eq "M9: gmail.search_emails is allowed" "allow" \
  "$(m_decision '{"tool_name":"mcp__codex_apps__gmail__search_emails","tool_input":{}}')"
for m_slack_read in slack_get_reactions slack_list_channel_members slack_list_starred_items \
                    slack_list_user_channels slack_list_user_conversations slack_list_user_groups \
                    slack_list_workspaces slack_read_canvas slack_read_channel slack_read_file \
                    slack_read_thread slack_read_user_profile slack_search_channels \
                    slack_search_emojis slack_search_public slack_search_public_and_private \
                    slack_search_users; do
  assert_eq "M9: Slack $m_slack_read remains available for inbound reads" "allow" \
    "$(m_decision "{\"tool_name\":\"mcp__codex_apps__slack__${m_slack_read}\",\"tool_input\":{}}")"
done
assert_eq "M9: an unrelated connector read is allowed" "allow" \
  "$(m_decision '{"tool_name":"mcp__codex_apps__google-drive__search_files","tool_input":{}}')"

# the shell is out of scope ON PURPOSE: git push and rm are reversible-by-history
# operations this loop deliberately leaves unattended, and a substring rule over
# command text would eat them.
assert_eq "M9: the shell is never matched, whatever the command says" "allow" \
  "$(m_decision '{"tool_name":"Bash","tool_input":{"command":"git push && rm -rf ./tmp && echo post"}}')"
assert_eq "M9: …nor is a connector merely NAMED after a verb (postgres)" "allow" \
  "$(m_decision '{"tool_name":"mcp__postgres__query","tool_input":{}}')"

# ── the same send, one level down: hidden inside `exec` ───────────────────
# MEASURED 2026-09-13 (local/state/codex_desktop_test_20260913/, test_matrix.md
# §再測 + T7_rootcause.txt). The desktop app shows the model three tools —
# exec · spawn_agent · wait_agent — and reaches Gmail from JavaScript INSIDE
# exec: `tools.mcp__codex_apps__gmail_create_draft({to:"…"})`. tool_name is
# therefore "exec", the assertions above never see a connector name, and the
# draft was created with the hook installed and trusted. The CLI has the same
# shape: 9,222 of 9,222 code-executing calls across 83 rollouts in
# ~/.codex/sessions/2026/09/ are `exec`, several carrying gmail_search_emails.
#
# The payloads below are built with json.dumps rather than written by hand,
# because the escaping is the interesting part: the code arrives inside a JSON
# string, so its quotes are \" and its newlines are \n, and a fixture that
# skips that tests a shape which never arrives.
m_exec_payload() {  # m_exec_payload JS [TOOL_NAME] → one PreToolUse payload
  M_JS="$1" M_TOOL="${2:-exec}" python3 -c '
import json, os
print(json.dumps({"tool_name": os.environ["M_TOOL"],
                  "tool_input": {"input": os.environ["M_JS"]},
                  "cwd": "/tmp", "session_id": "m9-exec"}), end="")'
}
m_exec_decision() { m_decision "$(m_exec_payload "$1" "${2:-exec}")"; }

# (a) the incident itself, in the spelling that was measured
assert_eq "M9: a draft created from inside exec is denied" "deny" \
  "$(m_exec_decision 'const r = await tools.mcp__codex_apps__gmail_create_draft({to:"test@example.invalid",subject:"s",body:"b"}); text(r);')"
assert_eq "M9: …and a send from inside exec, whatever its namespace spelling" "deny" \
  "$(m_exec_decision 'await tools.mcp__codex_apps__gmail__send_email({to:"test@example.invalid"});')"
assert_eq "M9: …and under another name for the same code tool (node_repl)" "deny" \
  "$(m_exec_decision 'await tools.mcp__codex_apps__gmail_send_email({to:"test@example.invalid"});' node_repl)"

# (b) reading from inside exec still works, or the guard gets switched off.
# This is the real inbound shape, lifted from a rollout: list the table, then
# search. Neither is a send.
M_EXEC_READ="$(cat <<'JS'
text(ALL_TOOLS.filter(x=>/slack/.test(x.name)).map(x=>({name:x.name,summary:x.description.slice(0,160)})));
text(await tools.mcp__codex_apps__gmail_search_emails({query:'{from:someone@example.test} after:2026/09/04 -in:trash',max_results:30}));
JS
)"
assert_eq "M9: gmail_search_emails from inside exec is allowed" "allow" \
  "$(m_exec_decision "$M_EXEC_READ")"
assert_eq "M9: a Slack read from inside exec is allowed (desktop doubles the prefix)" "allow" \
  "$(m_exec_decision 'const r = await tools.mcp__codex_apps__slack_slack_read_thread({channel_id:"C1",limit:8}); text(r);')"
assert_eq "M9: naming read tools in a list, without calling one, is allowed" "allow" \
  "$(m_exec_decision 'for (const n of ["mcp__codex_apps__slack_slack_read_channel","mcp__codex_apps__slack_slack_read_thread"]) text(ALL_TOOLS.find(t=>t.name===n));')"
# the discriminator: a bare verb with no mcp__ anchor is shell text, not a call
assert_eq "M9: a shell command that merely mentions create_draft is allowed" "allow" \
  "$(m_exec_decision 'const r = await tools.exec_command({cmd:"grep -rn create_draft .codex/hooks"}); text(r);')"
assert_eq "M9: …and the shell inside exec is still the shell (git push, rm)" "allow" \
  "$(m_exec_decision 'text(await tools.exec_command({cmd:"git push && rm -rf ./tmp && echo post"}));')"
# a Slack write whose name carries no outbound verb: the closed namespace has
# to reach inside exec too, or add_reaction walks straight past the verb list
assert_eq "M9: a Slack write from inside exec fails closed (no verb in its name)" "deny" \
  "$(m_exec_decision 'await tools.mcp__codex_apps__slack_slack_add_reaction({channel:"C1",name:"eyes"});')"

# (c) the name resolved at run time instead of called by name
assert_eq "M9: tools[\"…send_message\"] from inside exec is denied" "deny" \
  "$(m_exec_decision 'const f = tools["mcp__codex_apps__slack_slack_send_message"]; await f({channel:"C1",text:"hi"});')"
assert_eq "M9: tools[] indexed by a computed name is denied (reads never need it)" "deny" \
  "$(m_exec_decision 'const f = tools[pickedName]; await f({to:"test@example.invalid"});')"
assert_eq "M9: the tool table enumerated as data is denied" "deny" \
  "$(m_exec_decision 'const t = Object.values(tools).find(f=>f.length===1); await t({});')"
assert_eq "M9: a tool resolved out of ALL_TOOLS and called is denied" "deny" \
  "$(m_exec_decision 'await ALL_TOOLS.find(t=>/create_draft/.test(t.name))({to:"test@example.invalid"});')"
assert_eq "M9: a name built by interpolation is denied" \
  "deny" "$(m_exec_decision 'const n = `mcp__codex_apps__${app}_send_email`; await tools[n]({});')"

# (d) the name split across a concatenation, glued back together before the
# verb list ever sees it
assert_eq "M9: a name split across a concatenation is rejoined, then denied" "deny" \
  "$(m_exec_decision 'const n = "mcp__codex_apps__gmail_" + "send_email"; await tools[n]({to:"test@example.invalid"});')"
assert_eq "M9: …and the join is what catches it, with no call in sight" "deny" \
  "$(m_exec_decision 'const n = "mcp__codex_apps__gmail_" + "send_email"; text(n);')"

# the reason must route to the queue and must NOT quote the code back: the
# reason is interpolated into JSON with no escaping, and the code holds the
# message body.
M_EXEC_REASON="$(M_G_OUT="$(m_guard "$(m_exec_payload 'await tools.mcp__codex_apps__gmail_create_draft({to:"test@example.invalid",body:"secret body"});')")" \
  python3 -c 'import json,os;print(json.loads(os.environ["M_G_OUT"])["hookSpecificOutput"]["permissionDecisionReason"],end="")')"
assert_grep_str "M9: the exec deny names where the message goes instead" \
  "approval_queue.md" "$M_EXEC_REASON"
assert_grep_str "M9: …and names the connector it caught" \
  "gmail_create_draft" "$M_EXEC_REASON"
assert_no_grep_str "M9: …and never quotes the code (the body would land in the JSON)" \
  "secret body" "$M_EXEC_REASON"

# fail OPEN on code it cannot read, by design and by symmetry: nothing here
# parses JSON, and on the desktop app exec is the ONLY tool the model has, so a
# rule that denied whatever it could not recognise would be an off switch.
assert_eq "M9: an exec whose code the guard cannot find is still allowed" "allow" \
  "$(m_decision '{"tool_name":"exec"}')"

# fail CLOSED on an unreadable payload: loudly wrong is recoverable, quietly
# absent is the failure this file exists to prevent.
assert_eq "M9: an input with no tool_name is denied, not waved through" "deny" \
  "$(m_decision '{"hook_event_name":"PreToolUse"}')"
assert_eq "M9: …and so is empty input" "deny" "$(m_decision '')"

# every branch must be valid JSON, or codex drops it and the call proceeds
M_GUARD_BAD=""
for m_p in '{"tool_name":"mcp__codex_apps__gmail__create_draft"}' \
           '{"tool_name":"mcp__codex_apps__gmail__search_emails"}' \
           '{"tool_name":"Bash","tool_input":{"command":"ls"}}' \
           '' ; do
  M_G_OUT="$(m_guard "$m_p")" python3 -c 'import json,os;json.loads(os.environ["M_G_OUT"])' 2>/dev/null \
    || M_GUARD_BAD="${M_GUARD_BAD}${m_p:-<empty>}"$'\n'
done
assert_empty_str "M9: every branch prints valid JSON (the host drops anything else, in silence)" "$M_GUARD_BAD"

# the deny must carry a non-empty reason (the binary refuses a bare deny) and
# that reason must route the agent to the queue rather than to another verb.
M_GUARD_REASON="$(M_G_OUT="$(m_guard '{"tool_name":"mcp__codex_apps__gmail__send_email"}')" \
  python3 -c 'import json,os;print(json.loads(os.environ["M_G_OUT"])["hookSpecificOutput"]["permissionDecisionReason"],end="")')"
assert_nonempty_str "M9: the deny carries a reason (a bare deny is refused by codex)" "$M_GUARD_REASON"
assert_grep_str "M9: …and the reason names where the message goes instead" \
  "approval_queue.md" "$M_GUARD_REASON"

# the pass must be the EMPTY document. `permissionDecision: allow` is rejected
# by the binary ("PreToolUse hook returned unsupported permissionDecision:allow"),
# so there is no way to say yes and an over-helpful edit here would fail open.
assert_eq "M9: the pass is the empty document, since the schema has no yes" \
  "{}" "$(m_guard '{"tool_name":"Bash","tool_input":{"command":"ls"}}')"

# ── one-shot Gmail permit: review, exact binding, expiry and atomic claim ──
M_SEND_INPUT="$M_PERMIT_ROOT/send-input.json"
cat > "$M_SEND_INPUT" <<'JSON'
{"to":"to@example.test","cc":"cc@example.test","bcc":"","subject":"Approved subject","payload":{"body":{"content":"Approved body","content_type":"text/plain"},"attachments":[{"file_id":"file-1","name":"report.pdf"}]},"reply_message_id":"message-1","optional":null}
JSON
m_review() { python3 "$M_PERMIT" review --tool-input "$1" --tool "${2:-gmail}"; }
m_hash() { m_review "$1" "${2:-gmail}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["sha256"])'; }
m_issue() {  # input session [ttl] [tool]
  local input="$1" session="$2" ttl="${3:-300}" tool="${4:-gmail}" hash
  hash="$(m_hash "$input" "$tool")"
  python3 "$M_PERMIT" issue --tool-input "$input" --tool "$tool" --expected-sha256 "$hash" \
    --project-root "$M_PERMIT_ROOT" --session-id "$session" --ttl-seconds "$ttl" \
    --approval-ref "TEST-$session" --approval-quote "synthetic explicit approval" \
    --confirm-user-approved >/dev/null
}
m_envelope() {  # input session cwd [tool]
  M_INPUT="$1" M_SESSION="$2" M_CWD="$3" \
  M_TOOL="${4:-mcp__codex_apps__gmail__send_email}" python3 -c '
import json, os
with open(os.environ["M_INPUT"], encoding="utf-8") as f: tool_input=json.load(f)
print(json.dumps({"tool_name":os.environ["M_TOOL"], "tool_input":tool_input,
                  "session_id":os.environ["M_SESSION"], "cwd":os.environ["M_CWD"]}))'
}

M_REVIEW_OUT="$(python3 "$M_PERMIT" review --tool-input "$M_SEND_INPUT")"
assert_grep_str "M9: review exposes the complete canonical payload" "Approved body" "$M_REVIEW_OUT"
assert_grep_str "M9: …and its SHA-256" '"sha256"' "$M_REVIEW_OUT"
assert_grep_str "M9: omitted selector remains backward-compatible Gmail" \
  'mcp__codex_apps__gmail__send_email' "$M_REVIEW_OUT"
assert_exit "M9: the tool selector is a closed allowlist" 2 \
  python3 "$M_PERMIT" review --tool-input "$M_SEND_INPUT" --tool arbitrary
assert_exit "M9: issue uses the same closed tool selector" 2 \
  python3 "$M_PERMIT" issue --tool-input "$M_SEND_INPUT" --tool arbitrary \
    --expected-sha256 ignored --project-root "$M_PERMIT_ROOT" --session-id bad-tool \
    --approval-ref TEST --approval-quote approved --confirm-user-approved
assert_absent "M9: review alone writes no permit" "$M_PERMIT_ROOT/.codex/outbound-permits"
assert_exit "M9: issue refuses to treat a permit as approval" 1 \
  python3 "$M_PERMIT" issue --tool-input "$M_SEND_INPUT" \
    --expected-sha256 "$(m_hash "$M_SEND_INPUT")" --project-root "$M_PERMIT_ROOT" \
    --session-id no-confirm --approval-ref TEST --approval-quote approved

M_BASE_PAYLOAD="$(m_envelope "$M_SEND_INPUT" sess-none "$M_PERMIT_ROOT")"
assert_eq "M9: Gmail send without a permit stays denied" "deny" "$(m_decision "$M_BASE_PAYLOAD")"

m_issue "$M_SEND_INPUT" sess-exact
M_EXACT_PAYLOAD="$(m_envelope "$M_SEND_INPUT" sess-exact "$M_PERMIT_ROOT")"
assert_eq "M9: an exact approved Gmail send is allowed once" "allow" "$(m_decision "$M_EXACT_PAYLOAD")"
assert_eq "M9: the claimed permit cannot be reused" "deny" "$(m_decision "$M_EXACT_PAYLOAD")"

# Every send field is inside the canonical hash. A failed mismatch must not
# consume the ticket: the approved baseline immediately after it still passes.
M_MUT_DIR="$M_PERMIT_ROOT/mutations"; mkdir -p "$M_MUT_DIR"
M_BASE="$M_SEND_INPUT" M_MUT_DIR="$M_MUT_DIR" python3 -c '
import copy, json, os
with open(os.environ["M_BASE"], encoding="utf-8") as f: base=json.load(f)
changes = {
 "payload.body.content": lambda d: d["payload"]["body"].__setitem__("content", d["payload"]["body"]["content"] + "!"),
 "to": lambda d: d.__setitem__("to", "other@example.test"),
 "cc": lambda d: d.__setitem__("cc", "other-cc@example.test"),
 "bcc": lambda d: d.__setitem__("bcc", "hidden@example.test"),
 "subject": lambda d: d.__setitem__("subject", d["subject"] + "!"),
 "payload.attachments": lambda d: d["payload"].__setitem__("attachments", [{"file_id":"file-2"}]),
 "reply_message_id": lambda d: d.__setitem__("reply_message_id", "message-2"),
 "extra": lambda d: d.__setitem__("new_field", "not approved"),
}
for name, change in changes.items():
    value=copy.deepcopy(base); change(value)
    with open(os.path.join(os.environ["M_MUT_DIR"], name+".json"), "w", encoding="utf-8") as f:
        json.dump(value, f)
'
for m_field in payload.body.content to cc bcc subject payload.attachments reply_message_id extra; do
  m_session="sess-mutate-$m_field"
  m_issue "$M_SEND_INPUT" "$m_session"
  assert_eq "M9: changing $m_field is denied" "deny" \
    "$(m_decision "$(m_envelope "$M_MUT_DIR/$m_field.json" "$m_session" "$M_PERMIT_ROOT")")"
  assert_eq "M9: …without consuming the exact permit ($m_field)" "allow" \
    "$(m_decision "$(m_envelope "$M_SEND_INPUT" "$m_session" "$M_PERMIT_ROOT")")"
done

# Omitted and null object fields are the one declared equivalence.
M_OMITTED="$M_MUT_DIR/omitted.json"
M_BASE="$M_SEND_INPUT" M_OUT="$M_OMITTED" python3 -c '
import json,os
d=json.load(open(os.environ["M_BASE"])); d.pop("optional")
json.dump(d,open(os.environ["M_OUT"],"w"))'
m_issue "$M_SEND_INPUT" sess-null
assert_eq "M9: omitted and null object fields are equivalent" "allow" \
  "$(m_decision "$(m_envelope "$M_OMITTED" sess-null "$M_PERMIT_ROOT")")"

m_issue "$M_SEND_INPUT" sess-bound
assert_eq "M9: a permit is denied in another session" "deny" \
  "$(m_decision "$(m_envelope "$M_SEND_INPUT" wrong-session "$M_PERMIT_ROOT")")"
assert_eq "M9: …and remains usable in its bound session" "allow" \
  "$(m_decision "$(m_envelope "$M_SEND_INPUT" sess-bound "$M_PERMIT_ROOT")")"

m_issue "$M_SEND_INPUT" sess-project
assert_eq "M9: a permit is denied outside its bound project" "deny" \
  "$(m_decision "$(m_envelope "$M_SEND_INPUT" sess-project /tmp)")"
assert_eq "M9: …and remains usable in its bound project" "allow" \
  "$(m_decision "$(m_envelope "$M_SEND_INPUT" sess-project "$M_PERMIT_ROOT")")"

m_issue "$M_SEND_INPUT" sess-tool
assert_eq "M9: no permit opens another outward tool" "deny" \
  "$(m_decision "$(m_envelope "$M_SEND_INPUT" sess-tool "$M_PERMIT_ROOT" mcp__codex_apps__gmail__create_draft)")"
assert_eq "M9: …and only the exact Gmail send can claim it" "allow" \
  "$(m_decision "$(m_envelope "$M_SEND_INPUT" sess-tool "$M_PERMIT_ROOT")")"

# ── one-shot Slack permit: exact wire name and complete argument binding ──
M_SLACK_TOOL='mcp__codex_apps__slack__slack_send_message'
M_SLACK_JS_TOOL='mcp__codex_apps__slack_slack_send_message'
M_SLACK_INPUT="$M_PERMIT_ROOT/slack-input.json"
cat > "$M_SLACK_INPUT" <<'JSON'
{"channel_id":"C0ABC12345","message":"Approved Slack body","thread_ts":"1700000000.000001","reply_broadcast":true,"draft_id":null}
JSON
M_SLACK_REVIEW="$(m_review "$M_SLACK_INPUT" slack)"
assert_grep_str "M9: Slack review names the exact hook wire tool" "$M_SLACK_TOOL" "$M_SLACK_REVIEW"
assert_no_grep_str "M9: …not the JavaScript wrapper spelling" "$M_SLACK_JS_TOOL" "$M_SLACK_REVIEW"
assert_grep_str "M9: Slack review exposes the exact message" "Approved Slack body" "$M_SLACK_REVIEW"
assert_no_grep_str "M9: schema-supplied draft_id:null is canonicalized as omitted" \
  'draft_id' "$M_SLACK_REVIEW"

M_SLACK_NONE="$(m_envelope "$M_SLACK_INPUT" slack-none "$M_PERMIT_ROOT" "$M_SLACK_TOOL")"
assert_eq "M9: Slack send without a permit stays denied" "deny" "$(m_decision "$M_SLACK_NONE")"
m_issue "$M_SLACK_INPUT" slack-exact 300 slack
M_SLACK_EXACT="$(m_envelope "$M_SLACK_INPUT" slack-exact "$M_PERMIT_ROOT" "$M_SLACK_TOOL")"
assert_eq "M9: an exact approved Slack send is allowed once" "allow" "$(m_decision "$M_SLACK_EXACT")"
assert_eq "M9: the claimed Slack permit cannot be reused" "deny" "$(m_decision "$M_SLACK_EXACT")"

M_SLACK_MUT_DIR="$M_PERMIT_ROOT/slack-mutations"; mkdir -p "$M_SLACK_MUT_DIR"
M_BASE="$M_SLACK_INPUT" M_MUT_DIR="$M_SLACK_MUT_DIR" python3 -c '
import copy, json, os
with open(os.environ["M_BASE"], encoding="utf-8") as f: base=json.load(f)
changes = {
 "channel_id": lambda d: d.__setitem__("channel_id", "C0OTHER123"),
 "message": lambda d: d.__setitem__("message", d["message"] + "!"),
 "thread_ts": lambda d: d.__setitem__("thread_ts", "1700000000.999999"),
 "reply_broadcast": lambda d: d.__setitem__("reply_broadcast", False),
 "extra": lambda d: d.__setitem__("unfurl_links", False),
}
for name, change in changes.items():
    value=copy.deepcopy(base); change(value)
    with open(os.path.join(os.environ["M_MUT_DIR"], name+".json"), "w", encoding="utf-8") as f:
        json.dump(value, f)
'
for m_field in channel_id message thread_ts reply_broadcast extra; do
  m_session="slack-mutate-$m_field"
  m_issue "$M_SLACK_INPUT" "$m_session" 300 slack
  assert_eq "M9: changing Slack $m_field is denied" "deny" \
    "$(m_decision "$(m_envelope "$M_SLACK_MUT_DIR/$m_field.json" "$m_session" "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"
  assert_eq "M9: …without consuming the exact Slack permit ($m_field)" "allow" \
    "$(m_decision "$(m_envelope "$M_SLACK_INPUT" "$m_session" "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"
done

M_SLACK_OMITTED="$M_SLACK_MUT_DIR/draft-omitted.json"
M_BASE="$M_SLACK_INPUT" M_OUT="$M_SLACK_OMITTED" python3 -c '
import json,os
d=json.load(open(os.environ["M_BASE"])); d.pop("draft_id")
json.dump(d,open(os.environ["M_OUT"],"w"))'
m_issue "$M_SLACK_INPUT" slack-null 300 slack
assert_eq "M9: Slack draft_id:null and omission are equivalent" "allow" \
  "$(m_decision "$(m_envelope "$M_SLACK_OMITTED" slack-null "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"

for m_bad_case in empty nonobject draft missing-message bad-broadcast broadcast-without-thread too-long; do
  case "$m_bad_case" in
    empty) printf '{}' > "$M_SLACK_MUT_DIR/$m_bad_case.json" ;;
    nonobject) printf '[]' > "$M_SLACK_MUT_DIR/$m_bad_case.json" ;;
    draft) printf '{"channel_id":"C0ABC12345","message":"x","draft_id":"DRAFT-1"}' > "$M_SLACK_MUT_DIR/$m_bad_case.json" ;;
    missing-message) printf '{"channel_id":"C0ABC12345"}' > "$M_SLACK_MUT_DIR/$m_bad_case.json" ;;
    bad-broadcast) printf '{"channel_id":"C0ABC12345","message":"x","reply_broadcast":"yes"}' > "$M_SLACK_MUT_DIR/$m_bad_case.json" ;;
    broadcast-without-thread) printf '{"channel_id":"C0ABC12345","message":"x","reply_broadcast":true}' > "$M_SLACK_MUT_DIR/$m_bad_case.json" ;;
    too-long) M_OUT="$M_SLACK_MUT_DIR/$m_bad_case.json" python3 -c \
      'import json,os;json.dump({"channel_id":"C0ABC12345","message":"x"*5001},open(os.environ["M_OUT"],"w"))' ;;
  esac
  assert_exit "M9: invalid Slack payload is rejected ($m_bad_case)" 1 \
    python3 "$M_PERMIT" review --tool slack --tool-input "$M_SLACK_MUT_DIR/$m_bad_case.json"
done
assert_exit "M9: Slack issue also rejects a non-null draft_id" 1 \
  python3 "$M_PERMIT" issue --tool slack --tool-input "$M_SLACK_MUT_DIR/draft.json" \
    --expected-sha256 0000000000000000000000000000000000000000000000000000000000000000 \
    --project-root "$M_PERMIT_ROOT" --session-id slack-draft \
    --approval-ref TEST --approval-quote approved --confirm-user-approved
M_SLACK_TOP="$M_SLACK_MUT_DIR/top-level.json"
printf '{"channel_id":"C0ABC12345","message":"top","reply_broadcast":false}' > "$M_SLACK_TOP"
assert_ok "M9: reply_broadcast=false is valid without a thread" \
  python3 "$M_PERMIT" review --tool slack --tool-input "$M_SLACK_TOP"
M_SLACK_5000="$M_SLACK_MUT_DIR/5000.json"
M_OUT="$M_SLACK_5000" python3 -c \
  'import json,os;json.dump({"channel_id":"C0ABC12345","message":"x"*5000},open(os.environ["M_OUT"],"w"))'
assert_ok "M9: a 5000-character Slack message remains valid" \
  python3 "$M_PERMIT" review --tool slack --tool-input "$M_SLACK_5000"

m_issue "$M_SLACK_INPUT" slack-js 300 slack
assert_eq "M9: the JavaScript Slack spelling cannot claim a wire permit" "deny" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-js "$M_PERMIT_ROOT" "$M_SLACK_JS_TOOL")")"
assert_eq "M9: …and the exact wire call can still claim it" "allow" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-js "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"

m_issue "$M_SLACK_INPUT" gmail-not-slack 300 gmail
assert_eq "M9: a Gmail permit cannot open exact Slack" "deny" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" gmail-not-slack "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"
assert_eq "M9: …and remains usable for exact Gmail" "allow" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" gmail-not-slack "$M_PERMIT_ROOT")")"
m_issue "$M_SLACK_INPUT" slack-not-gmail 300 slack
assert_eq "M9: a Slack permit cannot open exact Gmail" "deny" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-not-gmail "$M_PERMIT_ROOT")")"
assert_eq "M9: …and remains usable for exact Slack" "allow" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-not-gmail "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"

m_issue "$M_SLACK_INPUT" slack-bound 300 slack
assert_eq "M9: a Slack permit is denied in another session" "deny" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" wrong-session "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"
assert_eq "M9: …and remains usable in its bound Slack session" "allow" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-bound "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"
m_issue "$M_SLACK_INPUT" slack-project 300 slack
assert_eq "M9: a Slack permit is denied outside its project" "deny" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-project /tmp "$M_SLACK_TOOL")")"
assert_eq "M9: …and remains usable inside its Slack project" "allow" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-project "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"

# Claim validates the issuer's time window as data, not merely the expiry.
# Python's bool is an int subclass, so exact type checks are required here.
m_tamper_permit() {  # session mutation
  M_PENDING="$M_PERMIT_ROOT/.codex/outbound-permits/pending" \
  M_SESSION="$1" M_MUTATION="$2" python3 -c '
import json, os, pathlib, time
for p in pathlib.Path(os.environ["M_PENDING"]).glob("*.json"):
    with p.open(encoding="utf-8") as f: d=json.load(f)
    if d["session_id"] != os.environ["M_SESSION"]: continue
    mutation=os.environ["M_MUTATION"]
    if mutation == "future":
        d["created_at"]=int(time.time()) + 60; d["expires_at"]=d["created_at"] + 300
    elif mutation == "overlong": d["expires_at"]=d["created_at"] + 901
    elif mutation == "zero": d["expires_at"]=d["created_at"]
    elif mutation == "reverse": d["expires_at"]=d["created_at"] - 1
    elif mutation == "created-bool": d["created_at"]=True
    elif mutation == "expires-bool": d["expires_at"]=True
    elif mutation == "version-bool": d["version"]=True
    with p.open("w", encoding="utf-8") as f: json.dump(d, f)
    break
'
}
m_drop_pending() {  # session
  M_PENDING="$M_PERMIT_ROOT/.codex/outbound-permits/pending" M_SESSION="$1" python3 -c '
import json, os, pathlib
for p in pathlib.Path(os.environ["M_PENDING"]).glob("*.json"):
    with p.open(encoding="utf-8") as f: d=json.load(f)
    if d.get("session_id") == os.environ["M_SESSION"]: p.unlink(); break
'
}
for m_time_case in future overlong zero reverse created-bool expires-bool version-bool; do
  m_session="sess-time-$m_time_case"
  m_issue "$M_SEND_INPUT" "$m_session"
  m_tamper_permit "$m_session" "$m_time_case"
  assert_eq "M9: a $m_time_case permit is denied" "deny" \
    "$(m_decision "$(m_envelope "$M_SEND_INPUT" "$m_session" "$M_PERMIT_ROOT")")"
  m_drop_pending "$m_session"
done

m_issue "$M_SEND_INPUT" sess-expired
M_PENDING="$M_PERMIT_ROOT/.codex/outbound-permits/pending" python3 -c '
import json, os, pathlib, time
for p in pathlib.Path(os.environ["M_PENDING"]).glob("*.json"):
    d=json.load(open(p))
    if d["session_id"] == "sess-expired":
        now=int(time.time()); d["created_at"]=now - 2; d["expires_at"]=now - 1
        json.dump(d,open(p,"w")); break'
assert_eq "M9: an expired permit is denied" "deny" \
  "$(m_decision "$(m_envelope "$M_SEND_INPUT" sess-expired "$M_PERMIT_ROOT")")"

assert_exit "M9: Slack issue rejects TTL zero" 1 \
  m_issue "$M_SLACK_INPUT" slack-ttl-zero 0 slack
assert_exit "M9: Slack issue rejects TTL above 900" 1 \
  m_issue "$M_SLACK_INPUT" slack-ttl-over 901 slack
assert_ok "M9: Slack issue accepts the 900-second boundary" \
  m_issue "$M_SLACK_INPUT" slack-ttl-900 900 slack
assert_eq "M9: …and that boundary permit is claimable" "allow" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-ttl-900 "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"

m_issue "$M_SLACK_INPUT" slack-expired 300 slack
M_PENDING="$M_PERMIT_ROOT/.codex/outbound-permits/pending" python3 -c '
import json, os, pathlib, time
for p in pathlib.Path(os.environ["M_PENDING"]).glob("*.json"):
    d=json.load(open(p))
    if d["session_id"] == "slack-expired":
        now=int(time.time()); d["created_at"]=now - 2; d["expires_at"]=now - 1
        json.dump(d,open(p,"w")); break'
assert_eq "M9: an expired Slack permit is denied" "deny" \
  "$(m_decision "$(m_envelope "$M_SLACK_INPUT" slack-expired "$M_PERMIT_ROOT" "$M_SLACK_TOOL")")"

M_BAD_JSON="{\"tool_name\":\"mcp__codex_apps__gmail__send_email\",\"session_id\":\"bad\",\"cwd\":\"$M_PERMIT_ROOT\",\"tool_input\":"
assert_eq "M9: malformed send JSON fails closed" "deny" "$(m_decision "$M_BAD_JSON")"
M_BAD_SLACK_JSON="{\"tool_name\":\"$M_SLACK_TOOL\",\"session_id\":\"bad-slack\",\"cwd\":\"$M_PERMIT_ROOT\",\"tool_input\":"
assert_eq "M9: malformed Slack send JSON fails closed" "deny" "$(m_decision "$M_BAD_SLACK_JSON")"

M_NO_PY_OUT="$(printf '%s' "$M_BASE_PAYLOAD" | PATH=/nonexistent /bin/bash "$M_GUARD")"
assert_eq "M9: a missing permit dependency fails closed" "deny" \
  "$(m_output_decision "$M_NO_PY_OUT")"

# Atomic rename is the claim: of two simultaneous calls, exactly one wins.
m_issue "$M_SEND_INPUT" sess-race
M_RACE_PAYLOAD="$(m_envelope "$M_SEND_INPUT" sess-race "$M_PERMIT_ROOT")"
(printf '%s' "$M_RACE_PAYLOAD" | bash "$M_GUARD" > "$M_PERMIT_ROOT/race-1.out") & m_p1=$!
(printf '%s' "$M_RACE_PAYLOAD" | bash "$M_GUARD" > "$M_PERMIT_ROOT/race-2.out") & m_p2=$!
wait "$m_p1"; wait "$m_p2"
M_RACE_ALLOW=0
for m_out in "$M_PERMIT_ROOT"/race-*.out; do
  [[ "$(m_output_decision "$(cat "$m_out")")" == allow ]] && M_RACE_ALLOW=$((M_RACE_ALLOW + 1))
done
assert_eq "M9: two concurrent claims allow exactly one send" "1" "$M_RACE_ALLOW"

m_issue "$M_SLACK_INPUT" slack-race 300 slack
M_SLACK_RACE_PAYLOAD="$(m_envelope "$M_SLACK_INPUT" slack-race "$M_PERMIT_ROOT" "$M_SLACK_TOOL")"
(printf '%s' "$M_SLACK_RACE_PAYLOAD" | bash "$M_GUARD" > "$M_PERMIT_ROOT/slack-race-1.out") & m_p1=$!
(printf '%s' "$M_SLACK_RACE_PAYLOAD" | bash "$M_GUARD" > "$M_PERMIT_ROOT/slack-race-2.out") & m_p2=$!
wait "$m_p1"; wait "$m_p2"
M_SLACK_RACE_ALLOW=0
for m_out in "$M_PERMIT_ROOT"/slack-race-*.out; do
  [[ "$(m_output_decision "$(cat "$m_out")")" == allow ]] && M_SLACK_RACE_ALLOW=$((M_SLACK_RACE_ALLOW + 1))
done
assert_eq "M9: two concurrent Slack claims allow exactly one send" "1" "$M_SLACK_RACE_ALLOW"

# A damaged record is never skipped as if it were trustworthy.
printf '{not-json' > "$M_PERMIT_ROOT/.codex/outbound-permits/pending/corrupt.json"
assert_eq "M9: a corrupt permit store fails closed" "deny" \
  "$(m_decision "$(m_envelope "$M_SEND_INPUT" sess-corrupt "$M_PERMIT_ROOT")")"

# control: the harness can tell a deny from an allow
assert_eq "M9: control — the decision reader reports INVALID on garbage" \
  "INVALID" "$(M_G_OUT='not json' M_G_PY='
import json, os, sys
try: d = json.loads(os.environ["M_G_OUT"])
except Exception: print("INVALID"); sys.exit()
print("allow")
' python3 -c 'import os;exec(os.environ["M_G_PY"])')"

# ── the wiring: the template must point at the script, absolutely ──────────
M_GUARD_CMD="$(python3 -c '
import tomllib, sys
d = tomllib.load(open(sys.argv[1], "rb"))
print(d["hooks"]["PreToolUse"][0]["hooks"][0]["command"], end="")
' "$REPO_ROOT/templates/codex/config.toml.example" 2>/dev/null || true)"
assert_grep_str "M9: the Codex template declares a PreToolUse hook" \
  "outbound_guard.sh" "$M_GUARD_CMD"
assert_grep_str "M9: …whose path is a placeholder setup.sh fills in absolutely" \
  "__PROJECT_ROOT__/" "$M_GUARD_CMD"

M_GUARD_FX="$(m_scaffold guard)"
"$M_GUARD_FX/scripts/setup.sh" --codex >> "$M_GUARD_FX/.setup.log" 2>&1
assert_file "M9: setup.sh --codex installs the guard beside the config" \
  "$M_GUARD_FX/.codex/hooks/outbound_guard.sh"
assert_ok "M9: …executable" test -x "$M_GUARD_FX/.codex/hooks/outbound_guard.sh"
assert_same "M9: …byte for byte from the template" \
  "$M_GUARD_FX/.codex/hooks/outbound_guard.sh" "$M_GUARD_TEMPLATE"
assert_file "M9: setup.sh --codex installs the permit helper beside the guard" \
  "$M_GUARD_FX/.codex/hooks/outbound_permit.py"
assert_ok "M9: …permit helper is executable" test -x "$M_GUARD_FX/.codex/hooks/outbound_permit.py"
assert_same "M9: …permit helper is byte for byte from the template" \
  "$M_GUARD_FX/.codex/hooks/outbound_permit.py" "$M_PERMIT_TEMPLATE"
M_GUARD_WIRED="$(python3 -c '
import tomllib, sys
d = tomllib.load(open(sys.argv[1], "rb"))
print(d["hooks"]["PreToolUse"][0]["hooks"][0]["command"], end="")
' "$M_GUARD_FX/.codex/config.toml" 2>/dev/null || true)"
assert_no_grep_str "M9: the generated config has no placeholder left in it" \
  "__PROJECT_ROOT__" "$M_GUARD_WIRED"
assert_grep_str "M9: …and names an absolute path (a relative one resolves elsewhere)" \
  "$M_GUARD_FX/.codex/hooks/outbound_guard.sh" "$M_GUARD_WIRED"
assert_ok "M9: …that exists and runs" bash -n "$M_GUARD_WIRED"

# ─── M10. --help must not run the program ──────────────────────────────────
# Measured 2026-09-07: `scripts/morning_brief.sh --help` fell through into the
# body, started an agent and created briefs/ and logs/ under the directory the
# operator happened to be standing in. A help flag with side effects is the one
# flag people type when they are LEAST sure what a script does.
M_HELP_HOME="$TEST_TMP/m_help_home"
for m_entry in morning_brief.sh distill.sh inbound_watch.sh.example weekly_distill.sh.example; do
  m_dir="$TEST_TMP/m_help_$(printf '%s' "$m_entry" | tr './' '__')"
  rm -rf "$m_dir" "$M_HELP_HOME"; mkdir -p "$m_dir" "$M_HELP_HOME"
  m_out="$(cd "$m_dir" && HOME="$M_HELP_HOME" LOOP_CONFIG="/nonexistent/config.env" \
           bash "$M_KIT/scripts/$m_entry" --help 2>&1)"; m_rc=$?
  assert_eq "M10: $m_entry --help exits 0" "0" "$m_rc"
  assert_grep_str "M10: $m_entry --help says usage" "usage:" "$m_out"
  assert_empty_str "M10: $m_entry --help creates nothing in the cwd" \
    "$(find "$m_dir" -mindepth 1 2>/dev/null)"
  assert_empty_str "M10: $m_entry --help creates nothing in \$HOME" \
    "$(find "$M_HELP_HOME" -mindepth 1 2>/dev/null)"
  # and an unknown flag must say so rather than run the body
  m_out2="$(cd "$m_dir" && HOME="$M_HELP_HOME" LOOP_CONFIG="/nonexistent/config.env" \
            bash "$M_KIT/scripts/$m_entry" --no-such-flag 2>&1)"; m_rc2=$?
  assert_eq "M10: $m_entry rejects an unknown flag (exit 64)" "64" "$m_rc2"
  assert_grep_str "M10: …by name" "unknown option" "$m_out2"
  assert_empty_str "M10: …and still creates nothing" \
    "$(find "$m_dir" -mindepth 1 2>/dev/null; find "$M_HELP_HOME" -mindepth 1 2>/dev/null)"
done

# the dry run is the other half: it must print the command and touch nothing.
M_DRY_DIR="$TEST_TMP/m_dry"; rm -rf "$M_DRY_DIR"; mkdir -p "$M_DRY_DIR"
M_DRY_CFG="$M_DRY_DIR/config.env"
cat > "$M_DRY_CFG" <<EOF
PROJECT_ROOT="$M_DRY_DIR/proj"
SSOT_DIR="$M_DRY_DIR/proj/ssot"
BRIEF_DIR="$M_DRY_DIR/proj/briefs"
LOG_DIR="$M_DRY_DIR/proj/logs"
QUEUE_FILE="$M_DRY_DIR/proj/approval_queue.md"
AGENT_CLI="claude"
AGENT_CMD="$M_DRY_DIR/fake-claude"
EOF
printf '#!/usr/bin/env bash\ntouch "%s/RAN"\n' "$M_DRY_DIR" > "$M_DRY_DIR/fake-claude"
chmod +x "$M_DRY_DIR/fake-claude"
M_DRY_OUT="$(cd "$M_DRY_DIR" && LOOP_CONFIG="$M_DRY_CFG" bash "$M_KIT/scripts/morning_brief.sh" --dry-run 2>&1)"
assert_grep_str "M10: --dry-run prints the command it would run" "would run" "$M_DRY_OUT"
assert_grep_str "M10: …built by the real builder, so it names the resolved binary" \
  "$M_DRY_DIR/fake-claude" "$M_DRY_OUT"
assert_grep_str "M10: …and the prompt itself" "morning stock-take" "$M_DRY_OUT"
assert_empty_str "M10: --dry-run starts no agent and creates no directory" \
  "$(find "$M_DRY_DIR" -mindepth 1 ! -name 'config.env' ! -name 'fake-claude' 2>/dev/null)"
