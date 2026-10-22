'use strict';
// --replay: 会議なしで試すための、ファイルの会話を字幕として流す。
// 行の形は「話者：本文」または「話者: 本文」（先頭に「[HH:MM] 」「[HH:MM:SS] 」があってもよい）。それ以外の行は読み飛ばす。
// 行の 8 割以上に時刻があれば、その間隔に合わせて流す（長い沈黙は 10 秒で打ち切る）。

const SECONDS_PER_LINE = 4; // 1 倍速のとき 1 行あたり約 4 秒

const TIME_RE = /^\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*/;
const MAX_GAP_SEC = 10; // 時刻つきで流すとき、長い沈黙はここで打ち切る（実時間の秒）
const MIN_GAP_SEC = 0.05;

/**
 * 行を読む。戻り値: [{ speaker, text, atSec }]（atSec は行頭の時刻の秒。無ければ null）
 * 時刻は [HH:MM:SS]・[H:MM:SS]・[HH:MM]。同じ分の [HH:MM] が続くときは、その 1 分の中に等間隔で並べる。
 * 日付をまたいで時刻が戻ったら 24 時間足す
 */
function parseReplayTimed(text) {
  const out = [];
  for (const rawLine of String(text).split(/\r?\n/)) {
    let line = rawLine.replace(/^\uFEFF/, '').trim();
    if (!line || line.startsWith('#')) continue;
    let atSec = null;
    let minuteOnly = false;
    const tm = TIME_RE.exec(line);
    if (tm) {
      atSec = Number(tm[1]) * 3600 + Number(tm[2]) * 60 + (tm[3] !== undefined ? Number(tm[3]) : 0);
      minuteOnly = tm[3] === undefined;
      line = line.slice(tm[0].length);
    }
    const m = /^([^：:\s][^：:]{0,23}?)\s*[：:]\s*(.+)$/.exec(line);
    if (!m) continue;
    const speaker = m[1].trim();
    const body = m[2].trim();
    if (!speaker || !body || /^\d+$/.test(speaker)) continue;
    out.push({ speaker: /^(あなた|you)$/i.test(speaker) ? '__SELF__' : speaker, text: body, atSec, minuteOnly });
  }
  // 日付をまたいだら 24 時間足す
  let add = 0;
  let prev = null;
  for (const l of out) {
    if (l.atSec === null) continue;
    if (prev !== null && l.atSec + add < prev - 12 * 3600) add += 24 * 3600;
    l.atSec += add;
    prev = l.atSec;
  }
  // 同じ分の [HH:MM] が続くときは、その 1 分の中に等間隔で並べる
  for (let i = 0; i < out.length; ) {
    if (out[i].atSec === null || !out[i].minuteOnly) {
      i += 1;
      continue;
    }
    let j = i;
    while (j + 1 < out.length && out[j + 1].minuteOnly && out[j + 1].atSec === out[i].atSec) j += 1;
    const n = j - i + 1;
    for (let k = 0; k < n; k++) out[i + k].atSec += Math.floor((60 * k) / n);
    i = j + 1;
  }
  return out.map((l) => ({ speaker: l.speaker, text: l.text, atSec: l.atSec }));
}

/** 時刻つきとして流すか（行の 8 割以上に時刻がある） */
function isTimed(lines) {
  if (!lines.length) return false;
  const n = lines.filter((l) => typeof l.atSec === 'number').length;
  return n / lines.length >= 0.8;
}

function parseReplayText(text) {
  return parseReplayTimed(text).map((l) => ({ speaker: l.speaker, text: l.text }));
}

/** 1 倍速で流したときの長さ（秒）。時刻つきなら最初と最後の差（長い沈黙は打ち切る）、なければ 1 行 4 秒 */
function replaySeconds(lines) {
  if (!isTimed(lines)) return lines.length * SECONDS_PER_LINE;
  const ts = lines.map((l) => l.atSec).filter((t) => typeof t === 'number');
  let sec = 0;
  for (let i = 1; i < ts.length; i++) sec += Math.min(Math.max(ts[i] - ts[i - 1], 0), MAX_GAP_SEC);
  return Math.max(sec, lines.length * 0.5);
}

/**
 * 既定の速さ（--speed auto）: 整理が 6 回ほど入る長さで流す。
 * 1 回の整理のサイクル ≒ 字数のきっかけの待ち（20 秒・間隔が短ければそれ）＋ claude の返事（見込み 45 秒）
 *   例: 277 行（1 倍で 1108 秒）→ 2.8 倍（約 6 分半）／付属の 58 行（232 秒）→ 0.6 倍（約 6 分半）
 */
function autoSpeed({ realSec, intervalSec, estClaudeSec, targetUpdates }) {
  const cycleSec = Math.min(intervalSec || 60, 20) + (estClaudeSec || 45);
  const wantSec = (targetUpdates || 6) * cycleSec;
  return Math.min(50, Math.max(0.5, Math.round((realSec / wantSec) * 10) / 10));
}

/** 行を entry（拡張機能が送るのと同じ形）にする。時刻は 1 行 4 秒ずつ進む仮想時計 */
function toEntries(lines, baseMs) {
  const timed = isTimed(lines);
  const first = timed ? lines.find((l) => typeof l.atSec === 'number').atSec : 0;
  let lastAt = first;
  return lines.map((l, i) => {
    let t;
    if (timed) {
      if (typeof l.atSec === 'number') lastAt = l.atSec;
      t = baseMs + Math.max(0, lastAt - first) * 1000 + i; // 同じ時刻の行の順を保つ
    } else {
      t = baseMs + i * SECONDS_PER_LINE * 1000;
    }
    const e = { id: 'replay-' + (i + 1), speaker: l.speaker, text: l.text, firstSeen: t, lastUpdate: t, final: true };
    if (timed) e.atSec = lastAt;
    return e;
  });
}

/** 流すときの待ち（ミリ秒）。delays[i] は i 行目を流してから次の行までの待ち */
function replayDelays(entries, speed) {
  const sp = speed > 0 ? speed : 1;
  const timed = entries.length > 0 && entries.every((e) => typeof e.atSec === 'number');
  return entries.map((e, i) => {
    if (!timed) return (SECONDS_PER_LINE * 1000) / sp;
    const next = entries[i + 1];
    if (!next) return 0;
    const gapSec = Math.max(next.atSec - e.atSec, 0) / sp;
    return Math.round(Math.min(MAX_GAP_SEC, Math.max(MIN_GAP_SEC, gapSec)) * 1000);
  });
}

/**
 * 実時間で流す。speed 倍速（1 行 = 4 秒 / speed）。
 * onEntry(entry) を 1 行ずつ呼ぶ。stop() で止める。done は全部流し終えたら解決する。
 */
function startReplay(entries, speed, onEntry) {
  const delays = replayDelays(entries, speed);
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
    const wait = delays[i];
    i += 1;
    timer = setTimeout(step, wait);
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

module.exports = {
  parseReplayText,
  parseReplayTimed,
  isTimed,
  replaySeconds,
  autoSpeed,
  toEntries,
  replayDelays,
  startReplay,
  SECONDS_PER_LINE,
  MAX_GAP_SEC,
};
