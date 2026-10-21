'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const C = require(path.join(__dirname, '..', 'extension', 'captions-core.js'));

// ── 結合規則 ────────────────────────────────────────────────
test('mergeText: 新しい文面が古い文面の続き → 新しい方', () => {
  assert.equal(C.mergeText('今日は', '今日は晴れです'), '今日は晴れです');
  assert.equal(C.mergeText('', 'はじめまして'), 'はじめまして');
});

test('mergeText: 古い文面が新しい文面を含む（頭が切り詰められた・一瞬戻った）→ 古い方', () => {
  assert.equal(C.mergeText('先週の件ですが、見積もりは来週出します', '見積もりは来週出します'), '先週の件ですが、見積もりは来週出します');
  assert.equal(C.mergeText('abc def ghi', 'def ghi'), 'abc def ghi');
  assert.equal(C.mergeText('そのまま', ''), 'そのまま');
});

test('mergeText: 末尾と先頭の重なりを 1 回だけ残してつなぐ（切り詰め + 続き）', () => {
  const merged = C.mergeText('今日は天気が良いので散歩', '良いので散歩に行きます');
  assert.equal(merged, '今日は天気が良いので散歩に行きます');
  // いちばん長い重なりを使う
  assert.equal(C.mergeText('aaa bbb ccc ddd', 'ccc ddd eee'), 'aaa bbb ccc ddd eee');
});

test('mergeText: 重なりが無ければ半角空白でつなぐ', () => {
  assert.equal(C.mergeText('こんにちは', '山田です'), 'こんにちは 山田です');
});

test('mergeText: 偶然の 1〜2 文字の一致は重なりとみなさない', () => {
  assert.equal(C.mergeText('よろしくお願いしますね', 'ねえ、次の件です'), 'よろしくお願いしますね ねえ、次の件です');
});

test('mergeText: 言い直し（頭と尻が大きく共通）は新しい方を採る', () => {
  assert.equal(C.mergeText('きょうは晴れですね', '今日は晴れですね'), '今日は晴れですね');
  assert.equal(C.mergeText('部長からの連絡です', '課長からの連絡です'), '課長からの連絡です');
});

test('mergeText: 新しい文面が古い文面を途中に含む（言い足し）→ 新しい方', () => {
  assert.equal(C.mergeText('こんにちは', 'えーと、こんにちは、山田です'), 'えーと、こんにちは、山田です');
});

// ── 話者と行の読み取り ──────────────────────────────────────
test('mapSpeaker: 自分のラベルは __SELF__、ほかは整えるだけ', () => {
  assert.equal(C.mapSpeaker('あなた'), '__SELF__');
  assert.equal(C.mapSpeaker(' You '), '__SELF__');
  assert.equal(C.mapSpeaker('you'), '__SELF__');
  assert.equal(C.mapSpeaker('  山田   太郎 '), '山田 太郎');
  assert.equal(C.mapSpeaker('佐々木:'), '佐々木');
  assert.equal(C.mapSpeaker(''), '');
  // 名前の一部に You が入っているだけの人は自分扱いしない
  assert.equal(C.mapSpeaker('Youko'), 'Youko');
});

test('parseBlockLines: 1 行目が話者、残りが発言（日本語どうしは空白なしでつなぐ）', () => {
  assert.deepEqual(C.parseBlockLines(['山田', '今日は', '晴れです']), { speaker: '山田', text: '今日は晴れです' });
  assert.deepEqual(C.parseBlockLines(['Alice', 'hello', 'world']), { speaker: 'Alice', text: 'hello world' });
  assert.deepEqual(C.parseBlockLines(['あなた', 'テストです']), { speaker: '__SELF__', text: 'テストです' });
  assert.deepEqual(C.parseBlockLines(['山田']), { speaker: '山田', text: '' });
  assert.equal(C.parseBlockLines(['', '  ']), null);
});

// ── ブロックの追跡 ──────────────────────────────────────────
test('tracker: 同じブロックの書き換えは 1 本の発言になり、増えた分だけ送る', () => {
  const k = {};
  const t = C.createTracker({ idPrefix: 't' });
  t.scan([{ key: k, speaker: '山田', text: 'こんにちは' }], 1000);
  let out = t.drain();
  assert.equal(out.length, 1);
  assert.equal(out[0].id, 't-1');
  assert.equal(out[0].speaker, '山田');
  assert.equal(out[0].firstSeen, 1000);
  assert.equal(out[0].final, false);

  t.scan([{ key: k, speaker: '山田', text: 'こんにちは、山田です' }], 1500);
  out = t.drain();
  assert.equal(out.length, 1);
  assert.equal(out[0].id, 't-1');
  assert.equal(out[0].text, 'こんにちは、山田です');
  assert.equal(out[0].firstSeen, 1000);
  assert.equal(out[0].lastUpdate, 1500);

  // 変化なし → 何も送らない
  t.scan([{ key: k, speaker: '山田', text: 'こんにちは、山田です' }], 2000);
  assert.deepEqual(t.drain(), []);
});

