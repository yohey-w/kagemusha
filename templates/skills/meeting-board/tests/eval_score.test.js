'use strict';
// 品質の物差し（tests/eval/score_board.js）の採点そのものの試験。物差しを本物の claude で回すのは手で（README）
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const S = require('./fixtures/support.js');
const { scoreBoard } = require(path.join(__dirname, 'eval', 'score_board.js'));
const { normalizeBoardV2 } = require(path.join(S.HELPER_DIR, 'lib', 'board.js'));
const { parseNotes } = require(path.join(S.HELPER_DIR, 'lib', 'notes.js'));

function fixtureBoard() {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'board_v2_sample.json'), 'utf8'));
  const spec = parseNotes(fs.readFileSync(path.join(S.SAMPLE_DIR, 'sample_notes.md'), 'utf8'));
  return normalizeBoardV2(raw, { hasNotes: true, spec, prev: null, users: ['山田'] }).board;
}

test('物差し: 架空のボードを採点し、外れた項目を NG にする（使う人の発言の割合・あいさつの話題・前提の食い違い）', () => {
  const b = fixtureBoard();
  const r = scoreBoard(b, { me: '山田' });
  const by = Object.fromEntries(r.rows.map((x) => [x.name, x]));
  assert.equal(by['話題の数'].ok, true);
  assert.equal(by['要点のうち使う人の発言の割合'].ok, true);
  assert.equal(by['聞くこと q4 の状態'].ok, false, '架空のボードでは q4 はまだ（期待は持ち帰り）');
  assert.equal(by['前提の食い違いの再現率（仕込んだもののうち出したもの）'].value, '2/2');

  const worse = JSON.parse(JSON.stringify(b));
  worse.topics[0].title = '冒頭のあいさつ';
  worse.topics[0].points = [{ speaker: '山田', text: 'a' }, { speaker: '山田', text: 'b' }, { speaker: '山田', text: 'c' }];
  worse.premise_conflicts.push({ ref: '', heard: '作り話', speaker: '佐々木' });
  const w = Object.fromEntries(scoreBoard(worse, { me: '山田' }).rows.map((x) => [x.name, x]));
  assert.equal(w['あいさつ等の話題'].ok, false);
  assert.equal(w['要点のうち使う人の発言の割合'].ok, false);
  assert.equal(w['前提の食い違いの適合率（出したもののうち仕込んだもの）'].ok, false);
});
