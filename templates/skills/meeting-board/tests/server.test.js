'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const S = require('./fixtures/support.js');

const SECRET = '秘密の発言ZQX9172を話しました';
const T0 = Date.now();

function cap(id, speaker, text, extra) {
  return Object.assign({ id, speaker, text, firstSeen: T0 + 1000, lastUpdate: T0 + 2000, final: false }, extra || {});
}

async function post(h, p, body, headers) {
  return S.request(h.port, 'POST', p, { headers: headers || S.API, body });
}
async function get(h, p, headers) {
  return S.request(h.port, 'GET', p, { headers: headers || S.API });
}

// ── 入口の札（X-Meeting-Board）と Host ───────────────────────
test('GET / だけは札なしで読める。それ以外は札が無ければ 403 で、何も変わらない', async () => {
  const h = await S.startApp();
  try {
    const home = await S.request(h.port, 'GET', '/');
    assert.equal(home.status, 200);
    assert.match(home.headers['content-type'], /text\/html/);
    assert.match(home.text, /会議ボード/);
    assert.match(home.headers['content-security-policy'], /default-src 'none'/);
    assert.equal(home.headers['access-control-allow-origin'], undefined, '他のサイトへ許可を出さない');

    for (const [method, p, body] of [
      ['GET', '/state'],
      ['GET', '/diag'],
      ['GET', '/notes'],
      ['POST', '/captions', { entries: [cap('x', '山田', 'こっそり')] }],
      ['POST', '/diag', { a: 1 }],
      ['POST', '/notes', { text: 'こっそり' }],
      ['POST', '/settings', { selfName: 'こっそり' }],
      ['POST', '/reset'],
    ]) {
      const r = await S.request(h.port, method, p, { body });
      assert.equal(r.status, 403, method + ' ' + p);
    }
    const wrongValue = await S.request(h.port, 'GET', '/state', { headers: { 'X-Meeting-Board': '0' } });
    assert.equal(wrongValue.status, 403);

    // 札なしの書き込みは反映されていない
    const st = await get(h, '/state');
    assert.equal(st.status, 200);
    assert.deepEqual(st.json.recent, []);
    assert.equal(st.json.notesPresent, false);
    assert.equal(st.json.selfName, '');
  } finally {
    await h.close();
  }
});

test('Host が 127.0.0.1 / localhost 以外なら断る（DNS リバインディング対策）', async () => {
  const h = await S.startApp();
  try {
    assert.equal((await S.request(h.port, 'GET', '/', { host: 'evil.example.com' })).status, 403);
    assert.equal((await S.request(h.port, 'GET', '/state', { headers: S.API, host: 'evil.example.com:' + h.port })).status, 403);
    assert.equal((await S.request(h.port, 'GET', '/state', { headers: S.API, host: 'localhost:' + h.port })).status, 200);
    assert.equal((await S.request(h.port, 'GET', '/state', { headers: S.API })).status, 200);
  } finally {
    await h.close();
  }
});

test('サーバーは 127.0.0.1 だけで待ち受ける', async () => {
  const h = await S.startApp();
  try {
    assert.equal(h.server.address().address, '127.0.0.1');
  } finally {
    await h.close();
  }
});

test('知らない道・違うメソッド・壊れた本文・大きすぎる本文', async () => {
  const h = await S.startApp();
  try {
    assert.equal((await get(h, '/nope')).status, 404);
    assert.equal((await S.request(h.port, 'POST', '/state', { headers: S.API, body: {} })).status, 405);
    assert.equal((await S.request(h.port, 'GET', '/captions', { headers: S.API })).status, 405);
    const bad = await S.request(h.port, 'POST', '/captions', { headers: S.API, body: '{ これは JSON ではない' });
    assert.equal(bad.status, 400);
    const big = await S.request(h.port, 'POST', '/notes', { headers: S.API, body: JSON.stringify({ text: 'あ'.repeat(1_200_000) }) });
    assert.equal(big.status, 413);
  } finally {
    await h.close();
  }
});

