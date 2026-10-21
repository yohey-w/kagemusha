'use strict';
// 保存先（<data-dir>）の読み書き。会議ごとにフォルダを切る:
//   <data-dir>/<開始時刻>/transcript.jsonl  字幕（1 発言 1 行）
//   <data-dir>/<開始時刻>/board.json        最新の「ここまでの話」
//   <data-dir>/<開始時刻>/notes.md          事前メモ
//   <data-dir>/settings.json                自分の表示名
//   <data-dir>/_cwd/                        claude を走らせる空のフォルダ
// data/ の中身は .gitignore で「コミットできない」ようにしてある。

const fs = require('fs');
const path = require('path');
const { sessionStamp } = require('./util');

function writeFileAtomic(file, text) {
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, text, 'utf8');
  try {
    fs.renameSync(tmp, file);
  } catch (e) {
    // Windows でウイルス対策などが掴んでいると rename が失敗することがある → 直接書く
    fs.writeFileSync(file, text, 'utf8');
    try {
      fs.unlinkSync(tmp);
    } catch (_) {
      /* 無くてよい */
    }
  }
}

class Store {
  constructor(dataDir) {
    this.dataDir = dataDir;
    this.sessionDir = null;
    fs.mkdirSync(dataDir, { recursive: true });
    this.ensureIgnoreFile();
  }

  // data/ が空の新規フォルダでも、中身をコミットできないようにしておく
  ensureIgnoreFile() {
    const f = path.join(this.dataDir, '.gitignore');
    if (!fs.existsSync(f)) {
      try {
        fs.writeFileSync(f, '*\n!.gitignore\n', 'utf8');
      } catch (_) {
        /* 書けなくても動作には影響しない */
      }
    }
  }

  cwdDir() {
    const d = path.join(this.dataDir, '_cwd');
    fs.mkdirSync(d, { recursive: true });
    return d;
  }

  startSession(ms) {
    let name = sessionStamp(ms);
    let dir = path.join(this.dataDir, name);
    let n = 2;
    while (fs.existsSync(dir)) {
      dir = path.join(this.dataDir, name + '-' + n);
      n += 1;
    }
    fs.mkdirSync(dir, { recursive: true });
    this.sessionDir = dir;
    return dir;
  }

  saveTranscript(jsonl) {
    if (this.sessionDir) writeFileAtomic(path.join(this.sessionDir, 'transcript.jsonl'), jsonl ? jsonl + '\n' : '');
  }

  saveBoard(board) {
    if (this.sessionDir) writeFileAtomic(path.join(this.sessionDir, 'board.json'), JSON.stringify(board, null, 2) + '\n');
  }

  saveNotes(text) {
    if (this.sessionDir) writeFileAtomic(path.join(this.sessionDir, 'notes.md'), text);
  }

  loadSettings() {
    try {
      const j = JSON.parse(fs.readFileSync(path.join(this.dataDir, 'settings.json'), 'utf8'));
      return j && typeof j === 'object' ? j : {};
    } catch (_) {
      return {};
    }
  }

  saveSettings(obj) {
    writeFileAtomic(path.join(this.dataDir, 'settings.json'), JSON.stringify(obj, null, 2) + '\n');
  }
}

module.exports = { Store, writeFileAtomic };
