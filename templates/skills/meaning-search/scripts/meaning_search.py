#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""論点に関係する記録を意味で拾う。入力は読み取り専用、結果は使い捨て。"""
import argparse
import bisect
import concurrent.futures as cf
import datetime as dt
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from contextlib import ExitStack, contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent

CALL_LOCK = threading.Lock()
STATS = {"calls": 0, "retries": 0, "failures": 0, "call_secs": 0.0, "by_kind": {}}


# ───────────────────────── 小道具 ─────────────────────────
def est_tokens(s: str) -> int:
    """日本語は1文字≒1トークン、ASCII は0.35で見積もる。"""
    non_ascii = sum(1 for c in s if ord(c) > 127)
    return int(non_ascii + (len(s) - non_ascii) * 0.35) + 1


RUN_LOG = None


def log(msg: str):
    line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
    with CALL_LOCK:
        print(line, file=sys.stderr, flush=True)
        if RUN_LOG is not None:
            print(line, file=RUN_LOG, flush=True)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def physical_lines(text):
    """Count LF-delimited lines like grep -n and normalize their CRLF endings."""
    return [line.removesuffix("\r") for line in text.removesuffix("\n").split("\n")] if text else []


def read_physical_lines(p: Path):
    with p.open(encoding="utf-8", newline="\n") as file:
        return physical_lines(file.read())


def write_text(path, text):
    # Replace the directory entry instead of writing through a link to an input.
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8") as f:
        temp = Path(f.name)
        try:
            f.write(text)
            f.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def write_json(path, data):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def find_bash() -> str:
    for c in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if c and Path(c).exists():
            return c
    raise ValueError("bash が見つからない（Git Bash が要る）")


def agent_call(prompt, label, outdir, kind, args, key, expected_snippets=None):
    """依頼と各試行を残し、想定の配列が読めるまで再試行する。"""
    calls_dir = outdir / "calls"
    write_text(calls_dir / f"{label}.prompt.txt", prompt)
    last_err = ""
    rescued_hits = []
    timeout = args.timeout if args.agent else args.timeout + 60
    for attempt in range(args.retries + 1):
        t0 = time.time()
        try:
            r = subprocess.run(
                args.agent_command, cwd=args.run_cwd, input=prompt.encode("utf-8"),
                capture_output=True, env=args.agent_env, timeout=timeout,
            )
            out = r.stdout.decode("utf-8", "replace")
            err = r.stderr.decode("utf-8", "replace")
            rc = r.returncode
        except subprocess.TimeoutExpired:
            out, err, rc = "", "timeout", 124
        except OSError as exc:
            out, err, rc = "", str(exc), 2
        secs = time.time() - t0
        with CALL_LOCK:
            STATS["calls"] += 1
            STATS["call_secs"] += secs
            STATS["by_kind"][kind] = STATS["by_kind"].get(kind, 0) + 1
            if attempt:
                STATS["retries"] += 1
        write_text(calls_dir / f"{label}.try{attempt}.out.txt", out + ("\n---stderr---\n" + err if err else ""))
        if rc == 0 and out.strip():
            data, rescued = extract_json(out, key)
            if rescued:
                last_err = f"途中で切れた JSON の {key} を救済（{len(data[key])} 件）"
                log(f"  {label}: {last_err}")
                if key == "hits":
                    for hit in data[key]:
                        if hit not in rescued_hits:
                            rescued_hits.append(hit)
            else:
                last_err = validate_response(data, key, expected_snippets)
                if not last_err:
                    return data, secs, ""
        else:
            last_err = " ".join(part for part in (f"rc={rc}", err.strip()[:200], out.strip()[:200]) if part)
        if attempt < args.retries:
            log(f"  {label}: 失敗（{last_err}）。再試行 {attempt + 1}/{args.retries}")
            time.sleep(15 * (attempt + 1))
    with CALL_LOCK:
        STATS["failures"] += 1
    if rescued_hits and "救済" not in last_err:
        last_err += f"（{len(rescued_hits)} 件を救済）"
    log(f"  {label}: 諦めた（{last_err}）")
    return ({"hits": rescued_hits} if rescued_hits else None), 0.0, last_err


def extract_json(text: str, key):
    """先頭の JSON オブジェクトか、期待した配列の途中までを読む。"""
    i = text.find("{")
    if i < 0:
        return None, False
    s = text[i:]
    decoder = json.JSONDecoder()
    try:
        return decoder.raw_decode(s)[0], False
    except (ValueError, RecursionError):
        pass
    match = re.match(r'\{\s*"' + re.escape(key) + r'"\s*:\s*\[\s*', s)
    if not match:
        return None, False
    rest, items = s[match.end():], []
    while rest:
        try:
            item, end = decoder.raw_decode(rest)
        except (ValueError, RecursionError):
            break
        if not isinstance(item, dict):
            break
        items.append(item)
        rest = rest[end:].lstrip()
        if not rest.startswith(","):
            break
        rest = rest[1:].lstrip()
    return ({key: items}, True) if items else (None, False)


def validate_response(data, key, expected_snippets):
    if not (isinstance(data, dict) and isinstance(data.get(key), list) and
            all(isinstance(item, dict) for item in data[key])):
        return f"JSON の {key} 配列を取り出せない"
    if expected_snippets is None:
        return ""
    snippets = data[key]
    if any(not isinstance(item.get("snippet"), str) or type(item.get("relevant")) is not bool
           or not isinstance(item.get("passages"), list) for item in snippets):
        return "逐語の答えは窓 ID・真偽値の relevant・配列の passages が必要"
    received = {item["snippet"] for item in snippets}
    if received != expected_snippets or len(received) != len(snippets):
        return f"答えの窓 ID が一致しない（期待：{', '.join(sorted(expected_snippets))}）"
    return ""


# ───────────────────────── 台帳・判断台帳の分解 ─────────────────────────
def field(text, key, indent=None):
    matches = re.finditer(rf"(?m)^([ \t]*(?:[-*][ \t]+)?){key}:[ \t]*(.*)$", text)
    match = next((m for m in matches if indent is None or len(m[1]) == indent), None)
    if not match:
        return ""
    value = match[2].strip()
    pieces = [] if re.fullmatch(r"[>|](?:[1-9][+-]?|[+-][1-9]?)?", value) else [value]
    for line in physical_lines(text[match.end():]):
        if not line.strip():
            continue
        if len(line) - len(line.lstrip(" \t")) <= len(match[1]):
            break
        pieces.append(line.strip())
    return " ".join(p for p in pieces if p)


class Entry:
    def __init__(self, section, match, lines, file, line):
        self.section, self.file, self.line = section, file, line
        self.id = match[1].strip("'\"")
        self.id_span = match.span(1)
        self.text = "\n".join(lines).rstrip() + "\n"
        item = re.match(r"[ \t]*-[ \t]+", lines[0]) if section != "journal" else None
        indent = item.end() if item else None
        self.source = field(self.text, "source", indent)
        self.fresh = field(self.text, "fresh", indent)

    def disambiguate(self, identifier):
        start, end = self.id_span
        self.text = self.text[:start] + identifier + self.text[end:]
        self.id = identifier


DEFAULT_RECORD_RE = re.compile(r"^[ \t]*-[ \t]+id:[ \t]*(\S+)")
DEFAULT_JOURNAL_RE = re.compile(r"^###\s+(D-[0-9A-Za-z-]+)")
JOURNAL_RECORD_HEADING_RE = re.compile(r"^ {0,3}#{1,6}[ \t]+D-")
JOURNAL_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
UNREAD_RANGE_LIMIT = 5


def parse_entries(file, id_re, journal=False, coverage=None):
    entries, section, cur = [], "journal" if journal else None, None
    default_record = id_re is None and not journal
    id_re = id_re or (DEFAULT_JOURNAL_RE if journal else DEFAULT_RECORD_RE)
    try:
        original = read_physical_lines(file)
    except UnicodeDecodeError as exc:
        raise ValueError(f"UTF-8 で読めない：{file}") from exc
    lines = original
    if journal:
        # Keep physical line numbers. No sample or other comment text enters a record.
        lines = JOURNAL_COMMENT_RE.sub(lambda m: " " + "\n" * m[0].count("\n") + " ",
                                       "\n".join(original)).split("\n")
    section_indent = None
    journal_preface = journal
    preface = unread = 0
    ranges = []
    for i, (raw, line) in enumerate(zip(original, lines), 1):
        nonempty = bool(raw.strip())
        hidden = nonempty and not line.strip()
        heading = None if journal else re.match(r"^([\w-]+):(?:\s|$)", line)
        match = id_re.match(line) if section and section != "meta" and not hidden else None
        starts_record = bool(journal and JOURNAL_RECORD_HEADING_RE.match(line))
        if default_record and section and not heading and nonempty and not line.lstrip().startswith("#"):
            content = line.lstrip(" \t")
            indent = len(line) - len(content)
            if section_indent is None:
                section_indent = indent
            if indent != section_indent:
                match = None
            else:
                starts_record = bool(re.match(r"^-(?:[ \t]|$)", content))
        if journal and (match or starts_record):
            journal_preface = False
        if heading or match or starts_record:
            if cur:
                entries.append(Entry(*cur))
            cur = None
        if heading:
            section = heading[1]
            section_indent = None
            preface += 1
        elif match:
            cur = (section, match, [line], file, i)
        elif cur and not hidden:
            cur[2].append(line)
        elif nonempty:
            if journal_preface or (section == "meta" and not entries):
                preface += 1
            else:
                unread += 1
                if ranges and ranges[-1][1] == i - 1:
                    ranges[-1][1] = i
                elif len(ranges) < UNREAD_RANGE_LIMIT:
                    ranges.append([i, i])
    if cur:
        entries.append(Entry(*cur))
    if coverage is not None:
        coverage.update(file=str(file), records=len(entries), preface_lines=preface,
                        unread_lines=unread, unread_ranges=ranges)
    return entries


