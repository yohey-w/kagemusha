'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const S = require('./fixtures/support.js');

const SERVER = path.join(S.HELPER_DIR, 'server.js');
const SAMPLE_TX = path.join(S.SAMPLE_DIR, 'sample_transcript.txt');
const SAMPLE_NOTES = path.join(S.SAMPLE_DIR, 'sample_notes.md');

function runCli(args, env) {
  return spawnSync(process.execPath, [SERVER].concat(args), { env: S.stubEnv(env), encoding: 'utf8', timeout: 60000 });
}

test('--once: 全部読み込んで整理を 1 回だけ行い、標準出力には JSON だけを出す', () => {
  const dir = S.tmpDir();
  const log = path.join(dir, 'calls.jsonl');
  try {
    const r = runCli(['--replay', SAMPLE_TX, '--notes', SAMPLE_NOTES, '--once', '--data-dir', dir, '--port', '0'], { STUB_LOG: log });
    assert.equal(r.status, 0, r.stderr);
    const board = JSON.parse(r.stdout); // 余計な文字が混ざっていれば、ここで落ちる
    assert.ok(Array.isArray(board.topics) && board.topics.length >= 1);
    assert.ok(Array.isArray(board.checklist) && board.checklist.length >= 1, '事前メモがあるので聞くことの表がある');
    assert.ok(Array.isArray(board.cards) && board.cards.length >= 1);
    assert.match(r.stderr, /OK .*Node\.js/);
    assert.match(r.stderr, /58 行を読み込みました/);

    const calls = fs.readFileSync(log, 'utf8').trim().split('\n').map((l) => JSON.parse(l));
    assert.equal(calls.length, 1, '整理はちょうど 1 回');
    const input = calls[0].stdin;
    assert.ok(input.includes('【事前メモ】\n# 勤怠システム入れ替え 打ち合わせメモ'), '事前メモが入っている');
    assert.ok(input.includes('【字幕の範囲】\n全部'));
    assert.match(input, /\[\d\d:\d\d\] 山田：もしもし、佐々木さん、聞こえますか。/);
    assert.match(input, /\[\d\d:\d\d\] 佐々木：お疲れさまでした。/);
    const captionLines = input.split('【字幕】\n')[1].trim().split('\n');
    assert.equal(captionLines.length, 58);
    // 保存: 会議フォルダに board.json / transcript.jsonl / notes.md
    const sessions = fs.readdirSync(dir).filter((d) => /^\d{4}-/.test(d));
    assert.equal(sessions.length, 1);
    for (const f of ['board.json', 'transcript.jsonl', 'notes.md']) {
      assert.ok(fs.existsSync(path.join(dir, sessions[0], f)), f);
    }
    assert.equal(fs.readFileSync(path.join(dir, sessions[0], 'transcript.jsonl'), 'utf8').trim().split('\n').length, 58);
  } finally {
    S.rmDir(dir);
  }
});

test('--once: 整理に失敗したら標準出力は空、終了コード 1、理由は標準エラーに日本語で', () => {
  const dir = S.tmpDir();
  try {
    const r = runCli(['--replay', SAMPLE_TX, '--once', '--data-dir', dir, '--port', '0'], { STUB_MODE: 'garbage' });
    assert.equal(r.status, 1);
    assert.equal(r.stdout, '');
    assert.match(r.stderr, /整理に失敗しました/);
  } finally {
    S.rmDir(dir);
  }
});

test('--once は --replay が無ければ使えない。--help は使い方を出す。知らないオプションは断る', () => {
  const a = runCli(['--once']);
  assert.equal(a.status, 2);
  assert.match(a.stderr, /--replay/);
  const h = runCli(['--help']);
  assert.equal(h.status, 0);
  assert.match(h.stdout, /使い方/);
  const u = runCli(['--no-such-option']);
  assert.equal(u.status, 2);
  assert.match(u.stderr, /知らないオプション/);
});

