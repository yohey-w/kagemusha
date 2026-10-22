'use strict';
// ヘルパー本体の状態と動き（HTTP は httpserver.js、起動と引数は ../server.js）。
//
//   拡張機能 ──字幕──▶ Transcript ──(一定量たまったら)──▶ claude -p ──▶ ボード(JSON)
//
// ・claude の呼び出しは同時に 1 つだけ。タイムアウトは 120 秒
// ・失敗したら前のボードを残し、間をあけてやり直す（使い切りの上限に当たったら長めに待つ）
// ・診断（GET /diag）には字幕の中身を入れない

const fs = require('fs');
const os = require('os');

const { Store } = require('./store');
const { Transcript } = require('./transcript');
const { buildWindow, buildPrompt, shouldUpdate } = require('./prompt');
const { extractJsonObject } = require('./extract');
const { normalizeBoardV2, toPromptBoard } = require('./board');
const { parseNotes } = require('./notes');
const { resolveClaude, callClaude, claudeVersion } = require('./claude');
const { buildDiagText } = require('./diag');
const { errMsg, clip, shortenHome } = require('./util');

const CAPTION_FRESH_MS = 20000; // これ以内に届いていれば「受信中」
const EXT_FRESH_MS = 30000; // 拡張機能の状態がこれ以内なら「いま見えている」とみなす
const MAX_NAME_LEN = 40;
const MAX_NOTES_LEN = 100000;

class MeetingBoardApp {
  constructor(options) {
    const o = options;
    this.version = o.version || '0.2.0';
    this.port = o.port || 0;
    this.model = o.model || 'sonnet';
    this.intervalMs = (o.intervalSec || 60) * 1000;
    this.timeoutMs = o.timeoutMs || 120000;
    this.now = o.now || (() => Date.now());
    this.log = o.log || (() => {});
    // エラーを黒い画面（標準出力）にも出す。字幕・事前メモと同じ並びを含む文は伏せてから渡す
    this.warn = o.warn || (() => {});
    this.env = o.env || process.env;
    this.promptMd = fs.readFileSync(o.promptPath, 'utf8');
    this.boardHtmlPath = o.boardHtmlPath;
    this.boardCorePath = o.boardCorePath || null;
    this.me = o.me ? String(o.me).replace(/\s+/g, ' ').trim().slice(0, MAX_NAME_LEN) : ''; // --me（字幕に出る自分の名前）

    this.store = new Store(o.dataDir);
    this.settings = this.store.loadSettings();
    this.resolved = resolveClaude({ env: this.env });
    this.claudeState = { flagSet: 'full' };
    this.claudeVer = null;
    this.selfCheck = [];

    this.startedAt = this.now();
    this.errors = []; // 診断用（新しい順・最大 5 件）
    this.lastError = null; // 画面の帯に出す 1 件
    this.updateCount = 0;
    this.failCount = 0;
    this.consecutiveFails = 0;
    this.lastEndAt = this.startedAt;
    this.blockedUntil = 0;
    this.inFlight = false;
    this.lastDurationMs = null;
    this.lastUpdateAt = 0;
    this.ignoreBefore = 0; // 「新しい会議」より前に始まった発言は取り込まない
    this.extStatus = null;
    this.extStatusAt = 0;
    this.extDiag = null;
    this.extDiagAt = 0;
    this.replay = null; // { active, index, total }
    this.flushNow = false;
    this.sessionToken = 0;
    this.timer = null;

    this.beginSession(this.startedAt, o.notes || '');
  }

  // ── 会議（セッション） ─────────────────────────────────────
  beginSession(now, notes) {
    this.sessionToken += 1;
    this.sessionStartedAt = now;
    this.store.startSession(now);
    this.transcript = new Transcript();
    this.board = null;
    this.notes = notes || '';
    this.notesVersion = 0;
    this.notesDirty = false;
    this.lastLineCount = 0;
    this.lastTotalChars = 0;
    this.lastTextRevision = 0;
    // 帯の「最終更新・更新 N 回」と診断の件数は、会議ごとに数え直す
    this.updateCount = 0;
    this.failCount = 0;
    this.lastUpdateAt = 0;
    this.lastDurationMs = null;
    this.lastClaudeMs = null; // claude が返した duration_ms
    this.lastCostUsd = null; // claude が返した total_cost_usd
    this.totalCostUsd = 0; // この会議で使った分の合計
    this.savedRevision = 0;
    this.lastSaveAt = now;
    this.lastEndAt = now;
    this.safe(() => this.store.saveTranscript(''));
    if (this.notes) this.safe(() => this.store.saveNotes(this.notes));
  }

