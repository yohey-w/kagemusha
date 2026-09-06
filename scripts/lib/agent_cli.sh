#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# scripts/lib/agent_cli.sh — the ONE place this kit starts an AI CLI.
#
# WHY A LIBRARY AND NOT A COMMENT. Until now every script carried a "CLI-SWAP
# POINT" comment: three commented-out invocation lines and an instruction to
# edit one of them. That is a swap you have to perform four times, by hand, in
# four files, and get right in all four — and nothing checks that you did. Here
# the swap is one environment variable, and tests/test_m_codex.sh asserts the
# argv each CLI actually receives.
#
#   source "$SCRIPT_DIR/lib/agent_cli.sh"
#   agent_run --write -- "$PROMPT"                 # agentic: may read/write files
#   OUT="$(agent_run -- "$PROMPT")"                # read-only: text on stdout
#
# WHAT IT IS NOT. It is not an abstraction over what the CLIs *mean*. Claude
# Code and Codex differ in sandboxing, in what a "model" id looks like, and in
# what `--json` wraps the answer in. This file normalises the CALL, names the
# differences out loud, and leaves the rest to the caller.
#
# ─── options ───────────────────────────────────────────────────────────────
#   --model M       model id for the CLI in use ("" = let the CLI decide)
#   --effort E      reasoning effort  (claude: --effort · codex: -c model_reasoning_effort=)
#   --write         the run is allowed to touch files (codex: -s workspace-write)
#                   Without it the run is read-only and, on codex, gets a
#                   "no tools, output only" preamble.
#   --json          ask for machine-readable output. THE ENVELOPES DIFFER:
#                   claude --output-format json is one JSON object; codex --json
#                   is JSONL events. No caller in this kit uses it yet.
#   --schema FILE   JSON Schema for the final answer
#                   (claude: --json-schema · codex: --output-schema)
#   --timeout N     seconds (default: $AGENT_TIMEOUT, else 120)
#   --cd DIR        working root (codex -C; claude inherits the shell's cwd)
#   --flags "..."   extra flags for the CLI in use, verbatim, word-split
#   --no-preamble   never prepend the codex read-only preamble
#   --              end of options; everything after it is the PROMPT
#
# ─── environment ───────────────────────────────────────────────────────────
#   AGENT_CLI              claude | codex | auto   (default: auto)
#                          auto = whichever is on PATH via `command -v`; if both
#                          are, claude. Detection NEVER executes a CLI.
#   AGENT_CMD              the binary to run (default: the resolved CLI's name).
#                          Cron's PATH is short, so an absolute path belongs here.
#                          If AGENT_CLI is unset, the basename of AGENT_CMD picks
#                          the dialect: .../claude -> claude, .../codex -> codex.
#   AGENT_MODEL            model id. Per-CLI overrides win over it:
#   AGENT_MODEL_CLAUDE     …when the resolved CLI is claude
#   AGENT_MODEL_CODEX      …when it is codex
#   AGENT_EFFORT / AGENT_EFFORT_CLAUDE / AGENT_EFFORT_CODEX   same shape
#   AGENT_FLAGS            extra flags, claude only (this is where
#                          --dangerously-skip-permissions lives)
#   CODEX_FLAGS            extra flags, codex only
#   AGENT_TIMEOUT          seconds
#   AGENT_CLI_NO_PREAMBLE  1 = never prepend the codex preamble
#   AGENT_CLI_RECORD       1 = drop --ephemeral, so codex records these runs in
#                          ~/.codex/sessions. OFF by default: that tree is what
#                          the distillation lane mines, and the machinery's own
#                          prompts are not your judgment. Turn it on to debug a
#                          scheduled run, then turn it off.
#
# ⚠️ AGENT_MODEL is a single key shared by both dialects, and a Claude model id
# is not a Codex model id. If you switch AGENT_CLI, either change AGENT_MODEL or
# set the two per-CLI keys and leave it empty. Nothing can detect this for you:
# a wrong model id comes back as the CLI's own error, not as a kit error.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash

# The one sentence that turns an agentic CLI into a text generator. codex exec
# will otherwise happily start reading the repository to answer a question that
# was already fully specified in the prompt.
AGENT_CLI_PREAMBLE="${AGENT_CLI_PREAMBLE:-Answer with output only. Do not use any tool: do not read or write files, do not run commands, do not search.（ツールを使わず、出力だけを返す）}"

agent_cli_die() { printf 'agent_cli: %s\n' "$1" >&2; return 2; }

