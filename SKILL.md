---
name: create-colleague
description: "同僚をAI Skillに蒸留する。Feishu/DingTalkのデータを自動収集し、Work Skill + Personaを生成、継続的な進化をサポート。"
argument-hint: "[colleague-name-or-slug]"
version: "1.0.0"
user-invocable: true
allowed-tools: Read, Write, Edit, Bash
---

# 同僚.skill クリエイター（Claude Code 版）

## トリガー条件

ユーザーが以下のいずれかを入力したとき起動：
- `/create-colleague`
- 「同僚のskillを作って」
- 「同僚を蒸留したい」
- 「新しい同僚」
- 「XXのskillを作って」

既存の同僚 Skill に対してユーザーが以下を入力したとき、進化モードに入る：
- 「新しいファイルがある」/「追加」
- 「違う」/「この人はこんなことしない」/「この人はこうあるべき」
- `/update-colleague {slug}`

ユーザーが `/list-colleagues` と入力したとき、生成済みの全同僚を一覧表示する。

---

## ツール使用ルール

本 Skill は Claude Code 環境で動作し、以下のツールを使用する：

| タスク | 使用ツール |
|--------|-----------|
| PDFドキュメントの読み取り | `Read` ツール（PDF ネイティブ対応） |
| 画像スクリーンショットの読み取り | `Read` ツール（画像ネイティブ対応） |
| MD/TXT ファイルの読み取り | `Read` ツール |
| Feishu（飛書）メッセージ JSON エクスポートの解析 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/feishu_parser.py` |
| Feishu 全自動収集（推奨） | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/feishu_auto_collector.py` |
| Feishu ドキュメント（ブラウザログイン状態） | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/feishu_browser.py` |
| Feishu ドキュメント（MCP App Token） | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/feishu_mcp_client.py` |
| DingTalk 全自動収集 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/dingtalk_auto_collector.py` |
| メール .eml/.mbox の解析 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/email_parser.py` |
| Skill ファイルの書き込み/更新 | `Write` / `Edit` ツール |
| バージョン管理 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py` |
| 既存 Skill の一覧表示 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/skill_writer.py --action list` |

**ベースディレクトリ**：Skill ファイルは `./colleagues/{slug}/`（本プロジェクトディレクトリからの相対パス）に書き込まれる。
グローバルパスに変更する場合は `--base-dir ~/.openclaw/workspace/skills/colleagues` を使用。

---

## メインフロー：新しい同僚 Skill の作成

### Step 1：基本情報の入力（3つの質問）

`${CLAUDE_SKILL_DIR}/prompts/intake.md` の質問シーケンスを参考に、3つの質問のみ行う：

1. **ニックネーム/コードネーム**（必須）
2. **基本情報**（一言：会社、職位、役職、性別、思いつくまま）
   - 例：`バイトダンス 2-1 バックエンドエンジニア 男`
3. **性格プロフィール**（一言：MBTI、星座、個性タグ、企業文化、印象）
   - 例：`INTJ 山羊座 責任転嫁の達人 バイトダンス流 CRは厳しいが理由は一切説明しない`

名前以外はすべてスキップ可能。収集後に内容を確認してから次のステップへ進む。

### Step 2：原材料のインポート

ユーザーに原材料の提供方法を確認し、4つの方式を提示する：

```
原材料の提供方法は？

  [A] Feishu 自動収集（推奨）
      名前を入力すると、メッセージ記録 + ドキュメント + 多次元テーブルを自動取得

  [B] DingTalk 自動収集
      名前を入力すると、ドキュメント + 多次元テーブルを自動取得
      メッセージ記録はブラウザ経由で収集（DingTalk API は履歴メッセージ非対応）

  [C] Feishu リンク
      ドキュメント/Wiki のリンクを直接提供（ブラウザログイン状態 または MCP）

  [D] ファイルアップロード
      PDF / 画像 / エクスポート JSON / メール .eml

  [E] テキスト直接貼り付け
      テキストをそのままコピー＆ペースト

組み合わせ可能。スキップも可（手動入力情報のみで生成）。
```

---

#### 方式 A：Feishu 自動収集（推奨）

初回利用時に設定が必要：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/feishu_auto_collector.py --setup
```

**グループチャット収集**（tenant_access_token を使用、bot がグループに参加している必要あり）：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/feishu_auto_collector.py \
  --name "{name}" \
  --output-dir ./knowledge/{slug} \
  --msg-limit 1000 \
  --doc-limit 20
```

**プライベートチャット収集**（user_access_token + プライベートチャット chat_id が必要）：

プライベートメッセージはユーザー身分（user_access_token）でのみ取得可能。アプリ身分ではプライベートチャットにアクセスできない。

**前提条件**：

