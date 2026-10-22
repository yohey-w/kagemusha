'use strict';
// ボードの形（board.json の schema 2）を整え、更新をまたいで安定させる。
// claude が書くのは提案（話題・状態・次の一手など）。ヘルパーがここで、
//   ・話題に id を付けて引き継ぐ（題名は一度出たら変えない・前の話題を消さない）
//   ・聞くことの表を事前メモの文言と順番で固定し、状態（済／持ち帰り／まだ）だけを当てる
//   ・形の崩れた要素を捨てる（何が来ても例外を出さない）
// をする。extract.js の normalizeBoard() はそのまま使い、その結果に上乗せする。

const { normalizeBoard } = require('./extract');

const STATES = ['open', 'deferred', 'done'];
const RANK = { open: 0, deferred: 1, done: 2 };
const MAX_CARDS = 2;
const HEADLINE_MAX = 60;

// あいさつ・接続の確認・自己紹介だけの話題（中身があれば雑音ではない）
const NOISE_TITLE = /(あいさつ|挨拶|自己紹介|音声|聞こえ|接続確認|接続の確認|画面共有の確認|雑談|本日の進め方|会議の進め方)/;

function isObj(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}
function arr(v) {
  return Array.isArray(v) ? v : [];
}
function str(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'object') return '';
  return String(v).replace(/\s+/g, ' ').trim();
}
function clip(s, n) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}
function normText(s) {
  return str(s).replace(/[\s。．.、，,？?！!]/g, '');
}

/** 状態の言い方を 3 つに寄せる。分からなければ null（前回のまま） */
function stateOf(r) {
  if (!isObj(r)) return null;
  const s = str(r.state).toLowerCase();
  if (/^(done|済|済み|answered|told|伝え済み)$/.test(s)) return 'done';
  if (/^(deferred|持ち帰り|carried|pending)$/.test(s)) return 'deferred';
  if (/^(open|まだ|未|todo|partial)$/.test(s)) return 'open';
  if (r.done === true) return 'done'; // 0.1 の形（done だけ）も読む
  if (r.done === false) return 'open';
  return null;
}

function isNoiseTopic(t) {
  if (t.decisions.length || t.todos.length || t.numbers.length) return false;
  return NOISE_TITLE.test(t.title) && t.points.length <= 3;
}

function normTodos(list) {
  return arr(list)
    .map((d) => (isObj(d) ? { who: str(d.who), what: str(d.what), when: str(d.when), ref: str(d.ref) } : { who: '', what: str(d), when: '', ref: '' }))
    .filter((d) => d.what);
}

/** 話題: id を付けて前回から引き継ぐ。前回にあって今回に無い話題は、元の位置に戻す */
function buildTopics(rawTopics, baseTopics, prev) {
  const prevTopics = prev && Array.isArray(prev.topics) ? prev.topics : [];
  const prevById = new Map();
  const prevByTitle = new Map();
  prevTopics.forEach((p, i) => {
    if (p && p.id) prevById.set(p.id, i);
    if (p && p.title && !prevByTitle.has(p.title)) prevByTitle.set(p.title, i);
  });
  let seq = 0;
  for (const p of prevTopics) {
    const m = /^t(\d+)$/.exec((p && p.id) || '');
    if (m) seq = Math.max(seq, Number(m[1]));
  }
  const used = new Set();
  const out = [];
  baseTopics.forEach((b, i) => {
    const r = rawTopics[i] || {};
    let pi = -1;
    const rid = str(r.id);
    if (rid && prevById.has(rid) && !used.has(prevById.get(rid))) pi = prevById.get(rid);
    else if (prevByTitle.has(b.title) && !used.has(prevByTitle.get(b.title))) pi = prevByTitle.get(b.title);
    let id;
    let title = b.title;
    if (pi >= 0) {
      used.add(pi);
      id = prevTopics[pi].id;
      title = prevTopics[pi].title || b.title; // 題名は一度出たら変えない
    } else {
      seq += 1;
      id = 't' + seq;
    }
    out.push({
      title,
      id,
      headline: clip(str(r.headline), HEADLINE_MAX),
      current: b.current,
      points: b.points,
      decisions: b.decisions,
      todos: normTodos(r.todos),
      numbers: b.numbers,
      _prev: pi,
    });
  });
  // 前回にあって今回に無い話題を、前回の並びの位置に戻す（「前の話題を消さない」をヘルパーで守る）
  prevTopics.forEach((p, j) => {
    if (used.has(j) || !isObj(p) || !p.id) return;
    const kept = Object.assign({}, p, { current: false, _prev: j });
    let at = 0;
    for (let k = 0; k < out.length; k++) if (out[k]._prev >= 0 && out[k]._prev < j) at = k + 1;
    out.splice(at, 0, kept);
  });
  return out
    .map((t) => {
      const c = Object.assign({}, t);
      delete c._prev;
      return c;
    })
    .filter((t) => !isNoiseTopic(t));
}

