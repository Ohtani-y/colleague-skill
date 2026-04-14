#!/usr/bin/env python3
"""
Feishu ブラウザスクレイパー（Playwright 方式）

ローカル Chrome のログインセッションを再利用し、トークン不要で権限のある全 Feishu コンテンツにアクセス可能。

対応：
  - Feishu ドキュメント（docx/docs）
  - Feishu ナレッジベース（wiki）
  - Feishu スプレッドシート（sheets）→ CSV としてエクスポート
  - Feishu メッセージ履歴（指定グループチャット）

インストール：
  pip install playwright
  playwright install chromium

使い方：
  python3 feishu_browser.py --url "https://xxx.feishu.cn/wiki/xxx" --output out.txt
  python3 feishu_browser.py --url "https://xxx.feishu.cn/docx/xxx" --output out.txt
  python3 feishu_browser.py --chat "バックエンドチーム" --target "田中太郎" --limit 500 --output out.txt
  python3 feishu_browser.py --url "https://xxx.feishu.cn/sheets/xxx" --output out.csv
"""

from __future__ import annotations

import sys
import time
import json
import argparse
import platform
from pathlib import Path
from typing import Optional


def get_default_chrome_profile() -> str:
    """OS に応じた Chrome デフォルト Profile パスを返す"""
    system = platform.system()
    if system == "Darwin":
        return str(Path.home() / "Library/Application Support/Google/Chrome/Default")
    elif system == "Linux":
        return str(Path.home() / ".config/google-chrome/Default")
    elif system == "Windows":
        import os
        return str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default")
    return str(Path.home() / ".config/google-chrome/Default")


def make_context(playwright, chrome_profile: Optional[str], headless: bool):
    """ログインセッションを再利用するブラウザコンテキストを作成"""
    profile = chrome_profile or get_default_chrome_profile()
    try:
        ctx = playwright.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900},
        )
        return ctx
    except Exception as e:
        print(f"⚠️  Chrome Profile のロードに失敗：{e}", file=sys.stderr)
        print(f"   試行したパス：{profile}", file=sys.stderr)
        print("   --chrome-profile でパスを手動指定してください", file=sys.stderr)
        sys.exit(1)


def detect_page_type(url: str) -> str:
    """URL から Feishu ページタイプを判定"""
    if "/wiki/" in url:
        return "wiki"
    elif "/docx/" in url or "/docs/" in url:
        return "doc"
    elif "/sheets/" in url or "/spreadsheets/" in url:
        return "sheet"
    elif "/base/" in url:
        return "base"
    else:
        return "unknown"


def fetch_doc(page, url: str) -> str:
    """Feishu ドキュメントまたは Wiki のテキスト内容を取得"""
    page.goto(url, wait_until="domcontentloaded", timeout=30000)

    # エディターの読み込みを待機（Feishu ドキュメントのレンダリングは時間がかかる）
    selectors = [
        ".docs-reader-content",
        ".lark-editor-content",
        "[data-block-type]",
        ".doc-render-core",
        ".wiki-content",
        ".node-doc-content",
    ]

    loaded = False
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=15000)
            loaded = True
            break
        except Exception:
            continue

    if not loaded:
        # しばらく待ってから body テキストを直接抽出
        time.sleep(5)

    # 非同期コンテンツのレンダリングを追加で待機
    time.sleep(2)

    # 複数のセレクターで本文を抽出
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text()
                if len(text.strip()) > 50:
                    return text.strip()
        except Exception:
            continue

    # フォールバック：body 全体を抽出
    text = page.inner_text("body")
    return text.strip()


