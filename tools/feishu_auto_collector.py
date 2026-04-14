#!/usr/bin/env python3
"""
Feishu 自動収集ツール

同僚の氏名を入力すると、自動で以下を実行：
  1. Feishu ユーザーを検索し、user_id を取得
  2. 共通のグループチャットを見つけ、対象者のメッセージ履歴を取得
  3. DM メッセージを取得（user_access_token が必要）
  4. 作成/編集したドキュメントや Wiki を検索
  5. ドキュメント内容を取得
  6. マルチディメンションテーブル（あれば）を取得
  7. 統一フォーマットで出力し、create-colleague の分析フローへ直接投入

前提条件：
  python3 feishu_auto_collector.py --setup   # App ID / Secret を設定（初回のみ）

DM 収集（追加手順が必要）：
  1. Feishu アプリでユーザー権限を開通：im:message, im:chat
  2. OAuth 認可コードを取得：
     ブラウザで開く: https://open.feishu.cn/open-apis/authen/v1/authorize?app_id={APP_ID}&redirect_uri=http://www.example.com&scope=im:message%20im:chat
     認可後にアドレスバーから code をコピー
  3. トークンに交換：
     python3 feishu_auto_collector.py --exchange-code {CODE}
  4. 収集時に DM の chat_id を指定：
     python3 feishu_auto_collector.py --name "田中太郎" --p2p-chat-id oc_xxx

使い方：
  # グループチャット収集（従来の方法）
  python3 feishu_auto_collector.py --name "田中太郎" --output-dir ./knowledge/tanaka
  python3 feishu_auto_collector.py --name "田中太郎" --msg-limit 1000 --doc-limit 20

  # DM 収集
  python3 feishu_auto_collector.py --name "田中太郎" --p2p-chat-id oc_xxx

  # open_id + DM を直接指定（ユーザー検索をスキップ）
  python3 feishu_auto_collector.py --open-id ou_xxx --p2p-chat-id oc_xxx --name "田中太郎"

  # user_access_token への交換
  python3 feishu_auto_collector.py --exchange-code {CODE}
"""

from __future__ import annotations

import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
except ImportError:
    print("エラー：先に requests をインストールしてください：pip3 install requests", file=sys.stderr)
    sys.exit(1)


CONFIG_PATH = Path.home() / ".colleague-skill" / "feishu_config.json"
BASE_URL = "https://open.feishu.cn/open-apis"


# ─── 設定 ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("設定が見つかりません。先に実行してください：python3 feishu_auto_collector.py --setup", file=sys.stderr)
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))


def setup_config() -> None:
    print("=== Feishu 自動収集設定 ===\n")
    print("https://open.feishu.cn で企業自建アプリを作成し、以下の権限を開通してください：")
    print()
    print("  メッセージ系（アプリ権限、グループチャット収集用）：")
    print("    im:message:readonly          メッセージの読取")
    print("    im:chat:readonly             グループチャット情報の読取")
    print("    im:chat.members:readonly     グループメンバーの読取")
    print()
    print("  メッセージ系（ユーザー権限、DM 収集用）：")
    print("    im:message                   ユーザーとしてメッセージを読取/送信")
    print("    im:chat                      ユーザーとして会話リストを読取")
    print()
    print("  ユーザー系：")
    print("    contact:user.base:readonly       ユーザー基本情報の読取")
    print("    contact:department.base:readonly  部門を巡回してユーザーを検索（氏名検索に必須）")
    print()
    print("  ドキュメント系：")
    print("    docs:doc:readonly            ドキュメントの読取")
    print("    wiki:wiki:readonly           ナレッジベースの読取")
    print("    drive:drive:readonly         クラウドドライブファイルの検索")
    print()
    print("  マルチディメンションテーブル：")
    print("    bitable:app:readonly         マルチディメンションテーブルの読取")
    print()
    print("  ─── DM 収集について ───")
    print("  DM メッセージは user_access_token 経由で取得する必要があります（アプリ権限では DM にアクセスできません）。")
    print("  取得方法：OAuth 認可。認可リンクのフォーマット：")
    print("    https://open.feishu.cn/open-apis/authen/v1/authorize?app_id={APP_ID}&redirect_uri={REDIRECT}&scope=im:message%20im:chat")
    print("  認可後にコールバック URL から code を取得し、--exchange-code でトークンに交換してください。")
    print()

    app_id = input("App ID (cli_xxx): ").strip()
    app_secret = input("App Secret: ").strip()

    config = {"app_id": app_id, "app_secret": app_secret}

    print("\nuser_access_token を設定しますか？（DM メッセージ収集用、スキップ可能）")
    user_token = input("user_access_token (空欄でスキップ): ").strip()
    if user_token:
        config["user_access_token"] = user_token
    p2p_chat_id = input("DM chat_id (空欄でスキップ): ").strip()
    if p2p_chat_id:
        config["p2p_chat_id"] = p2p_chat_id

    save_config(config)
    print(f"\n✅ 設定を {CONFIG_PATH} に保存しました")