/** 聞くことの表（済／持ち帰り／まだ）。文言と順番は事前メモのまま */
function buildChecklist(spec, rawChecklist, prevList, todos, hasNotes) {
  if (!hasNotes) return [];
  const raws = arr(rawChecklist).filter(isObj);
  const prevs = arr(prevList).filter(isObj);
  const items = spec && Array.isArray(spec.items) ? spec.items : [];
  if (items.length) {
    const byId = new Map();
    const byText = new Map();
    for (const r of raws) {
      if (str(r.id)) byId.set(str(r.id), r);
      if (normText(r.item)) byText.set(normText(r.item), r);
    }
    return items.map((it) => {
      const r = byId.get(it.id) || byText.get(normText(it.text)) || null;
      const p = prevs.find((x) => x.id === it.id) || null;
      let state = stateOf(r);
      if (state === null) state = p && STATES.includes(p.state) ? p.state : 'open';
      // 済・持ち帰りは claude の気まぐれでは戻さない（済 → 持ち帰り → まだ の向きには動かさない）
      if (p && STATES.includes(p.state) && RANK[p.state] > RANK[state]) state = p.state;
      const todo = todos.find((t) => t.ref === it.id) || null;
      if (state === 'open' && todo) state = 'deferred'; // 宿題に結びついていれば少なくとも持ち帰り
      const owner = state === 'deferred' ? str(r && r.owner) || (todo ? todo.who : '') || (p ? str(p.owner) : '') : '';
      const evidence = str(r && r.evidence) || (p ? str(p.evidence) : '');
      return { id: it.id, kind: it.kind, item: it.text, state, owner, evidence, done: state === 'done' };
    });
  }
  // 事前メモに見出しが無い → 今までどおり claude が事前メモから作った表を使う（状態は 3 つにする）
  return raws
    .map((r, i) => {
      const item = str(r.item);
      const p = prevs.find((x) => normText(x.item) === normText(item)) || null;
      let state = stateOf(r) || (p ? p.state : 'open');
      if (p && STATES.includes(p.state) && RANK[p.state] > RANK[state]) state = p.state;
      return {
        id: str(r.id) || 'c' + (i + 1),
        kind: 'ask',
        item,
        state,
        owner: state === 'deferred' ? str(r.owner) : '',
        evidence: str(r.evidence),
        done: state === 'done',
      };
    })
    .filter((c) => c.item);
}

const WARN_KINDS = ['drift', 'premise', 'missing'];
const MAX_WARNINGS = 2;
const MAX_CONFLICTS = 20;
const LINE_MAX = 60;

function stripEnd(s) {
  return s.replace(/[。．.]+$/, '');
}

/**
 * 次の一手。claude の提案が使えればそれ。使えなければ規則で作る（事前メモがあれば空にしない）:
 *   事前メモの順で最初の「まだ」→「聞く：…」/「伝える：…」。全部「済」か「持ち帰り」→ 持ち帰りの読み上げ
 */
function decideNextAction(rawNext, checklist, beliefs, todos) {
  const ids = new Set(checklist.map((c) => c.id).concat((beliefs || []).map((b) => b.id)));
  if (isObj(rawNext)) {
    const text = str(rawNext.text);
    let ref = str(rawNext.ref || (isObj(rawNext.source) ? rawNext.source.ref : ''));
    if (ref && !ids.has(ref)) ref = '';
    const target = checklist.find((c) => c.id === ref);
    // 済んだ・持ち帰りになった項目を指したままの提案は古い（もう言った・聞いた・相手が調べる）ので使わない
    if (text && !(target && target.state !== 'open')) {
      return { text: clip(text, LINE_MAX), reason: clip(str(rawNext.reason), LINE_MAX), ref, by: 'llm' };
    }
  }
  if (!checklist.length) return null;
  const open = checklist.find((c) => c.state === 'open');
  if (open) {
    const no = checklist.indexOf(open) + 1;
    const tell = open.kind === 'tell';
    return {
      text: clip((tell ? '伝える：' : '聞く：') + stripEnd(open.item), LINE_MAX),
      reason: (tell ? 'まだ伝えていない' : 'まだ答えをもらっていない') + '（事前メモの ' + no + ' 番目）',
      ref: open.id,
      by: 'rule',
    };
  }
  return {
    text: '持ち帰りを読み上げて確かめる',
    reason: '聞くこと・伝えることは全部「済」か「持ち帰り」' + (todos.length ? '（持ち帰り ' + todos.length + ' 件）' : ''),
    ref: '',
    by: 'rule',
  };
}

