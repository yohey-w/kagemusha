'use strict';
// 台本（--script）: Markdown の台本を節に分け、字幕から「いま台本のどこか」を規則で当てる（claude は使わない）。
//
//   parseScript(text) → [{ title, startSec, lines: [{ kind: 'say' | 'note', text, who }] }]
//     節の見出し: 「【5:00〜 今の流れを聞く】」（** で囲んでもよい。m:ss / h:mm:ss）か「## 見出し」（「# 」は題名なので読まない）
//     節の中: 「名前「…」」で始まる行は自分が言う台詞（say）、それ以外は覚え書き・分岐（note）
//   locate(sections, recent, elapsedSec, prev, opts) → { sectionIndex, lineIndex, by: 'match' | 'time' | 'none', score }
//     直近の字幕（約 60 秒）と各台詞の文字の 2 字組の重なりで、いちばん近い台詞を探す。
//     自分の発言（opts.me / 「自分」/ あなた）は重く見る。弱ければ、最初の字幕からの経過時間で節を選ぶ。
//     強い一致でなければ、1 節より前へは戻らない

const MAX_SECTIONS = 60;
const MAX_LINES = 80;
const MAX_LEN = 300;
const WINDOW_MS = 60000;
const THRESHOLD = 0.3; // これ以上で「一致」
const STRONG = 0.55; // これ以上なら、前の節へ大きく戻ってもよい

function clean(s) {
  return String(s).replace(/\s+/g, ' ').trim();
}

function parseTime(t) {
  const p = String(t).split(':').map(Number);
  if (p.some((x) => !Number.isFinite(x))) return null;
  return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + (p[1] || 0);
}

