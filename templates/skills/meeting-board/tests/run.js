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
const r = spawnSync(process.execPath, ['--test'].concat(files), { stdio: 'inherit' });
process.exit(r.status === null ? 1 : r.status);
