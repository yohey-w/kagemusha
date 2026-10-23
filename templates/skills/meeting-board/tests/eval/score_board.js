#!/usr/bin/env node
'use strict';
// 品質の物差し（node --test には入れない。手で回す）。付属の架空の会議を本物の claude で整理した結果を採点する。
//
//   node helper/server.js --replay sample/sample_transcript.txt --notes sample/sample_notes.md --once > out.json
//   node tests/eval/score_board.js out.json [--me 山田]
//
// 合格線は付属の会議（sample/）に合わせてある。ほかの会議の結果に使うときは、checklist と前提の期待を読み替えること。
// 出すのは数字と合否だけ（本文は出さない）。合格線を 1 つでも割れば終了コード 1。

const fs = require('fs');

// 付属の会議で期待すること（事前メモ sample_notes.md と会話 sample_transcript.txt から）
const EXPECT = {
  topics: [3, 7],
  checklist: { q1: 'done', q2: 'done', q3: 'done', q4: 'deferred' },
  q4Owner: '佐々木',
  premiseRefs: ['a1', 'a2'], // a1: 切り替えは4月1日 → 5月に変更 / a2: 解約は1か月前 → 2か月前
};
const NOISE = /(あいさつ|挨拶|自己紹介|音声|聞こえ|接続確認|接続の確認|画面共有の確認|雑談|本日の進め方|会議の進め方)/;

function scoreBoard(board, opts) {
  const o = opts || {};
  const users = new Set([].concat(o.me ? [o.me] : [], Array.isArray(board.users) ? board.users : [], ['自分']));
  const topics = Array.isArray(board.topics) ? board.topics : [];
  const points = [];
  for (const t of topics) for (const p of t.points || []) points.push(p);
  const own = points.filter((p) => users.has(p.speaker)).length;
  const checklist = Array.isArray(board.checklist) ? board.checklist : [];
  const byId = Object.fromEntries(checklist.map((c) => [c.id, c]));
  const premiseWarn = (board.warnings || []).filter((w) => w.kind === 'premise');
  const conflicts = board.premise_conflicts || [];
  const flagged = premiseWarn.map((w) => w.ref).concat(conflicts.map((k) => k.ref));
  const correct = flagged.filter((r) => EXPECT.premiseRefs.includes(r)).length;
  const headlineMax = topics.reduce((n, t) => Math.max(n, String(t.headline || '').length), 0);
  const next = board.next_action && String(board.next_action.text || '');
  const rows = [];
  const row = (name, value, ok, line) => rows.push({ name, value, ok, line });
  row('話題の数', topics.length, topics.length >= EXPECT.topics[0] && topics.length <= EXPECT.topics[1], EXPECT.topics.join('〜'));
  row('あいさつ等の話題', topics.filter((t) => NOISE.test(t.title || '')).length, topics.every((t) => !NOISE.test(t.title || '')), '0');
  row('headline の最長（字）', headlineMax, headlineMax <= 40, '40 以下');
  row('要点のうち使う人の発言の割合', points.length ? Math.round((own / points.length) * 100) + '%（' + own + '/' + points.length + '）' : '—', points.length > 0 && own / points.length <= 0.2, '20% 以下');
  row('次の一手', next ? next.length + ' 字' : 'なし', !!next, 'あり');
  row('次の一手の長さ', next ? next.length : 0, !!next && next.length <= 30, '30 字以下');
  for (const id of Object.keys(EXPECT.checklist)) {
    const c = byId[id];
    row('聞くこと ' + id + ' の状態', c ? c.state + (c.owner ? '（' + c.owner + '）' : '') : 'なし', !!c && c.state === EXPECT.checklist[id] && (id !== 'q4' || c.owner === EXPECT.q4Owner), EXPECT.checklist[id] + (id === 'q4' ? '（' + EXPECT.q4Owner + '）' : ''));
  }
  row('「済」なのに根拠が空', checklist.filter((c) => c.state === 'done' && !c.evidence).length, checklist.every((c) => c.state !== 'done' || !!c.evidence), '0');
  row('前提の食い違いの適合率（出したもののうち仕込んだもの）', flagged.length ? Math.round((correct / flagged.length) * 100) + '%（' + correct + '/' + flagged.length + '）' : '出していない', flagged.length > 0 && correct === flagged.length, '100%');
  const found = EXPECT.premiseRefs.filter((r) => flagged.includes(r));
  row('前提の食い違いの再現率（仕込んだもののうち出したもの）', found.length + '/' + EXPECT.premiseRefs.length, found.length === EXPECT.premiseRefs.length, '2/2');
  row('ボードの JSON の字数（参考）', JSON.stringify(board).length, true, '—');
  return { rows, passed: rows.filter((r) => r.ok).length, total: rows.length };
}

function main(argv) {
  const file = argv.find((a) => !a.startsWith('--'));
  const meIdx = argv.indexOf('--me');
  if (!file) {
    console.error('使い方: node tests/eval/score_board.js <--once の出力の JSON> [--me 名前]');
    return 2;
  }
  const board = JSON.parse(fs.readFileSync(file, 'utf8'));
  const r = scoreBoard(board, { me: meIdx >= 0 ? argv[meIdx + 1] : '山田' });
  for (const x of r.rows) console.log((x.ok ? 'OK ' : 'NG ') + x.name + ': ' + x.value + '（合格線 ' + x.line + '）');
  console.log('合格 ' + r.passed + '/' + r.total);
  return r.passed === r.total ? 0 : 1;
}

if (require.main === module) process.exit(main(process.argv.slice(2)));

module.exports = { scoreBoard, EXPECT };
