'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const S = require('./fixtures/support.js');
const { normalizeBoardV2, stateOf } = require(path.join(S.HELPER_DIR, 'lib', 'board.js'));
const { parseNotes } = require(path.join(S.HELPER_DIR, 'lib', 'notes.js'));

const NOTES = '自分：山田\n## 前回の決定\n- 切り替えは4月1日\n## 今日伝えること\n- 予算の上限は150万円\n## 今日聞くこと\n1. 月額はいくらか\n2. 解約の連絡はいつまでか\n3. スマホ打刻のルールは';
const SPEC = parseNotes(NOTES);

function topic(title, extra) {
  return Object.assign({ title, current: false, points: [], decisions: [], todos: [], numbers: [] }, extra || {});
}
function v2(raw, prev) {
  const r = normalizeBoardV2(raw, { hasNotes: true, spec: SPEC, prev: prev || null });
  assert.equal(r.ok, true, r.error);
  return r.board;
}

// ── 聞くことの表（3 状態） ──────────────────────────────────
test('聞くことの表: 文言と順番は事前メモのまま。claude が何を返しても変わらない（知らない id は無視）', () => {
  const b = v2({
    topics: [],
    checklist: [
      { id: 'q4', state: 'done', evidence: 'はい（佐々木）' },
      { id: 'zz', item: '作り話の項目', state: 'done' },
      { id: 'q2', item: '書き換えられた文言', state: 'done', evidence: '1人月350円（佐々木）' },
    ],
  });
  assert.deepEqual(b.checklist.map((c) => [c.id, c.kind, c.item, c.state]), [
    ['q1', 'tell', '予算の上限は150万円', 'open'],
    ['q2', 'ask', '月額はいくらか', 'done'],
    ['q3', 'ask', '解約の連絡はいつまでか', 'open'],
    ['q4', 'ask', 'スマホ打刻のルールは', 'done'],
  ]);
  assert.equal(b.checklist[1].evidence, '1人月350円（佐々木）');
  assert.equal(b.checklist[1].done, true, '0.1 の形の done も残す');
  assert.equal(b.schema, 2);
});

test('聞くことの表: 持ち帰りは担当（誰）つき。宿題に ref があれば少なくとも持ち帰りで、担当は宿題の who', () => {
  const b = v2({
    topics: [topic('スマホ打刻', { todos: [{ who: '佐々木', what: '端末のルールを確認', when: '来週金曜', ref: 'q4' }] })],
    checklist: [
      { id: 'q3', state: 'deferred', owner: '佐々木', evidence: '契約書を確認して回答' },
      { id: 'q4', state: 'open', evidence: '設計書には記載なし。担当に確認して回答' },
    ],
  });
  const q3 = b.checklist.find((c) => c.id === 'q3');
  const q4 = b.checklist.find((c) => c.id === 'q4');
  assert.deepEqual([q3.state, q3.owner, q3.done], ['deferred', '佐々木', false]);
  assert.deepEqual([q4.state, q4.owner], ['deferred', '佐々木']);
  assert.equal(q4.evidence, '設計書には記載なし。担当に確認して回答');
  assert.equal(b.topics[0].todos[0].ref, 'q4');
});

test('聞くことの表: 0.1 の形（item と done だけ）も読む。返ってこなかった項目は前回の状態のまま。済は claude では戻さない', () => {
  const first = v2({ topics: [], checklist: [{ item: '月額はいくらか', done: true, evidence: '350円' }, { id: 'q3', state: 'deferred', owner: '佐々木' }] });
  assert.equal(first.checklist[1].state, 'done', '文言の一致で当てる');
  const second = v2({ topics: [], checklist: [{ id: 'q2', state: 'open' }, { id: 'q3', state: 'open' }] }, first);
  assert.equal(second.checklist[1].state, 'done', '済はまだに戻さない');
  assert.equal(second.checklist[1].evidence, '350円', '根拠は前回のものを残す');
  assert.equal(second.checklist[2].state, 'deferred', '持ち帰りもまだに戻さない');
  assert.equal(second.checklist[2].owner, '佐々木');
  const third = v2({ topics: [], checklist: [{ id: 'q3', state: 'done', evidence: '2か月前（佐々木）' }] }, second);
  assert.equal(third.checklist[2].state, 'done', '持ち帰り → 済 はよい');
});

