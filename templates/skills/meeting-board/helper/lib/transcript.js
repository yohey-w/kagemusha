'use strict';
// 字幕の保管と、claude に渡す形（「[HH:MM] 話者：発言」の行）への整形。
//
// 1 人の発言は 1 つの entry（拡張機能が付けた id で上書き更新）。長い発言は、
// 整形のときだけ文の切れ目で何行かに分ける（窓の切り出しを行単位で安定させるため）。

const { hhmm } = require('./util');

const SELF_TOKEN = '__SELF__';
const MAX_ID_LEN = 120;
const MAX_SPEAKER_LEN = 80;
const MAX_TEXT_LEN = 20000;
const LINE_SPLIT_AT = 600; // 1 行がこれより長い発言は文の切れ目で分ける

function splitLongText(text, limit) {
  if (text.length <= limit) return [text];
  const out = [];
  let rest = text;
  while (rest.length > limit) {
    // limit 以内で一番うしろの文末（。！？．.!?）を探す
    let cut = -1;
    for (let i = limit; i >= Math.floor(limit / 2); i--) {
      if (/[。！？!?]/.test(rest[i - 1]) || (rest[i - 1] === '.' && (rest[i] === ' ' || i === rest.length))) {
        cut = i;
        break;
      }
    }
    if (cut < 0) cut = limit;
    out.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }
  if (rest) out.push(rest);
  return out.filter(Boolean);
}

class Transcript {
  constructor() {
    this.entries = []; // firstSeen 順
    this.byId = new Map();
    this.seq = 0;
    this.lastCaptionAt = 0; // 最後に字幕が届いた時刻（ヘルパーの時計）
    this.revision = 0; // 変わるたびに増える（保存・描画の判定用）
  }

  /**
   * 拡張機能（または replay）からの 1 件を反映する。反映したら true。
   * raw: { id, speaker, text, firstSeen, lastUpdate, final }
   */
  upsert(raw, now) {
    if (!raw || typeof raw !== 'object') return false;
    const id = typeof raw.id === 'string' ? raw.id.slice(0, MAX_ID_LEN) : '';
    let text = typeof raw.text === 'string' ? raw.text.replace(/\s+/g, ' ').trim() : '';
    if (!id || !text) return false;
    if (text.length > MAX_TEXT_LEN) text = text.slice(text.length - MAX_TEXT_LEN);
    const speaker = typeof raw.speaker === 'string' ? raw.speaker.replace(/\s+/g, ' ').trim().slice(0, MAX_SPEAKER_LEN) : '';
    const num = (v, dflt) => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : dflt);
    const firstSeen = num(raw.firstSeen, now);
    const lastUpdate = num(raw.lastUpdate, now);
    const final = raw.final === true;

    const cur = this.byId.get(id);
    this.lastCaptionAt = now;
    if (!cur) {
      const ent = { id, speaker, text, firstSeen, lastUpdate, final, seq: ++this.seq };
      // firstSeen 順に差し込む（ほぼ末尾）
      let i = this.entries.length;
      while (i > 0 && this.entries[i - 1].firstSeen > firstSeen) i--;
      this.entries.splice(i, 0, ent);
      this.byId.set(id, ent);
      this.revision++;
      return true;
    }
    if (lastUpdate < cur.lastUpdate) return false; // 古い版が遅れて届いた
    let changed = false;
    if (cur.text !== text) {
      cur.text = text;
      changed = true;
    }
    if (speaker && cur.speaker !== speaker) {
      cur.speaker = speaker;
      changed = true;
    }
    if (final && !cur.final) {
      cur.final = true;
      changed = true;
    }
    cur.lastUpdate = lastUpdate;
    if (changed) this.revision++;
    return changed;
  }

  totalChars() {
    let n = 0;
    for (const e of this.entries) n += e.text.length;
    return n;
  }

  /** claude に渡す行。selfName で __SELF__ を置き換える */
  lines(selfName) {
    const self = selfName || '自分';
    const out = [];
    for (const e of this.entries) {
      const who = e.speaker === SELF_TOKEN ? self : e.speaker || '不明';
      const stamp = '[' + hhmm(e.firstSeen) + '] ';
      for (const piece of splitLongText(e.text, LINE_SPLIT_AT)) {
        out.push({ text: stamp + who + '：' + piece, chars: piece.length, entryId: e.id });
      }
    }
    return out;
  }

  /** 画面の「字幕（最新）」用。話者と本文だけ */
  recent(n, selfName) {
    const self = selfName || '自分';
    return this.entries.slice(-n).map((e) => ({
      speaker: e.speaker === SELF_TOKEN ? self : e.speaker || '不明',
      text: e.text,
      at: e.firstSeen,
      final: e.final,
    }));
  }

  toJsonl() {
    return this.entries
      .map((e) =>
        JSON.stringify({ id: e.id, speaker: e.speaker, text: e.text, firstSeen: e.firstSeen, lastUpdate: e.lastUpdate, final: e.final })
      )
      .join('\n');
  }
}

module.exports = { Transcript, splitLongText, SELF_TOKEN, LINE_SPLIT_AT };
