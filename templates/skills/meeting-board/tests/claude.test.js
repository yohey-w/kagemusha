'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const S = require('./fixtures/support.js');
const { resolveClaude, callClaude, interpret, isUsageLimit, FLAGS_FULL, UNKNOWN_FLAG_RE } = require(path.join(S.HELPER_DIR, 'lib', 'claude.js'));

// ── claude の見つけ方 ───────────────────────────────────────
test('resolveClaude: CLAUDE_BIN の .js は node で起動する（cli.js と同じ経路）', () => {
  const r = resolveClaude({ env: { CLAUDE_BIN: S.STUB } });
  assert.equal(r.ok, true);
  assert.equal(r.kind, 'node-script');
  assert.equal(r.command, process.execPath);
  assert.deepEqual(r.prefix, [S.STUB]);
});

test('resolveClaude: CLAUDE_BIN の場所に無ければ、PATH へは落とさず日本語で断る', () => {
  const r = resolveClaude({ env: { CLAUDE_BIN: path.join(os.tmpdir(), 'mb-test-none', 'no-such-claude'), PATH: '' } });
  assert.equal(r.ok, false);
  assert.match(r.message, /CLAUDE_BIN/);
});

function fakeFs(files) {
  const set = new Set(files.map((f) => f.toLowerCase()));
  return (p) => set.has(p.toLowerCase());
}

test('resolveClaude (Windows): PATH の claude.exe を直接起動する。claude.cmd より優先', () => {
  const r = resolveClaude({
    platform: 'win32',
    env: { PATH: 'C:\\Tools;C:\\Profiles\\u\\AppData\\Roaming\\npm', USERPROFILE: 'C:\\Profiles\\u' },
    home: 'C:\\Profiles\\u',
    execPath: 'C:\\nodejs\\node.exe',
    exists: fakeFs(['C:\\Tools\\claude.exe', 'C:\\Profiles\\u\\AppData\\Roaming\\npm\\claude.cmd']),
  });
  assert.equal(r.ok, true);
  assert.equal(r.kind, 'direct');
  assert.equal(r.command, 'C:\\Tools\\claude.exe');
});

test('resolveClaude (Windows): PATH に無ければ %USERPROFILE%\\.local\\bin の claude.exe', () => {
  const r = resolveClaude({
    platform: 'win32',
    env: { PATH: 'C:\\Windows', USERPROFILE: 'C:\\Profiles\\u' },
    home: 'C:\\Profiles\\u',
    exists: fakeFs(['C:\\Profiles\\u\\.local\\bin\\claude.exe']),
  });
  assert.equal(r.ok, true);
  assert.equal(r.command, 'C:\\Profiles\\u\\.local\\bin\\claude.exe');
  assert.match(r.display, /^~/, '診断にはユーザー名を出さない（~ に置き換える）');
});

test('resolveClaude (Windows): claude.cmd だけなら、隣の cli.js を node で直接起動する（シェルを通さない）', () => {
  const cli = 'C:\\Profiles\\u\\AppData\\Roaming\\npm\\node_modules\\@anthropic-ai\\claude-code\\cli.js';
  const r = resolveClaude({
    platform: 'win32',
    env: { PATH: 'C:\\Profiles\\u\\AppData\\Roaming\\npm', USERPROFILE: 'C:\\Profiles\\u' },
    home: 'C:\\Profiles\\u',
    execPath: 'C:\\nodejs\\node.exe',
    exists: fakeFs(['C:\\Profiles\\u\\AppData\\Roaming\\npm\\claude.cmd', cli]),
  });
  assert.equal(r.ok, true);
  assert.equal(r.kind, 'node-script');
  assert.equal(r.command, 'C:\\nodejs\\node.exe');
  assert.deepEqual(r.prefix, [cli]);
});

test('resolveClaude (Windows): claude.cmd はあるが cli.js が無ければ、理由を日本語で言う', () => {
  const r = resolveClaude({
    platform: 'win32',
    env: { PATH: 'C:\\npm' },
    home: 'C:\\Profiles\\u',
    exists: fakeFs(['C:\\npm\\claude.cmd']),
  });
  assert.equal(r.ok, false);
  assert.match(r.message, /cli\.js/);
});

