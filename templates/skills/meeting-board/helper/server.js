#!/usr/bin/env node
'use strict';
// 会議ボードのヘルパー。Meet の字幕（拡張機能から届く）を、この PC の Claude Code に整理してもらい、
// ボード（http://127.0.0.1:47431/）に出す。127.0.0.1 だけで待ち受け、外には何も送らない。
//
//   node helper/server.js [--port 47431] [--interval 60] [--model sonnet] [--open]
//                         [--notes ファイル] [--replay ファイル [--speed auto]] [--once] [--data-dir フォルダ] [--me 名前]
//                         [--mode live|full|diff]
//   node helper/server.js --minutes <会議フォルダ | board.json> [--out ファイル]   議事録の素（Markdown）を書き出す

// 古い Node でも、ここまでは読めるように古い構文だけで書いてある（18 未満なら理由を出して終わる）
const nodeMajor = Number(String(process.versions.node).split('.')[0]);
if (nodeMajor < 18) {
  console.error('Node.js が古すぎます（' + process.version + '）。Node.js 18 以上を入れてください。');
  process.exit(1);
}

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const { parseArgs, USAGE } = require('./lib/args');
const { MeetingBoardApp } = require('./lib/app');
const { listen, probeExisting } = require('./lib/httpserver');
const { toEntries, startReplay, autoSpeed, replaySeconds } = require('./lib/replay');
const { importTranscript } = require('./lib/importers');
const { boardToMarkdown, transcriptInfo } = require('./lib/minutes');

const VERSION = '0.3.0';
const HELPER_DIR = __dirname;

// 会議の最中に落ちないように、想定外のエラーは表示だけして続ける
process.on('uncaughtException', function (e) {
  console.error('想定外のエラー（続行します）: ' + (e && e.stack ? e.stack : e));
});
process.on('unhandledRejection', function (e) {
  console.error('想定外のエラー（続行します）: ' + (e && e.stack ? e.stack : e));
});

function openBrowser(url) {
  try {
    let child;
    if (process.platform === 'win32') {
      // cmd /c start "" <url>
      child = spawn('cmd.exe', ['/d', '/s', '/c', 'start "" "' + url + '"'], {
        windowsVerbatimArguments: true,
        windowsHide: true,
        detached: true,
        stdio: 'ignore',
      });
    } else if (process.platform === 'darwin') {
      child = spawn('open', [url], { detached: true, stdio: 'ignore' });
    } else {
      child = spawn('xdg-open', [url], { detached: true, stdio: 'ignore' });
    }
    child.on('error', function () {
      /* 開けなくても動作には影響しない */
    });
    child.unref();
  } catch (_) {
    /* 開けなくても動作には影響しない */
  }
}

function formatCheck(c) {
  return '  ' + (c.ok ? 'OK ' : 'NG ') + c.name + ': ' + c.detail;
}

/**
 * --minutes: 保存したボードから議事録の素（Markdown）を書き出す。この PC の中だけ（標準出力かファイル）。
 * 場所が会議フォルダなら board.json と transcript.jsonl（日時と名前だけ使う）を読む。JSON ファイルならそれを読む
 */
