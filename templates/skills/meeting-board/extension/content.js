/* content.js — Google Meet の字幕を、話者つきで読み取る。
 *
 * 読むのは画面に出ている字幕の文字だけ（音声は扱わない）。送り先は background.js 経由で
 * この PC のヘルパー（127.0.0.1）だけ。
 *
 * 字幕の場所の探し方（上から順に試し、字幕のブロックが取れた最初のものを使う）:
 *   1. aria-label  [role="region"] で aria-label が「字幕」「caption」に当たるもの（現行の Meet）
 *   2. tabindex    div[role="region"][tabindex="0"]   （公開されている字幕保存拡張の多くが使う目印。画面の下にあるものだけ）
 *   3. jscontroller  [jscontroller="KPn5nb"] / [jscontroller="D1tHje"]
 *   4. class       .nMcdL.bj4p3b のブロックの親       （壊れやすい。最後の頼み）
 *   5. 「最新の字幕に移動」ボタンの親の region
 *
 * 現行の Meet の字幕の領域は、子が 2 つ: 1 つ目が字幕の入れ物、2 つ目（IMKgW）は「最新の字幕に移動」
 * のボタン。そこで領域全体の innerText は使わず、ボタンやアイコンの文字を除いた「見える文字の行」
 * から、話者ブロックを探す。ブロックの中は「1 行目 = 話者、残り = 発言」と読む。
 */
