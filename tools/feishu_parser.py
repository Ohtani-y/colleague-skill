#!/usr/bin/env python3
"""
Feishu メッセージエクスポート JSON 解析ツール

対応エクスポートフォーマット：
1. Feishu 公式エクスポート（グループチャット記録）：通常 JSON 配列、各メッセージに sender、content、timestamp を含む
2. 手動整理された TXT フォーマット（各行：時間 送信者：内容）

使い方：
    python feishu_parser.py --file messages.json --target "田中太郎" --output output.txt
    python feishu_parser.py --file messages.txt --target "田中太郎" --output output.txt
"""

import json
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime


def parse_feishu_json(file_path: str, target_name: str) -> list[dict]:
    """Feishu 公式エクスポートの JSON フォーマットメッセージを解析"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = []

    # 複数の JSON 構造に対応
    if isinstance(data, list):
        raw_messages = data
    elif isinstance(data, dict):
        # data.messages や data.records 等のフィールド配下にある可能性
        raw_messages = (
            data.get("messages")
            or data.get("records")
            or data.get("data")
            or []
        )
    else:
        return []

    for msg in raw_messages:
        sender = (
            msg.get("sender_name")
            or msg.get("sender")
            or msg.get("from")
            or msg.get("user_name")
            or ""
        )
        content = (
            msg.get("content")
            or msg.get("text")
            or msg.get("message")
            or msg.get("body")
            or ""
        )
        timestamp = (
            msg.get("timestamp")
            or msg.get("create_time")
            or msg.get("time")
            or ""
        )

        # content はネスト構造の可能性あり
        if isinstance(content, dict):
            content = content.get("text") or content.get("content") or str(content)
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") if isinstance(c, dict) else str(c)
                for c in content
            )

        # フィルター：対象者が送信したメッセージのみ保持
        if target_name and target_name not in str(sender):
            continue

        # フィルター：システムメッセージ、スタンプ、取消メッセージをスキップ
        if not content or content.strip() in ["[图片]", "[文件]", "[撤回了一条消息]", "[语音]"]:
            continue

        messages.append({
            "sender": str(sender),
            "content": str(content).strip(),
            "timestamp": str(timestamp),
        })

    return messages


def parse_feishu_txt(file_path: str, target_name: str) -> list[dict]:
    """手動整理された TXT フォーマットのメッセージを解析（フォーマット：時間 送信者：内容）"""
    messages = []

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # マッチフォーマット：2024-01-01 10:00 田中太郎：メッセージ内容
    pattern = re.compile(
        r"^(?P<time>\d{4}[-/]\d{1,2}[-/]\d{1,2}[\s\d:]*)\s+(?P<sender>.+?)[:：]\s*(?P<content>.+)$"
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = pattern.match(line)
        if m:
            sender = m.group("sender").strip()
            content = m.group("content").strip()
            timestamp = m.group("time").strip()

            if target_name and target_name not in sender:
                continue
            if not content:
                continue

            messages.append({
                "sender": sender,
                "content": content,
                "timestamp": timestamp,
            })
        else:
            # フォーマットにマッチしない場合、対象者の名前が含まれているか確認
            if target_name and target_name in line:
                messages.append({
                    "sender": target_name,
                    "content": line,
                    "timestamp": "",
                })

    return messages


def extract_key_content(messages: list[dict]) -> dict:
    """
    メッセージを分類して抽出：
    - 長文メッセージ（>50文字）：意見、提案、技術判断を含む可能性
    - 判断系リプライ：「同意」「不行」「觉得」「建议」などのキーワードを含む
    - 日常コミュニケーション：その他のメッセージ
    """
    long_messages = []
    decision_messages = []
    daily_messages = []

    decision_keywords = [
        "同意", "不行", "觉得", "建议", "应该", "不应该", "可以", "不可以",
        "方案", "思路", "考虑", "决定", "确认", "拒绝", "推进", "暂缓",
        "没问题", "有问题", "风险", "评估", "判断"
    ]

    for msg in messages:
        content = msg["content"]

        if len(content) > 50:
            long_messages.append(msg)
        elif any(kw in content for kw in decision_keywords):
            decision_messages.append(msg)
        else:
            daily_messages.append(msg)

    return {
        "long_messages": long_messages,
        "decision_messages": decision_messages,
        "daily_messages": daily_messages,
        "total_count": len(messages),
    }


def format_output(target_name: str, extracted: dict) -> str:
    """AI 分析用にフォーマットして出力"""
    lines = [
        f"# Feishu メッセージ抽出結果",
        f"対象人物：{target_name}",
        f"メッセージ総数：{extracted['total_count']}",
        "",
        "---",
        "",
        "## 長文メッセージ（意見/提案系、最高ウェイト）",
        "",
    ]

    for msg in extracted["long_messages"]:
        ts = f"[{msg['timestamp']}] " if msg["timestamp"] else ""
        lines.append(f"{ts}{msg['content']}")
        lines.append("")

    lines += [
        "---",
        "",
        "## 判断系リプライ",
        "",
    ]

    for msg in extracted["decision_messages"]:
        ts = f"[{msg['timestamp']}] " if msg["timestamp"] else ""
        lines.append(f"{ts}{msg['content']}")
        lines.append("")

    lines += [
        "---",
        "",
        "## 日常コミュニケーション（スタイル参考）",
        "",
    ]

    # 日常メッセージは先頭 100 件のみ取得（長くなりすぎるのを防止）
    for msg in extracted["daily_messages"][:100]:
        ts = f"[{msg['timestamp']}] " if msg["timestamp"] else ""
        lines.append(f"{ts}{msg['content']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Feishu メッセージエクスポートファイルを解析")
    parser.add_argument("--file", required=True, help="入力ファイルパス（.json または .txt）")
    parser.add_argument("--target", required=True, help="対象人物の氏名（この人が送信したメッセージのみ抽出）")
    parser.add_argument("--output", default=None, help="出力ファイルパス（デフォルトは stdout に出力）")

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"エラー：ファイルが存在しません {file_path}", file=sys.stderr)
        sys.exit(1)

    # ファイルタイプに応じてパーサーを選択
    if file_path.suffix.lower() == ".json":
        messages = parse_feishu_json(str(file_path), args.target)
    else:
        messages = parse_feishu_txt(str(file_path), args.target)

    if not messages:
        print(f"警告：'{args.target}' が送信したメッセージが見つかりませんでした", file=sys.stderr)
        print("ヒント：対象の氏名がファイル内の送信者名と一致しているか確認してください", file=sys.stderr)

    extracted = extract_key_content(messages)
    output = format_output(args.target, extracted)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"{args.output} に出力しました。合計 {len(messages)} 件のメッセージ")
    else:
        print(output)


if __name__ == "__main__":
    main()
