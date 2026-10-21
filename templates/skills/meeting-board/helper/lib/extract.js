'use strict';
// claude の返事から「ここまでの話」の JSON を取り出して、形を整える。
// 返事は JSON だけのはずだが、コードフェンスや前置きが付くことがあるので許す。

function tryParse(text) {
  try {
    return JSON.parse(text);
  } catch (_) {
    return undefined;
  }
}

// 末尾のカンマ（`,}` `,]`）だけを直す。文字列の中は触らない
function stripTrailingCommas(text) {
  let out = '';
  let inStr = false;
  let esc = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      out += ch;
      if (esc) esc = false;
      else if (ch === '\\') esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') {
      inStr = true;
      out += ch;
      continue;
    }
    if (ch === ',') {
      let j = i + 1;
      while (j < text.length && /\s/.test(text[j])) j++;
      if (text[j] === '}' || text[j] === ']') continue; // このカンマは捨てる
    }
    out += ch;
  }
  return out;
}

// text[start] が '{' のとき、対応する '}' までを返す（文字列の中の括弧は数えない）
function balancedObjectAt(text, start) {
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === '\\') esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') inStr = true;
    else if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null;
}

function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function parseObject(candidate) {
  let v = tryParse(candidate);
  if (v === undefined) v = tryParse(stripTrailingCommas(candidate));
  return isPlainObject(v) ? v : undefined;
}

/**
 * 文字列から JSON オブジェクトを 1 つ取り出す。
 * 優先順: そのまま全体 → ```json フェンスの中 → 文中の { … }（topics 配列を持つものを優先）
 */
function extractJsonObject(text) {
  if (typeof text !== 'string') return null;
  const src = text.replace(/^﻿/, '').trim();
  if (!src) return null;

  const whole = parseObject(src);
  if (whole) return whole;

  const candidates = [];
  const fence = /```[a-zA-Z0-9_-]*\s*\n?([\s\S]*?)```/g;
  let m;
  while ((m = fence.exec(src)) !== null) {
    const inner = m[1].trim();
    const obj = parseObject(inner);
    if (obj) candidates.push(obj);
    else {
      const first = inner.indexOf('{');
      if (first >= 0) {
        const piece = balancedObjectAt(inner, first);
        const o2 = piece && parseObject(piece);
        if (o2) candidates.push(o2);
      }
    }
  }
  if (candidates.length === 0) {
    for (let i = 0; i < src.length; i++) {
      if (src[i] !== '{') continue;
      const piece = balancedObjectAt(src, i);
      if (!piece) continue;
      const obj = parseObject(piece);
      if (obj) {
        candidates.push(obj);
        i += piece.length - 1; // 入れ子の中は見ない
      }
    }
  }
  if (candidates.length === 0) return null;
  const withTopics = candidates.filter((c) => Array.isArray(c.topics));
  return (withTopics.length ? withTopics : candidates)[0];
}

function str(v) {
  if (v === null || v === undefined) return '';
  return typeof v === 'string' ? v.trim() : String(v).trim();
}

function arr(v) {
  return Array.isArray(v) ? v : [];
}

/**
 * ボードの形を整える。topics が配列でなければ失敗（呼び出し側は前のボードを残す）。
 * 事前メモが無いときは checklist / cards を空にする（作り話を出さない）。
 */
function normalizeBoard(obj, options) {
  const hasNotes = !!(options && options.hasNotes);
  if (!isPlainObject(obj) || !Array.isArray(obj.topics)) {
    return { ok: false, error: 'topics の配列がありません' };
  }
  const topics = obj.topics.filter(isPlainObject).map((t) => ({
    title: str(t.title) || '（題名なし）',
    current: t.current === true,
    points: arr(t.points)
      .map((p) => (isPlainObject(p) ? { speaker: str(p.speaker), text: str(p.text) } : { speaker: '', text: str(p) }))
      .filter((p) => p.text),
    decisions: arr(t.decisions).map(str).filter(Boolean),
    todos: arr(t.todos)
      .map((d) => (isPlainObject(d) ? { who: str(d.who), what: str(d.what), when: str(d.when) } : { who: '', what: str(d), when: '' }))
      .filter((d) => d.what),
    numbers: arr(t.numbers).map(str).filter(Boolean),
  }));

  // current はひとつだけ（複数なら最後のもの）
  let lastCurrent = -1;
  topics.forEach((t, i) => {
    if (t.current) lastCurrent = i;
  });
  topics.forEach((t, i) => {
    t.current = i === lastCurrent;
  });

  const board = {
    topics,
    open_questions: arr(obj.open_questions).map(str).filter(Boolean),
    checklist: hasNotes
      ? arr(obj.checklist)
          .filter(isPlainObject)
          .map((c) => ({ item: str(c.item), done: c.done === true, evidence: str(c.evidence) }))
          .filter((c) => c.item)
      : [],
    cards: hasNotes
      ? arr(obj.cards)
          .filter(isPlainObject)
          .map((c) => ({ title: str(c.title), body: str(c.body), why: str(c.why), source: str(c.source) }))
          .filter((c) => c.title || c.body)
          .slice(0, 3)
      : [],
  };
  return { ok: true, board };
}

module.exports = { extractJsonObject, normalizeBoard, stripTrailingCommas, balancedObjectAt };