test('resolveClaude (Windows): どこにも無ければ「claude が見つかりません」', () => {
  const r = resolveClaude({ platform: 'win32', env: { PATH: 'C:\\Windows' }, home: 'C:\\Profiles\\u', exists: () => false });
  assert.equal(r.ok, false);
  assert.match(r.message, /claude/);
  assert.match(r.message, /見つかりません/);
});

test('resolveClaude (mac/linux): PATH の claude', () => {
  const r = resolveClaude({ platform: 'linux', env: { PATH: '/usr/bin:/opt/x/bin' }, home: '/work/u', exists: (p) => p === '/opt/x/bin/claude' });
  assert.equal(r.ok, true);
  assert.equal(r.command, '/opt/x/bin/claude');
  assert.equal(resolveClaude({ platform: 'linux', env: { PATH: '/usr/bin' }, home: '/work/u', exists: () => false }).ok, false);
});

// ── 返事の読み取り ──────────────────────────────────────────
test('UNKNOWN_FLAG_RE: 古い版が返す文言を拾う', () => {
  for (const s of ["error: unknown option '--safe-mode'", 'Unknown argument: tools', "error: option '--tools <tools...>' argument missing", 'UNKNOWN OPTION']) {
    assert.ok(UNKNOWN_FLAG_RE.test(s), s);
  }
  assert.ok(!UNKNOWN_FLAG_RE.test('Invalid API key'));
});

test('isUsageLimit: 上限の文言を拾い、ふつうのエラーは拾わない', () => {
  for (const s of ['Claude AI usage limit reached|1730000000', "You've hit your session limit · resets 3pm", '5-hour limit reached ∙ resets 3pm', 'Weekly limit reached', '利用上限に達しました']) {
    assert.ok(isUsageLimit(s), s);
  }
  assert.ok(!isUsageLimit('Invalid API key · Please run /login'));
});

test('interpret: 成功・エラー JSON・本文だけの返事', () => {
  const ok = interpret({ code: 0, stdout: JSON.stringify({ type: 'result', subtype: 'success', is_error: false, result: '{"topics":[]}' }), stderr: '' }, 1000);
  assert.deepEqual([ok.ok, ok.text], [true, '{"topics":[]}']);
  const err = interpret({ code: 1, stdout: JSON.stringify({ type: 'result', subtype: 'error_during_execution', is_error: true, result: 'boom' }), stderr: '' }, 1000);
  assert.equal(err.ok, false);
  assert.equal(err.kind, 'claude-error');
  const plain = interpret({ code: 0, stdout: 'ただの本文', stderr: '' }, 1000);
  assert.deepEqual([plain.ok, plain.text], [true, 'ただの本文']);
  assert.equal(interpret({ code: 0, stdout: '', stderr: '' }, 1000).kind, 'bad-output');
  assert.equal(interpret({ code: null, stdout: '', stderr: '', timedOut: true }, 120000).kind, 'timeout');
  assert.equal(interpret({ code: null, stdout: '', stderr: '', spawnError: Object.assign(new Error('spawn x ENOENT'), { code: 'ENOENT' }) }, 1000).kind, 'spawn');
});

// ── 偽 claude を実際に走らせる ──────────────────────────────
function setup(extraEnv) {
  const dir = S.tmpDir();
  const log = path.join(dir, 'calls.jsonl');
  const env = S.stubEnv(Object.assign({ STUB_LOG: log }, extraEnv || {}));
  const resolved = resolveClaude({ env });
  const calls = () => (fs.existsSync(log) ? fs.readFileSync(log, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []);
  const run = (state, over) =>
    callClaude(Object.assign({ resolved, model: 'sonnet', prompt: 'テスト用の入力 ✓', cwd: dir, timeoutMs: 15000, state, env }, over || {}));
  return { dir, calls, run, cleanup: () => S.rmDir(dir) };
}

test('callClaude: 全部入りのオプションで呼び、プロンプトは標準入力で渡る', async () => {
  const t = setup();
  try {
    const state = {};
    const r = await t.run(state);
    assert.equal(r.ok, true, JSON.stringify(r));
    assert.match(r.text, /"topics"/);
    assert.equal(state.confirmed, true, '返事が来たオプションの組は「確かめた」と覚える');
    const calls = t.calls();
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0].argv, ['-p', '--output-format', 'json', '--model', 'sonnet'].concat(FLAGS_FULL));
    assert.deepEqual(FLAGS_FULL, ['--tools', '', '--safe-mode', '--no-session-persistence']);
    assert.equal(calls[0].stdin, 'テスト用の入力 ✓', '本文は引数ではなく標準入力');
  } finally {
    t.cleanup();
  }
});

