# 算法优化建议（基于 PDF 五级标准审查）

> 审查日期：2026-04-16
> 基于：Phase 3 代码 + App界面相似规则.pdf + 全部项目文档

---

## 0. 背景

### PDF 五级标准回顾

| 级别 | 数值范围 | 定义 | PDF 示例 | 变化维度 |
|------|---------|------|---------|---------|
| 1级 | 0.1-0.2 | 完全不同 | 天气 App vs 音乐播放器 | 布局+色彩+功能全不同 |
| 2级 | 0.3-0.4 | 略微相似 | 蓝色天气 vs 绿色天气 | 色彩系统变化，框架保留（换肤） |
| 3级 | 0.5-0.6 | 部分相似 | 天气 vs 生活指数天气 | 底部模块替换，顶部一致 |
| 4级 | 0.7-0.8 | 高度相似 | 天气 vs 增强信息天气 | 信息密度增加，布局配色不变（高仿） |
| 5级 | 0.9-1.0 | 几乎一致 | 天气 vs 微调天气 | 仅像素级微调 |

### PDF 传达的核心判定逻辑

1. **三维同时评估**：布局结构 × 色彩系统 × 功能元素
2. **颜色变化有强力降分效果**：同框架换色 = 从 80%+ 降到 30-40%
3. **换肤（Level 2）和高仿（Level 4）都需要检测**

### Phase 3 对 PDF 五级的预估表现

| 级别 | PDF 期望 | Phase 3 预估 | 问题 |
|------|---------|-------------|------|
| 1级 | 10-20% | 25-35% | 偏高（Chrome 地板 + 部分颜色重叠） |
| 2级 | 30-40% | 35-50% | 偏高（灰度 SSIM 对蓝/绿不敏感 + dHash 框架噪声） |
| 3级 | 50-60% | 50-65% | 基本命中，略高 |
| 4级 | 70-80% | 65-75% | 略低（SSIM 对信息增加过于敏感） |
| 5级 | 90-100% | 85-95% | 基本命中 |

---

## 1. 阈值体系与 PDF 对齐

### 问题

代码 `get_label` 阈值（20/40/60/80）与 PDF（10-20/30-40/50-60/70-80/90-100）存在 10 分系统性偏移。术语也不一致（代码"中度相似" vs PDF"部分相似"）。

### 建议

```python
def get_label(combined: float) -> str:
    if combined >= 90:
        return "几乎一致"      # 5级
    if combined >= 70:
        return "高度相似"      # 4级
    if combined >= 50:
        return "部分相似"      # 3级
    if combined >= 30:
        return "略微相似"      # 2级
    return "完全不同"          # 1级
```

注意：PDF 级别之间有空隔（0.2-0.3、0.4-0.5 等），但代码用连续阈值覆盖全域更实用。如果算法精度提高后需要严格对齐 PDF 区间，可以在此基础上增加分级映射层。

### 优先级：P0

---

## 2. iOS Chrome 裁剪

### 问题

iOS 系统级 UI 组件（status bar、nav bar、tab bar、home indicator）在所有截图中都相似，贡献了约 10-15% 的"相似度地板"。这是 Level 1 和 Level 2 偏高的首要原因。

### 建议：两步走

**第一步（快速验证）—— 固定比例裁剪：**

```python
def crop_ios_chrome(img, top_pct=0.12, bottom_pct=0.10):
    """裁剪 iOS 系统 UI 区域，只保留内容区域"""
    h = img.shape[0]
    top = int(h * top_pct)
    bottom = int(h * (1 - bottom_pct))
    return img[top:bottom, :]
```

在 `compare` 函数中，`resize_to_match` 之后、计算任何指标之前调用。只改一行代码就能验证方向是否正确。

**第二步（自适应检测）—— 验证有效后推进：**

按 Phase 4 方案 A 的自底向上检测策略，实现 Sobel 梯度密度检测器。

### 验证标准

用 Phase 3 的 6 个测试用例：裁剪后 Case A（深色音乐 vs 浅色新闻）应 <20%，Case F（教程 vs 标签设置）应 <30%。

### 优先级：P0

---

## 3. CHI-SQUARE 归一化替换

### 问题

`compute_spatial_color_histogram` 中 `chi2 / 10.0` 的 10.0 是无理论依据的魔法数字。卡方距离没有有界范围，除以 10 在不同图片上表现不稳定。

### 建议

替换为 Bhattacharyya 距离，天然归一化到 [0, 1]：

```python
# 替换前
chi2 = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CHISQR)
sim = float(max(0, 1 - chi2 / 10.0) * 100)

# 替换后
bhatt = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_BHATTACHARYYA)
sim = float((1.0 - bhatt) * 100)  # bhatt=0 → sim=100%, bhatt=1 → sim=0%
```

