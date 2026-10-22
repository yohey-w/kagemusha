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

/**
 * claude の返事（オブジェクト）→ schema 2 のボード。
 *   ctx = { hasNotes, spec（parseNotes の結果）, prev（前のボード。無ければ null） }
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
  const board = {
    topics,
    open_questions: base.board.open_questions,
    checklist,
    cards: base.board.cards.slice(0, MAX_CARDS),
    schema: 2,
  };
  return { ok: true, board };
}

module.exports = { normalizeBoardV2, buildChecklist, buildTopics, stateOf, isNoiseTopic, MAX_CARDS };
