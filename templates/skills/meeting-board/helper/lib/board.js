'use strict';
// ボードの形（board.json の schema 2）を整え、更新をまたいで安定させる。
// claude が書くのは提案（話題・状態・次の一手など）。ヘルパーがここで、
//   ・話題に id を付けて引き継ぐ（題名は一度出たら変えない・前の話題を消さない）
//   ・聞くことの表を事前メモの文言と順番で固定し、状態（済／一部／持ち帰り／まだ）だけを当てる
//   ・形の崩れた要素を捨てる（何が来ても例外を出さない）
// をする。extract.js の normalizeBoard() はそのまま使い、その結果に上乗せする。

const { normalizeBoard } = require('./extract');

// partial（一部）… 答えの一部だけが出た。0.5 までは open に丸めて「まだ」に見えていた（2026-11-07 の本番）
const STATES = ['open', 'partial', 'deferred', 'done'];
const RANK = { open: 0, partial: 1, deferred: 2, done: 3 };
/** まだ残りがある（次の一手・言い忘れの警告・「あと○つ」の対象） */
function isUnfinished(state) {
  return state === 'open' || state === 'partial';
}
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

/** 状態の言い方を 4 つに寄せる。分からなければ null（前回のまま） */
function stateOf(r) {
  if (!isObj(r)) return null;
  const s = str(r.state).toLowerCase();
  if (/^(done|済|済み|answered|told|伝え済み)$/.test(s)) return 'done';
  if (/^(deferred|持ち帰り|carried|pending)$/.test(s)) return 'deferred';
  if (/^(partial|partially|一部|一部回答|一部済み?|in[ _-]?progress)$/.test(s)) return 'partial';
  if (/^(open|まだ|未|todo)$/.test(s)) return 'open';
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
      // 前回の判定は、id だけでなく本文も同じときだけ引き継ぐ（事前メモを貼り直して番号がずれたとき、別の項目の根拠を付けない）
      const p = prevs.find((x) => x.id === it.id && (!str(x.item) || normText(x.item) === normText(it.text))) || null;
      let state = stateOf(r);
      if (state === null) state = p && STATES.includes(p.state) ? p.state : 'open';
      // 済・持ち帰り・一部は claude の気まぐれでは戻さない（済 → 持ち帰り → 一部 → まだ の向きには動かさない）
      if (p && STATES.includes(p.state) && RANK[p.state] > RANK[state]) state = p.state;
      const todo = todos.find((t) => t.ref === it.id) || null;
      if (isUnfinished(state) && todo) state = 'deferred'; // 宿題に結びついていれば少なくとも持ち帰り
      const owner = state === 'deferred' ? str(r && r.owner) || (todo ? todo.who : '') || (p ? str(p.owner) : '') : '';
      const evidence = str(r && r.evidence) || (p ? str(p.evidence) : '');
      return { id: it.id, kind: it.kind, item: it.text, state, owner, evidence, done: state === 'done' };
    });
  }
  // 事前メモに見出しが無い → 今までどおり claude が事前メモから作った表を使う（状態は 4 つにする）
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
    if (text && !(target && !isUnfinished(target.state))) {
      return { text: clip(text, LINE_MAX), reason: clip(str(rawNext.reason), LINE_MAX), ref, by: 'llm' };
    }
  }
  if (!checklist.length) return null;
  // 事前メモの順で、まだ残りがある最初の項目（まだ・一部）
  const open = checklist.find((c) => isUnfinished(c.state));
  if (open) {
    const no = checklist.indexOf(open) + 1;
    const tell = open.kind === 'tell';
    const part = open.state === 'partial';
    return {
      text: clip((tell ? '伝える：' : '聞く：') + stripEnd(open.item), LINE_MAX),
      reason:
        (part ? (tell ? '一部しか伝えていない' : '答えが一部だけ出た（残りを聞く）') : tell ? 'まだ伝えていない' : 'まだ答えをもらっていない') +
        '（事前メモの ' + no + ' 番目）',
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
      return !(c && !isUnfinished(c.state)); // もう済んだ・持ち帰りになった項目の言い忘れは出さない
    })
    .slice(0, MAX_WARNINGS);
}