/** 警告（ずれ・前提と違う・言い忘れ）。相手の発言の要点と返す一言がそろったものだけ。多くても 2 つ */
function normWarnings(rawList, checklist, beliefs) {
  const beliefIds = new Set((beliefs || []).map((b) => b.id));
  return arr(rawList)
    .filter(isObj)
    .map((w) => {
      const kind = str(w.kind);
      let ref = str(w.ref);
      if (kind === 'premise' && ref && !beliefIds.has(ref)) ref = ''; // 事前メモに無い前提の id は作り話
      return {
        kind,
        what: clip(str(w.what || w.point || w.heard), 80),
        speaker: str(w.speaker).slice(0, 40),
        reply: clip(str(w.reply), LINE_MAX),
        ref,
      };
    })
    .filter((w) => WARN_KINDS.includes(w.kind) && w.what && w.reply)
    .filter((w) => {
      if (w.kind !== 'missing') return true;
      const c = checklist.find((x) => x.id === w.ref);
      return !(c && c.state !== 'open'); // もう済んだ・持ち帰りになった項目の言い忘れは出さない
    })
    .slice(0, MAX_WARNINGS);
}

/** 前提と食い違ったこと（会議のあとの振り返り・議事録用）。一度出たものは会議の間ずっと残す */
function mergeConflicts(prevList, warnings, beliefs, now) {
  const out = arr(prevList).filter(isObj).slice();
  for (const w of warnings) {
    if (w.kind !== 'premise') continue;
    if (out.some((x) => x.ref === w.ref && x.heard === w.what)) continue;
    const b = (beliefs || []).find((x) => x.id === w.ref);
    out.push({ ref: w.ref, premise: b ? b.text : '', kind: b ? b.kind : '', heard: w.what, speaker: w.speaker, reply: w.reply, at: now || 0 });
  }
  return out.slice(-MAX_CONFLICTS);
}

/**
 * claude の返事（オブジェクト）→ schema 2 のボード。
 *   ctx = { hasNotes, spec（parseNotes の結果）, prev（前のボード。無ければ null）, users（使う人の名前）, now }
 * topics が配列でなければ失敗（呼び出し側は前のボードを残す）。それ以外は何が来ても例外を出さない。
 */
function normalizeBoardV2(raw, ctx) {
  const c = ctx || {};
  const base = normalizeBoard(raw, { hasNotes: !!c.hasNotes });
  if (!base.ok) return base;
  const rawTopics = arr(raw.topics).filter(isObj);
  const prev = isObj(c.prev) ? c.prev : null;
  const topics = buildTopics(rawTopics, base.board.topics, prev);
  const allTodos = [];
  for (const t of topics) for (const d of t.todos) allTodos.push(d);
  const checklist = buildChecklist(c.spec, raw.checklist, prev ? prev.checklist : [], allTodos, !!c.hasNotes);
  const beliefs = c.hasNotes && c.spec && Array.isArray(c.spec.beliefs) ? c.spec.beliefs : [];
  const warnings = c.hasNotes ? normWarnings(raw.warnings, checklist, beliefs) : normWarnings(raw.warnings, [], []).filter((w) => w.kind !== 'missing');
  const board = {
    topics,
    open_questions: base.board.open_questions,
    checklist,
    cards: base.board.cards.slice(0, MAX_CARDS),
    next_action: decideNextAction(raw.next_action, checklist, beliefs, allTodos),
    warnings,
    status: clip(str(raw.status), LINE_MAX),
    premise_conflicts: mergeConflicts(prev ? prev.premise_conflicts : [], warnings, beliefs, c.now),
    users: arr(c.users).map(str).filter(Boolean),
    schema: 2,
  };
  return { ok: true, board };
}

/**
 * 【前回までの整理】として claude に渡す形。ヘルパーだけが使う欄（by・users・schema など）は渡さない。
 * topics を先頭、各話題は title を先頭にする（JSON の並びは入れた順）
 */
function toPromptBoard(board) {
  if (!isObj(board)) return board;
  const out = {
    topics: arr(board.topics).map((t) => ({
      title: t.title,
      id: t.id,
      headline: t.headline,
      current: t.current,
      points: t.points,
      decisions: t.decisions,
      todos: t.todos,
      numbers: t.numbers,
    })),
    open_questions: arr(board.open_questions),
    checklist: arr(board.checklist).map((x) => (x.kind ? { id: x.id, state: x.state, owner: x.owner, evidence: x.evidence } : x)),
  };
  if (board.next_action) out.next_action = { text: board.next_action.text, reason: board.next_action.reason, ref: board.next_action.ref };
  if (Array.isArray(board.warnings)) out.warnings = board.warnings;
  if (typeof board.status === 'string') out.status = board.status;
  out.cards = arr(board.cards);
  return out;
}

module.exports = {
  normalizeBoardV2,
  toPromptBoard,
  buildChecklist,
  buildTopics,
  decideNextAction,
  normWarnings,
  stateOf,
  isNoiseTopic,
  MAX_CARDS,
};
