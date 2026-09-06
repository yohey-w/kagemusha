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
# PRECEDENCE, one line: an explicit ENVIRONMENT VARIABLE beats config.env, and
# config.env beats auto-detection. This matters because every script here does
# `source config.env` AFTER sourcing this library, and a plain assignment in a
# config file overwrites what you exported on the command line. So the keys
# below are read from the environment ONCE, when this file is sourced, and a
# key that was non-empty then wins for the rest of the run.
#   ⚠️ The corollary: assigning one of these in the SAME shell after sourcing
#   this file does nothing — the frozen value still wins. Set them in the
#   environment of the command (`AGENT_CLI=codex ./scripts/morning_brief.sh`)
#   or in config.env, not in between.
#
#   AGENT_CLI              claude | codex | auto   (default: auto). THE TYPE OF
#                          CLI, and the only key that decides it.
#                          auto = whichever is on PATH via `command -v`; if both
#                          are, claude. Detection NEVER executes a CLI.
#   AGENT_CMD              WHICH EXECUTABLE to run for that type — a path
#                          override, not a second way to choose the type.
#                          Cron's PATH is short, so an absolute path belongs here.
#                          · AGENT_CLI unset and AGENT_CMD=.../codex -> type codex;
#                            any other basename (.../claude, your own wrapper,
#                            gemini) -> type claude. That is the old behaviour and
#                            it still holds.
#                          · AGENT_CLI set and AGENT_CMD naming the OTHER CLI
#                            (AGENT_CLI=codex, AGENT_CMD=claude — an old config.env
#                            plus a new environment) is a contradiction: AGENT_CLI
#                            wins, AGENT_CMD is dropped, and one line says so on
#                            stderr. Building `claude exec -m …` out of the two is
#                            the bug this rule exists to prevent.
#   AGENT_MODEL            model id for CLAUDE — the kit's original single key,
#                          kept for backward compatibility. CODEX NEVER READS IT:
#                          a Claude model id is not a Codex model id, and the two
#                          dialects sharing one key is how `claude-opus-4-8` ended
#                          up on a codex command line.
#   AGENT_MODEL_CLAUDE     model id when the resolved type is claude (beats AGENT_MODEL)
#   AGENT_MODEL_CODEX      model id when it is codex. Unset -> the built-in
#                          default below, never AGENT_MODEL.
#   AGENT_EFFORT / AGENT_EFFORT_CLAUDE / AGENT_EFFORT_CODEX   effort, same shape.
#                          Effort names ("high", "xhigh") are not model ids, so
#                          the shared key still serves both.
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
# ⚠️ A model id that belongs to the other dialect is not something the CLI tells
# you about kindly: codex would go and ask its API for "claude-opus-4-8". So the
# two crossings are handled here — the shared AGENT_MODEL is simply not read for
# codex, and a `claude-*` id that reaches a codex call any other way (--model,
# AGENT_MODEL_CODEX) FAILS THE BUILD, before anything is spawned.
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck shell=bash

# The one sentence that turns an agentic CLI into a text generator. codex exec
# will otherwise happily start reading the repository to answer a question that
# was already fully specified in the prompt.
# ⚠️ A PROMPT DOES NOT ALWAYS FIT IN AN ARGUMENT. Linux caps one argv entry at
# 128 KB (MAX_ARG_STRLEN); past it, exec fails with "Argument list too long" —
# measured here at 180 KB. Japanese runs 3 bytes per character, so that ceiling
# is about 43,000 characters, and this kit routinely builds prompts out of your
# own material (distill.sh pastes up to DISTILL_MAX_MATERIAL_LINES of it). So a
# big prompt goes in on STDIN instead, and the switch is automatic: nothing a
# caller has to remember, because forgetting it fails at 6am inside cron.
#
#   claude : claude -p --model … with no positional, prompt on stdin
#   codex  : codex exec … -o <file> -   (`-` is the read-from-stdin marker)
AGENT_CLI_ARGV_MAX_BYTES="${AGENT_CLI_ARGV_MAX_BYTES:-98304}"   # 96 KB, under the 128 KB cap

AGENT_CLI_PREAMBLE="${AGENT_CLI_PREAMBLE:-Answer with output only. Do not use any tool: do not read or write files, do not run commands, do not search.（ツールを使わず、出力だけを返す）}"

