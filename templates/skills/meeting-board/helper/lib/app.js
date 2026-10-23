'use strict';
// ヘルパー本体の状態と動き（HTTP は httpserver.js、起動と引数は ../server.js）。
//
//   拡張機能 ──字幕──▶ Transcript ──(一定量たまったら)──▶ claude -p ──▶ ボード(JSON)
//
// ・claude の呼び出しは同時に 1 つだけ。タイムアウトは 120 秒
// ・失敗したら前のボードを残し、間をあけてやり直す（使い切りの上限に当たったら長めに待つ）
// ・claude が古くて安全のためのオプションを知らないときは、外して呼び直さず、以後は呼ばずに止める
// ・「会議を終える」: 最後の整理（全体）を 1 回行い、議事録の素を会議フォルダに書いて、以後は自動の整理をしない
// ・診断（GET /diag）には字幕の中身を入れない

const fs = require('fs');
const os = require('os');

const { Store } = require('./store');
const { Transcript, SELF_TOKEN } = require('./transcript');
const { buildWindow, buildWindowDiff, buildPrompt, shouldUpdate } = require('./prompt');
const { extractJsonObject } = require('./extract');
const { normalizeBoardV2, toPromptBoard, applyOverrides, mergePatch, detailTopicIds } = require('./board');
const { parseNotes } = require('./notes');
const { boardToMarkdown, transcriptInfo } = require('./minutes');
const { parseScript, locate, findClosingLine } = require('./script');
const { resolveClaude, callClaude, claudeVersion } = require('./claude');
const { buildDiagText } = require('./diag');
const { errMsg, clip, shortenHome } = require('./util');

const CAPTION_FRESH_MS = 20000; // これ以内に届いていれば「受信中」
const EXT_FRESH_MS = 30000; // 拡張機能の状態がこれ以内なら「いま見えている」とみなす
const MAX_NAME_LEN = 40;
const MAX_NOTES_LEN = 100000;
const BLOCKED_FOR_GOOD = Number.MAX_SAFE_INTEGER; // 古い claude: このプロセスの間は自動では呼び直さない

