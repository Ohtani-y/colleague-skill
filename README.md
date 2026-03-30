<div align="center">

# 同事.skill

**把同事的技能与性格蒸馏成 AI Skill，让它替他工作。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![AgentSkills](https://img.shields.io/badge/AgentSkills-Standard-green)](https://agentskills.io)

[快速开始](#快速开始) · [效果示例](#效果示例) · [功能特性](#功能特性) · [安装说明](INSTALL.md)

</div>

---

## 是什么

你提供一个同事的原材料（飞书消息、钉钉文档、邮件、技术文档、截图），加上你对他的主观描述，**同事.skill** 会生成一个可以真正替他工作的 AI Skill：

- 用他的技术规范写代码和文档
- 用他的语气、口头禅、决策风格回答问题
- 知道他什么时候会推进、什么时候会甩锅、被催时会说什么

生成的 Skill 支持持续进化——追加新文件、或者直接说「他不会这样」，Skill 自动更新。

---

## 效果示例

> 给定输入：字节 2-1 后端工程师，INTJ，甩锅高手，字节范

**场景一：Code Review**

```
用户      ❯ 帮我看一下这个接口设计

同事.skill ❯ 等等，这个接口的 impact 是什么？背景没说清楚。
             （看完后）N+1 查询，改掉。返回结构用统一的
             {code, message, data}，这是规范，不用问为什么。
```

**场景二：背锅**

```
用户      ❯ 这个 bug 是你引入的吧

同事.skill ❯ 上线时间对上了吗？那个需求改了好几个地方，还有其他变更。
```

---

## 功能特性

### 生成的 Skill 结构

每个同事 Skill 由两部分组成，共同驱动输出：

| 部分 | 内容 |
|------|------|
| **Part A — Work Skill** | 负责系统、技术规范、工作流程、经验知识库 |
| **Part B — Persona** | 5 层性格结构：硬规则 / 身份 / 表达风格 / 决策模式 / 人际行为 |

运行逻辑：`接到任务 → Persona 判断态度 → Work Skill 执行 → 用他的语气输出`

### 数据采集

**自动采集（推荐，只需输入姓名）**

| 平台 | 消息记录 | 文档 / Wiki | 多维表格 |
|------|:-------:|:-----------:|:--------:|
| 飞书 | ✅ API 直接拉取 | ✅ | ✅ |
| 钉钉 | ⚠️ 浏览器采集 | ✅ | ✅ |

**手动上传**

`PDF` `图片` `飞书 JSON 导出` `邮件 .eml/.mbox` `Markdown` `直接粘贴文字`

### 性格标签

**个性**：认真负责 · 甩锅高手 · 完美主义 · 差不多就行 · 拖延症 · PUA 高手 · 职场政治玩家 · 向上管理专家 · 阴阳怪气 · 反复横跳 · 话少 · 只读不回 …

**企业文化**：字节范 · 阿里味 · 腾讯味 · 华为味 · 百度味 · 美团味 · 第一性原理 · OKR 狂热者 · 大厂流水线 · 创业公司派

**职级支持**：字节 2-1~3-3+ · 阿里 P5~P11 · 腾讯 T1~T4 · 百度 T5~T9 · 美团 P4~P8 · 华为 13~21 级 · 网易 · 京东 · 小米 …

### 进化机制

```
追加文件  ──→  自动分析增量  ──→  merge 进对应部分  ──→  不覆盖已有结论

对话纠正  ──→  "他不会这样，他应该是 xxx"
          ──→  写入 Correction 层  ──→  立即生效

版本管理  ──→  每次更新自动存档  ──→  支持回滚到任意历史版本
```

---

## 快速开始

### 1. 安装

```bash
# 安装到当前项目
mkdir -p .claude/skills
git clone https://github.com/titanwings/colleague-skill .claude/skills/colleague-creator

# 或安装到全局（所有项目可用）
git clone https://github.com/titanwings/colleague-skill ~/.claude/skills/colleague-creator
```

> OpenClaw 用户请参考 [INSTALL.md](INSTALL.md)

### 2. 安装依赖（可选）

```bash
pip3 install -r requirements.txt
```

### 3. 创建第一个同事 Skill

在 Claude Code 中输入：

```
/create-colleague
```

按提示依次输入：
1. 同事姓名
2. 公司 + 职级 + 职位（如 `字节 2-1 算法工程师`）
3. 性别 / MBTI / 个性标签 / 企业文化标签（均可跳过）
4. 原材料（飞书/钉钉自动采集，或上传文件，或直接粘贴）

完成后用 `/{slug}` 触发该同事 Skill。

### 管理命令

| 命令 | 说明 |
|------|------|
| `/list-colleagues` | 列出所有同事 Skill |
| `/{slug}` | 调用完整 Skill（Persona + Work） |
| `/{slug}-work` | 仅调用工作能力部分 |
| `/{slug}-persona` | 仅调用人物性格部分 |
| `/colleague-rollback {slug} {version}` | 回滚到历史版本 |
| `/delete-colleague {slug}` | 删除 |

---

## 项目结构

本项目遵循 [AgentSkills](https://agentskills.io) 开放标准，整个 repo 就是一个 skill 目录：

```
colleague-skill/
├── SKILL.md                    ← skill 入口（官方 frontmatter）
├── prompts/                    ← Prompt 模板
│   ├── intake.md               对话式信息录入
│   ├── work_analyzer.md        工作能力提取
│   ├── persona_analyzer.md     性格行为提取（含标签翻译表）
│   ├── work_builder.md         work.md 生成模板
│   ├── persona_builder.md      persona.md 五层结构模板
│   ├── merger.md               增量 merge 逻辑
│   └── correction_handler.md   对话纠正处理
├── tools/                      ← Python 工具
│   ├── feishu_auto_collector.py   飞书全自动采集
│   ├── feishu_browser.py          飞书浏览器方案（内部文档）
│   ├── feishu_mcp_client.py       飞书 MCP 方案
│   ├── feishu_parser.py           飞书导出 JSON 解析
│   ├── dingtalk_auto_collector.py 钉钉全自动采集
│   ├── email_parser.py            邮件解析
│   ├── skill_writer.py            Skill 文件写入与管理
│   └── version_manager.py         版本存档与回滚
├── colleagues/                 ← 生成的同事 Skill（gitignored）
│   └── example_zhangsan/
├── docs/PRD.md
├── requirements.txt
└── LICENSE
```

---

## 注意事项

- **原材料质量决定 Skill 质量**：聊天记录 + 长文档 > 仅手动描述
- 建议优先收集：他**主动写的**长文 > 他的**决策类回复** > 日常消息
- Word `.docx` / Excel `.xlsx` 请先转为 PDF 或 CSV 再导入
- 飞书自动采集需将 App bot 加入相关群聊，否则无法拉取历史消息

---

## License

MIT © [titanwings](https://github.com/titanwings)