// ── 字幕の取り込みと状態 ────────────────────────────────────
test('POST /captions は id で上書きする。__SELF__ は表示名で出る', async () => {
  const h = await S.startApp();
  try {
    let r = await post(h, '/captions', { entries: [cap('a', '山田', 'こんにちは'), cap('b', '__SELF__', 'よろしくお願いします')] });
    assert.equal(r.status, 200);
    assert.equal(r.json.accepted, 2);
    r = await post(h, '/captions', { entries: [cap('a', '山田', 'こんにちは、山田です', { lastUpdate: T0 + 3000 })] });
    assert.equal(r.json.accepted, 1);

    let st = (await get(h, '/state')).json;
    assert.deepEqual(
      st.recent.map((x) => [x.speaker, x.text]),
      [
        ['山田', 'こんにちは、山田です'],
        ['自分', 'よろしくお願いします'],
      ]
    );
    assert.deepEqual(Object.keys(st).sort(), ['board', 'notesPresent', 'recent', 'selfName', 'status']);
    assert.equal(st.board, null);

    r = await post(h, '/settings', { selfName: '渡辺' });
    assert.equal(r.json.selfName, '渡辺');
    st = (await get(h, '/state')).json;
    assert.equal(st.selfName, '渡辺');
    assert.equal(st.recent[1].speaker, '渡辺');
    assert.equal(JSON.parse(fs.readFileSync(path.join(h.dataDir, 'settings.json'), 'utf8')).selfName, '渡辺');

    // 発言は会議フォルダに保存される（生の __SELF__ のまま）
    h.app.persist(true);
    const dirs = fs.readdirSync(h.dataDir).filter((d) => /^\d{4}-\d{2}-\d{2}_\d{6}/.test(d));
    assert.equal(dirs.length, 1);
    const lines = fs.readFileSync(path.join(h.dataDir, dirs[0], 'transcript.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
    assert.equal(lines.length, 2);
    assert.ok(lines.some((l) => l.speaker === '__SELF__'));
  } finally {
    await h.close();
  }
});

test('字幕の状態: 拡張機能が「通話中なのに字幕の領域が無い」と言えば missing、届けば receiving', async () => {
  const h = await S.startApp();
  try {
    assert.equal((await get(h, '/state')).json.status.captions.state, 'waiting');
    await post(h, '/captions', { entries: [], status: { inCall: true, regionFound: false, captionsOff: false } });
    assert.equal((await get(h, '/state')).json.status.captions.state, 'missing');
    await post(h, '/captions', { entries: [cap('a', '山田', '届きました')], status: { inCall: true, regionFound: true } });
    const st = (await get(h, '/state')).json.status.captions;
    assert.equal(st.state, 'receiving');
    assert.equal(st.entries, 1);
  } finally {
    await h.close();
  }
});

test('事前メモ: 保存・読み戻し・会議フォルダの notes.md', async () => {
  const h = await S.startApp();
  try {
    assert.equal((await get(h, '/state')).json.notesPresent, false);
    const r = await post(h, '/notes', { text: '## 聞くこと\n- 月額' });
    assert.equal(r.json.notesPresent, true);
    assert.equal((await get(h, '/notes')).json.text, '## 聞くこと\n- 月額');
    assert.equal((await get(h, '/state')).json.notesPresent, true);
    const dir = fs.readdirSync(h.dataDir).find((d) => /^\d{4}-/.test(d));
    assert.equal(fs.readFileSync(path.join(h.dataDir, dir, 'notes.md'), 'utf8'), '## 聞くこと\n- 月額');
  } finally {
    await h.close();
  }
});

test('新しい会議: 前の記録はフォルダに残り、ボードは空になり、前の会議の字幕の再送は取り込まない', async () => {
  const h = await S.startApp();
  try {
    await post(h, '/captions', { entries: [cap('a', '山田', '前の会議の発言です', { firstSeen: Date.now() - 5000, lastUpdate: Date.now() - 5000 })] });
    await post(h, '/notes', { text: '前の会議のメモ' });
    h.app.persist(true);
    const before = fs.readdirSync(h.dataDir).filter((d) => /^\d{4}-/.test(d));
    assert.equal(before.length, 1);
    const oldTranscript = path.join(h.dataDir, before[0], 'transcript.jsonl');
    assert.match(fs.readFileSync(oldTranscript, 'utf8'), /前の会議の発言です/);

    await S.sleep(1100); // 会議フォルダ名は秒単位
    assert.equal((await post(h, '/reset')).status, 200);

    const after = fs.readdirSync(h.dataDir).filter((d) => /^\d{4}-/.test(d));
    assert.equal(after.length, 2, '前の会議のフォルダが残り、新しいフォルダができる');
    assert.match(fs.readFileSync(oldTranscript, 'utf8'), /前の会議の発言です/);
    const st = (await get(h, '/state')).json;
    assert.deepEqual(st.recent, []);
    assert.equal(st.board, null);
    assert.equal(st.notesPresent, false);

    // 画面に残っていた前の会議のブロックが再送されても取り込まない
    const stale = await post(h, '/captions', { entries: [cap('a', '山田', '前の会議の発言です。続き', { firstSeen: Date.now() - 5000, lastUpdate: Date.now() })] });
    assert.equal(stale.json.accepted, 0);
    const fresh = await post(h, '/captions', { entries: [cap('z', '山田', '新しい会議の発言', { firstSeen: Date.now(), lastUpdate: Date.now() })] });
    assert.equal(fresh.json.accepted, 1);
  } finally {
    await h.close();
  }
});

// ── 診断に字幕の中身を入れない ──────────────────────────────
test('GET /diag は字幕の本文・話者名を含まない。拡張機能の診断に混ざった本文も伏せる', async () => {
  const h = await S.startApp({ env: { STUB_MODE: 'garbage' } });
  try {
    await post(h, '/captions', { entries: [cap('a', '山田太郎', SECRET)], status: { inCall: true, regionFound: true } });
    await post(h, '/notes', { text: '事前メモの本文です。取り扱い注意の記述' });
    // 拡張機能が万一、本文を混ぜて送ってきても出さない
    await post(h, '/diag', {
      v: 1,
      regionFound: true,
      selector: 'aria-label',
      tree: [{ t: 'div', c: 'abc', n: 2, tl: 40 }],
      oops: '誤送信: ' + SECRET,
      notesOops: '取り扱い注意の記述 を含む',
    });
    // 失敗を 1 つ作る（エラー欄にも本文が出ないこと）
    await h.app.runUpdate('test');
    const d = await get(h, '/diag');
    assert.equal(d.status, 200);
    assert.match(d.headers['content-type'], /text\/plain/);
    const text = d.text;
    assert.ok(!text.includes('ZQX9172'), '字幕の本文が診断に入っている');
    assert.ok(!text.includes('山田太郎'), '話者名が診断に入っている');
    assert.ok(!text.includes('取り扱い注意'), '事前メモが診断に入っている');
    assert.match(text, /会議ボード 診断/);
    assert.match(text, /Node v?\d+/);
    assert.match(text, /claude/);
    assert.match(text, /発言 1 件/);
    assert.match(text, /regionFound/);
    assert.match(text, /bad-json/);
    assert.ok(!text.includes(os.homedir()), 'ホームフォルダのパス（ユーザー名つき）を出さない');
  } finally {
    await h.close();
  }
});

// ── 整理（偽 claude） ───────────────────────────────────────
function lines(n, prefix) {
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push(cap(prefix + i, i % 2 ? '佐々木' : '山田', 'これは試験用の発言です。' + String(i).padStart(3, '0') + 'あいうえおかきくけこ', { firstSeen: T0 + i * 1000 }));
  }
  return out;
}

test('整理: しきい値を満たすと偽 claude に渡り、ボードが出て保存される（渡る入力の形も確かめる）', async () => {
  const h = await S.startApp({ fakeClock: true, notes: '## 聞くこと\n- 月額はいくらか' });
  try {
    await post(h, '/captions', { entries: lines(8, 'a') }); // 1 行 30 字ほど × 8 = 120 字超
    assert.ok(h.app.pendingChars() >= 120, 'しきい値: ' + h.app.pendingChars());

    h.clock.t += 5000;
    h.app.tick();
    assert.equal(h.calls().length, 0, '前回の終わりから 20 秒たつまで動かない');

    h.clock.t += 20000;
    h.app.tick();
    await S.waitFor(() => h.app.updateCount === 1, 15000);

    const calls = h.calls();
    assert.equal(calls.length, 1);
    const input = calls[0].stdin;
    const sections = ['【事前メモ】', '【前回までの整理】', '【字幕の範囲】', '【字幕】'].map((s) => input.indexOf('\n' + s + '\n'));
    assert.ok(sections.every((i) => i > 0), '4 つの節: ' + sections);
    assert.deepEqual(sections.slice().sort((a, b) => a - b), sections);
    assert.ok(input.includes('【事前メモ】\n## 聞くこと\n- 月額はいくらか'));
    assert.ok(input.includes('【前回までの整理】\nなし'));
    assert.ok(input.includes('【字幕の範囲】\n全部'));
    assert.match(input, /\[\d\d:\d\d\] 山田：これは試験用の発言です。000/);
    assert.match(input, /\[\d\d:\d\d\] 佐々木：これは試験用の発言です。001/);
    assert.ok(input.startsWith(fs.readFileSync(path.join(S.HELPER_DIR, 'prompt.md'), 'utf8').replace(/\s+$/, '')), 'prompt.md をそのまま使う');
    assert.ok(calls[0].argv.includes('--safe-mode'));

    const st = (await get(h, '/state')).json;
    assert.equal(st.status.update.count, 1);
    assert.equal(st.board.topics[0].title, '勤怠システムの入れ替え');
    assert.equal(st.board.checklist.length, 1, '事前メモがあるので聞くことの表が残る');
    assert.equal(st.board.cards.length, 1);
    assert.equal(st.status.lastError, null);
    assert.equal(st.status.update.pendingChars, 0);

    const dir = fs.readdirSync(h.dataDir).find((d) => /^\d{4}-/.test(d));
    const saved = JSON.parse(fs.readFileSync(path.join(h.dataDir, dir, 'board.json'), 'utf8'));
    assert.equal(saved.topics[0].title, '勤怠システムの入れ替え');
  } finally {
    await h.close();
  }
});

test('整理: 2 回目は前回のボードを渡す。事前メモが無ければ聞くことの表とカードは空', async () => {
  const h = await S.startApp({ fakeClock: true });
  try {
    await post(h, '/captions', { entries: lines(8, 'a') });
    h.clock.t += 30000;
    await h.app.runUpdate('test');
    assert.equal(h.app.updateCount, 1);
    const st = (await get(h, '/state')).json;
    assert.deepEqual(st.board.checklist, []);
    assert.deepEqual(st.board.cards, []);

    await post(h, '/captions', { entries: lines(4, 'b') });
    h.clock.t += 30000;
    await h.app.runUpdate('test');
    const calls = h.calls();
    assert.equal(calls.length, 2);
    assert.ok(calls[1].stdin.includes('【前回までの整理】\n{"topics":[{"title":"勤怠システムの入れ替え"'), '前回のボードが入っている');
  } finally {
    await h.close();
  }
});

test('整理: 失敗したら前のボードを残してエラーを出し、間をあけてやり直す', async () => {
  const h = await S.startApp({ fakeClock: true });
  try {
    await post(h, '/captions', { entries: lines(8, 'a') });
    h.clock.t += 30000;
    assert.equal((await h.app.runUpdate('test')).ok, true);

    h.app.env.STUB_MODE = 'garbage';
    await post(h, '/captions', { entries: lines(8, 'b') });
    h.clock.t += 30000;
    const r = await h.app.runUpdate('test');
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'bad-json');
    let st = (await get(h, '/state')).json;
    assert.equal(st.board.topics[0].title, '勤怠システムの入れ替え', '前のボードを残す');
    assert.equal(st.status.lastError.kind, 'bad-json');
    assert.match(st.status.lastError.message, /JSON/);
    assert.ok(h.app.pendingChars() > 0, '失敗した分は次回に回る');

    // すぐには再開しない（待ち時間あり）
    h.app.tick();
    await S.sleep(100);
    assert.equal(h.calls().length, 2);

    // 待ったあとにうまくいけばエラーは消える
    h.app.env.STUB_MODE = 'ok';
    h.clock.t += 400000;
    assert.equal((await h.app.runUpdate('test')).ok, true);
    st = (await get(h, '/state')).json;
    assert.equal(st.status.lastError, null);
  } finally {
    await h.close();
  }
});

