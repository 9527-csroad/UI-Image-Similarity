# Docs Folder - 文档索引

最后更新：2026-04-16

## 保留文档（7 个）

### 1. `algorithm_evolution.md` — 算法演化报告
**定位**: 算法核心技术文档，包含 Phase 1→4 完整演化历程和 Phase 4 实施方案
**内容**: 算法组成与权重变更、核心问题诊断（iOS chrome 污染）、Phase 4 方案（Chrome 自适应检测与剥离、权重重新校准、掩码策略）、10 对测试基准、实施步骤、配置参数表
**面向**: 研发工程师

### 2. `product_analysis.md` — 产品分析 + Phase 4 需求
**定位**: 产品需求文档，定义 Phase 4 必须满足的产品要求
**内容**: Phase 3 测试结果（6 个用例）、PRD-001 至 PRD-007 需求、三方共识、预期结果、不可妥协的要求
**面向**: 产品经理、研发工程师
**关键**: PRD 需求是 Phase 4 的验收标准，不可删除

### 3. `ui_plagiarism_standards.md` — iOS 抄袭判定标准
**定位**: UI/设计视角的抄袭判定标准
**内容**: Apple App Store 审核标准（Guideline 4.1/4.3）、抄袭 vs HIG 的界定、系统组件排除列表、自定义组件权重建议、相似度层级判定
**面向**: UI 工程师、产品经理、算法工程师
**关键**: 定义了"什么算抄袭"的判定维度

### 4. `product-design.md` — 产品设计规格
**定位**: 产品功能设计文档
**内容**: 产品定位、功能范围（P0/P1/P2）、用户故事（US-1 至 US-7）、交互流程、页面线框图
**面向**: 产品、UI、研发

### 5. `ui-image-similarity-research.md` — 算法调研报告
**定位**: 算法方案调研与选型
**内容**: 各算法方案对比（SSIM、感知哈希、直方图、特征匹配、深度学习）、开源工具对比、技术架构建议
**面向**: 研发工程师

### 6. `test-report.md` — 测试报告
**定位**: 自动化测试结果与质量评估
**内容**: 24 个 API 测试用例、算法精度验证、边界用例、已知问题
**面向**: 测试工程师、研发工程师

### 7. `App界面相似规则.pdf` — Apple 参考规则
**定位**: 外部参考文档（Apple 官方 5 级相似度规则）
**内容**: 5 级相似度判定标准
**面向**: 全员参考

---

## 已删除文档（4 个中间过程文档）

| 原文件 | 删除理由 |
|--------|---------|
| `algorithm_phase4_discussion.md` | 算法第一轮讨论回应，内容已吸收至 `algorithm_evolution.md` |
| `round2_feedback.md` | 第二轮交叉讨论反馈，分歧已在 `algorithm_evolution.md` 中解决 |
| ~~`product_phase3_analysis.md`~~ | 恢复为 `product_analysis.md`（PRD 需求未被合并，需独立保留） |
| ~~`ui_analysis_ios_plagiarism.md`~~ | 恢复为 `ui_plagiarism_standards.md`（Apple 标准未被合并，需独立保留） |

---

## 最终文档结构

```
docs/
├── README.md                              # 本文档索引
├── App界面相似规则.pdf                    # Apple 官方规则（外部参考）
├── ui-image-similarity-research.md        # 算法调研报告
├── product-design.md                      # 产品设计规格
├── algorithm_evolution.md                 # 算法演化 + Phase 4 方案
├── product_analysis.md                    # 产品需求（PRD-001~007）
├── ui_plagiarism_standards.md             # iOS 抄袭判定标准
└── test-report.md                         # 测试报告
```

7 个文件。算法、产品、UI 各有独立文档，无冗余。
