'use strict';
// 手元の Claude Code（claude -p）を呼ぶ。字幕の中身が出ていく先は、この PC の claude だけ。
//
//  ・claude の場所の見つけ方: 環境変数 CLAUDE_BIN → Windows は PATH などから claude.exe →
//    claude.cmd（隣の node_modules にある cli.js を node で直接起動）/ それ以外は PATH の claude
//  ・シェルは使わない（shell:true と引数配列の組み合わせは使わない）
//  ・安全のためのオプション（FLAGS_FULL）は、いつも付けて呼ぶ。未対応の古い版なら、外して呼び直さずに止める
//    （道具が使える状態で動かさない。直し方は「claude update」と伝える）

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');
const { shortenHome, clip } = require('./util');

const FLAGS_FULL = ['--tools', '', '--safe-mode', '--no-session-persistence'];
const UNKNOWN_FLAG_RE = /unknown option|unknown argument|error: option/i;
// 古い版の claude が安全のためのオプションを知らないとき、画面と黒い画面に出す文
const OLD_CLAUDE_MESSAGE =
  'お使いの Claude Code が古く、安全のための設定（道具を使わせない・会話を残さない など）に対応していません。' +
  '設定を外しての実行はしないので、整理はこれ以上行いません（字幕の記録は続きます）。' +
  'ターミナルで「claude update」を実行して新しくしてから、このヘルパーを起動し直してください。';
const USAGE_LIMIT_RE =
  /usage limit|limit reached|hit your .{0,40}limit|rate.?limit|quota|exceeded your|credit balance|resets? (at|in|on) |利用上限|使用上限|上限/i;
const MAX_OUTPUT_CHARS = 8 * 1024 * 1024;

function isFile(p) {
  try {
    return fs.statSync(p).isFile();
  } catch (_) {
    return false;
  }
}

const NOT_FOUND_MESSAGE =
  'Claude Code（claude コマンド）が見つかりません。ターミナルで「claude」と入力して動くことを確かめてください。' +
  '（見つからないときは、環境変数 CLAUDE_BIN に claude の場所を指定できます）';

/**
 * claude の起動方法を決める。
 * 戻り値: { ok:true, command, prefix:[], kind:'direct'|'node-script', display } | { ok:false, message }
 */
function resolveClaude(opts) {
  const o = opts || {};
  const env = o.env || process.env;
  const platform = o.platform || process.platform;
  const exists = o.exists || isFile;
  const home = o.home || os.homedir();
  const execPath = o.execPath || process.execPath;
  const p = platform === 'win32' ? path.win32 : path.posix;
  const fail = (message) => ({ ok: false, message });
  const done = (command, prefix, kind, shown) => ({
    ok: true,
    command,
    prefix,
    kind,
    display: shortenHome(shown, home),
  });

  function fromCmdShim(cmdPath) {
    const dir = p.dirname(cmdPath);
    const cli = p.join(dir, 'node_modules', '@anthropic-ai', 'claude-code', 'cli.js');
    if (exists(cli)) return done(execPath, [cli], 'node-script', cli);
    const nativeExe = p.join(dir, 'node_modules', '@anthropic-ai', 'claude-code', 'bin', 'claude.exe');
    if (exists(nativeExe)) return done(nativeExe, [], 'direct', nativeExe);
    return fail(
      'claude.cmd は見つかりましたが、隣の node_modules の中に cli.js がありません（' +
        shortenHome(cmdPath, home) +
        '）。環境変数 CLAUDE_BIN に claude.exe か cli.js の場所を指定してください。'
    );
  }

  function fromPath(bin) {
    const lower = bin.toLowerCase();
    if (/\.(cjs|mjs|js)$/.test(lower)) return done(execPath, [bin], 'node-script', bin);
    if (platform === 'win32' && /\.(cmd|bat)$/.test(lower)) return fromCmdShim(bin);
    return done(bin, [], 'direct', bin);
  }

  const forced = env.CLAUDE_BIN;
  if (forced) {
    if (!exists(forced)) return fail('環境変数 CLAUDE_BIN の場所に claude がありません: ' + shortenHome(forced, home));
    return fromPath(forced);
  }

  if (platform === 'win32') {
    const dirs = String(env.PATH || env.Path || '')
      .split(';')
      .filter(Boolean);
    dirs.push(p.join(env.USERPROFILE || home, '.local', 'bin'));
    for (const d of dirs) {
      const exe = p.join(d, 'claude.exe');
      if (exists(exe)) return done(exe, [], 'direct', exe);
    }
    for (const d of dirs) {
      const cmd = p.join(d, 'claude.cmd');
      if (exists(cmd)) return fromCmdShim(cmd);
    }
    return fail(NOT_FOUND_MESSAGE);
  }

  const dirs = String(env.PATH || '')
    .split(':')
    .filter(Boolean);
  dirs.push(p.join(home, '.local', 'bin'), p.join(home, '.claude', 'local'), '/usr/local/bin', '/opt/homebrew/bin');
  for (const d of dirs) {
    const bin = p.join(d, 'claude');
    if (exists(bin)) return done(bin, [], 'direct', bin);
  }
  return fail(NOT_FOUND_MESSAGE);
}

