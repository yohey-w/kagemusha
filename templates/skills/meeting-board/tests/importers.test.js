'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const S = require('./fixtures/support.js');
const { importTranscript } = require(path.join(S.HELPER_DIR, 'lib', 'importers.js'));
const FX = path.join(__dirname, 'fixtures');
const read = (f) => fs.readFileSync(path.join(FX, f), 'utf8');

test('WebVTT（Teams の形と推定・<v 名前>）: 話者・本文・秒。同じ話者の続いた合図（間 2 秒未満）はつなぐ', () => {
  const r = importTranscript(read('sample_teams.vtt'), 'meeting.vtt');
  assert.equal(r.format, 'vtt');
  assert.deepEqual(r.lines, [
    { speaker: '山田 太郎', text: 'もしもし、佐々木さん、聞こえますか。', atSec: 1 },
    { speaker: '佐々木 花子', text: 'はい、聞こえています。画面も見えています。', atSec: 4 },
    { speaker: '山田 太郎', text: 'それでは、勤怠システムの入れ替えの件、始めましょうか。', atSec: 12 },
    { speaker: '佐々木 花子', text: 'A社は1人あたり月額400円で、初期費用はありません。', atSec: 62 },
  ]);
  assert.match(r.note, /合図 5 個 → 発言 4 件/);
});

test('WebVTT（Zoom の形と推定・本文の頭に「名前: 」）。拡張子が無くても WEBVTT で見分ける', () => {
  const r = importTranscript(read('sample_zoom.vtt'), 'x.txt');
  assert.equal(r.format, 'vtt');
  assert.deepEqual(r.lines.map((l) => [l.speaker, l.atSec]), [['山田 太郎', 1], ['佐々木 花子', 4], ['山田 太郎', 12]]);
});

test('「名前 時刻」＋本文の .txt（Teams の .docx を保存した形と推定）', () => {
  const r = importTranscript(read('sample_teams.txt'), 'meeting.txt');
  assert.equal(r.format, 'teams-txt');
  assert.deepEqual(r.lines, [
    { speaker: '山田 太郎', text: 'もしもし、佐々木さん、聞こえますか。', atSec: 1 },
    { speaker: '佐々木 花子', text: 'はい、聞こえています。画面も見えています。', atSec: 4 },
    { speaker: '山田 太郎', text: 'それでは、勤怠システムの入れ替えの件、始めましょうか。', atSec: 12 },
    { speaker: '佐々木 花子', text: 'A社は1人あたり月額400円で、初期費用はありません。', atSec: 3725 },
  ]);
});

test('今までの「話者：本文」はそのまま。見分けられない形は unknown（でたらめな行を作らない）', () => {
  const plain = importTranscript(fs.readFileSync(path.join(S.SAMPLE_DIR, 'sample_transcript.txt'), 'utf8'), 'a.txt');
  assert.equal(plain.format, 'lines');
  assert.equal(plain.lines.length, 58);
  const bad = importTranscript('これは議事録のメモです。\n誰が何を言ったかは書いていません。\n以上。', 'memo.txt');
  assert.equal(bad.format, 'unknown');
  assert.deepEqual(bad.lines, []);
  assert.match(bad.note, /形を見分けられませんでした/);
  const brokenVtt = importTranscript('WEBVTT\n\nNOTE だけ\n', 'x.vtt');
  assert.equal(brokenVtt.format, 'unknown');
});

test('--replay: .vtt を読み、形と件数を案内する。読めない形は終了コード 2 で理由を言う', () => {
  const dir = S.tmpDir();
  try {
    const server = path.join(S.HELPER_DIR, 'server.js');
    const log = path.join(dir, 'calls.jsonl');
    const ok = spawnSync(process.execPath, [server, '--replay', path.join(FX, 'sample_teams.vtt'), '--once', '--data-dir', dir, '--port', '0'], { env: S.stubEnv({ STUB_LOG: log }), encoding: 'utf8', timeout: 30000 });
    assert.equal(ok.status, 0, ok.stderr);
    assert.match(ok.stderr, /WebVTT として読みました/);
    const input = JSON.parse(fs.readFileSync(log, 'utf8').trim()).stdin;
    assert.match(input, /佐々木 花子：はい、聞こえています。画面も見えています。/);
    const memo = path.join(dir, 'memo.txt');
    fs.writeFileSync(memo, 'これは議事録のメモです。\n誰が何を言ったかは書いていません。\n');
    const ng = spawnSync(process.execPath, [server, '--replay', memo, '--once', '--data-dir', dir, '--port', '0'], { env: S.stubEnv(), encoding: 'utf8', timeout: 30000 });
    assert.equal(ng.status, 2);
    assert.match(ng.stderr, /形を見分けられませんでした/);
    assert.equal(ng.stdout, '');
  } finally {
    S.rmDir(dir);
  }
});