ユーザーは以下の情報を提供する必要がある：
1. **Feishu アプリ認証情報**：`app_id` と `app_secret`（Feishu オープンプラットフォームで自社アプリを作成して取得）
2. **ユーザー権限**：アプリに以下のユーザー権限（scope）を有効化する必要がある：
   - `im:message` — ユーザーとしてメッセージの読み取り/送信
   - `im:chat` — ユーザーとして会話リストの読み取り
3. **OAuth 認証コード（code）**：ユーザーがブラウザで OAuth 認証を完了した後、コールバック URL から取得

上記のいずれかが不足している場合は、設定完了までガイドする。事前に設定済みとは想定しないこと。

**user_access_token 取得の完全フロー**：

ユーザーが app_id、app_secret を提供し、ユーザー権限の有効化を確認した後：

1. OAuth 認証リンクを生成する：
   ```
   https://open.feishu.cn/open-apis/authen/v1/authorize?app_id={APP_ID}&redirect_uri=http://www.example.com&scope=im:message%20im:chat
   ```
   > ⚠️ 注意：`redirect_uri` は Feishu アプリの「セキュリティ設定 → リダイレクト URL」に `http://www.example.com` を追加する必要がある
   
2. ユーザーがブラウザでリンクを開き、ログインして認証する
3. `http://www.example.com?code=xxx` にリダイレクトされるので、ユーザーが code をコピーして提供
4. code でトークンを取得：
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/tools/feishu_auto_collector.py --exchange-code {CODE}
   ```
   または Python スクリプトで Feishu API を直接呼び出して取得：
   ```python
   # 1. app_access_token を取得
   POST https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal
   Body: {"app_id": "xxx", "app_secret": "xxx"}
   
   # 2. code で user_access_token を取得
   POST https://open.feishu.cn/open-apis/authen/v1/oidc/access_token
   Header: Authorization: Bearer {app_access_token}
   Body: {"grant_type": "authorization_code", "code": "xxx"}
   ```

**プライベートチャット chat_id の取得**：

ユーザーは通常 chat_id を知らない。user_access_token はあるが chat_id がない場合、**自分で Python スクリプトを書いて**取得する：

- **方法**：相手の open_id にメッセージを送信すると、レスポンスに chat_id が含まれる
  ```python
  POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id
  Header: Authorization: Bearer {user_access_token}
  Body: {"receive_id": "{相手のopen_id}", "msg_type": "text", "content": "{\"text\":\"こんにちは\"}"}
  # レスポンス内の chat_id がプライベートチャットの会話 ID
  ```
- **注意**：`GET /im/v1/chats` はプライベートチャットを返さない。これは Feishu API の制限であり、権限の問題ではないため、このAPIでプライベートチャットを探そうとしないこと
- ユーザーが相手の open_id を知らない場合、tenant_access_token で連絡先 API を検索：
  ```python
  GET https://open.feishu.cn/open-apis/contact/v3/scopes
  # アプリの可視範囲内の全ユーザーの open_id を返す
  ```

**収集の実行**：

user_access_token と chat_id を取得後：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/feishu_auto_collector.py \
  --open-id {相手のopen_id} \
  --p2p-chat-id {chat_id} \
  --user-token {user_access_token} \
  --name "{name}" \
  --output-dir ./knowledge/{slug} \
  --msg-limit 1000
```

**柔軟性の原則**：上記の API 呼び出しは必ずしも collector スクリプトを経由する必要はない。スクリプトが動作しない場合やシナリオに合わない場合は、Feishu API を直接呼び出す Python スクリプトを書いてよい。主要 API リファレンス：
- トークン取得：`POST /auth/v3/app_access_token/internal`、`POST /authen/v1/oidc/access_token`
- メッセージ送信（chat_id 取得）：`POST /im/v1/messages?receive_id_type=open_id`
- メッセージ取得：`GET /im/v1/messages?container_id_type=chat&container_id={chat_id}`
- 連絡先検索：`GET /contact/v3/scopes`、`GET /contact/v3/users/{user_id}`

自動収集の内容：
- グループチャット：共通グループ内で本人が送信したメッセージ（システムメッセージ・スタンプは除外）
- プライベートチャット：双方の完全な会話（対話の文脈理解のため）
- 本人が作成/編集した Feishu ドキュメントと Wiki
- 関連する多次元テーブル（アクセス権限がある場合）

収集完了後、`Read` で出力ディレクトリ内のファイルを読み取る：
- `knowledge/{slug}/messages.txt` → メッセージ記録（グループ + プライベート）
- `knowledge/{slug}/docs.txt` → ドキュメント内容
- `knowledge/{slug}/collection_summary.json` → 収集サマリー

