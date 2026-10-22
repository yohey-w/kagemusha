'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const HELPER = path.join(__dirname, '..', 'helper');
const { Transcript, splitLongText } = require(path.join(HELPER, 'lib', 'transcript.js'));
const { buildWindow, buildPrompt, shouldUpdate, WHOLE_LIMIT, OVERLAP_CHARS } = require(path.join(HELPER, 'lib', 'prompt.js'));
const { parseReplayText, toEntries } = require(path.join(HELPER, 'lib', 'replay.js'));
const { parseArgs } = require(path.join(HELPER, 'lib', 'args.js'));

const T0 = new Date(2026, 9, 21, 9, 5, 0).getTime(); // ローカル 09:05（時差に左右されない）

function entry(i, speaker, text, at) {
  const t = at === undefined ? T0 + i * 60000 : at;
  return { id: 'e' + i, speaker, text, firstSeen: t, lastUpdate: t, final: true };
}

test('Transcript.lines: 「[HH:MM] 話者：発言」。__SELF__ は表示名に置き換える', () => {
  const tr = new Transcript();
  tr.upsert(entry(1, '山田', 'おはようございます'), T0);
  tr.upsert(entry(2, '__SELF__', 'よろしくお願いします'), T0);
  tr.upsert(entry(3, '', '話者が分からない発言'), T0);
  assert.deepEqual(
    tr.lines('渡辺').map((l) => l.text),
    ['[09:06] 山田：おはようございます', '[09:07] 渡辺：よろしくお願いします', '[09:08] 不明：話者が分からない発言']
  );
  assert.equal(tr.lines('').map((l) => l.text)[1], '[09:07] 自分：よろしくお願いします');
});

test('Transcript.upsert: id で上書き。古い版は無視、確定は戻らない', () => {
  const tr = new Transcript();
  assert.equal(tr.upsert({ id: 'a', speaker: '山田', text: 'こんにちは', firstSeen: T0, lastUpdate: T0 + 1000 }, T0), true);
  assert.equal(tr.upsert({ id: 'a', speaker: '山田', text: 'こんにちは、山田です', firstSeen: T0, lastUpdate: T0 + 2000 }, T0), true);
  assert.equal(tr.upsert({ id: 'a', speaker: '山田', text: 'こん', firstSeen: T0, lastUpdate: T0 + 500 }, T0), false);
  assert.equal(tr.entries.length, 1);
  assert.equal(tr.entries[0].text, 'こんにちは、山田です');
  assert.equal(tr.upsert({ id: 'a', speaker: '山田', text: 'こんにちは、山田です', firstSeen: T0, lastUpdate: T0 + 2000, final: true }, T0), true);
  assert.equal(tr.upsert({ id: 'a', speaker: '山田', text: 'こんにちは、山田です', firstSeen: T0, lastUpdate: T0 + 2500, final: false }, T0), false);
  assert.equal(tr.entries[0].final, true);
  assert.equal(tr.upsert({ id: '', text: 'x' }, T0), false);
  assert.equal(tr.upsert({ id: 'b', text: '   ' }, T0), false);
});

test('Transcript.upsert: 同じ id の更新は全文の置き換え（付け足さない）。3 回書き換わっても 1 行で最新の文面', () => {
  const tr = new Transcript();
  ['字。', '字幕。', '字幕を字幕の？'].forEach((text, i) => {
    tr.upsert({ id: 'blk', speaker: '山田', text, firstSeen: T0, lastUpdate: T0 + i * 500 }, T0 + i * 500);
  });
  assert.equal(tr.entries.length, 1);
  assert.equal(tr.entries[0].text, '字幕を字幕の？');
  assert.deepEqual(tr.lines('').map((l) => l.text), ['[09:05] 山田：字幕を字幕の？']);
  assert.equal(tr.toJsonl().split('\n').length, 1);
});

test('Transcript.settle: 話者が替わらず 6 秒伸びなければ確定。また伸びたら確定を取り消す（拡張機能の確定は戻さない）', () => {
  const tr = new Transcript();
  tr.upsert({ id: 'a', speaker: '山田', text: '長い説明の途中です', firstSeen: T0, lastUpdate: T0, final: false }, T0);
  assert.equal(tr.settle(T0 + 5999), 0);
  assert.equal(tr.entries[0].final, false);
  assert.equal(tr.settle(T0 + 6000), 1);
  assert.equal(tr.entries[0].final, true);
  assert.equal(tr.settle(T0 + 9000), 0, '確定済みは数えない');
  // 同じブロックがまた伸びた → まだ話している
  tr.upsert({ id: 'a', speaker: '山田', text: '長い説明の途中です。続けます', firstSeen: T0, lastUpdate: T0 + 9000, final: false }, T0 + 9000);
  assert.equal(tr.entries[0].final, false);
  assert.equal(tr.settle(T0 + 15000), 1);
  // 拡張機能が確定と言った発言は、あとから伸びても確定のまま
  tr.upsert({ id: 'b', speaker: '佐々木', text: '了解です', firstSeen: T0 + 16000, lastUpdate: T0 + 16000, final: true }, T0 + 16000);
  tr.upsert({ id: 'b', speaker: '佐々木', text: '了解です。進めます', firstSeen: T0 + 16000, lastUpdate: T0 + 17000, final: false }, T0 + 17000);
  assert.equal(tr.byId.get('b').final, true);
});

