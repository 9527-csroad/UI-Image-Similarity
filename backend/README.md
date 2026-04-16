# UI Image Compare - Backend API

## 快速启动

```bash
# 激活虚拟环境
source venv/bin/activate

# 安装依赖（首次运行）
pip install -r requirements.txt

# 启动服务
python main.py
# 服务运行在 http://localhost:8000
```

## API 接口

### 健康检查

```
GET /api/health
```

### 图像对比

```
POST /api/compare
```

**请求**: FormData，两个文件字段
- `image_a`: 第一张 UI 图像
- `image_b`: 第二张 UI 图像

**支持格式**: PNG, JPG, WebP, BMP
**大小限制**: 10 MB

**响应**:
```json
{
  "combined": 87.3,       // 综合相似度
  "ssim": 92.1,           // 结构相似度 (SSIM)
  "dhash": 85.6,          // 布局相似度 (dHash)
  "hist": 78.2,           // 颜色相似度 (HSV 直方图)
  "insight": "分析文案",   // 智能解读
  "label": "高度相似",     // 定性标签
  "processing_time_ms": 130, // 处理耗时
  "heatmap": "base64..."    // 差异热力图 (PNG base64)
}
```

### 批量对比

```
POST /api/compare/batch
```

**请求**: FormData，`images` 字段，偶数个文件
**响应**: 包含所有对比结果的数组

## 算法说明

采用加权融合方案（基于技术调研报告）：
- **SSIM (50%)**: 结构相似度，scikit-image 实现
- **dHash (25%)**: 差异哈希，imagehash 库实现
- **HSV 直方图 (25%)**: 颜色分布相似度，OpenCV CORREL 方法

## 技术栈

- FastAPI 0.128
- scikit-image 0.24 (SSIM)
- imagehash 4.3 (dHash)
- OpenCV 4.13 (HSV 直方图 + 热力图)
- Pillow 11.3 (图像加载)
- Python 3.9+
