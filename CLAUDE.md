# CLAUDE.md

## 项目概述

**项目名称**: UI 图像相似度对比工具 (Image Compare)

**目标**: 开发一个 Web 界面，用户上传两张 **iOS App UI 截图**后，系统计算并展示两张图像之间的相似度，用于检测 UI 抄袭。

**核心需求**:
- Web 界面支持上传两张 iOS App UI 截图
- 计算两张 UI 图像的相似度（需区分"遵循 iOS HIG"与"抄袭"）
- 展示对比结果

**关键约束**：
- 本工具专门针对 **iOS App UI 截图**的相似度比较
- 必须排除 iOS 系统级组件（status bar、nav bar、home indicator、tab bar）的干扰
- "布局相似" ≠ "抄袭"——所有 iOS App 都遵循 HIG 有相似框架，真正需要比较的是用户内容区域的组件布局

## 技术栈

- **后端**: FastAPI (Python) + OpenCV + scikit-image + imagehash + Pillow
- **前端**: 纯 HTML/CSS/JavaScript
- **测试**: pytest

## 项目结构

```
image-compare/
├── CLAUDE.md                     # 项目总览（本文件）
├── .claude/
│   ├── agents/                   # 专用 Agent 定义
│   │   ├── product.md            # 产品经理 Agent
│   │   ├── engineer.md           # 研发工程师 Agent
│   │   ├── ui-engineer.md        # UI 工程师 Agent
│   │   └── test-engineer.md      # 测试工程师 Agent
│   └── settings.json             # Claude Code 设置
├── backend/
│   ├── main.py                   # FastAPI 后端 (v3.0.0)
│   └── test_api.py               # 测试套件 (28 tests)
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── docs/
│   ├── App界面相似规则.pdf         # 5级相似度判定规则
│   ├── algorithm_evolution.md     # 算法演化报告 (Phase 1-3 + Phase 4 方案)
│   ├── product_phase3_analysis.md # Phase 3 产品分析
│   └── ui_analysis_ios_plagiarism.md # iOS 抄袭判定标准分析
├── images/                       # 测试图像
│   ├── 1/                        # Phase 2/3 测试截图
│   └── 2/                        # 真实 UI 测试截图
└── test-images/                  # 测试图像数据集
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

## 算法当前状态

### 已完成 (Phase 1-3)

| Phase | 核心改进 | 状态 |
|-------|---------|------|
| 1 | SSIM 50% + dHash 25% + 全局直方图 25% | 白底页面虚高 |
| 2 | 新增 Edge/Spatial Color/Dominant Color，多指标融合 | 奖励"共享模板" |
| 3 | 内容掩码 SSIM、dHash 替换 pHash、8x8 边缘网格 | 有改善但 iOS chrome 仍干扰 |

### 当前测试结果 (Phase 3)

6 个测试用例中仅 1 个达标，核心问题：**iOS 通用框架元素（status bar/nav bar/tab bar）在所有维度上贡献"相似度地板"**。

详细分析见 `docs/algorithm_evolution.md` 和 `docs/product_phase3_analysis.md`。

### 下一步 (Phase 4)

**核心任务**：iOS Chrome 剥离 + 内容区域独立比较。详见 `docs/algorithm_evolution.md` §5。

## 参考文档

- `docs/App界面相似规则.pdf` — 5级相似度判定规则
- `docs/algorithm_evolution.md` — 算法演化报告 + Phase 4 方案
- `docs/product_phase3_analysis.md` — Phase 3 产品分析 + 优化需求
- `docs/ui_analysis_ios_plagiarism.md` — iOS 抄袭判定标准 + UI 建议
