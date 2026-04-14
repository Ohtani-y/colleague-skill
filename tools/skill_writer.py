#!/usr/bin/env python3
"""
Skill 文件写入器

负责将生成的 work.md、persona.md 写入到正确的目录结构，
并生成 meta.json 和完整的 SKILL.md。

用法：
    python3 skill_writer.py --action create --slug zhangsan --meta meta.json \
        --work work_content.md --persona persona_content.md \
        --base-dir ./colleagues

    python3 skill_writer.py --action update --slug zhangsan \
        --work-patch work_patch.md --persona-patch persona_patch.md \
        --base-dir ./colleagues

    python3 skill_writer.py --action list --base-dir ./colleagues
"""

from __future__ import annotations

import json
import shutil
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


SKILL_MD_TEMPLATE = """\
---
name: colleague_{slug}
description: {name}，{identity}
user-invocable: true
---

# {name}

{identity}

---

## PART A：工作能力

{work_content}

---

## PART B：人物性格

{persona_content}

---

## 运行规则

接收到任何任务或问题时：

1. **先由 PART B 判断**：你会不会接这个任务？用什么态度接？
2. **再由 PART A 执行**：用你的技术能力和工作方法完成任务
3. **输出时保持 PART B 的表达风格**：你说话的方式、用词习惯、句式

**PART B 的 Layer 0 规则永远优先，任何情况下不得违背。**
"""


def slugify(name: str) -> str:
    """
    氏名を slug に変換。
    pypinyin（インストール済みの場合）を優先的に試行し、なければシンプルな処理にフォールバック。
    """
    # pypinyin でピンイン変換を試行
    try:
        from pypinyin import lazy_pinyin
        parts = lazy_pinyin(name)
        slug = "_".join(parts)
    except ImportError:
        # フォールバック：ASCII 英数字を保持、中国語文字は除去
        import unicodedata
        result = []
        for char in name.lower():
            cat = unicodedata.category(char)
            if char.isascii() and (char.isalnum() or char in ("-", "_")):
                result.append(char)
            elif char == " ":
                result.append("_")
            # 中国語文字はスキップ（pypinyin がない場合は変換不可）
        slug = "".join(result)

    # クリーンアップ：連続アンダースコアと先頭末尾のアンダースコアを除去
    import re
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug if slug else "colleague"


def build_identity_string(meta: dict) -> str:
    """meta からアイデンティティ説明文字列を構築"""
    profile = meta.get("profile", {})
    parts = []

    company = profile.get("company", "")
    level = profile.get("level", "")
    role = profile.get("role", "")

    if company:
        parts.append(company)
    if level:
        parts.append(level)
    if role:
        parts.append(role)

    identity = " ".join(parts) if parts else "同僚"

    mbti = profile.get("mbti", "")
    if mbti:
        identity += f"，MBTI {mbti}"

    return identity


