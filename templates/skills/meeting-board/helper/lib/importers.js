'use strict';
// --replay で読む文字起こしの形を見分けて、[{ speaker, text, atSec }] にする。
//
//   vtt        WebVTT（.vtt）。話者は <v 名前>本文</v>（Teams の形と推定）か、本文の頭の「名前: 」（Zoom の形と推定）。
//              時刻は「00:00:03.120 --> …」の始まり。同じ話者の続いた合図は、間が 2 秒未満ならつなぐ
//   teams-txt  Teams の文字起こし（.docx）を Word で .txt に保存した形と推定: 「名前  0:01:23」の行の次から、
//              空行か次の「名前 時刻」の行までが本文
//   lines      今までの「話者：本文」（行頭の [時:分:秒] は任意）
//
// どの形も、実物の Teams・Zoom のファイルでは確かめていない（広く知られた形からの推定）。
// 見分けられなければ format: 'unknown' を返す（呼び出し側が理由を言って止まる。でたらめな行は作らない）。

const { parseReplayTimed } = require('./replay');

const VTT_TIME = /^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})/;
const TXT_HEAD = /^(.{1,40}?)[ \t\u3000]{1,}((?:\d{1,2}:)?\d{1,2}:\d{2})\s*$/;
const MERGE_GAP_SEC = 2;
const MAX_SPEAKER = 40;

function sec(h, m, s, ms) {
  return Number(h || 0) * 3600 + Number(m) * 60 + Number(s) + Number(String(ms || '0').padEnd(3, '0')) / 1000;
}

function clean(s) {
  return String(s)
    .replace(/<\/?(?:c|i|b|u|lang|ruby|rt)(?:\.[^>]*)?(?:\s[^>]*)?>/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function selfOr(name) {
  return /^(あなた|you)$/i.test(name) ? '__SELF__' : name;
}

/** WebVTT → [{ speaker, text, atSec, endSec }]（つなぐ前） */
function parseVttCues(text) {
  const blocks = String(text).replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n').split(/\n{2,}/);
  const cues = [];
  let unknownCues = 0;
  for (const block of blocks) {
    const ls = block.split('\n').filter((l) => l.trim() !== '');
    const ti = ls.findIndex((l) => VTT_TIME.test(l));
    if (ti < 0) continue; // WEBVTT の見出し・NOTE・STYLE・番号だけの塊
    const m = VTT_TIME.exec(ls[ti]);
    const atSec = sec(m[1], m[2], m[3], m[4]);
    const endSec = sec(m[5], m[6], m[7], m[8]);
    const payload = ls.slice(ti + 1).join('\n');
    let speaker = '';
    let body = payload;
    const v = /<v(?:\.[^\s>]*)?\s+([^>]+)>([\s\S]*?)(?:<\/v>|$)/.exec(payload);
    if (v) {
      speaker = clean(v[1]);
      body = v[2];
    } else {
      const z = /^([^：:\n]{1,40}?)\s*[：:]\s*([\s\S]+)$/.exec(clean(payload));
      if (z && !/^\d+$/.test(z[1])) {
        speaker = z[1].trim();
        body = z[2];
      }
    }
    body = clean(body);
    if (!body) continue;
    if (!speaker) unknownCues += 1;
    cues.push({ speaker: selfOr(speaker.slice(0, MAX_SPEAKER)) || '不明', text: body, atSec, endSec });
  }
  return { cues, unknownCues };
}

function joinText(a, b) {
  const last = a.charAt(a.length - 1);
  const cjk = /[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]/;
  return a + (cjk.test(last) || cjk.test(b.charAt(0)) ? '' : ' ') + b;
}

function parseVtt(text) {
  const { cues, unknownCues } = parseVttCues(text);
  const out = [];
  for (const c of cues) {
    const prev = out[out.length - 1];
    if (prev && prev.speaker === c.speaker && c.atSec - prev.endSec < MERGE_GAP_SEC) {
      prev.text = joinText(prev.text, c.text);
      prev.endSec = Math.max(prev.endSec, c.endSec);
    } else out.push(Object.assign({}, c));
  }
  return { lines: out.map((c) => ({ speaker: c.speaker, text: c.text, atSec: Math.round(c.atSec) })), cues: cues.length, unknownCues };
}

/** 「名前  0:01:23」＋本文の形 */
function parseTeamsTxt(text) {
  const rows = String(text).replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let cur = null;
  let heads = 0;
  for (const raw of rows) {
    const line = raw.trim();
    const h = TXT_HEAD.exec(line);
    if (h && !/[：:]\s*$/.test(h[1])) {
      heads += 1;
      if (cur && cur.text) out.push(cur);
      const p = h[2].split(':').map(Number);
      const atSec = p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1];
      cur = { speaker: selfOr(h[1].trim().slice(0, MAX_SPEAKER)), text: '', atSec };
      continue;
    }
    if (!line) {
      if (cur && cur.text) {
        out.push(cur);
        cur = null;
      }
      continue;
    }
    if (cur) cur.text = cur.text ? joinText(cur.text, clean(line)) : clean(line);
  }
  if (cur && cur.text) out.push(cur);
  return { lines: out, heads };
}

/**
 * 形を見分けて読む。戻り値: { format: 'vtt' | 'teams-txt' | 'lines' | 'unknown', lines, note }
 * note は案内の 1 行（読めた件数・読み飛ばした数。本文は入れない）
 */
function importTranscript(text, filename) {
  const src = String(text == null ? '' : text);
  const name = String(filename || '').toLowerCase();
  const head = src.replace(/^\uFEFF/, '').trimStart();
  if (/^WEBVTT/.test(head) || name.endsWith('.vtt') || /\d:\d{2}[.,]\d{1,3}\s*-->/.test(src)) {
    const r = parseVtt(src);
    if (!r.lines.length) return { format: 'unknown', lines: [], note: 'WebVTT の合図が読めませんでした（時刻の行「00:00:03.120 --> …」と本文が見つからない）' };
    const note = 'WebVTT として読みました: 合図 ' + r.cues + ' 個 → 発言 ' + r.lines.length + ' 件' + (r.unknownCues ? '（話者が分からない合図 ' + r.unknownCues + ' 個は「不明」）' : '');
    return { format: 'vtt', lines: r.lines, note };
  }
  const t = parseTeamsTxt(src);
  const plain = parseReplayTimed(src);
  if (t.heads >= 2 && t.lines.length >= plain.length) {
    return { format: 'teams-txt', lines: t.lines, note: '「名前 時刻」＋本文の形（Teams の文字起こしを .txt に保存した形と推定）として読みました: 発言 ' + t.lines.length + ' 件' };
  }
  if (plain.length) return { format: 'lines', lines: plain, note: '「話者：本文」の形として読みました: ' + plain.length + ' 行' };
  return {
    format: 'unknown',
    lines: [],
    note: '形を見分けられませんでした。読める形は「話者：本文」の行・WebVTT（.vtt）・「名前 時刻」の行＋本文の 3 つです',
  };
}

module.exports = { importTranscript, parseVtt, parseVttCues, parseTeamsTxt };