test('整理: 使用上限は上限として知らせ、5 分は呼び直さない', async () => {
  const h = await S.startApp({ fakeClock: true, env: { STUB_MODE: 'limit-json' } });
  try {
    await post(h, '/captions', { entries: lines(8, 'a') });
    h.clock.t += 30000;
    const r = await h.app.runUpdate('test');
    assert.equal(r.kind, 'usage-limit');
    const st = (await get(h, '/state')).json;
    assert.match(st.status.lastError.message, /利用上限/);
    h.clock.t += 120000;
    h.app.tick();
    await S.sleep(100);
    assert.equal(h.calls().length, 1, '2 分後はまだ呼ばない');
    h.clock.t += 200000;
    h.app.env.STUB_MODE = 'ok';
    h.app.tick();
    await S.waitFor(() => h.app.updateCount === 1, 15000);
  } finally {
    await h.close();
  }
});

test('整理: 長い発言が書き換わって行が減っても止まらない（0.1 の「内部エラー: reading \'text\'」で以後ずっと止まった件）', async () => {
  const h = await S.startApp({ fakeClock: true });
  try {
    // 前半: 100 字 × 130 発言（1 万 3 千字。窓は「前回より後だけ」になる）、後半: 1 人の長い発言（600 字ごとに分かれて何行にもなる）
    const many = [];
    for (let i = 0; i < 130; i++) many.push(cap('m' + i, '佐々木', String(i).padStart(3, '0') + 'い'.repeat(97), { firstSeen: T0 + i * 1000 }));
    const longText = 'これは長い発言の一文です。'.repeat(1000).slice(0, 12000);
    await post(h, '/captions', { entries: many.concat([cap('long', '山田', longText, { firstSeen: T0 + 200000, lastUpdate: T0 + 200000 })]) });
    h.clock.t += 30000;
    assert.equal((await h.app.runUpdate('test')).ok, true);
    const before = h.app.lastLineCount;
    assert.ok(before > 140, '長い発言が何行にもなっている: ' + before);

    // 同じ発言（同じ id）が短く書き換わった → 行の数が前回より減る
    await post(h, '/captions', { entries: [cap('long', '山田', '言い直して短くなりました。', { firstSeen: T0 + 200000, lastUpdate: T0 + 300000 })] });
    h.clock.t += 30000;
    const r = await h.app.runUpdate('test');
    assert.equal(r.ok, true, r.message);
    assert.equal(h.app.inFlight, false);
    assert.ok(h.app.lastLineCount < before);
    assert.equal(h.app.updateCount, 2);
    assert.match(h.calls()[1].stdin, /言い直して短くなりました。/);
  } finally {
    await h.close();
  }
});

