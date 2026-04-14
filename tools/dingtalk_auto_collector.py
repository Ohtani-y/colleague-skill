#!/usr/bin/env python3
"""
DingTalk 自動収集ツール

同僚の氏名を入力すると、自動で以下を実行：
  1. DingTalk ユーザーを検索し、userId を取得
  2. 作成/編集したドキュメントやナレッジベースの内容を検索
  3. マルチディメンションテーブル（あれば）を取得
  4. メッセージ履歴（API が履歴取得に対応しないため、自動でブラウザ方式に切替）
  5. 統一フォーマットで出力し、create-colleague の分析フローへ直接投入

DingTalk 制限事項：
  DingTalk Open API は履歴メッセージ取得インターフェースを提供していないため、
  メッセージ履歴の収集には Playwright ブラウザ方式を自動的に使用します。

前提条件：
  pip3 install requests playwright
  playwright install chromium
  python3 dingtalk_auto_collector.py --setup

使い方：
  python3 dingtalk_auto_collector.py --name "田中太郎" --output-dir ./knowledge/tanaka
  python3 dingtalk_auto_collector.py --name "田中太郎" --skip-messages   # メッセージ収集をスキップ
  python3 dingtalk_auto_collector.py --name "田中太郎" --doc-limit 20
"""

from __future__ import annotations

import json
import sys
import time
import argparse
import platform
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
except ImportError:
    print("エラー：先に依存パッケージをインストールしてください：pip3 install requests", file=sys.stderr)
    sys.exit(1)


CONFIG_PATH = Path.home() / ".colleague-skill" / "dingtalk_config.json"
API_BASE = "https://api.dingtalk.com"


# ─── 設定 ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("設定が見つかりません。先に実行してください：python3 dingtalk_auto_collector.py --setup", file=sys.stderr)
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))


def setup_config() -> None:
    print("=== DingTalk 自動収集設定 ===\n")
    print("https://open-dev.dingtalk.com で企業内部アプリを作成し、以下の権限を開通してください：\n")
    print("  連絡先系：")
    print("    qyapi_get_member_detail     ユーザー詳細の照会")
    print("    Contact.User.mobile         ユーザー電話番号の読取（任意）")
    print()
    print("  メッセージ系（任意、メッセージ送信のみ。履歴メッセージはブラウザ方式が必要）：")
    print("    qyapi_robot_sendmsg         ロボットメッセージ送信")
    print()
    print("  ドキュメント系：")
    print("    Doc.WorkSpace.READ          ワークスペースの読取")
    print("    Doc.File.READ               ファイルの読取")
    print()
    print("  マルチディメンションテーブル：")
    print("    Bitable.Record.READ         レコードの読取")
    print()

    app_key = input("AppKey (ding_xxx): ").strip()
    app_secret = input("AppSecret: ").strip()

    config = {"app_key": app_key, "app_secret": app_secret}
    save_config(config)
    print(f"\n✅ 設定を {CONFIG_PATH} に保存しました")
    print("\n注意：メッセージ履歴の収集には Playwright が必要です。インストール済みであることを確認してください：")
    print("  pip3 install playwright && playwright install chromium")


# ─── Token ───────────────────────────────────────────────────────────────────

_token_cache: dict = {}


def get_access_token(config: dict) -> str:
    """DingTalk access_token を取得（キャッシュ付き）"""
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expire", 0) > now + 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{API_BASE}/v1.0/oauth2/accessToken",
        json={"appKey": config["app_key"], "appSecret": config["app_secret"]},
        timeout=10,
    )
    data = resp.json()

    if "accessToken" not in data:
        print(f"トークン取得に失敗：{data}", file=sys.stderr)
        sys.exit(1)

    token = data["accessToken"]
    _token_cache["token"] = token
    _token_cache["expire"] = now + data.get("expireIn", 7200)
    return token


def api_get(path: str, params: dict, config: dict) -> dict:
    token = get_access_token(config)
    resp = requests.get(
        f"{API_BASE}{path}",
        params=params,
        headers={"x-acs-dingtalk-access-token": token},
        timeout=15,
    )
    return resp.json()


def api_post(path: str, body: dict, config: dict) -> dict:
    token = get_access_token(config)
    resp = requests.post(
        f"{API_BASE}{path}",
        json=body,
        headers={"x-acs-dingtalk-access-token": token},
        timeout=15,
    )
    return resp.json()


