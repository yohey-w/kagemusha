'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const S = require('./fixtures/support.js');
const { normalizeBoardV2, stateOf, toPromptBoard } = require(path.join(S.HELPER_DIR, 'lib', 'board.js'));
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

// ── 次の一手・警告・順調 ────────────────────────────────────

test('次の一手: claude が出さなくても、事前メモの順で最初の「まだ」から規則で作る（空にしない）', () => {
  const b = v2({ topics: [], checklist: [] });
  assert.deepEqual(b.next_action, { text: '伝える：予算の上限は150万円', reason: 'まだ伝えていない（事前メモの 1 番目）', ref: 'q1', by: 'rule' });
  const c = v2({ topics: [], checklist: [{ id: 'q1', state: 'done' }], next_action: 'ただの文字列' });
  assert.equal(c.next_action.text, '聞く：月額はいくらか');
  assert.equal(c.next_action.ref, 'q2');
});

test('次の一手: claude の提案が使えればそれ。済んだ項目を指したままの提案は使わない。知らない id は外す', () => {
  const ok = v2({ topics: [], checklist: [], next_action: { text: '解約の期限を聞く', reason: '契約の話が出た', ref: 'q3' } });
  assert.deepEqual(ok.next_action, { text: '解約の期限を聞く', reason: '契約の話が出た', ref: 'q3', by: 'llm' });
  const stale = v2({ topics: [], checklist: [{ id: 'q2', state: 'done' }], next_action: { text: '月額を聞く', reason: '', ref: 'q2' } });
  assert.equal(stale.next_action.by, 'rule', 'もう済んだことは次の一手にしない');
  const deferred = v2({ topics: [], checklist: [{ id: 'q3', state: 'deferred', owner: '佐々木' }], next_action: { text: '解約の期限を聞く', ref: 'q3' } });
  assert.equal(deferred.next_action.by, 'rule', '持ち帰りになった項目も次の一手にしない');
  const unknown = v2({ topics: [], checklist: [], next_action: { text: 'それとなく聞く', ref: 'q99' } });
  assert.equal(unknown.next_action.ref, '');
});

test('次の一手: 全部「済」か「持ち帰り」なら、持ち帰りの読み上げ。事前メモが無く claude も出さなければ null', () => {
  const b = v2({
    topics: [topic('スマホ打刻', { todos: [{ who: '佐々木', what: 'ルール確認', ref: 'q4' }] })],
    checklist: ['q1', 'q2', 'q3'].map((id) => ({ id, state: 'done' })),
  });
  assert.equal(b.next_action.text, '持ち帰りを読み上げて確かめる');
  assert.match(b.next_action.reason, /持ち帰り 1 件/);
  const none = normalizeBoardV2({ topics: [] }, { hasNotes: false, spec: parseNotes(''), prev: null });
  assert.equal(none.board.next_action, null);
});

test('警告: ずれ・前提と違う・言い忘れだけ。相手の要点と返す一言がそろったものを多くても 2 つ', () => {
  const b = v2({
    topics: [],
    checklist: [{ id: 'q2', state: 'done' }],
    warnings: [
      { kind: 'premise', what: '解約の連絡は2か月前まで', speaker: '佐々木', reply: '1か月前と理解していたと確かめる', ref: 'zz' },
      { kind: 'missing', what: '月額をまだ聞いていない', reply: '月額を聞く', ref: 'q2' },
      { kind: 'echo', what: 'いま言ったこと', reply: '…' },
      { kind: 'drift', what: '', reply: '戻す' },
      { kind: 'drift', what: '雑談が続いている', speaker: '佐々木', reply: '本題に戻す' },
      { kind: 'drift', what: '三つ目', reply: '多すぎる' },
    ],
  });
  assert.deepEqual(b.warnings.map((w) => [w.kind, w.ref]), [['premise', ''], ['drift', '']]);
  assert.equal(b.warnings[0].speaker, '佐々木');
});

