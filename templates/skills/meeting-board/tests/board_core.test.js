'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const S = require('./fixtures/support.js');
const V = require(path.join(S.HELPER_DIR, 'board-core.js'));

const NOW = new Date(2026, 9, 21, 10, 30, 0).getTime();

function state(board, extra) {
  const st = {
    status: {
      now: NOW,
      version: 'test',
      captions: { state: 'receiving', ageSec: 1 },
      update: { count: 3, lastAt: NOW - 30000, inFlight: false, pendingChars: 0, intervalSec: 60 },
      lastError: null,
    },
    board,
    recent: [],
    notesPresent: true,
    selfName: '',
  };
  return Object.assign(st, extra || {});
}

const BOARD = {
  topics: [
    { title: '候補2社の費用', id: 't1', headline: 'B社に決定', current: false, points: [{ speaker: '佐々木', text: 'B社は月額350円' }, { speaker: '山田', text: 'それでお願いします' }], decisions: ['B社で進める'], todos: [], numbers: ['B社 月額350円'] },
    { title: '切り替えの時期', id: 't2', headline: '', current: true, points: [{ speaker: '佐々木', text: '5月の連休明けが安全' }], decisions: [], todos: [{ who: '山田', what: '延長の費用を聞く', when: '今月末', ref: 'q4' }], numbers: [] },
  ],
  open_questions: ['延長だと割増になるか'],
  checklist: [
    { id: 'q1', kind: 'tell', item: '予算の上限は150万円であること。', state: 'done', owner: '', evidence: '山田が伝えた', done: true },
    { id: 'q2', kind: 'ask', item: '新システムの月額（1人あたり）はいくらか。', state: 'done', owner: '', evidence: '350円（佐々木）', done: true },
    { id: 'q3', kind: 'ask', item: '解約の連絡はいつまでに必要か。', state: 'open', owner: '', evidence: '', done: false },
    { id: 'q4', kind: 'ask', item: 'スマホ打刻のルールはどうなっているか。', state: 'deferred', owner: '佐々木', evidence: '', done: false },
  ],
  cards: [],
  next_action: { text: '解約の期限を聞く', reason: '契約の話が出た', ref: 'q3', by: 'llm' },
  warnings: [],
  status: '費用は済み。次は切り替えの時期',
  premise_conflicts: [],
  users: ['山田'],
  schema: 2,
};

// ── 会議中の画面 ─────────────────────────────────────────────
test('会議中: 次の一手（1 行）・順調・伝え済み／まだ・あと○つ。話題の一覧や表の全体は出さない', () => {
  const m = V.meetingView(state(BOARD));
  assert.deepEqual(m.next, { text: '解約の期限を聞く', reason: '契約の話が出た', placeholder: false });
  assert.equal(m.warning, null, '警告が無ければ何も出さない');
  assert.deepEqual(m.ok, { text: '費用は済み。次は切り替えの時期' });
  assert.deepEqual(m.items.map((x) => [x.id, x.state, x.label, x.next]), [
    ['q1', 'done', '伝え済み', false],
    ['q2', 'done', '済', false],
    ['q3', 'open', 'まだ', true],
    ['q4', 'deferred', '持ち帰り（佐々木）', false],
  ]);
  assert.equal(m.items[1].text, '新システムの月額（1人あたり）はいくらか', '句点を落とし短く');
  assert.ok(m.items.every((x) => x.text.length <= 26));
  assert.equal(m.left, 'あと1つ');
  assert.deepEqual(Object.keys(m).sort(), ['items', 'left', 'next', 'ok', 'stale', 'updatedText', 'updating', 'warning']);
  assert.equal(m.stale.stale, false);
  assert.match(m.updatedText, /^最終更新 10:29:30（更新 3 回）$/);
});

test('会議中: 警告があるときだけ赤（相手の要点＋返す一言）。そのときは順調を出さない', () => {
  const b = Object.assign({}, BOARD, {
    warnings: [
      { kind: 'premise', what: '解約の連絡は2か月前まで', speaker: '佐々木', reply: '1か月前と理解していたと確かめる', ref: 'a2' },
      { kind: 'drift', what: '雑談が続いている', speaker: '', reply: '本題に戻す', ref: '' },
    ],
  });
  const m = V.meetingView(state(b));
  assert.deepEqual(m.warning, { label: '前提と違います', what: '佐々木：解約の連絡は2か月前まで', reply: '1か月前と理解していたと確かめる', more: 1 });
  assert.equal(m.ok, null);
});

test('会議中: 次の一手はいつも何か出す（事前メモが無い・まだ整理が無い・claude が出さない）', () => {
  assert.match(V.meetingView(state(null, { notesPresent: false })).next.text, /事前メモ/);
  assert.equal(V.meetingView(state(null, { notesPresent: false })).next.placeholder, true);
  assert.match(V.meetingView(state(null)).next.text, /字幕が届くと/);
  const noNext = Object.assign({}, BOARD, { next_action: null });
  assert.ok(V.meetingView(state(noNext)).next.text);
  const m0 = V.meetingView(state(null));
  assert.equal(m0.warning, null);
  assert.equal(m0.ok, null);
  assert.deepEqual(m0.items, []);
  assert.equal(m0.left, '');
});