# The model a codex call uses when nothing names one. It exists because the
# alternative — falling back to the shared AGENT_MODEL — is exactly how a Claude
# model id reached a codex command line. Override it per machine if you want a
# different default; set AGENT_MODEL_CODEX to pin one per config.
AGENT_CLI_DEFAULT_MODEL_CODEX="${AGENT_CLI_DEFAULT_MODEL_CODEX:-gpt-5.6-sol}"

# ─── the environment, frozen once ──────────────────────────────────────────
# Read here, at source time, which is BEFORE the caller sources config.env
# (tests/test_m_codex.sh pins that order for every script that does both). A key
# that is non-empty in the environment now is the operator's explicit choice and
# outranks whatever config.env assigns to it later. An EMPTY environment value
# is not a choice — "" already means "let it be decided" everywhere in
# config.env.example — so it is not frozen.
if [[ -z "${AGENT_CLI_ENV_FROZEN:-}" ]]; then
  AGENT_CLI_ENV_FROZEN=1
  for _agent_cli_k in AGENT_CLI AGENT_CMD AGENT_MODEL AGENT_MODEL_CLAUDE AGENT_MODEL_CODEX \
                      AGENT_EFFORT AGENT_EFFORT_CLAUDE AGENT_EFFORT_CODEX \
                      AGENT_FLAGS CODEX_FLAGS; do
    _agent_cli_v="${!_agent_cli_k:-}"
    [[ -n "$_agent_cli_v" ]] || continue
    # AGENT_CLI=auto is "decide for me", not a choice that beats config.env
    [[ "$_agent_cli_k" == "AGENT_CLI" && "$_agent_cli_v" == "auto" ]] && continue
    printf -v "AGENT_CLI_ENV__${_agent_cli_k}" '%s' "$_agent_cli_v"
  done
  unset _agent_cli_k _agent_cli_v
fi

# agent_cli_env KEY — the value that wins for KEY: the environment's, if it
# named one when this file was sourced; otherwise the current one (config.env's).
agent_cli_env() {
  local key="$1" snap="AGENT_CLI_ENV__$1"
  if [[ -n "${!snap:-}" ]]; then printf '%s' "${!snap}"; else printf '%s' "${!key:-}"; fi
}

agent_cli_die() { printf 'agent_cli: %s\n' "$1" >&2; return 2; }

# agent_cli_kind_of PATH_OR_NAME — the dialect a binary's NAME implies:
# claude | codex | "" for a name we do not know (your own wrapper, the demo's
# stub distiller, gemini). "" is not an error: it means the name says nothing
# about the dialect, so something else has to.
agent_cli_kind_of() {
  case "$(basename -- "$1")" in
    *codex*)  printf 'codex' ;;
    *claude*) printf 'claude' ;;
    *)        printf '' ;;
  esac
}

# agent_cli_which — print the dialect this machine will use: claude | codex.
# AGENT_CLI decides it; AGENT_CMD only gets a vote when AGENT_CLI is silent.
# `command -v` only: a detector that runs a CLI to find out whether it exists
# costs a login round-trip, and fails differently when you are logged out.
agent_cli_which() {
  local want cmd kind
  want="$(agent_cli_env AGENT_CLI)"; want="${want:-auto}"
  case "$want" in
    claude|codex) printf '%s' "$want"; return 0 ;;
    auto) : ;;
    *) agent_cli_die "AGENT_CLI must be claude, codex or auto (got: $want)"; return 2 ;;
  esac
  # No AGENT_CLI: an explicit AGENT_CMD names the dialect by its basename — and
  # if the name is one we do not know, the answer is `claude`, meaning the
  # `-p <prompt>` argv form. That is not a guess about which vendor you
  # installed: it is the form every CLI but codex in this kit's history has
  # used, and it is what the CLI-SWAP comment this library replaced had as its
  # default line.
  cmd="$(agent_cli_env AGENT_CMD)"
  if [[ -n "$cmd" ]]; then
    kind="$(agent_cli_kind_of "$cmd")"
    printf '%s' "${kind:-claude}"; return 0
  fi
  if command -v claude >/dev/null 2>&1; then printf 'claude'; return 0; fi
  if command -v codex  >/dev/null 2>&1; then printf 'codex';  return 0; fi
  agent_cli_die "no agent CLI found on PATH (looked for: claude, codex).
  Install one, or set AGENT_CLI and AGENT_CMD in config.env — under cron
  AGENT_CMD needs the ABSOLUTE path, because cron's PATH is short."
  return 2
}

