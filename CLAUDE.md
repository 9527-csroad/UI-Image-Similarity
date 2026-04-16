# CLAUDE.md

## 项目概述

**项目名称**: UI 图像相似度对比工具 (Image Compare)

**目标**: 开发一个 Web 界面，用户上传两张 UI 图像后，系统计算并展示两张图像之间的相似度。

**核心需求**:
- Web 界面支持上传两张 UI 图像
- 计算两张 UI 图像的相似度（需调研合适的算法方案）
- 展示对比结果

## 技术栈

（待确定，根据调研结果补充）

## 项目结构

```
image-compare/
├── CLAUDE.md          # 项目总览（本文件）
├── .claude/
│   ├── agents/        # 专用 Agent 定义
│   │   ├── product.md         # 产品经理 Agent
│   │   ├── engineer.md        # 研发工程师 Agent
│   │   ├── ui-engineer.md     # UI 工程师 Agent
│   │   └── test-engineer.md   # 测试工程师 Agent
│   └── settings.json  # Claude Code 设置
├── reference.jpeg     # 参考图像
```

## Agent 团队

本项目配置了四位专属 Agent 协作开发：

| Agent | 职责 | 文件 |
|-------|------|------|
| 产品经理 | 需求分析、功能规划、用户故事 | `.claude/agents/product.md` |
| 研发工程师 | 架构设计、核心算法、代码实现 | `.claude/agents/engineer.md` |
| UI 工程师 | 前端界面设计、交互体验 | `.claude/agents/ui-engineer.md` |
| 测试工程师 | 测试策略、质量保障、Bug 追踪 | `.claude/agents/test-engineer.md` |

## 协作原则

- 各 Agent 各司其职，产品先行，研发跟进，UI 配合，测试兜底
- 重要决策需要跨 Agent 视角评估
- 代码提交前需经过测试工程师审视

## 关键技术调研方向

- UI 图像相似度算法（SSIM、感知哈希、深度学习等）
- Web 框架选型
- 前后端架构设计
