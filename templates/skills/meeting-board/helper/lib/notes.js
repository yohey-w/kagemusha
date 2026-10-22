'use strict';
// 事前メモを読む。「今日聞くこと・伝えること」と「こちらの理解（前提）・前回の決定」を取り出し、
// 聞くことの表の文言と順番をヘルパー側で固定する（claude には状態だけを決めてもらう）。
//
//   parseNotes(text) → {
//     items:   [{ id: 'q1', no: 1, kind: 'ask' | 'tell', text: '新システムの月額（1人あたり）はいくらか。' }, ...],
//     beliefs: [{ id: 'a1', kind: 'decision' | 'belief', text: '切り替えは来年の4月1日に行う。' }, ...],
//     me: '山田' | ''
//   }
//
// 見出し（行頭の # ～ ######、【…】、「…：」で終わる短い行）で節を分ける:
//   前回の決定   /前回の決定|決定事項|決まっていること|前回決めたこと/            → beliefs（kind 'decision'）
//   こちらの理解 /こちらの理解|前提|理解していること|認識|仮説/                     → beliefs（kind 'belief'）
//   聞くこと     /聞くこと|聞きたいこと|確認すること|確認したいこと|確認事項|質問/   → items（kind 'ask'）
//   伝えること   /伝えること|伝えたいこと|話すこと|共有すること|説明すること/       → items（kind 'tell'）
//   （「前回の決定・前提」のように両方に当たる見出しは decision。「聞くこと／伝えること」は項目ごとに見分ける）
// 項目: 「- 」「* 」「・」「1. 」「1) 」「①」で始まる行。字下げした続きの行は前の項目に足す。
//       記号の無い行も、上の節の中なら 1 項目として読む（括弧だけの注記の行は読まない）
// 使う人: 「自分：名前」「使う人：名前」の行（任意）

const MAX_ITEMS = 30;
const MAX_BELIEFS = 20;
const MAX_ITEM_LEN = 200;

const RE_DECISION = /前回の決定|決定事項|決まっていること|前回決めたこと/;
const RE_BELIEF = /こちらの理解|前提|理解していること|認識|仮説/;
const RE_ASK = /聞くこと|聞きたいこと|確認すること|確認したいこと|確認事項|質問/;
const RE_TELL = /伝えること|伝えたいこと|話すこと|共有すること|説明すること|お伝えすること/;
// 「聞くこと／伝えること」が 1 つの見出しのとき、項目の言い方で「伝える」を見分ける
const RE_TELL_ITEM = /^(伝える|伝えること|お伝え|説明|共有)\s*[：:]|(を)?(伝える|お伝えする|説明する|共有する|話す|伝えます|説明します|共有します|お伝えします)[。．.]?$/;

const RE_LIST = /^(?:[-*•・]\s*|\d{1,2}[.)．）]\s*|[０-９]{1,2}[．.）)]\s*|\(\d{1,2}\)\s*|[①-⑳]\s*)/;
const RE_ME = /^(?:自分|使う人|わたし|私)\s*[：:]\s*(.+)$/;

function clipItem(s) {
  const t = String(s).replace(/\s+/g, ' ').trim();
  return t.length > MAX_ITEM_LEN ? t.slice(0, MAX_ITEM_LEN) + '…' : t;
}

/** 見出しの行なら、その文字（記号を除いたもの）を返す。見出しでなければ null */
function headingText(line) {
  let m = /^#{1,6}\s*(.+?)\s*#*\s*$/.exec(line);
  if (m) return m[1];
  m = /^【(.+?)】\s*$/.exec(line);
  if (m) return m[1];
  m = /^■\s*(.+)$/.exec(line);
  if (m) return m[1];
  if (!RE_LIST.test(line) && line.length <= 30) {
    m = /^(.+?)\s*[：:]\s*$/.exec(line);
    if (m) return m[1];
  }
  return null;
}

function classify(heading) {
  if (RE_DECISION.test(heading)) return 'decision';
  if (RE_BELIEF.test(heading)) return 'belief';
  const ask = RE_ASK.test(heading);
  const tell = RE_TELL.test(heading);
  if (ask && tell) return 'mixed';
  if (ask) return 'ask';
  if (tell) return 'tell';
  return 'other';
}

function parseNotes(text) {
  const items = [];
  const beliefs = [];
  let me = '';
  let section = 'none';
  let last = null; // 続きの行を足す先

  const lines = String(text == null ? '' : text).replace(/^﻿/, '').split(/\r?\n/);
  for (const raw of lines) {
    if (!raw.trim()) {
      last = null;
      continue;
    }
    const indented = /^(\s{2,}|\t)/.test(raw);
    const line = raw.trim();

    const meMatch = RE_ME.exec(line);
    if (meMatch && !RE_LIST.test(line)) {
      me = clipItem(meMatch[1]).slice(0, 40);
      last = null;
      continue;
    }

    const h = indented ? null : headingText(line);
    if (h !== null) {
      section = classify(h);
      last = null;
      continue;
    }
    if (section === 'none' || section === 'other') continue;

    const isList = RE_LIST.test(line);
    const body = clipItem(line.replace(RE_LIST, ''));
    if (!body) continue;
    if (!isList && indented && last) {
      // 字下げした続きの行は前の項目に足す
      last.text = clipItem(last.text + ' ' + body);
      continue;
    }
    // 括弧だけの行（「（〜のときは赤い帯で知らせます）」のような注記）は項目にしない
    if (!isList && /^[（(].*[）)]$/.test(line)) continue;
    if (section === 'decision' || section === 'belief') {
      if (beliefs.length >= MAX_BELIEFS) continue;
      last = { id: 'a' + (beliefs.length + 1), kind: section, text: body };
      beliefs.push(last);
    } else {
      if (items.length >= MAX_ITEMS) continue;
      let kind = section;
      if (kind === 'mixed') kind = RE_TELL_ITEM.test(body) ? 'tell' : 'ask';
      last = { id: 'q' + (items.length + 1), no: items.length + 1, kind, text: body };
      items.push(last);
    }
  }
  return { items, beliefs, me };
}

module.exports = { parseNotes, classify, headingText, MAX_ITEMS, MAX_BELIEFS, MAX_ITEM_LEN };
