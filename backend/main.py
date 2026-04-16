"""
UI Image Similarity Comparison - Backend API
FastAPI server for computing similarity between two UI images.
Phase 2: Color SSIM + pHash(16x16) + Edge similarity + Spatial color histogram + Dominant color fusion.
"""

from __future__ import annotations

import io
import time
import logging
import base64
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image
import cv2
import imagehash
from skimage.metrics import structural_similarity as ssim
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="UI Image Compare API",
    description="Compute similarity between two UI images using SSIM, pHash, edge, spatial color, and dominant color fusion.",
    version="2.0.0",
)

# Allow frontend CORS (development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Phase 2 weight configuration (5-level similarity spec)
# SSIM 30% (core structure+color), Edge 25% (layout, color-invariant),
# Spatial color 25% (color+position), pHash 10% (perceptual coarse), Dominant 10% (theme identity)
WEIGHTS = {
    "ssim": 0.30,
    "edge": 0.25,
    "spatial_color": 0.25,
    "phash": 0.10,
    "dominant_color": 0.10,
}


# --- Pydantic Models ---

class SimilarityResponse(BaseModel):
    combined: float
    ssim: float
    edge: float
    spatial_color: float
    phash: float
    dominant_color: float
    insight: str
    label: str
    processing_time_ms: float


class HealthResponse(BaseModel):
    status: str
    version: str


# --- Helper Functions ---

def validate_file(file: UploadFile) -> None:
    """Validate uploaded file extension and size."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )


def load_image(file: UploadFile) -> np.ndarray:
    """Read uploaded file into a numpy array (RGB)."""
    data = file.file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds 10 MB limit.")
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.array(img)


def resize_to_match(img_a: np.ndarray, img_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Resize the larger image to match the smaller one (preserves aspect ratio via resize)."""
    ha, wa = img_a.shape[:2]
    hb, wb = img_b.shape[:2]
    if (ha, wa) != (hb, wb):
        target_h, target_w = min(ha, hb), min(wa, wb)
        img_a = cv2.resize(img_a, (target_w, target_h), interpolation=cv2.INTER_AREA)
        img_b = cv2.resize(img_b, (target_w, target_h), interpolation=cv2.INTER_AREA)
    return img_a, img_b


def compute_ssim(img_a: np.ndarray, img_b: np.ndarray) -> tuple[float, Optional[np.ndarray]]:
    """
    Compute per-channel (RGB) SSIM score.
    Returns (score_0_to_100, diff_map_or_None).
    Uses color SSIM (channel_axis=2) to capture both structure and chrominance differences.
    Raw SSIM for valid images is in [0, 1], mapped directly to [0, 100].
    """
    # Per-channel SSIM: captures color + structure (fixes grayscale range bug)
    score = float(ssim(img_a, img_b, channel_axis=2))
    score_pct = max(0, min(100, score * 100))

    # Grayscale SSIM for heatmap visualization only (not used for scoring)
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)
    _, diff_map = ssim(gray_a, gray_b, full=True)

    return round(score_pct, 1), diff_map