test('会議中: 順調の 1 行は claude が書かなければ表から作る。全部済なら「全部済」', () => {
  const b = Object.assign({}, BOARD, { status: '', checklist: BOARD.checklist.map((c) => Object.assign({}, c, { state: 'done' })) });
  const m = V.meetingView(state(b));
  assert.equal(m.ok.text, '済 4・持ち帰り 0・まだ 0');
  assert.equal(m.left, '全部済');
  const d = Object.assign({}, b, { checklist: b.checklist.map((c, i) => Object.assign({}, c, { state: i === 3 ? 'deferred' : 'done' })) });
  assert.equal(V.meetingView(state(d)).left, 'あと0・持ち帰り1', '持ち帰りが残っていれば「全部済」とは言わない');
});

test('会議中: 整理でエラー・または字幕は進んでいるのに整理が古い → 薄くして「○分前の内容」。整理中の印', () => {
  const err = V.meetingView(state(BOARD, { status: Object.assign({}, state(BOARD).status, { lastError: { at: NOW, kind: 'internal', message: '内部エラー' }, update: { count: 3, lastAt: NOW - 4 * 60000, inFlight: false, pendingChars: 0, intervalSec: 60 } }) }));
  assert.deepEqual(err.stale, { stale: true, minutes: 4, text: '4分前の内容' });
  const old = state(BOARD);
  old.status.update = { count: 3, lastAt: NOW - 10 * 60000, inFlight: true, pendingChars: 500, intervalSec: 60 };
  const m = V.meetingView(old);
  assert.equal(m.stale.text, '10分前の内容');
  assert.equal(m.updating, true);
  const quiet = state(BOARD);
  quiet.status.captions.state = 'stalled';
  quiet.status.update = { count: 3, lastAt: NOW - 10 * 60000, inFlight: false, pendingChars: 0, intervalSec: 60 };
  assert.equal(V.meetingView(quiet).stale.stale, false, '字幕が止まっていて未反映も無いなら、古くても正しい内容');
  assert.equal(V.meetingView(state(null, { status: Object.assign({}, state(null).status, { lastError: { at: NOW, kind: 'x', message: 'x' } }) })).stale.stale, false, 'ボードが無ければ薄くしない');
});

// ── 会議の前と後 ─────────────────────────────────────────────
test('会議の前と後: 決まったこと・宿題・結果（まだ／持ち帰りが上・済は別）・話題は新しい順、自分の発言は数だけ', () => {
  const a = V.afterView(state(BOARD));
  assert.deepEqual(a.decisions, [{ text: 'B社で進める', topic: '候補2社の費用' }]);
  assert.deepEqual(a.todos, [{ who: '山田', what: '延長の費用を聞く', when: '今月末', topic: '切り替えの時期' }]);
  assert.deepEqual(a.checkOpen.map((c) => [c.id, c.label]), [['q3', 'まだ'], ['q4', '持ち帰り（佐々木）']]);
  assert.deepEqual(a.checkDone.map((c) => c.id), ['q1', 'q2']);
  assert.deepEqual(a.topics.map((t) => t.id), ['t2', 't1'], '新しい話題が上');
  const t1 = a.topics[1];
  assert.deepEqual(t1.points.map((p) => p.speaker), ['佐々木']);
  assert.equal(t1.hiddenSelf, 1);
  assert.equal(a.topics[0].headline, '5月の連休明けが安全', 'headline が無ければ相手の最初の要点');
  assert.deepEqual(a.openQuestions, ['延長だと割増になるか']);
});

test('会議の前と後: 0.1 の形のボード（done だけ・id なし）も描ける', () => {
  const v1 = { topics: [{ title: '勤怠', current: true, points: [{ speaker: '佐々木', text: 'はい' }], decisions: [], todos: [], numbers: [] }], open_questions: [], checklist: [{ item: '月額', done: true, evidence: '400円' }, { item: '納期', done: false, evidence: '' }], cards: [{ title: 'メモ', body: '中身' }] };
  const a = V.afterView(state(v1));
  assert.deepEqual(a.checkDone.map((c) => c.item), ['月額']);
  assert.deepEqual(a.checkOpen.map((c) => c.label), ['まだ']);
  assert.equal(a.topics[0].id, '勤怠');
  const m = V.meetingView(state(v1));
  assert.equal(m.left, 'あと1つ');
  assert.equal(m.ok.text, '済 1・持ち帰り 0・まだ 1');
});

test('欄の名前は役目そのもの（カード →「今使えるメモ」など）。どの欄にも 1 行の説明がある', () => {
  assert.equal(V.LABELS.cards.title, '今使えるメモ');
  assert.equal(V.LABELS.open.title, 'まだ答えをもらっていないこと');
  for (const k of Object.keys(V.LABELS)) assert.ok(V.LABELS[k].title && V.LABELS[k].help, k);
});

test('board-core.js は <script> に埋め込める（</script を含まない・fetch を使わない・DOM に触らない）', () => {
  const src = fs.readFileSync(path.join(S.HELPER_DIR, 'board-core.js'), 'utf8');
  assert.doesNotMatch(src, /<\/script/i);
  assert.doesNotMatch(src, /\bfetch\(|document\.|innerHTML/);
});
