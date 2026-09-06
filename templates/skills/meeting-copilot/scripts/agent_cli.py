#!/usr/bin/env python3
"""agent_cli.py — the one place this skill starts an AI CLI.

会議中は**引き直しがきかない**。だから起動口を3か所に散らさない: 前提監視・
回答役・返し役はどれもここを通り、CLI を差し替えるのは環境変数1個で済む。

    from agent_cli import run
    out = run(prompt, model=m, effort=e, timeout=20)

対応 CLI（bash 側の scripts/lib/agent_cli.sh と同じ設計・同じ既定）:

  claude : claude -p <prompt> --model <m> --effort <e>
  codex  : codex exec -m <m> -c model_reasoning_effort=<e> --ephemeral
           -s read-only -C <cwd> -o <tmp> <prompt>
           …そして <tmp> を読む。codex exec は経過をstdoutに流すので、
           最終回答だけを取り出すには -o が要る。

環境変数（**MEETLIVE_ で始まる設定はここでは読まない**——このスキルの設定は
すべて ``meetlive_config`` が解決する。ここが見るのは、bash 側の
``scripts/lib/agent_cli.sh`` と共有の、CLI そのものに関する3つだけ）:

  AGENT_CLI             claude | codex | auto  (既定 auto)
                        auto = PATH にある方。両方あれば claude。
                        検出は shutil.which のみ——**CLIを起動して確かめない**
                        (会議直前に無駄な往復をしない)
  AGENT_CMD             実行するバイナリ（既定は CLI 名そのもの）
  AGENT_CLI_NO_PREAMBLE 1 で下の前置き文を付けない

呼び出し側が CLI を指定したいときは ``run(..., cli=...)``。
``MEETLIVE_AGENT_CLI`` はそこに渡される値であって、この行を読むのは
``meetlive_config.agent_cli_name()`` の仕事。

⚠️ codex は既定で agentic（ファイルを読みに行く）。ここでの呼び出しは全て
「材料は渡してある・出力だけ返せ」なので、read-only サンドボックスに加えて
プロンプト先頭に一文を足す。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

PREAMBLE = (
    "ツールを使わず、出力だけを返してください。"
    "ファイルの読み書き・コマンド実行・検索はしないこと。\n\n"
)


class NoAgentCLI(RuntimeError):
    """PATH に claude も codex も無い。"""


def which() -> str:
    """使う CLI 名を返す: "claude" | "codex"。起動はしない。"""
    want = (os.environ.get("AGENT_CLI") or "auto").strip().lower()
    if want in ("claude", "codex"):
        return want
    if want not in ("", "auto"):
        raise NoAgentCLI(f"AGENT_CLI は claude / codex / auto のいずれか (got: {want})")
    cmd = os.environ.get("AGENT_CMD") or ""
    if cmd:
        return "codex" if "codex" in os.path.basename(cmd) else "claude"
    if shutil.which("claude"):
        return "claude"
    if shutil.which("codex"):
        return "codex"
    raise NoAgentCLI("claude も codex も PATH にありません "
                     "(AGENT_CLI / AGENT_CMD、または MEETLIVE_AGENT_CLI を設定してください)")


def build(prompt: str, model: str = "", effort: str = "",
          cli: str = "", out_path: str = "<outfile>",
          no_preamble: bool = False) -> list[str]:
    """実際に走る argv を組み立てる。表示・テスト・実行が同じ組み立てを通る。"""
    cli = cli or which()
    binary = os.environ.get("AGENT_CMD") or cli
    if cli == "claude":
        argv = [binary, "-p", prompt]
        if model:
            argv += ["--model", model]
        if effort:
            argv += ["--effort", effort]
        return argv
    quiet = no_preamble or os.environ.get("AGENT_CLI_NO_PREAMBLE") == "1"
    body = prompt if quiet else PREAMBLE + prompt
    argv = [binary, "exec"]
    if model:
        argv += ["-m", model]
    if effort:
        argv += ["-c", f"model_reasoning_effort={effort}"]
    argv += ["--ephemeral", "-s", "read-only", "-C", os.getcwd(), "-o", out_path, body]
    return argv


def run(prompt: str, model: str = "", effort: str = "", timeout: float = 40.0,
        cli: str = "", no_preamble: bool = False) -> str:
    """モデルの回答を返す。落ちても止めない——空文字は呼び出し側が扱う。

    raises: subprocess.TimeoutExpired（呼び出し側が既に握っている）
    """
    cli = cli or which()
    if cli == "claude":
        r = subprocess.run(build(prompt, model, effort, cli=cli),
                           capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        return (r.stdout or "").strip()

    # codex: 最終回答は -o のファイルにしか無い（stdout は経過ログ）
    fd, out_path = tempfile.mkstemp(prefix="meetlive_codex_", suffix=".txt")
    os.close(fd)
    try:
        subprocess.run(build(prompt, model, effort, cli=cli, out_path=out_path,
                             no_preamble=no_preamble),
                       capture_output=True, text=True, timeout=timeout,
                       stdin=subprocess.DEVNULL)
        with open(out_path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


if __name__ == "__main__":  # 手で1回叩いて配管を確かめるため
    import sys
    print(f"cli={which()}")
    print(" ".join(build("<prompt>", "<model>", "<effort>")))
    if len(sys.argv) > 1:
        print(run(sys.argv[1], timeout=60))