/**
 * 前提と食い違ったこと（会議のあとの振り返り・議事録用）。一度出たものは会議の間ずっと残す。
 * 材料は claude の conflicts（確かめ済みも含む）と、premise の警告。同じ前提（ref）は 1 件にまとめ、言い分は新しい方にする
 */
function mergeConflicts(prevList, rawConflicts, warnings, beliefs, now) {
  const beliefIds = new Set((beliefs || []).map((b) => b.id));
  const out = arr(prevList)
    .filter(isObj)
    .map((x) => Object.assign({}, x));
  const incoming = [];
  for (const k of arr(rawConflicts).filter(isObj)) {
    let ref = str(k.ref);
    if (ref && !beliefIds.has(ref)) ref = '';
    const heard = clip(str(k.what || k.heard), 80);
    if (heard) incoming.push({ ref, heard, speaker: str(k.speaker).slice(0, 40), reply: '', settled: k.settled === true });
  }
  for (const w of warnings) {
    if (w.kind === 'premise') incoming.push({ ref: w.ref, heard: w.what, speaker: w.speaker, reply: w.reply, settled: false });
  }
  for (const k of incoming) {
    const same = out.find((x) => (k.ref ? x.ref === k.ref : !x.ref && normText(x.heard) === normText(k.heard)));
    if (same) {
      same.heard = k.heard;
      if (k.speaker) same.speaker = k.speaker;
      if (k.reply) same.reply = k.reply;
      if (k.settled) same.settled = true;
      continue;
    }
    const b = (beliefs || []).find((x) => x.id === k.ref);
    out.push({ ref: k.ref, premise: b ? b.text : '', kind: b ? b.kind : '', heard: k.heard, speaker: k.speaker, reply: k.reply, settled: k.settled, at: now || 0 });
  }
  return out.slice(-MAX_CONFLICTS);
}

/**
 * 台本の「最後に確かめる文」の埋め方の候補（よい順に多くても 3 つ）。形の崩れた候補は捨てる。
 * 返ってこなかった・全部崩れていたときは前回のまま。台本に確かめる文が無ければ []
 */
function normClosing(rawList, prev, hasClosing) {
  if (!hasClosing) return [];
  const list = arr(rawList)
    .filter(isObj)
    .map((x) => ({ text: clip(str(x.text), 200), why: clip(str(x.why), 30) }))
    .filter((x) => x.text)
    .slice(0, 3);
  if (list.length) return list;
  return prev && Array.isArray(prev.closing_candidates) ? prev.closing_candidates : [];
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
    premise_conflicts: c.hasNotes ? mergeConflicts(prev ? prev.premise_conflicts : [], raw.conflicts, warnings, beliefs, c.now) : [],
    users: arr(c.users).map(str).filter(Boolean),
    closing_candidates: normClosing(raw.closing_candidates, prev, !!c.closing),
    schema: 2,
  };
  return { ok: true, board };
}

/**
 * 人が手で直した聞くことの状態（済／一部／持ち帰り／まだ）を当てる。人の操作が claude より勝つ。
 *   overrides = { q1: { state: 'done' | 'partial' | 'deferred' | 'open', owner: '' } }
 * 当てたあと、次の一手と言い忘れの警告を、直した状態に合わせて決め直す。元のボードは変えない（新しいボードを返す）
 */