def fetch_sheet(page, url: str) -> str:
    """Feishu スプレッドシートを取得し、CSV フォーマットに変換"""
    page.goto(url, wait_until="domcontentloaded", timeout=30000)

    try:
        page.wait_for_selector(".spreadsheet-container, .sheet-container", timeout=15000)
    except Exception:
        time.sleep(5)

    time.sleep(3)

    # JS 経由でテーブルデータを抽出
    data = page.evaluate("""
        () => {
            const rows = [];
            // 尝试从 DOM 提取可见单元格
            const cells = document.querySelectorAll('[data-row][data-col]');
            if (cells.length === 0) return null;

            const grid = {};
            let maxRow = 0, maxCol = 0;
            cells.forEach(cell => {
                const r = parseInt(cell.getAttribute('data-row'));
                const c = parseInt(cell.getAttribute('data-col'));
                if (!grid[r]) grid[r] = {};
                grid[r][c] = cell.innerText.replace(/\\n/g, ' ').trim();
                maxRow = Math.max(maxRow, r);
                maxCol = Math.max(maxCol, c);
            });

            for (let r = 0; r <= maxRow; r++) {
                const row = [];
                for (let c = 0; c <= maxCol; c++) {
                    row.push(grid[r] && grid[r][c] ? grid[r][c] : '');
                }
                rows.push(row);
            }
            return rows;
        }
    """)

    if data:
        lines = []
        for row in data:
            lines.append(",".join(f'"{cell}"' for cell in row))
        return "\n".join(lines)

    # フォールバック：テキストを直接抽出
    return page.inner_text("body")


