#!/usr/bin/env node
'use strict';
// 試験の入口: このフォルダの *.test.js を明示して node --test に渡す。
// シェルの展開（Windows の cmd は *.test.js を展開しない）や Node の版（22 以上は
// 「node --test フォルダ」を受け付けない）に左右されずに、Node 18 以上のどれでも同じ命令で動く。
//   node tests/run.js        （このスキルのフォルダで）
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const files = fs
  .readdirSync(__dirname)
  .filter((f) => f.endsWith('.test.js'))
  .sort()
  .map((f) => path.join(__dirname, f));

if (files.length === 0) {
  console.error('試験ファイル（*.test.js）が見つかりません: ' + __dirname);
  process.exit(1);
}
// 画面ではなくファイルやパイプへ出すときは TAP（「# pass N」の集計行）にする。Node 18〜22 は元からそうだったが、
// 23 以降は既定が spec になり、scripts/test.sh の P7 が件数を読めなくなった。--test-reporter が無い古い 18 では付けない
const [maj, min] = process.versions.node.split('.').map(Number);
const hasReporterFlag = maj > 19 || (maj === 19 && min >= 6) || (maj === 18 && min >= 15);
const args = ['--test'];
if (!process.stdout.isTTY && hasReporterFlag) args.push('--test-reporter=tap');
const r = spawnSync(process.execPath, args.concat(files), { stdio: 'inherit' });
process.exit(r.status === null ? 1 : r.status);