test('Transcript: firstSeen 順に並ぶ', () => {
  const tr = new Transcript();
  tr.upsert(entry(2, '佐々木', '二番目', T0 + 2000), T0);
  tr.upsert(entry(1, '山田', '一番目', T0 + 1000), T0);
  assert.deepEqual(tr.entries.map((e) => e.text), ['一番目', '二番目']);
});

test('splitLongText: 長い発言は文の切れ目で分ける（短ければそのまま）', () => {
  assert.deepEqual(splitLongText('短い', 600), ['短い']);
  const sentence = 'これは一文です。';
  const long = sentence.repeat(200); // 1600 字
  const parts = splitLongText(long, 600);
  assert.ok(parts.length >= 3);
  assert.ok(parts.every((p) => p.length <= 600));
  assert.ok(parts.slice(0, -1).every((p) => p.endsWith('。')));
  assert.equal(parts.join(''), long);
});

test('buildWindow: 12000 字以下なら「全部」', () => {
  const tr = new Transcript();
  for (let i = 0; i < 20; i++) tr.upsert(entry(i, '山田', 'あ'.repeat(100)), T0);
  const w = buildWindow(tr.lines(''), 7);
  assert.equal(w.range, '全部');
  assert.equal(w.lines.length, 20);
});

test('buildWindow: 超えたら「前回より後だけ」＋手前に約 2000 字の重なり', () => {
  const tr = new Transcript();
  for (let i = 0; i < 200; i++) tr.upsert(entry(i, '山田', String(i).padStart(3, '0') + 'あ'.repeat(97)), T0);
  const lines = tr.lines('');
  const total = lines.reduce((n, l) => n + l.text.length + 1, 0);
  assert.ok(total > WHOLE_LIMIT);
  const lastLineCount = 150;
  const w = buildWindow(lines, lastLineCount);
  assert.equal(w.range, '前回より後だけ');
  assert.equal(w.lines[w.lines.length - 1].text, lines[199].text);
  // 前回の最後の行（149 行目）は含まれ、その手前に重なりがある
  const idx = lines.findIndex((l) => l.text === w.lines[0].text);
  assert.ok(idx < lastLineCount - 1, '手前の行から始まる');
  const overlapChars = lines.slice(idx, lastLineCount - 1).reduce((n, l) => n + l.text.length + 1, 0);
  assert.ok(overlapChars >= OVERLAP_CHARS, '重なりは 2000 字以上: ' + overlapChars);
  assert.ok(overlapChars < OVERLAP_CHARS + 300, '重なりは 2000 字ほど: ' + overlapChars);
});

test('buildWindow: 字幕が書き換わって前回より行が減っても、いまの最後の行を越えて読まない', () => {
  // 0.1 では lines[start] が undefined になり「Cannot read properties of undefined (reading 'text')」で止まった
  const tr = new Transcript();
  for (let i = 0; i < 200; i++) tr.upsert(entry(i, '山田', String(i).padStart(3, '0') + 'あ'.repeat(97)), T0);
  const lines = tr.lines('');
  const w = buildWindow(lines, lines.length + 30);
  assert.equal(w.range, '前回より後だけ');
  assert.equal(w.lines[w.lines.length - 1].text, lines[199].text, 'いまの最後の行まで入る');
  assert.ok(w.lines.every((l) => l && typeof l.text === 'string'));
  const overlap = w.lines.slice(0, -1).reduce((n, l) => n + l.text.length + 1, 0);
  assert.ok(overlap >= OVERLAP_CHARS, '手前の重なりも付く: ' + overlap);
});

test('buildWindow: 初回（前回が無い）は長くても「全部」', () => {
  const tr = new Transcript();
  for (let i = 0; i < 200; i++) tr.upsert(entry(i, '山田', 'あ'.repeat(100)), T0);
  const w = buildWindow(tr.lines(''), 0);
  assert.equal(w.range, '全部');
  assert.equal(w.lines.length, 200);
});

