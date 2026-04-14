#!/usr/bin/env python3
"""
Feishu MCP クライアントラッパー（cso1z/Feishu-MCP 方式）

Feishu MCP Server 経由でドキュメント、wiki、メッセージ履歴を読み取る。
適用場面：会社で認可済みのドキュメント、App トークン権限のあるコンテンツ。

前提条件：
  1. Feishu MCP をインストール：npm install -g feishu-mcp
  2. App ID と App Secret を設定（Feishu 開放プラットフォームで企業自建アプリを作成）
  3. アプリに必要な権限を開通（以下の REQUIRED_PERMISSIONS を参照）

権限リスト（Feishu 開放プラットフォーム → 権限管理 → 開通）：
  - docs:doc:readonly          ドキュメントの読取
  - wiki:wiki:readonly         ナレッジベースの読取
  - im:message:readonly        メッセージの読取
  - bitable:app:readonly       マルチディメンションテーブルの読取
  - sheets:spreadsheet:readonly スプレッドシートの読取

使い方：
  # トークン設定（初回のみ）
  python3 feishu_mcp_client.py --setup

  # ドキュメントを読取
  python3 feishu_mcp_client.py --url "https://xxx.feishu.cn/wiki/xxx" --output out.txt

  # メッセージ履歴を読取
  python3 feishu_mcp_client.py --chat-id "oc_xxx" --target "田中太郎" --output out.txt

  # 特定スペース配下の全ドキュメントを一覧表示
  python3 feishu_mcp_client.py --list-wiki --space-id "xxx"
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Optional


CONFIG_PATH = Path.home() / ".colleague-skill" / "feishu_config.json"


# ─── 設定管理 ────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    print(f"設定を {CONFIG_PATH} に保存しました")


def setup_config() -> None:
    print("=== Feishu MCP 設定 ===")
    print("Feishu 開放プラットフォーム（open.feishu.cn）で企業自建アプリを作成し、以下の情報を取得してください：\n")

    app_id = input("App ID (cli_xxx): ").strip()
    app_secret = input("App Secret: ").strip()

    print("\n設定方式を選択：")
    print("  [1] App Token（アプリ権限。Feishu 管理画面で対応する権限を開通する必要があります）")
    print("  [2] User Token（個人権限。自分が権限を持つ全コンテンツにアクセス可能。定期的な更新が必要）")
    mode = input("選択 [1/2]、デフォルト 1：").strip() or "1"

    config = {
        "app_id": app_id,
        "app_secret": app_secret,
        "mode": "app" if mode == "1" else "user",
    }

    if mode == "2":
        print("\nUser Token の取得方法：Feishu 開放プラットフォーム → OAuth 2.0 → user_access_token を取得")
        user_token = input("User Access Token (u-xxx)：").strip()
        config["user_token"] = user_token
        print("注意：User Token の有効期限は約 2 時間です。期限切れ後は再設定が必要です")

    save_config(config)
    print("\n✅ 設定完了！")


# ─── MCP 呼び出しラッパー ────────────────────────────────────────────────────

def call_mcp(tool: str, params: dict, config: dict) -> dict:
    """
    npx 経由で feishu-mcp ツールを呼び出す。
    feishu-mcp は stdio モードに対応し、JSON で直接通信する。
    """
    env = os.environ.copy()
    env["FEISHU_APP_ID"] = config.get("app_id", "")
    env["FEISHU_APP_SECRET"] = config.get("app_secret", "")

    if config.get("mode") == "user" and config.get("user_token"):
        env["FEISHU_USER_ACCESS_TOKEN"] = config["user_token"]

    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": params,
        },
        "id": 1,
    })

    try:
        result = subprocess.run(
            ["npx", "-y", "feishu-mcp", "--stdio"],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"MCP 呼び出しに失敗：{result.stderr}")
        return json.loads(result.stdout)
    except FileNotFoundError:
        print("エラー：npx が見つかりません。先に Node.js をインストールしてください", file=sys.stderr)
        print("Feishu MCP のインストール：npm install -g feishu-mcp", file=sys.stderr)
        sys.exit(1)


def extract_doc_token(url: str) -> tuple[str, str]:
    """Feishu URL からドキュメントトークンとタイプを抽出"""
    import re
    patterns = [
        (r"/wiki/([A-Za-z0-9]+)", "wiki"),
        (r"/docx/([A-Za-z0-9]+)", "docx"),
        (r"/docs/([A-Za-z0-9]+)", "doc"),
        (r"/sheets/([A-Za-z0-9]+)", "sheet"),
        (r"/base/([A-Za-z0-9]+)", "base"),
    ]
    for pattern, doc_type in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1), doc_type
    raise ValueError(f"URL からドキュメントトークンを解析できません：{url}")


# ─── 機能関数 ─────────────────────────────────────────────────────────────────

def fetch_doc_via_mcp(url: str, config: dict) -> str:
    """MCP 経由で Feishu ドキュメントまたは Wiki を読取"""
    token, doc_type = extract_doc_token(url)

    if doc_type == "wiki":
        result = call_mcp("get_wiki_node", {"token": token}, config)
    elif doc_type in ("docx", "doc"):
        result = call_mcp("get_doc_content", {"doc_token": token}, config)
    elif doc_type == "sheet":
        result = call_mcp("get_spreadsheet_content", {"spreadsheet_token": token}, config)
    else:
        raise ValueError(f"サポートされていないドキュメントタイプ：{doc_type}")

    # MCP から返された内容を抽出
    if "result" in result:
        content = result["result"]
        if isinstance(content, list):
            # MCP tool result フォーマット
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text", "")
        elif isinstance(content, str):
            return content
    elif "error" in result:
        raise RuntimeError(f"MCP がエラーを返しました：{result['error']}")

    return json.dumps(result, ensure_ascii=False, indent=2)


def fetch_messages_via_mcp(
    chat_id: str,
    target_name: str,
    limit: int,
    config: dict,
) -> str:
    """MCP 経由でグループチャットのメッセージ履歴を読取"""
    result = call_mcp(
        "get_chat_messages",
        {
            "chat_id": chat_id,
            "page_size": min(limit, 50),  # Feishu API は 1 回最大 50 件
        },
        config,
    )

    messages = []
    raw = result.get("result", [])
    if isinstance(raw, list):
        messages = raw
    elif isinstance(raw, str):
        try:
            messages = json.loads(raw)
        except Exception:
            return raw

    # 対象人物でフィルター
    if target_name:
        messages = [
            m for m in messages
            if target_name in str(m.get("sender", {}).get("name", ""))
        ]

    # 分類して出力
    long_msgs = [m for m in messages if len(str(m.get("content", ""))) > 50]
    short_msgs = [m for m in messages if len(str(m.get("content", ""))) <= 50]

    lines = [
        "# Feishu メッセージ履歴（MCP 方式）",
        f"グループチャット ID：{chat_id}",
        f"対象人物：{target_name or '全員'}",
        f"合計 {len(messages)} 件",
        "",
        "---",
        "",
        "## 長文メッセージ",
        "",
    ]
    for m in long_msgs:
        sender = m.get("sender", {}).get("name", "")
        content = m.get("content", "")
        ts = m.get("create_time", "")
        lines.append(f"[{ts}] {sender}：{content}")
        lines.append("")

    lines += ["---", "", "## 日常メッセージ", ""]
    for m in short_msgs[:200]:
        sender = m.get("sender", {}).get("name", "")
        content = m.get("content", "")
        lines.append(f"{sender}：{content}")

    return "\n".join(lines)


def list_wiki_docs(space_id: str, config: dict) -> str:
    """ナレッジベーススペース配下の全ドキュメントを一覧表示"""
    result = call_mcp("list_wiki_nodes", {"space_id": space_id}, config)
    raw = result.get("result", "")
    if isinstance(raw, str):
        return raw
    return json.dumps(raw, ensure_ascii=False, indent=2)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Feishu MCP クライアント")
    parser.add_argument("--setup", action="store_true", help="設定を初期化（App ID / Secret）")
    parser.add_argument("--url", help="Feishu ドキュメント/Wiki/スプレッドシートのリンク")
    parser.add_argument("--chat-id", help="グループチャット ID（oc_xxx フォーマット）")
    parser.add_argument("--target", help="対象人物の氏名")
    parser.add_argument("--limit", type=int, default=500, help="最大メッセージ取得件数")
    parser.add_argument("--list-wiki", action="store_true", help="ナレッジベースのドキュメントを一覧表示")
    parser.add_argument("--space-id", help="ナレッジベース Space ID")
    parser.add_argument("--output", default=None, help="出力ファイルパス")

    args = parser.parse_args()

    if args.setup:
        setup_config()
        return

    config = load_config()
    if not config:
        print("エラー：未設定です。先に実行してください：python3 feishu_mcp_client.py --setup", file=sys.stderr)
        sys.exit(1)

    content = ""

    if args.url:
        print(f"MCP 経由で読取中：{args.url}", file=sys.stderr)
        content = fetch_doc_via_mcp(args.url, config)

    elif args.chat_id:
        print(f"MCP 経由でメッセージを読取中：{args.chat_id}", file=sys.stderr)
        content = fetch_messages_via_mcp(
            args.chat_id,
            args.target or "",
            args.limit,
            config,
        )

    elif args.list_wiki:
        if not args.space_id:
            print("エラー：--list-wiki には --space-id が必要です", file=sys.stderr)
            sys.exit(1)
        content = list_wiki_docs(args.space_id, config)

    else:
        parser.print_help()
        return

    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"✅ {args.output} に保存しました", file=sys.stderr)
    else:
        print(content)


if __name__ == "__main__":
    main()