  safe(fn) {
    try {
      return fn();
    } catch (e) {
      this.recordError('save', '保存に失敗しました（' + clip(errMsg(e), 120) + '）', clip(errMsg(e), 120));
      return undefined;
    }
  }

  persist(force) {
    const now = this.now();
    if (this.transcript.revision === this.savedRevision) return;
    if (!force && now - this.lastSaveAt < 3000) return;
    this.safe(() => this.store.saveTranscript(this.transcript.toJsonl()));
    this.savedRevision = this.transcript.revision;
    this.lastSaveAt = now;
  }

  /** 「新しい会議」: いまの記録はフォルダに残したまま、空のボードで始め直す */
  reset() {
    this.persist(true);
    const now = this.now();
    this.ignoreBefore = now;
    this.lastError = null;
    this.consecutiveFails = 0;
    this.blockedUntil = 0;
    this.replay = null;
    this.beginSession(now, '');
  }

  // ── 入力 ──────────────────────────────────────────────────
  ingestCaptions(entries, status) {
    const now = this.now();
    let accepted = 0;
    if (Array.isArray(entries)) {
      for (const raw of entries.slice(0, 500)) {
        if (raw && typeof raw.firstSeen === 'number' && raw.firstSeen < this.ignoreBefore) continue;
        if (this.transcript.upsert(raw, now)) accepted += 1;
      }
    }
    if (status && typeof status === 'object') this.setExtStatus(status);
    return accepted;
  }

  setExtStatus(status) {
    const b = (v) => (v === true ? true : v === false ? false : null);
    this.extStatus = { inCall: b(status.inCall), regionFound: b(status.regionFound), captionsOff: b(status.captionsOff) };
    this.extStatusAt = this.now();
  }

  setDiag(obj) {
    if (!obj || typeof obj !== 'object') return false;
    this.extDiag = sanitizeDiag(obj, 0);
    this.extDiagAt = this.now();
    return true;
  }

  setNotes(text) {
    const t = String(text == null ? '' : text).slice(0, MAX_NOTES_LEN);
    if (t === this.notes) return;
    this.notes = t;
    this.notesVersion += 1;
    this.notesDirty = true;
    this.safe(() => this.store.saveNotes(t));
  }

  setSelfName(name) {
    const n = String(name == null ? '' : name).replace(/\s+/g, ' ').trim().slice(0, MAX_NAME_LEN);
    this.settings.selfName = n;
    this.safe(() => this.store.saveSettings(this.settings));
    return n;
  }

  /** 事前メモを読んだ結果（聞くこと・伝えること・こちらの理解）。メモが変わったときだけ読み直す */
  notesSpec() {
    if (!this._spec || this._specFor !== this.notes) {
      this._spec = parseNotes(this.notes);
      this._specFor = this.notes;
    }
    return this._spec;
  }

  /** Meet の「あなた」（__SELF__）を整理に渡すときの名前: 画面で決めた表示名 → --me → 事前メモの「自分：」→「自分」 */
  selfName() {
    return this.settings.selfName || this.me || this.notesSpec().me || '自分';
  }

  /** 使う人の名前（字幕でこの名前の発言は使う人のもの） */
  userNames() {
    const names = [];
    for (const n of [this.selfName(), this.me, this.settings.selfName, this.notesSpec().me]) {
      if (n && names.indexOf(n) < 0) names.push(n);
    }
    return names;
  }

  /** 【使う人】の節の 1 行 */
  usersLine() {
    const names = this.userNames();
    return (
      names.join('、') +
      '（字幕でこの名前の発言は使う人のもの。Meet の字幕で「あなた」と出た発言も「' +
      this.selfName() +
      '」として渡しています）'
    );
  }