test('tracker: 頭が切り詰められても、積み上げた文面は縮まない', () => {
  const k = {};
  const t = C.createTracker({ idPrefix: 't' });
  t.scan([{ key: k, speaker: '山田', text: '先週の件ですが、見積もりは来週出します' }], 1000);
  t.scan([{ key: k, speaker: '山田', text: '見積もりは来週出します。その前に仕様を確認します' }], 1500);
  const out = t.drain();
  assert.equal(out.length, 1);
  assert.equal(out[0].text, '先週の件ですが、見積もりは来週出します。その前に仕様を確認します');
});

test('tracker: 画面から消えたブロックは確定（final）として 1 度だけ送る', () => {
  const k = {};
  const t = C.createTracker({ idPrefix: 't' });
  t.scan([{ key: k, speaker: '山田', text: 'おわります' }], 1000);
  t.drain();
  t.scan([], 9000);
  const out = t.drain();
  assert.equal(out.length, 1);
  assert.equal(out[0].final, true);
  assert.equal(out[0].text, 'おわります');
  t.scan([], 9500);
  assert.deepEqual(t.drain(), []);
  assert.equal(t.liveCount(), 0);
});

test('tracker: 話者が変われば別の発言（別 id）', () => {
  const a = {};
  const b = {};
  const t = C.createTracker({ idPrefix: 't' });
  t.scan([{ key: a, speaker: '山田', text: '以上です' }], 1000);
  t.scan(
    [
      { key: a, speaker: '山田', text: '以上です' },
      { key: b, speaker: '佐々木', text: '了解です' },
    ],
    2000
  );
  const out = t.drain();
  assert.equal(out.length, 2);
  assert.notEqual(out[0].id, out[1].id);
  assert.deepEqual(out.map((e) => e.speaker).sort(), ['佐々木', '山田']);
});

test('tracker: 要素が作り直されても、中身が地続きなら同じ発言として引き継ぐ', () => {
  const a = {};
  const b = {};
  const t = C.createTracker({ idPrefix: 't' });
  t.scan([{ key: a, speaker: '山田', text: '資料は共有フォルダにあります' }], 1000);
  t.drain();
  // a が消えて b が現れた（描き直し）。b は a の続き
  t.scan([{ key: b, speaker: '山田', text: '資料は共有フォルダにあります。確認してください' }], 1500);
  const out = t.drain();
  assert.equal(out.length, 1, '新しい発言を増やさない');
  assert.equal(out[0].id, 't-1');
  assert.equal(out[0].text, '資料は共有フォルダにあります。確認してください');
  assert.equal(out[0].final, false);
  assert.equal(t.trackedCount(), 1);
});

test('tracker: 一瞬だけ中身が空になる描き直しでは確定させない', () => {
  const k = {};
  const t = C.createTracker({ idPrefix: 't' });
  t.scan([{ key: k, speaker: '山田', text: 'ちょっと待ってください' }], 1000);
  t.drain();
  t.scan([{ key: k, speaker: '山田', text: '' }], 1200);
  assert.deepEqual(t.drain(), []);
  t.scan([{ key: k, speaker: '山田', text: 'ちょっと待ってください、確認します' }], 1400);
  const out = t.drain();
  assert.equal(out.length, 1);
  assert.equal(out[0].id, 't-1');
  assert.equal(out[0].final, false);
});

test('tracker: 話者名があとから分かったら更新する', () => {
  const k = {};
  const t = C.createTracker({ idPrefix: 't' });
  t.scan([{ key: k, speaker: '', text: '聞こえますか' }], 1000);
  t.drain();
  t.scan([{ key: k, speaker: '佐々木', text: '聞こえますか' }], 1200);
  const out = t.drain();
  assert.equal(out.length, 1);
  assert.equal(out[0].speaker, '佐々木');
});

test('tracker: 送れなかった分を戻しても、新しい版や確定を古い版で上書きしない', () => {
  const k = {};
  const t = C.createTracker({ idPrefix: 't' });
  t.scan([{ key: k, speaker: '山田', text: 'ひとこと' }], 1000);
  const first = t.drain();
  t.scan([], 2000); // 確定
  t.requeue(first); // 古い版を戻す
  const out = t.drain();
  assert.equal(out.length, 1);
  assert.equal(out[0].final, true);
});