class MeetingBoardApp {
  constructor(options) {
    const o = options;
    this.version = o.version || '0.5.0';
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
    // 整理の仕方。'full' … 毎回全体／'diff' … 2 回目から「変わったところだけ」／
    // 'live' … 2 回目から会議中の画面の分だけ（話題は書かせない）。話題は数分おきと、字幕が止まったときに全体でまとめ直す。
    // 毎回全体を書き直させると、返事が長くなるほど 1 回が遅くなる（2026-10-23 の会議で 8 秒 → 20〜40 秒）
    this.mode = o.mode === 'diff' || o.mode === 'live' ? o.mode : 'full';
    const dir = require('path').dirname(o.promptPath);
    const patchPath = o.patchPromptPath || require('path').join(dir, 'prompt_patch.md');
    const livePath = o.livePromptPath || require('path').join(dir, 'prompt_live.md');
    this.patchMd = this.mode === 'diff' ? fs.readFileSync(patchPath, 'utf8') : this.mode === 'live' ? fs.readFileSync(livePath, 'utf8') : '';
    this.fullEvery = o.fullEvery || (this.mode === 'live' ? 1000 : 8); // 差分をこの回数続けたら、1 回は全体でまとめ直す
    this.fullEveryMs = o.fullEveryMs || (this.mode === 'live' ? 300000 : 600000); // または前の全体から 10 分（live は 5 分）たったら
    this.liveIdleMs = o.liveIdleMs || 45000; // live: 字幕がこれだけ止まったら、話題を全体でまとめ直す（会議の終わり）
    this.minGapMs = this.mode !== 'full' ? o.minGapMs || 8000 : 0; // 前倒しの整理の最短の間
    this.boardHtmlPath = o.boardHtmlPath;
    this.boardCorePath = o.boardCorePath || null;
    // 台本（--script）。claude には渡さない。いまの位置は字幕から規則で当てる
    this.scriptSections = o.script ? parseScript(o.script) : null;
    this.scriptManual = !!o.scriptManual; // 台本の位置は人が押したときだけ動かす
    this.scriptPos = null;
    this.closingLine = this.scriptSections ? findClosingLine(this.scriptSections) : null; // 最後に確かめる文（穴あき）
    this.me = o.me ? String(o.me).replace(/\s+/g, ' ').trim().slice(0, MAX_NAME_LEN) : ''; // --me（字幕に出る自分の名前）

    this.store = new Store(o.dataDir);
    this.settings = this.store.loadSettings();
    this.resolved = resolveClaude({ env: this.env });
    this.claudeState = {}; // callClaude が持ち回る（返事が来たら confirmed = true）
    this.claudeUnusable = ''; // 古くて安全のためのオプションを知らない claude のとき、その案内文（空なら問題なし）
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
    this.blockedBy = ''; // blockedUntil まで待つ原因（失敗の kind）
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
    this.finishing = null; // 「会議を終える」の最中〜終わったあとの Promise（二度押しは同じものを返す）
    this.finishInfo = null; // 同じ結果の中身（null のあいだは会議中）
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
    this.overrides = {}; // 人が手で直した聞くことの状態 { q1: { state, owner, at } }（会議ごと）
    this.notes = notes || '';
    this.notesVersion = 0;
    this.notesDirty = false;
    this.lastLineCount = 0;
    this.lastTotalChars = 0;
    this.lastTextRevision = 0;
    this.lastEntryCount = 0;
    this.diffsSinceFull = 0;
    this.lastFullAt = now;
    this.forceFull = false;
    this.lastMode = null;
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
    this.blockedBy = '';
    this.finishing = null; // 「会議を終える」の状態は会議ごと（新しい会議では自動の整理が戻る）
    this.finishInfo = null;
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
      this.updateScriptPos();
      this.persist(false);
      if (this.finishInfo) return; // 「会議を終える」を押したあとは、自動の整理をしない（字幕の記録は続く）
      let reason = shouldUpdate({
        inFlight: this.inFlight,
        now,
        lastEndAt: this.lastEndAt,
        blockedUntil: this.blockedUntil,
        newChars: this.pendingChange(),
        intervalMs: this.intervalMs,
        notesDirty: this.notesDirty,
        hasTranscript: this.transcript.entries.length > 0,
        speakerTurns: this.transcript.speakerTurnsSince(this.lastEntryCount),
        minGapMs: this.board ? this.minGapMs : 0,
      });
      // live: 字幕が止まったら（会議の終わり）、短い版のままの話題を全体でまとめ直す
      if (
        !reason &&
        this.mode === 'live' &&
        this.lastMode === 'live' &&
        !this.inFlight &&
        now >= this.blockedUntil &&
        now - this.lastEndAt >= 5000 &&
        this.transcript.lastCaptionAt > 0 &&
        now - this.transcript.lastCaptionAt >= this.liveIdleMs
      ) {
        reason = 'flush';
      }
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
    if (this.claudeUnusable) {
      // 古い claude: 外して呼ぶことはしない。呼ばずに、案内を出し続ける
      if (!this.lastError || this.lastError.kind !== 'unknown-flag') {
        this.recordError('unknown-flag', this.claudeUnusable, this.claudeUnusable);
      }
      this.blockedUntil = this.now() + 30000;
      return { ok: false, kind: 'unknown-flag', message: this.claudeUnusable };
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
    let snapshotEntries = this.lastEntryCount;
    // 差分にするか: 2 回目から。全体に戻すのは、まとめ直しの時期・再生の終わり・--once・事前メモが変わった・前の差分がおかしかったとき
    const useDiff =
      this.mode !== 'full' &&
      !!this.board &&
      !this.forceFull &&
      ['once', 'flush', 'notes', 'final'].indexOf(reason) < 0 &&
      this.diffsSinceFull < this.fullEvery &&
      startedAt - this.lastFullAt < this.fullEveryMs;
    const compactIds = new Set();

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
      snapshotEntries = this.transcript.entries.length;
      const win = useDiff ? buildWindowDiff(lines, this.lastLineCount) : buildWindow(lines, this.lastLineCount);
      let prevBoard = null;
      if (this.board) {
        if (useDiff && this.mode === 'live') {
          // 短い版: 話題は見出しだけ渡し、中身は返させない（ヘルパーが前回のまま残す）
          for (const t of this.board.topics) compactIds.add(t.id);
          prevBoard = toPromptBoard(this.board, { detailIds: new Set() });
        } else if (useDiff) {
          const detail = detailTopicIds(this.board);
          for (const t of this.board.topics) if (!detail.has(t.id)) compactIds.add(t.id);
          prevBoard = toPromptBoard(this.board, { detailIds: detail });
        } else prevBoard = toPromptBoard(this.board);
      }
      const prompt = buildPrompt({
        promptMd: useDiff ? this.promptMd.replace(/\s+$/, '') + '\n\n' + this.patchMd : this.promptMd,
        notes: this.notes,
        prevBoard,
        range: win.range,
        lines: win.lines,
        users: this.usersLine(),
        spec: hasNotes ? this.notesSpec() : null,
        closing: this.closingLine ? this.closingLine.text : null,
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
      outcome = this.digest(r, hasNotes, useDiff ? { compactIds } : null);
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
          mode: useDiff ? this.mode : 'full',
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
      if (useDiff && (outcome.kind === 'bad-json' || outcome.kind === 'bad-shape')) this.forceFull = true; // 次は全体で
      this.failCount += 1;
      this.consecutiveFails += 1;
      const backoff =
        outcome.kind === 'usage-limit' ? 300000 : Math.min(300000, 20000 * Math.pow(2, this.consecutiveFails - 1));
      if (outcome.kind === 'unknown-flag') {
        // 古い claude は、待っても直らない（claude update と起動し直しが要る）。以後は呼ばない
        this.claudeUnusable = outcome.message;
        this.blockedUntil = BLOCKED_FOR_GOOD;
      } else this.blockedUntil = endedAt + backoff;
      this.blockedBy = outcome.kind;
      this.recordError(outcome.kind, outcome.message, outcome.detail || '');
      return { ok: false, kind: outcome.kind, message: outcome.message };
    }

    this.board = outcome.board;
    this.updateCount += 1;
    this.consecutiveFails = 0;
    this.blockedUntil = 0;
    this.blockedBy = '';
    this.lastUpdateAt = endedAt;
    this.lastError = null;
    this.lastLineCount = snapshotLines;
    this.lastTotalChars = snapshotChars;
    this.lastTextRevision = snapshotTextRev;
    this.lastEntryCount = snapshotEntries;
    this.lastMode = useDiff ? this.mode : 'full';
    if (useDiff) this.diffsSinceFull += 1;
    else {
      this.diffsSinceFull = 0;
      this.lastFullAt = endedAt;
      this.forceFull = false;
    }
    if (this.notesVersion === notesVersion) this.notesDirty = false;
    this.safe(() => this.store.saveBoard(this.board));
    this.persist(true);
    this.log('board updated (' + reason + ')');
    return { ok: true, board: this.board };
  }

  /** claude の返事 → ボード or エラー */
  digest(r, hasNotes, diff) {
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
    let raw = obj;
    if (diff) {
      // 差分の返事を前回のボードに重ねる（全体の形で返ってきても同じく重ねる。省いて渡した話題の中身を消さないため）
      raw = mergePatch(this.board, obj, diff);
      if (!raw) {
        return {
          ok: false,
          kind: 'bad-shape',
          message: 'claude の差分の返事の形が想定と違いました。前のボードを残し、次は全体で整理し直します。',
          detail: 'patch の形が違う',
        };
      }
    }
    const norm = normalizeBoardV2(raw, { hasNotes, spec: this.notesSpec(), prev: this.board, users: this.userNames(), now: this.now(), closing: !!this.closingLine });
    if (!norm.ok) {
      return {
        ok: false,
        kind: 'bad-shape',
        message: 'claude の返事の形が想定と違いました（' + norm.error + '）。前のボードをそのまま残します。',
        detail: norm.error,
      };
    }
    return { ok: true, board: applyOverrides(norm.board, this.overrides, { spec: this.notesSpec() }) };
  }

  /**
   * 人が聞くことの状態を直す（済／持ち帰り／まだ。'auto' で claude の判断に戻す）。
   * 戻り値: { ok:true, board } | { ok:false, status, error }
   */
  setOverride(id, state, owner) {
    const key = String(id == null ? '' : id).slice(0, 20);
    const known = new Set(this.notesSpec().items.map((x) => x.id));
    if (this.board) for (const c of this.board.checklist || []) known.add(c.id);
    if (!known.has(key)) return { ok: false, status: 404, error: 'その項目は聞くことの表にありません' };
    if (state === 'auto') delete this.overrides[key];
    else if (['done', 'deferred', 'open'].indexOf(state) >= 0) {
      this.overrides[key] = { state, owner: String(owner == null ? '' : owner).replace(/\s+/g, ' ').trim().slice(0, 40), at: this.now() };
    } else return { ok: false, status: 400, error: 'state は done / deferred / open / auto のどれかです' };
    this.safe(() => this.store.saveOverrides(this.overrides));
    if (this.board) {
      this.board = applyOverrides(this.board, this.overrides, { spec: this.notesSpec() });
      this.safe(() => this.store.saveBoard(this.board));
    }
    return { ok: true, board: this.board };
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
    const out = {
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
          mode: this.mode,
          lastMode: this.lastMode,
          failures: this.failCount,
        },
        finish: this.finishStatus(),
        claude: {
          found: this.resolved.ok,
          version: this.claudeVer,
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
    // 台本は --script のときだけ（診断には入れない）
    if (this.scriptSections) out.script = { sections: this.scriptSections, pos: this.scriptPos || this.updateScriptPos(), closing: this.closingLine };
    return out;
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
        safetyFlags: this.claudeUnusable
          ? '古くて使えない（--tools / --safe-mode / --no-session-persistence を知らない版。外しての実行はしない）'
          : this.claudeState.confirmed
            ? '付けて動いた（-p --output-format json --model --tools "" --safe-mode --no-session-persistence）'
            : 'まだ確かめていない（最初の整理から、安全のためのオプションを付けて呼ぶ。知らない版なら止まる）',
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

  /** 台本のいまの位置を、直近の字幕から当て直す（tick ごと・claude は使わない） */
  updateScriptPos() {
    if (!this.scriptSections) return null;
    if (this.scriptManual) return this.scriptPos || (this.scriptPos = { sectionIndex: 0, lineIndex: -1, by: 'manual', score: 1 });
    const entries = this.transcript.entries;
    const first = entries.length ? entries[0].firstSeen : 0;
    const elapsed = first ? Math.max(0, (this.now() - first) / 1000) : null;
    let recent = this.transcript.recent(40, this.selfName());
    if (this.scriptPin) {
      // 人が位置を決めたあとは、そのあとに増えた字幕だけで位置を当てる（決めた位置へ前の字幕で引き戻さない）
      const pin = this.scriptPin;
      recent = entries
        .slice(-40)
        .map((e) => {
          const before = pin.has(e.id) ? pin.get(e.id) : 0;
          const text = String(e.text || '').slice(before);
          return { speaker: e.speaker === SELF_TOKEN ? this.selfName() : e.speaker || '不明', text, at: e.lastUpdate || e.firstSeen };
        })
        .filter((c) => c.text.trim().length >= 4);
      if (!recent.length) return this.scriptPos;
    }
    this.scriptPos = locate(this.scriptSections, recent, elapsed, this.scriptPos, { me: this.me || this.selfName() });
    return this.scriptPos;
  }

  /** 人が台本の位置を決める（台詞・節を押したとき）。lineIndex が -1 なら節の頭 */
  setScriptPos(sectionIndex, lineIndex) {
    const secs = this.scriptSections;
    const si = Number(sectionIndex);
    const li = lineIndex === undefined || lineIndex === null ? -1 : Number(lineIndex);
    if (!secs || !Number.isInteger(si) || si < 0 || si >= secs.length) return { ok: false, status: 400, error: '節の番号が台本にありません' };
    if (!Number.isInteger(li) || li < -1 || li >= secs[si].lines.length) return { ok: false, status: 400, error: '台詞の番号が台本にありません' };
    this.scriptPin = new Map(this.transcript.entries.map((e) => [e.id, String(e.text || '').length]));
    this.scriptPos = { sectionIndex: si, lineIndex: li, by: 'manual', score: 1 };
    return { ok: true };
  }

  // ── 会議を終える ──────────────────────────────────────────
  /** いま claude を呼んでも通らない状態か（見つからない・古い版・利用上限の待ち時間のあいだ） */
  claudeBlocked() {
    if (!this.resolved.ok || this.claudeUnusable) return true;
    return this.blockedBy === 'usage-limit' && this.now() < this.blockedUntil;
  }

  /** 整理の最中なら、終わるまで待つ（claude のタイムアウトで必ず終わる） */
  async waitIdle() {
    while (this.inFlight) await new Promise((resolve) => setTimeout(resolve, 50));
  }

  /** 最後の整理をしない理由。'' なら整理する */
  finalSkipReason() {
    if (this.transcript.entries.length === 0) return 'no-captions';
    // 直近の整理が全体で、そのあとに字幕が増えていない → 全体の整理は新しいまま
    // （会議中の短い版のあとは、話題が全体でまとめ直されていないので、字幕が増えていなくても整理する）
    if (this.board && this.lastMode === 'full' && this.pendingChange() === 0) return 'no-new';
    if (this.claudeBlocked()) return 'blocked';
    return '';
  }

  /**
   * 「会議を終える」: 整理の最中なら終わるのを待ち、全体の整理を 1 回（reason 'final'）行い、
   * 議事録の素（minutes.md）を会議フォルダに書く。以後、この会議では自動の整理をしない（字幕の記録は続く）。
   * 字幕が増えていない・claude が使えないときは、整理せずに今あるものを保存する。
   * 二度押しや、終わったあとの呼び直しは、同じ Promise を返すだけで、整理は 1 回しか走らない。
   * 戻り値の Promise は決して reject しない。「新しい会議」に切り替わったら null。
   */
  finishMeeting() {
    if (this.finishing) return this.finishing;
    this.finishInfo = { phase: 'finishing' }; // 先に印を付ける（この間に tick が整理を始めないように）
    this.finishing = this.runFinish(this.sessionToken);
    return this.finishing;
  }

  async runFinish(token) {
    const info = { phase: 'done', at: 0, rebuild: 'skipped', skip: '', error: '', hasBoard: false, minutesPath: '', minutesError: '' };
    try {
      await this.waitIdle();
      if (token !== this.sessionToken) return null;
      info.skip = this.finalSkipReason();
      if (!info.skip) {
        const r = await this.runUpdate('final');
        if (token !== this.sessionToken) return null;
        if (r.ok) info.rebuild = 'done';
        else {
          info.rebuild = 'failed';
          info.error = r.message || '';
        }
      }
    } catch (e) {
      if (token !== this.sessionToken) return null;
      info.rebuild = 'failed';
      info.error = '内部エラー: ' + clip(errMsg(e), 160);
      this.recordError('internal', info.error, clip(errMsg(e), 160));
    }
    // ここから先は await が無い（途中で「新しい会議」に切り替わることはない）
    this.persist(true);
    info.hasBoard = !!this.board;
    try {
      const md = boardToMarkdown(this.board, transcriptInfo(this.transcript.toJsonl(), this.selfName()));
      info.minutesPath = this.store.saveMinutes(md);
    } catch (e) {
      info.minutesError = clip(errMsg(e), 120);
      this.recordError('save', '議事録の素を保存できませんでした（' + info.minutesError + '）', info.minutesError);
    }
    info.at = this.now();
    this.finishInfo = info;
    this.log('meeting finished (' + (info.skip || info.rebuild) + ')');
    return info;
  }

  /** 画面に渡す「会議を終える」の状態（押していなければ null） */
  finishStatus() {
    return this.finishInfo ? Object.assign({}, this.finishInfo) : null;
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
