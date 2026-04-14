#!/usr/bin/env python3
"""
メール解析ツール

対応フォーマット：
1. .eml ファイル（標準メールフォーマット）
2. .txt ファイル（プレーンテキストメール記録）
3. .mbox ファイル（複数メール集約ファイル）

使い方：
    python email_parser.py --file emails.eml --target "tanaka@company.com" --output output.txt
    python email_parser.py --file inbox.mbox --target "田中太郎" --output output.txt
"""

import email
import email.policy
import mailbox
import re
import sys
import argparse
from pathlib import Path
from email.header import decode_header
from html.parser import HTMLParser


class HTMLTextExtractor(HTMLParser):
    """HTML メール内容からプレーンテキストを抽出"""

    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "br", "div", "tr"):
            self.result.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.result.append(data)

    def get_text(self):
        return re.sub(r"\n{3,}", "\n\n", "".join(self.result)).strip()


def decode_mime_str(s: str) -> str:
    """MIME エンコードされたメールヘッダーフィールドをデコード"""
    if not s:
        return ""
    parts = decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            charset = charset or "utf-8"
            try:
                result.append(part.decode(charset, errors="replace"))
            except Exception:
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def extract_email_body(msg) -> str:
    """メールオブジェクトから本文テキストを抽出"""
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in disposition:
                continue

            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                try:
                    body = payload.decode(charset, errors="replace")
                    break
                except Exception:
                    body = payload.decode("utf-8", errors="replace")
                    break

            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                try:
                    html = payload.decode(charset, errors="replace")
                except Exception:
                    html = payload.decode("utf-8", errors="replace")
                extractor = HTMLTextExtractor()
                extractor.feed(html)
                body = extractor.get_text()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                body = payload.decode(charset, errors="replace")
            except Exception:
                body = payload.decode("utf-8", errors="replace")

    # 引用内容のクリーンアップ（Re: 時の元メッセージ引用）
    body = re.sub(r"\n>.*", "", body)
    body = re.sub(r"\n-{3,}.*?原始邮件.*?\n", "\n", body, flags=re.DOTALL)
    body = re.sub(r"\n_{3,}\n.*", "", body, flags=re.DOTALL)

    return body.strip()


def is_from_target(from_field: str, target: str) -> bool:
    """メールが対象者から送信されたものかを判定"""
    from_str = decode_mime_str(from_field).lower()
    target_lower = target.lower()
    return target_lower in from_str


def parse_eml_file(file_path: str, target: str) -> list[dict]:
    """単一の .eml ファイルを解析"""
    with open(file_path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)

    from_field = str(msg.get("From", ""))
    if not is_from_target(from_field, target):
        return []

    subject = decode_mime_str(str(msg.get("Subject", "")))
    date = str(msg.get("Date", ""))
    body = extract_email_body(msg)

    if not body:
        return []

    return [{
        "from": decode_mime_str(from_field),
        "subject": subject,
        "date": date,
        "body": body,
    }]


def parse_mbox_file(file_path: str, target: str) -> list[dict]:
    """mbox ファイルを解析（複数メール集約ファイル）"""
    results = []
    mbox = mailbox.mbox(file_path)

    for msg in mbox:
        from_field = str(msg.get("From", ""))
        if not is_from_target(from_field, target):
            continue

        subject = decode_mime_str(str(msg.get("Subject", "")))
        date = str(msg.get("Date", ""))
        body = extract_email_body(msg)

        if not body:
            continue

        results.append({
            "from": decode_mime_str(from_field),
            "subject": subject,
            "date": date,
            "body": body,
        })

    return results