/** 通常起動のヘルパーを子プロセスで立てる。バナーからボードの URL（ポート）を読む */
function startServer(args, env) {
  const child = spawn(process.execPath, [SERVER].concat(args), { env: S.stubEnv(env), stdio: ['ignore', 'pipe', 'pipe'] });
  let out = '';
  let err = '';
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  child.stdout.on('data', (d) => {
    out += d;
  });
  child.stderr.on('data', (d) => {
    err += d;
  });
  const exited = new Promise((resolve) => child.on('close', (code) => resolve(code)));
  return {
    child,
    out: () => out,
    err: () => err,
    exited,
    port: async () => {
      const m = await S.waitFor(() => /ボード: http:\/\/127\.0\.0\.1:(\d+)\//.exec(out), 15000);
      return Number(m[1]);
    },
    stop: async () => {
      child.kill('SIGTERM');
      return Promise.race([exited, S.sleep(8000).then(() => 'timeout')]);
    },
  };
}

test('--replay（通常起動）: 会話を流し、最後に 1 回整理して、ボードに出る', async () => {
  const dir = S.tmpDir();
  const log = path.join(dir, 'calls.jsonl');
  const srv = startServer(['--replay', SAMPLE_TX, '--notes', SAMPLE_NOTES, '--speed', '500', '--interval', '5', '--port', '0', '--data-dir', dir], { STUB_LOG: log });
  try {
    const port = await srv.port();
    assert.match(srv.out(), /会議ボード ヘルパー/);
    assert.match(srv.out(), /起動時の点検/);
    assert.match(srv.out(), /OK +Node\.js/);

    // 流し終えるまでは「受信中」
    const state = await S.waitFor(async () => {
      const r = await S.request(port, 'GET', '/state', { headers: S.API });
      return r.json && r.json.status.update.count >= 1 && r.json ? r.json : null;
    }, 30000, 200);
    assert.equal(state.status.captions.entries, 58);
    assert.equal(state.board.topics[0].title, '勤怠システムの入れ替え');
    assert.equal(state.notesPresent, true);
    assert.equal(state.recent.length, 30, '字幕（最新）は直近 30 行');
    assert.equal(state.status.replay.active, false);

    const calls = fs.readFileSync(log, 'utf8').trim().split('\n');
    assert.ok(calls.length >= 1 && calls.length <= 2, '整理の回数: ' + calls.length);

    // ボードの画面も配られる
    const page = await S.request(port, 'GET', '/');
    assert.equal(page.status, 200);
    assert.match(page.text, /ここまでの話/);
  } finally {
    const code = await srv.stop();
    assert.equal(code, 0, 'Ctrl+C（SIGTERM）できれいに終わる: ' + srv.err());
    S.rmDir(dir);
  }
});

test('二重起動: すでに動いていれば、その旨を言って正常終了する（--open は付けない）', async () => {
  const dir = S.tmpDir();
  const first = startServer(['--port', '0', '--data-dir', dir], {});
  try {
    const port = await first.port();
    const second = spawnSync(process.execPath, [SERVER, '--port', String(port), '--data-dir', dir], { env: S.stubEnv(), encoding: 'utf8', timeout: 20000 });
    assert.equal(second.status, 0, second.stderr);
    assert.match(second.stdout, /すでに起動しています/);
  } finally {
    await first.stop();
    S.rmDir(dir);
  }
});

test('ポートを別のプログラムが使っていれば、日本語で理由を言って終わる', async () => {
  const dir = S.tmpDir();
  const blocker = net.createServer((sock) => sock.end());
  await new Promise((r) => blocker.listen(0, '127.0.0.1', r));
  try {
    const port = blocker.address().port;
    const r = spawnSync(process.execPath, [SERVER, '--port', String(port), '--data-dir', dir], { env: S.stubEnv(), encoding: 'utf8', timeout: 20000 });
    assert.equal(r.status, 1);
    assert.match(r.stderr, /別のプログラムが使っています/);
  } finally {
    await new Promise((res) => blocker.close(res));
    S.rmDir(dir);
  }
});

test('claude が見つからなくても起動でき、画面の帯に理由が出る', async () => {
  const dir = S.tmpDir();
  const srv = startServer(['--port', '0', '--data-dir', dir], { CLAUDE_BIN: path.join(dir, 'no-such-claude') });
  try {
    const port = await srv.port();
    assert.match(srv.out(), /NG +claude/);
    const st = (await S.request(port, 'GET', '/state', { headers: S.API })).json;
    assert.equal(st.status.claude.found, false);
    assert.match(st.status.claude.message, /CLAUDE_BIN/);
  } finally {
    await srv.stop();
    S.rmDir(dir);
  }
});