def compute_phash(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """
    Compute perceptual hash similarity at 16x16 resolution.
    pHash uses DCT (Discrete Cosine Transform), capturing overall visual impression.
    16x16 = 256 bits, giving 257 possible distinct values (vs 65 for 8x8 dHash).
    """
    hash_a = imagehash.phash(Image.fromarray(img_a), hash_size=16)
    hash_b = imagehash.phash(Image.fromarray(img_b), hash_size=16)
    max_bits = 256  # 16x16
    hamming = int(hash_a - hash_b)
    similarity = (max_bits - hamming) / max_bits * 100
    return round(max(0, min(100, similarity)), 1)


def compute_edge_similarity(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """
    Canny edge detection + 4x4 spatial histogram comparison.
    Captures layout structure independent of color theme.
    - Edges are invariant to color changes (good for theme detection)
    - Edges are sensitive to layout changes (good for module swap detection)
    """
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)

    # Gaussian blur to reduce noise
    blur_a = cv2.GaussianBlur(gray_a, (5, 5), 0)
    blur_b = cv2.GaussianBlur(gray_b, (5, 5), 0)

    # Canny edge detection with adaptive thresholds
    edges_a = cv2.Canny(blur_a, 50, 150)
    edges_b = cv2.Canny(blur_b, 50, 150)

    # Spatial histogram: divide into 4x4 grid, count edge pixels per cell
    h, w = edges_a.shape
    grid_h, grid_w = 4, 4
    cell_h, cell_w = h // grid_h, w // grid_w

    hist_a = np.zeros(grid_h * grid_w, dtype=np.float32)
    hist_b = np.zeros(grid_h * grid_w, dtype=np.float32)

    for i in range(grid_h):
        for j in range(grid_w):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            hist_a[i * grid_w + j] = np.sum(edges_a[y1:y2, x1:x2])
            hist_b[i * grid_w + j] = np.sum(edges_b[y1:y2, x1:x2])

    # Cosine similarity between spatial edge histograms
    norm_a = np.linalg.norm(hist_a)
    norm_b = np.linalg.norm(hist_b)
    if norm_a == 0 or norm_b == 0:
        return 100.0 if norm_a == norm_b else 0.0

    cosine_sim = float(np.dot(hist_a, hist_b) / (norm_a * norm_b))
    return round(max(0, min(100, cosine_sim * 100)), 1)


def compute_spatial_color_histogram(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """
    Divide image into 4x4 grid, compute H-S histogram per cell,
    compare corresponding cells using CHI-SQUARE, and average.
    Captures both color AND spatial distribution.
    Fixes the pure-color CORREL=100% bug from global histogram.
    """
    hsv_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2HSV)
    hsv_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2HSV)

    h, w = hsv_a.shape[:2]
    grid_h, grid_w = 4, 4
    cell_h, cell_w = h // grid_h, w // grid_w

    similarities = []
    for i in range(grid_h):
        for j in range(grid_w):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w

            cell_a = hsv_a[y1:y2, x1:x2]
            cell_b = hsv_b[y1:y2, x1:x2]

            # 2D H-S histogram per cell
            hist_a = cv2.calcHist([cell_a], [0, 1], None, [30, 32], [0, 180, 0, 256])
            hist_b = cv2.calcHist([cell_b], [0, 1], None, [30, 32], [0, 180, 0, 256])

            # CHI-SQUARE: lower = more similar. Map to [0, 100].
            # For normalized histograms, practical max chi2 ~10.
            chi2 = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CHISQR)
            sim = float(max(0, 1 - chi2 / 10.0) * 100)
            similarities.append(sim)

    return round(float(np.mean(similarities)), 1)


def compute_dominant_color_similarity(img_a: np.ndarray, img_b: np.ndarray, k: int = 5) -> float:
    """
    Extract top-k dominant colors via k-means, compare palettes.
    Uses CIELAB color space for perceptual distance.
    Bidirectional matching: for each color in A, find closest in B, and vice versa.
    """
    # Sample pixels for speed (use every 4th pixel)
    pixels_a = img_a[::4, ::4].reshape(-1, 3).astype(np.float32)
    pixels_b = img_b[::4, ::4].reshape(-1, 3).astype(np.float32)

    # K-means clustering
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels_a, centers_a = cv2.kmeans(
        pixels_a, k, None, criteria, 3, cv2.KMEANS_RANDOM_CENTERS
    )
    _, labels_b, centers_b = cv2.kmeans(
        pixels_b, k, None, criteria, 3, cv2.KMEANS_RANDOM_CENTERS
    )

    # Convert centers to LAB for perceptual distance
    centers_a_lab = cv2.cvtColor(np.uint8([centers_a]), cv2.COLOR_RGB2LAB)[0]
    centers_b_lab = cv2.cvtColor(np.uint8([centers_b]), cv2.COLOR_RGB2LAB)[0]

    # Compute weight (cluster population) for each center
    weights_a = np.bincount(labels_a.flatten(), minlength=k).astype(np.float32)
    weights_b = np.bincount(labels_b.flatten(), minlength=k).astype(np.float32)
    weights_a /= weights_a.sum()
    weights_b /= weights_b.sum()

    # For each color in A, find closest color in B (weighted)
    # CIELAB Euclidean distance; max theoretical distance ~442
    max_lab_dist = 442.0
    total_sim = 0.0
    for i in range(k):
        if weights_a[i] == 0:
            continue
        distances = np.linalg.norm(centers_a_lab[i] - centers_b_lab, axis=1)
        min_dist = distances.min()
        sim = max(0, 1 - min_dist / max_lab_dist)
        total_sim += float(sim * weights_a[i])

    # Bidirectional: also check B -> A
    total_sim_b = 0.0
    for i in range(k):
        if weights_b[i] == 0:
            continue
        distances = np.linalg.norm(centers_b_lab[i] - centers_a_lab, axis=1)
        min_dist = distances.min()
        sim = max(0, 1 - min_dist / max_lab_dist)
        total_sim_b += float(sim * weights_b[i])

    # Average bidirectional similarity, ensure Python float
    return round(float((total_sim + total_sim_b) / 2 * 100), 1)