# agent_cli_bin DIALECT — the executable to run for that dialect.
# AGENT_CMD overrides the name; it cannot change the dialect. When it names the
# OTHER known CLI the two keys contradict each other, and the resolution is
# fixed and loud: the dialect wins, the binary falls back to the dialect's own
# name, and ONE line goes to stderr. The alternative — running the named binary
# in the other dialect's argv form — is `claude exec -m claude-opus-4-8`, a
# command line that belongs to no CLI at all.
agent_cli_bin() {
  local cli="$1" cmd kind
  cmd="$(agent_cli_env AGENT_CMD)"
  [[ -n "$cmd" ]] || { printf '%s' "$cli"; return 0; }
  kind="$(agent_cli_kind_of "$cmd")"
  if [[ -n "$kind" && "$kind" != "$cli" ]]; then
    # ONE line, every time a command line is built — this function runs inside a
    # command substitution, so it cannot remember that it already spoke, and a
    # flag pretending otherwise would just be dead code. A run that builds two
    # command lines (a dry run, then the call) says it twice, on purpose: the
    # second one is the line that actually spawns.
    printf 'agent_cli: AGENT_CLI=%s wins over AGENT_CMD=%s (that names %s) — running %s; AGENT_CMD only overrides the path of the CLI that AGENT_CLI names, so clear it in config.env.\n' \
      "$cli" "$cmd" "$kind" "$cli" >&2
    printf '%s' "$cli"; return 0
  fi
  printf '%s' "$cmd"
}

# agent_cli_build [options] -- PROMPT
#   Fills the array AGENT_CLI_ARGV with the exact command line, and sets
#   AGENT_CLI_DIALECT / AGENT_CLI_TIMEOUT / AGENT_CLI_PROMPT, plus what was
#   resolved out of the keys above: AGENT_CLI_BIN / AGENT_CLI_MODEL /
#   AGENT_CLI_EFFORT. It runs nothing.
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
  bin="$(agent_cli_bin "$cli")"
  # shellcheck disable=SC2034  # read by callers and by tests/test_m_codex.sh
  AGENT_CLI_DIALECT="$cli"
  AGENT_CLI_TIMEOUT="${timeout_s:-${AGENT_TIMEOUT:-120}}"

  # An explicit --model beats every key. Then the per-CLI key. Then: claude
  # falls back to the shared AGENT_MODEL (the kit's original key, which was
  # always a Claude id), and codex falls back to ITS OWN default — never to
  # AGENT_MODEL. One key cannot hold two vendors' model ids, and the version
  # that let it try is what put `claude exec -m claude-opus-4-8` on screen.
  if [[ -z "$model" ]]; then
    case "$cli" in
      claude) model="$(agent_cli_env AGENT_MODEL_CLAUDE)"
              [[ -n "$model" ]] || model="$(agent_cli_env AGENT_MODEL)" ;;
      codex)  model="$(agent_cli_env AGENT_MODEL_CODEX)"
              [[ -n "$model" ]] || model="${AGENT_CLI_DEFAULT_MODEL_CODEX:-}" ;;
    esac
  fi
  # Effort names are not model ids ("high" means the same thing to both), so the
  # shared key still serves both dialects.
  if [[ -z "$effort" ]]; then
    case "$cli" in
      claude) effort="$(agent_cli_env AGENT_EFFORT_CLAUDE)" ;;
      codex)  effort="$(agent_cli_env AGENT_EFFORT_CODEX)" ;;
    esac
    [[ -n "$effort" ]] || effort="$(agent_cli_env AGENT_EFFORT)"
  fi

  # The crossing that survives every fallback above: an id aimed AT codex by
  # hand (--model, or AGENT_MODEL_CODEX) that is a Claude id. Fail here, while
  # the keys that set it are still on screen — codex would instead go to its own
  # API and come back with a vendor error that names none of them.
  if [[ "$cli" == "codex" && "$model" == claude-* ]]; then
    agent_cli_die "codex cannot run the Claude model id '$model'.
  Set AGENT_MODEL_CODEX (or pass --model) to a Codex model id — AGENT_MODEL is
  the Claude key and codex does not read it."
    return 2
  fi
  # `--flags ""` means "no flags", NOT "fall back to the environment": the one
  # caller that passes an empty string (distill.sh) does so precisely to keep
  # --dangerously-skip-permissions OUT of a run that must have no hands.
  if [[ -z "$flags_given" ]]; then
    case "$cli" in
      claude) extra_flags="$(agent_cli_env AGENT_FLAGS)" ;;
      codex)  extra_flags="$(agent_cli_env CODEX_FLAGS)" ;;
    esac
  fi

  # codex gets its preamble before the size is measured, since it is part of
  # what has to fit.
  if [[ "$cli" == "codex" && -z "$write" && -z "$no_preamble" \
        && "${AGENT_CLI_NO_PREAMBLE:-0}" != "1" ]]; then
    prompt="${AGENT_CLI_PREAMBLE}"$'\n\n'"${prompt}"
  fi
  if [[ "$(printf '%s' "$prompt" | wc -c)" -gt "$AGENT_CLI_ARGV_MAX_BYTES" ]]; then
    AGENT_CLI_STDIN=1
  else
    AGENT_CLI_STDIN=""
  fi

  AGENT_CLI_ARGV=()
  case "$cli" in
    claude)
      # Claude Code reads its permissions from AGENT_FLAGS, so --write changes
      # nothing here: it is the caller's statement of intent, and the flag that
      # actually grants the write is the operator's (see config.env.example).
      AGENT_CLI_ARGV=("$bin" -p)
      [[ -n "$AGENT_CLI_STDIN" ]] || AGENT_CLI_ARGV+=("$prompt")
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
      # the positional goes LAST, and is `-` when the prompt rides on stdin
      AGENT_CLI_ARGV+=("$([[ -n "$AGENT_CLI_STDIN" ]] && printf -- '-' || printf '%s' "$prompt")")
      ;;
  esac
  # shellcheck disable=SC2034  # read by callers and by tests/test_m_codex.sh
  AGENT_CLI_PROMPT="$prompt"
  # the resolution, published so a dry run can print what was decided and not a
  # second hand-written guess at it
  # shellcheck disable=SC2034
  AGENT_CLI_BIN="$bin"
  # shellcheck disable=SC2034
  AGENT_CLI_MODEL="$model"
  # shellcheck disable=SC2034
  AGENT_CLI_EFFORT="$effort"
}

