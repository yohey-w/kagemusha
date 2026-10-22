'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const S = require('./fixtures/support.js');
const { parseNotes } = require(path.join(S.HELPER_DIR, 'lib', 'notes.js'));

test('parseNotes: 付属の事前メモから、聞くこと・伝えること（文言と順番そのまま）と前提・前回の決定・使う人を読む', () => {
  const spec = parseNotes(fs.readFileSync(path.join(S.SAMPLE_DIR, 'sample_notes.md'), 'utf8'));
  assert.deepEqual(
    spec.items.map((x) => [x.id, x.kind, x.text]),
    [
      ['q1', 'tell', '予算の上限は年額150万円であること。'],
      ['q2', 'ask', '新システムの月額（1人あたり）はいくらか。'],
      ['q3', 'ask', '現行システムの契約はいつ終わり、解約の連絡はいつまでに必要か。'],
      ['q4', 'ask', 'スマホで打刻する場合、社内の端末・セキュリティのルールはどうなっているか。'],
    ]
  );
  assert.deepEqual(
    spec.beliefs.map((x) => [x.id, x.kind, x.text]),
    [
      ['a1', 'decision', '切り替えは来年の4月1日に行う。'],
      ['a2', 'belief', '解約の連絡は1か月前で足りる。'],
    ],
    '括弧だけの注記の行は項目にしない'
  );
  assert.equal(spec.me, '山田');
});

test('parseNotes: 見出しの揺れ（【】・「：」で終わる行・### ）と番号の書き方を読む', () => {
  const a = parseNotes('【今日聞くこと】\n1) 月額は？\n② 初期費用は？\n\n確認事項：\n・納期\n### 質問\n* 保守の窓口');
  assert.deepEqual(a.items.map((x) => x.text), ['月額は？', '初期費用は？', '納期', '保守の窓口']);
  assert.ok(a.items.every((x) => x.kind === 'ask'));
  assert.deepEqual(a.items.map((x) => x.no), [1, 2, 3, 4]);
});

test('parseNotes: 「聞くこと／伝えること」が 1 つの見出しなら、項目の言い方で伝えるを見分ける', () => {
  const s = parseNotes('## 今日聞くこと・伝えること\n- 月額はいくらか\n- 予算の上限を伝える\n- 伝える：来月から担当が替わる');
  assert.deepEqual(s.items.map((x) => x.kind), ['ask', 'tell', 'tell']);
});

test('parseNotes: 「前回の決定・前提」は decision。字下げの続きの行は前の項目に入る', () => {
  const s = parseNotes('## 前回の決定・前提\n- 切り替えは4月1日\n  （人事と合意済み）\n## 聞くこと\n- 月額\n    1人あたりで');
  assert.deepEqual(s.beliefs, [{ id: 'a1', kind: 'decision', text: '切り替えは4月1日 （人事と合意済み）' }]);
  assert.equal(s.items[0].text, '月額 1人あたりで');
});

test('parseNotes: 見出しが無い・知らない見出しだけのメモは空。上限と長さを守る', () => {
  assert.deepEqual(parseNotes('ただのメモです\n- 何か'), { items: [], beliefs: [], me: '' });
  assert.deepEqual(parseNotes('## 手元の数字\n- 年額 96万円').items, []);
  assert.deepEqual(parseNotes(''), { items: [], beliefs: [], me: '' });
  const many = parseNotes('## 聞くこと\n' + Array.from({ length: 40 }, (_, i) => '- 問い' + i + 'あ'.repeat(300)).join('\n'));
  assert.equal(many.items.length, 30);
  assert.ok(many.items.every((x) => x.text.length <= 201));
});
