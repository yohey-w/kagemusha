// 拡張機能の E2E（node --test には含めない: Playwright が要るため）。
//
// Playwright の Chromium に未パッケージの拡張を読み込み、Meet のなりすましページ（meet_fixture.html。
// 現行の Meet の字幕の領域を写したもの）の字幕を、本物のヘルパーが受け取れるかを確かめる。
// 本物の claude は呼ばない（CLAUDE_BIN は tests/fixtures/claude_stub.js）。
//
//   実行: PLAYWRIGHT_MODULE=<playwright のフォルダ> node tests/e2e/run_e2e.js
//         （PLAYWRIGHT_MODULE を省くと、普通に require('playwright') する。ブラウザは
//          `npx playwright install chromium` で入れておく。ポート 47431 が空いていること）
//   結果を残したいとき: E2E_OUT=<フォルダ> を付けると、診断のサンプルと通過項目をそこへ書く。
//
// 確かめるのは、拡張機能のロジック（領域の探し方・ブロックの読み取り・結合・確定・診断・バッジ・字幕オン）。
// 話者ブロックの中の実際の構造は、現行の Meet で確かめきれていない部分があり、このなりすましは
// 公開されている字幕保存拡張の読み方と、領域の構造の実機の確認をもとに作った推定である。
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('assert/strict');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const WT = path.join(__dirname, '..', '..');
const EXT = path.join(WT, 'extension');
const SERVER = path.join(WT, 'helper', 'server.js');
const STUB = path.join(WT, 'tests', 'fixtures', 'claude_stub.js');
const FIXTURE = fs.readFileSync(path.join(__dirname, 'meet_fixture.html'), 'utf8');
const OUT = process.env.E2E_OUT || null;
if (OUT) fs.mkdirSync(OUT, { recursive: true });
const PORT = 47431;
const MEET = 'https://meet.google.com/abc-defg-hij';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

function request(method, p, body) {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? null : JSON.stringify(body);
    const headers = { 'X-Meeting-Board': '1' };
    if (payload) { headers['Content-Type'] = 'application/json'; headers['Content-Length'] = Buffer.byteLength(payload); }
    const req = http.request({ host: '127.0.0.1', port: PORT, method, path: p, headers }, (res) => {
      let d = '';
      res.setEncoding('utf8');
      res.on('data', (c) => (d += c));
      res.on('end', () => { let j = null; try { j = JSON.parse(d); } catch (_) {} resolve({ status: res.statusCode, text: d, json: j }); });
    });
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}
const state = async () => (await request('GET', '/state')).json;

async function waitFor(fn, label, timeoutMs = 12000) {
  const end = Date.now() + timeoutMs;
  let last;
  while (Date.now() < end) {
    try { last = await fn(); if (last) return last; } catch (_) {}
    await sleep(200);
  }
  throw new Error('時間切れ: ' + label + ' / 最後の値: ' + JSON.stringify(last));
}
const waitRecent = (pred, label) => waitFor(async () => { const s = await state(); return pred(s.recent, s) ? s : null; }, label);