/** 子プロセスを 1 回走らせる。決して reject しない */
function runProcess(command, args, { cwd, env, timeoutMs, input }) {
  return new Promise((resolve) => {
    const started = Date.now();
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    let settled = false;
    let spawnError = null;
    let timer = null;
    let killTimer = null;
    let child;

    const finish = (code, signal) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(killTimer);
      resolve({ code, signal, stdout, stderr, timedOut, spawnError, durationMs: Date.now() - started });
    };

    try {
      child = spawn(command, args, { cwd, env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    } catch (e) {
      spawnError = e;
      finish(null, null);
      return;
    }
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (d) => {
      if (stdout.length < MAX_OUTPUT_CHARS) stdout += d;
    });
    child.stderr.on('data', (d) => {
      if (stderr.length < MAX_OUTPUT_CHARS) stderr += d;
    });
    child.on('error', (e) => {
      spawnError = e;
      finish(null, null);
    });
    child.on('close', (code, signal) => finish(code, signal));
    child.stdin.on('error', () => {}); // 相手が先に終わったときの EPIPE は無視
    child.stdin.end(input == null ? '' : input);

    timer = setTimeout(() => {
      timedOut = true;
      try {
        child.kill();
      } catch (_) {
        /* 既に終わっている */
      }
      killTimer = setTimeout(() => {
        try {
          child.kill('SIGKILL');
        } catch (_) {
          /* 既に終わっている */
        }
        finish(null, 'SIGKILL');
      }, 3000);
    }, timeoutMs);
  });
}

function tryParseJson(text) {
  try {
    return JSON.parse(text);
  } catch (_) {
    return undefined;
  }
}

function isUsageLimit(message) {
  return USAGE_LIMIT_RE.test(String(message || ''));
}