収集が失敗した場合、エラーメッセージから原因を判断し修正を試みる。よくある問題：
- グループチャット収集：bot がグループに未追加
- プライベートチャット収集：user_access_token の期限切れ（有効期間2時間、refresh_token で更新可能）
- 権限不足：Feishu オープンプラットフォームで対応する権限を有効化し再認証するようユーザーをガイド
- または方式 B/C に切り替え

---

#### 方式 B：DingTalk 自動収集

初回利用時に設定が必要：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/dingtalk_auto_collector.py --setup
```

名前を入力してワンクリック収集：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/dingtalk_auto_collector.py \
  --name "{name}" \
  --output-dir ./knowledge/{slug} \
  --msg-limit 500 \
  --doc-limit 20 \
  --show-browser   # 初回利用時にこのパラメータを追加し、DingTalk にログイン
```

収集内容：
- 本人が作成/編集した DingTalk ドキュメントとナレッジベース
- 多次元テーブル
- メッセージ記録（⚠️ DingTalk API は履歴メッセージの取得に非対応のため、自動的にブラウザ収集に切り替え）

収集完了後 `Read` で読み取り：
- `knowledge/{slug}/docs.txt`
- `knowledge/{slug}/bitables.txt`
- `knowledge/{slug}/messages.txt`

メッセージ収集が失敗した場合は、チャット画面のスクリーンショットをアップロードするようユーザーに案内する。

---

#### 方式 D：ファイルアップロード

- **PDF / 画像**：`Read` ツールで直接読み取り
- **Feishu メッセージ JSON エクスポート**：
  ```bash
  python3 ${CLAUDE_SKILL_DIR}/tools/feishu_parser.py --file {path} --target "{name}" --output /tmp/feishu_out.txt
  ```
  その後 `Read /tmp/feishu_out.txt`
- **メールファイル .eml / .mbox**：
  ```bash
  python3 ${CLAUDE_SKILL_DIR}/tools/email_parser.py --file {path} --target "{name}" --output /tmp/email_out.txt
  ```
  その後 `Read /tmp/email_out.txt`
- **Markdown / TXT**：`Read` ツールで直接読み取り

---

#### 方式 C：Feishu リンク

ユーザーが Feishu ドキュメント/Wiki のリンクを提供した場合、読み取り方式を確認する：

```
Feishu リンクを検出しました。読み取り方式を選択してください：

  [1] ブラウザ方式（推奨）
      ローカル Chrome のログイン状態を再利用
      ✅ 社内ドキュメントや権限が必要なドキュメントも読み取り可能
      ✅ トークン設定不要
      ⚠️  ローカルに Chrome + playwright のインストールが必要

  [2] MCP 方式
      Feishu App Token で公式 API を呼び出し
      ✅ 安定、ブラウザ不要
      ✅ メッセージ記録の読み取りも可能（グループチャット ID が必要）
      ⚠️  事前に App ID / App Secret の設定が必要
      ⚠️  社内ドキュメントは管理者によるアプリ認可が必要

選択 [1/2]：
```

**選択肢 1（ブラウザ方式）**：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/feishu_browser.py \
  --url "{feishu_url}" \
  --target "{name}" \
  --output /tmp/feishu_doc_out.txt
```
初回利用時にログインしていない場合、ブラウザウィンドウが開いてログインを求められる（一度きり）。

**選択肢 2（MCP 方式）**：

初回利用時に設定の初期化が必要：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/feishu_mcp_client.py --setup
```

その後は直接読み取り：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/feishu_mcp_client.py \
  --url "{feishu_url}" \
  --output /tmp/feishu_doc_out.txt
```

メッセージ記録の読み取り（グループチャット ID が必要、形式は `oc_xxx`）：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/feishu_mcp_client.py \
  --chat-id "oc_xxx" \
  --target "{name}" \
  --limit 500 \
  --output /tmp/feishu_msg_out.txt
```

どちらの方式も出力後、`Read` で結果ファイルを読み取り、分析フローに進む。

---

#### 方式 E：直接貼り付け

ユーザーが貼り付けたコンテンツはそのままテキスト原材料として使用する。ツールの呼び出しは不要。

---

ユーザーが「ファイルはない」または「スキップ」と言った場合、Step 1 の手動入力情報のみで Skill を生成する。

### Step 3：原材料の分析

収集したすべての原材料とユーザーが入力した基本情報を統合し、以下の2つのラインで分析する：

**ライン A（Work Skill）**：
- `${CLAUDE_SKILL_DIR}/prompts/work_analyzer.md` の抽出ディメンションを参照
- 抽出項目：担当システム、技術規範、ワークフロー、出力の好み、経験知識
- 職種に応じた重点抽出（バックエンド/フロントエンド/アルゴリズム/プロダクト/デザインで重点が異なる）

**ライン B（Persona）**：
- `${CLAUDE_SKILL_DIR}/prompts/persona_analyzer.md` の抽出ディメンションを参照
- ユーザーが入力したタグを具体的な行動ルールに変換（タグ変換表を参照）
- 原材料から抽出：表現スタイル、意思決定パターン、対人行動

