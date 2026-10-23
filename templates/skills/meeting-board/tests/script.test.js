'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const S = require('./fixtures/support.js');
const { parseScript, locate } = require(path.join(S.HELPER_DIR, 'lib', 'script.js'));
const SCRIPT = fs.readFileSync(path.join(__dirname, 'fixtures', 'sample_script.md'), 'utf8');

test('parseScript: 【m:ss〜 題】と ## 見出しで節に分け、「名前「…」」は台詞・それ以外は覚え書き', () => {
  const s = parseScript(SCRIPT);
  assert.deepEqual(s.map((x) => [x.title, x.startSec, x.lines.length]), [
    ['あいさつと目的', 0, 3],
    ['候補と費用', 60, 3],
    ['切り替えの時期', 150, 3],
    ['まとめ', null, 1],
  ]);
  assert.deepEqual(s[0].lines[0], { kind: 'say', who: '山田', text: '本日はお時間をいただきありがとうございます。勤怠システムの入れ替えの件、始めましょうか' });
  assert.deepEqual(s[0].lines[2], { kind: 'note', text: '相手が目的を言い直したら、そちらに合わせる' });
  assert.equal(s[1].lines[2].kind, 'note');
  assert.deepEqual(parseScript('**【1:02:03〜 長い会議】**\n殿「はい」'), [{ title: '長い会議', startSec: 3723, lines: [{ kind: 'say', who: '殿', text: 'はい' }] }]);
  assert.deepEqual(parseScript('見出しの無い文だけ'), []);
});

const T = 1_000_000;
const cap = (speaker, text, sec) => ({ speaker, text, at: T + sec * 1000 });

test('locate: 直近の字幕と台詞の 2 字組の重なりで、いまの台詞を当てる（自分の発言を重く見る）', () => {
  const s = parseScript(SCRIPT);
  const r = locate(s, [cap('佐々木', 'はい、お願いします', 70), cap('あなた', '予算の上限は年額150万円までです', 80)], 80, null, { me: '山田' });
  assert.deepEqual([r.sectionIndex, r.lineIndex, r.by], [1, 1, 'match']);
  const named = locate(s, [cap('山田', '前回は来年の4月1日に切り替えると決めましたよね', 160)], 160, r, { me: '山田' });
  assert.deepEqual([named.sectionIndex, named.lineIndex], [2, 0]);
});

test('locate: 一致が弱ければ経過時間で節を選ぶ。一致で進んだ位置からは時間で戻さない。強い一致でなければ 1 節より前へ戻らない', () => {
  const s = parseScript(SCRIPT);
  const t = locate(s, [cap('佐々木', 'ところで天気の話ですが', 100)], 100, null, {});
  assert.deepEqual([t.sectionIndex, t.lineIndex, t.by], [1, -1, 'time']);
  const ahead = { sectionIndex: 3, lineIndex: 0, by: 'match', score: 0.8 };
  assert.equal(locate(s, [cap('佐々木', '雑談', 10)], 10, ahead, {}).sectionIndex, 3, '時間では戻さない');
  // 弱い一致（相手の発言だけ）で 2 節前へは戻らない
  const weak = locate(s, [cap('佐々木', '目的は締め作業ですね', 200)], 200, ahead, { me: '山田' });
  assert.equal(weak.sectionIndex, 3);
  // 自分がはっきり言い直したら戻る
  const strong = locate(s, [cap('あなた', '目的は、締め作業を1日以内にすることと、打刻漏れを減らすこと、でよろしいですか', 210)], 210, ahead, {});
  assert.deepEqual([strong.sectionIndex, strong.lineIndex], [0, 1]);
  assert.equal(locate([], [], 0, null, {}).by, 'none');
});

test('--script: /state に台本と位置が出る（--script が無ければ欄ごと出ない）。台本は claude に渡さない', async () => {
  const h = await S.startApp({ fakeClock: true });
  try {
    assert.equal('script' in h.app.stateJson(), false);
  } finally {
    await h.close();
  }
  const { MeetingBoardApp } = require(path.join(S.HELPER_DIR, 'lib', 'app.js'));
  const dir = S.tmpDir();
  try {
    const app = new MeetingBoardApp({ version: 't', dataDir: dir, promptPath: path.join(S.HELPER_DIR, 'prompt.md'), boardHtmlPath: path.join(S.HELPER_DIR, 'board.html'), env: S.stubEnv(), script: SCRIPT, me: '山田' });
    app.ingestCaptions([{ id: 'a', speaker: '__SELF__', text: '予算の上限は年額150万円までです', firstSeen: Date.now(), lastUpdate: Date.now() }]);
    app.tick();
    const st = app.stateJson();
    assert.equal(st.script.sections.length, 4);
    assert.deepEqual([st.script.pos.sectionIndex, st.script.pos.lineIndex, st.script.pos.by], [1, 1, 'match']);
    assert.ok(!app.diagText().includes('予算の上限'), '診断に台本・字幕を入れない');
    app.shutdown();
  } finally {
    S.rmDir(dir);
  }
});

// ── 最後に確かめる文（穴あきの台詞の埋め方の候補） ─────────────────
const { findClosingLine } = require(path.join(S.HELPER_DIR, 'lib', 'script.js'));
const { normalizeBoardV2 } = require(path.join(S.HELPER_DIR, 'lib', 'board.js'));