function headingOf(line) {
  const t = line.replace(/^\*\*|\*\*$/g, '').replace(/^#{1,6}\s*(?=【)/, '').trim();
  let m = /^【\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[〜~ー-]?\s*([^】]*)】$/.exec(t);
  if (m) return { title: clean(m[2]) || m[1], startSec: parseTime(m[1]) };
  m = /^#{2,6}\s+(.+)$/.exec(line); // 「# 」1 つは台本の題名なので節にしない
  if (m) {
    const inner = m[1].replace(/\*\*/g, '').trim();
    const mm = /^【\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[〜~ー-]?\s*([^】]*)】$/.exec(inner);
    if (mm) return { title: clean(mm[2]) || mm[1], startSec: parseTime(mm[1]) };
    return { title: clean(inner), startSec: null };
  }
  return null;
}

function parseScript(text) {
  const sections = [];
  let cur = null;
  for (const raw of String(text == null ? '' : text).replace(/^﻿/, '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const h = headingOf(line);
    if (h) {
      if (sections.length >= MAX_SECTIONS) break;
      cur = { title: h.title.slice(0, 80), startSec: h.startSec, lines: [] };
      sections.push(cur);
      continue;
    }
    if (!cur) continue; // 最初の見出しより前（題名・前書き）は読まない
    if (cur.lines.length >= MAX_LINES) continue;
    const body = line.replace(/^(?:[-*・]\s+|\d{1,2}[.)]\s+|>\s*)/, '');
    const say = /^([^「」\s]{1,12})「(.+?)」?$/.exec(body);
    if (say) cur.lines.push({ kind: 'say', who: say[1], text: clean(say[2]).slice(0, MAX_LEN) });
    else cur.lines.push({ kind: 'note', text: clean(body.replace(/\*\*/g, '')).slice(0, MAX_LEN) });
  }
  return sections;
}

function norm(s) {
  return String(s).replace(/[\s、。，．,.!！?？「」『』（）()・…ー-]/g, '');
}
function bigrams(s) {
  const t = norm(s);
  const out = new Set();
  for (let i = 0; i + 2 <= t.length; i++) out.add(t.slice(i, i + 2));
  return out;
}
/** 台詞の 2 字組のうち、字幕に出た割合（0〜1） */
function overlap(lineGrams, textGrams) {
  if (!lineGrams.size) return 0;
  let n = 0;
  for (const g of lineGrams) if (textGrams.has(g)) n += 1;
  return n / lineGrams.size;
}

function isUser(speaker, me) {
  return speaker === '自分' || speaker === '__SELF__' || /^(あなた|you)$/i.test(speaker || '') || (!!me && speaker === me);
}

function locate(sections, recent, elapsedSec, prev, opts) {
  const o = opts || {};
  const none = { sectionIndex: -1, lineIndex: -1, by: 'none', score: 0 };
  if (!Array.isArray(sections) || !sections.length) return none;
  const caps = Array.isArray(recent) ? recent : [];
  const lastAt = caps.reduce((m, c) => Math.max(m, c.at || 0), 0);
  const win = caps.filter((c) => !lastAt || !c.at || c.at >= lastAt - WINDOW_MS);
  // 字幕は 1 行ずつ比べる（まとめて比べると、長い台詞がどれとでも少しずつ重なってしまう）。
  // 自分の発言は重く、相手の発言は 6 割。新しい字幕ほど少し重く（1 行古くなるごとに 3% ずつ割り引く）
  const capGrams = win
    .slice()
    .reverse()
    .slice(0, 20)
    .map((c, age) => ({ grams: bigrams(c.text), w: (isUser(c.speaker, o.me) ? 1 : 0.6) * Math.max(0.5, 1 - 0.03 * age) }));
  let best = null;
  sections.forEach((s, si) => {
    s.lines.forEach((l, li) => {
      if (l.kind !== 'say') return;
      const g = bigrams(l.text);
      let score = 0;
      for (const c of capGrams) score = Math.max(score, overlap(g, c.grams) * c.w);
      if (!best || score > best.score) best = { sectionIndex: si, lineIndex: li, by: 'match', score: Math.round(score * 100) / 100 };
    });
  });
  const p = prev && prev.sectionIndex >= 0 ? prev : null;
  if (best && best.score >= THRESHOLD) {
    // 1 節より前へ戻るのは、強い一致のときだけ
    if (p && best.sectionIndex < p.sectionIndex - 1 && best.score < STRONG) return p;
    return best;
  }
  // 一致が弱い → 経過時間で節を選ぶ（台詞の位置は先頭）
  if (typeof elapsedSec === 'number' && elapsedSec >= 0 && sections.some((s) => typeof s.startSec === 'number')) {
    let si = 0;
    sections.forEach((s, i) => {
      if (typeof s.startSec === 'number' && s.startSec <= elapsedSec) si = i;
    });
    if (p && p.sectionIndex > si && p.by === 'match') return p; // 一致で進んだ位置から、時間で戻さない
    return { sectionIndex: si, lineIndex: p && p.sectionIndex === si ? p.lineIndex : -1, by: 'time', score: best ? best.score : 0 };
  }
  return p || { sectionIndex: 0, lineIndex: -1, by: 'none', score: 0 };
}

const PLACEHOLDER = /(〇〇|○○|◯◯|△△|□□|××|＿＿|__)/;

/**
 * 台本の「最後に確かめる文」: 〇〇・△△・□□ などの穴のある台詞。いくつもあれば、穴のある台詞を含む
 * いちばん後ろの節で、問いの形（か。／か？）のもの（無ければその節の最後の穴あき台詞）。無ければ null
 */
function findClosingLine(sections) {
  const list = Array.isArray(sections) ? sections : [];
  for (let si = list.length - 1; si >= 0; si--) {
    const cands = [];
    list[si].lines.forEach((l, li) => {
      if (l.kind === 'say' && PLACEHOLDER.test(l.text)) cands.push({ sectionIndex: si, lineIndex: li, text: l.text, who: l.who });
    });
    if (!cands.length) continue;
    const q = cands.filter((c) => /か[。？?]?$/.test(c.text));
    return (q.length ? q[q.length - 1] : cands[cands.length - 1]);
  }
  return null;
}

module.exports = { parseScript, locate, findClosingLine, PLACEHOLDER, bigrams, overlap, THRESHOLD, STRONG };