  // ── 整理（claude への依頼） ──────────────────────────────
  recordError(kind, message, detail) {
    const at = this.now();
    this.lastError = { at, kind, message };
    this.errors.unshift({ at, kind, detail: detail || '' });
    if (this.errors.length > 5) this.errors.length = 5;
    try {
      this.warn('整理のエラー [' + kind + '] ' + this.scrub(detail || message || ''));
    } catch (_) {
      /* 表示できなくても動作には影響しない */
    }
  }

  pendingChars() {
    return Math.max(0, this.transcript.totalChars() - this.lastTotalChars);
  }

  /** 前回の整理のあとに字幕が変わったか（書き換えで短くなった・同じ長さで言い直した、も変化に数える） */
  pendingChange() {
    const chars = this.pendingChars();
    if (chars > 0) return chars;
    return this.transcript.textRevision !== this.lastTextRevision ? 1 : 0;
  }

  tick() {
    try {
      const now = this.now();
      this.transcript.settle(now);
      this.persist(false);
      let reason = shouldUpdate({
        inFlight: this.inFlight,
        now,
        lastEndAt: this.lastEndAt,
        blockedUntil: this.blockedUntil,
        newChars: this.pendingChange(),
        intervalMs: this.intervalMs,
        notesDirty: this.notesDirty,
        hasTranscript: this.transcript.entries.length > 0,
      });
      // --replay が流し終わったあとは、間隔を待たずに最後の整理を行う
      if (
        !reason &&
        this.flushNow &&
        this.pendingChange() > 0 &&
        !this.inFlight &&
        now >= this.blockedUntil &&
        now - this.lastEndAt >= 5000
      ) {
        reason = 'flush';
      }
      if (reason) {
        this.flushNow = false;
        this.runUpdate(reason).catch((e) => {
          this.recordError('internal', '内部エラー: ' + clip(errMsg(e), 160), clip(errMsg(e), 160));
        });
      }
    } catch (e) {
      this.recordError('internal', '内部エラー: ' + clip(errMsg(e), 160), 'tick: ' + clip(errMsg(e), 160));
    }
  }