test('整理: 途中で例外が出ても「整理中」のまま固まらず、黒い画面に（本文を伏せて）出し、間をあけて次の回にやり直す', async () => {
  const h = await S.startApp({ fakeClock: true });
  const warned = [];
  h.app.warn = (m) => warned.push(m);
  try {
    await post(h, '/captions', { entries: lines(8, 'a').concat([cap('s', '山田', SECRET)]) });
    const realLines = h.app.transcript.lines.bind(h.app.transcript);
    h.app.transcript.lines = () => {
      throw new Error('試験の例外: ' + SECRET);
    };
    h.clock.t += 30000;
    const r = await h.app.runUpdate('test');
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'internal');
    assert.equal(h.app.inFlight, false, '整理中のまま固まらない');
    assert.equal(warned.length, 1);
    assert.match(warned[0], /整理のエラー \[internal\]/);
    assert.ok(!warned.join('\n').includes('ZQX9172'), '黒い画面に字幕の本文を出さない');

    // 直したら、待ち時間のあとの tick で自動でやり直して更新される
    h.app.transcript.lines = realLines;
    h.clock.t += 1000;
    h.app.tick();
    await S.sleep(100);
    assert.equal(h.calls().length, 0, '失敗の直後は呼ばない');
    h.clock.t += 60000;
    h.app.tick();
    await S.waitFor(() => h.app.updateCount === 1, 15000);
    assert.equal((await get(h, '/state')).json.status.lastError, null);
  } finally {
    await h.close();
  }
});

