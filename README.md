<div align="center">

# colleague.skill

> *"お前らAI屋は裏切り者だ — フロントエンドはもう殺した、次はバックエンド、QA、インフラ、セキュリティ、チップ設計、そしていずれは自分たち自身と全人類を滅ぼすつもりだろう"*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![AgentSkills](https://img.shields.io/badge/AgentSkills-Standard-green)](https://agentskills.io)

[![Discord](https://img.shields.io/badge/Discord-Join%20Community-5865F2?logo=discord&logoColor=white)](https://discord.gg/aRjmJBdK)

<br>

同僚が辞めた、メンテされないドキュメントの山だけが残った？<br>
インターンが去った、空のデスクと中途半端なプロジェクトだけが残った？<br>
メンターが卒業した、すべてのコンテキストと経験を持って行ってしまった？<br>
パートナーが異動した、せっかく築いたケミストリーが一晩でリセットされた？<br>
前任者が引き継いだ、3年分の知識を3ページに凝縮しようとしていた？<br>

**冷たい別れを温かい Skill に変えよう — サイバー不死へようこそ！**

<br>

ソース資料（Feishu メッセージ、DingTalk ドキュメント、Slack メッセージ、メール、スクリーンショット）<br>
＋ その人に対するあなた自身の主観的な説明を入力するだけで<br>
**本人のように動く AI Skill** が生成されます

[対応データソース](#対応データソース) · [インストール](#インストール) · [使い方](#使い方) · [デモ](#デモ) · [詳細インストール](INSTALL.md) · [💬 Discord](https://discord.gg/aRjmJBdK)

[**中文**](docs/lang/README_ZH.md) · [**Español**](docs/lang/README_ES.md) · [**Deutsch**](docs/lang/README_DE.md) · [**日本語**](docs/lang/README_JA.md) · [**Русский**](docs/lang/README_RU.md) · [**Português**](docs/lang/README_PT.md)

</div>

---

> 🆕 **2026.04.13 更新** — **dot-skill ロードマップ公開！** colleague.skill は **dot-skill** へと進化します — 同僚だけでなく、誰でも蒸留可能に。マルチモーダル出力、Skill エコシステムなど、続々登場予定。
>
> 👉 **[ロードマップ全文を読む](ROADMAP.md)** · **[💬 Discord](https://discord.gg/aRjmJBdK)**
>
> Issue の整理、Milestone の追加、[公開プロジェクトボード](https://github.com/users/titanwings/projects/1)の設置も完了しました。コミュニティからの貢献を歓迎します — `good-first-issue` ラベルをチェックしてください！

> 🆕 **2026.04.07 更新** — コミュニティの dot-skill リミックスへの熱意が素晴らしいです！コミュニティギャラリーを作りました — PR 歓迎！
>
> どんな Skill やメタ Skill でもシェアできます。トラフィックはあなた自身の GitHub リポジトリに直接流れます。仲介者なし。
>
> 👉 **[titanwings.github.io/colleague-skill-site](https://titanwings.github.io/colleague-skill-site/)**
>
> 掲載中: 户晨风.skill · 峰哥亡命天涯.skill · 罗翔.skill ほか

---

作成者: [@titanwings](https://github.com/titanwings) | Powered by Shanghai AI Lab · AI Safety Center

## 対応データソース

> これはまだ colleague.skill のベータ版です — 今後さらに多くのソースに対応予定です。お楽しみに！

| ソース | メッセージ | ドキュメント / Wiki | スプレッドシート | 備考 |
|--------|:--------:|:-----------:|:------------:|-------|
| Feishu（自動） | ✅ API | ✅ | ✅ | 名前を入力するだけで完全自動 |
| DingTalk（自動） | ⚠️ ブラウザ | ✅ | ✅ | DingTalk API はメッセージ履歴に非対応 |
| Slack（自動） | ✅ API | — | — | 管理者による Bot インストールが必要。無料プランは90日間制限 |
| WeChat チャット履歴 | ✅ SQLite | — | — | 現在不安定、以下のオープンソースツールの使用を推奨 |
| PDF | — | ✅ | — | 手動アップロード |
| 画像 / スクリーンショット | ✅ | — | — | 手動アップロード |
| Feishu JSON エクスポート | ✅ | ✅ | — | 手動アップロード |
| メール `.eml` / `.mbox` | ✅ | — | — | 手動アップロード |
| Markdown | ✅ | ✅ | — | 手動アップロード |
| テキスト直接貼り付け | ✅ | — | — | 手動入力 |

### 推奨 WeChat チャットエクスポートツール

これらは独立したオープンソースプロジェクトです。本プロジェクトにそれらのコードは含まれていませんが、パーサーはそれらのエクスポート形式と互換性があります。WeChat の自動復号は現在不安定なため、以下のオープンソースツールでチャット履歴をエクスポートし、本プロジェクトに貼り付けまたはインポートすることを推奨します：

| ツール | プラットフォーム | 説明 |
|------|----------|-------------|
| [WeChatMsg](https://github.com/LC044/WeChatMsg) | Windows | WeChat チャット履歴エクスポート、複数形式に対応 |
| [PyWxDump](https://github.com/xaoyaoo/PyWxDump) | Windows | WeChat データベース復号・エクスポート |
| [留痕 (Liuhen)](https://github.com/greyovo/留痕) | macOS | WeChat チャット履歴エクスポート（Mac ユーザー推奨） |

> ツール推薦: [@therealXiaomanChu](https://github.com/therealXiaomanChu)。すべてのオープンソース作者に感謝します — 共にサイバー不死を目指しましょう！

---

## インストール

### Claude Code

> **重要**: Claude Code は **Git リポジトリルート** の `.claude/skills/` からスキルを検索します。正しい場所で実行してください。

```bash
# 現在のプロジェクトにインストール（Git リポジトリルートで実行）
mkdir -p .claude/skills
git clone https://github.com/titanwings/colleague-skill .claude/skills/create-colleague

# またはグローバルにインストール（すべてのプロジェクトで利用可能）
git clone https://github.com/titanwings/colleague-skill ~/.claude/skills/create-colleague
```

### OpenClaw

```bash
git clone https://github.com/titanwings/colleague-skill ~/.openclaw/workspace/skills/create-colleague
```

### 依存関係（オプション）

```bash
pip3 install -r requirements.txt
```

> Feishu/DingTalk/Slack 自動収集には App の認証情報が必要です。詳細は [INSTALL.md](INSTALL.md) を参照してください。

---

## 使い方

Claude Code で以下を入力します：

```
/create-colleague
```

プロンプトに従って操作します：エイリアスを入力、会社/レベル（例: `ByteDance L2-1 バックエンドエンジニア`）、性格タグを選択し、データソースを選びます。すべてのフィールドはスキップ可能です — 説明文だけでも Skill を生成できます。

作成後は `/{slug}` で同僚 Skill を呼び出せます。

### コマンド

| コマンド | 説明 |
|---------|-------------|
| `/list-colleagues` | すべての同僚 Skill を一覧表示 |
| `/{slug}` | フル Skill を呼び出し（ペルソナ + ワーク） |
| `/{slug}-work` | ワーク能力のみ |
| `/{slug}-persona` | ペルソナのみ |
| `/colleague-rollback {slug} {version}` | 以前のバージョンにロールバック |
| `/delete-colleague {slug}` | 削除 |

---

## デモ

> 入力: `ByteDance L2-1 バックエンドエンジニア、INTJ、責任転嫁型、ByteDance スタイル`

**シナリオ 1: コードレビュー**

```
User            ❯ この API 設計をレビューしてくれる？

colleague.skill ❯ ちょっと待って — 影響範囲は？コンテキストの説明がないんだけど。
                  （読んだ後）N+1 クエリ、直して。標準の
                  {code, message, data} レスポンス形式を使え。仕様だから、
                  理由は聞くな。
```

**シナリオ 2: 責任転嫁**

```
User            ❯ このバグ、あなたが入れたんじゃない？

colleague.skill ❯ タイムラインは合ってる？その機能は複数箇所に影響してたし、
                  他にも変更が入ってたよ。
```

---

## 機能

### 生成される Skill の構造

各同僚 Skill は連携して動作する2つのパートで構成されます：

| パート | 内容 |
|------|---------|
| **パート A — ワーク Skill** | システム、技術標準、ワークフロー、経験 |
| **パート B — ペルソナ** | 5層の性格構造：ハードルール → アイデンティティ → 表現 → 意思決定 → 対人関係 |

実行フロー: `タスク受信 → ペルソナが態度を決定 → ワーク Skill が実行 → その人の声で出力`

### 対応タグ

**性格**: 責任感が強い · 責任転嫁型 · 完璧主義者 · とりあえず動けばOK · 先延ばし型 · PUA マスター · 社内政治家 · 上司アピール型 · 受動攻撃型 · 手のひら返し型 · 寡黙 · 既読スルー …

**企業文化**: ByteDance スタイル · Alibaba スタイル · Tencent スタイル · Huawei スタイル · Baidu スタイル · Meituan スタイル · ファーストプリンシプル · OKR 至上主義 · 大企業パイプライン · スタートアップモード

**レベル**: ByteDance 2-1~3-3+ · Alibaba P5~P11 · Tencent T1~T4 · Baidu T5~T9 · Meituan P4~P8 · Huawei 13~21 · NetEase · JD · Xiaomi …

### 進化

- **ファイル追加** → 差分を自動分析 → 関連セクションにマージ、既存の結論は上書きしない
- **会話での修正** → 「あの人はそんなことしない、本当は xxx なはず」と言えば → 修正レイヤーに書き込まれ、即座に反映
- **バージョン管理** → 更新のたびに自動アーカイブ、任意の過去バージョンにロールバック可能

---

## プロジェクト構造

本プロジェクトは [AgentSkills](https://agentskills.io) オープン標準に準拠しています。リポジトリ全体がスキルディレクトリです：

```
create-colleague/
├── SKILL.md              # Skill エントリポイント（公式フロントマター）
├── prompts/              # プロンプトテンプレート
│   ├── intake.md         #   対話型情報収集
│   ├── work_analyzer.md  #   ワーク能力抽出
│   ├── persona_analyzer.md #  性格抽出（タグ翻訳付き）
│   ├── work_builder.md   #   work.md 生成テンプレート
│   ├── persona_builder.md #   persona.md 5層構造
│   ├── merger.md         #   増分マージロジック
│   └── correction_handler.md # 会話修正ハンドラー
├── tools/                # Python ツール
│   ├── feishu_auto_collector.py  # Feishu 自動コレクター
│   ├── feishu_browser.py         # Feishu ブラウザ方式
│   ├── feishu_mcp_client.py      # Feishu MCP 方式
│   ├── dingtalk_auto_collector.py # DingTalk 自動コレクター
│   ├── slack_auto_collector.py   # Slack 自動コレクター
│   ├── email_parser.py           # メールパーサー
│   ├── skill_writer.py           # Skill ファイル管理
│   └── version_manager.py        # バージョンアーカイブ＆ロールバック
├── colleagues/           # 生成された同僚 Skill（gitignore 対象）
├── docs/PRD.md
├── requirements.txt
└── LICENSE
```

---

## 注意事項

- **ソース資料の品質 = Skill の品質**: チャットログ + 長文ドキュメント > 手動の説明のみ
- 優先的に収集すべきもの：**本人が書いた**長文 > **意思決定に関する返信** > カジュアルなメッセージ
- Feishu 自動収集には、App ボットを関連するグループチャットに追加する必要があります
- これはまだデモ版です — バグを見つけたら Issue を立ててください！

---
### 📄 テクニカルレポート

> **[Colleague.Skill: Automated AI Skill Generation via Expert Knowledge Distillation](colleague_skill.pdf)**
>
> colleague.skill のシステム設計を詳述した論文を執筆しました — 2パート構成（ワーク Skill + ペルソナ）、マルチソースデータ収集、Skill の生成・進化メカニズム、実際のシナリオでの評価結果について解説しています。興味のある方はぜひご覧ください！

---

## Star History

<a href="https://www.star-history.com/?repos=titanwings%2Fcolleague-skill&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=titanwings/colleague-skill&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=titanwings/colleague-skill&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=titanwings/colleague-skill&type=date&legend=top-left" />
 </picture>
</a>

---

<div align="center">

MIT License © [titanwings](https://github.com/titanwings)

</div>
