'use strict';
// --replay: 会議なしで試すための、ファイルの会話を字幕として流す。
// 行の形は「話者：本文」または「話者: 本文」（先頭に「[HH:MM] 」があってもよい）。それ以外の行は読み飛ばす。

const SECONDS_PER_LINE = 4; // 1 倍速のとき 1 行あたり約 4 秒

function parseReplayText(text) {
  const out = [];
  for (const rawLine of String(text).split(/\r?\n/)) {
    let line = rawLine.replace(/^﻿/, '').trim();
    if (!line || line.startsWith('#')) continue;
    line = line.replace(/^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*/, '');
    const m = /^([^：:\s][^：:]{0,23}?)\s*[：:]\s*(.+)$/.exec(line);
    if (!m) continue;
    const speaker = m[1].trim();
    const body = m[2].trim();
    if (!speaker || !body || /^\d+$/.test(speaker)) continue;
    out.push({ speaker: /^(あなた|you)$/i.test(speaker) ? '__SELF__' : speaker, text: body });
  }
  return out;
}

/** 行を entry（拡張機能が送るのと同じ形）にする。時刻は 1 行 4 秒ずつ進む仮想時計 */
function toEntries(lines, baseMs) {
  return lines.map((l, i) => {
    const t = baseMs + i * SECONDS_PER_LINE * 1000;
    return { id: 'replay-' + (i + 1), speaker: l.speaker, text: l.text, firstSeen: t, lastUpdate: t, final: true };
  });
}

/**
 * 実時間で流す。speed 倍速（1 行 = 4 秒 / speed）。
 * onEntry(entry) を 1 行ずつ呼ぶ。stop() で止める。done は全部流し終えたら解決する。
 */
function startReplay(entries, speed, onEntry) {
  const gap = (SECONDS_PER_LINE * 1000) / speed;
  let i = 0;
  let timer = null;
  let stopped = false;
  let resolveDone;
  const done = new Promise((r) => {
    resolveDone = r;
  });
  const step = () => {
    if (stopped) return;
    if (i >= entries.length) {
      resolveDone(true);
      return;
    }
    onEntry(entries[i], i);
    i += 1;
    timer = setTimeout(step, gap);
  };
  timer = setTimeout(step, 0);
  return {
    done,
    stop() {
      stopped = true;
      clearTimeout(timer);
      resolveDone(false);
    },
    progress() {
      return { index: i, total: entries.length };
    },
  };
}

module.exports = { parseReplayText, toEntries, startReplay, SECONDS_PER_LINE };
