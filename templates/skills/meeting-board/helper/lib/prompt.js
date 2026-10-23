'use strict';
// claude に渡す入力の組み立て（窓の切り出し・4 つの節・更新を始める条件）。
// 指示文そのものは prompt.md（そのまま使う。ここでは書き換えない）。

const WHOLE_LIMIT = 12000; // 字幕がこれ以下なら毎回「全部」を渡す
const OVERLAP_CHARS = 2000; // 「前回より後だけ」のとき、前回の手前から重ねて渡す量
const HARD_CAP_CHARS = 60000; // 長く止まっていたあとの安全弁
const NOTES_CAP_CHARS = 30000;

function linesLength(lines) {
  let n = 0;
  for (const l of lines) n += l.text.length + 1;
  return n;
}

/**
 * 渡す字幕の範囲を決める。
 *   lines: transcript.lines() の結果 / lastLineCount: 前回の更新時点の行数（0 = 初回）
 * 戻り値: { range: '全部' | '前回より後だけ', lines }
 */
function buildWindow(lines, lastLineCount) {
  if (linesLength(lines) <= WHOLE_LIMIT) return { range: '全部', lines: lines.slice() };

  // 初回（前回の整理が無い）は、長くても「全部」から組み立てる。安全弁で古い側だけ削る
  if (!lastLineCount) {
    let all = lines.slice();
    while (all.length > 1 && linesLength(all) > HARD_CAP_CHARS) all = all.slice(1);
    return { range: '全部', lines: all };
  }

  // 前回の最後の行は、あとから伸びていることがあるのでもう一度含める。
  // 字幕は書き換わって短くなることがある（長い発言の切れ目が変わる・言い直し）ので、
  // 前回の行数がいまの行数より多くても、いまの最後の行を越えて読まない
  // （0.1 では越えて読み、undefined.text で整理が止まった）
  const from = Math.min(Math.max(0, lastLineCount - 1), lines.length - 1);
  let start = from;
  let overlap = 0;
  while (start > 0 && overlap < OVERLAP_CHARS) {
    start -= 1;
    overlap += lines[start].text.length + 1;
  }
  let picked = lines.slice(start);
  // 長く更新できなかったあとの安全弁: 新しい側を残す
  while (picked.length > 1 && linesLength(picked) > HARD_CAP_CHARS) picked = picked.slice(1);
  return { range: '前回より後だけ', lines: picked };
}

const KIND_LABEL = { ask: '聞く', tell: '伝える', decision: '前回の決定', belief: 'こちらの理解' };

/** 【聞くこと・伝えることの表】【こちらの理解】の 1 行 1 項目（例: 「q1（聞く）: 月額はいくらか。」） */
function specLines(list) {
  if (!Array.isArray(list) || !list.length) return 'なし';
  return list.map((x) => x.id + '（' + (KIND_LABEL[x.kind] || x.kind) + '）: ' + x.text).join('\n');
}

const DIFF_OVERLAP_CHARS = 800; // 差分の整理で、前回の手前から重ねて渡す量

/**
 * 差分の整理の窓: 前回より後の行だけ（手前に約 800 字重ねる）。前回が無ければ buildWindow と同じ
 */
function buildWindowDiff(lines, lastLineCount) {
  if (!lastLineCount || !lines.length) return buildWindow(lines, lastLineCount);
  const from = Math.min(Math.max(0, lastLineCount - 1), lines.length - 1);
  let start = from;
  let overlap = 0;
  while (start > 0 && overlap < DIFF_OVERLAP_CHARS) {
    start -= 1;
    overlap += lines[start].text.length + 1;
  }
  let picked = lines.slice(start);
  while (picked.length > 1 && linesLength(picked) > HARD_CAP_CHARS) picked = picked.slice(1);
  return { range: '前回より後だけ', lines: picked };
}

/**
 * claude へ標準入力で渡す全文。prompt.md の後ろに節を続ける:
 *   【使う人】【事前メモ】【聞くこと・伝えることの表】【こちらの理解】【前回までの整理】【字幕の範囲】【字幕】
 * （0.1 からある 4 つ —— 事前メモ・前回までの整理・字幕の範囲・字幕 —— の順番は変えない）
 *   users: 使う人の説明の 1 行（無ければ「なし」）/ spec: parseNotes() の結果（無ければ「なし」）
 */
function buildPrompt({ promptMd, notes, prevBoard, range, lines, users, spec }) {
  const memo = (notes || '').trim();
  const memoText = memo ? (memo.length > NOTES_CAP_CHARS ? memo.slice(0, NOTES_CAP_CHARS) : memo) : 'なし';
  const sp = spec || {};
  return [
    String(promptMd).replace(/\s+$/, ''),
    '',
    '【使う人】',
    users ? String(users) : 'なし',
    '',
    '【事前メモ】',
    memoText,
    '',
    '【聞くこと・伝えることの表】',
    specLines(sp.items),
    '',
    '【こちらの理解】',
    specLines(sp.beliefs),
    '',
    '【前回までの整理】',
    prevBoard ? JSON.stringify(prevBoard) : 'なし',
    '',
    '【字幕の範囲】',
    range,
    '',
    '【字幕】',
    lines.map((l) => l.text).join('\n'),
    '',
  ].join('\n');
}

/**
 * 更新を始めてよいか。
 *   - 新しい字幕が 120 字以上、かつ前回の終わりから 20 秒以上 → 始める
 *   - 新しい字幕が 1 字でもあり、かつ前回の終わりから interval 秒以上 → 始める
 *   - 事前メモを変えた直後は、字幕がすでにあれば 20 秒空けて 1 回やり直す
 *   - minGapMs があれば（差分の整理）、話者の交代 3 回＋80 字、または 120 字で、minGapMs から前倒しで始める
 * 戻り値: 理由の文字列（始める）/ null（まだ）
 */
function shouldUpdate({ inFlight, now, lastEndAt, blockedUntil, newChars, intervalMs, notesDirty, hasTranscript, speakerTurns, minGapMs }) {
  if (inFlight) return null;
  if (now < (blockedUntil || 0)) return null;
  const since = now - lastEndAt;
  // 前倒し（差分の整理のとき。minGapMs を渡したときだけ効く）: 話者の交代が 3 回以上・80 字以上、
  // または 120 字以上たまったら、前回の終わりから minGapMs（既定 8 秒）で始める
  if (minGapMs && since >= minGapMs) {
    if ((speakerTurns || 0) >= 3 && newChars >= 80) return 'turns';
    if (newChars >= 120) return 'chars';
  }
  if (newChars >= 120 && since >= 20000) return 'chars';
  if (newChars > 0 && since >= intervalMs) return 'interval';
  if (notesDirty && hasTranscript && since >= 20000) return 'notes';
  return null;
}

module.exports = {
  buildWindow,
  buildWindowDiff,
  DIFF_OVERLAP_CHARS,
  buildPrompt,
  shouldUpdate,
  WHOLE_LIMIT,
  OVERLAP_CHARS,
  HARD_CAP_CHARS,
  NOTES_CAP_CHARS,
};
