# 独立审视：算法重新设计方案

> 日期：2026-04-16
> 定位：跳出 Phase 1-4 演化路径，从第一性原理重新审视
> 状态：方案提议，待实测验证

---

## 1. 现有方案的根本问题诊断

### 1.1 三个根本病因

**病因 1：dHash 是错误的工具**

实测数据显示，完全不相关的页面 dHash 得分经常在 60-98%：

| 对比 | dHash | 合理吗？ |
|------|-------|---------|
| 锁屏 vs 主题商店 | 82.4% | 不合理（完全不同的页面） |
| 教程 vs 标签设置 | 70.9% | 不合理 |
| 两个键盘主题页 | 98.5% | 合理（确实相似） |

dHash 将 17×16=272 个像素的梯度压缩为哈希，iOS Chrome（status bar + tab bar）贡献了 30-40% 的有效位。dHash 实际测量的是"iOS 截图共性度"，不是"布局相似度"。

应该直接移除，不是设为 0% 权重保留。

**病因 2：五个指标重叠 + 语义模糊**

- SSIM 和 Edge 都测"结构"但粗糙度不同
- Spatial Color 和 Dominant Color 都测"颜色"但方法不同
- dHash 同时掺杂结构和颜色但都不纯
- 五个信号线性混合后丢失了"哪个维度相似"的关键信息

**病因 3：线性加权无法表达 PDF 的条件决策逻辑**

PDF 的 5 级标准本质上是二维条件判定：

```
IF 布局不同 AND 颜色不同 → Level 1 (10-20%)
IF 布局相同 AND 颜色不同 → Level 2 (30-40%) — 换肤
IF 布局部分相同           → Level 3 (50-60%)
IF 布局相同 AND 颜色相同 → Level 4-5 (70-100%) — 高仿
```

这是非线性的条件逻辑。`W1×M1 + W2×M2 + ... + W5×M5` 是一维线性函数，无法表达这种关系。所以才需要 density gate、disagreement penalty、theme detection 三个补丁，而每个补丁又引入 3-5 个魔法数字。

### 1.2 Phase 1→3 的迭代模式

| Phase | 做了什么 | 效果 |
|-------|---------|------|
| 1 | 3 指标线性加权 | 白底虚高 |
| 2 | 加到 5 指标 + 空间网格 | 改善但奖励共享模板 |
| 3 | 内容掩码 + 密度门控 + 分歧惩罚 | 6 个 case 仅 1 个达标 |

每轮都在原架构上加补丁。Phase 4 计划引入 Chrome 检测器（又一个补丁）。

**核心问题不是"需要更多修正"，而是"架构不匹配问题结构"。**

---

## 2. 重新设计方案

### 2.1 核心思路

用**两个干净的维度**替代五个混杂的指标 + 三个后处理修正：

| 维度 | 测量目标 | PDF 对应概念 |
|------|---------|-------------|
| Layout Score（布局分） | UI 元素的空间位置关系 | "布局结构" |
| Style Score（风格分） | 色彩方案相似度 | "色彩系统" |

加上一个**条件融合**逻辑替代线性加权。

### 2.2 布局分：Edge-SSIM

**做法**：在两张图的 Canny 边缘图上计算 SSIM。

```python
def compute_layout_score(img_a, img_b):
    """
    在边缘图上计算 SSIM = 纯结构比较，完全忽略颜色和亮度。
    Canny 提取按钮边框、卡片边界、分隔线、图标轮廓。
    SSIM 用 11x11 窗口逐像素比较这些边缘的空间位置。
    """
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)

    edges_a = cv2.Canny(cv2.GaussianBlur(gray_a, (5,5), 0), 50, 150)
    edges_b = cv2.Canny(cv2.GaussianBlur(gray_b, (5,5), 0), 50, 150)

    score, _ = ssim(edges_a, edges_b, full=True)
    return max(0, min(100, score * 100))
```

**为什么比现有方案好**：
- 直接衡量 PDF 所说的"布局结构" — 边缘图上的 SSIM 就是在问"两张图的 UI 组件是否出现在相同位置"
- 完全不受颜色影响（蓝色天气 vs 绿色天气在边缘图上几乎一样）
- 比 Edge 8x8 精细得多（SSIM 用 11x11 窗口 vs 8x8 网格每格覆盖几万像素）
- 一个指标替代 SSIM + Edge 8x8 + dHash 三个指标的功能，信号更纯

### 2.3 风格分：Bhattacharyya 距离

**做法**：HSV 空间全图直方图，用 Bhattacharyya 距离比较。

```python
def compute_style_score(img_a, img_b):
    """
    HSV 直方图 Bhattacharyya 距离。
    输出 [0, 100]，100 = 色彩方案完全相同。
    """
    hsv_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2HSV)
    hsv_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2HSV)

    hist_a = cv2.calcHist([hsv_a], [0, 1], None, [30, 32], [0, 180, 0, 256])
    hist_b = cv2.calcHist([hsv_b], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist_a, hist_a)
    cv2.normalize(hist_b, hist_b)

    bhatt = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_BHATTACHARYYA)
    return max(0, min(100, (1.0 - bhatt) * 100))
```

**为什么比现有方案好**：
- Bhattacharyya 天然归一化到 [0,1]，不需要 `chi2/10.0` 魔法数字
- 一个指标替代 Spatial Color + Dominant Color
- 归一化后的直方图不受图像尺寸影响

### 2.4 融合：条件逻辑