test('整理: claude の返事の要素が欠けていても（text の無い要点・オブジェクトでない話題）落ちず、次の回も更新される', async () => {
  const h = await S.startApp({ fakeClock: true, notes: '## 聞くこと\n- 月額はいくらか' });
  const bad = path.join(h.dataDir, 'bad.json');
  const good = path.join(h.dataDir, 'good.json');
  fs.writeFileSync(bad, JSON.stringify({
    topics: [null, 'ただの文字列', { title: '費用', current: true, points: [{ speaker: '佐々木' }, null, { text: '月額は400円です', speaker: '佐々木' }], todos: [{ who: '山田' }, null], decisions: [null, 1] }],
    open_questions: [null, { q: 'x' }],
    checklist: [null, { evidence: 'item が無い' }, { item: '月額はいくらか', done: 'はい' }],
    cards: [null, {}],
    next_action: 'ただの文字列',
    warnings: [{ heard: '' }, null],
  }));
  fs.writeFileSync(good, JSON.stringify({ topics: [{ title: '費用の続き', current: true, points: [{ speaker: '佐々木', text: '初期費用は30万円です' }] }] }));
  try {
    await post(h, '/captions', { entries: lines(8, 'a') });
    h.app.env.STUB_BOARD = bad;
    h.clock.t += 30000;
    const r1 = await h.app.runUpdate('test');
    assert.equal(r1.ok, true, r1.message);
    const t = r1.board.topics.find((x) => x.title === '費用');
    assert.deepEqual(t.points.map((p) => p.text), ['月額は400円です'], 'text の無い要点は捨てる');

    h.app.env.STUB_BOARD = good;
    await post(h, '/captions', { entries: lines(8, 'b') });
    h.clock.t += 30000;
    const r2 = await h.app.runUpdate('test');
    assert.equal(r2.ok, true, r2.message);
    assert.equal(h.app.updateCount, 2, '次の回も更新される');
    assert.ok(r2.board.topics.some((x) => x.title === '費用の続き'));
  } finally {
    await h.close();
  }
});