(function () {
  'use strict';

  var Core = self.MeetingBoardCore;
  if (!Core || window.__meetingBoardContent) return;
  window.__meetingBoardContent = true;

  var VERSION = '0.0.0';
  try {
    VERSION = chrome.runtime.getManifest().version;
  } catch (e) {
    /* 拡張が入れ替わった直後など */
  }

  var POLL_MS = 1000; // 見つけ直し・取りこぼし防止
  var SEND_MS = 2000; // 変わった発言を送る間隔
  var DIAG_MS = 10000; // 構造の診断を送る間隔
  var AUTO_ON_AFTER_MS = 6000; // 通話に入ってから、字幕オンを試すまで

  var CAPTION_LABEL = /字幕|caption|キャプション/i;
  var ON_LABEL = /字幕をオンにする|turn on captions/i;
  var OFF_LABEL = /字幕をオフにする|turn off captions/i;
  var ICON_FONT = /google symbols|material (icons|symbols)/i;
  var ICON_CLASS = /google-symbols|material-icons|material-symbols/i;
  var KNOWN = {
    block: '.nMcdL.bj4p3b',
    name: '.adE6rb',
    text: '.ygicle.VbkSUe',
    controllers: ['[jscontroller="KPn5nb"]', '[jscontroller="D1tHje"]'],
  };

  var idPrefix = 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  var tracker = Core.createTracker({ idPrefix: idPrefix });

  var state = {
    region: null,
    strategy: null,
    mode: null,
    observer: null,
    observed: null,
    inCall: false,
    inCallSince: 0,
    regionFound: false,
    captionsOff: false,
    everSawCaption: false,
    autoClicked: false,
    lastCaptionAt: 0,
    lastScanAt: 0,
    blocks: 0,
    tried: [],
    sample: [],
    stopped: false,
    sentEntries: 0,
  };
  var timers = [];
  var scanScheduled = false;

  // ── 画面の読み取り（見える文字の行） ─────────────────────────
  function isInlineLevel(display) {
    return (
      display === 'inline' ||
      display === 'contents' ||
      display === 'inline-block' ||
      display === 'inline-flex' ||
      display === 'inline-grid' ||
      display === 'inline-table' ||
      display === 'ruby' ||
      display === 'ruby-base' ||
      display === 'ruby-text'
    );
  }

  // 字幕の文字ではないもの（ボタン・アイコン・隠れた要素）
  function shouldSkip(el) {
    var tag = el.tagName;
    if (tag === 'BUTTON' || tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'IMG') return true;
    if (String(tag).toLowerCase() === 'svg') return true;
    var role = el.getAttribute('role');
    if (role === 'button' || role === 'menuitem' || role === 'tab' || role === 'switch' || role === 'slider' || role === 'textbox' || role === 'combobox' || role === 'listbox') return true;
    if (el.getAttribute('aria-hidden') === 'true' || el.hasAttribute('hidden')) return true;
    var cls = typeof el.className === 'string' ? el.className : '';
    return ICON_CLASS.test(cls);
  }

  /** root の中の「見える文字」を、表示上の行ごとの配列にする（innerText に近いが、ボタンやアイコンを除く） */
  function textLines(root) {
    var lines = [];
    var cur = '';
    function flush() {
      var t = Core.cleanText(cur);
      if (t) lines.push(t);
      cur = '';
    }
    function walk(node) {
      if (node.nodeType === 3) {
        cur += node.nodeValue;
        return;
      }
      if (node.nodeType !== 1) return;
      if (node !== root && shouldSkip(node)) return;
      var cs = window.getComputedStyle(node);
      if (cs.display === 'none' || cs.visibility === 'hidden') return;
      if (ICON_FONT.test(cs.fontFamily || '')) return;
      if (node.tagName === 'BR') {
        flush();
        return;
      }
      var block = !isInlineLevel(cs.display);
      if (block) flush();
      for (var c = node.firstChild; c; c = c.nextSibling) walk(c);
      if (block) flush();
    }
    walk(root);
    flush();
    return lines;
  }

  function elementChildren(el) {
    var out = [];
    for (var c = el.firstElementChild; c; c = c.nextElementSibling) out.push(c);
    return out;
  }

  /**
   * region の中から話者ブロックを探す。
   *   既知のクラスがあればそれ。なければ構造から: 「同じ形の子が並ぶ入れ物」を、1 つ包んだだけの
   *   入れ物は降りながら探す。ボタンだけの子（文字の行が無い子）は数えない。
   */
  function findBlocks(region) {
    var byClass = region.querySelectorAll(KNOWN.block);
    if (byClass.length) return { mode: 'class', blocks: Array.prototype.slice.call(byClass) };

    var C = region;
    for (var depth = 0; depth < 8; depth++) {
      var kids = [];
      var kidLines = [];
      var children = elementChildren(C);
      for (var i = 0; i < children.length; i++) {
        var k = children[i];
        if (shouldSkip(k)) continue;
        var ls = textLines(k);
        if (ls.length) {
          kids.push(k);
          kidLines.push(ls.length);
        }
      }
      if (!kids.length) return { mode: 'none', blocks: [] };
      var all = textLines(C).length;
      var first = kidLines[0];
      if (first >= 2 && (kids.length >= 2 || first < all)) {
        var blocks = [];
        for (var j = 0; j < kids.length; j++) if (kidLines[j] >= 2) blocks.push(kids[j]);
        return { mode: 'structure', blocks: blocks };
      }
      if (kids.length === 1 && first === all) {
        C = kids[0];
        continue;
      }
      return { mode: C === region ? 'region' : 'structure', blocks: all >= 2 ? [C] : [] };
    }
    return { mode: 'none', blocks: [] };
  }

  /** 1 ブロック → { speaker, text } */
  function readBlock(el) {
    var nameEl = el.querySelector(KNOWN.name);
    var textEl = el.querySelector(KNOWN.text);
    if (nameEl && textEl) {
      return {
        speaker: Core.mapSpeaker(Core.joinLines(textLines(nameEl))),
        text: Core.cleanText(Core.joinLines(textLines(textEl))),
      };
    }
    return Core.parseBlockLines(textLines(el));
  }

  // ── 字幕の領域を探す ────────────────────────────────────────
  function regionByLabel() {
    var list = document.querySelectorAll('[role="region"]');
    for (var i = 0; i < list.length; i++) {
      if (CAPTION_LABEL.test(list[i].getAttribute('aria-label') || '')) return [list[i]];
    }
    return [];
  }
  // 字幕は画面の下の方に出る。横の参加者・チャットの枠（背が高く、上から始まる）を字幕と取り違えない
  function looksLikeCaptionPlace(el) {
    var r = el.getBoundingClientRect();
    var vh = window.innerHeight || 0;
    return !vh || (r.top >= vh * 0.35 && r.height <= vh * 0.6);
  }
  function regionByTabindex() {
    return Array.prototype.slice.call(document.querySelectorAll('div[role="region"][tabindex="0"]')).filter(looksLikeCaptionPlace);
  }
  function regionByController() {
    var out = [];
    for (var i = 0; i < KNOWN.controllers.length; i++) {
      var e = document.querySelector(KNOWN.controllers[i]);
      if (e) out.push(e);
    }
    return out;
  }
  function regionByClassBlock() {
    var b = document.querySelector(KNOWN.block);
    return b && b.parentElement ? [b.parentElement] : [];
  }
  function regionByJumpButton() {
    var btn = document.querySelector('button[aria-label*="最新の字幕"], button[aria-label*="atest caption" i]');
    if (!btn) return [];
    var r = btn.closest('[role="region"]');
    if (r) return [r];
    return btn.parentElement && btn.parentElement.parentElement ? [btn.parentElement.parentElement] : [];
  }

  var STRATEGIES = [
    { name: 'aria-label', find: regionByLabel },
    { name: 'tabindex', find: regionByTabindex },
    { name: 'jscontroller', find: regionByController },
    { name: 'class', find: regionByClassBlock },
    { name: 'jump-button', find: regionByJumpButton },
  ];

  function locate() {
    var tried = [];
    var fallback = null;
    var chosen = null;
    var seen = new Set(); // 同じ要素を戦略ごとに読み直さない
    for (var s = 0; s < STRATEGIES.length && !chosen; s++) {
      var cands = [];
      try {
        cands = STRATEGIES[s].find();
      } catch (e) {
        cands = [];
      }
      var best = null;
      for (var i = 0; i < cands.length; i++) {
        if (seen.has(cands[i])) continue;
        seen.add(cands[i]);
        var found = findBlocks(cands[i]);
        if (found.blocks.length && !best) best = { el: cands[i], strategy: STRATEGIES[s].name, mode: found.mode, blocks: found.blocks };
        if (!fallback) fallback = { el: cands[i], strategy: STRATEGIES[s].name, mode: found.mode, blocks: found.blocks };
      }
      tried.push({ name: STRATEGIES[s].name, found: cands.length, withBlocks: best ? 1 : 0 });
      if (best) chosen = best;
    }
    var result = chosen || fallback || { el: null, strategy: null, mode: null, blocks: [] };
    result.tried = tried;
    return result;
  }

  // ── 通話中か・字幕がオフか ──────────────────────────────────
  function buttonWithLabel(re) {
    var list = document.querySelectorAll('button[aria-label], [role="button"][aria-label]');
    for (var i = 0; i < list.length; i++) {
      if (re.test(list[i].getAttribute('aria-label') || '')) return list[i];
    }
    return null;
  }

  function detectInCall() {
    var p = location.pathname || '';
    if (!/^\/[a-z]{3}-[a-z]{4}-[a-z]{3}(\/|$)/i.test(p) && !/^\/lookup\//.test(p)) return false;
    var syms = document.querySelectorAll('.google-symbols, [class*="symbols"], i.material-icons');
    for (var i = 0; i < syms.length; i++) {
      if ((syms[i].textContent || '').trim() === 'call_end') return true;
    }
    return !!document.querySelector('[aria-label*="通話から退出"], button[aria-label*="Leave call" i]');
  }

  // 字幕がオフなら、通話に入って少したってから 1 度だけオンにする（オフにすることは決してしない）
  function maybeTurnOnCaptions(now) {
    if (state.autoClicked || !state.inCall || state.everSawCaption) return;
    if (!state.inCallSince) state.inCallSince = now;
    if (now - state.inCallSince < AUTO_ON_AFTER_MS) return;
    if (state.regionFound && !state.captionsOff) return;
    var btn = buttonWithLabel(ON_LABEL);
    if (!btn || OFF_LABEL.test(btn.getAttribute('aria-label') || '')) return;
    state.autoClicked = true;
    try {
      btn.click();
    } catch (e) {
      /* 押せなくても、バッジ「CC」が手がかりになる */
    }
  }

  // ── 取り込み ────────────────────────────────────────────────
  function scan() {
    if (state.stopped) return;
    var now = Date.now();
    state.lastScanAt = now;
    var loc = locate();
    state.region = loc.el;
    state.strategy = loc.strategy;
    state.mode = loc.mode;
    state.tried = loc.tried;
    state.regionFound = !!loc.el;
    if (loc.el && state.observed !== loc.el) attachObserver(loc.el);
    if (!loc.el && state.observer) {
      state.observer.disconnect();
      state.observer = null;
      state.observed = null;
    }

    var wasIn = state.inCall;
    state.inCall = detectInCall();
    if (state.inCall && !wasIn) state.inCallSince = now;
    if (!state.inCall) state.inCallSince = 0;
    state.captionsOff = !!buttonWithLabel(ON_LABEL);

    var items = [];
    var sample = [];
    for (var i = 0; i < loc.blocks.length; i++) {
      var r = readBlock(loc.blocks[i]);
      if (!r) continue;
      items.push({ key: loc.blocks[i], speaker: r.speaker, text: r.text });
      if (sample.length < 3) {
        var lines = textLines(loc.blocks[i]);
        sample.push({ lines: lines.length, lens: lines.slice(0, 6).map(function (l) { return l.length; }), speakerLen: (r.speaker || '').length, textLen: (r.text || '').length });
      }
    }
    state.blocks = loc.blocks.length;
    state.sample = sample;
    var changed = tracker.scan(items, now);
    if (changed) {
      state.lastCaptionAt = now;
      state.everSawCaption = true;
    }
    maybeTurnOnCaptions(now);
  }

  function scheduleScan() {
    if (scanScheduled || state.stopped) return;
    scanScheduled = true;
    setTimeout(function () {
      scanScheduled = false;
      try {
        scan();
      } catch (e) {
        /* 1 回の失敗で止めない */
      }
    }, 150);
  }

  function attachObserver(el) {
    if (state.observer) state.observer.disconnect();
    state.observer = new MutationObserver(scheduleScan);
    state.observer.observe(el, { childList: true, subtree: true, characterData: true });
    state.observed = el;
  }

  // ── 送る ────────────────────────────────────────────────────
  function shutdown() {
    state.stopped = true;
    if (state.observer) state.observer.disconnect();
    timers.forEach(clearInterval);
  }

  function safeSend(message, onReply) {
    try {
      chrome.runtime.sendMessage(message, function (reply) {
        var err = chrome.runtime.lastError;
        onReply(err ? null : reply);
      });
    } catch (e) {
      // 拡張が更新・削除されて、このページの読み取りだけが残った状態
      shutdown();
      onReply(null);
    }
  }

  function sendTick() {
    if (state.stopped) return;
    var entries = tracker.drain();
    safeSend(
      {
        type: 'tick',
        entries: entries,
        status: { inCall: state.inCall, regionFound: state.regionFound, captionsOff: state.captionsOff, lastCaptionAt: state.lastCaptionAt || null },
      },
      function (reply) {
        if (entries.length) {
          if (reply && reply.delivered === true) state.sentEntries += entries.length;
          else tracker.requeue(entries);
        }
      }
    );
  }

  // ── 構造だけの診断（本文・名前・会議コードは入れない） ────────
  function classString(el) {
    var c = typeof el.className === 'string' ? el.className : el.getAttribute('class') || '';
    return c.length > 80 ? c.slice(0, 80) : c;
  }

  function describe(el, depth, budget) {
    if (budget.n <= 0) return null;
    budget.n -= 1;
    var cs = window.getComputedStyle(el);
    var node = {
      t: el.tagName.toLowerCase(),
      c: classString(el),
      n: el.children.length,
      tl: (el.textContent || '').length,
      ln: textLines(el).length,
      d: cs.display,
    };
    var role = el.getAttribute('role');
    if (role) node.r = role;
    var js = el.getAttribute('jsname');
    if (js) node.j = js;
    var jc = el.getAttribute('jscontroller');
    if (jc) node.jc = jc;
    if (el.querySelector('button, [role="button"]')) node.btn = 1;
    if (depth > 0) {
      var kids = [];
      var children = elementChildren(el);
      for (var i = 0; i < children.length && i < 8; i++) {
        var d = describe(children[i], depth - 1, budget);
        if (d) kids.push(d);
      }
      if (kids.length) node.k = kids;
      if (children.length > 8) node.more = children.length - 8;
    }
    return node;
  }

  function buildDiag() {
    var now = Date.now();
    var region = state.region;
    var label = region ? region.getAttribute('aria-label') || '' : '';
    var diag = {
      v: 1,
      at: now,
      extVersion: VERSION,
      ua: navigator.userAgent,
      inCall: state.inCall,
      regionFound: state.regionFound,
      captionsOff: state.captionsOff,
      autoClicked: state.autoClicked,
      selector: state.strategy,
      mode: state.mode,
      tried: state.tried,
      blocks: state.blocks,
      blockSample: state.sample,
      lastCaptionAgoMs: state.lastCaptionAt ? now - state.lastCaptionAt : null,
      tracked: tracker.trackedCount(),
      live: tracker.liveCount(),
      pending: tracker.pendingCount(),
      sent: state.sentEntries,
      onMeetCodePath: /^\/[a-z]{3}-[a-z]{4}-[a-z]{3}(\/|$)/i.test(location.pathname || ''),
    };
    if (region) {
      // aria-label は領域の名前（「字幕」など）。ラベルで見つけたときだけ中身を出し、それ以外は長さだけ
      if (state.strategy === 'aria-label') diag.regionLabel = label.slice(0, 40);
      else diag.regionLabelLen = label.length;
      diag.regionTabindex = region.getAttribute('tabindex');
      var budget = { n: 120 };
      var root = describe(region, 0, budget);
      var kids = elementChildren(region);
      root.k = [];
      for (var i = 0; i < kids.length && i < 6; i++) {
        // 1 つ目の子（字幕の入れ物）は 3 段下まで、ほかは 1 段だけ
        var d = describe(kids[i], i === 0 ? 3 : 1, budget);
        if (d) root.k.push(d);
      }
      diag.tree = root;
    }
    return diag;
  }

  function sendDiag() {
    if (state.stopped) return;
    var diag;
    try {
      diag = buildDiag();
    } catch (e) {
      diag = { v: 1, extVersion: VERSION, error: String(e && e.name ? e.name : 'error') };
    }
    safeSend({ type: 'diag', diag: diag }, function () {});
  }

  // ── 開始 ────────────────────────────────────────────────────
  function pollTick() {
    try {
      scan();
    } catch (e) {
      /* 次の周期でまた試す */
    }
  }

  timers.push(setInterval(pollTick, POLL_MS));
  timers.push(setInterval(sendTick, SEND_MS));
  timers.push(setInterval(sendDiag, DIAG_MS));
  pollTick();
  setTimeout(sendDiag, 1500);
})();