# ─── ユーザー検索 ─────────────────────────────────────────────────────────────

def find_user(name: str, config: dict) -> Optional[dict]:
    """氏名で DingTalk ユーザーを検索"""
    print(f"  ユーザー検索：{name} ...", file=sys.stderr)

    data = api_post(
        "/v1.0/contact/users/search",
        {"searchText": name, "offset": 0, "size": 10},
        config,
    )

    users = data.get("list", []) or data.get("result", {}).get("list", [])

    if not users:
        # フォールバック：部門を巡回して検索
        print("  API 検索で結果なし、連絡先を巡回して検索中 ...", file=sys.stderr)
        users = search_users_by_dept(name, config)

    if not users:
        print(f"  ユーザーが見つかりません：{name}", file=sys.stderr)
        return None

    if len(users) == 1:
        u = users[0]
        print(f"  ユーザー発見：{u.get('name')}（{u.get('deptNameList', [''])[0] if isinstance(u.get('deptNameList'), list) else ''}）", file=sys.stderr)
        return u

    print(f"\n  {len(users)} 件の結果が見つかりました。選択してください：")
    for i, u in enumerate(users):
        dept = u.get("deptNameList", [""])
        dept_str = dept[0] if isinstance(dept, list) and dept else ""
        print(f"    [{i+1}] {u.get('name')}  {dept_str}  {u.get('unionId', '')}")

    choice = input("\n  番号を選択（デフォルト 1）：").strip() or "1"
    try:
        return users[int(choice) - 1]
    except (ValueError, IndexError):
        return users[0]


def search_users_by_dept(name: str, config: dict, dept_id: int = 1, depth: int = 0) -> list:
    """部門を再帰的に巡回してユーザーを検索（深さ制限 3 階層）"""
    if depth > 3:
        return []

    results = []

    # 部門ユーザーリストを取得
    data = api_post(
        "/v1.0/contact/users/simplelist",
        {"deptId": dept_id, "cursor": 0, "size": 100},
        config,
    )
    users = data.get("list", [])
    for u in users:
        if name in u.get("name", ""):
            # 詳細情報を取得
            detail = api_get(f"/v1.0/contact/users/{u.get('userId')}", {}, config)
            results.append(detail.get("result", u))

    # 子部門を取得
    sub_data = api_get(
        "/v1.0/contact/departments/listSubDepts",
        {"deptId": dept_id},
        config,
    )
    for sub in sub_data.get("result", []):
        results.extend(search_users_by_dept(name, config, sub.get("deptId"), depth + 1))

    return results


# ─── ドキュメント収集 ─────────────────────────────────────────────────────────

def list_workspaces(config: dict) -> list:
    """全ワークスペースを取得"""
    data = api_get("/v1.0/doc/workspaces", {"maxResults": 50}, config)
    return data.get("workspaceModels", []) or data.get("result", {}).get("workspaceModels", [])


def search_docs_by_user(user_id: str, name: str, doc_limit: int, config: dict) -> list:
    """ユーザーが作成したドキュメントを検索"""
    print(f"  {name} のドキュメントを検索中 ...", file=sys.stderr)

    # 方法1：グローバル検索
    data = api_post(
        "/v1.0/doc/search",
        {
            "keyword": name,
            "size": doc_limit,
            "offset": 0,
        },
        config,
    )

    docs = []
    items = data.get("docList", []) or data.get("result", {}).get("docList", [])

    for item in items:
        creator_id = item.get("creatorId", "") or item.get("creator", {}).get("userId", "")
        # フィルター：対象ユーザーが作成したもののみ保持
        if user_id and creator_id and creator_id != user_id:
            continue
        docs.append({
            "title": item.get("title", "無題"),
            "docId": item.get("docId", ""),
            "spaceId": item.get("spaceId", ""),
            "type": item.get("docType", ""),
            "url": item.get("shareUrl", ""),
            "creator": item.get("creatorName", name),
        })

    if not docs:
        # 方法2：ワークスペースを巡回してドキュメントを探す
        print("  検索結果なし、ワークスペースを巡回中 ...", file=sys.stderr)
        workspaces = list_workspaces(config)
        for ws in workspaces[:5]:  # 最大 5 スペースを検索
            ws_id = ws.get("spaceId") or ws.get("workspaceId")
            if not ws_id:
                continue
            files_data = api_get(
                f"/v1.0/doc/workspaces/{ws_id}/files",
                {"maxResults": 20, "orderBy": "modified_time", "order": "DESC"},
                config,
            )
            for f in files_data.get("files", []):
                creator_id = f.get("creatorId", "")
                if user_id and creator_id and creator_id != user_id:
                    continue
                docs.append({
                    "title": f.get("fileName", "無題"),
                    "docId": f.get("docId", ""),
                    "spaceId": ws_id,
                    "type": f.get("docType", ""),
                    "url": f.get("shareUrl", ""),
                    "creator": name,
                })

    print(f"  {len(docs)} 件のドキュメントが見つかりました", file=sys.stderr)
    return docs[:doc_limit]