# agent_cli_which — print the dialect this machine will use: claude | codex.
# `command -v` only: a detector that runs a CLI to find out whether it exists
# costs a login round-trip, and fails differently when you are logged out.
agent_cli_which() {
  local want="${AGENT_CLI:-auto}"
  case "$want" in
    claude|codex) printf '%s' "$want"; return 0 ;;
    auto) : ;;
    *) agent_cli_die "AGENT_CLI must be claude, codex or auto (got: $want)"; return 2 ;;
  esac
  # An explicit AGENT_CMD names the dialect by its basename — and if the name is
  # one we do not know (your own wrapper, the demo's stub distiller, gemini),
  # the answer is `claude`, meaning the `-p <prompt>` argv form. That is not a
  # guess about which vendor you installed: it is the form every CLI but codex
  # in this kit's history has used, and it is what the CLI-SWAP comment this
  # library replaced had as its default line.
  if [[ -n "${AGENT_CMD:-}" ]]; then
    case "$(basename -- "$AGENT_CMD")" in
      *codex*) printf 'codex';  return 0 ;;
      *)       printf 'claude'; return 0 ;;
    esac
  fi
  if command -v claude >/dev/null 2>&1; then printf 'claude'; return 0; fi
  if command -v codex  >/dev/null 2>&1; then printf 'codex';  return 0; fi
  agent_cli_die "no agent CLI found on PATH (looked for: claude, codex).
  Install one, or set AGENT_CLI and AGENT_CMD in config.env — under cron
  AGENT_CMD needs the ABSOLUTE path, because cron's PATH is short."
  return 2
}

# agent_cli_build [options] -- PROMPT
#   Fills the array AGENT_CLI_ARGV with the exact command line, and sets
#   AGENT_CLI_DIALECT / AGENT_CLI_TIMEOUT / AGENT_CLI_PROMPT. It runs nothing.
#   Everything that decides what a call LOOKS like lives here and nowhere else,
#   so the dry runs print the command that will actually be made rather than a
#   second hand-written copy of it that drifts.
#   codex only: -o takes ${AGENT_CLI_OUT_PATH:-<outfile>}.
agent_cli_build() {
  local model="" effort="" want_json="" schema="" write="" timeout_s="" workdir="" \
        extra_flags="" flags_given="" no_preamble="" prompt="" cli bin
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --model)        model="${2-}"; shift 2 ;;
      --effort)       effort="${2-}"; shift 2 ;;
      --json)         want_json=1; shift ;;
      --schema)       schema="${2-}"; shift 2 ;;
      --write)        write=1; shift ;;
      --timeout)      timeout_s="${2-}"; shift 2 ;;
      --cd)           workdir="${2-}"; shift 2 ;;
      --flags)        extra_flags="${2-}"; flags_given=1; shift 2 ;;
      --no-preamble)  no_preamble=1; shift ;;
      --)             shift; prompt="$*"; break ;;
      *)              agent_cli_die "unknown option: $1"; return 2 ;;
    esac
  done
  [[ -n "$prompt" ]] || { agent_cli_die "no prompt (did you forget the -- separator?)"; return 2; }

  cli="$(agent_cli_which)" || return 2
  bin="${AGENT_CMD:-$cli}"
  # shellcheck disable=SC2034  # read by callers and by tests/test_m_codex.sh
  AGENT_CLI_DIALECT="$cli"
  AGENT_CLI_TIMEOUT="${timeout_s:-${AGENT_TIMEOUT:-120}}"

  # per-CLI keys beat the shared one; an explicit --model beats both
  if [[ -z "$model" ]]; then
    case "$cli" in
      claude) model="${AGENT_MODEL_CLAUDE:-${AGENT_MODEL:-}}" ;;
      codex)  model="${AGENT_MODEL_CODEX:-${AGENT_MODEL:-}}" ;;
    esac
  fi
  if [[ -z "$effort" ]]; then
    case "$cli" in
      claude) effort="${AGENT_EFFORT_CLAUDE:-${AGENT_EFFORT:-}}" ;;
      codex)  effort="${AGENT_EFFORT_CODEX:-${AGENT_EFFORT:-}}" ;;
    esac
  fi
  # `--flags ""` means "no flags", NOT "fall back to the environment": the one
  # caller that passes an empty string (distill.sh) does so precisely to keep
  # --dangerously-skip-permissions OUT of a run that must have no hands.
  if [[ -z "$flags_given" ]]; then
    case "$cli" in
      claude) extra_flags="${AGENT_FLAGS:-}" ;;
      codex)  extra_flags="${CODEX_FLAGS:-}" ;;
    esac
  fi

  AGENT_CLI_ARGV=()
  case "$cli" in
    claude)
      # Claude Code reads its permissions from AGENT_FLAGS, so --write changes
      # nothing here: it is the caller's statement of intent, and the flag that
      # actually grants the write is the operator's (see config.env.example).
      AGENT_CLI_ARGV=("$bin" -p "$prompt")
      [[ -n "$model" ]]  && AGENT_CLI_ARGV+=(--model "$model")
      [[ -n "$effort" ]] && AGENT_CLI_ARGV+=(--effort "$effort")
      [[ -n "$want_json" ]] && AGENT_CLI_ARGV+=(--output-format json)
      [[ -n "$schema" ]]    && AGENT_CLI_ARGV+=(--json-schema "$schema")
      # shellcheck disable=SC2206
      [[ -n "$extra_flags" ]] && AGENT_CLI_ARGV+=($extra_flags)
      ;;
    codex)
      # `codex exec` is agentic by default and prints a session banner, so the
      # answer is collected from -o and the banner is dropped. --ephemeral keeps
      # these machine-driven runs OUT of ~/.codex/sessions, which is the same
      # corpus the distillation lane mines: a nightly cron writing sessions there
      # would distil the kit's own prompts back into your judgment model.
      if [[ -z "$write" && -z "$no_preamble" && "${AGENT_CLI_NO_PREAMBLE:-0}" != "1" ]]; then
        prompt="${AGENT_CLI_PREAMBLE}"$'\n\n'"${prompt}"
      fi
      AGENT_CLI_ARGV=("$bin" exec)
      [[ -n "$model" ]]  && AGENT_CLI_ARGV+=(-m "$model")
      [[ -n "$effort" ]] && AGENT_CLI_ARGV+=(-c "model_reasoning_effort=$effort")
      # --ephemeral is the DEFAULT and deliberately so: these calls are the
      # machinery talking to itself, and ~/.codex/sessions is the same corpus
      # the distillation lane mines. A nightly cron recording its own prompts
      # there would distil the kit's instructions back into your judgment model
      # — an agent's words harvested as yours. AGENT_CLI_RECORD=1 turns the
      # recording back on when you are debugging a scheduled run.
      [[ "${AGENT_CLI_RECORD:-0}" == "1" ]] || AGENT_CLI_ARGV+=(--ephemeral)
      AGENT_CLI_ARGV+=(-s "$([[ -n "$write" ]] && echo workspace-write || echo read-only)")
      # Trust and workspace-write are decided from the working root, and cron's
      # working directory is $HOME. Naming the root is not a nicety: without it a
      # scheduled workspace-write run would take $HOME as its workspace.
      workdir="${workdir:-${AGENT_CWD:-${PROJECT_ROOT:-}}}"
      [[ -n "$workdir" ]] && AGENT_CLI_ARGV+=(-C "$workdir")
      [[ -n "$want_json" ]] && AGENT_CLI_ARGV+=(--json)
      [[ -n "$schema" ]]    && AGENT_CLI_ARGV+=(--output-schema "$schema")
      AGENT_CLI_ARGV+=(-o "${AGENT_CLI_OUT_PATH:-<outfile>}")
      # shellcheck disable=SC2206
      [[ -n "$extra_flags" ]] && AGENT_CLI_ARGV+=($extra_flags)
      AGENT_CLI_ARGV+=("$prompt")
      ;;
  esac
  # shellcheck disable=SC2034  # read by callers and by tests/test_m_codex.sh
  AGENT_CLI_PROMPT="$prompt"
}