function applyOverrides(board, overrides, ctx) {
  if (!isObj(board)) return board;
  const ov = isObj(overrides) ? overrides : {};
  const c = ctx || {};
  const checklist = arr(board.checklist).map((item) => {
    const o = ov[item.id];
    const copy = Object.assign({}, item);
    delete copy.byUser;
    if (!isObj(o) || !STATES.includes(o.state)) return copy;
    copy.state = o.state;
    copy.owner = o.state === 'deferred' ? str(o.owner) || str(item.owner) : '';
    copy.done = o.state === 'done';
    copy.byUser = true;
    return copy;
  });
  const beliefs = c.spec && Array.isArray(c.spec.beliefs) ? c.spec.beliefs : [];
  const todos = [];
  for (const t of arr(board.topics)) for (const d of arr(t.todos)) todos.push(d);
  const out = Object.assign({}, board, { checklist });
  // 規則で作った一手は作り直す（直した状態で「最初のまだ」が変わる）。claude の一手は、指す項目がまだ「まだ」なら残す
  const prevNext = board.next_action && board.next_action.by === 'llm' ? board.next_action : null;
  out.next_action = decideNextAction(prevNext, checklist, beliefs, todos);
  out.warnings = arr(board.warnings).filter((w) => {
    if (!w || w.kind !== 'missing') return true;
    const it = checklist.find((x) => x.id === w.ref);
    return !(it && !isUnfinished(it.state));
  });
  return out;
}

/**
 * 事前メモを貼り直したときの id の対応（旧 id → 新 id）。本文が同じもの（聞くこと・伝えることは種類も同じ）だけ。
 * 同じ本文が 2 つあれば、上から順に 1 対 1 で結ぶ
 */
function specIdMap(oldList, newList, sameKind) {
  const map = new Map();
  const used = new Set();
  const news = arr(newList).filter(isObj);
  for (const o of arr(oldList).filter(isObj)) {
    const key = normText(o.text);
    if (!key || !str(o.id)) continue;
    const n = news.find((x) => !used.has(x.id) && normText(x.text) === key && (!sameKind || x.kind === o.kind));
    if (!n) continue;
    used.add(n.id);
    map.set(str(o.id), n.id);
  }
  return map;
}

/**
 * 事前メモを貼り直したとき、前のボードと人が直した状態を新しい事前メモの id に付け替える。
 *   ・本文が同じ項目は、状態・根拠・持ち帰りの人・人が直した状態を引き継ぐ（番号の位置が変わっても付いていく）
 *   ・対応の取れない古い判定は捨てる（新しい項目は「まだ」から。0.5 までは位置の番号で引き継ぎ、別の項目に根拠が付いた）
 *   ・宿題・次の一手・警告・前提と食い違ったことの参照（ref）も付け替える。対応の無い参照は外す（警告と次の一手は捨てる）
 * 戻り値: { board（新しいオブジェクト。元は変えない。board が無ければそのまま）, overrides }
 */
