'use strict';
// 「診断をコピー」の中身（GET /diag）。作者に送ってよいもの = 会議の発言・名前・会議コードを含まない。
// ここに渡す info は app.js が作る。字幕の本文は info に入れない（文字数だけ）。

function ago(sec) {
  if (sec === null || sec === undefined) return '（なし）';
  if (sec < 90) return sec + ' 秒前';
  return Math.round(sec / 60) + ' 分前';
}

function yesNo(v) {
  if (v === true) return 'はい';
  if (v === false) return 'いいえ';
  return '不明';
}

function buildDiagText(info) {
  const L = [];
  L.push('会議ボード 診断（会議の発言・名前・会議コードは入っていません）');
  L.push('');
  L.push('■ ヘルパー');
  L.push('  版: ' + info.version + ' / Node ' + info.node + ' / ' + info.platform + ' ' + info.osRelease + ' ' + info.arch);
  L.push('  稼働: ' + info.uptimeMin + ' 分 / ポート ' + info.port);
  L.push('');
  L.push('■ claude');
  if (info.claude.found) {
    L.push('  場所: ' + info.claude.display + '（' + info.claude.kind + '）');
    L.push('  版: ' + (info.claude.version || '（未確認）'));
  } else {
    L.push('  見つかりません: ' + info.claude.message);
  }
  L.push('  動いたオプション: ' + info.claude.flagSet);
  L.push('');
  L.push('■ 起動時の点検');
  for (const c of info.selfCheck) L.push('  ' + (c.ok ? 'OK' : 'NG') + ' ' + c.name + ' — ' + c.detail);
  L.push('');
  L.push('■ 字幕（件数と文字数だけ）');
  L.push('  状態: ' + info.captions.state + ' / 最後の受信: ' + ago(info.captions.lastAgoSec));
  L.push('  発言 ' + info.captions.entries + ' 件 / ' + info.captions.chars + ' 文字 / 話者 ' + info.captions.speakers + ' 人');
  L.push('');
  L.push('■ 整理（claude への依頼・この会議の分）');
  L.push('  成功 ' + info.updates.count + ' 回 / 失敗 ' + info.updates.failures + ' 回 / 実行中: ' + yesNo(info.updates.inFlight));
  L.push('  最後の成功: ' + ago(info.updates.lastAgoSec) + ' / 直近の所要: ' + (info.updates.lastDurationMs === null ? '（なし）' : Math.round(info.updates.lastDurationMs / 1000) + ' 秒'));
  L.push('  未反映の字幕: ' + info.updates.pendingChars + ' 文字 / 事前メモ: ' + (info.updates.notesPresent ? 'あり' : 'なし'));
  L.push('');
  L.push('■ 直近のエラー（新しい順・最大5件）');
  if (info.errors.length === 0) L.push('  なし');
  for (const e of info.errors) L.push('  ' + ago(e.agoSec) + ' [' + e.kind + '] ' + e.detail);
  L.push('');
  L.push('■ 拡張機能から届いた構造の情報（本文なし）');
  if (info.ext.status) {
    L.push('  状態の受信: ' + ago(info.ext.statusAgoSec) + ' → ' + JSON.stringify(info.ext.status));
  } else {
    L.push('  状態の受信: なし');
  }
  if (info.ext.diag) {
    L.push('  構造の受信: ' + ago(info.ext.diagAgoSec));
    L.push(JSON.stringify(info.ext.diag, null, 2).replace(/^/gm, '  '));
  } else {
    L.push('  構造の受信: なし（Meet のタブを開いて、通話に入ると届きます）');
  }
  L.push('');
  return L.join('\n');
}

module.exports = { buildDiagText };