Bhattacharyya 距离在颜色对比领域有广泛的学术验证，且不需要额外参数。

### 优先级：P0

---

## 4. 颜色差异的非线性降分

### 问题

当前线性加权 `combined = W_ssim × ssim + W_edge × edge + W_color × color` 无法表达 PDF 的非线性判定逻辑。

PDF 的 Level 2 示例说明：框架完全一致（结构维度 ~80%）但换色后，总分应降到 30-40%。线性加权做不到这一点 —— 如果结构权重 0.75、颜色权重 0.25，框架一致换色的最低分也是 80%×0.75 = 60%，远高于 PDF 要求的 30-40%。

### 建议

在加权融合后增加颜色差异的降分修正：

```python
def apply_color_divergence_correction(combined, structure_score, color_score):
    """
    当结构高但颜色低时（换肤场景），强制降分到 Level 2 范围。
    structure_score = max(ssim, edge) 取结构维度的最高分
    color_score = (spatial_color + dominant_color) / 2 取颜色维度的均分
    """
    if structure_score > 60 and color_score < 35:
        # 换肤场景：结构一致但颜色完全不同
        # 将综合分压缩到 25-45% 范围（Level 2）
        cap = 25 + color_score * 0.6  # color_score=0 → cap=25, color_score=35 → cap=46
        return min(combined, cap)
    return combined
```

这确保了"同框架换色"不会拿到超过 Level 2 范围的综合分。

### 优先级：P1

---

## 5. 换肤检测专项信号

### 问题

当前 `main.py:524-526` 的 theme change detection 用硬编码阈值（edge>75, spatial_color<40, dominant_color<60），逻辑含义不清晰。

### 建议

改为结构化的判定，输出到 API 响应中：

```python
def detect_patterns(ssim, edge, spatial_color, dominant_color):
    """
    检测特殊相似度模式，作为诊断信号输出。
    """
    patterns = []
    
    structure_avg = (ssim + edge) / 2
    color_avg = (spatial_color + dominant_color) / 2
    
    # 换肤检测
    if structure_avg > 60 and color_avg < 35:
        patterns.append({
            "type": "skin_swap",
            "message": "布局框架高度一致但色彩系统完全不同 — 疑似换肤型抄袭",
            "confidence": min(1.0, (structure_avg - 60) / 30)
        })
    
    # 高仿检测
    if structure_avg > 70 and color_avg > 60:
        patterns.append({
            "type": "high_copy",
            "message": "结构和色彩均高度一致 — 疑似高仿型抄袭",
            "confidence": min(1.0, (structure_avg - 70) / 20)
        })
    
    # 局部模块替换
    if ssim < 50 and edge > 60:
        patterns.append({
            "type": "partial_replace",
            "message": "整体布局框架相似但部分内容模块被替换",
            "confidence": min(1.0, (edge - ssim) / 40)
        })
    
    return patterns
```

API 响应中增加 `"patterns"` 字段，前端据此展示专项提示。

### 优先级：P1

---

## 6. 分级映射层

### 问题

线性加权输出的是连续分数（如 47.3%），但 PDF 定义的是离散级别。47.3% 对于用户来说不知道是"比较像还是不太像"。

### 建议

在线性加权 + 修正之后，可选择性地将分数映射到 PDF 级别区间：

```python
def map_to_level_range(combined):
    """
    将连续分数映射到 PDF 定义的级别区间内。
    仅在需要严格对齐 PDF 标准时启用。
    """
    if combined >= 85:
        return remap(combined, 85, 100, 90, 100)  # → Level 5
    if combined >= 65:
        return remap(combined, 65, 85, 70, 80)    # → Level 4
    if combined >= 45:
        return remap(combined, 45, 65, 50, 60)    # → Level 3
    if combined >= 25:
        return remap(combined, 25, 45, 30, 40)    # → Level 2
    return remap(combined, 0, 25, 10, 20)          # → Level 1

def remap(value, old_min, old_max, new_min, new_max):
    """线性映射"""
    ratio = (value - old_min) / (old_max - old_min)
    return new_min + ratio * (new_max - new_min)
```

此建议优先级较低，因为：
1. 需要先确保前面的改进让原始分数尽量接近目标区间
2. 强制映射会丢失分数的精细差异

建议作为可配置选项（默认关闭），在算法基本校准后再评估是否开启。

### 优先级：P2

---

## 附：K-Means 确定性修复

将 `cv2.KMEANS_RANDOM_CENTERS` 改为 `cv2.KMEANS_PP_CENTERS`，确保同一对图片多次对比分数一致。这是独立于上述建议的小修复，实施成本极低。

**优先级：P2**（独立修复，不影响其他建议的实施顺序）