test('stateOf: 3 状態の言い方の揺れを寄せる。分からなければ null', () => {
  assert.equal(stateOf({ state: '済' }), 'done');
  assert.equal(stateOf({ state: '持ち帰り' }), 'deferred');
  assert.equal(stateOf({ state: 'まだ' }), 'open');
  assert.equal(stateOf({ done: true }), 'done');
  assert.equal(stateOf({ done: false }), 'open');
  assert.equal(stateOf({ state: '???' }), null);
  assert.equal(stateOf(null), null);
});

test('聞くことの表: 事前メモに見出しが無ければ、claude が作った表を 3 状態で使う。事前メモが無ければ空', () => {
  const r = normalizeBoardV2(
    { topics: [], checklist: [{ item: '月額', state: 'deferred', owner: '佐々木' }, { item: '納期', done: true }, { item: '' }] },
    { hasNotes: true, spec: parseNotes('見出しの無いメモ\n- 月額\n- 納期'), prev: null }
  );
  assert.deepEqual(r.board.checklist.map((c) => [c.id, c.item, c.state, c.owner]), [
    ['c1', '月額', 'deferred', '佐々木'],
    ['c2', '納期', 'done', ''],
  ]);
  const none = normalizeBoardV2({ topics: [], checklist: [{ item: 'x', done: true }] }, { hasNotes: false, spec: parseNotes(''), prev: null });
  assert.deepEqual(none.board.checklist, []);
});

// ── 話題の id・引き継ぎ・雑音 ───────────────────────────────
test('話題: id を付けて引き継ぐ。題名は一度出たら変えない。前回にあって今回に無い話題は元の位置に残す', () => {
  const a = v2({ topics: [topic('現状の確認', { headline: '締めに毎月3日' }), topic('候補2社の費用', { current: true })] });
  assert.deepEqual(a.topics.map((t) => [t.id, t.title]), [['t1', '現状の確認'], ['t2', '候補2社の費用']]);
  assert.equal(a.topics[0].headline, '締めに毎月3日');
  const b = v2({ topics: [topic('別の名前にした', { id: 't2', current: true }), topic('切り替えの時期')] }, a);
  assert.deepEqual(b.topics.map((t) => [t.id, t.title, t.current]), [
    ['t1', '現状の確認', false],
    ['t2', '候補2社の費用', true],
    ['t3', '切り替えの時期', false],
  ]);
  assert.ok(Object.keys(b.topics[0])[0] === 'title' && Object.keys(b)[0] === 'topics', 'topics・title が先頭（前回のボードとして渡す形）');
});

test('話題: あいさつ・接続の確認・自己紹介だけの話題は出さない（中身があれば残す）', () => {
  const b = v2({
    topics: [
      topic('冒頭のあいさつと音声確認', { points: [{ speaker: '山田', text: '聞こえますか' }] }),
      topic('自己紹介', { points: [{ speaker: '佐々木', text: '佐々木です' }] }),
      topic('会議の進め方', { decisions: ['30分で終える'] }),
      topic('勤怠システムの入れ替え', { current: true }),
    ],
  });
  assert.deepEqual(b.topics.map((t) => t.title), ['会議の進め方', '勤怠システムの入れ替え']);
});

test('カードは多くても 2 枚', () => {
  const b = v2({ topics: [], cards: [1, 2, 3].map((n) => ({ title: 'メモ' + n, body: '中身' })) });
  assert.equal(b.cards.length, 2);
});
