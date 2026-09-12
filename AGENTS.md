# AGENTS.md

## 项目用途

本仓库专门用来跟 GitHub 仓库 `imovation/skills` 同步 opencode Skill 文件。每个 Skill 是一个独立目录，包含 `SKILL.md`（必须）及可选的脚本、资源、文档。

## 同步规则

- 本地目录即真实状态，GitHub 必须与本地完全一致
- 本地删除的目录，GitHub 上也应删除（force push）
- 新增或修改的 Skill 目录需 `git add -A && git commit` 后推送

## Skill 结构约定

每个 Skill 目录必须包含 `SKILL.md`，其 YAML frontmatter 至少有 `name` 和 `description` 字段：

```yaml
---
name: skill-name
description: 简短描述触发场景
---
```

可选文件：`scripts/`、`assets/`、`references/`、`SPEC.md`、`REQUESTS.md`、`evals/`。

## 当前 Skill 清单

| 目录 | 用途 |
|------|------|
| `deep-cure/` | 深度诊断与根治方法论 |
| `docx-to-md/` | Word (.docx) 转 Markdown |
| `headscale-self-host-expert/` | Headscale 自托管 VPN 部署 |
| `matrix-self-host-expert/` | Matrix (Synapse) 自建部署 |
| `md-to-docx/` | Markdown 转 Word (.docx) |
| `openclaw-matrix-acp-dedupe/` | OpenClaw Matrix ACP 重复回复修复 |
| `opencode-model-manager/` | OpenCode LLM 模型管理与切换 |
| `rdp-manager/` | Ubuntu 远程桌面管理（xrdp/内置） |

## 注意事项

- 本项目所有思考和回答必须使用中文
- 没有 build/test/lint 流程，这是一个纯内容仓库
- 提交信息风格：`sync: ...` 或 `feat: ...` 或 `fix: ...`，可用中文
- 推送时读取 `.secret` 文件作为 GitHub push token，格式为 `https://imovation:<token>@github.com/imovation/skills.git`