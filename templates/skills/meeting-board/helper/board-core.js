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
      return { id: str(c.id), text: clip(stripEnd(c.item), ITEM_MAX), state: stt, label: stateLabel(c), next: !!(na && na.ref && na.ref === c.id) };
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
      return { id: str(c.id), no: i + 1, kind: c.kind === 'tell' ? 'tell' : 'ask', item: str(c.item), state: stateOf(c), label: stateLabel(c), evidence: str(c.evidence) };
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

  // 画面の欄の名前（役目そのものの言葉）と、初めて見る人向けの 1 行の説明
  var LABELS = {
    next: { title: '次の一手', help: '次に言うこと・聞くことを 1 つだけ。会議中はここだけ見れば足ります。' },
    warn: { title: '気をつけること', help: '話のずれ・事前メモの前提と違う発言・言い忘れのときだけ赤く出ます。返す一言つき。' },
    ok: { title: '順調', help: '警告が無いときは、進み具合を 1 行で出します。' },
    list: { title: '伝え済み／まだ', help: '事前メモの「今日聞くこと・伝えること」が、済んだか・持ち帰りか・まだかの一覧です。' },
    decisions: { title: '決まったこと', help: 'その場で合意がはっきりしたことだけ。' },
    todos: { title: '宿題（誰・いつまで）', help: '「誰が・何を」が言われた持ち帰りです。' },
    check: { title: '聞くこと・伝えることの結果', help: 'まだ・持ち帰りを上に、済は畳んであります。' },
    conflicts: { title: '前提と食い違ったこと', help: '事前メモの「こちらの理解」「前回の決定」と違うことを言われた記録です。' },
    open: { title: 'まだ答えをもらっていないこと', help: '会議の中で出たのに、まだ答えが出ていない問いです。' },
    topics: { title: '話題ごとの記録（ここまでの話）', help: '新しい話題が上。見出しを押すと、誰が何を言ったかが開きます。' },
    cards: { title: '今使えるメモ', help: '事前メモのうち、まだ言っていない・食い違っている、いま手元にあると助かるものです。' },
  };

  return {
    meetingView: meetingView,
    afterView: afterView,
    staleness: staleness,
    progressLine: progressLine,
    stateOf: stateOf,
    stateLabel: stateLabel,
    LABELS: LABELS,
    STALE_MIN_SEC: STALE_MIN_SEC,
  };
});