def generate_heatmap(diff_map: Optional[np.ndarray]) -> Optional[str]:
    """
    Generate a base64-encoded heatmap image from SSIM diff map.
    Returns None if diff_map is not available.
    """
    if diff_map is None:
        return None

    # Normalize diff_map to [0, 255]
    diff_norm = np.clip(1.0 - diff_map, 0, 1)  # Invert: high diff = bright
    diff_uint8 = (diff_norm * 255).astype(np.uint8)

    # Apply colormap (COLORMAP_JET: blue=low, red=high)
    heatmap = cv2.applyColorMap(diff_uint8, cv2.COLORMAP_JET)

    # Encode to base64
    _, buf = cv2.imencode(".png", heatmap)
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def generate_insight(
    ssim: float, edge: float, spatial_color: float, phash: float, dominant_color: float, combined: float
) -> str:
    """Generate human-readable insight based on 5-level similarity spec and new metrics."""
    # Level 5: Almost identical (80-100)
    if combined >= 80:
        if dominant_color < 90:
            return "两张图几乎完全相同，仅存在轻微的颜色/饱和度调整。肉眼几乎无法区分差异。"
        if edge < ssim - 5:
            return "结构和色彩一致，但元素位置存在微调 — 可能为响应式布局微调或组件间距变化。"
        return "两张图几乎完全相同，仅存在像素级微调（如阴影、圆角、颜色饱和度的细微变化）。"

    # Level 4: Highly similar (60-80)
    if combined >= 60:
        if dominant_color < 50 and edge > 80:
            return "整体框架和布局高度一致，但主色调发生了变化 — 可能为夜间模式或主题切换。"
        if edge < 60:
            return "主结构一致，但元素位置存在调整，可能为响应式布局变化或组件重组。"
        return "整体框架和布局高度一致，但存在局部信息增减（如新增文字、图标或状态提示）。"

    # Level 3: Partially similar (40-60)
    if combined >= 40:
        if edge > 60 and ssim < 50:
            return "页面骨架相似，但组件内容发生了变化 — 可能为模块替换或内容更新。"
        return "整体布局框架相似，但局部模块内容发生了替换。顶部/底部区域保持一致，中间内容区域存在较大差异。"

    # Level 2: Slightly similar (20-40)
    if combined >= 20:
        if spatial_color > ssim and spatial_color > edge:
            return "色彩方案接近，但页面结构和内容布局差异较大 — 可能为不同功能的同类界面。"
        return "两张图在整体框架或视觉风格上存在一定相似性，但布局方向、主要色彩或内容区域存在明显差异。"

    # Level 1: Completely different (0-20)
    return "两张图在结构、色彩和内容上均无显著关联，属于完全不同的界面。请确认是否上传了正确的对比图片。"


def get_label(combined: float) -> str:
    """Get similarity label based on 5-level similarity spec."""
    if combined >= 80:
        return "几乎一致"
    if combined >= 60:
        return "高度相似"
    if combined >= 40:
        return "中度相似"
    if combined >= 20:
        return "略有相似"
    return "完全不同"


# --- Routes ---

@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version="2.0.0")