# agent_cli_show [same options] -- PLACEHOLDER
#   One line: the command that agent_run would make. For the dry runs, so what
#   they print and what they would do come from the same code.
agent_cli_show() {
  agent_cli_build "$@" || return 2
  printf '%s' "${AGENT_CLI_ARGV[*]}"
}

# agent_run [options] -- PROMPT
# stdout: the model's answer, exactly as the CLI produced it.
# return: the CLI's exit status (124 = the timeout fired).
agent_run() {
  local out_file="" rc
  if [[ "$(agent_cli_which)" == "codex" ]]; then
    out_file="$(mktemp "${TMPDIR:-/tmp}/agent_cli_codex.XXXXXX")" || return 2
    AGENT_CLI_OUT_PATH="$out_file"
  fi
  agent_cli_build "$@" || { [[ -n "$out_file" ]] && rm -f "$out_file"; return 2; }
  unset AGENT_CLI_OUT_PATH

  if [[ -n "$out_file" ]]; then
    # Three things about this one line:
    #   · `< /dev/null` is REQUIRED. `codex exec` reads stdin as extra input, so
    #     under cron — where stdin is not a terminal — it waits, and the run
    #     dies on the timeout with nothing in the log to explain it.
    #   · the CLI's own banner and diagnostics go to STDERR, so a caller that
    #     captures stdout gets the answer and only the answer, while a caller
    #     that redirects 2>&1 into a log still has something to read when a
    #     cron run comes back empty at 6am.
    #   · success is the EXIT STATUS, never the stderr text. codex prints a
    #     bubblewrap warning on machines without it and still works; reading
    #     stderr for failure would call every one of those runs broken.
    timeout "$AGENT_CLI_TIMEOUT" "${AGENT_CLI_ARGV[@]}" < /dev/null >&2
    rc=$?
    cat "$out_file"
    rm -f "$out_file"
    return $rc
  fi
  timeout "$AGENT_CLI_TIMEOUT" "${AGENT_CLI_ARGV[@]}" < /dev/null
}