def parse_requested_file(file, id_re, coverage, *, journal=False):
    row = {}
    entries = parse_entries(file, id_re, journal, row)
    if not entries:
        flag, default = ("--journal-re", DEFAULT_JOURNAL_RE) if journal else ("--record-re", DEFAULT_RECORD_RE)
        raise ValueError(f"記録が0件：{file}（{flag} の既定の正規表現 {default.pattern}）")
    coverage.append(row)
    return entries


def describe_parse_coverage(row):
    ranges = "、".join(f"L{a}" if a == b else f"L{a}〜L{b}" for a, b in row["unread_ranges"])
    shown = sum(b - a + 1 for a, b in row["unread_ranges"])
    if ranges and shown < row["unread_lines"]:
        ranges += "、…"
    return (f"記録 {row['records']} 件・読まない前書き {row['preface_lines']} 行・"
            f"記録に入らなかった行 {row['unread_lines']} 行" + (f"（{ranges}）" if ranges else ""))


def index_entries(entries):
    counts = Counter(e.id for e in entries)
    reserved = set(counts)
    by_id = {}
    for e in entries:
        if counts[e.id] > 1:
            old_id = e.id
            identifier = f"{old_id}@{e.line}"
            # Two ledgers can put the same ID on the same line.
            if identifier in reserved or identifier in by_id:
                base = f"{identifier}@{e.file.name}"
                identifier, suffix = base, 1
                while identifier in reserved or identifier in by_id:
                    suffix += 1
                    identifier = f"{base}@{suffix}"
            e.disambiguate(identifier)
            log(f"重複した番号 {old_id} → {identifier}（{e.file}:{e.line}）")
        by_id[e.id] = e
    return by_id


def make_chunks(entries, limit_tokens, prefix, first_limit=None):
    """1件を途中で切らずに、見積りトークン数が limit を超えない区切りへ。"""
    chunks, cur, cur_tok = [], [], 0
    for e in entries:
        label = {"journal": "【判断台帳 journal】"}.get(e.section, f"【台帳 {e.section}】")
        block = f"{label}\n{e.text}\n"
        tk = est_tokens(block)
        lim = first_limit if (first_limit and not chunks) else limit_tokens
        if cur and cur_tok + tk > lim:
            chunks.append(cur)
            cur, cur_tok = [], 0
        cur.append((e, block))
        cur_tok += tk
    if cur:
        chunks.append(cur)
    return [(f"{prefix}{i + 1}", c, sum(est_tokens(b) for _, b in c)) for i, c in enumerate(chunks)]


# ───────────────────────── プロンプト ─────────────────────────
def escape_prompt_material(text):
    return re.sub(r"</(?:glossary|mishearings|records|snippets?)\s*>",
                  lambda match: html.escape(match[0], quote=False), text, flags=re.IGNORECASE)


def build_prompt(template_name, args, body):
    values = {
        "CASE": args.case, "GLOSSARY": escape_prompt_material(args.glossary_text),
        "MISHEARINGS": escape_prompt_material(args.mishearings_text), "TOPIC": args.topic,
        "HINT": "補足：" + args.hint if args.hint else "",
        "BODY": escape_prompt_material(body) if template_name == "scan.md" else body,
    }
    prompts = SKILL / "prompts"
    template = read(prompts / template_name).replace("{{COMMON}}", read(prompts / "common.md"))
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m[1]], template)


# ───────────────────────── 逐語の場所をたどる ─────────────────────────
_raw_cache = {}


def raw_lines(p: Path):
    if p not in _raw_cache:
        _raw_cache[p] = read_physical_lines(p)
    return _raw_cache[p]


def source_encoding_issue(file):
    try:
        raw_lines(file)
    except UnicodeDecodeError:
        return f"{file}：文字コードのため UTF-8 で読み取れない"
    return ""


def ts_index(p: Path):
    """[(秒, 行番号)] 行頭の [hh:mm:ss] から"""
    out = []
    for i, ln in enumerate(raw_lines(p), 1):
        m = re.match(r"\[?(\d{1,2}):(\d{2}):(\d{2})\]?", ln)
        if m:
            out.append((int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]), i))
    return sorted(out)


DATE_RE = re.compile(r"(?<!\d)(\d{4})-?(\d{2})-?(\d{2})(?!\d)")
SHORT_DATE_RE = re.compile(r"(?<![\d:L])(\d{1,2})/(\d{1,2})(?![\d:])")
RANGE_RE = re.compile(r"L(\d+)(?:\s*[〜~\-–]\s*L?(\d+))?")
GYO_RE = re.compile(r"(?<![\w])(\d+)\s*行(?:\s*[〜~\-–]\s*(\d+))?|行\s*(\d+)\s*[〜~\-–]\s*(\d+)")
TS_RE = re.compile(r"(?<![\d:L])(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*[〜~\-–]\s*(\d{1,2}):(\d{2})(?::(\d{2}))?)?(?![\d])")
GENERIC_SOURCE_WORDS = {"会議", "minutes", "raw", "社内", "wav", "md"}


def date_keys(text):
    return {"".join(m.groups()) for m in DATE_RE.finditer(text)}