function remapToSpec(board, overrides, oldSpec, newSpec) {
  const os = isObj(oldSpec) ? oldSpec : {};
  const ns = isObj(newSpec) ? newSpec : {};
  const im = specIdMap(os.items, ns.items, true);
  const bm = specIdMap(os.beliefs, ns.beliefs, false);
  const ov = {};
  for (const k of Object.keys(isObj(overrides) ? overrides : {})) if (im.has(k)) ov[im.get(k)] = overrides[k];
  if (!isObj(board)) return { board, overrides: ov };
  // 参照の付け替え: '' → ''（参照なし）、対応あり → 新しい id、対応なし → null
  const oldIds = new Set(arr(os.items).concat(arr(os.beliefs)).filter(isObj).map((x) => str(x.id)));
  const ref = (r) => {
    const v = str(r);
    if (!v) return '';
    if (im.has(v)) return im.get(v);
    if (bm.has(v)) return bm.get(v);
    return oldIds.has(v) ? null : v; // 事前メモ由来でない参照（claude が作った表の c1 など）はそのまま
  };
  const out = Object.assign({}, board);
  const newItems = arr(ns.items).filter(isObj);
  if (newItems.length) {
    const old = arr(board.checklist).filter(isObj);
    out.checklist = newItems.map((it) => {
      const c = old.find((x) => im.get(str(x.id)) === it.id) || null;
      const state = c && STATES.includes(c.state) ? c.state : 'open';
      return {
        id: it.id,
        kind: it.kind,
        item: it.text,
        state,
        owner: c && state === 'deferred' ? str(c.owner) : '',
        evidence: c ? str(c.evidence) : '',
        done: state === 'done',
      };
    });
  } else if (arr(os.items).length) out.checklist = []; // 事前メモから項目が読めなくなった → 次の整理で claude の表に戻る
  out.topics = arr(board.topics).map((t) =>
    isObj(t) ? Object.assign({}, t, { todos: arr(t.todos).map((d) => (isObj(d) ? Object.assign({}, d, { ref: ref(d.ref) || '' }) : d)) }) : t
  );
  if (isObj(board.next_action)) {
    const r = ref(board.next_action.ref);
    out.next_action = r === null ? null : Object.assign({}, board.next_action, { ref: r });
  }
  out.warnings = arr(board.warnings)
    .filter(isObj)
    .map((w) => Object.assign({}, w, { ref: ref(w.ref) }))
    .filter((w) => w.ref !== null);
  out.premise_conflicts = arr(board.premise_conflicts)
    .filter(isObj)
    .map((k) => Object.assign({}, k, { ref: ref(k.ref) || '' }));
  return { board: out, overrides: ov };
}

/**
 * 【前回までの整理】として claude に渡す形。ヘルパーだけが使う欄（by・users・schema など）は渡さない。
 * topics を先頭、各話題は title を先頭にする（JSON の並びは入れた順）
 */
function toPromptBoard(board, opts) {
  if (!isObj(board)) return board;
  const detail = opts && opts.detailIds ? opts.detailIds : null; // 差分のときは、この id の話題だけ中身まで渡す
  const out = {
    topics: arr(board.topics).map((t) =>
      detail && !detail.has(t.id)
        ? { title: t.title, id: t.id, headline: t.headline, current: t.current }
        : {
            title: t.title,
            id: t.id,
            headline: t.headline,
            current: t.current,
            points: t.points,
            decisions: t.decisions,
            todos: t.todos,
            numbers: t.numbers,
          }
    ),
    open_questions: arr(board.open_questions),
    checklist: arr(board.checklist).map((x) => {
      if (!x.kind) return x;
      const o = { id: x.id, state: x.state, owner: x.owner, evidence: x.evidence };
      if (x.byUser) o.by_user = true; // 使う人が手で直した状態（そのまま返してもらう）
      return o;
    }),
  };
  if (board.next_action) out.next_action = { text: board.next_action.text, reason: board.next_action.reason, ref: board.next_action.ref };
  if (Array.isArray(board.warnings)) out.warnings = board.warnings;
  if (typeof board.status === 'string') out.status = board.status;
  if (Array.isArray(board.premise_conflicts)) {
    out.conflicts = board.premise_conflicts.map((k) => ({ ref: k.ref, what: k.heard, speaker: k.speaker, settled: !!k.settled }));
  }
  out.cards = arr(board.cards);
  if (arr(board.closing_candidates).length) out.closing_candidates = board.closing_candidates;
  return out;
}

/** 差分の整理で中身まで渡す話題: いまの話題と、うしろ 2 つ */
function detailTopicIds(board) {
  const topics = arr(board && board.topics);
  const ids = new Set(topics.slice(-2).map((t) => t.id));
  const cur = topics.find((t) => t.current);
  if (cur) ids.add(cur.id);
  return ids;
}

function sameText(a, b) {
  return normText(isObj(a) ? a.text || a.what : a) === normText(isObj(b) ? b.text || b.what : b);
}
function appendNew(list, more) {
  const out = arr(list).slice();
  for (const x of arr(more)) if (!out.some((y) => sameText(x, y))) out.push(x);
  return out;
}