# ─── Token ───────────────────────────────────────────────────────────────────

_token_cache: dict = {}


def get_tenant_token(config: dict) -> str:
    """tenant_access_token を取得（キャッシュ付き、有効期限約 2 時間）"""
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expire", 0) > now + 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": config["app_id"], "app_secret": config["app_secret"]},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"トークン取得に失敗：{data}", file=sys.stderr)
        sys.exit(1)

    token = data["tenant_access_token"]
    _token_cache["token"] = token
    _token_cache["expire"] = now + data.get("expire", 7200)
    return token


def api_get(path: str, params: dict, config: dict, use_user_token: bool = False) -> dict:
    if use_user_token and config.get("user_access_token"):
        token = config["user_access_token"]
    else:
        token = get_tenant_token(config)
    resp = requests.get(
        f"{BASE_URL}{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    return resp.json()


def api_post(path: str, body: dict, config: dict, use_user_token: bool = False) -> dict:
    if use_user_token and config.get("user_access_token"):
        token = config["user_access_token"]
    else:
        token = get_tenant_token(config)
    resp = requests.post(
        f"{BASE_URL}{path}",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    return resp.json()


def exchange_code_for_token(code: str, config: dict) -> dict:
    """OAuth 認可コードを user_access_token に交換"""
    app_token = get_tenant_token(config)
    resp = requests.post(
        f"{BASE_URL}/authen/v1/oidc/access_token",
        headers={"Authorization": f"Bearer {app_token}"},
        json={"grant_type": "authorization_code", "code": code},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"トークン交換に失敗：{data}", file=sys.stderr)
        return {}
    return data.get("data", {})


# ─── ユーザー検索 ─────────────────────────────────────────────────────────────

def _find_user_by_contact(name: str, config: dict) -> Optional[dict]:
    """メールアドレスまたは電話番号でユーザーを検索（tenant_access_token を使用）"""
    # 入力タイプを判定
    emails, mobiles = [], []
    if "@" in name:
        emails = [name]
    elif name.replace("+", "").replace("-", "").isdigit():
        mobiles = [name]
    else:
        return None  # メールアドレスでも電話番号でもないため、スキップ

    body = {}
    if emails:
        body["emails"] = emails
    if mobiles:
        body["mobiles"] = mobiles

    data = api_post("/contact/v3/users/batch_get_id", body, config)
    if data.get("code") != 0:
        print(f"  メールアドレス/電話番号検索に失敗（code={data.get('code')}）：{data.get('msg')}", file=sys.stderr)
        return None

    user_list = data.get("data", {}).get("user_list", [])
    for item in user_list:
        user_id = item.get("user_id")
        if user_id:
            # ユーザー詳細を取得
            detail = api_get(f"/contact/v3/users/{user_id}", {"user_id_type": "user_id"}, config)
            if detail.get("code") == 0:
                user_data = detail.get("data", {}).get("user", {})
                print(f"  ユーザー発見：{user_data.get('name', user_id)}", file=sys.stderr)
                return user_data
            # 詳細が取得できない場合、基本情報を返す
            return {"user_id": user_id, "open_id": item.get("open_id", ""), "name": name}

    return None


def _find_user_by_department(name: str, config: dict) -> Optional[dict]:
    """部門を巡回してユーザーを検索（tenant_access_token を使用、contact:department.base:readonly が必要）"""
    print(f"  部門を巡回して {name} を検索中 ...", file=sys.stderr)

    # 全部門 ID を再帰的に取得
    dept_ids = ["0"]  # 0 = ルート部門
    queue = ["0"]
    while queue:
        parent_id = queue.pop(0)
        data = api_get(
            f"/contact/v3/departments/{parent_id}/children",
            {"page_size": 50, "fetch_child": False},
            config,
        )
        if data.get("code") != 0:
            if parent_id == "0":
                print(f"  部門巡回に失敗（code={data.get('code')}）：{data.get('msg')}", file=sys.stderr)
                print(f"  contact:department.base:readonly 権限が開通済みであることを確認してください", file=sys.stderr)
                return None
            continue

        children = data.get("data", {}).get("items", [])
        for child in children:
            child_id = child.get("department_id", "")
            if child_id:
                dept_ids.append(child_id)
                queue.append(child_id)

    print(f"  合計 {len(dept_ids)} 部門、ユーザーを検索中 ...", file=sys.stderr)

    # 各部門でユーザーを検索
    matches = []
    for dept_id in dept_ids:
        page_token = None
        while True:
            params = {"department_id": dept_id, "page_size": 50}
            if page_token:
                params["page_token"] = page_token

            data = api_get("/contact/v3/users/find_by_department", params, config)
            if data.get("code") != 0:
                break

            users = data.get("data", {}).get("items", [])
            for u in users:
                uname = u.get("name", "")
                en_name = u.get("en_name", "")
                if name in uname or name in en_name or uname == name or en_name == name:
                    matches.append(u)

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token")

        if len(matches) >= 10:
            break  # 够了

    return _select_user(matches, name)


def _select_user(users: list, name: str) -> Optional[dict]:
    """候補リストからユーザーを選択"""
    if not users:
        print(f"  ユーザーが見つかりません：{name}", file=sys.stderr)
        return None

    # 重複を除去（user_id 基準）
    seen = set()
    deduped = []
    for u in users:
        uid = u.get("user_id", u.get("open_id", id(u)))
        if uid not in seen:
            seen.add(uid)
            deduped.append(u)
    users = deduped

    if len(users) == 1:
        u = users[0]
        dept_ids = u.get("department_ids", [])
        print(f"  ユーザー発見：{u.get('name')}（部門：{dept_ids[0] if dept_ids else ''}）", file=sys.stderr)
        return u

    # 複数の結果がある場合、ユーザーに選択させる
    print(f"\n  {len(users)} 件の結果が見つかりました。選択してください：")
    for i, u in enumerate(users):
        dept_ids = u.get("department_ids", [])
        dept_str = dept_ids[0] if dept_ids else ""
        en = u.get("en_name", "")
        label = f"{u.get('name', '')} ({en})" if en else u.get("name", "")
        print(f"    [{i+1}] {label}  dept={dept_str}  uid={u.get('user_id', '')}")

    choice = input("\n  番号を選択（デフォルト 1）：").strip() or "1"
    try:
        idx = int(choice) - 1
        return users[idx]
    except (ValueError, IndexError):
        return users[0]


def find_user(name: str, config: dict) -> Optional[dict]:
    """Feishu ユーザーを検索

    戦略：
      1. 入力がメールアドレス/電話番号の場合 → batch_get_id で直接検索（最速）
      2. それ以外 → 部門を巡回して検索（contact:department.base:readonly が必要）
      3. 部門巡回も失敗した場合 → メールアドレス/電話番号の使用を提案
    """
    print(f"  ユーザー検索：{name} ...", file=sys.stderr)

    # 方法 1：メールアドレス/電話番号で直接検索
    user = _find_user_by_contact(name, config)
    if user:
        return user

    # 方法 2：部門巡回
    user = _find_user_by_department(name, config)
    if user:
        return user

    # すべて失敗
    print(f"\n  ❌ ユーザー {name} が見つかりませんでした", file=sys.stderr)
    print(f"  推奨事項：", file=sys.stderr)
    print(f"    1. contact:department.base:readonly 権限が開通済みであることを確認", file=sys.stderr)
    print(f"    2. メールアドレスで検索してみてください：--name user@company.com", file=sys.stderr)
    print(f"    3. 電話番号で検索してみてください：--name +8190XXXXXXXX", file=sys.stderr)
    return None


# ─── メッセージ履歴 ──────────────────────────────────────────────────────────

def get_chats_with_user(user_open_id: str, config: dict) -> list:
    """bot と対象ユーザーの両方が参加しているグループチャットを検索"""
    print("  グループチャットリストを取得中 ...", file=sys.stderr)

    chats = []
    page_token = None

    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token

        data = api_get("/im/v1/chats", params, config)
        if data.get("code") != 0:
            print(f"  グループチャットの取得に失敗：{data.get('msg')}", file=sys.stderr)
            break

        items = data.get("data", {}).get("items", [])
        chats.extend(items)

        if not data.get("data", {}).get("has_more"):
            break
        page_token = data.get("data", {}).get("page_token")

    print(f"  合計 {len(chats)} グループチャット、メンバーを確認中 ...", file=sys.stderr)

    # フィルター：対象ユーザーが参加しているグループ
    result = []
    for chat in chats:
        chat_id = chat.get("chat_id")
        if not chat_id:
            continue

        members_data = api_get(
            f"/im/v1/chats/{chat_id}/members",
            {"page_size": 100},
            config,
        )
        members = members_data.get("data", {}).get("items", [])
        for m in members:
            if m.get("member_id") == user_open_id or m.get("open_id") == user_open_id:
                result.append(chat)
                print(f"    ✓ {chat.get('name', chat_id)}", file=sys.stderr)
                break

    return result


def fetch_messages_from_chat(
    chat_id: str,
    user_open_id: str,
    limit: int,
    config: dict,
) -> list:
    """指定グループチャットから対象ユーザーのメッセージを取得"""
    messages = []
    page_token = None

    while len(messages) < limit:
        params = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "page_size": 50,
            "sort_type": "ByCreateTimeDesc",
        }
        if page_token:
            params["page_token"] = page_token

        data = api_get("/im/v1/messages", params, config)
        if data.get("code") != 0:
            break

        items = data.get("data", {}).get("items", [])
        if not items:
            break

        for item in items:
            sender = item.get("sender", {})
            sender_id = sender.get("id") or sender.get("open_id", "")
            if sender_id != user_open_id:
                continue

            # メッセージ内容を解析
            content_raw = item.get("body", {}).get("content", "")
            try:
                content_obj = json.loads(content_raw)
                # 富文本消息
                if isinstance(content_obj, dict):
                    text_parts = []
                    for line in content_obj.get("content", []):
                        for seg in line:
                            if seg.get("tag") in ("text", "a"):
                                text_parts.append(seg.get("text", ""))
                    content = " ".join(text_parts)
                else:
                    content = str(content_obj)
            except Exception:
                content = content_raw

            content = content.strip()
            if not content or content in ("[图片]", "[文件]", "[表情]", "[语音]"):
                continue

            ts = item.get("create_time", "")
            if ts:
                try:
                    ts = datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            messages.append({"content": content, "time": ts})

        if not data.get("data", {}).get("has_more"):
            break
        page_token = data.get("data", {}).get("page_token")

    return messages[:limit]


def fetch_p2p_messages(
    chat_id: str,
    user_open_id: str,
    limit: int,
    config: dict,
) -> list:
    """user_access_token を使用して DM 会話からメッセージを取得（双方の全メッセージを含む）"""
    messages = []
    page_token = None

    while len(messages) < limit:
        params = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "page_size": 50,
            "sort_type": "ByCreateTimeDesc",
        }
        if page_token:
            params["page_token"] = page_token

        data = api_get("/im/v1/messages", params, config, use_user_token=True)
        if data.get("code") != 0:
            print(f"  DM メッセージの取得に失敗（code={data.get('code')}）：{data.get('msg')}", file=sys.stderr)
            break

        items = data.get("data", {}).get("items", [])
        if not items:
            break

        for item in items:
            sender = item.get("sender", {})
            sender_id = sender.get("id") or sender.get("open_id", "")

            # メッセージ内容を解析
            content_raw = item.get("body", {}).get("content", "")
            try:
                content_obj = json.loads(content_raw)
                if isinstance(content_obj, dict):
                    # プレーンテキストメッセージ
                    if "text" in content_obj:
                        content = content_obj["text"]
                    else:
                        # リッチテキストメッセージ
                        text_parts = []
                        for line in content_obj.get("content", []):
                            for seg in line:
                                if seg.get("tag") in ("text", "a"):
                                    text_parts.append(seg.get("text", ""))
                        content = " ".join(text_parts)
                else:
                    content = str(content_obj)
            except Exception:
                content = content_raw

            content = content.strip()
            if not content or content in ("[图片]", "[文件]", "[表情]", "[语音]"):
                continue

            ts = item.get("create_time", "")
            if ts:
                try:
                    ts = datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            is_target = (sender_id == user_open_id)
            messages.append({
                "content": content,
                "time": ts,
                "sender_id": sender_id,
                "is_target": is_target,
            })

        if not data.get("data", {}).get("has_more"):
            break
        page_token = data.get("data", {}).get("page_token")

    return messages[:limit]