test('整理: 話者が替わらない長い発言（final:false のまま）も整理に渡り、6 秒伸びなければ確定になる', async () => {
  const h = await S.startApp({ fakeClock: true });
  try {
    const long = 'まだ話し続けています。' + 'これは長い独り語りの一部です。'.repeat(12);
    await post(h, '/captions', { entries: [cap('solo', '山田', long, { final: false })] });
    h.clock.t += 3000;
    h.app.tick();
    assert.equal((await get(h, '/state')).json.recent[0].final, false, '3 秒ではまだ確定にしない');
    h.clock.t += 4000;
    h.app.tick();
    assert.equal((await get(h, '/state')).json.recent[0].final, true, '6 秒伸びなければ確定');

    h.clock.t += 20000;
    h.app.tick();
    await S.waitFor(() => h.app.updateCount === 1, 15000);
    assert.match(h.calls()[0].stdin, /山田：まだ話し続けています。/, '確定を待たずに整理へ渡る');

    // 同じ長さのまま言い直された（字数は増えない）→ 間隔が来れば整理し直す
    const revised = long.replace('まだ', 'いま');
    assert.equal(revised.length, long.length);
    await post(h, '/captions', { entries: [cap('solo', '山田', revised, { final: false, lastUpdate: T0 + 90000 })] });
    assert.equal(h.app.pendingChars(), 0);
    h.clock.t += 61000;
    h.app.tick();
    await S.waitFor(() => h.app.updateCount === 2, 15000);
    assert.match(h.calls()[1].stdin, /山田：いま話し続けています。/);
  } finally {
    await h.close();
  }
});