def fetch_messages(page, chat_name: str, target_name: str, limit: int = 500) -> str:
    """
    指定グループチャット内の対象人物のメッセージ履歴を取得。
    Feishu Web 版のメッセージページに先にナビゲートする必要があります。
    """
    # Feishu メッセージページを開く
    page.goto("https://applink.feishu.cn/client/chat/open", wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)

    # グループチャットを検索
    try:
        # 検索をクリック
        search_btn = page.query_selector('[data-test-id="search-btn"], .search-button, [placeholder*="搜索"]')
        if search_btn:
            search_btn.click()
            time.sleep(1)
            page.keyboard.type(chat_name)
            time.sleep(2)

            # 最初の結果を選択
            result = page.query_selector('.search-result-item:first-child, .im-search-item:first-child')
            if result:
                result.click()
                time.sleep(2)
    except Exception as e:
        print(f"⚠️  グループチャットの自動検索に失敗：{e}", file=sys.stderr)
        print(f"   「{chat_name}」グループチャットに手動でナビゲートし、Enter キーを押して続行してください...", file=sys.stderr)
        input()

    # 上にスクロールして履歴メッセージを読み込み
    print(f"メッセージ履歴を読み込み中...", file=sys.stderr)
    messages_container = page.query_selector('.message-list, .im-message-list, [data-testid="message-list"]')

    if messages_container:
        for _ in range(10):  # 10 回スクロール
            page.evaluate("el => el.scrollTop = 0", messages_container)
            time.sleep(1.5)
    else:
        for _ in range(10):
            page.keyboard.press("Control+Home")
            time.sleep(1.5)

    time.sleep(2)

    # メッセージを抽出
    messages = page.evaluate(f"""
        () => {{
            const target = "{target_name}";
            const results = [];

            // 常见的消息 DOM 结构
            const msgSelectors = [
                '.message-item',
                '.im-message-item',
                '[data-message-id]',
                '.msg-list-item',
            ];

            let items = [];
            for (const sel of msgSelectors) {{
                items = document.querySelectorAll(sel);
                if (items.length > 0) break;
            }}

            items.forEach(item => {{
                const senderEl = item.querySelector(
                    '.sender-name, .message-sender, [data-testid="sender-name"], .name'
                );
                const contentEl = item.querySelector(
                    '.message-content, .msg-content, [data-testid="message-content"], .text-content'
                );
                const timeEl = item.querySelector(
                    '.message-time, .msg-time, [data-testid="message-time"], .time'
                );

                const sender = senderEl ? senderEl.innerText.trim() : '';
                const content = contentEl ? contentEl.innerText.trim() : '';
                const time = timeEl ? timeEl.innerText.trim() : '';

                if (!content) return;
                if (target && !sender.includes(target)) return;

                results.push({{ sender, content, time }});
            }});

            return results.slice(-{limit});
        }}
    """)

    if not messages:
        print("⚠️  メッセージの自動抽出に失敗、ページテキストの抽出を試行中", file=sys.stderr)
        return page.inner_text("body")

    # ウェイト別に分類して出力
    long_msgs = [m for m in messages if len(m.get("content", "")) > 50]
    short_msgs = [m for m in messages if len(m.get("content", "")) <= 50]

    lines = [
        f"# Feishu メッセージ履歴（ブラウザスクレイピング）",
        f"グループチャット：{chat_name}",
        f"対象人物：{target_name}",
        f"合計 {len(messages)} 件のメッセージ",
        "",
        "---",
        "",
        "## 長文メッセージ（意見/判断系）",
        "",
    ]
    for m in long_msgs:
        lines.append(f"[{m.get('time', '')}] {m.get('content', '')}")
        lines.append("")

    lines += ["---", "", "## 日常メッセージ", ""]
    for m in short_msgs[:200]:
        lines.append(f"[{m.get('time', '')}] {m.get('content', '')}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Feishu ブラウザスクレイパー（Chrome ログインセッション再利用）")
    parser.add_argument("--url", help="Feishu ドキュメント/Wiki/スプレッドシートのリンク")
    parser.add_argument("--chat", help="グループチャット名（メッセージ履歴取得時に使用）")
    parser.add_argument("--target", help="対象人物の氏名（この人のメッセージのみ抽出）")
    parser.add_argument("--limit", type=int, default=500, help="最大メッセージ取得件数（デフォルト 500）")
    parser.add_argument("--output", default=None, help="出力ファイルパス（デフォルトは stdout に出力）")
    parser.add_argument("--chrome-profile", default=None, help="Chrome Profile パス（デフォルト自動検出）")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスモード（ブラウザウィンドウを表示しない）")
    parser.add_argument("--show-browser", action="store_true", help="ブラウザウィンドウを表示（デバッグ用）")

    args = parser.parse_args()

    if not args.url and not args.chat:
        parser.error("--url（ドキュメントリンク）または --chat（グループチャット名）を指定してください")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("エラー：先に Playwright をインストールしてください：pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    headless = args.headless and not args.show_browser

    print(f"ブラウザを起動中（{'ヘッドレス' if headless else 'GUI'}モード）...", file=sys.stderr)

    with sync_playwright() as p:
        ctx = make_context(p, args.chrome_profile, headless=headless)
        page = ctx.new_page()

        # ログイン済みか確認
        page.goto("https://www.feishu.cn", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        if "login" in page.url.lower() or "signin" in page.url.lower():
            print("⚠️  未ログイン状態が検出されました。", file=sys.stderr)
            print("   表示されたブラウザウィンドウで Feishu にログインし、完了後に Enter キーを押してください...", file=sys.stderr)
            if headless:
                print("   ヒント：--show-browser パラメータでブラウザウィンドウを表示してログインしてください", file=sys.stderr)
                sys.exit(1)
            input()

        # タスクタイプに応じて実行
        if args.url:
            page_type = detect_page_type(args.url)
            print(f"ページタイプ：{page_type}、スクレイピング開始...", file=sys.stderr)

            if page_type == "sheet":
                content = fetch_sheet(page, args.url)
            else:
                content = fetch_doc(page, args.url)

        elif args.chat:
            content = fetch_messages(
                page,
                chat_name=args.chat,
                target_name=args.target or "",
                limit=args.limit,
            )

        ctx.close()

    if not content or len(content.strip()) < 10:
        print("⚠️  有効なコンテンツを抽出できませんでした", file=sys.stderr)
        sys.exit(1)

    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"✅ {args.output} に保存しました（{len(content)} 文字）", file=sys.stderr)
    else:
        print(content)


if __name__ == "__main__":
    main()