test('findClosingLine: 穴（〇〇・△△・□□）のある台詞のうち、後ろの節の問いの形のもの。無ければ null', () => {
  const c = findClosingLine(parseScript(SCRIPT));
  assert.deepEqual([c.sectionIndex, c.lineIndex], [3, 0]);
  assert.match(c.text, /〇〇を、△△に、□□までに返せれば成功、ということで合っていますか。$/);
  const two = parseScript('## 前半\n殿「〇〇でよろしいですか」\n## 終わり\n殿「〇〇をお送りします」\n殿「〇〇を△△までに、で合っていますか。」\n殿「ありがとうございました」');
  assert.match(findClosingLine(two).text, /合っていますか/);
  assert.equal(findClosingLine(parseScript('## 前半\n殿「穴のない台詞です」')), null);
});

test('closing_candidates: 形の崩れた候補は捨て、多くても 3 つ。返ってこない・全部崩れていたら前回のまま。確かめる文が無ければ []', () => {
  const ctx = (prev) => ({ hasNotes: false, prev, closing: true });
  const a = normalizeBoardV2({ topics: [], closing_candidates: [null, { why: 'text が無い' }, { text: '見積もりを、山田に、来週水曜までに返せれば成功、ということで合っていますか。', why: '見積もりの話が出た' }, { text: '二' }, { text: '三' }, { text: '四' }] }, ctx(null)).board;
  assert.deepEqual(a.closing_candidates.map((c) => c.text.slice(0, 3)), ['見積も', '二', '三']);
  assert.equal(a.closing_candidates[0].why, '見積もりの話が出た');
  const b = normalizeBoardV2({ topics: [] }, ctx(a)).board;
  assert.deepEqual(b.closing_candidates, a.closing_candidates, '返ってこなければ前回のまま');
  const c = normalizeBoardV2({ topics: [], closing_candidates: 'ただの文字列' }, ctx(a)).board;
  assert.deepEqual(c.closing_candidates, a.closing_candidates, '崩れていたら前回のまま');
  const none = normalizeBoardV2({ topics: [], closing_candidates: [{ text: 'x' }] }, { hasNotes: false, prev: null, closing: false }).board;
  assert.deepEqual(none.closing_candidates, []);
});

test('--script の確かめる文: 【最後に確かめる文】の節で穴あきの 1 文だけを claude に渡し（台本の全体は渡さない）、候補がボードに出る', async () => {
  const { MeetingBoardApp } = require(path.join(S.HELPER_DIR, 'lib', 'app.js'));
  const dir = S.tmpDir();
  const log = path.join(dir, 'stub.log');
  const board = path.join(dir, 'b.json');
  fs.writeFileSync(board, JSON.stringify({ topics: [{ title: '見積もり', current: true, points: [] }], closing_candidates: [{ text: '正式見積もりを、山田に、来週水曜までに返せれば成功、ということで合っていますか。', why: '見積もり依頼が出た' }, { bad: 1 }] }));
  try {
    const app = new MeetingBoardApp({ version: 't', dataDir: dir, promptPath: path.join(S.HELPER_DIR, 'prompt.md'), boardHtmlPath: path.join(S.HELPER_DIR, 'board.html'), env: S.stubEnv({ STUB_LOG: log, STUB_BOARD: board }), script: SCRIPT });
    app.ingestCaptions([{ id: 'a', speaker: '佐々木', text: '正式な見積もりを来週水曜までにお願いします', firstSeen: Date.now(), lastUpdate: Date.now() }]);
    const r = await app.runUpdate('test');
    assert.equal(r.ok, true, r.message);
    const stdin = JSON.parse(fs.readFileSync(log, 'utf8').trim()).stdin;
    assert.match(stdin, /\n【最後に確かめる文】\n最後に、今日伺ったことをまとめさせてください。〇〇を、△△に、□□までに返せれば成功、ということで合っていますか。\n/);
    assert.ok(!stdin.includes('候補はA社とB社の2つに絞っています'), '台本の全体は渡さない');
    const st = app.stateJson();
    assert.equal(st.board.closing_candidates.length, 1);
    assert.equal(st.script.closing.lineIndex, 0);
    app.shutdown();
  } finally {
    S.rmDir(dir);
  }
  // --script が無ければ節ごと渡さない
  const h = await S.startApp({ fakeClock: true });
  try {
    await S.request(h.port, 'POST', '/captions', { headers: S.API, body: { entries: [{ id: 'x', speaker: '佐々木', text: 'はい', firstSeen: Date.now(), lastUpdate: Date.now() }] } });
    await h.app.runUpdate('test');
    assert.ok(!h.calls()[0].stdin.includes('\n【最後に確かめる文】\n'), '節は渡さない（prompt.md の説明の中の語は除く）');
  } finally {
    await h.close();
  }
});

test('台本: 見出しのあとに注記が続く行も節として読む', () => {
  const r = parseScript('**【0:00〜 はじめ】**\n\n山田「よろしくお願いします」\n\n**【14:00〜 ゴールを聞く】**（流れの途中でも、ここで切り替える）\n\n山田「いちばん解決したいのは何ですか」\n');
  const secs = r.sections || r;
  assert.equal(secs.length, 2);
  assert.equal(secs[1].title, 'ゴールを聞く');
  assert.equal(secs[1].startSec, 840);
});
