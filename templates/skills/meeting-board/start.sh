#!/usr/bin/env bash
# 会議ボード: ヘルパーを起動します（mac / linux）。止めるときは Ctrl+C。
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js が見つかりません。https://nodejs.org/ja/download から入れてください（18 以上）。" >&2
  exit 1
fi
if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)'; then
  echo "Node.js が古すぎます（$(node --version)）。18 以上を入れてください。" >&2
  exit 1
fi

exec node "$here/helper/server.js" --open "$@"