def create_skill(
    base_dir: Path,
    slug: str,
    meta: dict,
    work_content: str,
    persona_content: str,
) -> Path:
    """新しい同僚 Skill ディレクトリ構造を作成"""

    skill_dir = base_dir / slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    # サブディレクトリを作成
    (skill_dir / "versions").mkdir(exist_ok=True)
    (skill_dir / "knowledge" / "docs").mkdir(parents=True, exist_ok=True)
    (skill_dir / "knowledge" / "messages").mkdir(parents=True, exist_ok=True)
    (skill_dir / "knowledge" / "emails").mkdir(parents=True, exist_ok=True)

    # work.md を書き込み
    (skill_dir / "work.md").write_text(work_content, encoding="utf-8")

    # persona.md を書き込み
    (skill_dir / "persona.md").write_text(persona_content, encoding="utf-8")

    # SKILL.md を生成して書き込み
    name = meta.get("name", slug)
    identity = build_identity_string(meta)

    skill_md = SKILL_MD_TEMPLATE.format(
        slug=slug,
        name=name,
        identity=identity,
        work_content=work_content,
        persona_content=persona_content,
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # work-only skill を書き込み
    work_only = (
        f"---\nname: colleague_{slug}_work\n"
        f"description: {name} 的工作能力（仅 Work，无 Persona）\n"
        f"user-invocable: true\n---\n\n{work_content}\n"
    )
    (skill_dir / "work_skill.md").write_text(work_only, encoding="utf-8")

    # persona-only skill を書き込み
    persona_only = (
        f"---\nname: colleague_{slug}_persona\n"
        f"description: {name} 的人物性格（仅 Persona，无工作能力）\n"
        f"user-invocable: true\n---\n\n{persona_content}\n"
    )
    (skill_dir / "persona_skill.md").write_text(persona_only, encoding="utf-8")

    # meta.json を書き込み
    now = datetime.now(timezone.utc).isoformat()
    meta["slug"] = slug
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    meta["version"] = "v1"
    meta.setdefault("corrections_count", 0)

    (skill_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return skill_dir


def update_skill(
    skill_dir: Path,
    work_patch: Optional[str] = None,
    persona_patch: Optional[str] = None,
    correction: Optional[dict] = None,
) -> str:
    """既存の Skill を更新。現在のバージョンをアーカイブしてから更新を書き込み"""

    meta_path = skill_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    current_version = meta.get("version", "v1")
    try:
        version_num = int(current_version.lstrip("v").split("_")[0]) + 1
    except ValueError:
        version_num = 2
    new_version = f"v{version_num}"

    # 現在のバージョンをアーカイブ
    version_dir = skill_dir / "versions" / current_version
    version_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("SKILL.md", "work.md", "persona.md"):
        src = skill_dir / fname
        if src.exists():
            shutil.copy2(src, version_dir / fname)

    # work patch を適用
    if work_patch:
        current_work = (skill_dir / "work.md").read_text(encoding="utf-8")
        new_work = current_work + "\n\n" + work_patch
        (skill_dir / "work.md").write_text(new_work, encoding="utf-8")

    # persona patch または correction を適用
    if persona_patch or correction:
        current_persona = (skill_dir / "persona.md").read_text(encoding="utf-8")

        if correction:
            correction_line = (
                f"\n- [{correction.get('scene', '通用')}] "
                f"不应该 {correction['wrong']}，应该 {correction['correct']}"
            )
            target = "## Correction 记录"
            if target in current_persona:
                insert_pos = current_persona.index(target) + len(target)
                # 直後の空行と「記録なし」プレースホルダー行をスキップ
                rest = current_persona[insert_pos:]
                skip = "\n\n（暂无记录）"
                if rest.startswith(skip):
                    rest = rest[len(skip):]
                new_persona = current_persona[:insert_pos] + correction_line + rest
            else:
                new_persona = (
                    current_persona
                    + f"\n\n## Correction 记录\n{correction_line}\n"
                )
            meta["corrections_count"] = meta.get("corrections_count", 0) + 1
        else:
            new_persona = current_persona + "\n\n" + persona_patch

        (skill_dir / "persona.md").write_text(new_persona, encoding="utf-8")

    # SKILL.md を再生成
    work_content = (skill_dir / "work.md").read_text(encoding="utf-8")
    persona_content = (skill_dir / "persona.md").read_text(encoding="utf-8")
    name = meta.get("name", skill_dir.name)
    identity = build_identity_string(meta)

    skill_md = SKILL_MD_TEMPLATE.format(
        slug=skill_dir.name,
        name=name,
        identity=identity,
        work_content=work_content,
        persona_content=persona_content,
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # meta を更新
    meta["version"] = new_version
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return new_version


def list_colleagues(base_dir: Path) -> list:
    """作成済みの全同僚 Skill を一覧表示"""
    colleagues = []

    if not base_dir.exists():
        return colleagues

    for skill_dir in sorted(base_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        meta_path = skill_dir / "meta.json"
        if not meta_path.exists():
            continue

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        colleagues.append({
            "slug": meta.get("slug", skill_dir.name),
            "name": meta.get("name", skill_dir.name),
            "identity": build_identity_string(meta),
            "version": meta.get("version", "v1"),
            "updated_at": meta.get("updated_at", ""),
            "corrections_count": meta.get("corrections_count", 0),
        })

    return colleagues


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill ファイルライター")
    parser.add_argument("--action", required=True, choices=["create", "update", "list"])
    parser.add_argument("--slug", help="同僚の slug（ディレクトリ名に使用）")
    parser.add_argument("--name", help="同僚の氏名")
    parser.add_argument("--meta", help="meta.json ファイルパス")
    parser.add_argument("--work", help="work.md コンテンツファイルパス")
    parser.add_argument("--persona", help="persona.md コンテンツファイルパス")
    parser.add_argument("--work-patch", help="work.md 差分更新コンテンツファイルパス")
    parser.add_argument("--persona-patch", help="persona.md 差分更新コンテンツファイルパス")
    parser.add_argument(
        "--base-dir",
        default="./colleagues",
        help="同僚 Skill ルートディレクトリ（デフォルト：./colleagues）",
    )

    args = parser.parse_args()
    base_dir = Path(args.base_dir).expanduser()

    if args.action == "list":
        colleagues = list_colleagues(base_dir)
        if not colleagues:
            print("作成済みの同僚 Skill はありません")
        else:
            print(f"{len(colleagues)} 件の同僚 Skill が作成済み：\n")
            for c in colleagues:
                updated = c["updated_at"][:10] if c["updated_at"] else "不明"
                print(f"  [{c['slug']}]  {c['name']} — {c['identity']}")
                print(f"    バージョン: {c['version']}  修正回数: {c['corrections_count']}  更新: {updated}")
                print()

    elif args.action == "create":
        if not args.slug and not args.name:
            print("エラー：create 操作には --slug または --name が必要です", file=sys.stderr)
            sys.exit(1)

        meta: dict = {}
        if args.meta:
            meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
        if args.name:
            meta["name"] = args.name

        slug = args.slug or slugify(meta.get("name", "colleague"))

        work_content = ""
        if args.work:
            work_content = Path(args.work).read_text(encoding="utf-8")

        persona_content = ""
        if args.persona:
            persona_content = Path(args.persona).read_text(encoding="utf-8")

        skill_dir = create_skill(base_dir, slug, meta, work_content, persona_content)
        print(f"✅ Skill を作成しました：{skill_dir}")
        print(f"   トリガーワード：/{slug}")

    elif args.action == "update":
        if not args.slug:
            print("エラー：update 操作には --slug が必要です", file=sys.stderr)
            sys.exit(1)

        skill_dir = base_dir / args.slug
        if not skill_dir.exists():
            print(f"エラー：Skill ディレクトリが見つかりません {skill_dir}", file=sys.stderr)
            sys.exit(1)

        work_patch = Path(args.work_patch).read_text(encoding="utf-8") if args.work_patch else None
        persona_patch = Path(args.persona_patch).read_text(encoding="utf-8") if args.persona_patch else None

        new_version = update_skill(skill_dir, work_patch, persona_patch)
        print(f"✅ Skill を {new_version} に更新しました：{skill_dir}")


if __name__ == "__main__":
    main()