### Step 4：生成とプレビュー

`${CLAUDE_SKILL_DIR}/prompts/work_builder.md` を参考に Work Skill の内容を生成。
`${CLAUDE_SKILL_DIR}/prompts/persona_builder.md` を参考に Persona の内容を生成（5層構造）。

ユーザーにサマリーを表示（各5〜8行）して確認：
```
Work Skill サマリー：
  - 担当：{xxx}
  - 技術スタック：{xxx}
  - CRの重点：{xxx}
  ...

Persona サマリー：
  - コア性格：{xxx}
  - 表現スタイル：{xxx}
  - 意思決定パターン：{xxx}
  ...

生成を確認しますか？それとも調整が必要ですか？
```

### Step 5：ファイル書き込み

ユーザーの確認後、以下の書き込み操作を実行する：

**1. ディレクトリ構造の作成**（Bash を使用）：
```bash
mkdir -p colleagues/{slug}/versions
mkdir -p colleagues/{slug}/knowledge/docs
mkdir -p colleagues/{slug}/knowledge/messages
mkdir -p colleagues/{slug}/knowledge/emails
```

**2. work.md の書き込み**（Write ツールを使用）：
パス：`colleagues/{slug}/work.md`

**3. persona.md の書き込み**（Write ツールを使用）：
パス：`colleagues/{slug}/persona.md`

**4. meta.json の書き込み**（Write ツールを使用）：
パス：`colleagues/{slug}/meta.json`
内容：
```json
{
  "name": "{name}",
  "slug": "{slug}",
  "created_at": "{ISO時間}",
  "updated_at": "{ISO時間}",
  "version": "v1",
  "profile": {
    "company": "{company}",
    "level": "{level}",
    "role": "{role}",
    "gender": "{gender}",
    "mbti": "{mbti}"
  },
  "tags": {
    "personality": [...],
    "culture": [...]
  },
  "impression": "{impression}",
  "knowledge_sources": [...インポート済みファイルリスト],
  "corrections_count": 0
}
```

**5. 完全な SKILL.md の生成**（Write ツールを使用）：
パス：`colleagues/{slug}/SKILL.md`

SKILL.md の構造：
```markdown
---
name: colleague-{slug}
description: {name}、{company} {level} {role}
user-invocable: true
---

# {name}

{company} {level} {role}{性別とMBTIがあれば付記}

---

## PART A：仕事能力

{work.md の全内容}

---

## PART B：人物性格

{persona.md の全内容}

---

## 実行ルール

1. まず PART B で判断：このタスクにどのような態度で臨むか？
2. 次に PART A で実行：自分の技術力でタスクを遂行する
3. 出力時は常に PART B の表現スタイルを維持する
4. PART B Layer 0 のルールは最優先であり、いかなる状況でも違反してはならない
```

ユーザーに通知：
```
✅ 同僚 Skill を作成しました！

ファイル場所：colleagues/{slug}/
トリガーワード：/{slug}（フルバージョン）
              /{slug}-work（仕事能力のみ）
              /{slug}-persona（人物性格のみ）

使ってみて違和感があれば、「この人はこうじゃない」と言ってください。更新します。
```

---

## 進化モード：ファイル追加

ユーザーが新しいファイルやテキストを提供したとき：

1. Step 2 の方式で新しいコンテンツを読み取る
2. `Read` で既存の `colleagues/{slug}/work.md` と `persona.md` を読み取る
3. `${CLAUDE_SKILL_DIR}/prompts/merger.md` を参考に増分内容を分析
4. 現在のバージョンをアーカイブ（Bash を使用）：
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py --action backup --slug {slug} --base-dir ./colleagues
   ```
5. `Edit` ツールで増分内容を対応するファイルに追加
6. `SKILL.md` を再生成（最新の work.md + persona.md をマージ）
7. `meta.json` の version と updated_at を更新

---

## 進化モード：対話による修正

ユーザーが「違う」/「こうあるべき」と表現したとき：

1. `${CLAUDE_SKILL_DIR}/prompts/correction_handler.md` を参考に修正内容を特定
2. Work（技術/プロセス）と Persona（性格/コミュニケーション）のどちらに属するか判断
3. correction 記録を生成
4. `Edit` ツールで対応ファイルの `## Correction 記録` セクションに追加
5. `SKILL.md` を再生成

---

## 管理コマンド

`/list-colleagues`：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/skill_writer.py --action list --base-dir ./colleagues
```

`/colleague-rollback {slug} {version}`：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py --action rollback --slug {slug} --version {version} --base-dir ./colleagues
```

`/delete-colleague {slug}`：
確認後に実行：
```bash
rm -rf colleagues/{slug}
```