  /** 整理を 1 回行う。戻り値: { ok:true, board } | { ok:false, kind, message } */
  async runUpdate(reason) {
    if (this.inFlight) return { ok: false, kind: 'busy', message: '整理の最中です' };
    if (!this.resolved.ok) {
      if (!this.lastError || this.lastError.kind !== 'no-claude') {
        this.recordError('no-claude', this.resolved.message, 'claude not found');
      }
      this.blockedUntil = this.now() + 30000;
      return { ok: false, kind: 'no-claude', message: this.resolved.message };
    }
    if (this.transcript.entries.length === 0) {
      return { ok: false, kind: 'empty', message: '字幕がまだありません' };
    }

    this.inFlight = true;
    this.inFlightSince = this.now();
    const token = this.sessionToken;
    const startedAt = this.now();
    const notesVersion = this.notesVersion;
    const hasNotes = !!this.notes.trim();
    let snapshotLines = this.lastLineCount;
    let snapshotChars = this.lastTotalChars;
    let snapshotTextRev = this.lastTextRevision;

    // ここから先で何が起きても inFlight は必ず戻す（0.1 では窓の切り出しの例外で戻らず、
    // 以後ずっと整理が止まった）。例外は「内部エラー」として扱い、間をあけて次の回にやり直す
    let outcome;
    let meta = null;
    let inChars = 0;
    let outChars = 0;
    let range = '';
    try {
      const lines = this.transcript.lines(this.selfName());
      snapshotLines = lines.length;
      snapshotChars = this.transcript.totalChars();
      snapshotTextRev = this.transcript.textRevision;
      const win = buildWindow(lines, this.lastLineCount);
      const prompt = buildPrompt({
        promptMd: this.promptMd,
        notes: this.notes,
        prevBoard: this.board ? toPromptBoard(this.board) : null,
        range: win.range,
        lines: win.lines,
        users: this.usersLine(),
        spec: hasNotes ? this.notesSpec() : null,
      });
      inChars = prompt.length;
      range = win.range;
      const r = await callClaude({
        resolved: this.resolved,
        model: this.model,
        prompt,
        cwd: this.store.cwdDir(),
        timeoutMs: this.timeoutMs,
        state: this.claudeState,
        env: this.env,
      });
      if (r && r.ok) {
        meta = r.meta || null;
        outChars = typeof r.text === 'string' ? r.text.length : 0;
      }
      outcome = this.digest(r, hasNotes);
    } catch (e) {
      outcome = { ok: false, kind: 'internal', message: '内部エラー: ' + clip(errMsg(e), 160), detail: clip(errMsg(e), 160) };
    } finally {
      this.inFlight = false;
    }

    const endedAt = this.now();
    this.lastEndAt = endedAt;
    this.lastDurationMs = endedAt - startedAt;
    // 速さと費用の記録（数字だけ）。費用は返事があった回だけ足す
    const costUsd = meta && typeof meta.cost === 'number' ? meta.cost : null;
    const claudeMs = meta && typeof meta.ms === 'number' ? meta.ms : null;
    if (token === this.sessionToken) {
      if (costUsd !== null) {
        this.lastCostUsd = costUsd;
        this.totalCostUsd += costUsd;
      }
      if (claudeMs !== null) this.lastClaudeMs = claudeMs;
      this.safe(() =>
        this.store.appendUpdateLog({
          at: endedAt,
          reason: String(reason || ''),
          ok: !!outcome.ok,
          kind: outcome.ok ? '' : String(outcome.kind || ''),
          range,
          inChars,
          outChars,
          ms: this.lastDurationMs,
          claudeMs,
          costUsd,
        })
      );
    }

    if (token !== this.sessionToken) {
      // 呼び出しの最中に「新しい会議」が押された → 結果は捨てる
      return { ok: false, kind: 'stale', message: '新しい会議に切り替わったため捨てました' };
    }

    if (!outcome.ok) {
      this.failCount += 1;
      this.consecutiveFails += 1;
      const backoff =
        outcome.kind === 'usage-limit' ? 300000 : Math.min(300000, 20000 * Math.pow(2, this.consecutiveFails - 1));
      this.blockedUntil = endedAt + backoff;
      this.recordError(outcome.kind, outcome.message, outcome.detail || '');
      return { ok: false, kind: outcome.kind, message: outcome.message };
    }

    this.board = outcome.board;
    this.updateCount += 1;
    this.consecutiveFails = 0;
    this.blockedUntil = 0;
    this.lastUpdateAt = endedAt;
    this.lastError = null;
    this.lastLineCount = snapshotLines;
    this.lastTotalChars = snapshotChars;
    this.lastTextRevision = snapshotTextRev;
    if (this.notesVersion === notesVersion) this.notesDirty = false;
    this.safe(() => this.store.saveBoard(this.board));
    this.persist(true);
    this.log('board updated (' + reason + ')');
    return { ok: true, board: this.board };
  }

  /** claude の返事 → ボード or エラー */
  digest(r, hasNotes) {
    if (!r.ok) return r;
    const obj = extractJsonObject(r.text);
    if (!obj) {
      return {
        ok: false,
        kind: 'bad-json',
        message: 'claude の返事から JSON を取り出せませんでした。前のボードをそのまま残します。',
        detail: 'JSON が見つからない返事（' + r.text.length + ' 文字）',
      };
    }
    const norm = normalizeBoardV2(obj, { hasNotes, spec: this.notesSpec(), prev: this.board, users: this.userNames(), now: this.now() });
    if (!norm.ok) {
      return {
        ok: false,
        kind: 'bad-shape',
        message: 'claude の返事の形が想定と違いました（' + norm.error + '）。前のボードをそのまま残します。',
        detail: norm.error,
      };
    }
    return { ok: true, board: norm.board };
  }