```python
def compute_combined(layout_score, style_score):
    """
    基于 PDF 五级标准的条件融合。

    PDF 的核心判定逻辑：
    - 布局决定落在哪个级别
    - 颜色/风格在级别内微调
    - 换肤是一个独立的判定分支
    """

    # 换肤场景：布局一致但颜色完全不同
    if layout_score > 55 and style_score < 30:
        # 限制到 Level 2 区间 (30-40%)
        return 30 + (layout_score - 55) * 0.15 + style_score * 0.1

    # 正常融合：布局为主轴 (65%)，风格为辅轴 (35%)
    base = layout_score * 0.65 + style_score * 0.35
    return round(max(0, min(100, base)), 1)
```

**为什么比线性加权好**：
- 换肤场景被显式处理为独立分支，不需要 theme_change_detection 补丁
- 布局是 PDF 的主要判定维度，给 65% 权重
- 当布局高但颜色低时，总分被限制在 Level 2 范围

### 2.5 Chrome 裁剪

```python
def crop_chrome(img, top_pct=0.12, bottom_pct=0.10):
    """简单固定比例裁剪，去除 status bar 和 tab bar/home indicator"""
    h = img.shape[0]
    return img[int(h * top_pct) : int(h * (1 - bottom_pct)), :]
```

在 resize 之后、计算指标之前调用。验证有效后再考虑自适应检测。

---

## 3. 方案对比

| 维度 | Phase 3（当前） | 本方案 |
|------|---------------|--------|
| 指标数量 | 5 个 | **2 个** |
| 后处理修正 | 3 个 | **1 个条件分支** |
| 硬编码魔法数字 | ~15 个 | **~5 个** |
| 能否原生表达换肤 | 不能（需 hack） | **是** |
| Chrome 敏感度 | 高 | **低**（Edge-SSIM 对 Chrome 不敏感） |
| 颜色分归一化 | chi2/10（无依据） | **Bhattacharyya（理论保证）** |
| 可解释性 | "五个分数的加权均值" | **"布局 X%，风格 Y%"** |

---

## 4. 对 PDF 五级的预期表现

| 级别 | 描述 | Layout Score | Style Score | Combined | PDF 目标 |
|------|------|-------------|-------------|----------|---------|
| 1级 | 天气 vs 音乐 | ~15% | ~20% | ~17% | 10-20% |
| 2级 | 蓝天气 vs 绿天气 | ~70% | ~20% | **~34%**（换肤分支） | 30-40% |
| 3级 | 天气 vs 生活指数天气 | ~50% | ~60% | ~54% | 50-60% |
| 4级 | 天气 vs 增强信息天气 | ~75% | ~80% | ~77% | 70-80% |
| 5级 | 天气 vs 微调天气 | ~95% | ~95% | ~95% | 90-100% |

---

## 5. 删除清单

以下组件在本方案中不再需要：

| 组件 | 删除理由 |
|------|---------|
| `compute_dhash()` | 被 Edge-SSIM 替代，且 dHash 对 iOS 截图根本不适用 |
| `compute_edge_similarity()` | 被 Edge-SSIM 替代，且 8x8 太粗 |
| `compute_dominant_color_similarity()` | 被 Bhattacharyya 替代 |
| `compute_content_mask()` | Edge-SSIM 天然只关注边缘，不需要内容掩码 |
| `apply_density_gate()` | Edge-SSIM 对密度差异的处理比 Sobel 均值更自然 |
| `apply_disagreement_penalty()` | 只有 2 个维度，不存在"五个指标互相矛盾"的问题 |
| theme change detection（main.py:524-526） | 被条件融合中的换肤分支替代 |

---

## 6. 风险与待验证项

### 6.1 Edge-SSIM 未经实测

理论上 Edge-SSIM 应该优于 Edge 8x8 + 灰度 SSIM 的组合，但需要实际跑 Phase 3 的 6 个测试用例验证。特别需要关注：
- 文字密集页面的 Canny 边缘图可能过于"满"，导致不同页面的 Edge-SSIM 虚高
- Canny 阈值 (50, 150) 对不同亮度背景的适应性

### 6.2 两维度够不够

两维度（布局 + 风格）可能不足以区分 Level 3 和 Level 4。如果实测发现这两级区分不清，可以加入第三维度：

- **内容分（Content Score）**：灰度 SSIM（不是 Edge-SSIM），捕获像素级内容差异
- 三维度仍然远少于五维度，且每个维度语义清晰

### 6.3 Bhattacharyya 对换肤的灵敏度

需要验证：当两张图只换了主色调（如蓝→绿），Bhattacharyya 距离是否足够大（<30%），使换肤条件分支能触发。如果 Bhattacharyya 对色调变化不够敏感（因为 V 通道不变），可能需要只用 H 通道，或加入 dominant color 作为辅助。

### 6.4 固定比例 Chrome 裁剪的局限

12%/10% 裁剪对标准 iPhone 截图有效，但对以下场景可能不适用：
- 无 tab bar 的页面（底部多裁了）
- 有 large title nav bar 的页面（顶部可能裁少了）
- 非 iOS 截图（Android、Web）

Phase 4 方案中的自适应检测器可以作为后续迭代。

---

## 7. 实施建议

### 7.1 最小验证路径

1. 写一个独立脚本，对 Phase 3 的 6 个测试用例分别计算 Edge-SSIM 和 Bhattacharyya
2. 对比与 Phase 3 的 5 指标结果
3. 如果 Edge-SSIM + Bhattacharyya 的二维分布能比 5 指标更好地区分 6 个 case → 推进
4. 如果不能 → 分析哪个 case 失败，针对性调整（加入 Content Score 第三维度，或调整 Canny 参数）

### 7.2 不要一次性重构

在验证通过后：
1. 先在 `main.py` 中**新增** `compute_layout_score` 和 `compute_style_score`，与现有指标并行计算
2. API 响应中同时返回新旧两套分数，前端可以对比展示
3. 确认新方案在所有 case 上表现更好后，再删除旧指标