test('buildPrompt: prompt.md のあとに 4 つの節が順に続く。無いものは「なし」', () => {
  const promptMd = fs.readFileSync(path.join(HELPER, 'prompt.md'), 'utf8');
  const lines = [{ text: '[09:05] 山田：こんにちは' }];
  const p = buildPrompt({ promptMd, notes: '', prevBoard: null, range: '全部', lines });
  assert.ok(p.startsWith(promptMd.replace(/\s+$/, '')), 'prompt.md はそのまま先頭に入る');
  const pos = ['【事前メモ】\nなし', '【前回までの整理】\nなし', '【字幕の範囲】\n全部', '【字幕】\n[09:05] 山田：こんにちは'].map((s) => p.indexOf('\n' + s));
  assert.ok(pos.every((n) => n > 0), '4 つの節がある: ' + pos);
  assert.deepEqual(pos.slice().sort((a, b) => a - b), pos, '順番どおり');

  const q = buildPrompt({ promptMd, notes: '## 聞くこと\n- 月額', prevBoard: { topics: [] }, range: '前回より後だけ', lines });
  assert.ok(q.includes('【事前メモ】\n## 聞くこと\n- 月額'));
  assert.ok(q.includes('【前回までの整理】\n{"topics":[]}'));
  assert.ok(q.includes('【字幕の範囲】\n前回より後だけ'));
});

test('shouldUpdate: 120 字以上かつ前回の終わりから 20 秒、または 1 字以上かつ interval 秒', () => {
  const base = { inFlight: false, now: 100000, lastEndAt: 0, blockedUntil: 0, newChars: 0, intervalMs: 60000, notesDirty: false, hasTranscript: true };
  const go = (o) => shouldUpdate(Object.assign({}, base, o));
  assert.equal(go({ newChars: 0 }), null, '新しい字幕が無ければ動かない');
  assert.equal(go({ newChars: 120, lastEndAt: 100000 - 20000 }), 'chars');
  assert.equal(go({ newChars: 119, lastEndAt: 100000 - 20000 }), null, '119 字ではまだ');
  assert.equal(go({ newChars: 500, lastEndAt: 100000 - 19999 }), null, '20 秒に 1ms 足りない');
  assert.equal(go({ newChars: 1, lastEndAt: 100000 - 60000 }), 'interval');
  assert.equal(go({ newChars: 1, lastEndAt: 100000 - 59999 }), null);
  assert.equal(go({ newChars: 500, lastEndAt: 0, inFlight: true }), null, '同時に 2 つは走らせない');
  assert.equal(go({ newChars: 500, lastEndAt: 0, blockedUntil: 100001 }), null, '失敗後の待ち');
  assert.equal(go({ newChars: 0, notesDirty: true, lastEndAt: 100000 - 20000 }), 'notes');
  assert.equal(go({ newChars: 0, notesDirty: true, hasTranscript: false, lastEndAt: 0 }), null);
});

test('parseReplayText: 「話者：本文」「話者: 本文」と先頭の [HH:MM] を読み、それ以外の行は読み飛ばす', () => {
  const text = [
    '# コメント',
    '',
    '山田：こんにちは',
    '佐々木: 見積もりは10:30までです',
    '[09:01] 山田：時刻つきの行',
    '10:30 開始',
    '説明だけの行',
    'あなた：自分の発言',
  ].join('\r\n');
  assert.deepEqual(parseReplayText(text), [
    { speaker: '山田', text: 'こんにちは' },
    { speaker: '佐々木', text: '見積もりは10:30までです' },
    { speaker: '山田', text: '時刻つきの行' },
    { speaker: '__SELF__', text: '自分の発言' },
  ]);
  const entries = toEntries(parseReplayText(text), T0);
  assert.equal(entries[1].firstSeen - entries[0].firstSeen, 4000, '1 行あたり約 4 秒（1 倍速）');
});

test('parseArgs: 既定値・値つきオプション・誤り', () => {
  const d = parseArgs([]);
  assert.deepEqual(d.errors, []);
  assert.equal(d.opts.port, 47431);
  assert.equal(d.opts.interval, 60);
  assert.equal(d.opts.model, 'sonnet');
  const r = parseArgs(['--port', '0', '--interval=30', '--model', 'opus', '--open', '--replay', 'a.txt', '--once', '--speed', '20', '--data-dir', '/tmp/x', '--notes', 'n.md']);
  assert.deepEqual(r.errors, []);
  assert.equal(r.opts.port, 0);
  assert.equal(r.opts.interval, 30);
  assert.equal(r.opts.model, 'opus');
  assert.equal(r.opts.open, true);
  assert.equal(r.opts.once, true);
  assert.equal(r.opts.speed, 20);
  assert.equal(r.opts.dataDir, '/tmp/x');
  assert.equal(r.opts.notes, 'n.md');
  assert.ok(parseArgs(['--nope']).errors.length > 0);
  assert.ok(parseArgs(['--port']).errors.length > 0);
  assert.ok(parseArgs(['--port', 'abc']).errors.length > 0);
  assert.ok(parseArgs(['--once']).errors.length > 0, '--once は --replay が要る');
});