let helper = null;
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'mb-e2e-data-'));
async function startHelper() {
  helper = spawn(process.execPath, [SERVER, '--port', String(PORT), '--interval', '3600', '--data-dir', dataDir], {
    env: Object.assign({}, process.env, { CLAUDE_BIN: STUB, STUB_LOG: path.join(dataDir, 'stub.log') }),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let out = '';
  helper.stdout.on('data', (d) => (out += d));
  helper.stderr.on('data', (d) => (out += d));
  await waitFor(() => /ボード: http/.test(out), 'ヘルパーの起動', 15000);
}
async function stopHelper() {
  if (!helper) return;
  const h = helper; helper = null;
  h.kill('SIGTERM');
  await new Promise((r) => h.on('close', r));
}

async function main() {
  const results = [];
  const ok = (name) => { results.push(name); log('OK  ' + name); };

  await startHelper();
  ok('ヘルパー起動（127.0.0.1:' + PORT + '）');

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'mb-e2e-profile-'));
  const ctx = await chromium.launchPersistentContext(profile, {
    channel: 'chromium',
    headless: true,
    viewport: { width: 1000, height: 700 },
    args: ['--disable-extensions-except=' + EXT, '--load-extension=' + EXT],
  });
  let sw = ctx.serviceWorkers()[0] || (await ctx.waitForEvent('serviceworker', { timeout: 15000 }));
  await ctx.route('https://meet.google.com/**', (route) => route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: FIXTURE }));

  const tabIds = () => sw.evaluate(async () => (await chrome.tabs.query({})).map((t) => t.id));
  const badgeOf = async () => {
    const ids = await tabIds();
    return sw.evaluate(async (ids) => {
      const out = {};
      for (const id of ids) out[id] = await chrome.action.getBadgeText({ tabId: id });
      out.global = await chrome.action.getBadgeText({});
      return out;
    }, ids);
  };

  // ── 3 通りの DOM 形で、同じ筋書きを流す ─────────────────────
  for (const variant of ['class', 'generic', 'multiline']) {
    log('--- variant: ' + variant);
    await request('POST', '/reset');
    const page = await ctx.newPage();
    await page.goto(MEET + '?variant=' + variant);

    await page.evaluate(() => sim.say('a', '山田', 'こんにちは'));
    await waitRecent((r) => r.length === 1 && r[0].speaker === '山田' && r[0].text === 'こんにちは', variant + ': 最初の一言');
    ok(variant + ': 話者つきで最初の発言が届いた');

    await page.evaluate(() => sim.update('a', '山田', 'こんにちは、山田です'));
    await sleep(300);
    await page.evaluate(() => sim.update('a', '山田', 'こんにちは、山田です。今日は勤怠システムの件でお願いします'));
    await waitRecent((r) => r.length === 1 && r[0].text === 'こんにちは、山田です。今日は勤怠システムの件でお願いします', variant + ': その場で伸びる');
    ok(variant + ': その場で伸びる字幕が 1 本の発言にまとまる（増殖しない）');

    await page.evaluate(() => sim.say('b', 'あなた', '聞こえています'));
    await page.evaluate(() => sim.update('b', 'あなた', '聞こえています。よろしくお願いします'));
    await waitRecent((r) => r.length === 2 && r[1].speaker === '自分' && r[1].text === '聞こえています。よろしくお願いします', variant + ': 自分');
    ok(variant + ': 「あなた」は自分の目印になり、表示名「自分」で出る');

    await page.evaluate(() => sim.update('a', '山田', '今日は勤怠システムの件でお願いします。まず現状の資料を共有します'));
    const expectedMerged = 'こんにちは、山田です。今日は勤怠システムの件でお願いします。まず現状の資料を共有します';
    await waitRecent((r) => r[0].text === expectedMerged, variant + ': 頭の切り詰め');
    ok(variant + ': 頭が切り詰められても、積み上げた文面に重なりを 1 回だけ足してつながる');

    await page.evaluate(() => { sim.remove('a'); sim.say('c', '山田', '二つ目の発言です'); });
    await waitRecent((r) => r.length === 3 && r[2].text === '二つ目の発言です' && r[0].final === true, variant + ': 消えたら確定');
    ok(variant + ': 消えたブロックは確定（final）、同じ話者の次のブロックは別の発言');

    await page.evaluate(() => sim.say('c', '山田', '二つ目の発言です。続きがあります'));
    const s2 = await waitRecent((r) => r.length === 3 && r[2].text === '二つ目の発言です。続きがあります', variant + ': 描き直し');
    ok(variant + ': 要素が作り直されても同じ発言として引き継ぐ（増えない）');

    for (const r of s2.recent) assert.ok(!/最新の字幕|arrow_downward|call_end|closed_caption/.test(r.text), 'ボタンやアイコンの文字が混ざった: ' + r.text);
    ok(variant + ': 「最新の字幕に移動」ボタンやアイコンの文字は混ざらない');

    const clicks = await page.evaluate(() => sim.clicks);
    assert.equal(clicks, 0, '字幕がオンのときにボタンを押してはいけない');
    ok(variant + ': 字幕がオンのときはトグルを押さない');

    // 診断（10 秒ごと）。構造だけで、本文・名前・会議コードは入らない
    const diagState = await waitFor(async () => { const d = (await request('GET', '/diag')).text; return /構造の受信: \d/.test(d) ? d : null; }, variant + ': 診断の受信', 20000);
    const diagText = diagState;
    for (const secret of ['山田', 'あなた', 'こんにちは', '勤怠システム', '資料を共有', '聞こえています', 'abc-defg-hij', '二つ目', '最新の字幕に移動']) {
      assert.ok(!diagText.includes(secret), '診断に入ってはいけない語: ' + secret);
    }
    assert.match(diagText, /"regionFound": true/);
    assert.match(diagText, /"selector": "aria-label"/);
    assert.match(diagText, /"tree"/);
    assert.match(diagText, /"extVersion": "0\.1\.0"/);
    assert.match(diagText, /HeadlessChrome|Chrome\//);
    ok(variant + ': 診断は構造だけ（本文・名前・会議コード・ボタン名を含まない）');
    if (OUT && variant === 'class') fs.writeFileSync(path.join(OUT, 'diag_sample_class.txt'), diagText);
    if (OUT && variant === 'generic') fs.writeFileSync(path.join(OUT, 'diag_sample_generic.txt'), diagText);

    const badges = await badgeOf();
    assert.ok(Object.values(badges).every((b) => b === ''), 'バッジは空のはず: ' + JSON.stringify(badges));
    ok(variant + ': バッジは空（正常）');

    await page.close();
  }

  // ── aria-label が無くても、tabindex の手がかり（画面の下の region）で見つかる ──
  {
    log('--- nolabel');
    await request('POST', '/reset');
    const page = await ctx.newPage();
    await page.goto(MEET + '?variant=nolabel');
    await page.evaluate(() => sim.say('a', '山田', 'ラベルが無くても読めます'));
    await waitRecent((r) => r.length === 1 && r[0].speaker === '山田' && r[0].text === 'ラベルが無くても読めます', 'nolabel: 発言');
    ok('nolabel: aria-label が無くても、下にある region[tabindex=0] から話者つきで読める');
    const diagText = await waitFor(async () => { const d = (await request('GET', '/diag')).text; return /"selector": "tabindex"/.test(d) ? d : null; }, 'nolabel: 診断', 20000);
    assert.match(diagText, /"selector": "tabindex"/);
    assert.ok(!/"regionLabel"/.test(diagText), 'ラベルで見つけていないので、ラベルの中身は診断に出さない');
    ok('nolabel: 診断は selector=tabindex を示し、ラベルの中身は出さない');
    await page.close();
  }

  // ── 字幕の領域が無く、横の参加者パネルだけがある → 字幕と取り違えない ──
  {
    log('--- decoy');
    await request('POST', '/reset');
    const page = await ctx.newPage();
    await page.goto(MEET + '?variant=decoy');
    await waitFor(async () => (await state()).status.captions.state === 'missing', 'decoy: 見つからない', 15000);
    await sleep(3500);
    const s = await state();
    assert.equal(s.recent.length, 0, '参加者パネルの文字を字幕として取り込んではいけない: ' + JSON.stringify(s.recent));
    ok('decoy: 横の参加者パネル（上から始まる region[tabindex=0]）は字幕と取り違えない');
    await page.close();
  }

  // ── 字幕がオフ → 1 度だけオンにする。再度オフにされても押し直さない ──
  {
    log('--- captionsoff');
    await request('POST', '/reset');
    const page = await ctx.newPage();
    await page.goto(MEET + '?variant=captionsoff');
    await waitFor(async () => (await page.evaluate(() => sim.onClicks)) === 1, '字幕オフ → 自動でオン', 20000);
    ok('字幕がオフなら、通話に入って少し後に 1 度だけ「字幕をオンにする」を押す');
    await page.evaluate(() => sim.say('a', '佐々木', 'オンになりました'));
    await waitRecent((r) => r.length === 1 && r[0].speaker === '佐々木', 'オン後の字幕');
    ok('オンになった後の字幕が届く');
    await page.evaluate(() => sim.setCaptions(false));
    await sleep(9000);
    const c = await page.evaluate(() => ({ on: sim.onClicks, off: sim.offClicks }));
    assert.deepEqual(c, { on: 1, off: 0 });
    ok('再度オフにされても押し直さない。「オフにする」は決して押さない');
    await page.close();
  }

  // ── 字幕の領域が無い（トグルも無い）→ CC のバッジ、画面の帯は「字幕が見つからない」 ──
  {
    log('--- noregion');
    await request('POST', '/reset');
    const page = await ctx.newPage();
    await page.goto(MEET + '?variant=noregion');
    await waitFor(async () => (await state()).status.captions.state === 'missing', '字幕が見つからない', 15000);
    ok('通話中に字幕の領域が無いと、ヘルパーの状態は missing');
    await waitFor(async () => Object.values(await badgeOf()).includes('CC'), 'CC のバッジ', 10000);
    ok('バッジ「CC」が出る');
    await page.close();
  }

  // ── ヘルパーが止まると OFF、戻ると消える ───────────────────
  {
    log('--- helper off/on');
    await request('POST', '/reset');
    const page = await ctx.newPage();
    await page.goto(MEET + '?variant=class');
    await page.evaluate(() => sim.say('a', '山田', '止める前の発言'));
    await waitRecent((r) => r.length === 1, '止める前');
    await stopHelper();
    await waitFor(async () => Object.values(await badgeOf()).includes('OFF'), 'OFF のバッジ', 15000);
    ok('ヘルパーが止まるとバッジ「OFF」');
    // 止まっている間の発言は手元にため、戻ったら送る
    await page.evaluate(() => sim.say('b', '佐々木', '止まっている間の発言'));
    await sleep(3500);
    await startHelper();
    await waitFor(async () => { const s = await state(); return s.recent.some((r) => r.text === '止まっている間の発言') ? s : null; }, '戻ったあとに届く', 20000);
    ok('止まっている間の発言は、ヘルパーが戻ると届く（手元にためて送り直す）');
    await waitFor(async () => Object.values(await badgeOf()).every((b) => b === ''), 'OFF が消える', 15000);
    ok('ヘルパーが戻るとバッジが消える');
    await page.close();
  }

  await ctx.close();
  await stopHelper();
  fs.rmSync(profile, { recursive: true, force: true });
  fs.rmSync(dataDir, { recursive: true, force: true });
  log('すべて通過: ' + results.length + ' 項目');
  if (OUT) fs.writeFileSync(path.join(OUT, 'e2e_results.txt'), results.join('\n') + '\n');
}

main().then(() => process.exit(0), async (e) => {
  console.error('E2E 失敗:', e && e.stack ? e.stack : e);
  try { await stopHelper(); } catch (_) {}
  process.exit(1);
});
