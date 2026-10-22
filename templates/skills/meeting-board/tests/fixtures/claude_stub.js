#!/usr/bin/env node
'use strict';
// テスト用の偽 claude（本物は呼ばない）。振る舞いは環境変数で決める:
//   STUB_LOG    呼び出しの記録を追記するファイル（1 行 1 回の JSON: argv と標準入力）
//   STUB_MODE   ok（既定） | old-cli | error-json | limit-json | garbage | slow | exit1 | empty
//                 old-cli   --tools / --safe-mode / --no-session-persistence を知らない古い版のふり
//   STUB_BOARD  返すボードの JSON ファイル（無ければ内蔵の小さなボード）
//   STUB_WRAP   ボードの包み方: raw（既定）| fence | prose
//   STUB_DELAY_MS  返事を返すまでの待ち（ミリ秒。更新の最中に別の操作が入る試験用）
const fs = require('fs');

const argv = process.argv.slice(2);

if (argv.includes('--version')) {
  console.log('9.9.9 (Stub Code)');
  process.exit(0);
}

let stdin = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (d) => {
  stdin += d;
});
process.stdin.on('end', () => {
  const mode = process.env.STUB_MODE || 'ok';
  if (process.env.STUB_LOG) {
    fs.appendFileSync(process.env.STUB_LOG, JSON.stringify({ argv, stdin }) + '\n');
  }

  const oldFlags = ['--tools', '--safe-mode', '--no-session-persistence'];
  if (mode === 'old-cli') {
    const bad = argv.find((a) => oldFlags.includes(a));
    if (bad) {
      process.stderr.write("error: unknown option '" + bad + "'\n");
      process.exit(1);
    }
  }
  if (mode === 'exit1') {
    process.stderr.write('boom: something broke\n');
    process.exit(1);
  }
  if (mode === 'garbage') {
    process.stdout.write('これは JSON ではありません\n');
    process.exit(0);
  }
  if (mode === 'empty') {
    process.exit(0);
  }
  if (mode === 'slow') {
    setTimeout(() => process.exit(0), 60000);
    return;
  }
  if (mode === 'error-json') {
    process.stdout.write(
      JSON.stringify({ type: 'result', subtype: 'success', is_error: true, result: 'Invalid API key · Please run /login' }) + '\n'
    );
    process.exit(1);
  }
  if (mode === 'limit-json') {
    process.stdout.write(
      JSON.stringify({ type: 'result', subtype: 'success', is_error: true, result: '5-hour limit reached ∙ resets 3pm' }) + '\n'
    );
    process.exit(1);
  }

  let board;
  if (process.env.STUB_BOARD) {
    board = fs.readFileSync(process.env.STUB_BOARD, 'utf8').trim();
  } else {
    board = JSON.stringify({
      topics: [
        {
          title: '勤怠システムの入れ替え',
          current: true,
          points: [{ speaker: '山田', text: 'テスト用の発言' }],
          decisions: [],
          todos: [],
          numbers: [],
        },
      ],
      open_questions: [],
      checklist: [{ item: '月額はいくらか', done: false, evidence: '' }],
      cards: [{ title: '前回の決定', body: '切り替えは4月1日', why: '試験用', source: '事前メモ' }],
    });
  }
  const wrap = process.env.STUB_WRAP || 'raw';
  let result = board;
  if (wrap === 'fence') result = '```json\n' + board + '\n```';
  if (wrap === 'prose') result = '整理しました。\n\n' + board + '\n\n以上です。';
  // 本物の claude -p --output-format json と同じく、費用と所要時間（数字）も付ける
  const out =
    JSON.stringify({ type: 'result', subtype: 'success', is_error: false, result, total_cost_usd: Number(process.env.STUB_COST_USD || 0.0125), duration_ms: 4321 }) + '\n';
  const delay = Number(process.env.STUB_DELAY_MS || 0);
  setTimeout(() => {
    process.stdout.write(out, () => process.exit(0));
  }, delay);
});