  // ── 出力 ──────────────────────────────────────────────────
  captionState(now) {
    const last = this.transcript.lastCaptionAt;
    const extFresh = this.extStatus && now - this.extStatusAt <= EXT_FRESH_MS;
    if (this.replay && this.replay.active) return 'receiving';
    if (last > 0 && now - last <= CAPTION_FRESH_MS) return 'receiving';
    if (extFresh && this.extStatus.inCall === true && (this.extStatus.regionFound === false || this.extStatus.captionsOff === true)) {
      return 'missing';
    }
    if (last > 0) return 'stalled';
    if (extFresh || (this.extDiag && now - this.extDiagAt <= EXT_FRESH_MS)) return 'waiting';
    return now - this.startedAt > 20000 ? 'no-extension' : 'waiting';
  }

  stateJson() {
    const now = this.now();
    const sec = (t) => (t ? Math.max(0, Math.round((now - t) / 1000)) : null);
    return {
      status: {
        version: this.version,
        now,
        port: this.port,
        captions: {
          state: this.captionState(now),
          lastAt: this.transcript.lastCaptionAt || null,
          ageSec: sec(this.transcript.lastCaptionAt),
          entries: this.transcript.entries.length,
          chars: this.transcript.totalChars(),
        },
        update: {
          count: this.updateCount,
          lastAt: this.lastUpdateAt || null,
          ageSec: sec(this.lastUpdateAt),
          inFlight: this.inFlight,
          inFlightSince: this.inFlight ? this.inFlightSince : null,
          intervalSec: Math.round(this.intervalMs / 1000),
          pendingChars: this.pendingChars(),
          lastDurationMs: this.lastDurationMs,
          lastClaudeMs: this.lastClaudeMs,
          lastCostUsd: this.lastCostUsd,
          totalCostUsd: Math.round(this.totalCostUsd * 1e6) / 1e6,
          failures: this.failCount,
        },
        claude: {
          found: this.resolved.ok,
          version: this.claudeVer,
          flagSet: this.claudeState.flagSet,
          message: this.resolved.ok ? null : this.resolved.message,
        },
        selfCheck: this.selfCheck,
        lastError: this.lastError ? { at: this.lastError.at, kind: this.lastError.kind, message: this.lastError.message } : null,
        replay: this.replay,
      },
      board: this.board,
      recent: this.transcript.recent(30, this.selfName()),
      notesPresent: !!this.notes.trim(),
      selfName: this.settings.selfName || '',
    };
  }

  /** 字幕・名前・会議コードを含めない診断テキスト */
  diagText() {
    const now = this.now();
    const sec = (t) => (t ? Math.max(0, Math.round((now - t) / 1000)) : null);
    const speakers = new Set(this.transcript.entries.map((e) => e.speaker));
    const home = os.homedir();
    const info = {
      version: this.version,
      node: process.version,
      platform: os.platform(),
      osRelease: os.release(),
      arch: os.arch(),
      uptimeMin: Math.round((now - this.startedAt) / 60000),
      port: this.port,
      claude: {
        found: this.resolved.ok,
        display: this.resolved.ok ? shortenHome(this.resolved.display, home) : '',
        kind: this.resolved.ok ? this.resolved.kind : '',
        version: this.claudeVer,
        flagSet:
          this.claudeState.flagSet === 'minimal'
            ? 'minimal で動いた（-p --output-format json --model のみ。--tools / --safe-mode / --no-session-persistence は未対応の版）'
            : this.claudeState.confirmed
              ? 'full で動いた（-p --output-format json --model --tools "" --safe-mode --no-session-persistence）'
              : 'まだ確かめていない（最初の整理で full を試し、未対応の版なら minimal に落とす）',
        message: this.resolved.ok ? '' : this.resolved.message,
      },
      selfCheck: this.selfCheck.map((c) => ({ ok: c.ok, name: c.name, detail: this.scrub(c.detail) })),
      captions: {
        state: this.captionState(now),
        lastAgoSec: sec(this.transcript.lastCaptionAt),
        entries: this.transcript.entries.length,
        chars: this.transcript.totalChars(),
        speakers: speakers.size,
      },
      updates: {
        count: this.updateCount,
        failures: this.failCount,
        inFlight: this.inFlight,
        lastAgoSec: sec(this.lastUpdateAt),
        lastDurationMs: this.lastDurationMs,
        lastClaudeMs: this.lastClaudeMs,
        lastCostUsd: this.lastCostUsd,
        totalCostUsd: Math.round(this.totalCostUsd * 1e6) / 1e6,
        pendingChars: this.pendingChars(),
        notesPresent: !!this.notes.trim(),
      },
      errors: this.errors.map((e) => ({ agoSec: sec(e.at), kind: e.kind, detail: this.scrub(e.detail) })),
      ext: {
        status: this.extStatus,
        statusAgoSec: sec(this.extStatusAt),
        diag: this.extDiag ? this.scrubDeep(this.extDiag) : null,
        diagAgoSec: sec(this.extDiagAt),
      },
    };
    return buildDiagText(info);
  }

