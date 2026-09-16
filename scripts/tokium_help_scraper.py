#!/usr/bin/env python3
"""support.keihi.com/ai-agent/ 配下の「TOKIUM AI明細入力」関連ページを
ヘッドレスブラウザで描画してから逐語Markdownに保存するスクレイパ。

使い方:
    pip install playwright && playwright install chromium
    python3 scripts/tokium_help_scraper.py [--outdir ./tokium_help] [--depth 2]

方針:
  - 本文は逐語のみ。要約・言い換えはしない。
  - 取得できなかったページは「未取得」と理由だけ記録し、内容は推測しない。
  - support.keihi.com 以外へは遷移しない。フォーム送信もしない。
  - robots.txt を先に取得し、Disallow に該当する URL は取得しない。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.parse as up
from pathlib import Path

from playwright.sync_api import sync_playwright, Error as PWError

DOMAIN = "support.keihi.com"
BASE = f"https://{DOMAIN}"
SECTION_PREFIX = "/ai-agent/"
START_URL = (
    "https://support.keihi.com/ai-agent/"
    "tokium-ai-%E6%98%8E%E7%B4%B0%E5%85%A5%E5%8A%9B%E3%82%92%E5%88%A9%E7%94%A8%E3%81%99%E3%82%8B"
)

# 再帰取得の対象にするかを判定するキーワード（タイトル or 本文に含まれること）
CRAWL_KEYWORDS = [
    "明細入力", "抽出ルール", "共有ルール", "抽出設定", "学習", "勘定科目", "仕訳",
]

# _summary.md に抽出するキーワード
SUMMARY_KEYWORDS = [
    "プロンプト", "抽出ルール", "共有ルール", "抽出設定", "学習", "自動改善",
    "勘定科目", "仕訳", "優先", "上書き", "承認", "履歴", "復元", "元に戻す",
    "即時", "反映", "LLM", "生成AI", "OpenAI",
]

# ログイン要求の判定に使う手掛かり
LOGIN_HINTS = [
    "ログインしてください", "ログインが必要", "サインイン", "この記事を表示する権限",
    "Sign in to continue", "ログインしてサポートに問い合わせ",
]

CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]


# ---------------------------------------------------------------- robots.txt

class Robots:
    def __init__(self, text: str | None, source_note: str):
        self.text = text
        self.source_note = source_note
        self.disallow: list[str] = []
        self.allow: list[str] = []
        if text:
            self._parse(text)

    def _parse(self, text: str) -> None:
        applies = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "user-agent":
                applies = value == "*"
            elif applies and key == "disallow" and value:
                self.disallow.append(value)
            elif applies and key == "allow" and value:
                self.allow.append(value)

    def allowed(self, url: str) -> bool:
        if not self.text:
            # robots.txt が取れていない場合は「不明」。安全側に倒して取得しない。
            return False
        path = up.urlsplit(url).path or "/"
        path = up.unquote(path)
        best_allow = max((len(p) for p in self.allow if path.startswith(up.unquote(p))), default=-1)
        best_deny = max((len(p) for p in self.disallow if path.startswith(up.unquote(p))), default=-1)
        return best_allow >= best_deny


# ---------------------------------------------------------------- DOM 抽出

# ページ内の本文コンテナ候補（上から順に試す）
EXTRACT_JS = r"""
() => {
  const sels = [
    'article', 'main', '[class*="article-body"]', '[class*="ArticleBody"]',
    '[class*="content-body"]', '[class*="post-content"]', '#content', '.content',
  ];
  let root = null;
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.innerText && el.innerText.trim().length > 200) { root = el; break; }
  }
  if (!root) root = document.body;

  const blocks = [];
  const images = [];
  const seen = new Set();

  const walk = (node) => {
    if (node.nodeType !== 1) return;
    const tag = node.tagName.toLowerCase();
    if (['script','style','noscript','nav','header','footer','svg'].includes(tag)) return;

    if (tag === 'img') {
      images.push({alt: node.getAttribute('alt') || '', src: node.currentSrc || node.src || node.getAttribute('src') || ''});
      blocks.push({type: 'img', alt: node.getAttribute('alt') || '', src: node.currentSrc || node.src || node.getAttribute('src') || ''});
      return;
    }
    if (/^h[1-6]$/.test(tag)) {
      const t = (node.innerText || '').trim();
      if (t && !seen.has('h:' + t + ':' + blocks.length)) {
        blocks.push({type: 'heading', level: parseInt(tag[1], 10), text: t, id: node.id || ''});
      }
      return;
    }
    if (['p','li','td','th','dd','dt','blockquote','pre','figcaption'].includes(tag)) {
      // 入れ子の li/p を二重に出さないため、子に同種ブロックが無い場合のみ出力
      const nested = node.querySelector('p,li,td,th,dd,dt,blockquote,pre');
      if (!nested) {
        const t = (node.innerText || '').trim();
        if (t) blocks.push({type: tag === 'li' ? 'li' : (tag === 'pre' ? 'pre' : 'p'), text: t});
        // 画像は本文ブロック内にも入りうるので拾う
        node.querySelectorAll('img').forEach(im => {
          images.push({alt: im.getAttribute('alt') || '', src: im.currentSrc || im.src || im.getAttribute('src') || ''});
          blocks.push({type: 'img', alt: im.getAttribute('alt') || '', src: im.currentSrc || im.src || im.getAttribute('src') || ''});
        });
        return;
      }
    }
    for (const child of node.childNodes) walk(child);
  };
  walk(root);

  const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
    href: a.href, text: (a.innerText || '').trim()
  }));

  // 最終更新日らしき表記を拾う（本文中の表記のみ。推測はしない）
  let updated = '';
  const bodyText = document.body.innerText || '';
  const m = bodyText.match(/(最終更新[^\n]{0,40}|更新日[^\n]{0,40}|Updated[^\n]{0,40})/);
  if (m) updated = m[1].trim();

  return {
    title: (document.querySelector('h1')?.innerText || document.title || '').trim(),
    docTitle: document.title || '',
    blocks, images, links, updated,
    fullText: bodyText,
  };
}
"""


def slugify(url: str) -> str:
    path = up.unquote(up.urlsplit(url).path)
    slug = path.rstrip("/").split("/")[-1] or "index"
    slug = re.sub(r'[\\/:*?"<>|\s]+', "_", slug)
    return slug[:120]


def to_markdown(url: str, fetched_at: str, data: dict) -> str:
    out: list[str] = []
    out.append(f"# {data['title'] or slugify(url)}")
    out.append("")
    out.append(f"- 取得URL: {url}")
    out.append(f"- 取得日時: {fetched_at}")
    out.append(f"- ページの最終更新日: {data['updated'] or '（本文に記載なし）'}")
    out.append("")
    out.append("---")
    out.append("")
    for b in data["blocks"]:
        if b["type"] == "heading":
            lvl = min(max(b["level"], 1), 6)
            anchor = f" <!-- id={b['id']} -->" if b.get("id") else ""
            out.append("")
            out.append("#" * (lvl + 1) + " " + b["text"] + anchor)
            out.append("")
        elif b["type"] == "li":
            out.append(f"- {b['text']}")
        elif b["type"] == "pre":
            out.append("```")
            out.append(b["text"])
            out.append("```")
        elif b["type"] == "img":
            out.append(f"![{b['alt']}]({b['src']})")
        else:
            out.append(b["text"])
            out.append("")
    if data["images"]:
        out.append("")
        out.append("## 画像一覧（alt / src のみ。画像内テキストの推測はしない）")
        out.append("")
        out.append("| alt | src |")
        out.append("| --- | --- |")
        for im in data["images"]:
            alt = im["alt"].replace("|", "\\|") or "(alt なし)"
            out.append(f"| {alt} | {im['src']} |")
    return "\n".join(out) + "\n"


SENT_SPLIT = re.compile(r"(?<=[。！？\n])")


def split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in SENT_SPLIT.split(text)]
    return [s for s in parts if s]


def build_summary(pages: list[dict]) -> str:
    rows = []
    for page in pages:
        body = "\n".join(
            b.get("text", "") for b in page["data"]["blocks"] if b["type"] != "img"
        )
        sents = split_sentences(body)
        for i, s in enumerate(sents):
            hits = [k for k in SUMMARY_KEYWORDS if k in s]
            if not hits:
                continue
            ctx = " ".join(sents[max(0, i - 1): i + 2])
            ctx = ctx.replace("|", "\\|").replace("\n", " ")
            title = page["data"]["title"].replace("|", "\\|")
            hit_str = " / ".join(hits)
            rows.append(f"| {title} | {page['url']} | {hit_str} | {ctx} |")
    head = [
        "# _summary.md — キーワード該当文（逐語）",
        "",
        f"- 生成日時: {dt.datetime.now().astimezone().isoformat()}",
        f"- 対象キーワード: {' / '.join(SUMMARY_KEYWORDS)}",
        f"- ヒット件数: {len(rows)}",
        "",
        "| ページタイトル | URL | ヒット語 | 該当文（逐語、前後1文込み） |",
        "| --- | --- | --- | --- |",
    ]
    return "\n".join(head + rows) + "\n"


def launch_browser(p):
    for path in CHROMIUM_CANDIDATES:
        if Path(path).exists():
            return p.chromium.launch(executable_path=path)
    return p.chromium.launch()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="./tokium_help")
    ap.add_argument("--depth", type=int, default=2)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    fetched: list[dict] = []
    skipped: list[dict] = []

    with sync_playwright() as p:
        browser = launch_browser(p)
        ctx = browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        # 1. robots.txt
        try:
            r = page.goto(f"{BASE}/robots.txt", wait_until="domcontentloaded", timeout=30000)
            robots_text = page.evaluate("() => document.body.innerText") if r and r.ok else None
            robots = Robots(robots_text, f"HTTP {r.status if r else 'n/a'}")
        except PWError as e:
            robots = Robots(None, f"取得失敗: {type(e).__name__}: {e}")
        (outdir / "_robots.txt").write_text(
            (robots.text or f"（robots.txt 未取得: {robots.source_note}）") + "\n", encoding="utf-8"
        )
        print(f"[robots] {robots.source_note}; Disallow={robots.disallow}", file=sys.stderr)
        if not robots.text:
            print("robots.txt が取得できないため、クロールを中止します。", file=sys.stderr)
            browser.close()
            return 2

        # 2. BFS クロール
        queue: list[tuple[str, int]] = [(START_URL, 0)]
        visited: set[str] = set()

        while queue:
            url, depth = queue.pop(0)
            key = up.unquote(up.urlsplit(url).path)
            if key in visited:
                continue
            visited.add(key)

            if up.urlsplit(url).netloc != DOMAIN:
                skipped.append({"url": url, "reason": "同一ドメイン外"})
                continue
            if not robots.allowed(url):
                skipped.append({"url": url, "reason": "robots.txt で Disallow"})
                continue

            try:
                resp = page.goto(url, wait_until="networkidle", timeout=60000)
            except PWError as e:
                skipped.append({"url": url, "reason": f"未取得: {type(e).__name__}: {str(e)[:200]}"})
                continue
            if resp and resp.status >= 400:
                skipped.append({"url": url, "reason": f"未取得: HTTP {resp.status}"})
                continue

            data = page.evaluate(EXTRACT_JS)

            if any(h in data["fullText"] for h in LOGIN_HINTS):
                skipped.append({"url": url, "reason": "ログイン必須"})
                continue

            haystack = data["title"] + "\n" + data["fullText"]
            if depth > 0 and not any(k in haystack for k in CRAWL_KEYWORDS):
                skipped.append({"url": url, "reason": "対象キーワード不一致（保存対象外）"})
                continue

            fetched_at = dt.datetime.now().astimezone().isoformat()
            (outdir / f"{slugify(url)}.md").write_text(
                to_markdown(url, fetched_at, data), encoding="utf-8"
            )
            fetched.append({"url": url, "data": data})
            print(f"[ok] depth={depth} {url}", file=sys.stderr)

            if depth < args.depth:
                for link in data["links"]:
                    href = link["href"].split("#")[0]
                    sp = up.urlsplit(href)
                    if sp.netloc != DOMAIN:
                        continue
                    if not up.unquote(sp.path).startswith(SECTION_PREFIX):
                        continue
                    if up.unquote(sp.path) in visited:
                        continue
                    queue.append((href, depth + 1))

        browser.close()

    (outdir / "_summary.md").write_text(build_summary(fetched), encoding="utf-8")
    report = {
        "fetched_count": len(fetched),
        "fetched": [f["url"] for f in fetched],
        "skipped_count": len(skipped),
        "skipped": skipped,
        "robots_disallow": robots.disallow,
    }
    (outdir / "_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