def parse_txt_file(file_path: str, target: str) -> list[dict]:
    """
    プレーンテキスト形式のメール記録を解析
    以下のようなシンプルな区切りフォーマットに対応：
    From: xxx
    Subject: xxx
    Date: xxx
    ---
    本文内容
    ===
    """
    results = []

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 区切り文字で複数メールを分割
    emails_raw = re.split(r"\n={3,}\n|\n-{3,}\n(?=From:)", content)

    for raw in emails_raw:
        from_match = re.search(r"^From:\s*(.+)$", raw, re.MULTILINE)
        subject_match = re.search(r"^Subject:\s*(.+)$", raw, re.MULTILINE)
        date_match = re.search(r"^Date:\s*(.+)$", raw, re.MULTILINE)

        from_field = from_match.group(1).strip() if from_match else ""
        if not is_from_target(from_field, target):
            continue

        # 本文を抽出（ヘッダーフィールドを除去した内容）
        body = re.sub(r"^(From|To|Subject|Date|CC|BCC):.*\n?", "", raw, flags=re.MULTILINE)
        body = body.strip()

        if not body:
            continue

        results.append({
            "from": from_field,
            "subject": subject_match.group(1).strip() if subject_match else "",
            "date": date_match.group(1).strip() if date_match else "",
            "body": body,
        })

    return results


def classify_emails(emails: list[dict]) -> dict:
    """
    メールを内容別に分類：
    - 長文メール（本文 > 200 文字）：技術提案、意見表明
    - 判断系：明確な判断を含むメール
    - 日常コミュニケーション：短いメール
    """
    long_emails = []
    decision_emails = []
    daily_emails = []

    decision_keywords = [
        "同意", "不同意", "建议", "方案", "觉得", "应该", "决定", "确认",
        "approve", "reject", "lgtm", "suggest", "recommend", "think",
        "我的看法", "我认为", "我觉得", "需要", "必须", "不需要"
    ]

    for e in emails:
        body = e["body"]

        if len(body) > 200:
            long_emails.append(e)
        elif any(kw in body.lower() for kw in decision_keywords):
            decision_emails.append(e)
        else:
            daily_emails.append(e)

    return {
        "long_emails": long_emails,
        "decision_emails": decision_emails,
        "daily_emails": daily_emails,
        "total_count": len(emails),
    }


def format_output(target: str, classified: dict) -> str:
    """AI 分析用にフォーマットして出力"""
    lines = [
        f"# メール抽出結果",
        f"対象人物：{target}",
        f"メール総数：{classified['total_count']}",
        "",
        "---",
        "",
        "## 長文メール（技術提案/意見系、最高ウェイト）",
        "",
    ]

    for e in classified["long_emails"]:
        lines.append(f"**件名：{e['subject']}** [{e['date']}]")
        lines.append(e["body"])
        lines.append("")
        lines.append("---")
        lines.append("")

    lines += [
        "## 判断系メール",
        "",
    ]

    for e in classified["decision_emails"]:
        lines.append(f"**件名：{e['subject']}** [{e['date']}]")
        lines.append(e["body"])
        lines.append("")

    lines += [
        "---",
        "",
        "## 日常コミュニケーション（スタイル参考）",
        "",
    ]

    for e in classified["daily_emails"][:30]:
        lines.append(f"**{e['subject']}**：{e['body'][:200]}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="メールファイルを解析し、対象者が送信したメールを抽出")
    parser.add_argument("--file", required=True, help="入力ファイルパス（.eml / .mbox / .txt）")
    parser.add_argument("--target", required=True, help="対象人物（メールアドレスまたは氏名）")
    parser.add_argument("--output", default=None, help="出力ファイルパス（デフォルトは stdout に出力）")

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"エラー：ファイルが存在しません {file_path}", file=sys.stderr)
        sys.exit(1)

    suffix = file_path.suffix.lower()

    if suffix == ".eml":
        emails = parse_eml_file(str(file_path), args.target)
    elif suffix == ".mbox":
        emails = parse_mbox_file(str(file_path), args.target)
    else:
        emails = parse_txt_file(str(file_path), args.target)

    if not emails:
        print(f"警告：'{args.target}' からのメールが見つかりませんでした", file=sys.stderr)
        print("ヒント：対象の名前/メールアドレスがファイル内の From フィールドと一致しているか確認してください", file=sys.stderr)

    classified = classify_emails(emails)
    output = format_output(args.target, classified)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"{args.output} に出力しました。合計 {len(emails)} 通のメール")
    else:
        print(output)


if __name__ == "__main__":
    main()