test('前提と食い違ったこと: 警告が消えても会議の間は残る（振り返り・議事録用）。同じものは重ねない', () => {
  const w = { kind: 'premise', what: '解約の連絡は2か月前まで', speaker: '佐々木', reply: '確かめる', ref: 'a1' };
  const a = normalizeBoardV2({ topics: [], warnings: [w] }, { hasNotes: true, spec: SPEC, prev: null, now: 1000 }).board;
  assert.deepEqual(a.premise_conflicts, [{ ref: 'a1', premise: '切り替えは4月1日', kind: 'decision', heard: '解約の連絡は2か月前まで', speaker: '佐々木', reply: '確かめる', settled: false, at: 1000 }]);
  const b = normalizeBoardV2({ topics: [], warnings: [w] }, { hasNotes: true, spec: SPEC, prev: a, now: 2000 }).board;
  assert.equal(b.premise_conflicts.length, 1);
  const c = normalizeBoardV2({ topics: [], warnings: [] }, { hasNotes: true, spec: SPEC, prev: b, now: 3000 }).board;
  assert.equal(c.premise_conflicts.length, 1, '警告が消えても残る');
  assert.deepEqual(c.warnings, []);
  // claude の conflicts（確かめ済みも含む）からも残す。同じ前提は 1 件にまとめ、確かめ済みの印を付ける
  const d = normalizeBoardV2(
    { topics: [], conflicts: [{ ref: 'a1', what: '5月12日に切り替えると決め直した', speaker: '佐々木', settled: true }, { ref: 'zz', what: '作り話の前提', speaker: '佐々木' }, { what: '' }] },
    { hasNotes: true, spec: SPEC, prev: c, now: 4000 }
  ).board;
  assert.equal(d.premise_conflicts.length, 2);
  assert.deepEqual([d.premise_conflicts[0].heard, d.premise_conflicts[0].settled], ['5月12日に切り替えると決め直した', true]);
  assert.equal(d.premise_conflicts[1].ref, '', '事前メモに無い前提の id は外す');
  assert.deepEqual(toPromptBoard(d).conflicts[0], { ref: 'a1', what: '5月12日に切り替えると決め直した', speaker: '佐々木', settled: true }, '次の回にも渡して消させない');
});

test('順調の 1 行は短く切る。前回のボードとして渡す形にヘルパーだけの欄（by・users・schema）は入れない', () => {
  const b = normalizeBoardV2(
    { topics: [topic('費用', { current: true })], status: 'あ'.repeat(100), next_action: { text: '月額を聞く', ref: 'q2' } },
    { hasNotes: true, spec: SPEC, prev: null, users: ['山田'] }
  ).board;
  assert.ok(b.status.length <= 60);
  assert.deepEqual(b.users, ['山田']);
  const p = toPromptBoard(b);
  assert.equal(JSON.stringify(p).slice(0, 20), '{"topics":[{"title":');
  assert.deepEqual(Object.keys(p.next_action), ['text', 'reason', 'ref']);
  assert.ok(!('users' in p) && !('schema' in p) && !('premise_conflicts' in p));
  assert.deepEqual(p.conflicts, []);
  assert.deepEqual(Object.keys(p.checklist[0]), ['id', 'state', 'owner', 'evidence'], '文言は渡さない（事前メモの表で渡す）');
});

// ── 人が直した状態（d-2） ────────────────────────────────────
const { applyOverrides } = require(path.join(S.HELPER_DIR, 'lib', 'board.js'));

test('人が直した状態: claude より勝つ。次の一手と言い忘れの警告も直した状態に合わせる。元のボードは変えない', () => {
  const b = v2({ topics: [], checklist: [], warnings: [{ kind: 'missing', what: '予算をまだ伝えていない', reply: '予算を伝える', ref: 'q1' }] });
  assert.equal(b.next_action.ref, 'q1');
  const o = applyOverrides(b, { q1: { state: 'done' }, q3: { state: 'deferred', owner: '佐々木' }, zz: { state: 'done' }, q4: { state: 'へん' } }, { spec: SPEC });
  assert.deepEqual(o.checklist.map((c) => [c.id, c.state, c.owner, !!c.byUser]), [
    ['q1', 'done', '', true],
    ['q2', 'open', '', false],
    ['q3', 'deferred', '佐々木', true],
    ['q4', 'open', '', false],
  ]);
  assert.equal(o.next_action.ref, 'q2', '規則の一手は、直した状態で最初の「まだ」へ');
  assert.deepEqual(o.warnings, [], '済にした項目の言い忘れは出さない');
  assert.equal(b.checklist[0].state, 'open', '元のボードは変えない');
  // 次の整理で claude が「まだ」と返しても、人の「済」が勝つ（前回のボードに直した状態が入っている）
  const next = applyOverrides(v2({ topics: [], checklist: [{ id: 'q1', state: 'open' }] }, o), { q1: { state: 'done' } }, { spec: SPEC });
  assert.equal(next.checklist[0].state, 'done');
  // 人が「まだ」に戻すこともできる（claude の済より勝つ）
  const back = applyOverrides(v2({ topics: [], checklist: [{ id: 'q2', state: 'done' }] }), { q2: { state: 'open' } }, { spec: SPEC });
  assert.equal(back.checklist[1].state, 'open');
  assert.deepEqual(toPromptBoard(o).checklist[0], { id: 'q1', state: 'done', owner: '', evidence: '', by_user: true }, '直した印は claude にも渡す');
});
