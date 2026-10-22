/* captions-core.js — 字幕の取り込みロジック（画面 DOM には触らない純粋な関数だけ）
 *
 * ブラウザ拡張（content.js）と Node のテスト（tests/）の両方から読む。
 *   ブラウザ: globalThis.MeetingBoardCore  /  Node: module.exports
 *
 * Meet の字幕は「話者ごとのブロック」が画面に並び、認識が進むたびにブロックの中身が
 * その場で書き換わる。長くなると頭が切り詰められる。ブロックは数秒の沈黙で消える。
 * ここでは、その書き換えを 1 本の発言（id つき）に畳み込む。
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.MeetingBoardCore = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var SELF_TOKEN = '__SELF__';
  var MIN_OVERLAP = 3; // これ未満の重なりは偶然とみなす
  var MAX_OVERLAP_SCAN = 2000;
  var MAX_ENTRY_CHARS = 20000;

  // ── 文字列の整形 ────────────────────────────────────────────
  function cleanText(s) {
    return String(s == null ? '' : s)
      .replace(/[​-‍⁠﻿]/g, '')
      .replace(/ /g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // 自分の表示ラベル（日本語 UI は「あなた」、英語 UI は "You"）を目印に置き換える
  function mapSpeaker(raw) {
    var s = cleanText(raw).replace(/[:：]$/, '').trim();
    if (!s) return '';
    if (/^(あなた|you)$/i.test(s)) return SELF_TOKEN;
    return s.length > 80 ? s.slice(0, 80) : s;
  }

  function isCjkEdge(ch) {
    return /[　-ヿ㐀-鿿＀-￯]/.test(ch || '');
  }

  // 行を 1 本のテキストにつなぐ。日本語どうしの境目には空白を入れない
  function joinLines(parts) {
    var out = '';
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      if (!p) continue;
      if (!out) {
        out = p;
        continue;
      }
      var a = out.charAt(out.length - 1);
      var b = p.charAt(0);
      out += (isCjkEdge(a) || isCjkEdge(b) ? '' : ' ') + p;
    }
    return out;
  }

  // ブロックの中の可視テキスト行 → { speaker, text }（1 行目が話者、残りが発言）
  function parseBlockLines(lines) {
    var cleaned = [];
    for (var i = 0; i < lines.length; i++) {
      var c = cleanText(lines[i]);
      if (c) cleaned.push(c);
    }
    if (cleaned.length === 0) return null;
    return {
      speaker: mapSpeaker(cleaned[0]),
      text: joinLines(cleaned.slice(1)),
    };
  }

  // ── 結合規則 ────────────────────────────────────────────────
  function overlapLen(oldText, newText) {
    var max = Math.min(oldText.length, newText.length, MAX_OVERLAP_SCAN);
    for (var k = max; k >= 1; k--) {
      if (oldText.slice(oldText.length - k) === newText.slice(0, k)) return k;
    }
    return 0;
  }

  function commonPrefixLen(a, b) {
    var n = Math.min(a.length, b.length);
    var i = 0;
    while (i < n && a.charCodeAt(i) === b.charCodeAt(i)) i++;
    return i;
  }

  function commonSuffixLen(a, b) {
    var n = Math.min(a.length, b.length);
    var i = 0;
    while (i < n && a.charCodeAt(a.length - 1 - i) === b.charCodeAt(b.length - 1 - i)) i++;
    return i;
  }

  // 同じブロックの言い直し（「きょう」→「今日」など）。頭と尻が大きく共通なら新しい方を採る
  function looksLikeRevision(oldText, newText) {
    var base = Math.min(oldText.length, newText.length);
    if (base < 8) return false;
    var cp = commonPrefixLen(oldText, newText);
    var cs = commonSuffixLen(oldText.slice(cp), newText.slice(cp));
    return cp + cs >= base * 0.6;
  }

  /**
   * 同じブロックの古い文面と新しい文面を 1 本にする。ブロックの文面は「いま画面に出ている全文」なので、
   * 基本は新しい方で置き換える。古い方を残すのは、頭が切り詰められたと分かるときだけ。
   *   新が旧を含む（伸びた）→ 新
   *   旧が新で始まる（認識が尻を取り消した）→ 新
   *   旧が新を含む（頭が切り詰められた・一瞬戻った）→ 旧
   *   旧の末尾と新の先頭が重なる（切り詰め＋続き）→ 重なりを 1 回だけ残してつなぐ
   *   それ以外（言い直し・途中経過の書き換え）→ 新
   *
   * 0.1 は最後を「旧 + " " + 新」にしていたため、Meet の途中経過（「字。」→「字幕。」→「字幕を。」…）
   * が全部つながって 1 行に入り、25 分で字幕の保存が約 480KB に膨れた。
   */
  function mergeText(oldText, newText) {
    var o = oldText == null ? '' : String(oldText);
    var n = newText == null ? '' : String(newText);
    if (!n) return o;
    if (!o) return n;
    if (n.indexOf(o) !== -1) return n;
    if (o.slice(0, n.length) === n) return n;
    if (o.indexOf(n) !== -1) return o;
    var k = overlapLen(o, n);
    if (k >= MIN_OVERLAP) return o + n.slice(k);
    return n;
  }

  // ── ブロックの追跡 ──────────────────────────────────────────
  /**
   * 画面のブロック（要素）を id に結びつけ、書き換えを 1 本の発言にまとめる。
   * blocks の key は要素そのもの（WeakMap の鍵にする）。Node のテストでは普通のオブジェクトでよい。
   *
   *   var t = createTracker({ idPrefix: 'p1' });
   *   t.scan([{ key: el, speaker: 'あなた' → mapSpeaker 済み, text: '…' }], Date.now());
   *   var changed = t.drain();   // 送るべき発言（変わったもの・消えたもの）
   */
  function createTracker(options) {
    var opts = options || {};
    var prefix = opts.idPrefix || 'c';
    var keyToId = typeof WeakMap === 'function' ? new WeakMap() : null;
    var live = new Map(); // id → 発言（まだ画面にあるもの）
    var dirty = new Map(); // id → 発言のコピー（送る前のもの）
    var counter = 0;
    var tracked = 0;

    function snapshot(ent) {
      return {
        id: ent.id,
        speaker: ent.speaker,
        text: ent.text,
        firstSeen: ent.firstSeen,
        lastUpdate: ent.lastUpdate,
        final: !!ent.final,
      };
    }

    function markDirty(ent) {
      dirty.set(ent.id, snapshot(ent));
    }

    // 要素が作り直された（鍵が変わった）のに中身が地続き、というときは同じ発言とみなす
    function adopt(orphans, taken, b) {
      for (var i = 0; i < orphans.length; i++) {
        var o = orphans[i];
        if (taken.has(o.id)) continue;
        if (o.speaker !== b.speaker) continue;
        var related =
          b.text.indexOf(o.text) !== -1 ||
          o.text.indexOf(b.text) !== -1 ||
          overlapLen(o.text, b.text) >= 8;
        if (related) {
          taken.add(o.id);
          return o;
        }
      }
      return null;
    }

    function scan(blocks, now) {
      var t = now == null ? Date.now() : now;
      var present = new Set();
      var seen = new Set();
      var i;
      for (i = 0; i < blocks.length; i++) present.add(blocks[i].key);

      var orphans = [];
      var taken = new Set();
      live.forEach(function (ent) {
        if (!present.has(ent.key)) orphans.push(ent);
      });

      var changed = false;
      for (i = 0; i < blocks.length; i++) {
        var b = blocks[i];
        var text = cleanText(b.text);
        var speaker = b.speaker || '';
        var id = keyToId ? keyToId.get(b.key) : undefined;
        var ent = id !== undefined ? live.get(id) : null;
        if (!text) {
          // 一瞬だけ中身が空になる描き直しでは、発言を確定させない
          if (ent) seen.add(ent.id);
          continue;
        }
        if (!ent) {
          ent = adopt(orphans, taken, { speaker: speaker, text: text });
          if (ent) {
            ent.key = b.key;
          } else {
            counter += 1;
            ent = {
              id: prefix + '-' + counter,
              key: b.key,
              speaker: speaker,
              text: '',
              firstSeen: t,
              lastUpdate: t,
              final: false,
            };
            live.set(ent.id, ent);
            tracked += 1;
          }
          if (keyToId) keyToId.set(b.key, ent.id);
        }
        seen.add(ent.id);
        var merged = mergeText(ent.text, text);
        if (merged.length > MAX_ENTRY_CHARS) merged = merged.slice(merged.length - MAX_ENTRY_CHARS);
        var speakerChanged = speaker && speaker !== ent.speaker;
        if (merged !== ent.text || speakerChanged) {
          ent.text = merged;
          if (speakerChanged) ent.speaker = speaker;
          ent.lastUpdate = t;
          markDirty(ent);
          changed = true;
        }
      }

      // 画面から消えたブロックは確定させる（最後にもう一度だけ送る）
      live.forEach(function (ent, id) {
        if (seen.has(id)) return;
        ent.final = true;
        ent.lastUpdate = ent.lastUpdate || t;
        markDirty(ent);
        live.delete(id);
        changed = true;
      });
      return changed;
    }

    function drain() {
      var out = [];
      dirty.forEach(function (e) {
        out.push(e);
      });
      dirty.clear();
      return out;
    }

    // 送れなかった分を戻す（新しい版が既にあれば上書きしない。確定済みは確定のまま）
    function rank(x) {
      return x.lastUpdate * 2 + (x.final ? 1 : 0);
    }
    function requeue(entries) {
      for (var i = 0; i < entries.length; i++) {
        var e = entries[i];
        var cur = dirty.get(e.id);
        if (!cur || rank(e) > rank(cur)) dirty.set(e.id, e);
      }
    }

    return {
      scan: scan,
      drain: drain,
      requeue: requeue,
      pendingCount: function () {
        return dirty.size;
      },
      liveCount: function () {
        return live.size;
      },
      trackedCount: function () {
        return tracked;
      },
    };
  }

  return {
    SELF_TOKEN: SELF_TOKEN,
    cleanText: cleanText,
    mapSpeaker: mapSpeaker,
    joinLines: joinLines,
    parseBlockLines: parseBlockLines,
    overlapLen: overlapLen,
    looksLikeRevision: looksLikeRevision,
    mergeText: mergeText,
    createTracker: createTracker,
  };
});