def fetch_doc_content(doc_id: str, space_id: str, config: dict) -> str:
    """単一ドキュメントのテキスト内容を取得"""
    # 方法1：ドキュメント内容を直接取得
    data = api_get(
        f"/v1.0/doc/workspaces/{space_id}/files/{doc_id}/content",
        {},
        config,
    )

    content = (
        data.get("content")
        or data.get("result", {}).get("content")
        or data.get("markdown")
        or data.get("result", {}).get("markdown")
        or ""
    )

    if content:
        return content

    # 方法2：ダウンロードリンクを取得してダウンロード
    dl_data = api_get(
        f"/v1.0/doc/workspaces/{space_id}/files/{doc_id}/download",
        {},
        config,
    )
    dl_url = dl_data.get("downloadUrl") or dl_data.get("result", {}).get("downloadUrl")
    if dl_url:
        try:
            resp = requests.get(dl_url, timeout=15)
            return resp.text
        except Exception:
            pass

    return ""


def collect_docs(user: dict, doc_limit: int, config: dict) -> str:
    """対象ユーザーのドキュメントを収集"""
    user_id = user.get("userId", "")
    name = user.get("name", "")

    docs = search_docs_by_user(user_id, name, doc_limit, config)
    if not docs:
        return f"# ドキュメント内容\n\n{name} に関連するドキュメントが見つかりませんでした\n"

    lines = [
        "# ドキュメント内容（DingTalk 自動収集）",
        f"対象：{name}",
        f"合計 {len(docs)} 件",
        "",
    ]

    for doc in docs:
        title = doc.get("title", "無題")
        doc_id = doc.get("docId", "")
        space_id = doc.get("spaceId", "")
        url = doc.get("url", "")

        if not doc_id or not space_id:
            continue

        print(f"  ドキュメント取得中：{title} ...", file=sys.stderr)
        content = fetch_doc_content(doc_id, space_id, config)

        if not content or len(content.strip()) < 20:
            print(f"    内容が空のため、スキップします", file=sys.stderr)
            continue

        lines += [
            "---",
            f"## 《{title}》",
            f"リンク：{url}",
            f"作成者：{doc.get('creator', '')}",
            "",
            content.strip(),
            "",
        ]

    return "\n".join(lines)


# ─── マルチディメンションテーブル ─────────────────────────────────────────────

def search_bitables(user_id: str, name: str, config: dict) -> list:
    """対象ユーザーのマルチディメンションテーブルを検索"""
    print(f"  {name} のマルチディメンションテーブルを検索中 ...", file=sys.stderr)

    data = api_post(
        "/v1.0/doc/search",
        {"keyword": name, "size": 20, "offset": 0, "docTypes": ["bitable"]},
        config,
    )

    tables = []
    for item in data.get("docList", []):
        if item.get("docType") != "bitable":
            continue
        creator_id = item.get("creatorId", "")
        if user_id and creator_id and creator_id != user_id:
            continue
        tables.append(item)

    print(f"  {len(tables)} 件のマルチディメンションテーブルが見つかりました", file=sys.stderr)
    return tables


