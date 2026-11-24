#!/usr/bin/env bash
# Run a meaning-search prompt through the kit's shared agent adapter.
set -uo pipefail

die() { printf 'ms_agent: %s\n' "$*" >&2; exit 2; }

model="" effort="" seconds="" check=""
while (( $# )); do
  case "$1" in
    --check-config) check=1; shift ;;
    --model|--effort|--timeout)
      (( $# >= 2 )) || die "$1 requires a value"
      case "$1" in
        --model) model="$2" ;;
        --effort) effort="$2" ;;
        --timeout) seconds="$2" ;;
      esac
      shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

kit="${MSEARCH_KIT_ROOT:-}"
if [[ -z "$kit" ]]; then
  script="$(realpath -- "${BASH_SOURCE[0]}")" || die "cannot locate ms_agent.sh"
  kit="$(cd "$(dirname -- "$script")/../../../.." && pwd)" || die "cannot locate kit root"
fi
[[ -f "$kit/scripts/lib/agent_cli.sh" ]] ||
  die "scripts/lib/agent_cli.sh not found under $kit; set MSEARCH_KIT_ROOT"
env_cli="${MSEARCH_CLI:-}"
base_cli="${AGENT_CLI:-}"
env_model="${MSEARCH_MODEL:-}"
env_fast="${AGENT_MODEL_FAST:-}"
env_effort="${MSEARCH_EFFORT:-}"
env_timeout="${MSEARCH_TIMEOUT:-}"
# Keep the default selector out of the library's environment snapshot until
# config.env has supplied its skill-specific override.
unset AGENT_CLI
# Load the shared preamble from the library's default, rather than from the
# environment. Preserve that default even if config.env assigns either key.
unset AGENT_CLI_NO_PREAMBLE AGENT_CLI_PREAMBLE
# shellcheck source=/dev/null
source "$kit/scripts/lib/agent_cli.sh" || exit 2
preamble="$AGENT_CLI_PREAMBLE"
[[ -z "$base_cli" ]] || export AGENT_CLI="$base_cli"
if [[ -f "$kit/config.env" ]]; then
  # shellcheck source=/dev/null
  source "$kit/config.env" >&2 || exit 2
fi

cli_override="${env_cli:-${MSEARCH_CLI:-}}"
case "$cli_override" in
  "")
    if [[ -n "$base_cli" && "$base_cli" != auto ]]; then
      AGENT_CLI="$base_cli"
    fi ;;
  claude|codex) AGENT_CLI="$cli_override" ;;
  *) die "MSEARCH_CLI must be claude, codex or empty" ;;
esac

model="${model:-${env_model:-${MSEARCH_MODEL:-${env_fast:-${AGENT_MODEL_FAST:-}}}}}"
[[ -n "$model" ]] || die "set MSEARCH_MODEL or AGENT_MODEL_FAST (or pass --model)"
effort="${effort:-${env_effort:-${MSEARCH_EFFORT:-}}}"
seconds="${seconds:-${env_timeout:-${MSEARCH_TIMEOUT:-${MSEARCH_TIMEOUT_DEFAULT:-300}}}}"
[[ "$seconds" =~ ^[1-9][0-9]*$ ]] || die "timeout must be a positive integer"
cli="$(agent_cli_which)" || exit 2
flags=""
[[ "$cli" != claude ]] || flags="--tools= --strict-mcp-config --no-session-persistence"
# The child is started from an empty directory so that no project instruction
# file is loaded. Codex refuses to start outside a git repository unless told
# it is deliberate (measured: "Not inside a trusted directory and
# --skip-git-repo-check was not specified").
[[ "$cli" != codex ]] || flags="--skip-git-repo-check"
# Effort belongs to meaning-search; generic effort settings cannot fill a blank.
unset AGENT_EFFORT AGENT_EFFORT_CLAUDE AGENT_EFFORT_CODEX AGENT_DIFFICULTY CLAUDE_CODE_EFFORT_LEVEL
unset AGENT_CLI_ENV__AGENT_EFFORT AGENT_CLI_ENV__AGENT_EFFORT_CLAUDE AGENT_CLI_ENV__AGENT_EFFORT_CODEX AGENT_CLI_ENV__AGENT_DIFFICULTY
export AGENT_CLI_ARGV_MAX_BYTES=0
unset AGENT_CLI_NO_PREAMBLE AGENT_CLI_PREAMBLE AGENT_CLI_RECORD
AGENT_CLI_PREAMBLE="$preamble"
agent_options=(--model "$model" --effort "$effort" --timeout "$seconds" --cd "$PWD" --flags "$flags")
if [[ -n "$check" ]]; then
  agent_cli_build "${agent_options[@]}" -- "meaning-search config check" || exit 2
  printf '%s\n%s\n' "$model" "$seconds"
  exit 0
fi

prompt="$(cat)" || exit 2
if [[ "$cli" == codex ]]; then
  printf '%s\n' 'ms_agent: Codex はコネクタを外す指定がありません。SKILL.md の「安全」を確認してください。' >&2
fi
agent_run "${agent_options[@]}" -- "$prompt"
