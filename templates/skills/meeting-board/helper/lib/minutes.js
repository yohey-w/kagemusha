'use strict';
// 会議のあとに、保存したボード（board.json）から Markdown の議事録の素を作る。純粋な関数。
// 書き出し先はファイルと標準出力だけ（どこにも送らない）。
//
//   boardToMarkdown(board, { startedAt, endedAt, speakers }) → 文字列
//   節の順: 決まったこと／宿題（誰・いつまで）／まだ答えをもらっていないこと／前提と食い違ったこと／
//          聞くこと・伝えることの結果／話題ごとの記録。中身の無い節は出さない。
//   0.1 の形のボード（schema なし・checklist は done だけ）からも書ける。

function arr(v) {
  return Array.isArray(v) ? v : [];
}
function str(v) {
  if (v === null || v === undefined || typeof v === 'object') return '';
  return String(v).replace(/\s+/g, ' ').trim();
}
// 表の 1 マス: | と改行で表が崩れないようにする
function cell(v) {
  return str(v).replace(/\|/g, '\\|') || '—';
}
function pad(n) {
  return String(n).padStart(2, '0');
}
function dateTime(ms) {
  const d = new Date(ms);
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}
function hm(ms) {
  const d = new Date(ms);
  return pad(d.getHours()) + ':' + pad(d.getMinutes());
}
function stateOf(c) {
  if (c && (c.state === 'done' || c.state === 'deferred' || c.state === 'open')) return c.state;
  return c && c.done === true ? 'done' : 'open';
}

function boardToMarkdown(board, info) {
  const b = board && typeof board === 'object' ? board : {};
  const o = info || {};
  const topics = arr(b.topics).filter((t) => t && typeof t === 'object');
  const L = [];
  L.push('# 会議の記録（自動整理の下書き）');
  L.push('');
  if (o.startedAt && o.endedAt) L.push('- 日時: ' + dateTime(o.startedAt) + '〜' + hm(o.endedAt) + '（字幕の最初と最後）');
  if (arr(o.speakers).length) L.push('- 字幕に出た名前: ' + arr(o.speakers).map(str).filter(Boolean).join('、'));
  L.push('');
  L.push('> 自動字幕から整理した下書きです。〔?〕は聞き取りが怪しい語です。外に出す前に必ず見直してください。');

  const section = (title, lines) => {
    if (!lines.length) return;
    L.push('');
    L.push('## ' + title);
    L.push('');
    for (const l of lines) L.push(l);
  };

  const decisions = [];
  const todos = [];
  for (const t of topics) {
    for (const d of arr(t.decisions)) if (str(d)) decisions.push(str(d) + '（' + str(t.title) + '）');
    for (const d of arr(t.todos)) if (d && str(d.what)) todos.push(d);
  }
  section('決まったこと', decisions.map((d, i) => i + 1 + '. ' + d));
  section(
    '宿題（誰・いつまで）',
    todos.length ? ['| 誰が | 何を | いつまで |', '|---|---|---|'].concat(todos.map((d) => '| ' + cell(d.who) + ' | ' + cell(d.what) + ' | ' + cell(d.when) + ' |')) : []
  );
  section('まだ答えをもらっていないこと', arr(b.open_questions).map(str).filter(Boolean).map((q) => '- ' + q));
  section(
    '前提と食い違ったこと',
    arr(b.premise_conflicts)
      .filter((k) => k && str(k.heard))
      .map((k) => {
        const label = k.kind === 'decision' ? '前回の決定' : 'こちらの理解';
        const head = str(k.premise) ? label + '「' + str(k.premise) + '」→ ' : '';
        return '- ' + head + (str(k.speaker) ? str(k.speaker) + '「' : '「') + str(k.heard) + '」';
      })
  );
  section(
    '聞くこと・伝えることの結果',
    arr(b.checklist)
      .filter((c) => c && str(c.item))
      .map((c, i) => {
        const st = stateOf(c);
        const verb = c.kind === 'tell' ? '伝える' : '聞く';
        const label = st === 'done' ? (c.kind === 'tell' ? '伝え済み' : '済') : st === 'deferred' ? '持ち帰り' + (str(c.owner) ? '（' + str(c.owner) + '）' : '') : 'まだ';
        return '- [' + (st === 'done' ? 'x' : ' ') + '] ' + (i + 1) + '. ' + verb + '：' + str(c.item) + ' — ' + label + (str(c.evidence) ? ': ' + str(c.evidence) : '');
      })
  );
  const topicLines = [];
  topics.forEach((t, i) => {
    topicLines.push('### ' + (i + 1) + '. ' + (str(t.title) || '（題名なし）') + (str(t.headline) ? ' — ' + str(t.headline) : ''));
    for (const p of arr(t.points)) {
      if (p && str(p.text)) topicLines.push('- ' + (str(p.speaker) ? str(p.speaker) + '：' : '') + str(p.text));
    }
    const ds = arr(t.decisions).map(str).filter(Boolean);
    if (ds.length) topicLines.push('- 決まったこと: ' + ds.join('／'));
    const ns = arr(t.numbers).map(str).filter(Boolean);
    if (ns.length) topicLines.push('- 数字: ' + ns.join('／'));
    topicLines.push('');
  });
  if (topicLines.length && topicLines[topicLines.length - 1] === '') topicLines.pop();
  section('話題ごとの記録', topicLines);
  return L.join('\n') + '\n';
}

/** 会議フォルダの transcript.jsonl から、日時（最初と最後）と字幕に出た名前を取る（本文は使わない） */
function transcriptInfo(jsonlText, selfName) {
  let startedAt = 0;
  let endedAt = 0;
  const speakers = [];
  for (const line of String(jsonlText || '').split('\n')) {
    if (!line.trim()) continue;
    let e;
    try {
      e = JSON.parse(line);
    } catch (_) {
      continue;
    }
    if (typeof e.firstSeen === 'number') {
      if (!startedAt || e.firstSeen < startedAt) startedAt = e.firstSeen;
      const last = typeof e.lastUpdate === 'number' ? e.lastUpdate : e.firstSeen;
      if (last > endedAt) endedAt = last;
    }
    const who = e.speaker === '__SELF__' ? selfName || '自分' : str(e.speaker);
    if (who && speakers.indexOf(who) < 0) speakers.push(who);
  }
  return { startedAt, endedAt, speakers };
}

module.exports = { boardToMarkdown, transcriptInfo };
