/* background.js — Meet のタブから受け取った字幕を、この PC のヘルパー（127.0.0.1）へ渡す。
 *
 *  ・送り先は http://127.0.0.1:47431 だけ（manifest の host_permissions と同じ）
 *  ・ヘルパーが止まっていても、少しの間は手元にためて、つながったら送り直す（上限あり）
 *  ・ツールバーのアイコンの小さな札（バッジ）で状態を知らせる
 *      OFF（灰）… ヘルパーにつながらない / CC（赤）… 通話中なのに字幕が見つからない / 空 … 正常
 */
'use strict';

var HELPER = 'http://127.0.0.1:47431';
var MAX_PENDING = 3000; // ためておく発言の上限（古いものから捨てる）
var BATCH = 200;
var TIMEOUT_MS = 5000;

var pending = new Map(); // id → 発言（送りきれていないもの）
var tabStatus = new Map(); // tabId → { inCall, regionFound, captionsOff }
var helperOk = null; // null = まだ分からない
var chain = Promise.resolve();

function post(path, body) {
  var ctl = new AbortController();
  var timer = setTimeout(function () {
    ctl.abort();
  }, TIMEOUT_MS);
  return fetch(HELPER + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Meeting-Board': '1' },
    body: JSON.stringify(body),
    signal: ctl.signal,
    cache: 'no-store',
  }).then(
    function (res) {
      clearTimeout(timer);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res;
    },
    function (err) {
      clearTimeout(timer);
      throw err;
    }
  );
}

function trimPending() {
  if (pending.size <= MAX_PENDING) return;
  var drop = pending.size - MAX_PENDING;
  var it = pending.keys();
  for (var i = 0; i < drop; i++) pending.delete(it.next().value);
}

// ── バッジ ───────────────────────────────────────────────────
function badgeFor(tabId) {
  if (helperOk === false) {
    return { text: 'OFF', color: '#5f6368', title: '会議ボード: ヘルパーにつながりません（start.cmd を起動してください）' };
  }
  var st = tabStatus.get(tabId);
  if (st && st.inCall && (st.regionFound === false || st.captionsOff === true)) {
    return { text: 'CC', color: '#d93025', title: '会議ボード: 字幕が見つかりません（Meet で字幕をオン：C キー・言語は日本語）' };
  }
  if (helperOk === true) return { text: '', color: '#188038', title: '会議ボード: 字幕を送っています' };
  return { text: '', color: '#188038', title: '会議ボード' };
}

function applyBadge(tabId) {
  try {
    var b = badgeFor(tabId);
    if (tabId >= 0) {
      chrome.action.setBadgeText({ tabId: tabId, text: b.text });
      chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: b.color });
      chrome.action.setTitle({ tabId: tabId, title: b.title });
    }
    var g = badgeFor(-1);
    chrome.action.setBadgeText({ text: helperOk === false ? 'OFF' : '' });
    chrome.action.setBadgeBackgroundColor({ color: g.color });
    chrome.action.setTitle({ title: g.title });
  } catch (e) {
    /* タブが閉じた直後などは無視 */
  }
}

function setHelper(ok, tabId) {
  var changed = helperOk !== ok;
  helperOk = ok;
  if (changed) {
    tabStatus.forEach(function (_v, id) {
      applyBadge(id);
    });
  }
  applyBadge(tabId);
}

// ── ヘルパーへ送る（順番に 1 つずつ） ────────────────────────
function deliver(status) {
  var run = function () {
    var first = true;
    function step() {
      var batch = [];
      pending.forEach(function (e) {
        if (batch.length < BATCH) batch.push(e);
      });
      if (batch.length === 0 && !first) return Promise.resolve(true);
      var body = { entries: batch };
      if (first && status) body.status = status;
      first = false;
      return post('/captions', body).then(
        function () {
          batch.forEach(function (e) {
            if (pending.get(e.id) === e) pending.delete(e.id);
          });
          return pending.size > 0 && batch.length > 0 ? step() : true;
        },
        function () {
          return false;
        }
      );
    }
    return step();
  };
  var p = chain.then(run, run);
  chain = p.catch(function () {});
  return p;
}

function handleTick(msg, sender) {
  var tabId = sender && sender.tab ? sender.tab.id : -1;
  var status = msg.status && typeof msg.status === 'object' ? msg.status : {};
  tabStatus.set(tabId, { inCall: status.inCall === true, regionFound: status.regionFound === true, captionsOff: status.captionsOff === true });
  (Array.isArray(msg.entries) ? msg.entries : []).forEach(function (e) {
    if (e && typeof e.id === 'string') pending.set(e.id, e);
  });
  trimPending();
  return deliver(status).then(function (ok) {
    setHelper(ok, tabId);
    return { delivered: ok === true && pending.size === 0 };
  });
}

function handleDiag(msg, sender) {
  var tabId = sender && sender.tab ? sender.tab.id : -1;
  var diag = msg.diag && typeof msg.diag === 'object' ? msg.diag : {};
  diag.bg = { pending: pending.size, helperOk: helperOk };
  return post('/diag', diag).then(
    function () {
      setHelper(true, tabId);
      return { ok: true };
    },
    function () {
      setHelper(false, tabId);
      return { ok: false };
    }
  );
}

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || typeof msg !== 'object') return false;
  var task = null;
  if (msg.type === 'tick') task = handleTick(msg, sender);
  else if (msg.type === 'diag') task = handleDiag(msg, sender);
  if (!task) return false;
  task.then(sendResponse, function () {
    sendResponse({ delivered: false, ok: false });
  });
  return true; // 返事を非同期で返す
});

chrome.tabs.onRemoved.addListener(function (tabId) {
  tabStatus.delete(tabId);
});