function exportMinutes(opts) {
  const target = path.resolve(opts.minutes);
  let boardFile = target;
  let txFile = null;
  try {
    if (fs.statSync(target).isDirectory()) {
      boardFile = path.join(target, 'board.json');
      txFile = path.join(target, 'transcript.jsonl');
    }
  } catch (e) {
    console.error('--minutes の場所が見つかりません: ' + opts.minutes);
    return 2;
  }
  let board;
  try {
    board = JSON.parse(fs.readFileSync(boardFile, 'utf8'));
  } catch (e) {
    console.error('ボード（board.json）を読めませんでした: ' + boardFile + '（' + e.message + '）');
    return 2;
  }
  if (!board || !Array.isArray(board.topics)) {
    console.error('ボードの形ではありません（topics がありません）: ' + boardFile);
    return 2;
  }
  let info = {};
  if (txFile && fs.existsSync(txFile)) {
    let selfName = '';
    try {
      selfName = JSON.parse(fs.readFileSync(path.join(path.dirname(target), 'settings.json'), 'utf8')).selfName || '';
    } catch (_) {
      /* 無くてよい */
    }
    info = transcriptInfo(fs.readFileSync(txFile, 'utf8'), selfName || opts.me || '');
  }
  const md = boardToMarkdown(board, info);
  if (opts.out) {
    fs.writeFileSync(path.resolve(opts.out), md, 'utf8');
    console.error('議事録の素を書き出しました: ' + path.resolve(opts.out) + '（下書きです。外に出す前に見直してください）');
  } else {
    process.stdout.write(md);
  }
  return 0;
}

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  if (parsed.opts.help) {
    console.log(USAGE);
    return 0;
  }
  if (parsed.errors.length) {
    for (const e of parsed.errors) console.error('引数のエラー: ' + e);
    console.error('\n' + USAGE);
    return 2;
  }
  const opts = parsed.opts;
  if (opts.minutes) return exportMinutes(opts);
  // --once は結果の JSON だけを標準出力に出す。案内やログは標準エラーへ
  const say = opts.once ? function (m) { console.error(m); } : function (m) { console.log(m); };

  const dataDir = opts.dataDir ? path.resolve(opts.dataDir) : path.join(HELPER_DIR, '..', 'data');
  let notes = '';
  if (opts.notes) {
    try {
      notes = fs.readFileSync(path.resolve(opts.notes), 'utf8');
    } catch (e) {
      console.error('事前メモを読めませんでした（' + opts.notes + '）: ' + e.message);
      return 2;
    }
  }
  let scriptText = '';
  if (opts.script) {
    try {
      scriptText = fs.readFileSync(path.resolve(opts.script), 'utf8');
    } catch (e) {
      console.error('台本を読めませんでした（' + opts.script + '）: ' + e.message);
      return 2;
    }
  }
  let replayLines = null;
  if (opts.replay) {
    let imported;
    try {
      imported = importTranscript(fs.readFileSync(path.resolve(opts.replay), 'utf8'), opts.replay);
    } catch (e) {
      console.error('--replay のファイルを読めませんでした（' + opts.replay + '）: ' + e.message);
      return 2;
    }
    if (imported.format === 'unknown' || imported.lines.length === 0) {
      console.error('--replay のファイルを読めませんでした: ' + opts.replay);
      console.error('  ' + imported.note);
      return 2;
    }
    replayLines = imported.lines;
    say('--replay: ' + imported.note);
  }

  const app = new MeetingBoardApp({
    version: VERSION,
    port: opts.port,
    model: opts.model,
    intervalSec: opts.interval,
    dataDir: dataDir,
    promptPath: path.join(HELPER_DIR, 'prompt.md'),
    boardHtmlPath: path.join(HELPER_DIR, 'board.html'),
    notes: notes,
    me: opts.me,
    script: scriptText,
    scriptManual: opts.scriptManual,
    mode: opts.mode || 'live',
    log: function (m) {
      if (process.env.MEETING_BOARD_DEBUG) console.error('[debug] ' + m);
    },
    // 整理のエラーは黒い画面にも出す（--once では標準エラー）。字幕の本文と名前は伏せてある
    warn: function (m) {
      const d = new Date();
      const t = [d.getHours(), d.getMinutes(), d.getSeconds()].map(function (n) { return String(n).padStart(2, '0'); }).join(':');
      say(t + ' ' + m);
    },
  });

  // ── --once: 全部読み込んで 1 回だけ整理し、JSON を出して終わる ──
  if (opts.once) {
    await app.runSelfCheck({ listenInfo: null, withVersion: false });
    for (const c of app.selfCheck) say(formatCheck(c));
    const base = Date.now();
    const all = toEntries(replayLines, base);
    // --mode diff: 前 6 割で全体の整理 → 残りで差分の整理（差分の速さと形を 1 回で確かめるため）
    const split = opts.mode === 'diff' && all.length >= 4 ? Math.ceil(all.length * 0.6) : all.length;
    for (const e of all.slice(0, split)) app.transcript.upsert(e, Date.now());
    say('字幕 ' + app.transcript.entries.length + ' 行を読み込みました。claude に整理を頼みます（しばらくかかります）...');
    let r = await app.runUpdate('once');
    if (r.ok && split < all.length) {
      for (const e of all.slice(split)) app.transcript.upsert(e, Date.now());
      say('残りの ' + (all.length - split) + ' 行で、差分の整理を頼みます...');
      r = await app.runUpdate('once-diff');
    }
    app.shutdown();
    if (!r.ok) {
      console.error('整理に失敗しました: ' + r.message);
      return 1;
    }
    process.stdout.write(JSON.stringify(r.board, null, 2) + '\n');
    return 0;
  }

  // ── 通常: HTTP サーバーを立てる ──
  let server;
  try {
    server = await listen(app, opts.port);
  } catch (e) {
    if (e && e.code === 'EADDRINUSE') {
      const already = await probeExisting(opts.port);
      if (already) {
        const url = 'http://127.0.0.1:' + opts.port + '/';
        say('会議ボードはすでに起動しています: ' + url);
        say('（このウィンドウは閉じてかまいません。止めるときは、先に起動したウィンドウで Ctrl+C）');
        if (opts.open) openBrowser(url);
        return 0;
      }
      console.error('ポート ' + opts.port + ' は別のプログラムが使っています。');
      console.error('会議ボードの拡張機能は ' + opts.port + ' 番に送る作りなので、使っているプログラムを止めてからやり直してください。');
      return 1;
    }
    console.error('待ち受けを始められませんでした: ' + e.message);
    return 1;
  }
  app.port = server.address().port;
  const url = 'http://127.0.0.1:' + app.port + '/';

  await app.runSelfCheck({
    listenInfo: { name: 'ポート', ok: true, detail: app.port + ' 番で待ち受け中（この PC の中だけ）' },
    withVersion: false,
  });
  say('会議ボード ヘルパー ' + VERSION);
  say('  ボード: ' + url);
  say('  保存先: ' + dataDir);
  say('起動時の点検:');
  for (const c of app.selfCheck) say(formatCheck(c));
  if (!app.resolved.ok) {
    say('');
    say('!! ' + app.resolved.message);
    say('   claude が使えるようになるまで、字幕は集まりますが「ここまでの話」は作られません。');
  }
  say('');
  say('このウィンドウを閉じると止まります。止めるときは Ctrl+C。');
  if (opts.open) openBrowser(url);

  // claude の版は少し時間がかかるので、起動後に確かめて点検欄を更新する
  if (app.resolved.ok) {
    app.runSelfCheck({
      listenInfo: { name: 'ポート', ok: true, detail: app.port + ' 番で待ち受け中（この PC の中だけ）' },
      withVersion: true,
    }).then(function (checks) {
      const v = checks.find(function (c) { return c.name === 'claude の版'; });
      if (v) say('  ' + (v.ok ? 'OK ' : 'NG ') + 'claude の版: ' + v.detail);
    });
  }

  app.startLoop();

  let replayHandle = null;
  if (replayLines) {
    const entries = toEntries(replayLines, Date.now());
    app.replay = { active: true, index: 0, total: entries.length };
    const realSec = replaySeconds(replayLines);
    const speed = opts.speed === 'auto' ? autoSpeed({ realSec, intervalSec: opts.interval }) : opts.speed;
    const playMin = Math.max(1, Math.round(realSec / speed / 60));
    const cycles = Math.max(1, Math.round(realSec / speed / (Math.min(opts.interval, 20) + 45)));
    say(
      '--replay: ' + entries.length + ' 行を ' + speed + ' 倍速で流します（約 ' + playMin + ' 分・整理はおよそ ' + cycles + ' 回の見込み' +
        (opts.speed === 'auto' ? '。速さは --speed で変えられます' : '') + '）。'
    );
    replayHandle = startReplay(entries, speed, function (entry, i) {
      app.transcript.upsert(entry, Date.now());
      app.replay = { active: true, index: i + 1, total: entries.length };
    });
    replayHandle.done.then(function (finished) {
      app.replay = { active: false, index: entries.length, total: entries.length, finished: !!finished };
      if (finished) {
        say('--replay: 流し終わりました。最後の整理を行います。');
        app.flushNow = true; // 間隔を待たずに最後の整理へ
      }
    });
  }

  // 終了処理
  await new Promise(function (resolve) {
    let closing = false;
    const stop = function () {
      if (closing) return;
      closing = true;
      if (replayHandle) replayHandle.stop();
      app.shutdown();
      server.close(function () { resolve(); });
      setTimeout(resolve, 1500).unref();
    };
    process.on('SIGINT', stop);
    process.on('SIGTERM', stop);
    if (process.platform === 'win32') process.on('SIGBREAK', stop); // Ctrl+Break
    // 試験などで IPC つきで起動されたときは {type:'stop'} の合図でも同じ道で終わる。
    // Windows の Node は子への SIGTERM を強制終了にする（ハンドラが走らない）ため、どの OS でも
    // 同じ「きれいな終了」を通せるようにしてある。通常の起動（start.cmd）では IPC が無いので何も起きない
    if (typeof process.send === 'function') {
      process.on('message', function (m) {
        if (m && m.type === 'stop') stop();
      });
    }
  });
  return 0;
}

main().then(
  function (code) {
    process.exit(code);
  },
  function (e) {
    console.error('予期しないエラー: ' + (e && e.stack ? e.stack : e));
    process.exit(1);
  }
);