test('整理: claude の所要時間と費用（数字だけ）を状態・診断・updates.jsonl に残す（本文は入れない）', async () => {
  const h = await S.startApp({ fakeClock: true, env: { STUB_COST_USD: '0.02' } });
  try {
    await post(h, '/captions', { entries: lines(8, 'a').concat([cap('s', '山田', SECRET)]) });
    h.clock.t += 30000;
    assert.equal((await h.app.runUpdate('test')).ok, true);
    await post(h, '/captions', { entries: lines(4, 'b') });
    h.clock.t += 30000;
    assert.equal((await h.app.runUpdate('test')).ok, true);
    const u = (await get(h, '/state')).json.status.update;
    assert.equal(u.lastClaudeMs, 4321);
    assert.equal(u.lastCostUsd, 0.02);
    assert.equal(u.totalCostUsd, 0.04);
    const diag = (await get(h, '/diag')).text;
    assert.match(diag, /費用: 直近 \$0\.0200・この会議の合計 \$0\.0400/);
    const dir = fs.readdirSync(h.dataDir).find((d) => /^\d{4}-/.test(d));
    const rows = fs.readFileSync(path.join(h.dataDir, dir, 'updates.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
    assert.equal(rows.length, 2);
    assert.deepEqual(Object.keys(rows[0]).sort(), ['at', 'claudeMs', 'costUsd', 'inChars', 'kind', 'ms', 'ok', 'outChars', 'range', 'reason']);
    assert.equal(rows[0].ok, true);
    assert.equal(rows[0].costUsd, 0.02);
    assert.ok(rows[0].inChars > 0 && rows[0].outChars > 0);
    const raw = fs.readFileSync(path.join(h.dataDir, dir, 'updates.jsonl'), 'utf8');
    assert.ok(!raw.includes('ZQX9172') && !raw.includes('山田'), '本文・名前は入れない');
  } finally {
    await h.close();
  }
});

test('整理: 同時に 2 つは走らせない', async () => {
  const h = await S.startApp({ fakeClock: true, env: { STUB_DELAY_MS: '500' } });
  try {
    await post(h, '/captions', { entries: lines(4, 'a') });
    const p1 = h.app.runUpdate('test');
    const second = await h.app.runUpdate('test');
    assert.equal(second.kind, 'busy');
    assert.equal((await p1).ok, true);
    assert.equal(h.calls().length, 1);
  } finally {
    await h.close();
  }
});

test('整理: 呼び出しの最中に「新しい会議」が押されたら結果を捨てる', async () => {
  const h = await S.startApp({ fakeClock: true, env: { STUB_DELAY_MS: '600' } });
  try {
    await post(h, '/captions', { entries: lines(4, 'a') });
    const p = h.app.runUpdate('test');
    await S.sleep(100);
    h.app.reset();
    const r = await p;
    assert.equal(r.kind, 'stale');
    assert.equal(h.app.board, null);
    assert.equal(h.app.updateCount, 0);
  } finally {
    await h.close();
  }
});

test('整理: 字幕が無ければ claude を呼ばない', async () => {
  const h = await S.startApp({ fakeClock: true });
  try {
    h.clock.t += 600000;
    h.app.tick();
    await S.sleep(100);
    assert.equal(h.calls().length, 0);
    assert.equal((await h.app.runUpdate('test')).kind, 'empty');
  } finally {
    await h.close();
  }
});

test('起動時の点検: Node と claude の場所が日本語の欄に出る', async () => {
  const h = await S.startApp();
  try {
    const checks = await h.app.runSelfCheck({ listenInfo: { name: 'ポート', ok: true, detail: h.port + ' 番' }, withVersion: true });
    const byName = Object.fromEntries(checks.map((c) => [c.name, c]));
    assert.equal(byName['Node.js'].ok, true);
    assert.equal(byName['claude の場所'].ok, true);
    assert.equal(byName['claude の版'].detail, '9.9.9 (Stub Code)');
    assert.equal(byName['ポート'].ok, true);
    const st = (await get(h, '/state')).json;
    assert.equal(st.status.selfCheck.length, 4);
    assert.equal(st.status.claude.version, '9.9.9 (Stub Code)');
  } finally {
    await h.close();
  }
});

test('診断: 拡張機能の木（領域の下 4 段）は、いちばん下の段まで切り捨てずに残る', async () => {
  const h = await S.startApp();
  try {
    // 領域 → 入れ物 → ブロック → 話者/本文 → 葉、の 5 段（k の配列で 4 回入れ子になる）
    const leaf = { t: 'span', c: 'leaf', n: 0, tl: 4, ln: 1, d: 'inline' };
    const tree = { t: 'div', c: 'vNKgIf', n: 2, k: [{ t: 'div', c: '', n: 1, k: [{ t: 'div', c: 'blk', n: 2, k: [{ t: 'div', c: 'tx', n: 3, k: [leaf] }] }] }] };
    await post(h, '/diag', { v: 1, tree });
    const text = (await get(h, '/diag')).text;
    assert.match(text, /"c": "leaf"/, '最下段の葉が残っている');
    assert.doesNotMatch(text, /null/, '深さの上限で null に置き換わっていない');
    // 長い文字列は切り詰める（本文の混入を防ぐ最後の砦）が、User-Agent（Edge の印を含む長さ）は残る
    const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.7727.15 Safari/537.36 Edg/147.0.3912.60';
    await post(h, '/diag', { v: 1, ua });
    assert.ok((await get(h, '/diag')).text.includes('Edg/147.0.3912.60'));
  } finally {
    await h.close();
  }
});
