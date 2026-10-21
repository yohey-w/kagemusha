'use strict';
// 小さな共通関数。外部ライブラリなし。

function pad2(n) {
  return String(n).padStart(2, '0');
}

// [HH:MM]（この PC のローカル時刻）
function hhmm(ms) {
  const d = new Date(ms);
  return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
}

function hhmmss(ms) {
  const d = new Date(ms);
  return pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
}

// 会議フォルダ名: 2026-10-21_093015
function sessionStamp(ms) {
  const d = new Date(ms);
  return (
    d.getFullYear() +
    '-' +
    pad2(d.getMonth() + 1) +
    '-' +
    pad2(d.getDate()) +
    '_' +
    pad2(d.getHours()) +
    pad2(d.getMinutes()) +
    pad2(d.getSeconds())
  );
}

function clip(s, n) {
  const t = String(s == null ? '' : s);
  return t.length > n ? t.slice(0, n) + '…' : t;
}

function errMsg(e) {
  return e && e.message ? String(e.message) : String(e);
}

// 自分のホームフォルダ名を診断に出さない（~ に置き換える）
function shortenHome(p, home) {
  const s = String(p == null ? '' : p);
  if (!home) return s;
  const norm = (x) => x.replace(/\\/g, '/').toLowerCase();
  const ns = norm(s);
  const nh = norm(home).replace(/\/+$/, '');
  if (nh && (ns === nh || ns.startsWith(nh + '/'))) return '~' + s.slice(home.replace(/[\\/]+$/, '').length);
  return s;
}

module.exports = { pad2, hhmm, hhmmss, sessionStamp, clip, errMsg, shortenHome };
