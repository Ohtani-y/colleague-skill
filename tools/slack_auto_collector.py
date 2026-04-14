#!/usr/bin/env python3
"""
Slack 自動収集ツール

同僚の Slack 氏名/ユーザー名を入力すると、自動で以下を実行：
  1. Slack ユーザーを検索し、user_id を取得
  2. Bot と共通のチャンネルを見つけ、該当ユーザーが送信したメッセージを取得
  3. 統一フォーマットで出力し、create-colleague の分析フローへ直接投入

前提条件：
  python3 slack_auto_collector.py --setup   # Bot Token を設定（初回のみ）

使い方：
  python3 slack_auto_collector.py --name "田中太郎" --output-dir ./knowledge/tanaka
  python3 slack_auto_collector.py --name "john" --msg-limit 500 --channel-limit 30

必要な Bot Token Scopes（OAuth & Permissions）：
  channels:history      public channel メッセージの読取
  channels:read         public channels の一覧表示
  groups:history        private channel メッセージの読取
  groups:read           private channels の一覧表示
  im:history            DM メッセージの読取（任意）
  im:read               DM の一覧表示（任意）
  mpim:history          グループ DM メッセージの読取（任意）
  mpim:read             グループ DM の一覧表示（任意）
  users:read            ユーザーリストの検索

注意：
  - 無料版 Workspace は直近 90 日間のメッセージのみ保持
  - Workspace 管理者による Bot App のインストールが必要
"""

from __future__ import annotations

import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ─── 依存チェック ────────────────────────────────────────────────────────────

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    print(
        "エラー：先に slack_sdk をインストールしてください：pip3 install slack-sdk",
        file=sys.stderr,
    )
    sys.exit(1)

# ─── 定数 ──────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".colleague-skill" / "slack_config.json"

# Slack チャンネルタイプ（収集範囲）
CHANNEL_TYPES = "public_channel,private_channel,mpim,im"

# レートリミット リトライ設定
MAX_RETRIES = 5
RETRY_BASE_WAIT = 1.0     # 最短待機秒数
RETRY_MAX_WAIT = 60.0     # 最長待機秒数

# 収集デフォルト値
DEFAULT_MSG_LIMIT = 1000
DEFAULT_CHANNEL_LIMIT = 50  # 最大チェックチャンネル数


# ─── エラータイプ ────────────────────────────────────────────────────────────

class SlackCollectorError(Exception):
    """収集プロセスで想定されるエラー。直接終了"""


class SlackScopeError(SlackCollectorError):
    """Bot Token に必要な scope 権限が不足"""


class SlackAuthError(SlackCollectorError):
    """Token が無効または期限切れ"""


