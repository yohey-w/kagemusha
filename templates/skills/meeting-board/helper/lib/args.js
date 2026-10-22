'use strict';
// コマンドライン引数。node helper/server.js [--port N] [--interval 秒] [--model M] ...

const DEFAULTS = {
  port: 47431,
  interval: 60,
  model: 'sonnet',
  open: false,
  notes: null,
  replay: null,
  speed: 10,
  once: false,
  dataDir: null,
  me: null,
  minutes: null,
  out: null,
  help: false,
};

const USAGE = [
  '使い方: node helper/server.js [オプション]',
  '  --port N          待ち受けポート（既定 47431。拡張機能もこの番号を前提にしています）',
  '  --interval 秒     整理の最長間隔（既定 60）',
  '  --model 名前      claude のモデル（既定 sonnet）',
  '  --open            ボードをブラウザで開く',
  '  --notes ファイル  事前メモを読み込む',
  '  --replay ファイル 字幕のかわりにファイルの会話を流す（「話者：本文」の行）',
  '  --speed N         --replay の速さ（既定 10 倍。1 倍は 1 行あたり約 4 秒）',
  '  --once            --replay を全部読み込み、整理を 1 回だけ行い、結果の JSON を出力して終わる',
  '  --data-dir フォルダ  記録の保存先（既定は helper の隣の data/）',
  '  --me 名前         字幕に出る自分の名前（自分の発言を言い直して返さないため。Meet の「あなた」も自分として扱う）',
  '  --minutes 場所    会議のあとに、議事録の素（Markdown）を書き出して終わる。場所は会議フォルダ（data/<開始日時>）',
  '                    か、board.json・--once の出力の JSON ファイル。標準出力へ出す（--out ファイル でファイルへ）',
].join('\n');

function toNumber(name, value, errors, { min, max, int }) {
  const n = Number(value);
  if (value === undefined || value === null || value === '' || !Number.isFinite(n)) {
    errors.push(name + ' には数字を指定してください');
    return null;
  }
  if (int && !Number.isInteger(n)) {
    errors.push(name + ' には整数を指定してください');
    return null;
  }
  if (n < min || n > max) {
    errors.push(name + ' は ' + min + '〜' + max + ' の範囲で指定してください');
    return null;
  }
  return n;
}

function parseArgs(argv) {
  const opts = Object.assign({}, DEFAULTS);
  const errors = [];
  const takesValue = new Set(['--port', '--interval', '--model', '--notes', '--replay', '--speed', '--data-dir', '--me', '--minutes', '--out']);
  for (let i = 0; i < argv.length; i++) {
    let arg = argv[i];
    let inline;
    const eq = arg.indexOf('=');
    if (arg.startsWith('--') && eq > 0) {
      inline = arg.slice(eq + 1);
      arg = arg.slice(0, eq);
    }
    if (arg === '--open') opts.open = true;
    else if (arg === '--once') opts.once = true;
    else if (arg === '--help' || arg === '-h') opts.help = true;
    else if (takesValue.has(arg)) {
      let value = inline;
      if (value === undefined) {
        value = argv[i + 1];
        if (value === undefined || value.startsWith('--')) {
          errors.push(arg + ' には値が必要です');
          continue;
        }
        i += 1;
      }
      if (arg === '--port') {
        const n = toNumber('--port', value, errors, { min: 0, max: 65535, int: true });
        if (n !== null) opts.port = n;
      } else if (arg === '--interval') {
        const n = toNumber('--interval', value, errors, { min: 5, max: 3600, int: false });
        if (n !== null) opts.interval = n;
      } else if (arg === '--speed') {
        const n = toNumber('--speed', value, errors, { min: 0.1, max: 1000, int: false });
        if (n !== null) opts.speed = n;
      } else if (arg === '--model') opts.model = value;
      else if (arg === '--notes') opts.notes = value;
      else if (arg === '--replay') opts.replay = value;
      else if (arg === '--data-dir') opts.dataDir = value;
      else if (arg === '--minutes') opts.minutes = value;
      else if (arg === '--out') opts.out = value;
      else if (arg === '--me') {
        const n = String(value).replace(/\s+/g, ' ').trim().slice(0, 40);
        if (n) opts.me = n;
        else errors.push('--me には名前を指定してください');
      }
    } else {
      errors.push('知らないオプションです: ' + argv[i]);
    }
  }
  if (opts.once && !opts.replay) errors.push('--once は --replay といっしょに指定してください');
  if (opts.minutes && (opts.once || opts.replay)) errors.push('--minutes は --replay / --once とは別に使ってください');
  if (opts.out && !opts.minutes) errors.push('--out は --minutes といっしょに指定してください');
  return { opts, errors };
}

module.exports = { parseArgs, DEFAULTS, USAGE };
