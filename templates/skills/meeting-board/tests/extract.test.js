'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { extractJsonObject, normalizeBoard } = require(path.join(__dirname, '..', 'helper', 'lib', 'extract.js'));

const BOARD = {
  topics: [{ title: '勤怠システムの入れ替え', current: true, points: [{ speaker: '山田', text: '候補は2社です' }], decisions: [], todos: [], numbers: [] }],
  open_questions: [],
  checklist: [],
  cards: [],
};
const JSON_TEXT = JSON.stringify(BOARD);

test('extractJsonObject: JSON だけの返事', () => {
  assert.deepEqual(extractJsonObject(JSON_TEXT), BOARD);
  assert.deepEqual(extractJsonObject('﻿  ' + JSON_TEXT + '\n'), BOARD);
});

test('extractJsonObject: コードフェンスつき', () => {
  assert.deepEqual(extractJsonObject('```json\n' + JSON_TEXT + '\n```'), BOARD);
  assert.deepEqual(extractJsonObject('```\n' + JSON_TEXT + '\n```\n'), BOARD);
});

test('extractJsonObject: 前置き・後書きつき', () => {
  assert.deepEqual(extractJsonObject('整理しました。\n\n' + JSON_TEXT + '\n\n以上です。'), BOARD);
  assert.deepEqual(extractJsonObject('はい、こちらです:\n```json\n' + JSON_TEXT + '\n```\nご確認ください'), BOARD);
});

test('extractJsonObject: 文字列の中の波括弧・引用符に惑わされない', () => {
  const tricky = {
    topics: [{ title: '波括弧 { } の話', current: true, points: [{ speaker: '山田', text: '「{"a": 1}」と言いました \\ バックスラッシュ' }], decisions: [], todos: [], numbers: [] }],
    open_questions: [],
    checklist: [],
    cards: [],
  };
  const text = '前置き { これは JSON ではない }\n' + JSON.stringify(tricky) + '\n後書き }';
  assert.deepEqual(extractJsonObject(text), tricky);
});

test('extractJsonObject: 末尾のカンマは直して読む（文字列の中のカンマは触らない）', () => {
  const text = '{"topics": [{"title": "a,}", "current": true,}], "open_questions": [],}';
  const obj = extractJsonObject(text);
  assert.equal(obj.topics[0].title, 'a,}');
});

test('extractJsonObject: topics を持つものを優先する', () => {
  const text = '{"note": "メモ"}\n' + JSON_TEXT;
  assert.deepEqual(extractJsonObject(text), BOARD);
});

test('extractJsonObject: JSON が無ければ null', () => {
  assert.equal(extractJsonObject('JSON はありません'), null);
  assert.equal(extractJsonObject(''), null);
  assert.equal(extractJsonObject('{ 壊れた'), null);
  assert.equal(extractJsonObject(undefined), null);
});

test('normalizeBoard: topics が配列でなければ失敗（前のボードを残させる）', () => {
  assert.equal(normalizeBoard({}, { hasNotes: true }).ok, false);
  assert.equal(normalizeBoard({ topics: 'x' }, { hasNotes: true }).ok, false);
  assert.equal(normalizeBoard(null, {}).ok, false);
});

test('normalizeBoard: 欠けた項目を補い、current は最後のひとつだけにする', () => {
  const r = normalizeBoard(
    {
      topics: [
        { title: 'A', current: true },
        { title: 'B', current: true, points: [{ speaker: '山田', text: ' 発言 ' }, { text: '' }, '文字列だけの発言'], todos: [{ who: '佐々木', what: '確認する' }, { what: '' }], numbers: [100, '月額 400円'] },
      ],
    },
    { hasNotes: false }
  );
  assert.equal(r.ok, true);
  const [a, b] = r.board.topics;
  assert.equal(a.current, false);
  assert.equal(b.current, true);
  assert.deepEqual(a.points, []);
  assert.deepEqual(b.points, [
    { speaker: '山田', text: '発言' },
    { speaker: '', text: '文字列だけの発言' },
  ]);
  assert.deepEqual(b.todos, [{ who: '佐々木', what: '確認する', when: '' }]);
  assert.deepEqual(b.numbers, ['100', '月額 400円']);
  assert.deepEqual(r.board.open_questions, []);
});

test('normalizeBoard: 事前メモが無ければ checklist / cards は空にする。あれば cards は 3 枚まで', () => {
  const raw = {
    topics: [],
    checklist: [{ item: '聞くこと1', done: true, evidence: '山田「はい」' }, { item: '' }],
    cards: [1, 2, 3, 4].map((n) => ({ title: 'カード' + n, body: '中身', why: '理由', source: '出所' })),
  };
  const without = normalizeBoard(raw, { hasNotes: false });
  assert.deepEqual(without.board.checklist, []);
  assert.deepEqual(without.board.cards, []);
  const withNotes = normalizeBoard(raw, { hasNotes: true });
  assert.deepEqual(withNotes.board.checklist, [{ item: '聞くこと1', done: true, evidence: '山田「はい」' }]);
  assert.equal(withNotes.board.cards.length, 3);
});