# ─── 設定管理 ────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(
            "設定が見つかりません。先に実行してください：python3 slack_auto_collector.py --setup",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        return json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError:
        print(f"設定ファイルが破損しています。--setup を再実行してください：{CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))


def setup_config() -> None:
    print("=== Slack 自動収集設定 ===\n")
    print("手順 1：https://api.slack.com/apps にアクセスして新規 App を作成")
    print("        「From scratch」を選択 → App Name を入力 → 対象 Workspace を選択\n")
    print("手順 2：OAuth & Permissions で Bot Token Scopes に以下を追加：")
    print()
    print("  メッセージ系（必須）：")
    print("    channels:history     public channel 履歴メッセージの読取")
    print("    groups:history       private channel 履歴メッセージの読取")
    print("    mpim:history         グループ DM 履歴メッセージの読取")
    print("    im:history           DM 履歴メッセージの読取（任意）")
    print()
    print("  チャンネル情報（必須）：")
    print("    channels:read        public channels の一覧表示")
    print("    groups:read          private channels の一覧表示")
    print("    mpim:read            グループ DM の一覧表示")
    print("    im:read              DM の一覧表示（任意）")
    print()
    print("  ユーザー情報（必須）：")
    print("    users:read           ユーザーリストの検索")
    print()
    print("手順 3：Install to Workspace → Bot User OAuth Token（xoxb-...）をコピー")
    print("手順 4：Bot を対象チャンネルに追加（/invite @your-bot-name）\n")

    token = input("Bot User OAuth Token (xoxb-...): ").strip()
    if not token.startswith("xoxb-"):
        print("警告：Token の形式が正しくありません。xoxb- で始まる必要があります", file=sys.stderr)

    # トークンが有効か検証
    print("\nToken を検証中 ...", end=" ", flush=True)
    try:
        client = WebClient(token=token)
        resp = client.auth_test()
        workspace = resp.get("team", "Unknown")
        bot_name = resp.get("user", "Unknown")
        print(f"OK\n  Workspace：{workspace}，Bot：{bot_name}")
    except SlackApiError as e:
        err = e.response.get("error", str(e))
        print(f"失敗\n  エラー：{err}", file=sys.stderr)
        if err == "invalid_auth":
            print("  Token が無効です。再生成してください", file=sys.stderr)
        sys.exit(1)

    config = {"bot_token": token}
    save_config(config)
    print(f"\n✅ 設定を {CONFIG_PATH} に保存しました")
    print("   Bot を対象チャンネルに追加済みであることを確認してください。未追加の場合メッセージを読み取れません")


# ─── Slack Client ラッパー（レートリミット リトライ付き）──────────────────────

class RateLimitedClient:
    """slack_sdk WebClient のラッパー。429 レートリミットを自動処理"""

    def __init__(self, token: str) -> None:
        self._client = WebClient(token=token)

    def call(self, method: str, **kwargs) -> dict:
        """任意の Slack API を呼び出し、ratelimited の場合は自動的に待機してリトライ"""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                fn = getattr(self._client, method)
                resp = fn(**kwargs)
                return resp.data
            except SlackApiError as e:
                error = e.response.get("error", "")

                # レートリミット：Retry-After ヘッダーを読んで待機
                if error == "ratelimited":
                    wait = float(
                        e.response.headers.get("Retry-After", RETRY_BASE_WAIT * attempt)
                    )
                    wait = min(wait, RETRY_MAX_WAIT)
                    print(
                        f"  [レートリミット] {wait:.0f}秒待機中（{attempt}/{MAX_RETRIES} 回目のリトライ）...",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue

                # 権限エラー：リトライせずに直接スロー
                if error == "missing_scope":
                    missing = e.response.get("needed", "unknown")
                    raise SlackScopeError(
                        f"Bot Token に権限 scope が不足しています：{missing}\n"
                        f"  https://api.slack.com/apps → OAuth & Permissions → Bot Token Scopes で追加してください"
                    ) from e

                if error in ("invalid_auth", "token_revoked", "account_inactive"):
                    raise SlackAuthError(
                        f"Token 認証に失敗（{error}）。--setup を再実行して新しい Token を設定してください"
                    ) from e

                # チャンネルの権限なし（Bot 未参加）：呼び出し元で処理
                if error in ("not_in_channel", "channel_not_found"):
                    raise

                # その他のエラー：警告を表示し、空データを返す
                print(f"  [API 警告] {method} がエラーを返しました：{error}", file=sys.stderr)
                return {}

        # リトライ回数の上限に到達
        print(f"  [エラー] {method} 複数回のリトライ後も失敗、スキップします", file=sys.stderr)
        return {}

    def paginate(self, method: str, result_key: str, **kwargs) -> list:
        """自動ページネーション、全結果を統合したリストを返す"""
        items: list = []
        cursor = None

        while True:
            params = dict(kwargs)
            if cursor:
                params["cursor"] = cursor

            data = self.call(method, **params)
            if not data:
                break

            items.extend(data.get(result_key, []))

            meta = data.get("response_metadata", {})
            cursor = meta.get("next_cursor")
            if not cursor:
                break

        return items


# ─── ユーザー検索 ────────────────────────────────────────────────────────────

def find_user(name: str, client: RateLimitedClient) -> Optional[dict]:
    """
    氏名（real_name / display_name / name）で Slack ユーザーを検索。
    中国語名、英語ユーザー名、あいまい一致に対応。
    """
    print(f"  ユーザー検索：{name} ...", file=sys.stderr)

    try:
        members = client.paginate("users_list", "members", limit=200)
    except SlackScopeError as e:
        print(f"  ❌ {e}", file=sys.stderr)
        sys.exit(1)

    # Bot / 無効化されたアカウントを除外
    members = [
        m for m in members
        if not m.get("is_bot") and not m.get("deleted") and m.get("id") != "USLACKBOT"
    ]

    name_lower = name.lower()

    def score(member: dict) -> int:
        profile = member.get("profile", {})
        real_name = (profile.get("real_name") or "").lower()
        display_name = (profile.get("display_name") or "").lower()
        username = (member.get("name") or "").lower()

        if name_lower in (real_name, display_name, username):
            return 3  # 完全一致
        if (
            name_lower in real_name
            or name_lower in display_name
            or name_lower in username
        ):
            return 2  # 部分一致
        # 中国語名の文字分割マッチ
        if all(ch in real_name or ch in display_name for ch in name_lower if ch.strip()):
            return 1
        return 0

    scored = [(score(m), m) for m in members]
    candidates = [(s, m) for s, m in scored if s > 0]

    if not candidates:
        print(f"  ユーザーが見つかりません：{name}", file=sys.stderr)
        print(
            "  ヒント：氏名のスペルを確認するか、英語ユーザー名（例: john.doe）を試してください",
            file=sys.stderr,
        )
        return None

    candidates.sort(key=lambda x: -x[0])

    if len(candidates) == 1:
        _, user = candidates[0]
        _print_user(user)
        return user

    # 複数の候補がある場合、ユーザーに選択させる
    print(f"\n  {len(candidates)} 件のマッチが見つかりました。選択してください：")
    for i, (_, m) in enumerate(candidates[:10]):
        profile = m.get("profile", {})
        real_name = profile.get("real_name", "")
        display_name = profile.get("display_name", "")
        username = m.get("name", "")
        title = profile.get("title", "")
        print(f"    [{i+1}] {real_name}（@{display_name or username}）  {title}")

    choice = input("\n  番号を選択（デフォルト 1）：").strip() or "1"
    try:
        idx = int(choice) - 1
        _, user = candidates[idx]
    except (ValueError, IndexError):
        _, user = candidates[0]

    _print_user(user)
    return user


def _print_user(user: dict) -> None:
    profile = user.get("profile", {})
    real_name = profile.get("real_name", user.get("name", ""))
    display_name = profile.get("display_name", "")
    title = profile.get("title", "")
    print(
        f"  ユーザー発見：{real_name}（@{display_name}）  {title}",
        file=sys.stderr,
    )


# ─── チャンネル検出 ──────────────────────────────────────────────────────────

def get_channels_with_user(
    user_id: str,
    channel_limit: int,
    client: RateLimitedClient,
) -> list:
    """
    Bot が参加済みかつ対象ユーザーも参加している全チャンネルを返す。
    戦略：まず Bot の全チャンネルを一覧表示し、次にメンバーリストを個別にチェック。
    """
    print("  チャンネルリストを取得中 ...", file=sys.stderr)

    try:
        channels = client.paginate(
            "conversations_list",
            "channels",
            types=CHANNEL_TYPES,
            exclude_archived=True,
            limit=200,
        )
    except SlackScopeError as e:
        print(f"  ❌ {e}", file=sys.stderr)
        return []

    # Bot がメンバーであるチャンネルのみ保持
    bot_channels = [c for c in channels if c.get("is_member")]
    print(f"  Bot が参加済みの {len(bot_channels)} チャンネル、メンバーを確認中 ...", file=sys.stderr)

    if len(bot_channels) > channel_limit:
        print(
            f"  チャンネル数が上限 {channel_limit} を超えています。先頭 {channel_limit} チャンネルのみ確認します",
            file=sys.stderr,
        )
        bot_channels = bot_channels[:channel_limit]

    result = []
    for ch in bot_channels:
        ch_id = ch.get("id", "")
        ch_name = ch.get("name", ch_id)

        try:
            members = client.paginate(
                "conversations_members",
                "members",
                channel=ch_id,
                limit=200,
            )
        except SlackApiError as e:
            err = e.response.get("error", "")
            if err in ("not_in_channel", "channel_not_found"):
                continue
            print(f"    チャンネル {ch_name} をスキップ（{err}）", file=sys.stderr)
            continue
        except SlackScopeError as e:
            print(f"  ❌ {e}", file=sys.stderr)
            continue

        if user_id in members:
            result.append(ch)
            print(f"    ✓ #{ch_name}", file=sys.stderr)

    return result


# ─── メッセージ収集 ──────────────────────────────────────────────────────────

def fetch_messages_from_channel(
    channel_id: str,
    channel_name: str,
    user_id: str,
    limit: int,
    client: RateLimitedClient,
) -> list:
    """
    指定チャンネルから対象ユーザーが送信したメッセージを取得。
    時系列逆順でページネーションし、limit に達するかデータがなくなるまで取得。
    """
    messages = []
    cursor = None
    pages_fetched = 0
    MAX_PAGES = 50  # 無限ページネーションの防止

    while len(messages) < limit and pages_fetched < MAX_PAGES:
        params: dict = {"channel": channel_id, "limit": 200}
        if cursor:
            params["cursor"] = cursor

        try:
            data = client.call("conversations_history", **params)
        except SlackApiError as e:
            err = e.response.get("error", "")
            if err == "not_in_channel":
                print(
                    f"    Bot がチャンネル #{channel_name} に参加していません、スキップ（/invite @bot を実行してください）",
                    file=sys.stderr,
                )
            else:
                print(f"    #{channel_name} の取得に失敗（{err}）", file=sys.stderr)
            break

        if not data:
            break

        pages_fetched += 1
        raw_msgs = data.get("messages", [])

        for msg in raw_msgs:
            # 対象ユーザーの送信メッセージのみ、システムメッセージを除外
            if msg.get("user") != user_id:
                continue
            if msg.get("subtype"):  # join/leave/bot_message 等のシステムタイプ
                continue

            text = msg.get("text", "").strip()
            if not text:
                continue

            # 絵文字のみまたは添付ファイルのみのメッセージを除外
            if _is_noise(text):
                continue

            ts_raw = msg.get("ts", "")
            time_str = _format_ts(ts_raw)

            # thread_reply_count がある場合はスレッド開始メッセージで、ウェイトが高い
            is_thread_starter = bool(msg.get("reply_count", 0))

            messages.append(
                {
                    "content": text,
                    "time": time_str,
                    "channel": channel_name,
                    "is_thread_starter": is_thread_starter,
                }
            )

        meta = data.get("response_metadata", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break

    return messages[:limit]


def _is_noise(text: str) -> bool:
    """無意味なメッセージかどうかを判定（絵文字のみ、@mention、URL）"""
    import re
    # Slack 特殊フォーマットを除去した後ほぼ空になる
    cleaned = re.sub(r"<[^>]+>", "", text).strip()
    cleaned = re.sub(r":[a-z_]+:", "", cleaned).strip()
    return len(cleaned) < 2


def _format_ts(ts: str) -> str:
    """Slack タイムスタンプ（Unix float string）を読みやすい時刻に変換"""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return ts


# ─── メイン収集フロー ────────────────────────────────────────────────────────

def collect_messages(
    user: dict,
    channels: list,
    msg_limit: int,
    client: RateLimitedClient,
) -> str:
    """全チャンネルから対象ユーザーのメッセージを収集し、フォーマット済みテキストを返す"""
    user_id = user["id"]
    name = user.get("profile", {}).get("real_name") or user.get("name", user_id)

    if not channels:
        return (
            f"# メッセージ履歴\n\n"
            f"{name} との共通チャンネルが見つかりませんでした。\n"
            f"Bot が関連チャンネルに追加済みであることを確認してください（/invite @bot）\n"
        )

    all_messages: list = []
    per_channel_limit = max(100, msg_limit // len(channels))

    for ch in channels:
        ch_id = ch.get("id", "")
        ch_name = ch.get("name", ch_id)
        print(f"  #{ch_name} のメッセージを取得中 ...", file=sys.stderr)

        msgs = fetch_messages_from_channel(
            ch_id, ch_name, user_id, per_channel_limit, client
        )
        all_messages.extend(msgs)
        print(f"    {len(msgs)} 件取得", file=sys.stderr)

    # ウェイト別に分類
    thread_msgs = [m for m in all_messages if m["is_thread_starter"]]
    long_msgs = [
        m for m in all_messages
        if not m["is_thread_starter"] and len(m["content"]) > 50
    ]
    short_msgs = [
        m for m in all_messages
        if not m["is_thread_starter"] and len(m["content"]) <= 50
    ]

    channel_names = ", ".join(f"#{c.get('name', c.get('id', ''))}" for c in channels)

    lines = [
        "# Slack メッセージ履歴（自動収集）",
        f"対象：{name}",
        f"ソースチャンネル：{channel_names}",
        f"合計 {len(all_messages)} 件のメッセージ",
        f"  スレッド開始メッセージ：{len(thread_msgs)} 件",
        f"  長文メッセージ（>50文字）：{len(long_msgs)} 件",
        f"  短文メッセージ：{len(short_msgs)} 件",
        "",
        "---",
        "",
        "## スレッド開始メッセージ（最高ウェイト：意見/判断/技術共有）",
        "",
    ]
    for m in thread_msgs:
        lines.append(f"[{m['time']}][#{m['channel']}] {m['content']}")
        lines.append("")

    lines += [
        "---",
        "",
        "## 長文メッセージ（意見/提案/ディスカッション系）",
        "",
    ]
    for m in long_msgs:
        lines.append(f"[{m['time']}][#{m['channel']}] {m['content']}")
        lines.append("")

    lines += ["---", "", "## 日常メッセージ（スタイル参考）", ""]
    for m in short_msgs[:300]:
        lines.append(f"[{m['time']}] {m['content']}")

    return "\n".join(lines)


def collect_all(
    name: str,
    output_dir: Path,
    msg_limit: int,
    channel_limit: int,
    config: dict,
) -> dict:
    """同僚の全 Slack データを収集し、output_dir に出力"""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    print(f"\n🔍 収集開始：{name}\n", file=sys.stderr)

    # Client を初期化
    try:
        client = RateLimitedClient(config["bot_token"])
        # トークンの有効性を迅速に検証
        auth_data = client.call("auth_test")
        if not auth_data:
            raise SlackAuthError("auth_test 无响应，请检查 Token")
        print(
            f"  Workspace：{auth_data.get('team')}，Bot：{auth_data.get('user')}",
            file=sys.stderr,
        )
    except SlackAuthError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    # Step 1: ユーザーを検索
    user = find_user(name, client)
    if not user:
        print(f"❌ ユーザー {name} が見つかりません。氏名/ユーザー名が正しいか確認してください", file=sys.stderr)
        sys.exit(1)

    user_id = user["id"]
    profile = user.get("profile", {})
    real_name = profile.get("real_name") or user.get("name", user_id)

    # Step 2: 共通チャンネルを検索
    print(f"\n📡 {real_name} との共通チャンネルを検索中（上限 {channel_limit} チャンネル）...", file=sys.stderr)
    channels = get_channels_with_user(user_id, channel_limit, client)
    print(f"  共通チャンネル：{len(channels)} 件", file=sys.stderr)

    # Step 3: メッセージを収集
    print(f"\n📨 メッセージ履歴を収集中（上限 {msg_limit} 件）...", file=sys.stderr)
    try:
        msg_content = collect_messages(user, channels, msg_limit, client)
        msg_path = output_dir / "messages.txt"
        msg_path.write_text(msg_content, encoding="utf-8")
        results["messages"] = str(msg_path)
        print(f"  ✅ メッセージ履歴 → {msg_path}", file=sys.stderr)
    except SlackCollectorError as e:
        print(f"  ❌ {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"  ⚠️  メッセージ収集に失敗：{e}", file=sys.stderr)

    # サマリーを書き込み
    summary = {
        "name": real_name,
        "slack_user_id": user_id,
        "display_name": profile.get("display_name", ""),
        "title": profile.get("title", ""),
        "channels": [
            {"id": c.get("id"), "name": c.get("name")} for c in channels
        ],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "files": results,
        "note": "無料版 Workspace は直近 90 日間のメッセージのみ保持",
    }
    summary_path = output_dir / "collection_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"  ✅ 収集サマリー → {summary_path}", file=sys.stderr)

    print(f"\n✅ 収集完了。出力ディレクトリ：{output_dir}", file=sys.stderr)
    return results


# ─── CLI エントリーポイント ────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Slack データ自動収集ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例：
  # 初回設定
  python3 slack_auto_collector.py --setup

  # 同僚のデータを収集
  python3 slack_auto_collector.py --name "田中太郎"
  python3 slack_auto_collector.py --name "john.doe" --output-dir ./knowledge/john --msg-limit 500
        """,
    )
    parser.add_argument("--setup", action="store_true", help="設定を初期化（Bot Token）")
    parser.add_argument("--name", help="同僚の氏名または Slack ユーザー名")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="出力ディレクトリ（デフォルト ./knowledge/{name}）",
    )
    parser.add_argument(
        "--msg-limit",
        type=int,
        default=DEFAULT_MSG_LIMIT,
        help=f"最大メッセージ収集件数（デフォルト {DEFAULT_MSG_LIMIT}）",
    )
    parser.add_argument(
        "--channel-limit",
        type=int,
        default=DEFAULT_CHANNEL_LIMIT,
        help=f"最大チェックチャンネル数（デフォルト {DEFAULT_CHANNEL_LIMIT}）",
    )

    args = parser.parse_args()

    if args.setup:
        setup_config()
        return

    if not args.name:
        parser.print_help()
        parser.error("--name パラメータを指定してください")

    config = load_config()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(f"./knowledge/{args.name}")
    )

    try:
        collect_all(
            name=args.name,
            output_dir=output_dir,
            msg_limit=args.msg_limit,
            channel_limit=args.channel_limit,
            config=config,
        )
    except SlackCollectorError as e:
        print(f"\n❌ 収集に失敗：{e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nキャンセルされました", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