def fetch_bitable_content(base_id: str, config: dict) -> str:
    """マルチディメンションテーブルの内容を取得"""
    # 全シートを取得
    sheets_data = api_get(
        f"/v1.0/bitable/bases/{base_id}/sheets",
        {},
        config,
    )
    sheets = sheets_data.get("sheets", []) or sheets_data.get("result", {}).get("sheets", [])

    if not sheets:
        return "（マルチディメンションテーブルが空か権限がありません）\n"

    lines = []
    for sheet in sheets:
        sheet_id = sheet.get("sheetId") or sheet.get("id")
        sheet_name = sheet.get("name", sheet_id)

        # フィールドを取得
        fields_data = api_get(
            f"/v1.0/bitable/bases/{base_id}/sheets/{sheet_id}/fields",
            {"maxResults": 100},
            config,
        )
        fields = [f.get("name", "") for f in fields_data.get("fields", [])]

        # レコードを取得
        records_data = api_get(
            f"/v1.0/bitable/bases/{base_id}/sheets/{sheet_id}/records",
            {"maxResults": 200},
            config,
        )
        records = records_data.get("records", []) or records_data.get("result", {}).get("records", [])

        lines.append(f"### テーブル：{sheet_name}")
        lines.append("")

        if fields:
            lines.append("| " + " | ".join(fields) + " |")
            lines.append("| " + " | ".join(["---"] * len(fields)) + " |")

        for rec in records:
            row_data = rec.get("fields", {})
            row = []
            for f in fields:
                val = row_data.get(f, "")
                if isinstance(val, list):
                    val = " ".join(
                        v.get("text", str(v)) if isinstance(v, dict) else str(v)
                        for v in val
                    )
                row.append(str(val).replace("|", "｜").replace("\n", " "))
            lines.append("| " + " | ".join(row) + " |")

        lines.append("")

    return "\n".join(lines)


def collect_bitables(user: dict, config: dict) -> str:
    """対象ユーザーのマルチディメンションテーブルを収集"""
    user_id = user.get("userId", "")
    name = user.get("name", "")

    tables = search_bitables(user_id, name, config)
    if not tables:
        return f"# マルチディメンションテーブル\n\n{name} のマルチディメンションテーブルが見つかりませんでした\n"

    lines = [
        "# マルチディメンションテーブル（DingTalk 自動収集）",
        f"対象：{name}",
        f"合計 {len(tables)} 件",
        "",
    ]

    for t in tables:
        title = t.get("title", "無題")
        doc_id = t.get("docId", "")
        print(f"  マルチディメンションテーブル取得中：{title} ...", file=sys.stderr)

        content = fetch_bitable_content(doc_id, config)
        lines += [
            "---",
            f"## 《{title}》",
            "",
            content,
        ]

    return "\n".join(lines)


# ─── メッセージ履歴（ブラウザ方式）────────────────────────────────────────────

def get_default_chrome_profile() -> str:
    system = platform.system()
    if system == "Darwin":
        return str(Path.home() / "Library/Application Support/Google/Chrome/Default")
    elif system == "Linux":
        return str(Path.home() / ".config/google-chrome/Default")
    elif system == "Windows":
        import os
        return str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default")
    return str(Path.home() / ".config/google-chrome/Default")


