'use strict';
// テスト共通の道具。名前を test 系にしないのは、node --test が試験ファイルと取り違えないため。
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const HELPER_DIR = path.join(ROOT, 'helper');
const STUB = path.join(__dirname, 'claude_stub.js');
const SAMPLE_DIR = path.join(ROOT, 'sample');

const { MeetingBoardApp } = require(path.join(HELPER_DIR, 'lib', 'app.js'));
const { listen } = require(path.join(HELPER_DIR, 'lib', 'httpserver.js'));

function tmpDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix || 'mb-test-'));
}

function rmDir(dir) {
  // 自分で作った一時フォルダだけを消す
  if (dir && path.basename(dir).startsWith('mb-test-')) fs.rmSync(dir, { recursive: true, force: true });
}

/** 本物の claude は決して呼ばない: 環境は偽 claude を指す */
function stubEnv(extra) {
  return Object.assign({}, process.env, { CLAUDE_BIN: STUB }, extra || {});
}

async function startApp(options) {
  const o = options || {};
  const dataDir = o.dataDir || tmpDir();
  const log = path.join(dataDir, 'stub.log');
  const clock = { t: o.startAt || Date.now() };
  const app = new MeetingBoardApp({
    version: 'test',
    port: 0,
    model: 'sonnet',
    intervalSec: o.intervalSec || 60,
    timeoutMs: o.timeoutMs || 20000,
    dataDir,
    promptPath: path.join(HELPER_DIR, 'prompt.md'),
    boardHtmlPath: path.join(HELPER_DIR, 'board.html'),
    notes: o.notes || '',
    mode: o.mode,
    env: stubEnv(Object.assign({ STUB_LOG: log }, o.env || {})),
    now: o.fakeClock ? () => clock.t : undefined,
  });
  const server = await listen(app, 0);
  app.port = server.address().port;
  return {
    app,
    server,
    port: app.port,
    dataDir,
    clock,
    stubLog: log,
    calls() {
      if (!fs.existsSync(log)) return [];
      return fs
        .readFileSync(log, 'utf8')
        .split('\n')
        .filter(Boolean)
        .map((l) => JSON.parse(l));
    },
    async close() {
      app.shutdown();
      await new Promise((r) => server.close(r));
      rmDir(dataDir);
    },
  };
}

/** http.request の薄い包み（Node 18 でも警告が出ないよう fetch は使わない） */
function request(port, method, urlPath, { headers, body, host } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? null : typeof body === 'string' ? body : JSON.stringify(body);
    const h = Object.assign({}, headers || {});
    if (payload !== null) {
      h['Content-Type'] = h['Content-Type'] || 'application/json';
      h['Content-Length'] = Buffer.byteLength(payload);
    }
    if (host) h.Host = host;
    const req = http.request({ host: '127.0.0.1', port, method, path: urlPath, headers: h }, (res) => {
      let data = '';
      res.setEncoding('utf8');
      res.on('data', (d) => {
        data += d;
      });
      res.on('end', () => {
        let json = null;
        try {
          json = JSON.parse(data);
        } catch (_) {
          /* テキストのこともある */
        }
        resolve({ status: res.statusCode, headers: res.headers, text: data, json });
      });
    });
    req.on('error', reject);
    if (payload !== null) req.write(payload);
    req.end();
  });
}

const API = { 'X-Meeting-Board': '1' };

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitFor(fn, timeoutMs, stepMs) {
  const end = Date.now() + (timeoutMs || 10000);
  while (Date.now() < end) {
    const v = await fn();
    if (v) return v;
    await sleep(stepMs || 50);
  }
  throw new Error('waitFor: 時間切れ');
}

module.exports = {
  ROOT,
  HELPER_DIR,
  STUB,
  SAMPLE_DIR,
  tmpDir,
  rmDir,
  stubEnv,
  startApp,
  request,
  API,
  sleep,
  waitFor,
};