  /** 診断に出す文字列から、字幕・事前メモと同じ並び（8 文字以上）を含むものを消す */
  scrub(text) {
    const s = String(text == null ? '' : text);
    if (s.length < 8) return s;
    const grams = new Set();
    for (let i = 0; i + 8 <= s.length; i++) grams.add(s.slice(i, i + 8));
    const hits = (t) => {
      for (let i = 0; i + 8 <= t.length; i++) if (grams.has(t.slice(i, i + 8))) return true;
      return false;
    };
    for (const e of this.transcript.entries) if (hits(e.text)) return '（字幕の内容を含む可能性があるため省略）';
    if (this.notes && hits(this.notes)) return '（事前メモの内容を含む可能性があるため省略）';
    return s;
  }

  scrubDeep(v) {
    if (typeof v === 'string') return this.scrub(v);
    if (Array.isArray(v)) return v.map((x) => this.scrubDeep(x));
    if (v && typeof v === 'object') {
      const out = {};
      for (const k of Object.keys(v)) out[k] = this.scrubDeep(v[k]);
      return out;
    }
    return v;
  }

  // ── 起動時の点検（画面と診断に出す） ──────────────────────
  async runSelfCheck({ listenInfo, withVersion }) {
    const checks = [];
    const major = Number(process.versions.node.split('.')[0]);
    checks.push({ name: 'Node.js', ok: major >= 18, detail: process.version + (major >= 18 ? '' : '（18 以上が必要です）') });
    if (this.resolved.ok) {
      checks.push({ name: 'claude の場所', ok: true, detail: this.resolved.display });
      if (withVersion) {
        const v = await claudeVersion(this.resolved, this.env);
        if (v.ok) {
          this.claudeVer = v.version;
          checks.push({ name: 'claude の版', ok: true, detail: v.version });
        } else {
          checks.push({ name: 'claude の版', ok: false, detail: v.message });
        }
      }
    } else {
      checks.push({ name: 'claude', ok: false, detail: this.resolved.message });
    }
    if (listenInfo) checks.push(listenInfo);
    this.selfCheck = checks;
    return checks;
  }

  startLoop() {
    if (this.timer) return;
    this.timer = setInterval(() => this.tick(), 1000);
  }

  stopLoop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  shutdown() {
    this.stopLoop();
    this.persist(true);
  }
}

// 拡張機能から届いた診断を、構造だけに絞る（深さ・個数・文字数の上限）。
// 深さは、木の 1 段が「オブジェクト + 配列」で 2 つ数えられるので、4 段の木が入る大きさにしてある
function sanitizeDiag(v, depth) {
  if (depth > 16) return null;
  if (typeof v === 'string') return v.length > 160 ? v.slice(0, 160) + '…' : v;
  if (typeof v === 'number' || typeof v === 'boolean' || v === null) return v;
  if (Array.isArray(v)) return v.slice(0, 80).map((x) => sanitizeDiag(x, depth + 1));
  if (typeof v === 'object') {
    const out = {};
    for (const k of Object.keys(v).slice(0, 60)) out[k.slice(0, 40)] = sanitizeDiag(v[k], depth + 1);
    return out;
  }
  return null;
}

module.exports = { MeetingBoardApp, sanitizeDiag };