def pick_files_by_date(src, files, fresh=""):
    """日付で絞り、自由書式なら名前の語でも照合する。"""
    dates = date_keys(src)
    for m in SHORT_DATE_RE.finditer(src):
        month, day = map(int, m.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            dates.update(date[:4] + f"{month:02d}{day:02d}" for date in date_keys(fresh))
            if not date_keys(fresh):
                dates.update(date for f in files for date in date_keys(f.name)
                             if date.endswith(f"{month:02d}{day:02d}"))
    if not dates:
        return []
    candidates = [f for f in files if date_keys(f.name) & dates]
    context = src
    for pattern in (DATE_RE, SHORT_DATE_RE, RANGE_RE, GYO_RE, TS_RE):
        context = pattern.sub(" ", context)
    tokens = {t.casefold() for t in re.findall(r"[ぁ-んァ-ン一-龥A-Za-z0-9]{2,}", context)}
    tokens -= GENERIC_SOURCE_WORDS
    scores = {f: sum(t in f.stem.casefold() for t in tokens) for f in candidates}
    best = max(scores.values(), default=0)
    return [f for f in candidates if scores[f] == best]


def to_sec(a, b, c):
    if c is None:
        return int(a) * 60 + int(b)
    return int(a) * 3600 + int(b) * 60 + int(c)


def locators_from_context(ctx):
    """自由書式から (kind, 最初, 最後) を取り出す。"""
    out = []
    for part in ctx.split("／"):
        for m in RANGE_RE.finditer(part):
            a, b = int(m[1]), int(m[2] or m[1])
            out.append(("L", a, max(a, b)))
        for m in GYO_RE.finditer(part):
            a, b = int(m[1] or m[3]), int(m[2] or m[4] or m[1])
            out.append(("L", a, max(a, b)))
        for m in TS_RE.finditer(part):
            a = to_sec(m[1], m[2], m[3])
            b = to_sec(m[4], m[5], m[6]) if m[4] else a
            out.append(("T", a, max(a, b)))
    return out


def _add_windows(file, locators, windows):
    n = len(raw_lines(file))
    timestamps = None
    issues = []
    for kind, start, end in locators:
        if kind == "T":
            if timestamps is None:
                timestamps = ts_index(file)
            if timestamps and end > timestamps[-1][0] + 60:
                clock = f"{end // 3600:02d}:{end // 60 % 60:02d}:{end % 60:02d}"
                issues.append(f"{file.name}: 時刻が逐語の範囲の外（{clock}）")
                continue
            i = bisect.bisect_right(timestamps, (start, n)) - 1
            if i < 0:
                clock = f"{start // 3600:02d}:{start // 60 % 60:02d}:{start % 60:02d}"
                issues.append(f"{file.name}: {clock} に対応する時刻の行がない")
                continue
            j = bisect.bisect_right(timestamps, (end, n)) - 1
            start, end = timestamps[i][1], timestamps[j][1]
        elif not (1 <= start <= end <= n):
            location = f"L{start}" if start == end else f"L{start}–L{end}"
            issues.append(f"{file.name}: {location} は行の範囲外（全 {n} 行）")
        if 1 <= start <= n:
            windows.append((file, start, min(max(start, end), n)))
    return issues


def named_files(text, files):
    exact = [f for f in files if f.stem == text or f.name == text]
    return exact or [f for f in files if text and (text in f.name or f.stem in text)]


def source_value(entry):
    src = entry.source.strip("'\"")
    return re.sub(r"\s*（[^（）]*）\s*$", "", src).strip().strip("'\"")


def safe_source_file(candidate, args):
    """台帳から間接的に指定されたパスを、読む前に検査する。"""
    try:
        file = candidate.resolve()
    except (OSError, RuntimeError):
        return None, f"出典のパスを解けない：{candidate}"
    if not any(file.is_relative_to(root) for root in args.allowed_source_roots):
        return None, f"出典が許可した根の外：{candidate}"
    return (file if file.is_file() else None), ""


NO_SOURCE_FILE = "該当するファイルがない"


def choose_source_file(candidates, args, first=False):
    paths_by_file = {}
    issues = []
    for candidate in candidates:
        file, issue = safe_source_file(candidate, args)
        if issue:
            issues.append(issue)
        if file:
            paths_by_file.setdefault(file, []).append(candidate)
            if first:
                break
    if len(paths_by_file) == 1 and not issues:
        file, paths = next(iter(paths_by_file.items()))
        return file, paths, ""
    if len(paths_by_file) > 1:
        issues.append("候補が複数ある：" + "、".join(map(str, paths_by_file)))
    return None, [], "／".join(issues) or NO_SOURCE_FILE


def file_locator(entry, args):
    src = source_value(entry)
    match = re.fullmatch(r"(.+):(\d+)", src)
    if not match or src.startswith(("mail:", "talk:")):
        return None, None, [], ""
    path = Path(match[1])
    roots = args.source_root
    if not roots:
        roots = args.ledger_roots.get(entry.file, args.default_roots)
    candidates = [path] if path.is_absolute() else [root / path for root in roots]
    file, paths, issue = choose_source_file(candidates, args, first=not args.source_root)
    return file, int(match[2]), paths, issue


SOURCE_SENTENCE_END = re.compile(r"[。！？!?]|\.(?=\s|$)|\n\s*(?:\n|[-*]\s)")
SOURCE_PARTIAL_NAME = re.compile(
    r"(?<![\w-])([ぁ-んァ-ン一-龥A-Za-z0-9_-]{2,})[ \t:：の]+"
    r"(?=L\d|\d+\s*行|行\s*\d|\d{1,2}:\d{2})"
)


def legacy_mentions(ctx, files):
    """明記された名前と直後の位置指定を組にする。"""
    by_name = {}
    for file in files:
        names = {file.name}
        if file.stem.casefold() not in GENERIC_SOURCE_WORDS and not RANGE_RE.fullmatch(file.stem):
            names.add(file.stem)
        for name in names:
            by_name.setdefault(name, []).append(file)
    if not by_name:
        return []
    names = "|".join(re.escape(name) for name in sorted(by_name, key=lambda n: (-len(n), n)))
    exact = list(re.finditer(rf"(?<![A-Za-z0-9_-])(?:{names})(?![A-Za-z0-9_-])", ctx))
    mentions = [(m.start(), m.end(), by_name[m[0]]) for m in exact]
    for m in SOURCE_PARTIAL_NAME.finditer(ctx):
        name = m[1]
        if name.casefold() in GENERIC_SOURCE_WORDS or DATE_RE.fullmatch(name) or re.fullmatch(r"L\d+", name):
            continue
        if any(other.start() < m.end(1) and m.start() < other.end() for other in exact):
            continue
        candidates = [file for file in files if name in file.stem]
        if candidates:
            mentions.append((m.start(), m.end(1), candidates))
    mentions.sort()
    refs = []
    for i, (_, end, candidates) in enumerate(mentions):
        next_name = mentions[i + 1][0] if i + 1 < len(mentions) else len(ctx)
        tail = ctx[end:min(next_name, end + 200)]
        locator_text = SOURCE_SENTENCE_END.split(tail, maxsplit=1)[0]
        refs.append((candidates, locators_from_context(locator_text)))
    return refs


def resolve_refs(entry, args):
    """窓、会議だけの出典、丸ごと読む出典、未解決の理由を返す。"""
    src = source_value(entry)
    refs, issues = [], []
    force_whole = False

    if src.startswith("talk:"):
        talk = re.fullmatch(r"talk:(?:(.+)@)?(\d{1,2}):(\d{2}):(\d{2})", src)
        if not talk:
            return [], [], [], "talk: の書式外"
        if talk[1]:
            files = [f for f in args.raw_files if f.stem == talk[1]]
        else:
            fresh = date_keys(entry.fresh)
            files = [f for f in args.raw_files if date_keys(f.name) & fresh]
        at = to_sec(*talk.groups()[1:])
        refs.append((files, [("T", at, at)]))
    elif src.startswith("mail:"):
        m = re.fullmatch(r"mail:(\d{4}-\d{2}-\d{2})", src)
        if not m:
            return [], [], [], "mail: の書式外"
        if args.mail_dir is None:
            return [], [], [], "mail: を解く --mail-dir が指定されていない"
        files = [f for f in args.mail_files if date_keys(f.name) & date_keys(m[1])]
        refs.append((files, []))
        force_whole = True
    else:
        file, line, _, issue = file_locator(entry, args)
        if file:
            issue = source_encoding_issue(file)
            if issue:
                return [], [], [], issue
            windows = []
            issues = _add_windows(file, [("L", line, line)], windows)
            return windows, [], [], "／".join(issues)
        if line is not None and (issue != NO_SOURCE_FILE or not TS_RE.search(src)):
            return [], [], [], issue
        # 判断台帳の旧書式は、本文中で逐語ファイルを指すことがある。
        ctx = src or (entry.text if entry.section == "journal" else "")
        refs = legacy_mentions(ctx, args.raw_files)
        if not refs:
            files = pick_files_by_date(src, args.raw_files, entry.fresh)
            if not files:
                why = "日付に合う逐語がない" if date_keys(src) else "書式外" if src else "出典なし"
                return [], [], [], why
            refs.append((files, locators_from_context(src)))

    windows, meetings, whole = [], [], []
    for files, locators in refs:
        file, _, issue = choose_source_file(files, args)
        if file:
            issue = source_encoding_issue(file)
        if issue:
            issues.append(issue)
            continue
        if force_whole or (locators and all(k == "T" for k, _, _ in locators) and not ts_index(file)):
            whole.append(file)
        elif not locators:
            meetings.append(file)
        else:
            issues.extend(_add_windows(file, locators, windows))
    return windows, meetings, whole, "／".join(dict.fromkeys(issues))


def merge_windows(items, pad):
    """前後 pad 行を足して重なりをまとめ、記録ごとの元の範囲も保持する。"""
    by = {}
    for f, s, e, hid in items:
        by.setdefault(f, []).append((max(1, s - pad), min(len(raw_lines(f)), e + pad), hid))
    out = []
    for f, ws in by.items():
        ws.sort()
        cur = None
        for s, e, hid in ws:
            if cur and s <= cur[1] + 1:
                cur[1] = max(cur[1], e)
            else:
                if cur:
                    out.append((f, cur[0], cur[1], cur[2]))
                cur = [s, e, {}]
            ranges = cur[2].setdefault(hid, [])
            if ranges and s <= ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], e))
            else:
                ranges.append((s, e))
        if cur:
            out.append((f, cur[0], cur[1], cur[2]))
    return out


def clip_record_ranges(ranges, start, end):
    return {
        hid: clipped for hid, spans in sorted(ranges.items())
        if (clipped := [(max(start, a), min(end, b)) for a, b in spans if a <= end and start <= b])
    }


def numbered(f: Path, s: int, e: int):
    ls = raw_lines(f)
    return "\n".join(f"L{i}|{ls[i - 1]}" for i in range(s, e + 1))


def line_text(f: Path, i: int):
    return raw_lines(f)[i - 1]


RANK_STR = {"直接": 3, "関連": 2, "周辺": 1}