/** 1 回分の結果を ok / エラー種別に分類する */
function interpret(proc, timeoutMs) {
  if (proc.spawnError) {
    return {
      ok: false,
      kind: 'spawn',
      message: 'claude を起動できませんでした（' + clip(proc.spawnError.message, 160) + '）',
      detail: clip(proc.spawnError.code || proc.spawnError.message, 120),
    };
  }
  if (proc.timedOut) {
    return {
      ok: false,
      kind: 'timeout',
      message: 'claude の返事が ' + Math.round(timeoutMs / 1000) + ' 秒たっても来ませんでした。次の機会にやり直します。',
      detail: 'timeout ' + Math.round(timeoutMs / 1000) + 's',
    };
  }

  const out = (proc.stdout || '').trim();
  const parsed = out ? tryParseJson(out) : undefined;
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const subtype = typeof parsed.subtype === 'string' ? parsed.subtype : '';
    const text = typeof parsed.result === 'string' ? parsed.result : '';
    if (parsed.is_error === true || (subtype && subtype !== 'success')) {
      const raw = text || (typeof parsed.error === 'string' ? parsed.error : '') || subtype || 'error';
      if (isUsageLimit(raw)) {
        return {
          ok: false,
          kind: 'usage-limit',
          message: 'Claude の利用上限に達したようです。上限が戻るまで整理は止まります（字幕の記録は続きます）。claude のメッセージ: ' + clip(raw, 200),
          detail: clip(raw, 200),
        };
      }
      const login = /log ?in|authenticat|api key|credential|unauthori[sz]ed/i.test(raw)
        ? '（ターミナルで claude を起動して、ログインできているか確かめてください）'
        : '';
      return {
        ok: false,
        kind: 'claude-error',
        message: 'claude がエラーを返しました: ' + clip(raw, 200) + login,
        detail: clip(raw, 200),
      };
    }
    if (typeof parsed.result === 'string') {
      // 速さと費用を測るため、数字だけ持ち帰る（本文は持ち帰らない）
      const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
      return { ok: true, text: parsed.result, meta: { cost: num(parsed.total_cost_usd), ms: num(parsed.duration_ms) } };
    }
    return { ok: false, kind: 'bad-output', message: 'claude の返事に result がありませんでした。', detail: 'no result field' };
  }

  const combined = (proc.stderr || '') + '\n' + out.slice(0, 2000);
  if (proc.code !== 0) {
    if (UNKNOWN_FLAG_RE.test(combined)) {
      return {
        ok: false,
        kind: 'unknown-flag',
        unknownFlag: true,
        message: OLD_CLAUDE_MESSAGE,
        // detail は黒い画面にも出る。案内をそこにも載せる（claude の返事は添えるだけ）
        detail: OLD_CLAUDE_MESSAGE + '（claude の返事: ' + clip((proc.stderr || out).trim(), 120) + '）',
      };
    }
    if (isUsageLimit(combined)) {
      return {
        ok: false,
        kind: 'usage-limit',
        message: 'Claude の利用上限に達したようです。上限が戻るまで整理は止まります（字幕の記録は続きます）。claude のメッセージ: ' + clip(combined.trim(), 200),
        detail: clip(combined.trim(), 200),
      };
    }
    return {
      ok: false,
      kind: 'exit',
      message: 'claude が異常終了しました（終了コード ' + proc.code + '）: ' + clip((proc.stderr || out).trim(), 200),
      detail: 'exit ' + proc.code + ' ' + clip((proc.stderr || '').trim(), 160),
    };
  }
  if (!out) {
    return { ok: false, kind: 'bad-output', message: 'claude の返事が空でした。', detail: 'empty stdout' };
  }
  // JSON ではなく本文だけが返ってきた版 → 本文として扱う
  return { ok: true, text: out, meta: { raw: true } };
}

/**
 * claude -p を 1 回呼ぶ。安全のためのオプション（FLAGS_FULL）は必ず付ける。
 * 古い版が知らないときも、外して呼び直さない（kind: 'unknown-flag' の失敗をそのまま返す）。
 * state は呼び出し側が持ち回る。返事が来たら state.confirmed = true（このオプションの組で実際に動いた）。
 * 戻り値: { ok:true, text } | { ok:false, kind, message, detail }
 */
async function callClaude({ resolved, model, prompt, cwd, timeoutMs, state, env }) {
  const args = resolved.prefix.concat(['-p', '--output-format', 'json', '--model', model], FLAGS_FULL);
  const proc = await runProcess(resolved.command, args, { cwd, env: env || process.env, timeoutMs, input: prompt });
  const result = interpret(proc, timeoutMs);
  if (result.ok && state) state.confirmed = true;
  return result;
}

/** 起動時の点検: claude --version */
async function claudeVersion(resolved, env) {
  const proc = await runProcess(resolved.command, resolved.prefix.concat(['--version']), {
    cwd: os.tmpdir(),
    env: env || process.env,
    timeoutMs: 20000,
    input: '',
  });
  if (proc.spawnError) return { ok: false, message: clip(proc.spawnError.message, 160) };
  if (proc.timedOut) return { ok: false, message: '--version が 20 秒で返りませんでした' };
  if (proc.code !== 0) return { ok: false, message: clip((proc.stderr || proc.stdout).trim(), 160) || '終了コード ' + proc.code };
  return { ok: true, version: (proc.stdout || '').trim().split(/\r?\n/)[0] };
}

module.exports = {
  resolveClaude,
  callClaude,
  claudeVersion,
  runProcess,
  interpret,
  isUsageLimit,
  FLAGS_FULL,
  UNKNOWN_FLAG_RE,
  OLD_CLAUDE_MESSAGE,
};
