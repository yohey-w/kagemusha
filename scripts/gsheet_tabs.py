#!/usr/bin/env python3
"""Google Spreadsheet 全タブ実査ユーティリティ / full-tab inspector for a Google Sheet.

なぜ要るか (JA): Google Drive経由でスプレッドシートを「普通に」読み取る/エク
スポートする経路の多くは1タブ分しか見せず、複数タブのブックを渡すと調査エー
ジェントが「見つからない」と誤報告する事故を起こす。このスクリプトは Drive
API の export (xlsx) を直接叩いてワークブック全体を取得し、
xl/workbook.xml からシート名を列挙、各シートの先頭N行をTSVで出力する——
「このブックに何タブあるか」を最初の1手で機械的に確定させるための道具。

Why this exists (EN): Reading a multi-tab Google Sheet through most "plain"
Drive read/export paths surfaces only one tab, which causes investigating
agents to falsely report "sheet not found" when the data is actually on a
different tab. This tool hits the Drive API's xlsx export directly, lists
every sheet name from xl/workbook.xml inside the zip, and prints the first
N rows of each tab as TSV — a mechanical first move to confirm what tabs
actually exist before searching for data on any one of them.

方法の序列 / method hierarchy — もっとシンプルな方法が先にある:
    既定 (JA): エージェント文脈で Drive MCP (`download_file_content`) が使え
    るなら、xlsx形式を指定してダウンロードし、標準ライブラリの zipfile/xml
    だけでタブ名を読めば足りる——追加のOAuth認証もこのスクリプトも不要。
    最小例(5行程度):

        import zipfile, xml.etree.ElementTree as ET
        NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        zf = zipfile.ZipFile('downloaded.xlsx')
        root = ET.fromstring(zf.read('xl/workbook.xml'))
        names = [s.get('name') for s in root.find(f'{NS}sheets').findall(f'{NS}sheet')]

    このスクリプト (gsheet_tabs.py) は、Drive MCP が使えない環境
    (cron・素のシェル・MCPなしのCLI実行) 向けの予備手段——自前でDrive API
    を叩いてダウンロードからタブ列挙・行出力までを一括でやる。

    Default (EN): inside an agent context with Drive MCP available, just call
    `download_file_content` with the xlsx format and read tab names with the
    standard-library zipfile/xml combo above — no extra OAuth setup, no need
    for this script. This script is the **fallback for environments without
    Drive MCP** (cron jobs, a bare shell, any MCP-less CLI run): it drives the
    Drive API directly, end to end, from download through listing tabs to
    printing rows.

必要 / requires (このスクリプトを使う場合のみ / only if using this script):
    pip install google-auth-oauthlib google-api-python-client

認証 / auth:
    OAuth credentials (Desktop app client) + a token file, both JSON.
    既定パス / default paths:
        keys:  ~/.config/gsheet-tabs/gcp-oauth.keys.json
        token: ~/.config/gsheet-tabs/token.json
    上書き / override with env vars or flags:
        GSHEET_OAUTH_KEYS=/path/to/keys.json
        GSHEET_TOKEN=/path/to/token.json
    初回実行時、token が無ければブラウザなしのローカルサーバーフローで認可を
    求める(run_local_server(open_browser=False)) — 表示されるURLを手動で開く。
    以降はtokenをrefreshして使い回す。
    First run: if no token exists, it opens a local-server OAuth flow
    (open_browser=False) and prints a URL to visit manually; the resulting
    token is cached and refreshed on subsequent runs.

スコープ / scopes (readonly only):
    drive.readonly, documents.readonly, spreadsheets.readonly

使い方 / usage:
    python3 gsheet_tabs.py <fileId>                 # 全タブ・先頭5行 / all tabs, first 5 rows
    python3 gsheet_tabs.py <fileId> --rows 10        # 先頭10行 / first 10 rows
    python3 gsheet_tabs.py <fileId> --sheet 名前      # 特定タブのみ全行 / one tab, all rows

API 529 (overloaded) 対策 / on API 529:
    ダウンロードが529を返した場合は120秒待って1回だけ再試行する。
    On a transient 529 from the export call, wait 120s and retry once.
"""

import argparse
import io
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DEFAULT_CONFIG_DIR = Path.home() / '.config' / 'gsheet-tabs'
CREDS_PATH = Path(os.environ.get('GSHEET_OAUTH_KEYS', str(DEFAULT_CONFIG_DIR / 'gcp-oauth.keys.json')))
TOKEN_PATH = Path(os.environ.get('GSHEET_TOKEN', str(DEFAULT_CONFIG_DIR / 'token.json')))

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly',
]

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

NS_MAIN = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
NS_REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
NS_PKG_REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'

RETRY_WAIT_SECONDS = 120


