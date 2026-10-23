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