test('callClaude: 古い版（未対応オプション）→ 安全のためのオプションを外して呼び直さず、claude update を案内して止まる', async () => {
  const t = setup({ STUB_MODE: 'old-cli' });
  try {
    const state = {};
    const r1 = await t.run(state);
    assert.equal(r1.ok, false, '偽 claude は、オプションを外した呼び出しなら成功する。外したら ok になってしまう: ' + JSON.stringify(r1));
    assert.equal(r1.kind, 'unknown-flag');
    assert.match(r1.message, /claude update/);
    assert.match(r1.message, /起動し直/);
    assert.match(r1.detail, /claude update/, '黒い画面（detail を出す）にも案内が載る');
    assert.notEqual(state.confirmed, true, '失敗では「確かめた」にしない');
    let calls = t.calls();
    assert.equal(calls.length, 1, '外して呼び直さない（呼び出しは 1 回だけ）');
    assert.deepEqual(calls[0].argv, ['-p', '--output-format', 'json', '--model', 'sonnet'].concat(FLAGS_FULL));

    const r2 = await t.run(state);
    assert.equal(r2.ok, false);
    assert.equal(r2.kind, 'unknown-flag');
    calls = t.calls();
    assert.equal(calls.length, 2, '呼び直したときも 1 回だけ増える');
    for (const c of calls) assert.deepEqual(c.argv.slice(-FLAGS_FULL.length), FLAGS_FULL, 'どの呼び出しも安全のためのオプションつき');
  } finally {
    t.cleanup();
  }
});

test('callClaude: 未対応オプション以外の失敗は、ふつうの失敗として返す（古い版の案内にはしない）', async () => {
  const t = setup({ STUB_MODE: 'exit1' });
  try {
    const state = {};
    const r = await t.run(state);
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'exit');
    assert.doesNotMatch(r.message, /claude update/);
    assert.notEqual(state.confirmed, true, '失敗では「確かめた」にしない');
    assert.equal(t.calls().length, 1);
  } finally {
    t.cleanup();
  }
});

test('callClaude: エラー JSON は message に出す（ログイン切れの案内つき）。上限は上限として知らせる', async () => {
  let t = setup({ STUB_MODE: 'error-json' });
  try {
    const r = await t.run({});
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'claude-error');
    assert.match(r.message, /Invalid API key/);
    assert.match(r.message, /ログイン/);
  } finally {
    t.cleanup();
  }
  t = setup({ STUB_MODE: 'limit-json' });
  try {
    const r = await t.run({});
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'usage-limit');
    assert.match(r.message, /利用上限/);
    assert.match(r.message, /resets 3pm/);
  } finally {
    t.cleanup();
  }
});

test('callClaude: 返事が来なければタイムアウトで止める（子プロセスも終わらせる）', async () => {
  const t = setup({ STUB_MODE: 'slow' });
  try {
    const started = Date.now();
    const r = await t.run({}, { timeoutMs: 600 });
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'timeout');
    assert.ok(Date.now() - started < 10000, '60 秒の居座りを待たない');
  } finally {
    t.cleanup();
  }
});

test('callClaude: 起動できない claude は spawn エラーとして返す', async () => {
  const dir = S.tmpDir();
  try {
    const r = await callClaude({
      resolved: { ok: true, command: path.join(dir, 'no-such-binary'), prefix: [] },
      model: 'sonnet',
      prompt: 'x',
      cwd: dir,
      timeoutMs: 5000,
      state: {},
    });
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'spawn');
  } finally {
    S.rmDir(dir);
  }
});