/**
 * 差分の返事（mode: "patch"）を、前回のボードに重ねて「全体を返したときと同じ形」にする（このあと normalizeBoardV2 に通す）。
 *   ・書かれた話題は id で置き換える（中身を省いて渡した話題は、要点・決定・宿題・数字を足す）。id が無い・知らない話題は後ろに足す
 *   ・書かれなかった話題・聞くことの項目は前回のまま
 *   ・open_questions・warnings・cards・next_action・status は、返ってきたものが「いまの全部」
 * 形がおかしければ null（呼び出し側は全体の整理に戻す）
 */
function mergePatch(prev, patch, opts) {
  if (!isObj(prev) || !isObj(patch)) return null;
  if (patch.topics !== undefined && !Array.isArray(patch.topics)) return null;
  if (patch.checklist !== undefined && !Array.isArray(patch.checklist)) return null;
  const compact = opts && opts.compactIds ? opts.compactIds : new Set();
  const topics = arr(prev.topics).map((t) => Object.assign({}, t));
  for (const t of arr(patch.topics).filter(isObj)) {
    const id = str(t.id);
    const i = id ? topics.findIndex((x) => x.id === id) : -1;
    if (i < 0) {
      topics.push(Object.assign({}, t, { id: '' }));
      continue;
    }
    const old = topics[i];
    if (compact.has(id)) {
      topics[i] = Object.assign({}, old, {
        headline: str(t.headline) || old.headline,
        current: t.current === true,
        points: appendNew(old.points, t.points),
        decisions: appendNew(old.decisions, t.decisions),
        todos: appendNew(old.todos, t.todos),
        numbers: appendNew(old.numbers, t.numbers),
      });
    } else {
      // 書かれなかった欄は前回のまま（中身はその話題の分を全部書く約束だが、落としても消さない）
      const fields = {};
      for (const k of Object.keys(t)) if (t[k] !== undefined && t[k] !== null) fields[k] = t[k];
      topics[i] = Object.assign({}, old, fields, { id, title: old.title });
    }
  }
  // いまの話題: current_id があればそれ。無ければ書かれた話題の current。どれも無ければ前回のまま
  const curId = str(patch.current_id);
  const marked = arr(patch.topics).filter(isObj).some((t) => t.current === true);
  if (curId && topics.some((t) => t.id === curId)) topics.forEach((t) => (t.current = t.id === curId));
  else if (marked) {
    const last = topics.map((t, i) => (t.current === true ? i : -1)).filter((i) => i >= 0).pop();
    topics.forEach((t, i) => (t.current = i === last));
  }
  const checklist = arr(prev.checklist).map((c) => {
    const u = arr(patch.checklist).filter(isObj).find((x) => str(x.id) === c.id);
    return u ? Object.assign({ id: c.id, item: c.item }, u) : { id: c.id, item: c.item, state: c.state, owner: c.owner, evidence: c.evidence };
  });
  const pick = (k) => (patch[k] !== undefined ? patch[k] : prev[k]);
  return {
    topics,
    open_questions: pick('open_questions'),
    checklist,
    next_action: patch.next_action !== undefined ? patch.next_action : prev.next_action && prev.next_action.by === 'llm' ? prev.next_action : null,
    warnings: arr(patch.warnings),
    status: pick('status'),
    conflicts: arr(patch.conflicts),
    cards: pick('cards'),
    closing_candidates: patch.closing_candidates,
  };
}

module.exports = {
  mergePatch,
  detailTopicIds,
  normalizeBoardV2,
  applyOverrides,
  remapToSpec,
  specIdMap,
  normClosing,
  toPromptBoard,
  buildChecklist,
  buildTopics,
  decideNextAction,
  normWarnings,
  stateOf,
  isUnfinished,
  isNoiseTopic,
  MAX_CARDS,
};
