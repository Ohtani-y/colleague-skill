#!/usr/bin/env python3
"""
バージョンマネージャー

Skill ファイルのバージョンアーカイブとロールバックを担当。

使い方：
    python version_manager.py --action list --slug tanaka --base-dir ~/.openclaw/...
    python version_manager.py --action backup --slug tanaka --base-dir ~/.openclaw/...
    python version_manager.py --action rollback --slug tanaka --version v2 --base-dir ~/.openclaw/...
"""

from __future__ import annotations

import json
import shutil
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

MAX_VERSIONS = 10  # 最大保持バージョン数


def list_versions(skill_dir: Path) -> list:
    """全履歴バージョンを一覧表示"""
    versions_dir = skill_dir / "versions"
    if not versions_dir.exists():
        return []

    versions = []
    for v_dir in sorted(versions_dir.iterdir()):
        if not v_dir.is_dir():
            continue

        # ディレクトリ名からバージョン番号を解析
        version_name = v_dir.name

        # アーカイブ時間を取得（ディレクトリの更新時間で近似）
        mtime = v_dir.stat().st_mtime
        archived_at = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

        # ファイルを集計
        files = [f.name for f in v_dir.iterdir() if f.is_file()]

        versions.append({
            "version": version_name,
            "archived_at": archived_at,
            "files": files,
            "path": str(v_dir),
        })

    return versions


def rollback(skill_dir: Path, target_version: str) -> bool:
    """指定バージョンにロールバック"""
    version_dir = skill_dir / "versions" / target_version

    if not version_dir.exists():
        print(f"エラー：バージョン {target_version} が存在しません", file=sys.stderr)
        return False

    # まず現在のバージョンをアーカイブ
    meta_path = skill_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        current_version = meta.get("version", "v?")
        backup_dir = skill_dir / "versions" / f"{current_version}_before_rollback"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for fname in ("SKILL.md", "work.md", "persona.md"):
            src = skill_dir / fname
            if src.exists():
                shutil.copy2(src, backup_dir / fname)

    # 対象バージョンからファイルを復元
    restored_files = []
    for fname in ("SKILL.md", "work.md", "persona.md"):
        src = version_dir / fname
        if src.exists():
            shutil.copy2(src, skill_dir / fname)
            restored_files.append(fname)

    # meta を更新
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["version"] = target_version + "_restored"
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        meta["rollback_from"] = current_version
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{target_version} にロールバックしました。復元ファイル：{', '.join(restored_files)}")
    return True


def backup_current_version(skill_dir: Path) -> bool:
    """現在のバージョンを versions/ ディレクトリにアーカイブ"""
    meta_path = skill_dir / "meta.json"
    if not meta_path.exists():
        print(f"エラー：meta.json が見つかりません。現在のバージョン番号を特定できません", file=sys.stderr)
        return False

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    current_version = meta.get("version", "v1")

    version_dir = skill_dir / "versions" / current_version
    version_dir.mkdir(parents=True, exist_ok=True)

    backed_up = []
    for fname in ("SKILL.md", "work.md", "persona.md"):
        src = skill_dir / fname
        if src.exists():
            shutil.copy2(src, version_dir / fname)
            backed_up.append(fname)

    if backed_up:
        print(f"バージョン {current_version} をアーカイブしました。ファイル：{', '.join(backed_up)}")
    else:
        print(f"警告：{current_version} にアーカイブ可能なファイルがありません")

    return True


def cleanup_old_versions(skill_dir: Path, max_versions: int = MAX_VERSIONS):
    """制限を超えた古いバージョンをクリーンアップ"""
    versions_dir = skill_dir / "versions"
    if not versions_dir.exists():
        return

    # バージョン番号順にソートし、最新の max_versions 件を保持
    version_dirs = sorted(
        [d for d in versions_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
    )

    to_delete = version_dirs[:-max_versions] if len(version_dirs) > max_versions else []

    for old_dir in to_delete:
        shutil.rmtree(old_dir)
        print(f"古いバージョンをクリーンアップしました：{old_dir.name}")


def main():
    parser = argparse.ArgumentParser(description="Skill バージョンマネージャー")
    parser.add_argument("--action", required=True, choices=["list", "backup", "rollback", "cleanup"])
    parser.add_argument("--slug", required=True, help="同僚の slug")
    parser.add_argument("--version", help="対象バージョン番号（rollback 時に使用）")
    parser.add_argument(
        "--base-dir",
        default="~/.openclaw/workspace/skills/colleagues",
        help="同僚 Skill ルートディレクトリ",
    )

    args = parser.parse_args()
    base_dir = Path(args.base_dir).expanduser()
    skill_dir = base_dir / args.slug

    if not skill_dir.exists():
        print(f"エラー：Skill ディレクトリが見つかりません {skill_dir}", file=sys.stderr)
        sys.exit(1)

    if args.action == "list":
        versions = list_versions(skill_dir)
        if not versions:
            print(f"{args.slug} の履歴バージョンはありません")
        else:
            print(f"{args.slug} の履歴バージョン：\n")
            for v in versions:
                print(f"  {v['version']}  アーカイブ日時: {v['archived_at']}  ファイル: {', '.join(v['files'])}")

    elif args.action == "backup":
        backup_current_version(skill_dir)

    elif args.action == "rollback":
        if not args.version:
            print("エラー：rollback 操作には --version が必要です", file=sys.stderr)
            sys.exit(1)
        rollback(skill_dir, args.version)

    elif args.action == "cleanup":
        cleanup_old_versions(skill_dir)
        print("クリーンアップ完了")


if __name__ == "__main__":
    main()