@app.post("/api/compare", response_model=SimilarityResponse)
async def compare(
    image_a: UploadFile = File(..., description="First UI image"),
    image_b: UploadFile = File(..., description="Second UI image"),
):
    """
    Compare two UI images and return similarity scores.

    Phase 2 metrics:
    - ssim: color structural similarity (30%)
    - edge: Canny edge spatial similarity (25%)
    - spatial_color: 4x4 grid color histogram (25%)
    - phash: perceptual hash 16x16 (10%)
    - dominant_color: K-means palette similarity (10%)
    """
    start = time.time()

    try:
        # Validate
        validate_file(image_a)
        validate_file(image_b)

        # Load
        arr_a = load_image(image_a)
        arr_b = load_image(image_b)

        # Resize to match
        arr_a, arr_b = resize_to_match(arr_a, arr_b)

        logger.info(f"Image sizes after resize: {arr_a.shape}")

        # Compute Phase 2 similarity metrics
        ssim_score, diff_map = compute_ssim(arr_a, arr_b)
        edge_score = compute_edge_similarity(arr_a, arr_b)
        spatial_color_score = compute_spatial_color_histogram(arr_a, arr_b)
        phash_score = compute_phash(arr_a, arr_b)
        dominant_color_score = compute_dominant_color_similarity(arr_a, arr_b)

        # Weighted fusion
        combined = (
            WEIGHTS["ssim"] * ssim_score
            + WEIGHTS["edge"] * edge_score
            + WEIGHTS["spatial_color"] * spatial_color_score
            + WEIGHTS["phash"] * phash_score
            + WEIGHTS["dominant_color"] * dominant_color_score
        )

        # Semantic adjustment for theme changes (Level 2 detection)
        # If edge similarity is high but spatial color AND dominant color are both low → theme change
        # Brightness changes preserve dominant colors, so dominant_color check prevents false positives
        if edge_score > 85 and spatial_color_score < 40 and dominant_color_score < 60:
            # Compress toward Level 2 range: structure preserved, colors changed
            theme_score = spatial_color_score * 0.5 + edge_score * 0.3 + (100 - edge_score) * 0.2
            combined = combined * 0.6 + theme_score * 0.4

        combined = round(combined, 1)

        elapsed_ms = round((time.time() - start) * 1000, 1)

        logger.info(
            f"Scores: combined={combined}, ssim={ssim_score}, "
            f"edge={edge_score}, spatial_color={spatial_color_score}, "
            f"phash={phash_score}, dominant={dominant_color_score} in {elapsed_ms}ms"
        )

        # Generate heatmap
        heatmap_b64 = generate_heatmap(diff_map)

        return JSONResponse(content={
            "combined": combined,
            "ssim": ssim_score,
            "edge": edge_score,
            "spatial_color": spatial_color_score,
            "phash": phash_score,
            "dominant_color": dominant_color_score,
            "insight": generate_insight(
                ssim_score, edge_score, spatial_color_score, phash_score, dominant_color_score, combined
            ),
            "label": get_label(combined),
            "processing_time_ms": elapsed_ms,
            "heatmap": heatmap_b64,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error during comparison: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@app.post("/api/compare/batch")
async def batch_compare(
    images: List[UploadFile] = File(..., description="Even number of images (pairs)"),
):
    """
    Compare multiple pairs of images at once.
    Images are compared in order: (0,1), (2,3), etc.
    """
    if len(images) % 2 != 0:
        raise HTTPException(status_code=400, detail="Must provide an even number of images.")

    results = []
    for i in range(0, len(images), 2):
        img_a = images[i]
        img_b = images[i + 1]

        validate_file(img_a)
        validate_file(img_b)

        arr_a = load_image(img_a)
        arr_b = load_image(img_b)
        arr_a, arr_b = resize_to_match(arr_a, arr_b)

        ssim_score, diff_map = compute_ssim(arr_a, arr_b)
        edge_score = compute_edge_similarity(arr_a, arr_b)
        spatial_color_score = compute_spatial_color_histogram(arr_a, arr_b)
        phash_score = compute_phash(arr_a, arr_b)
        dominant_color_score = compute_dominant_color_similarity(arr_a, arr_b)

        combined = round(
            WEIGHTS["ssim"] * ssim_score
            + WEIGHTS["edge"] * edge_score
            + WEIGHTS["spatial_color"] * spatial_color_score
            + WEIGHTS["phash"] * phash_score
            + WEIGHTS["dominant_color"] * dominant_color_score,
            1,
        )

        results.append({
            "pair": f"{i // 2 + 1}",
            "file_a": img_a.filename,
            "file_b": img_b.filename,
            "combined": combined,
            "ssim": ssim_score,
            "edge": edge_score,
            "spatial_color": spatial_color_score,
            "phash": phash_score,
            "dominant_color": dominant_color_score,
            "label": get_label(combined),
        })

    return {"results": results, "total_pairs": len(results)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