def get_credentials():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                print(f"ERROR: OAuth credentials not found at {CREDS_PATH}", file=sys.stderr)
                print("Set GSHEET_OAUTH_KEYS or place a Desktop-app OAuth client JSON there.", file=sys.stderr)
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def download_xlsx_bytes(file_id):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from googleapiclient.errors import HttpError

    creds = get_credentials()
    service = build('drive', 'v3', credentials=creds)

    def _do_export():
        request = service.files().export_media(fileId=file_id, mimeType=XLSX_MIME)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue()

    try:
        return _do_export()
    except HttpError as e:
        if getattr(e, 'status_code', None) == 529 or ' 529' in str(e):
            print(f"[gsheet_tabs] API 529 (overloaded) — waiting {RETRY_WAIT_SECONDS}s and retrying once ...",
                  file=sys.stderr)
            time.sleep(RETRY_WAIT_SECONDS)
            return _do_export()
        raise


def list_sheets(zf):
    """workbook.xml + workbook.xml.rels からシート名→内部パス を得る."""
    wb_xml = zf.read('xl/workbook.xml')
    wb_root = ET.fromstring(wb_xml)
    sheets_el = wb_root.find(f'{NS_MAIN}sheets')

    rels_xml = zf.read('xl/_rels/workbook.xml.rels')
    rels_root = ET.fromstring(rels_xml)
    rid_to_target = {}
    for rel in rels_root.findall(f'{NS_PKG_REL}Relationship'):
        rid_to_target[rel.get('Id')] = rel.get('Target')

    sheets = []
    for sheet_el in sheets_el.findall(f'{NS_MAIN}sheet'):
        name = sheet_el.get('name')
        rid = sheet_el.get(f'{NS_REL}id')
        target = rid_to_target.get(rid)
        if target and not target.startswith('xl/'):
            target = 'xl/' + target
        sheets.append((name, target))
    return sheets


def col_letter_to_index(letters):
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1


def parse_shared_strings(zf):
    if 'xl/sharedStrings.xml' not in zf.namelist():
        return []
    root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    strings = []
    for si in root.findall(f'{NS_MAIN}si'):
        text = ''.join(t.text or '' for t in si.iter(f'{NS_MAIN}t'))
        strings.append(text)
    return strings


def read_sheet_rows(zf, sheet_path, shared_strings, max_rows=None):
    if sheet_path not in zf.namelist():
        return []
    root = ET.fromstring(zf.read(sheet_path))
    sheet_data = root.find(f'{NS_MAIN}sheetData')
    if sheet_data is None:
        return []

    rows_out = []
    cell_ref_re = re.compile(r'([A-Z]+)(\d+)')

    for row_el in sheet_data.findall(f'{NS_MAIN}row'):
        if max_rows is not None and len(rows_out) >= max_rows:
            break
        cells = {}
        max_col = -1
        for c in row_el.findall(f'{NS_MAIN}c'):
            ref = c.get('r', '')
            m = cell_ref_re.match(ref)
            if not m:
                continue
            col_idx = col_letter_to_index(m.group(1))
            cell_type = c.get('t')
            v_el = c.find(f'{NS_MAIN}v')
            is_el = c.find(f'{NS_MAIN}is')
            if cell_type == 's' and v_el is not None:
                try:
                    value = shared_strings[int(v_el.text)]
                except (ValueError, IndexError):
                    value = ''
            elif cell_type == 'inlineStr' and is_el is not None:
                value = ''.join(t.text or '' for t in is_el.iter(f'{NS_MAIN}t'))
            elif v_el is not None:
                value = v_el.text or ''
            else:
                value = ''
            cells[col_idx] = value
            max_col = max(max_col, col_idx)

        row_list = ['' for _ in range(max_col + 1)]
        for idx, val in cells.items():
            row_list[idx] = val
        rows_out.append(row_list)

    return rows_out


def main():
    parser = argparse.ArgumentParser(
        description='Google Spreadsheet 全タブ実査 / full-tab inspector for a Google Sheet')
    parser.add_argument('file_id', help='GドライブのスプレッドシートfileId / Drive file ID of the spreadsheet')
    parser.add_argument('--rows', type=int, default=5, help='各シートの表示行数(既定5) / rows per sheet (default 5)')
    parser.add_argument('--sheet', default=None, help='このシート名のみ全行表示 / show only this sheet, all rows')
    args = parser.parse_args()

    print(f"[gsheet_tabs] downloading xlsx export for {args.file_id} ...", file=sys.stderr)
    data = download_xlsx_bytes(args.file_id)
    zf = zipfile.ZipFile(io.BytesIO(data))

    sheets = list_sheets(zf)
    shared_strings = parse_shared_strings(zf)

    print(f"# {len(sheets)} タブ検出 / tabs detected")
    for name, _ in sheets:
        print(f"- {name}")
    print()

    targets = sheets
    if args.sheet:
        targets = [s for s in sheets if s[0] == args.sheet]
        if not targets:
            print(f"ERROR: シート '{args.sheet}' が見つかりません / sheet not found", file=sys.stderr)
            sys.exit(1)

    for name, path in targets:
        max_rows = None if args.sheet else args.rows
        rows = read_sheet_rows(zf, path, shared_strings, max_rows=max_rows)
        print(f"## {name} ({path})")
        for row in rows:
            print('\t'.join(row))
        print()


if __name__ == '__main__':
    main()