def collect_messages(
    user: dict,
    msg_limit: int,
    config: dict,
) -> str:
    """対象ユーザーの全メッセージ履歴を収集（グループチャット + DM）"""
    user_open_id = user.get("open_id") or user.get("user_id", "")
    name = user.get("name", "")

    all_messages = []
    chat_sources = []

    # ── DM 収集（user_access_token + p2p_chat_id が必要）──
    p2p_chat_id = config.get("p2p_chat_id", "")
    user_token = config.get("user_access_token", "")

    if user_token and p2p_chat_id:
        print(f"  📱 DM メッセージを収集中（chat_id: {p2p_chat_id}）...", file=sys.stderr)
        p2p_msgs = fetch_p2p_messages(p2p_chat_id, user_open_id, msg_limit, config)
        for m in p2p_msgs:
            m["chat"] = "DM"
        all_messages.extend(p2p_msgs)
        chat_sources.append(f"DM（{len(p2p_msgs)} 件）")
        print(f"    {len(p2p_msgs)} 件の DM メッセージを取得", file=sys.stderr)
    elif user_token and not p2p_chat_id:
        print(f"  ⚠️  user_access_token はありますが p2p_chat_id が未設定のため、DM 収集をスキップします", file=sys.stderr)
        print(f"     設定に p2p_chat_id を追加してください（メッセージ送信 API の返り値から取得可能）", file=sys.stderr)

    # ── グループチャット収集（tenant_access_token を使用）──
    remaining = msg_limit - len(all_messages)
    if remaining > 0:
        chats = get_chats_with_user(user_open_id, config)
        if chats:
            per_chat_limit = max(100, remaining // len(chats))
            for chat in chats:
                chat_id = chat.get("chat_id")
                chat_name = chat.get("name", chat_id)
                print(f"  「{chat_name}」のメッセージを取得中 ...", file=sys.stderr)

                msgs = fetch_messages_from_chat(chat_id, user_open_id, per_chat_limit, config)
                for m in msgs:
                    m["chat"] = chat_name
                all_messages.extend(msgs)
                chat_sources.append(f"{chat_name}（{len(msgs)} 件）")
                print(f"    {len(msgs)} 件取得", file=sys.stderr)

    if not all_messages:
        tips = f"# メッセージ履歴\n\n{name} のメッセージ履歴が見つかりませんでした。\n\n"
        tips += "原因として考えられること：\n"
        tips += "  - グループチャット収集：bot が関連するグループチャットに追加されていない\n"
        tips += "  - DM 収集：user_access_token または p2p_chat_id が未設定\n"
        tips += "\nDM 収集の設定方法：\n"
        tips += "  1. Feishu 開放プラットフォームで im:message と im:chat のユーザー権限を開通\n"
        tips += "  2. OAuth 認可で user_access_token を取得（--exchange-code）\n"
        tips += "  3. p2p_chat_id（DM 会話 ID）を設定\n"
        return tips

    # 分類して出力
    # DM メッセージは双方の会話を含むため、発言者を標記
    target_msgs = [m for m in all_messages if m.get("is_target", True)]
    other_msgs = [m for m in all_messages if not m.get("is_target", True)]

    long_msgs = [m for m in target_msgs if len(m.get("content", "")) > 50]
    short_msgs = [m for m in target_msgs if len(m.get("content", "")) <= 50]

    lines = [
        f"# Feishu メッセージ履歴（自動収集）",
        f"対象：{name}",
        f"ソース：{', '.join(chat_sources)}",
        f"合計 {len(all_messages)} 件のメッセージ（対象ユーザー {len(target_msgs)} 件、相手方 {len(other_msgs)} 件）",
        "",
        "---",
        "",
        "## 長文メッセージ（意見/判断/技術系）",
        "",
    ]
    for m in long_msgs:
        lines.append(f"[{m.get('time', '')}][{m.get('chat', '')}] {m['content']}")
        lines.append("")

    lines += ["---", "", "## 日常メッセージ（スタイル参考）", ""]
    for m in short_msgs[:300]:
        lines.append(f"[{m.get('time', '')}] {m['content']}")

    # DM 対話コンテキスト（双方の会話を保持し、文脈理解を容易にする）
    p2p_msgs = [m for m in all_messages if m.get("chat") == "DM"]
    if p2p_msgs:
        lines += ["", "---", "", "## DM 対話コンテキスト（双方のメッセージを含む）", ""]
        # 時系列で正順
        p2p_sorted = sorted(p2p_msgs, key=lambda x: x.get("time", ""))
        for m in p2p_sorted[:500]:
            who = f"[{name}]" if m.get("is_target") else "[相手]"
            lines.append(f"[{m.get('time', '')}] {who} {m['content']}")

    return "\n".join(lines)


# ─── ドキュメント収集 ─────────────────────────────────────────────────────────

def search_docs_by_user(user_open_id: str, name: str, doc_limit: int, config: dict) -> list:
    """対象ユーザーが作成または編集したドキュメントを検索"""
    print(f"  {name} のドキュメントを検索中 ...", file=sys.stderr)

    data = api_post(
        "/search/v2/message",
        {
            "query": name,
            "search_type": "docs",
            "docs_options": {
                "creator_ids": [user_open_id],
            },
            "page_size": doc_limit,
        },
        config,
    )

    if data.get("code") != 0:
        # フォールバック：キーワードで検索
        print(f"  作成者での検索に失敗、キーワード検索に切り替え中 ...", file=sys.stderr)
        data = api_post(
            "/search/v2/message",
            {
                "query": name,
                "search_type": "docs",
                "page_size": doc_limit,
            },
            config,
        )

    docs = []
    for item in data.get("data", {}).get("results", []):
        doc_info = item.get("docs_info", {})
        if doc_info:
            docs.append({
                "title": doc_info.get("title", ""),
                "url": doc_info.get("url", ""),
                "type": doc_info.get("docs_type", ""),
                "creator": doc_info.get("creator", {}).get("name", ""),
            })

    print(f"  {len(docs)} 件のドキュメントが見つかりました", file=sys.stderr)
    return docs


def fetch_doc_content(doc_token: str, doc_type: str, config: dict) -> str:
    """単一ドキュメントの内容を取得"""
    if doc_type in ("doc", "docx"):
        data = api_get(f"/docx/v1/documents/{doc_token}/raw_content", {}, config)
        return data.get("data", {}).get("content", "")

    elif doc_type == "wiki":
        # まず wiki node 情報を取得
        node_data = api_get(f"/wiki/v2/spaces/get_node", {"token": doc_token}, config)
        obj_token = node_data.get("data", {}).get("node", {}).get("obj_token", doc_token)
        obj_type = node_data.get("data", {}).get("node", {}).get("obj_type", "docx")
        return fetch_doc_content(obj_token, obj_type, config)

    return ""


def collect_docs(user: dict, doc_limit: int, config: dict) -> str:
    """対象ユーザーのドキュメントを収集"""
    import re
    user_open_id = user.get("open_id") or user.get("user_id", "")
    name = user.get("name", "")

    docs = search_docs_by_user(user_open_id, name, doc_limit, config)
    if not docs:
        return f"# ドキュメント内容\n\n{name} に関連するドキュメントが見つかりませんでした\n"

    lines = [
        f"# ドキュメント内容（自動収集）",
        f"対象：{name}",
        f"合計 {len(docs)} 件",
        "",
    ]

    for doc in docs:
        url = doc.get("url", "")
        title = doc.get("title", "無題")
        doc_type = doc.get("type", "")

        print(f"  ドキュメント取得中：{title} ...", file=sys.stderr)

        # URL からトークンを抽出
        token_match = re.search(r"/(?:wiki|docx|docs|sheets|base)/([A-Za-z0-9]+)", url)
        if not token_match:
            continue
        doc_token = token_match.group(1)

        content = fetch_doc_content(doc_token, doc_type or "docx", config)
        if not content or len(content.strip()) < 20:
            print(f"    内容が空のため、スキップします", file=sys.stderr)
            continue

        lines += [
            f"---",
            f"## 《{title}》",
            f"リンク：{url}",
            f"作成者：{doc.get('creator', '')}",
            "",
            content.strip(),
            "",
        ]

    return "\n".join(lines)


# ─── マルチディメンションテーブル ─────────────────────────────────────────────

def collect_bitable(app_token: str, config: dict) -> str:
    """マルチディメンションテーブルの内容を取得"""
    # 全テーブルを取得
    data = api_get(f"/bitable/v1/apps/{app_token}/tables", {"page_size": 100}, config)
    tables = data.get("data", {}).get("items", [])

    if not tables:
        return "（マルチディメンションテーブルが空です）\n"

    lines = []
    for table in tables:
        table_id = table.get("table_id")
        table_name = table.get("name", table_id)

        # フィールドを取得
        fields_data = api_get(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            {"page_size": 100},
            config,
        )
        fields = [f.get("field_name", "") for f in fields_data.get("data", {}).get("items", [])]

        # レコードを取得
        records_data = api_get(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            {"page_size": 100},
            config,
        )
        records = records_data.get("data", {}).get("items", [])

        lines.append(f"### テーブル：{table_name}")
        lines.append("")
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


# ─── メインフロー ─────────────────────────────────────────────────────────────

def collect_all(
    name: str,
    output_dir: Path,
    msg_limit: int,
    doc_limit: int,
    config: dict,
) -> dict:
    """同僚の利用可能な全データを収集し、output_dir に出力"""
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    print(f"\n🔍 収集開始：{name}\n", file=sys.stderr)

    # Step 1: ユーザーを検索
    user = find_user(name, config)
    if not user:
        print(f"❌ ユーザー {name} が見つかりません。氏名が正しいか確認してください", file=sys.stderr)
        sys.exit(1)

    # Step 2: メッセージ履歴を収集
    print(f"\n📨 メッセージ履歴を収集中（上限 {msg_limit} 件）...", file=sys.stderr)
    try:
        msg_content = collect_messages(user, msg_limit, config)
        msg_path = output_dir / "messages.txt"
        msg_path.write_text(msg_content, encoding="utf-8")
        results["messages"] = str(msg_path)
        print(f"  ✅ メッセージ履歴 → {msg_path}", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  メッセージ収集に失敗：{e}", file=sys.stderr)

    # Step 3: ドキュメントを収集
    print(f"\n📄 ドキュメント収集中（上限 {doc_limit} 件）...", file=sys.stderr)
    try:
        doc_content = collect_docs(user, doc_limit, config)
        doc_path = output_dir / "docs.txt"
        doc_path.write_text(doc_content, encoding="utf-8")
        results["docs"] = str(doc_path)
        print(f"  ✅ ドキュメント内容 → {doc_path}", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  ドキュメント収集に失敗：{e}", file=sys.stderr)

    # サマリーを書き込み
    summary = {
        "name": name,
        "user_id": user.get("user_id", ""),
        "open_id": user.get("open_id", ""),
        "department": user.get("department_path", []),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "files": results,
    }
    (output_dir / "collection_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )

    print(f"\n✅ 収集完了。出力ディレクトリ：{output_dir}", file=sys.stderr)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Feishu データ自動収集ツール")
    parser.add_argument("--setup", action="store_true", help="設定を初期化")
    parser.add_argument("--name", help="同僚の氏名")
    parser.add_argument("--output-dir", default=None, help="出力ディレクトリ（デフォルト ./knowledge/{name}）")
    parser.add_argument("--msg-limit", type=int, default=1000, help="最大メッセージ収集件数（デフォルト 1000）")
    parser.add_argument("--doc-limit", type=int, default=20, help="最大ドキュメント収集件数（デフォルト 20）")
    parser.add_argument("--exchange-code", metavar="CODE", help="OAuth 認可コードを user_access_token に交換して設定に保存")
    parser.add_argument("--user-token", metavar="TOKEN", help="user_access_token を直接指定（設定ファイルを上書き）")
    parser.add_argument("--p2p-chat-id", metavar="CHAT_ID", help="DM 会話 ID（設定ファイルを上書き）")
    parser.add_argument("--open-id", metavar="OPEN_ID", help="対象ユーザーの open_id を直接指定（ユーザー検索をスキップ）")

    args = parser.parse_args()

    if args.setup:
        setup_config()
        return

    config = load_config()

    # user_access_token に交換
    if args.exchange_code:
        token_data = exchange_code_for_token(args.exchange_code, config)
        if token_data:
            config["user_access_token"] = token_data["access_token"]
            config["refresh_token"] = token_data.get("refresh_token", "")
            save_config(config)
            print(f"✅ user_access_token を保存しました（scope: {token_data.get('scope', '')}）")
            print(f"   token: {token_data['access_token'][:20]}...")
        else:
            print("❌ 交換に失敗しました。code が有効か確認してください")
        return

    if not args.name and not args.open_id:
        parser.error("--name または --open-id を指定してください")

    # コマンドライン引数で設定を上書き
    if args.user_token:
        config["user_access_token"] = args.user_token
    if args.p2p_chat_id:
        config["p2p_chat_id"] = args.p2p_chat_id

    output_dir = Path(args.output_dir) if args.output_dir else Path(f"./knowledge/{args.name or 'target'}")

    # open_id が指定されている場合、ユーザー検索をスキップ
    if args.open_id:
        user = {"open_id": args.open_id, "name": args.name or "target"}
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n🔍 指定された open_id を使用: {args.open_id}\n", file=sys.stderr)

        # メッセージのみ収集
        print(f"📨 メッセージ履歴を収集中（上限 {args.msg_limit} 件）...", file=sys.stderr)
        msg_content = collect_messages(user, args.msg_limit, config)
        msg_path = output_dir / "messages.txt"
        msg_path.write_text(msg_content, encoding="utf-8")
        print(f"  ✅ メッセージ履歴 → {msg_path}", file=sys.stderr)
        return

    collect_all(
        name=args.name,
        output_dir=output_dir,
        msg_limit=args.msg_limit,
        doc_limit=args.doc_limit,
        config=config,
    )


if __name__ == "__main__":
    main()
