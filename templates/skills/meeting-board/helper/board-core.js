/* board-core.js — ボードの画面に「何を出すか」を決める（DOM には触らない純粋な関数だけ）
 *
 * board.html（ブラウザ）と Node の試験の両方から読む。
 *   ブラウザ: globalThis.MeetingBoardView  /  Node: module.exports
 * ヘルパーは GET / のとき、board.html の印（BOARD_CORE のコメント）をこのファイルの中身に差し替えて配る
 * （1 ファイル・外部リソースなしのまま）。
 *
 * 画面は 2 つ:
 *   会議中（既定）… ① 次の一手（青・1 行・大きい字。いつも出す）② 警告（赤。あるときだけ）
 *                   ③ 順調（緑。警告が無いとき）④ 伝え済み／まだ（短い一覧）＋右上に「あと○つ」
 *   会議の前と後 … 決まったこと・宿題・聞くことの結果・前提と食い違ったこと・まだ答えをもらっていないこと・
 *                   話題ごとの記録（新しい順・見出し 1 行で畳む）・今使えるメモ
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.MeetingBoardView = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var STALE_MIN_SEC = 180; // 整理がこれより古く、字幕は進んでいる → 「○分前の内容」と薄く出す
  var ITEM_MAX = 26; // 「伝え済み／まだ」の一覧の 1 項目の長さ

  function arr(v) {
    return Array.isArray(v) ? v : [];
  }
  function str(v) {
    return v === null || v === undefined ? '' : String(v);
  }
  function clip(s, n) {
    s = str(s);
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }
  function pad(n) {
    return (n < 10 ? '0' : '') + n;
  }
  function clockSec(ms) {
    var d = new Date(ms);
    return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }
  function stripEnd(s) {
    return str(s).replace(/[。．.]+$/, '');
  }

  /** 聞くことの表の状態（0.1 の形 { done } も読む） */
  function stateOf(c) {
    if (c && (c.state === 'done' || c.state === 'deferred' || c.state === 'open')) return c.state;
    return c && c.done === true ? 'done' : 'open';
  }

  function stateLabel(c) {
    var st = stateOf(c);
    if (st === 'done') return c.kind === 'tell' ? '伝え済み' : '済';
    if (st === 'deferred') return '持ち帰り' + (c.owner ? '（' + c.owner + '）' : '');
    return 'まだ';
  }

  /** 古い内容か: 整理でエラーが出ている、または最後の成功から時間がたっているのに字幕は進んでいる */
  function staleness(status, board, now) {
    var out = { stale: false, minutes: 0, text: '' };
    if (!board || !status || !status.update) return out;
    var u = status.update;
    var t = typeof now === 'number' ? now : status.now;
    var lastAt = u.lastAt || 0;
    var ageSec = lastAt ? Math.max(0, Math.round((t - lastAt) / 1000)) : null;
    var limit = Math.max(STALE_MIN_SEC, (u.intervalSec || 60) * 3);
    var moving = (u.pendingChars || 0) > 0 || (status.captions && status.captions.state === 'receiving');
    var errored = !!status.lastError;
    if (errored || (ageSec !== null && ageSec > limit && moving)) {
      out.stale = true;
      out.minutes = ageSec === null ? 0 : Math.max(1, Math.round(ageSec / 60));
      out.text = ageSec === null ? '古い内容' : out.minutes + '分前の内容';
    }
    return out;
  }

  /** 順調の 1 行。claude が書いた status が無ければ、聞くことの表から作る */
  function progressLine(board) {
    var s = str(board && board.status).trim();
    if (s) return s;
    var list = arr(board && board.checklist);
    if (!list.length) return '';
    var n = { done: 0, deferred: 0, open: 0 };
    list.forEach(function (c) {
      n[stateOf(c)] += 1;
    });
    return '済 ' + n.done + '・持ち帰り ' + n.deferred + '・まだ ' + n.open;
  }

  /** 会議中の一覧の項目を押したときの次の状態（まだ → 済 → 持ち帰り → まだ） */
  function nextState(state) {
    return state === 'open' ? 'done' : state === 'done' ? 'deferred' : 'open';
  }

  var WARN_LABEL = { drift: '話がずれています', premise: '前提と違います', missing: '言い忘れそうです' };

  /**
   * 会議中の画面に出すもの。state は GET /state の中身。
   * 戻り値: { next, warning, ok, items, left, stale, updating, updatedText }
   */
  function meetingView(state, now) {
    var st = state || {};
    var s = st.status || {};
    var board = st.board || null;
    var t = typeof now === 'number' ? now : s.now || 0;

    // ① 次の一手（いつも出す。無いときは何をすれば出るかを書く）
    var next;
    var na = board && board.next_action;
    if (na && str(na.text)) {
      next = { text: str(na.text), reason: str(na.reason), placeholder: false };
    } else if (!st.notesPresent) {
      next = { text: '事前メモに「今日聞くこと・伝えること」を貼ると、ここに次の一手が出ます', reason: '', placeholder: true };
    } else if (!board) {
      next = { text: '字幕が届くと、ここに次の一手が出ます', reason: '', placeholder: true };
    } else {
      next = { text: '話の流れを聞いています', reason: '', placeholder: true };
    }

    // ② 警告（あるときだけ。1 つだけ大きく、ほかは件数）
    var warns = arr(board && board.warnings).filter(function (w) {
      return w && str(w.what) && str(w.reply);
    });
    var warning = null;
    if (warns.length) {
      var w = warns[0];
      warning = {
        label: WARN_LABEL[w.kind] || '気をつけること',
        what: (w.speaker ? w.speaker + '：' : '') + str(w.what),
        reply: str(w.reply),
        more: warns.length - 1,
      };
    }

    // ③ 順調（警告が無いとき）
    var ok = null;
    if (!warning && board) {
      var line = progressLine(board);
      ok = { text: line || '話は進んでいます' };
    }

    // ④ 伝え済み／まだ（事前メモの順のまま。並びは更新で動かさない）＋ あと○つ
    var list = arr(board && board.checklist);
    var items = list.map(function (c) {
      var stt = stateOf(c);
      return { id: str(c.id), text: clip(stripEnd(c.item), ITEM_MAX), state: stt, label: stateLabel(c), next: !!(na && na.ref && na.ref === c.id), byUser: !!c.byUser };
    });
    var openCount = items.filter(function (x) {
      return x.state === 'open';
    }).length;
    var deferredCount = items.filter(function (x) {
      return x.state === 'deferred';
    }).length;
    var left = '';
    if (list.length) {
      if (openCount) left = 'あと' + openCount + 'つ';
      else left = deferredCount ? 'あと0・持ち帰り' + deferredCount : '全部済';
    }

    var u = s.update || {};
    var updating = !!u.inFlight;
    var updatedText = u.lastAt ? '最終更新 ' + clockSec(u.lastAt) + '（更新 ' + (u.count || 0) + ' 回）' : 'まだ整理していません';
    return {
      next: next,
      warning: warning,
      ok: ok,
      items: items,
      left: left,
      stale: staleness(s, board, t),
      updating: updating,
      updatedText: updatedText,
    };
  }

  /** 使う人の発言か（話題ごとの記録では、自分の発言は数だけにする） */
  function isUser(board, speaker, selfName) {
    var names = arr(board && board.users).slice();
    if (selfName) names.push(selfName);
    names.push('自分');
    return names.indexOf(str(speaker)) >= 0;
  }

  /**
   * 会議の前と後の画面に出すもの。
   * 戻り値: { decisions, todos, checkOpen, checkDone, conflicts, openQuestions, topics, cards, counts }
   */
  function afterView(state) {
    var st = state || {};
    var board = st.board || null;
    var topics = arr(board && board.topics);
    var decisions = [];
    var todos = [];
    topics.forEach(function (tp) {
      arr(tp.decisions).forEach(function (d) {
        decisions.push({ text: str(d), topic: str(tp.title) });
      });
      arr(tp.todos).forEach(function (d) {
        todos.push({ who: str(d.who), what: str(d.what), when: str(d.when), topic: str(tp.title) });
      });
    });
    var list = arr(board && board.checklist).map(function (c, i) {
      return { id: str(c.id), no: i + 1, kind: c.kind === 'tell' ? 'tell' : 'ask', item: str(c.item), state: stateOf(c), label: stateLabel(c), evidence: str(c.evidence), byUser: !!c.byUser };
    });
    var shownTopics = topics
      .map(function (tp) {
        var pts = arr(tp.points);
        var mine = pts.filter(function (p) {
          return isUser(board, p.speaker, st.selfName);
        });
        var others = pts.filter(function (p) {
          return !isUser(board, p.speaker, st.selfName);
        });
        var head = str(tp.headline) || (others[0] ? clip(others[0].text, 40) : '');
        return {
          id: str(tp.id) || str(tp.title),
          title: str(tp.title),
          headline: head,
          current: !!tp.current,
          points: others,
          hiddenSelf: mine.length,
          decisions: arr(tp.decisions).map(str),
          todos: arr(tp.todos),
          numbers: arr(tp.numbers).map(str),
        };
      })
      .reverse(); // 新しい話題を上に
    return {
      decisions: decisions,
      todos: todos,
      checkOpen: list.filter(function (c) {
        return c.state !== 'done';
      }),
      checkDone: list.filter(function (c) {
        return c.state === 'done';
      }),
      conflicts: arr(board && board.premise_conflicts).map(function (k) {
        return { premise: str(k.premise), kind: str(k.kind), heard: str(k.heard), speaker: str(k.speaker), reply: str(k.reply), settled: !!k.settled };
      }),
      openQuestions: arr(board && board.open_questions).map(str),
      topics: shownTopics,
      cards: arr(board && board.cards),
      counts: { topics: topics.length, checklist: list.length },
    };
  }

  /**
   * 「会議を終える」を押したあとの案内。state.status.finish = null | { phase, rebuild, skip, error, hasBoard, minutesPath, minutesError }。
   * 戻り値: null（押していない）| { phase: 'finishing'|'done', title, lines: [文], path: 保存したファイルの場所（無ければ ''） }
   */
  function finishView(state) {
    var f = state && state.status ? state.status.finish : null;
    if (!f || typeof f !== 'object') return null;
    if (f.phase !== 'done') {
      return {
        phase: 'finishing',
        title: '会議を終えています…',
        lines: ['いまの整理が終わるのを待ち、全体をもう一度まとめ直して、議事録の素を保存します。数十秒かかることがあります。'],
        path: '',
      };
    }
    var lines = [];
    if (f.rebuild === 'done') lines.push('最後に、全体を整理し直しました。');
    else if (f.rebuild === 'failed') {
      lines.push('最後の整理に失敗しました' + (f.error ? '（' + clip(f.error, 120) + '）' : '') + '。ここまでに作ったボードを保存しました。');
    } else if (f.skip === 'no-captions') lines.push('字幕がありませんでした。');
    else if (f.skip === 'no-new') lines.push('前の整理のあとに増えた字幕がないので、整理し直さず、いまのボードを保存しました。');
    else if (f.skip === 'blocked') {
      lines.push('Claude が使えない状態（利用上限・古い版・見つからない、のどれか。理由は上の赤い帯）なので、最後の整理はせず、ここまでに作ったボードを保存しました。');
    } else lines.push('整理し直さず、いまのボードを保存しました。');
    var path = str(f.minutesPath);
    if (path) {
      lines.push('議事録の素を保存しました。自動字幕からの下書きです。外に出す前に必ず見直してください。');
      if (!f.hasBoard) lines.push('整理がまだ一度もできていないので、中身は日時と名前だけです。');
    } else {
      lines.push('議事録の素を保存できませんでした' + (f.minutesError ? '（' + clip(f.minutesError, 120) + '）' : '') + '。あとで --minutes で書き出せます。');
    }
    lines.push('この画面は読めるままです。もう閉じてかまいません。ヘルパーを止めるときは、黒い画面で Ctrl+C。');
    lines.push('これ以降は自動の整理をしません。続けて別の会議をするときは、下の「新しい会議」を押してください。');
    return { phase: 'done', title: '会議を終えました', lines: lines, path: path };
  }

  /**
   * 台本の欄（--script のときだけ）。state.script = { sections, pos }。
   * 戻り値: null | { title, sectionIndex, total, by, lines: [{ kind, text, who, status: 'past'|'current'|'next'|'later' }],
   *                  all: [{ index, title, start, current }], captions: 直近 6 行 [{ speaker, text }] }
   */
  function scriptView(state) {
    var st = state || {};
    var sc = st.script;
    if (!sc || !Array.isArray(sc.sections) || !sc.sections.length) return null;
    var pos = sc.pos || { sectionIndex: 0, lineIndex: -1, by: 'none' };
    var si = pos.sectionIndex >= 0 && pos.sectionIndex < sc.sections.length ? pos.sectionIndex : 0;
    var sec = sc.sections[si];
    var li = si === pos.sectionIndex ? pos.lineIndex : -1;
    // 次に言う台詞: いまの行より後で最初の台詞
    var nextIdx = -1;
    for (var i = li + 1; i < sec.lines.length; i++) {
      if (sec.lines[i].kind === 'say') {
        nextIdx = i;
        break;
      }
    }
    var lines = sec.lines.map(function (l, i) {
      var status = i === li ? 'current' : i < li ? 'past' : i === nextIdx ? 'next' : 'later';
      return { kind: l.kind, text: str(l.text), who: str(l.who), status: status };
    });
    function mmss(t) {
      if (typeof t !== 'number') return '';
      return Math.floor(t / 60) + ':' + pad(t % 60);
    }
    return {
      title: str(sec.title),
      start: mmss(sec.startSec),
      sectionIndex: si,
      total: sc.sections.length,
      by: pos.by || 'none',
      lines: lines,
      all: sc.sections.map(function (s, i) {
        return { index: i, title: str(s.title), start: mmss(s.startSec), current: i === si };
      }),
      // 最後に確かめる文（台本に穴あきの確かめの文があるときだけ）。候補が無ければ穴あきのまま
      closing: sc.closing
        ? {
            template: str(sc.closing.text),
            candidates: arr(st.board && st.board.closing_candidates)
              .filter(function (c) {
                return c && str(c.text);
              })
              .slice(0, 3)
              .map(function (c) {
                return { text: str(c.text), why: str(c.why) };
              }),
          }
        : null,
      captions: arr(st.recent)
        .slice(-6)
        .map(function (r) {
          return { speaker: str(r.speaker), text: str(r.text) };
        }),
    };
  }

  // 画面の欄の名前（役目そのものの言葉）と、初めて見る人向けの 1 行の説明
  var LABELS = {
    next: { title: '次の一手', help: '次に言うこと・聞くことを 1 つだけ。会議中はここだけ見れば足ります。' },
    warn: { title: '気をつけること', help: '話のずれ・事前メモの前提と違う発言・言い忘れのときだけ赤く出ます。返す一言つき。' },
    ok: { title: '順調', help: '警告が無いときは、進み具合を 1 行で出します。' },
    list: { title: '伝え済み／まだ', help: '事前メモの「今日聞くこと・伝えること」が、済んだか・持ち帰りか・まだかの一覧です。違っていたら項目を押すと、まだ→済→持ち帰り の順に直せます。' },
    decisions: { title: '決まったこと', help: 'その場で合意がはっきりしたことだけ。' },
    todos: { title: '宿題（誰・いつまで）', help: '「誰が・何を」が言われた持ち帰りです。' },
    check: { title: '聞くこと・伝えることの結果', help: 'まだ・持ち帰りを上に、済は畳んであります。状態が違っていたら、右のボタンで直せます（手で直した状態は整理より優先します）。' },
    conflicts: { title: '前提と食い違ったこと', help: '事前メモの「こちらの理解」「前回の決定」と違うことを言われた記録です。' },
    open: { title: 'まだ答えをもらっていないこと', help: '会議の中で出たのに、まだ答えが出ていない問いです。' },
    topics: { title: '話題ごとの記録（ここまでの話）', help: '新しい話題が上。見出しを押すと、誰が何を言ったかが開きます。' },
    cards: { title: '今使えるメモ', help: '事前メモのうち、まだ言っていない・食い違っている、いま手元にあると助かるものです。' },
  };

  return {
    meetingView: meetingView,
    scriptView: scriptView,
    finishView: finishView,
    afterView: afterView,
    staleness: staleness,
    progressLine: progressLine,
    stateOf: stateOf,
    stateLabel: stateLabel,
    nextState: nextState,
    LABELS: LABELS,
    STALE_MIN_SEC: STALE_MIN_SEC,
  };
});