def add_hit(hits, h, route, name, allowed, unknown_ids):
    """同じ番号は強いほうを残し、経路・区切りを足す。今回の材料にない番号は捨てる。"""
    raw_id = h.get("id", "")
    hid = raw_id.strip() if isinstance(raw_id, str) else None
    if hid not in allowed:
        unknown_ids.append((str(raw_id).strip(), name))
        return None
    h = {
        "id": hid,
        "section": allowed[hid].section,
        **{k: h[k] for k in ("what", "why", "mishearing", "strength") if isinstance(h.get(k), str)},
    }
    cur = hits.get(hid)
    if cur is None:
        h["reasons"] = [h["why"]] if h.get("why") else []
        h["routes"] = [route]
        h["chunks"] = [name]
        hits[hid] = h
        return hid
    if route not in cur["routes"]:
        cur["routes"].append(route)
    cur["chunks"].append(name)
    if h.get("why") and h["why"] not in cur["reasons"]:
        cur["reasons"].append(h["why"])
    if RANK_STR.get(h.get("strength"), 0) > RANK_STR.get(cur.get("strength"), 0):
        h["routes"], h["chunks"], h["reasons"] = cur["routes"], cur["chunks"], cur["reasons"]
        if cur.get("grep_terms"):
            h["grep_terms"] = cur["grep_terms"]
        hits[hid] = h
    return hid


# ───────────────────────── 本体 ─────────────────────────
def input_locations(path):
    # Preserve the supplied directory entry as well as the symlink target.
    return {path.parent.resolve() / path.name, path.resolve()}


def prepare_inputs(args):
    root = kit_root()
    explicit_transcripts = args.transcripts is not None
    args.missing = []
    args.input_files, args.input_dirs = set(), set()
    if args.project:
        if args.project in (".", "..") or re.search(r"[/\\]", args.project):
            raise ValueError("--project にはフォルダ名を1つ指定する")
        project = root / "projects" / args.project
        if not project.is_dir():
            raise ValueError(f"--project: フォルダが見つからない：{project}")
        defaults = {
            "ledger": project / "ledgers" / "ledger.yaml", "journal": root / "judgment" / "decisions_journal.md",
            "glossary": root / "ssot" / "glossary.md", "mishearings": project / "ledgers" / "mishearings.md",
            "transcripts": project / "transcripts",
        }
        for key, path in defaults.items():
            if getattr(args, key):
                continue
            exists = path.is_dir() if key == "transcripts" else path.is_file()
            if exists:
                setattr(args, key, [path] if key == "ledger" else path)
            else:
                args.missing.append(str(path))

    for key in ("journal", "glossary", "mishearings", "transcripts", "mail_dir"):
        candidate = getattr(args, key)
        if candidate is None:
            continue
        path = candidate.resolve()
        exists = path.is_file() if key in ("journal", "glossary", "mishearings") else path.is_dir()
        if not exists:
            raise ValueError(f"--{key.replace('_', '-')}: 入力が見つからない：{path}")
        locations = input_locations(candidate)
        if key in ("transcripts", "mail_dir"):
            args.input_dirs.update(locations)
        else:
            args.input_files.update(locations)
        setattr(args, key, path)
    for path in args.ledger:
        args.input_files.update(input_locations(path))
    args.ledger = list(dict.fromkeys(p.resolve() for p in args.ledger))
    for path in args.ledger:
        if not path.is_file():
            raise ValueError(f"--ledger: 入力が見つからない：{path}")

    if args.source_root:
        args.source_root = [p.resolve() for p in args.source_root]
        for path in args.source_root:
            if not path.is_dir():
                raise ValueError(f"--source-root: フォルダが見つからない：{path}")
    args.ledger_roots = {}
    if args.project:
        args.default_roots = [project]
    else:
        for ledger in args.ledger:
            parent = ledger.parent.parent
            # A shallow ledger would otherwise grant access to the entire filesystem.
            args.ledger_roots[ledger] = [parent] if parent != Path(parent.anchor) else []
        args.default_roots = list(dict.fromkeys(parent for roots in args.ledger_roots.values() for parent in roots))
    args.allowed_source_roots = set(args.source_root + args.default_roots)
    if explicit_transcripts:
        args.allowed_source_roots.add(args.transcripts)
    if args.mail_dir:
        args.allowed_source_roots.add(args.mail_dir)

    for key, directory in (("raw_files", args.transcripts), ("mail_files", args.mail_dir)):
        files = sorted(p for p in directory.iterdir()
                       if (key != "raw_files" or p.suffix.lower() in {".txt", ".md", ".vtt", ".srt"})
                       and (p.is_symlink() or p.is_file())) if directory else []
        setattr(args, key, files)
        for candidate in files:
            file, _ = safe_source_file(candidate, args)
            if file:
                args.input_files.update((candidate, file))

    args.meeting_files = []
    for key in args.meeting:
        path = Path(key)
        if path.is_file():
            args.input_files.update(input_locations(path))
            files = [path.resolve()]
        else:
            files = [file for p in named_files(key, args.raw_files) if (file := safe_source_file(p, args)[0])]
        if not files:
            raise ValueError(f"--meeting {key}: 該当する逐語がない")
        args.meeting_files.extend(files)
    args.meeting_files = list(dict.fromkeys(args.meeting_files))
    if not (args.project or args.ledger or args.journal or args.meeting_files):
        raise ValueError("--project、--ledger、--journal、--meeting のいずれかを指定する")
    args.glossary_text = read(args.glossary) if args.glossary else "（用語集なし）"
    args.mishearings_text = read(args.mishearings) if args.mishearings else "（対応表なし）"
    return root


def prepare_output(args, entries, root):
    def validate_location(path):
        if path.is_relative_to(SKILL):
            raise ValueError(f"スキル内または入力のフォルダには出力できない：{path}")
        if path.is_relative_to(root) and not (
            path.is_relative_to(root / "local") or path.is_relative_to(root / "projects")
        ):
            raise ValueError(f"キット内では local/ または projects/ の下だけに出力できる：{path}")

    if args.out:
        outdir = Path(args.out).resolve()
        validate_location(outdir)
        input_dirs = args.input_dirs | {p.parent for p in args.input_files}
        for entry in entries:
            file, _, paths, _ = file_locator(entry, args)
            if file:
                input_dirs.add(file.parent)
                input_dirs.update(path.parent.resolve() for path in paths)
        if outdir in input_dirs:
            raise ValueError(f"スキル内または入力のフォルダには出力できない：{outdir}")
        if (outdir / "calls").resolve() in input_dirs:
            raise ValueError(f"calls/ が入力のフォルダと同じ：{outdir / 'calls'}")
        outdir.mkdir(parents=True, exist_ok=True)
        return outdir

    base = Path(os.environ.get("MSEARCH_OUT_DIR") or tempfile.gettempdir()).resolve()
    validate_location(base)
    base.mkdir(parents=True, exist_ok=True)
    short = re.sub(r'[\\/:*?"<>|\s]+', "", args.short or args.topic)[:20]
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(tempfile.mkdtemp(prefix=f"meaning-search-{timestamp}-{short}-", dir=base))