# agent_cli_show [same options] -- PLACEHOLDER
#   ONE line: the command that agent_run would make, then — after a `#`, so the
#   line stays a command you can read — the four things that were RESOLVED to
#   build it: type, executable, model, effort. Those four are where a config
#   goes wrong (an old AGENT_CMD, a model id from the other vendor), and the
#   argv alone does not say which key each came from. `-` means "nothing set;
#   the CLI decides". For the dry runs, so what they print and what they would
#   do come from the same code.
agent_cli_show() {
  agent_cli_build "$@" || return 2
  printf '%s  # cli=%s bin=%s model=%s effort=%s' "${AGENT_CLI_ARGV[*]}" \
    "$AGENT_CLI_DIALECT" "$AGENT_CLI_BIN" "${AGENT_CLI_MODEL:--}" "${AGENT_CLI_EFFORT:--}"
}

# agent_run [options] -- PROMPT
# stdout: the model's answer, exactly as the CLI produced it.
# return: the CLI's exit status (124 = the timeout fired).
agent_run() {
  local out_file="" rc
  AGENT_CLI_STDIN=""
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
    if [[ -n "$AGENT_CLI_STDIN" ]]; then
      printf '%s' "$AGENT_CLI_PROMPT" | timeout "$AGENT_CLI_TIMEOUT" "${AGENT_CLI_ARGV[@]}" >&2
    else
      timeout "$AGENT_CLI_TIMEOUT" "${AGENT_CLI_ARGV[@]}" < /dev/null >&2
    fi
    rc=$?
    cat "$out_file"
    rm -f "$out_file"
    return $rc
  fi
  if [[ -n "$AGENT_CLI_STDIN" ]]; then
    printf '%s' "$AGENT_CLI_PROMPT" | timeout "$AGENT_CLI_TIMEOUT" "${AGENT_CLI_ARGV[@]}"
    return $?
  fi
  timeout "$AGENT_CLI_TIMEOUT" "${AGENT_CLI_ARGV[@]}" < /dev/null
}
