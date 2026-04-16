# 项目审查问题清单

> 审查日期：2026-04-16
> 状态：记录存档，待后续修复

---

## 一、后端问题

### 1. 文件大小校验在读入内存之后（安全）
**文件**: `backend/main.py:94-96`
**问题**: `load_image()` 先 `file.file.read()` 读取全部内容到内存，然后才检查大小。一个 100MB 文件已经完全加载进 RAM 后校验才触发。
**修复方向**: 使用流式读取或 `file.file.read(MAX_SIZE + 1)` 限制读取量。

### 2. CORS 配置矛盾
**文件**: `backend/main.py:38-43`
**问题**: `allow_origins=["*"]` + `allow_credentials=True` 组合。按 CORS 规范，当允许 credentials 时 origin 不能是通配符。
**修复方向**: 去掉 `allow_credentials=True`（前端 fetch 不带 cookie），或改为具体 origin 列表。

### 3. `resize_to_match` 破坏宽高比
**文件**: `backend/main.py:101-108`
**问题**: 独立取 `min(ha, hb)` 和 `min(wa, wb)`。当两张图宽高比不同时会变形。例如 200x400 + 400x200 → 都变为 200x200 正方形。
**修复方向**: 按比例缩放到统一尺寸（以较小面积为基准），或用 padding 对齐。

### 4. Batch 接口逻辑不完整
**文件**: `backend/main.py:562-612`
**问题**: `batch_compare` 没有调用 `apply_density_gate()` 和主题切换检测逻辑。同一对图片在单张和批量接口中得分不同。
**修复方向**: 提取共享计算函数，batch 和 single 调用同一套逻辑。

### 5. K-Means 不确定性
**文件**: `backend/main.py:309`
**问题**: `cv2.KMEANS_RANDOM_CENTERS` 随机初始化，同一对图片多次对比 `dominant_color` 分数会波动。
**修复方向**: 改用 `cv2.KMEANS_PP_CENTERS`。

### 6. 内部错误信息泄露
**文件**: `backend/main.py:559`
**问题**: `raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")` 将内部异常直接暴露给用户。
**修复方向**: 返回通用错误信息，内部日志保留详细堆栈。

---

## 二、前端问题

### 7. Mock Fallback 静默误导用户（严重）
**文件**: `frontend/app.js:402-410`
**问题**: 后端不可用时，前端静默生成随机假数据，用户看到的"结果"是随机数，没有任何提示。
**修复方向**: 删除 mock fallback，改为显示错误提示。

### 8. 前端只展示 3/5 个指标，名称还对不上
**文件**: `frontend/app.js:463-471`, `frontend/index.html:124-143`
**问题**: 后端返回 5 个指标（ssim, edge, spatial_color, dhash, dominant_color），前端只展示 3 个，且映射关系错位：
- "布局分 dHash" 实际绑定的是 `edge` 字段（`barDHash.style.width = edge + '%'`）
- "颜色分 直方图" 绑定 `spatial_color`
- `dhash` 和 `dominant_color` 完全不展示
**修复方向**: 展示全部 5 个指标并正确对应。

### 9. Heatmap 备用逻辑中变量 `opacity` 未定义
**文件**: `frontend/app.js:630-638`
**问题**: Mock heatmap 代码中使用 `opacity` 变量，但该变量未定义（应为 `heatmapOpacity.value / 100`），导致 NaN。
**修复方向**: 改为 `const opacity = heatmapOpacity.value / 100;`。

### 10. 历史记录存截断的 data URL
**文件**: `frontend/app.js:698-699`
**问题**: `dataUrl.substring(0, 500)` 截断 Base64 数据，存入 localStorage 的是损坏的图片数据，无法显示缩略图。
**修复方向**: 用 canvas 先压缩到极小尺寸（如 40x30）再存，或只存文件名和分数。

---

## 三、文档/项目结构问题

### 11. CLAUDE.md 引用了不存在的文件名
| CLAUDE.md 中的引用 | 实际文件名 |
|-------------------|-----------|
| `docs/product_phase3_analysis.md` | `docs/product_analysis.md` |
| `docs/ui_analysis_ios_plagiarism.md` | `docs/ui_plagiarism_standards.md` |

### 12. CLAUDE.md 声称 "28 tests" 但实际约 21 个
CLAUDE.md 写 `test_api.py (28 tests)`，实际测试方法数（含参数化展开后约 23-24 个）。

### 13. 代码中的分级标签与 PDF 规则不完全一致
**代码阈值** (`get_label` 函数):
| 分数 | 标签 |
|------|------|
| >= 80 | 几乎一致 |
| >= 60 | 高度相似 |
| >= 40 | 中度相似 |
| >= 20 | 略有相似 |
| < 20 | 完全不同 |

**PDF 规则**:
| 级别 | 分数范围 | 标签 |
|------|---------|------|
| 5级 | 0.9-1.0 | 几乎一致 |
| 4级 | 0.7-0.8 | 高度相似 |
| 3级 | 0.5-0.6 | 部分相似 |
| 2级 | 0.3-0.4 | 略微相似 |
| 1级 | 0.1-0.2 | 完全不同 |

差异：
- 代码阈值每级比 PDF 低 10%（如 "几乎一致" 代码 >=80 vs PDF 90-100）
- 代码使用连续区间（无间隔），PDF 每级之间有空隔（0.2-0.3、0.4-0.5 等未定义）
- 代码用"中度相似"，PDF 用"部分相似"

### 14. `test-images/` 目录在 .gitignore 中排除
CLAUDE.md 的项目结构中列出了 `test-images/` 但该目录被 `.gitignore` 排除，仓库中不存在。算法演化文档中的 10 对测试基准无法复现。