def collect_messages_browser(
    name: str,
    msg_limit: int,
    chrome_profile: Optional[str],
    headless: bool,
) -> str:
    """Playwright ブラウザで DingTalk Web 版のメッセージ履歴を取得"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return (
            "# メッセージ履歴\n\n"
            "⚠️  Playwright がインストールされていないため、メッセージ履歴を収集できません。\n"
            "以下を実行してください：pip3 install playwright && playwright install chromium\n"
        )

    import re

    profile = chrome_profile or get_default_chrome_profile()
    print(f"  ブラウザを起動して DingTalk メッセージを取得中（{'ヘッドレス' if headless else 'GUI'}）...", file=sys.stderr)

    messages = []

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile,
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
                viewport={"width": 1280, "height": 900},
            )
        except Exception as e:
            return f"# メッセージ履歴\n\n⚠️  ブラウザの起動に失敗しました：{e}\n"

        page = ctx.new_page()

        # DingTalk Web 版を開く
        page.goto("https://im.dingtalk.com", wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)

        # ログイン状態を確認
        if "login" in page.url.lower() or page.query_selector(".login-wrap"):
            if headless:
                ctx.close()
                return (
                    "# メッセージ履歴\n\n"
                    "⚠️  未ログイン状態が検出されました。--show-browser パラメータで再実行し、表示されるウィンドウで DingTalk にログインしてください。\n"
                )
            print("  ブラウザで DingTalk にログインし、完了後に Enter キーを押してください...", file=sys.stderr)
            input()

        # 対象連絡先のメッセージを検索
        try:
            # 検索ボックスをクリック
            search_selectors = [
                '[placeholder*="搜索"]',
                '.search-input',
                '[data-testid="search"]',
                '.im-search',
            ]
            for sel in search_selectors:
                el = page.query_selector(sel)
                if el:
                    el.click()
                    time.sleep(0.5)
                    page.keyboard.type(name)
                    time.sleep(2)
                    break

            # 最初の結果をクリック
            result_selectors = [
                '.search-result-item',
                '.contact-item',
                '.result-item',
            ]
            for sel in result_selectors:
                result = page.query_selector(sel)
                if result:
                    result.click()
                    time.sleep(2)
                    break
        except Exception as e:
            print(f"  自動ナビゲーションに失敗：{e}", file=sys.stderr)
            if not headless:
                print(f"  「{name}」との会話を手動で開き、Enter キーを押して続行してください...", file=sys.stderr)
                input()

        # 上にスクロールして履歴メッセージを読み込み
        print("  履歴メッセージを読み込み中 ...", file=sys.stderr)
        for _ in range(15):
            page.keyboard.press("Control+Home")
            time.sleep(1)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(0.8)

        time.sleep(2)

        # メッセージを抽出
        raw_messages = page.evaluate(f"""
            () => {{
                const target = "{name}";
                const results = [];
                const selectors = [
                    '.message-item-content-container',
                    '.im-message-item',
                    '[data-message-id]',
                    '.msg-wrap',
                ];

                let items = [];
                for (const sel of selectors) {{
                    items = document.querySelectorAll(sel);
                    if (items.length > 0) break;
                }}

                items.forEach(item => {{
                    const senderEl = item.querySelector('.sender-name, .nick-name, .name');
                    const contentEl = item.querySelector(
                        '.message-text, .text-content, .msg-content, .im-richtext'
                    );
                    const timeEl = item.querySelector('.message-time, .time, .msg-time');

                    const sender = senderEl ? senderEl.innerText.trim() : '';
                    const content = contentEl ? contentEl.innerText.trim() : '';
                    const time = timeEl ? timeEl.innerText.trim() : '';

                    if (!content) return;
                    if (target && !sender.includes(target)) return;
                    if (['[图片]','[文件]','[表情]','[语音]'].includes(content)) return;

                    results.push({{ sender, content, time }});
                }});

                return results.slice(-{msg_limit});
            }}
        """)

        ctx.close()
        messages = raw_messages or []

    if not messages:
        return (
            "# メッセージ履歴\n\n"
            f"⚠️  {name} のメッセージを自動抽出できませんでした。\n"
            "原因として、DingTalk Web 版の DOM 構造の変更、または会話が見つからなかった可能性があります。\n"
            "チャット履歴を手動でスクリーンショットしてアップロードすることを推奨します。\n"
        )

    long_msgs = [m for m in messages if len(m.get("content", "")) > 50]
    short_msgs = [m for m in messages if len(m.get("content", "")) <= 50]

    lines = [
        "# メッセージ履歴（DingTalk ブラウザ収集）",
        f"対象：{name}",
        f"合計 {len(messages)} 件",
        "注意：DingTalk API は履歴メッセージ取得に対応していないため、本内容はブラウザ経由で収集されました",
        "",
        "---",
        "",
        "## 長文メッセージ（意見/判断/技術系）",
        "",
    ]
    for m in long_msgs:
        lines.append(f"[{m.get('time', '')}] {m.get('content', '')}")
        lines.append("")

    lines += ["---", "", "## 日常メッセージ（スタイル参考）", ""]
    for m in short_msgs[:300]:
        lines.append(f"[{m.get('time', '')}] {m.get('content', '')}")

    return "\n".join(lines)


# ─── メインフロー ─────────────────────────────────────────────────────────────

def collect_all(
    name: str,
    output_dir: Path,
    msg_limit: int,
    doc_limit: int,
    skip_messages: bool,
    chrome_profile: Optional[str],
    headless: bool,
    config: dict,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    print(f"\n🔍 収集開始（DingTalk）：{name}\n", file=sys.stderr)

    # Step 1: ユーザーを検索
    user = find_user(name, config)
    if not user:
        print(f"❌ ユーザーが見つかりません：{name}", file=sys.stderr)
        sys.exit(1)

    print(f"  ユーザー ID：{user.get('userId', '')}  部門：{user.get('deptNameList', [''])[0] if isinstance(user.get('deptNameList'), list) and user.get('deptNameList') else ''}", file=sys.stderr)

    # Step 2: ドキュメント
    print(f"\n📄 ドキュメント収集中（上限 {doc_limit} 件）...", file=sys.stderr)
    try:
        doc_content = collect_docs(user, doc_limit, config)
        doc_path = output_dir / "docs.txt"
        doc_path.write_text(doc_content, encoding="utf-8")
        results["docs"] = str(doc_path)
        print(f"  ✅ ドキュメント → {doc_path}", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  ドキュメント収集に失敗：{e}", file=sys.stderr)

    # Step 3: マルチディメンションテーブル
    print(f"\n📊 マルチディメンションテーブル収集中 ...", file=sys.stderr)
    try:
        bitable_content = collect_bitables(user, config)
        bt_path = output_dir / "bitables.txt"
        bt_path.write_text(bitable_content, encoding="utf-8")
        results["bitables"] = str(bt_path)
        print(f"  ✅ マルチディメンションテーブル → {bt_path}", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  マルチディメンションテーブルの収集に失敗：{e}", file=sys.stderr)

    # Step 4: メッセージ履歴（ブラウザ方式）
    if not skip_messages:
        print(f"\n📨 メッセージ履歴を収集中（ブラウザ方式、上限 {msg_limit} 件）...", file=sys.stderr)
        print(f"  ℹ️  DingTalk API は履歴メッセージ取得に対応していないため、自動でブラウザ方式に切り替えます", file=sys.stderr)
        try:
            msg_content = collect_messages_browser(name, msg_limit, chrome_profile, headless)
            msg_path = output_dir / "messages.txt"
            msg_path.write_text(msg_content, encoding="utf-8")
            results["messages"] = str(msg_path)
            print(f"  ✅ メッセージ履歴 → {msg_path}", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  メッセージ収集に失敗：{e}", file=sys.stderr)
    else:
        print(f"\n📨 メッセージ収集をスキップ（--skip-messages）", file=sys.stderr)

    # サマリーを書き込み
    summary = {
        "name": name,
        "user_id": user.get("userId", ""),
        "platform": "dingtalk",
        "department": user.get("deptNameList", []),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "files": results,
        "notes": "メッセージ履歴はブラウザ経由で収集。DingTalk API は履歴メッセージ取得に非対応",
    }
    (output_dir / "collection_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )

    print(f"\n✅ 収集完了 → {output_dir}", file=sys.stderr)
    print(f"   ファイル：{', '.join(results.keys())}", file=sys.stderr)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="DingTalk データ自動収集ツール")
    parser.add_argument("--setup", action="store_true", help="設定を初期化")
    parser.add_argument("--name", help="同僚の氏名")
    parser.add_argument("--output-dir", default=None, help="出力ディレクトリ")
    parser.add_argument("--msg-limit", type=int, default=500, help="最大メッセージ収集件数（デフォルト 500）")
    parser.add_argument("--doc-limit", type=int, default=20, help="最大ドキュメント収集件数（デフォルト 20）")
    parser.add_argument("--skip-messages", action="store_true", help="メッセージ履歴の収集をスキップ")
    parser.add_argument("--chrome-profile", default=None, help="Chrome Profile パス")
    parser.add_argument("--show-browser", action="store_true", help="ブラウザウィンドウを表示（デバッグ/初回ログイン）")

    args = parser.parse_args()

    if args.setup:
        setup_config()
        return

    if not args.name:
        parser.error("--name を指定してください")

    config = load_config()
    output_dir = Path(args.output_dir) if args.output_dir else Path(f"./knowledge/{args.name}")

    collect_all(
        name=args.name,
        output_dir=output_dir,
        msg_limit=args.msg_limit,
        doc_limit=args.doc_limit,
        skip_messages=args.skip_messages,
        chrome_profile=args.chrome_profile,
        headless=not args.show_browser,
        config=config,
    )


if __name__ == "__main__":
    main()
