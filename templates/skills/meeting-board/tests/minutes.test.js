'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const S = require('./fixtures/support.js');
const { boardToMarkdown, transcriptInfo } = require(path.join(S.HELPER_DIR, 'lib', 'minutes.js'));
const { normalizeBoardV2 } = require(path.join(S.HELPER_DIR, 'lib', 'board.js'));
const { parseNotes } = require(path.join(S.HELPER_DIR, 'lib', 'notes.js'));

const SERVER = path.join(S.HELPER_DIR, 'server.js');
const T0 = new Date(2026, 9, 21, 10, 0, 0).getTime();

function sampleBoard() {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'board_v2_sample.json'), 'utf8'));
  const spec = parseNotes(fs.readFileSync(path.join(S.SAMPLE_DIR, 'sample_notes.md'), 'utf8'));
  return normalizeBoardV2(raw, { hasNotes: true, spec, prev: null, now: T0 }).board;
}

test('議事録の素: 決まったこと／宿題／まだ答えをもらっていないこと／前提と食い違ったこと／聞くことの結果／話題ごと、の順', () => {
  const md = boardToMarkdown(sampleBoard(), { startedAt: T0, endedAt: T0 + 54 * 60000, speakers: ['山田', '佐々木'] });
  assert.ok(md.startsWith('# 会議の記録（自動整理の下書き）\n'));
  assert.match(md, /- 日時: 2026-10-21 10:00〜10:54（字幕の最初と最後）/);
  assert.match(md, /- 字幕に出た名前: 山田、佐々木/);
  assert.match(md, /外に出す前に必ず見直してください/);
  const heads = md.split('\n').filter((l) => l.startsWith('## '));
  assert.deepEqual(heads, ['## 決まったこと', '## 宿題（誰・いつまで）', '## まだ答えをもらっていないこと', '## 前提と食い違ったこと', '## 聞くこと・伝えることの結果', '## 話題ごとの記録']);
  assert.match(md, /\| 佐々木 \| 現行ベンダーに2か月だけの延長ができるか確認する \| 来週金曜 \|/);
  assert.match(md, /- こちらの理解「解約の連絡は1か月前で足りる。」→ 佐々木「解約の連絡は終了の2か月前まで（1月末）」/);
  assert.match(md, /- \[x\] 1\. 伝える：予算の上限は年額150万円であること。 — 伝え済み: /);
  assert.match(md, /- \[ \] 4\. 聞く：スマホで打刻する場合.* — まだ/);
  assert.match(md, /### 1\. 現状と入れ替えの目的 — 締め作業を1日以内に/);
  assert.match(md, /- 数字: 利用者 約150人／締め作業 毎月約3日/);
});

test('議事録の素: 0.1 の形のボードからも書ける。空の節は出さない。表の | は崩さない', () => {
  const v1 = {
    topics: [{ title: '費用', current: true, points: [{ speaker: '佐々木', text: 'A|B 案' }], decisions: [], todos: [{ who: '山田', what: '見積|再確認', when: '' }], numbers: [] }],
    open_questions: [],
    checklist: [{ item: '月額', done: true, evidence: '400円' }, { item: '納期', done: false, evidence: '' }],
    cards: [],
  };
  const md = boardToMarkdown(v1, {});
  const heads = md.split('\n').filter((l) => l.startsWith('## '));
  assert.deepEqual(heads, ['## 宿題（誰・いつまで）', '## 聞くこと・伝えることの結果', '## 話題ごとの記録']);
  assert.match(md, /\| 山田 \| 見積\\\|再確認 \| — \|/);
  assert.match(md, /- \[x\] 1\. 聞く：月額 — 済: 400円/);
  assert.match(md, /- \[ \] 2\. 聞く：納期 — まだ/);
  assert.ok(!md.includes('日時:'), '日時が分からなければ書かない');
});

test('transcriptInfo: 日時（最初と最後）と名前だけを取る。__SELF__ は表示名', () => {
  const jsonl = [
    { id: 'a', speaker: '佐々木', text: '本文', firstSeen: T0 + 5000, lastUpdate: T0 + 6000 },
    { id: 'b', speaker: '__SELF__', text: '本文', firstSeen: T0, lastUpdate: T0 + 1000 },
    { id: 'c', speaker: '佐々木', text: '本文', firstSeen: T0 + 9000, lastUpdate: T0 + 60000 },
  ].map((e) => JSON.stringify(e)).join('\n') + '\n壊れた行';
  assert.deepEqual(transcriptInfo(jsonl, '山田'), { startedAt: T0, endedAt: T0 + 60000, speakers: ['佐々木', '山田'] });
});

test('--minutes: 会議フォルダから標準出力へ（Markdown だけ）。--out でファイルへ。ボードが無ければ終了コード 2', () => {
  const dir = S.tmpDir();
  try {
    const session = path.join(dir, '2026-10-21_100000');
    fs.mkdirSync(session);
    fs.writeFileSync(path.join(session, 'board.json'), JSON.stringify(sampleBoard()));
    fs.writeFileSync(path.join(session, 'transcript.jsonl'), JSON.stringify({ id: 'a', speaker: '佐々木', text: 'x', firstSeen: T0, lastUpdate: T0 + 60000 }) + '\n');
    const env = S.stubEnv();
    const r = spawnSync(process.execPath, [SERVER, '--minutes', session], { env, encoding: 'utf8', timeout: 20000 });
    assert.equal(r.status, 0, r.stderr);
    assert.ok(r.stdout.startsWith('# 会議の記録（自動整理の下書き）'));
    assert.match(r.stdout, /字幕に出た名前: 佐々木/);

    const out = path.join(dir, 'minutes.md');
    const w = spawnSync(process.execPath, [SERVER, '--minutes', path.join(session, 'board.json'), '--out', out], { env, encoding: 'utf8', timeout: 20000 });
    assert.equal(w.status, 0, w.stderr);
    assert.equal(w.stdout, '');
    assert.match(fs.readFileSync(out, 'utf8'), /## 決まったこと/);

    const missing = spawnSync(process.execPath, [SERVER, '--minutes', path.join(dir, 'nothing')], { env, encoding: 'utf8', timeout: 20000 });
    assert.equal(missing.status, 2);
    fs.mkdirSync(path.join(dir, 'empty'));
    const empty = spawnSync(process.execPath, [SERVER, '--minutes', path.join(dir, 'empty')], { env, encoding: 'utf8', timeout: 20000 });
    assert.equal(empty.status, 2);
    assert.match(empty.stderr, /board\.json/);
    const both = spawnSync(process.execPath, [SERVER, '--minutes', session, '--once'], { env, encoding: 'utf8', timeout: 20000 });
    assert.equal(both.status, 2);
  } finally {
    S.rmDir(dir);
  }
});
