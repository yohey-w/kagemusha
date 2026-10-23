'use strict';
// 127.0.0.1 だけで待ち受ける小さな HTTP サーバー。
//   GET  /          ボード（board.html に board-core.js を埋め込んだもの）。ヘッダ不要
//   それ以外は X-Meeting-Board: 1 が必須（付いていなければ 403）。
//   別のサイトのページから勝手に叩かれないようにするための札で、ブラウザは他サイトからは
//   この独自ヘッダを付けて送れない（事前確認が必要になり、こちらは許可を返さない）。

const fs = require('fs');
const http = require('http');
const pathMod = require('path');

const HEADER = 'x-meeting-board';
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const BOARD_CSP =
  "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

function send(res, status, type, body) {
  const buf = Buffer.from(body, 'utf8');
  res.writeHead(status, {
    'Content-Type': type,
    'Content-Length': buf.length,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  res.end(buf);
}

function sendJson(res, status, obj) {
  send(res, status, 'application/json; charset=utf-8', JSON.stringify(obj));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    let failed = false;
    req.on('data', (c) => {
      if (failed) return;
      size += c.length;
      if (size > MAX_BODY_BYTES) {
        failed = true;
        const err = new Error('body too large');
        err.status = 413;
        reject(err);
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => {
      if (!failed) resolve(Buffer.concat(chunks).toString('utf8'));
    });
    req.on('error', (e) => {
      if (!failed) reject(e);
    });
  });
}

async function readJson(req) {
  const text = await readBody(req);
  if (!text.trim()) return {};
  try {
    const v = JSON.parse(text);
    return v && typeof v === 'object' ? v : {};
  } catch (_) {
    const err = new Error('invalid JSON');
    err.status = 400;
    throw err;
  }
}

const CORE_MARK = '<!--BOARD_CORE-->';

/** board.html の印 <!--BOARD_CORE--> を board-core.js の中身（<script> で包む）に差し替える */
function buildBoardPage(app) {
  const html = fs.readFileSync(app.boardHtmlPath, 'utf8');
  const corePath = app.boardCorePath || pathMod.join(pathMod.dirname(app.boardHtmlPath), 'board-core.js');
  const core = fs.readFileSync(corePath, 'utf8');
  if (/<\/script/i.test(core)) throw new Error('board-core.js に </script が含まれています');
  return html.replace(CORE_MARK, function () {
    return '<script>\n' + core + '\n</script>';
  });
}

function createHandler(app) {
  return async function handle(req, res) {
    try {
      const path = String(req.url || '/').split('?')[0];
      const method = req.method || 'GET';

      // Host が 127.0.0.1 / localhost 以外なら断る（DNS リバインディング対策）
      if (!/^(127\.0\.0\.1|localhost)(:\d+)?$/i.test(String(req.headers.host || ''))) {
        send(res, 403, 'text/plain; charset=utf-8', 'forbidden host');
        return;
      }

      if (method === 'GET' && path === '/') {
        let html;
        try {
          html = buildBoardPage(app);
        } catch (_) {
          send(res, 500, 'text/plain; charset=utf-8', 'board.html（または board-core.js）が読めません');
          return;
        }
        const buf = Buffer.from(html, 'utf8');
        res.writeHead(200, {
          'Content-Type': 'text/html; charset=utf-8',
          'Content-Length': buf.length,
          'Cache-Control': 'no-store',
          'Content-Security-Policy': BOARD_CSP,
          'X-Content-Type-Options': 'nosniff',
          'Referrer-Policy': 'no-referrer',
        });
        res.end(buf);
        return;
      }

      if (req.headers[HEADER] !== '1') {
        sendJson(res, 403, { error: 'X-Meeting-Board: 1 のヘッダが必要です' });
        return;
      }

      const route = method + ' ' + path;
      switch (route) {
        case 'GET /state':
          sendJson(res, 200, app.stateJson());
          return;
        case 'GET /diag':
          send(res, 200, 'text/plain; charset=utf-8', app.diagText());
          return;
        case 'GET /notes':
          sendJson(res, 200, { text: app.notes, spec: app.notesSpec() });
          return;
        case 'POST /captions': {
          const body = await readJson(req);
          const accepted = app.ingestCaptions(body.entries, body.status);
          sendJson(res, 200, { ok: true, accepted });
          return;
        }
        case 'POST /diag': {
          const body = await readJson(req);
          sendJson(res, 200, { ok: app.setDiag(body) });
          return;
        }
        case 'POST /notes': {
          const body = await readJson(req);
          app.setNotes(body.text);
          sendJson(res, 200, { ok: true, notesPresent: !!app.notes.trim() });
          return;
        }
        case 'POST /settings': {
          const body = await readJson(req);
          const selfName = app.setSelfName(body.selfName);
          sendJson(res, 200, { ok: true, selfName });
          return;
        }
        case 'POST /override': {
          // 人が聞くことの状態を直す: { target: 'checklist', id: 'q1', state: 'done' | 'deferred' | 'open' | 'auto', owner }
          const body = await readJson(req);
          if (body.target !== undefined && body.target !== 'checklist') {
            sendJson(res, 400, { error: 'target は checklist だけです' });
            return;
          }
          const r = app.setOverride(body.id, body.state, body.owner);
          if (!r.ok) sendJson(res, r.status, { error: r.error });
          else sendJson(res, 200, { ok: true });
          return;
        }
        case 'POST /reset':
          app.reset();
          sendJson(res, 200, { ok: true });
          return;
        default:
          break;
      }
      const known = ['/state', '/diag', '/notes', '/captions', '/settings', '/reset', '/override'];
      if (known.indexOf(path) >= 0) sendJson(res, 405, { error: 'method not allowed' });
      else sendJson(res, 404, { error: 'not found' });
    } catch (e) {
      const status = e && e.status ? e.status : 500;
      try {
        sendJson(res, status, { error: status === 500 ? 'internal error' : e.message });
      } catch (_) {
        /* 既に閉じている */
      }
    }
  };
}

/** 127.0.0.1 だけに bind して待ち受ける。戻り値: Promise<http.Server>（EADDRINUSE などは reject） */
function listen(app, port) {
  return new Promise((resolve, reject) => {
    const server = http.createServer(createHandler(app));
    server.on('error', reject);
    server.listen(port, '127.0.0.1', () => {
      server.removeListener('error', reject);
      server.on('error', () => {});
      resolve(server);
    });
  });
}

/** すでに別のヘルパーが同じポートで動いているか調べる（二重起動の案内用） */
function probeExisting(port) {
  return new Promise((resolve) => {
    const req = http.request(
      { host: '127.0.0.1', port, path: '/state', method: 'GET', headers: { 'X-Meeting-Board': '1' }, timeout: 3000 },
      (res) => {
        let data = '';
        res.setEncoding('utf8');
        res.on('data', (d) => {
          if (data.length < 200000) data += d;
        });
        res.on('end', () => {
          try {
            const j = JSON.parse(data);
            resolve(!!(j && j.status && typeof j.status.version === 'string'));
          } catch (_) {
            resolve(false);
          }
        });
      }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    req.end();
  });
}

module.exports = { createHandler, listen, probeExisting, buildBoardPage, HEADER, CORE_MARK };