def configure_agent(args, outdir, root, cleanup):
    args.run_cwd = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix="meaning-search-agent-")))
    args.agent_env = dict(os.environ, MSEARCH_KIT_ROOT=str(root), MSEARCH_TIMEOUT_DEFAULT="900",
                          TMPDIR=str(outdir))
    model_args = ["--model", args.model] if args.model else []
    effort_args = ["--effort", args.effort] if args.effort else []
    timeout_args = ["--timeout", str(args.timeout)] if args.timeout is not None else []
    if args.agent:
        path = Path(args.agent)
        command = [str(path)] if path.is_file() else shlex.split(args.agent, posix=os.name != "nt")
        exe = shutil.which(command[0]) if command else None
        if not exe and command and Path(command[0]).is_file():
            exe = command[0]
        if not exe:
            raise ValueError(f"--agent: コマンドが見つからない：{args.agent}")
        command[0] = Path(exe).resolve().as_posix()
        if Path(exe).suffix == ".sh":
            command.insert(0, find_bash())
        args.agent_command = command + model_args + effort_args
        args.timeout = args.timeout or int(os.environ.get("MSEARCH_TIMEOUT") or 900)
        if args.timeout < 1:
            raise ValueError("MSEARCH_TIMEOUT は正の整数にする")
        return

    args.agent_command = [find_bash(), (HERE / "ms_agent.sh").as_posix(), *model_args, *effort_args, *timeout_args]
    check = subprocess.run([*args.agent_command, "--check-config"], cwd=args.run_cwd,
                           env=args.agent_env, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    if check.returncode:
        raise ValueError(check.stderr.decode("utf-8", "replace").strip() or "ms_agent: 設定を読めない")
    args.model, seconds = physical_lines(check.stdout.decode("utf-8"))
    args.timeout = int(seconds)


def describe_chunk(item, limit):
    name, chunk, tokens = item
    prefix, _, index = name.rpartition("-")
    pass_match = re.match(r"p(\d+)-", prefix)
    files = list(dict.fromkeys(str(e.file) for e, _ in chunk))
    return {
        "name": name, "pass": int(pass_match[1]) if pass_match else None, "index": int(index),
        "file": files[0] if len(files) == 1 else None, "files": files,
        "ids": [e.id for e, _ in chunk], "tokens": tokens, "oversize": tokens > limit,
    }


def make_batches(snippets, limit):
    batches, cur, cur_tok = [], [], 0
    for sn in snippets:
        tk = est_tokens(sn[5]) + 60
        if cur and cur_tok + tk > limit:
            batches.append(cur)
            cur, cur_tok = [], 0
        cur.append(sn)
        cur_tok += tk
    if cur:
        batches.append(cur)
    return batches


def append_whole(snippets, files_to_ids, limit):
    for file, ids in files_to_ids.items():
        n = len(raw_lines(file))
        a = 1
        while a <= n:
            tok, b = 0, a
            while b <= n and tok + est_tokens(raw_lines(file)[b - 1]) + 8 < limit * 2:
                tok += est_tokens(raw_lines(file)[b - 1]) + 8
                b += 1
            b = max(a, b - 1)
            ranges = {hid: [(a, b)] for hid in ids}
            snippets.append([f"s{len(snippets) + 1}", file, a, b, ranges, numbered(file, a, b)])
            a = b + 1


def kit_root():
    override = os.environ.get("MSEARCH_KIT_ROOT")
    return Path(override).resolve() if override else HERE.parents[3]


def set_planning_defaults(args, parser):
    defaults = {"parallel": 10, "chunk_tokens": 25000, "passes": 2}
    pending = {}
    for name, fallback in defaults.items():
        if getattr(args, name) is not None:
            continue
        key = f"MSEARCH_{name.upper()}"
        pending[key] = (name, os.environ.get(key), fallback)

    values = {}
    if any(not env for _, env, _ in pending.values()):
        config = kit_root() / "config.env"
        if config.is_file():
            for line in read_physical_lines(config):
                key, _, value = line.lstrip().partition("=")
                if key not in pending:
                    continue
                # Accept only a literal integer assignment, with optional
                # quotes and an inline comment. Never evaluate shell text.
                match = re.fullmatch(r"""(['"]?)([+-]?\d+)\1(?:[ \t]+#.*|[ \t]*)""", value)
                if match:
                    values[key] = match[2]

    for key, (name, env, fallback) in pending.items():
        try:
            setattr(args, name, int(env or values.get(key, fallback)))
        except ValueError:
            parser.error(f"{key} は整数にする")


def is_dry_plan(path):
    try:
        plan = json.loads(read(path))
    except (OSError, ValueError, RecursionError):
        return False
    # Older runs recorded no mode, but also left an agent directory as soon as
    # a real run configured an agent. Reuse requires the plan and log alone.
    return (isinstance(plan, dict) and plan.get("dry_run", True) is True
            and isinstance(plan.get("topic"), str) and isinstance(plan.get("chunks"), list)
            and type(plan.get("planned_calls")) is int)


@contextmanager
def claim_output(outdir, *, reuse_dry):
    lock = outdir / ".meaning-search.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ValueError(f"出力先は使用中：{outdir}") from exc
    try:
        for name in ("result.json", "result.md", "hits.json", "stats.json", "calls"):
            artifact = outdir / name
            if artifact.exists() or artifact.is_symlink():
                raise ValueError(f"出力先に前の実行の成果物がある：{artifact}")

        plan, run_log = outdir / "plan.json", outdir / "run.log"
        if plan.exists() or plan.is_symlink() or run_log.exists() or run_log.is_symlink():
            if not (reuse_dry and {p.name for p in outdir.iterdir()} == {lock.name, plan.name, run_log.name}
                    and not (plan.is_symlink() or run_log.is_symlink())
                    and plan.is_file() and run_log.is_file() and is_dry_plan(plan)):
                raise ValueError(f"出力先に前の実行の成果物がある：{outdir}")
            # Remove the old plan before the new run starts, so an interrupted
            # real run cannot be mistaken for the preceding dry run.
            plan.unlink()
            run_log.unlink()

        fd = os.open(run_log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as log_file:
            yield log_file
    finally:
        lock.rmdir()


def main():
    ap = argparse.ArgumentParser(description="論点に関係する記録を意味で拾う（使い捨て）")
    ap.add_argument("--topic", required=True, help="論点（例：納品後の修正）")
    ap.add_argument("--hint", default="", help="補足（関係する言葉・拾いたい範囲・除きたいもの）")
    ap.add_argument("--short", default="", help="結果のフォルダ名に使う短い名（既定は論点の先頭）")
    ap.add_argument("--project")
    ap.add_argument("--ledger", action="append", type=Path, default=[])
    for key in ("journal", "glossary", "mishearings", "transcripts", "mail-dir"):
        ap.add_argument(f"--{key}", type=Path)
    ap.add_argument("--source-root", action="append", type=Path, default=[])
    ap.add_argument("--record-re", help="台帳の記録の先頭（既定は section 直下の - id:）")
    ap.add_argument("--journal-re", default=DEFAULT_JOURNAL_RE.pattern)
    ap.add_argument("--case", default=os.environ.get("MSEARCH_CASE") or "（説明なし）")
    ap.add_argument("--agent", help="試験・差し替え用。差し替えたコマンドには道具の制限もモデルの確認も掛からない")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default="", help="推論の effort（空なら MSEARCH_EFFORT）")
    ap.add_argument("--parallel", type=int, help="同時に流す数（目安10まで。利用上限のエラーが出たら減らす）")
    ap.add_argument("--chunk-tokens", type=int, help="台帳の1区切りの見積りトークン数（既定2万5千。日本語は1文字≒1トークン）")
    ap.add_argument("--pad", type=int, default=20, help="逐語の前後の行数（既定20）")
    ap.add_argument("--skip-ledger", action="store_true", help="台帳・判断台帳の下読みを飛ばす（--meeting と組む）")
    ap.add_argument("--skip-verbatim", action="store_true", help="出典から逐語をたどる段を飛ばす")
    ap.add_argument("--meeting", action="append", default=[], help="会議の逐語を丸ごと読ませる（ファイル名の一部・複数可）")
    ap.add_argument("--whole-meetings", type=int, default=3, help="「直接」の記録が出典の欄で（行の指定なしに）指している会議のうち、指す記録が多い順に N 件を丸ごと読ませる（既定3・0で無効）")
    ap.add_argument("--passes", type=int, help="台帳・判断台帳の下読みを何回流して和集合にするか（既定2。2回目以降は区切りの位置をずらす）")
    ap.add_argument("--expand-grep", action="store_true", help="言い換え語の grep の経路を追加する")
    ap.add_argument("--grep-direct-max", type=int, default=30, help="モデルが拾わなかった記録を grep が拾った数がこれ以下なら、そのまま結果に足す。超えたら当たった記録だけを モデルに読ませて判定（既定30）")
    ap.add_argument("--grep-generic", type=float, default=0.15, help="1つの語が全記録のこの割合を超えて当たったら、一般的すぎる語として捨てる（既定0.15）")
    ap.add_argument("--verbatim-from", default="直接,関連,周辺", help="逐語をたどる元にする強さ（既定は全部。直接,関連 に絞ると速いが漏れが出る）")
    ap.add_argument("--max-windows", type=int, default=80)
    ap.add_argument("--max-verbatim-tokens", type=int, default=45000, help="逐語を読ませる1回の窓の見積りトークン数")
    ap.add_argument("--timeout", type=int, default=None, help="1回の制限秒数（既定900）")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--only", default="", help="（試験用）台帳の区切りを番号で絞る 例 1,3")
    ap.add_argument("--dry-run", action="store_true", help="呼び出しの計画だけ出す")
    ap.add_argument("--out", default="", help="結果のフォルダ（省略時は MSEARCH_OUT_DIR または一時領域の下に自動作成）")
    args = ap.parse_args()
    set_planning_defaults(args, ap)
    for key in ("parallel", "chunk_tokens", "passes", "max_verbatim_tokens", "timeout"):
        value = getattr(args, key)
        if value is not None and value < 1:
            ap.error(f"--{key.replace('_', '-')} は正の整数にする")
    for key in ("pad", "whole_meetings", "grep_direct_max", "max_windows", "retries"):
        if getattr(args, key) < 0:
            ap.error(f"--{key.replace('_', '-')} は0以上にする")
    if not 0 <= args.grep_generic <= 1:
        ap.error("--grep-generic は0以上1以下にする")
    if args.only and not re.fullmatch(r"[1-9]\d*(?:,[1-9]\d*)*", args.only):
        ap.error("--only は1以上の区切り番号をカンマで区切る")

    record_re = re.compile(args.record_re) if args.record_re is not None else None
    journal_re = re.compile(args.journal_re)
    if (record_re is not None and not record_re.groups) or not journal_re.groups:
        ap.error("--record-re と --journal-re には番号を取る括弧が要る")
    root = prepare_inputs(args)
    args.parse_coverage = []
    ledger_groups, journal = [], []
    if not args.skip_ledger:
        ledger_groups = [parse_requested_file(p, record_re, args.parse_coverage) for p in args.ledger]
        if args.journal:
            journal = parse_requested_file(args.journal, journal_re, args.parse_coverage, journal=True)
    outdir = prepare_output(args, [*(entry for group in ledger_groups for entry in group), *journal], root)
    global RUN_LOG
    with claim_output(outdir, reuse_dry=bool(args.out)) as run_log, ExitStack() as cleanup:
        RUN_LOG = run_log
        try:
            return search(args, root, outdir, ledger_groups, journal, cleanup)
        finally:
            RUN_LOG = None


def search(args, root, outdir, ledger_groups, journal, cleanup):
    t_start = time.time()
    ledger = [e for group in ledger_groups for e in group]
    all_entries = ledger + journal
    by_id = index_entries(all_entries)
    log(f"台帳 {len(ledger)} 件・判断台帳 {len(journal)} 件")
    if not args.dry_run:
        for row in args.parse_coverage:
            log(f"{row['file']}（{describe_parse_coverage(row)}）")
    for path in args.missing:
        log(f"--project の既定の入力がない：{path}")

    plans = []
    chunk_rows = {}
    for p in range(args.passes):
        first = None if p == 0 else max(1, int(args.chunk_tokens * (1 - p / args.passes)))
        ledger_index = 0
        for entries, kind in [*((g, "ledger") for g in ledger_groups), (journal, "journal")]:
            chunks = make_chunks(entries, args.chunk_tokens, f"p{p + 1}-{kind}-", first)
            for i, (name, chunk, tk) in enumerate(chunks):
                if kind == "ledger":
                    ledger_index += 1
                    name = f"p{p + 1}-ledger-{ledger_index}"
                item = (name, chunk, tk)
                plans.append(item)
                limit = (first or args.chunk_tokens) if i == 0 else args.chunk_tokens
                chunk_rows[name] = describe_chunk(item, limit)
    if args.only:
        keep = set(map(int, args.only.split(",")))
        if max(keep) > len(plans):
            raise ValueError("--only: 存在しない区切り番号")
        plans = [c for i, c in enumerate(plans, 1) if i in keep]
        chunk_rows = {name: chunk_rows[name] for name, _, _ in plans}
    for name, c, tk in plans:
        log(f"区切り {name}: {len(c)} 件・見積り {tk} トークン（{c[0][0].id}〜{c[-1][0].id}）")

    explicit_meetings, unresolved_meetings = {}, []
    for file in args.meeting_files:
        issue = source_encoding_issue(file)
        if issue:
            log(issue)
            unresolved_meetings.append({"id": None, "raw": str(file), "state": "unresolved", "why": issue,
                                        "file": str(file), "line_from": None, "line_to": None})
        else:
            explicit_meetings[file] = ["(会議を丸ごと)"]
    explicit_snippets = []
    append_whole(explicit_snippets, explicit_meetings, args.max_verbatim_tokens)
    expand = args.expand_grep and not args.skip_ledger
    planned_calls = len(plans) + int(expand) + len(make_batches(explicit_snippets, args.max_verbatim_tokens))
    plan = {
        "topic": args.topic, "dry_run": args.dry_run, "passes": 0 if args.skip_ledger else args.passes,
        "parallel": args.parallel, "chunk_tokens": args.chunk_tokens,
        "files": [row["file"] for row in args.parse_coverage], "missing_defaults": args.missing,
        "parse_coverage": args.parse_coverage,
        "chunks": list(chunk_rows.values()), "planned_calls": planned_calls,
        "explicit_meetings": list(map(str, explicit_meetings)), "unresolved_sources": unresolved_meetings,
    }
    write_json(outdir / "plan.json", plan)
    if args.dry_run:
        for row in args.parse_coverage:
            print(f"{row['file']}（{describe_parse_coverage(row)}）")
        print(f"区切り {len(plans)} 件・予定呼び出し {planned_calls} 回（下読み後に決まる回数と再試行を除く）")
        print(outdir / "plan.json")
        return 0
    if planned_calls:
        configure_agent(args, outdir, root, cleanup)
        calls = outdir / "calls"
        if calls.is_symlink():
            raise ValueError(f"calls/ は実フォルダにする：{calls}")
        calls.mkdir(exist_ok=True)

    hits = {}  # (id) → dict
    unknown_ids = []

    # ── 1・2 台帳・判断台帳の下読み（passes 回・和集合）＋言い換え語の grep ──
    failed_chunks = []
    grep_info = {}

    def record_status(row, error):
        row.update(state="FAILED" if error else "OK", error=error)
        if error:
            failed_chunks.append(row["name"])

    if not args.skip_ledger:
        def run_chunk(item):
            name, c, tk = item
            body = "".join(b for _, b in c)
            prompt = build_prompt("scan.md", args, body)
            data, secs, error = agent_call(prompt, f"scan_{name}", outdir, "scan", args, "hits")
            log(f"  {name}: {'失敗' if error else '完了'}（{secs:.0f}秒・{len(data['hits']) if data else 0}件）")
            return name, c, data, error

        def run_terms():
            prompt = build_prompt("terms.md", args, "")
            data, secs, error = agent_call(prompt, "terms", outdir, "terms", args, "terms")
            log(f"  語の一覧: {'完了' if data is not None else '失敗'}（{secs:.0f}秒・{len(data.get('terms', [])) if data else 0}語）")
            return data, error

        jobs = ([("terms", None)] if expand else []) + [("scan", it) for it in plans]

        def run_job(job):
            return run_terms() if job[0] == "terms" else run_chunk(job[1])

        with cf.ThreadPoolExecutor(max_workers=args.parallel) as ex:
            jres_all = list(ex.map(run_job, jobs))
        terms_data = None
        results = []
        for job, r in zip(jobs, jres_all):
            if job[0] == "terms":
                terms_data, error = r
                row = {"name": "terms", "pass": None, "index": 1, "file": None, "ids": []}
                chunk_rows["terms"] = row
                record_status(row, error)
            else:
                results.append(r)
        for name, c, data, error in results:
            record_status(chunk_rows[name], error)
            if data is None:
                continue
            allowed = {e.id: e for e, _ in c}
            for h in data["hits"]:
                add_hit(hits, h, "preread:" + name.split("-")[0], name, allowed, unknown_ids)
        n_scan = len(hits)
        log(f"モデルが拾った記録 {n_scan} 件（{args.passes} 回の和集合・失敗した区切り {len(failed_chunks)}）")

        # ── grep の経路 ──
        if expand:
            terms = []
            if terms_data:
                for tm in terms_data.get("terms", []):
                    s = str(tm.get("term", "")).strip()
                    if len(s) >= 2 and s not in [x["term"] for x in terms]:
                        terms.append({"term": s, "kind": tm.get("kind", ""), "reading": tm.get("reading", "")})
            matched = {}  # 記録の位置 → [語]
            for tm in terms:
                ids_ = [i for i, e in enumerate(all_entries) if tm["term"] in e.text]
                tm["count"] = len(ids_)
                if len(ids_) > args.grep_generic * len(all_entries) or not ids_:
                    tm["dropped"] = "一般的すぎる" if ids_ else "当たりなし"
                    continue
                for i in ids_:
                    matched.setdefault(i, []).append(tm["term"])
            cand = [i for i in matched if all_entries[i].id not in hits]
            both = [i for i in matched if all_entries[i].id in hits]
            grep_info = {"terms": terms, "matched_entries": len(matched), "overlap_with_scan": len(both), "grep_only_candidates": len(cand)}
            log(f"grep：語 {len(terms)}（捨てた {sum(1 for t_ in terms if t_.get('dropped'))}）→ 当たった記録 {len(matched)} 件（モデルと重なる {len(both)}・grep だけ {len(cand)}）")
            for i in both:
                h = hits[all_entries[i].id]
                if "grep" not in h["routes"]:
                    h["routes"].append("grep")
                h["grep_terms"] = matched[i]
            if cand and len(cand) <= args.grep_direct_max:
                for i in cand:
                    e = all_entries[i]
                    hits[e.id] = {"id": e.id, "section": e.section, "what": "（語の一致で拾った・モデルは判定していない）",
                                  "why": "語の一致：" + "・".join(matched[i][:6]), "mishearing": "", "strength": "周辺",
                                  "routes": ["grep"], "chunks": ["grep"], "grep_terms": matched[i]}
            elif cand:
                ce = [all_entries[i] for i in cand]
                jchunks = make_chunks(ce, args.chunk_tokens, "grepjudge-")
                log(f"grep だけの当たり {len(cand)} 件が多いので、モデルに判定させる（{len(jchunks)} 回）")

                def run_judge(it):
                    prompt = build_prompt("scan.md", args, "".join(b for _, b in it[1]))
                    data, _, error = agent_call(prompt, f"judge_{it[0]}", outdir, "judge", args, "hits")
                    return it, data, error

                with cf.ThreadPoolExecutor(max_workers=args.parallel) as ex:
                    jres = list(ex.map(run_judge, jchunks))
                judged_in, rejected, unjudged = set(), set(), set()
                idx_of = {all_entries[i].id: i for i in cand}
                for it, data, error in jres:
                    name, chunk, _ = it
                    row = chunk_rows[name] = describe_chunk(it, args.chunk_tokens)
                    record_status(row, error)
                    allowed = {e.id: e for e, _ in chunk}
                    accepted = set()
                    for h in data["hits"] if data else []:
                        hid = add_hit(hits, h, "grep", name, allowed, unknown_ids)
                        if hid:
                            accepted.add(hid)
                            hits[hid]["grep_terms"] = matched[idx_of[hid]]
                    if error:
                        unjudged.update(allowed)
                    else:
                        judged_in.update(accepted)
                        rejected.update(allowed.keys() - accepted)
                grep_info["judged_in"] = len(judged_in)
                grep_info["judged_out"] = len(rejected)
                grep_info["rejected_ids"] = sorted(rejected)
                grep_info["unjudged_ids"] = sorted(unjudged)
        log(f"拾った記録 {len(hits)} 件（今回の材料にない番号 {len(unknown_ids)} 件は捨てた・失敗した区切り {len(failed_chunks)}）")

    # ── 3 出典から逐語の場所をたどる ──
    win_items, meeting_cites, unresolved = [], {}, unresolved_meetings.copy()
    direct_meeting_cites, mandatory_whole, sources = {}, {}, {}
    rank = {"直接": 0, "関連": 1, "周辺": 2}
    ordered_hits = sorted(hits.items(), key=lambda kv: (rank.get(kv[1].get("strength"), 3), kv[0]))
    vstr = set(args.verbatim_from.split(","))
    for hid, h in ordered_hits:
        entry = by_id[hid]
        ws, ms, full, why = resolve_refs(entry, args)
        file = ws[0][0] if ws else next(iter(full or ms), None)
        file_windows = [(s, e) for f, s, e in ws if f == file]
        state = "resolved" if file else "unresolved" if entry.source else "missing"
        sources[hid] = {
            "raw": entry.source, "state": state, "why": why, "file": str(file) if file else None,
            "line_from": max(1, min(s for s, _ in file_windows) - args.pad) if file_windows else
                         1 if file in full else None,
            "line_to": min(len(raw_lines(file)), max(e for _, e in file_windows) + args.pad) if file_windows else
                       len(raw_lines(file)) if file in full else None,
        }
        if why:
            unresolved.append({"id": hid, **sources[hid]})
        strength = h.get("strength", "周辺")
        if args.skip_verbatim or (strength if strength in rank else "周辺") not in vstr:
            continue
        win_items.extend((f, s, e, hid) for f, s, e in ws)
        for f in full:
            mandatory_whole.setdefault(f, set()).add(hid)
        for f in ms:
            meeting_cites.setdefault(f, set()).add(hid)
            if strength == "直接":
                direct_meeting_cites.setdefault(f, set()).add(hid)

    merged = merge_windows(win_items, args.pad)
    # 窓が多すぎるときは、直接の記録に由来するものを先に
    hit_rank = {hid: rank.get(h.get("strength"), 3) for hid, h in hits.items()}
    merged.sort(key=lambda w: (min(hit_rank.get(i, 3) for i in w[3]), w[0].name, w[1]))
    dropped_windows = merged[args.max_windows:]
    merged = merged[:args.max_windows]

    snippets = []  # (sid, file, s, e, record_ranges, text)
    if not args.skip_verbatim:
        for f, s, e, ranges in merged:
            # 長すぎる窓は割る
            step = 220
            for a in range(s, e + 1, step):
                b = min(e, a + step - 1)
                snippets.append([f"s{len(snippets) + 1}", f, a, b,
                                 clip_record_ranges(ranges, a, b), numbered(f, a, b)])

    # 明示の会議、時刻のない逐語／メール、行が指定されていない会議を丸ごと読む。
    ranked = sorted(direct_meeting_cites.items(), key=lambda kv: -len(kv[1]))[:args.whole_meetings]
    whole = {f: set(ids) for f, ids in explicit_meetings.items()}
    for f, ids in [*mandatory_whole.items(), *ranked]:
        whole.setdefault(f, set()).update(ids)
    append_whole(snippets, {f: sorted(ids) for f, ids in whole.items()}, args.max_verbatim_tokens)
    batches = make_batches(snippets, args.max_verbatim_tokens)
    log(f"逐語：窓 {len(merged)}（割った後 {len(snippets)}）→ 呼び出し {len(batches)} 回")

    verb = {}  # sid → result
    invalid_passages = 0
    if batches:
        def run_batch(item):
            i, bt = item
            body = "\n\n".join(
                f'<snippet id="{sid}" file="{html.escape(f.name)}" lines="L{a}-L{b}" '
                f'出典の記録="{html.escape(", ".join(ranges))}">\n{escape_prompt_material(txt)}\n</snippet>'
                for sid, f, a, b, ranges, txt in bt)
            prompt = build_prompt("verbatim.md", args, body)
            data, secs, error = agent_call(prompt, f"verbatim_{i}", outdir, "verbatim", args,
                                           "snippets", {sn[0] for sn in bt})
            log(f"  逐語 {i}: {'失敗' if error else '完了'}（{secs:.0f}秒）")
            return i, bt, data, error

        with cf.ThreadPoolExecutor(max_workers=args.parallel) as ex:
            vres = list(ex.map(run_batch, enumerate(batches, 1)))
        for i, bt, data, error in vres:
            expected = {sn[0]: (sn[2], sn[3]) for sn in bt}
            for r in data["snippets"] if data else []:
                sid = r["snippet"]
                a, b = expected[sid]
                valid = []
                for passage in r["passages"]:
                    lines = passage.get("lines") if isinstance(passage, dict) else None
                    if (isinstance(lines, list) and len(lines) == 2 and all(type(n) is int for n in lines)
                            and a <= lines[0] <= lines[1] <= b):
                        valid.append({
                            "lines": lines,
                            **{key: passage[key] for key in ("says", "mishearing") if isinstance(passage.get(key), str)},
                        })
                    else:
                        invalid_passages += 1
                verb[sid] = {"relevant": r["relevant"] is True, "summary": r.get("summary", ""), "passages": valid}
            if error:
                for sid in expected:
                    verb[sid] = {"failed": True}
            files = list(dict.fromkeys(str(sn[1]) for sn in bt))
            name = f"verbatim_{i}"
            row = chunk_rows[name] = {
                "name": name, "pass": None, "index": i, "file": files[0] if len(files) == 1 else None,
                "files": files, "ids": sorted({hid for sn in bt for hid in sn[4] if hid in by_id}),
                "snippets": [{"file": str(f), "line_from": a, "line_to": b, "id": sid} for sid, f, a, b, _, _ in bt],
            }
            record_status(row, error)

    # ── 4 結果と実行記録 ──
    elapsed = time.time() - t_start
    excerpts = []
    for sid, file, _, _, ranges, _ in snippets:
        answer = verb[sid]
        if answer.get("failed"):
            continue
        lines = sorted({n for passage in answer["passages"] for n in range(passage["lines"][0], passage["lines"][1] + 1)}
                       if answer["relevant"] is True else set())
        for hid, spans in ranges.items():
            for a, b in spans:
                excerpts.append({
                    "record_id": hid if hid in by_id else None, "file": str(file), "line_from": a, "line_to": b,
                    "quotes": [{"line": n, "text": line_text(file, n)} for n in lines if a <= n <= b],
                })

    for record_id in {ex["record_id"] for ex in excerpts} & hits.keys():
        hits[record_id]["routes"].append("source")
    records = [
        {**h, "file": str(by_id[hid].file), "line": by_id[hid].line, "reasons": h.get("reasons", [h.get("why", "")]),
         "misheard": [h["mishearing"]] if h.get("mishearing") else [],
         "source": sources[hid]}
        for hid, h in ordered_hits
    ]
    result = {
        "topic": args.topic, "status": "PARTIAL" if failed_chunks else "COMPLETE", "records": records,
        "excerpts": excerpts, "chunks": list(chunk_rows.values()), "unresolved_sources": unresolved,
        "counts": {"calls": STATS["calls"], "invented_ids_dropped": len(unknown_ids),
                   "unverified_quotes_dropped": invalid_passages, "invalid_passages_dropped": invalid_passages,
                   "parse_coverage": args.parse_coverage,
                   "preface_lines": sum(row["preface_lines"] for row in args.parse_coverage),
                   "unread_lines": sum(row["unread_lines"] for row in args.parse_coverage),
                   "unresolved_sources": len(unresolved), "skipped_windows": len(dropped_windows),
                   "failed_chunks": len(failed_chunks)},
    }
    write_json(outdir / "hits.json", {
        "hits": hits, "unknown_ids": unknown_ids, "failed_chunks": failed_chunks, "grep": grep_info})
    write_json(outdir / "result.json", result)
    write_result(outdir, args, plan, result, ledger, journal, hits, unknown_ids, snippets, verb,
                 meeting_cites, dropped_windows, elapsed, by_id)
    write_json(outdir / "stats.json", {**STATS, "elapsed_secs": elapsed, "hits": len(hits)})
    print(outdir / "result.md")
    log(f"{result['status']}：{elapsed:.0f}秒・モデル呼び出し {STATS['calls']} 回（再試行 {STATS['retries']}・失敗 {STATS['failures']}）")
    return 3 if failed_chunks else 0


def markdown_model_text(text):
    """モデルの自由文を Markdown に表示するときは1行・200字に収める。"""
    flat = " ".join(text.split()).replace("<!--", "&lt;!--") if isinstance(text, str) else ""
    return flat if len(flat) <= 200 else flat[:199] + "…"


def write_result(outdir, args, plan, result, ledger, journal, hits, unknown_ids, snippets, verb,
                 meeting_cites, dropped_windows, elapsed, by_id):
    L = [f"# 意味で拾った結果：{args.topic}", "", "## 見た範囲", ""]
    L.append(f"- 状態 {result['status']}・下読み {plan['passes']} 回（計画）")
    for row in plan["parse_coverage"]:
        filename = row["file"]
        n = sum(filename in chunk["files"] for chunk in plan["chunks"])
        L.append(f"- {filename}（下読み {n} 区切り・{describe_parse_coverage(row)}）")
    for filename in sorted({str(sn[1]) for sn in snippets}):
        n = sum(str(sn[1]) == filename for sn in snippets)
        L.append(f"- {filename}（切り出し {n} 窓）")
    for filename in plan["missing_defaults"]:
        L.append(f"- --project の既定の入力がない：{filename}")
    for row in result["chunks"]:
        if row["state"] != "FAILED":
            continue
        ids = row["ids"]
        span = f"（{ids[0]}〜{ids[-1]}）" if ids else ""
        L.append(f"- **FAILED {row['name']}**{span}：{markdown_model_text(row['error'])}")
    L.append(f"- 未解決の出典 {result['counts']['unresolved_sources']} 件")
    L.append(f"- 上限（--max-windows）で読まなかった窓 {result['counts']['skipped_windows']} 件")
    L.append(f"- 渡した窓の範囲にない引用 {result['counts']['invalid_passages_dropped']} 件を除外")
    L.extend(["", "拾い漏れが無いことは保証しない。関係ありの判定は緩い。使う前に正本と一次の記録を開いて確かめる。", ""])
    L.append(f"- 日時 {dt.datetime.now():%Y-%m-%d %H:%M}・モデル {args.model or '指定なし'}・使い捨て")
    if args.hint:
        L.append(f"- 補足：{args.hint}")
    L.append(f"- 台帳 {len(ledger)} 件・判断台帳 {len(journal)} 件を読んだ。かかった時間 {elapsed:.0f} 秒・モデルを呼んだ回数 {STATS['calls']}（再試行 {STATS['retries']}・失敗 {STATS['failures']}）")
    rc = {}
    for h in hits.values():
        key = "＋".join(sorted(set(h.get("routes", []))))
        rc[key] = rc.get(key, 0) + 1
    L.append(f"- 拾った経路の内訳（件）：" + "・".join(f"{k} {v}" for k, v in sorted(rc.items())))
    if unknown_ids:
        ids = ", ".join(sorted({u[0] for u in unknown_ids}))
        L.append(f"- 原文に無い番号を答えたので捨てた：{markdown_model_text(ids)}")
    L.append("")
    L.append("## A. 台帳・判断台帳で拾った記録")
    L.append("")
    rank = {"直接": 0, "関連": 1, "周辺": 2}
    items = sorted(hits.items(), key=lambda kv: (rank.get(kv[1].get("strength"), 3), kv[0]))
    for strength in ("直接", "関連", "周辺"):
        sub = [(k, h) for k, h in items if h.get("strength", "周辺") == strength] if strength != "周辺" else \
              [(k, h) for k, h in items if h.get("strength") not in ("直接", "関連")]
        if not sub:
            continue
        L.append(f"### {strength}（{len(sub)} 件）")
        L.append("")
        for k, h in sub:
            entry = by_id[k]
            sec = entry.section
            L.append(f"- **{k}**（{sec}）{markdown_model_text(h.get('what'))}")
            grep_terms = markdown_model_text("・".join(h.get("grep_terms", [])[:6]))
            L.append(f"  - 拾った経路：{'・'.join(h.get('routes', []))}" + (f"（当たった語：{grep_terms}）" if grep_terms else ""))
            L.append(f"  - 関係する理由：{markdown_model_text(h.get('why'))}")
            if h.get("mishearing"):
                L.append(f"  - 聞き違いと読んだ語：{markdown_model_text(h['mishearing'])}")
            if entry.source:
                L.append(f"  - 出典の欄：{entry.source[:300]}")
        L.append("")
    if not hits:
        L.append("（拾えたものなし）")
        L.append("")
    if result["unresolved_sources"]:
        L.extend(["### 未解決の出典", ""])
        for source in result["unresolved_sources"]:
            if source["id"] is None:
                L.append(f"- --meeting：{source['why']}")
            else:
                L.append(f"- {source['id']}：{source['why']}（{source['raw'] or '出典なし'}）")
        L.append("")

    L.append("## B. 一次の記録で関係する発言・記述")
    L.append("")
    L.append("引用は逐語の原文の行そのまま（聞き違いは直していない）。「読み」は モデルが音と業務の意味で読んだもの。")
    L.append("")
    by_file = {}
    for sid, f, a, b, ids, txt in snippets:
        r = verb.get(sid)
        if r is None:
            continue
        by_file.setdefault(f, []).append((a, b, ids, r))
    n_pass = 0
    for f, lst in sorted(by_file.items(), key=lambda kv: kv[0].name):
        rel_lst = [x for x in lst if x[3].get("relevant") is True and x[3].get("passages")]
        failed = [x for x in lst if x[3].get("failed")]
        if not rel_lst and not failed:
            continue
        L.append(f"### {f.name}")
        L.append("")
        for a, b, ranges, r in sorted(lst, key=lambda x: x[0]):
            if r.get("failed"):
                L.append(f"- （L{a}〜L{b}：読みに失敗）")
                continue
            if not (r.get("relevant") is True and r.get("passages")):
                continue
            L.append(f"- 窓 L{a}〜L{b} {markdown_model_text(r.get('summary'))}")
            for p in r.get("passages", []):
                s, e = p["lines"]
                n_pass += 1
                mishearing = markdown_model_text(p.get("mishearing"))
                L.append(f"  - **L{s}〜L{e}**：{markdown_model_text(p.get('says'))}" + (f"〔聞き違いと読んだ語：{mishearing}〕" if mishearing else ""))
                cited = [f"{hid} L{start}〜L{end}" for hid, spans in clip_record_ranges(ranges, s, e).items()
                         for start, end in spans if hid in by_id]
                if cited:
                    L.append(f"    出典の記録：{'、'.join(cited)}")
                shown = list(range(s, min(e, s + 11) + 1))
                for i in shown:
                    L.append(f"    > L{i}: {line_text(f, i)}")
                if e > s + 11:
                    L.append(f"    > …（L{s + 12}〜L{e} は省略）")
        L.append("")
    if not n_pass:
        L.append("（逐語で拾えた発言なし）")
        L.append("")
    nonrel = [(f, a, b, ids) for sid, f, a, b, ids, txt in snippets
              if verb.get(sid) and not verb[sid].get("failed") and not (verb[sid].get("relevant") is True and verb[sid].get("passages"))]
    if nonrel:
        L.append("### 逐語を読んだが関係する発言は無かった窓")
        L.append("")
        for f, a, b, ids in nonrel:
            L.append(f"- {f.name} L{a}〜L{b}（出典の記録：{', '.join(ids)}）")
        L.append("")
    if dropped_windows:
        L.append(f"### 上限（--max-windows）で読まなかった窓 {len(dropped_windows)} 件")
        L.append("")
        for f, a, b, ids in dropped_windows:
            L.append(f"- {f.name} L{a}〜L{b}（{', '.join(sorted(ids))}）")
        L.append("")
    if meeting_cites:
        L.append("### 出典の欄が会議までしか指していない（行の指定なし）記録")
        L.append("")
        for f, ids in sorted(meeting_cites.items(), key=lambda kv: -len(kv[1])):
            L.append(f"- {f.name}：{', '.join(sorted(ids))}（丸ごと読むなら --meeting {f.stem}）")
        L.append("")
    write_text(outdir / "result.md", "\n".join(L) + "\n")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, re.error, subprocess.TimeoutExpired) as exc:
        print(f"meaning_search: {exc}", file=sys.stderr)
        sys.exit(2)
