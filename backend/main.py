"""
UI Image Similarity Comparison - Backend API
FastAPI server for computing similarity between two UI images.
Phase 3: Content-masked SSIM + dHash(16) + Edge(8x8+orientation) + Spatial color + Dominant color
         + Content density gating + Disagreement penalty.
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
    description="Compute similarity between two UI images using content-masked SSIM, dHash, edge layout, spatial color, and dominant color fusion.",
    version="3.0.0",
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

# Phase 3 weight configuration (based on real UI test feedback)
# SSIM 35% (content-masked, now the primary metric), Edge 25% (8x8+orientation),
# Spatial color 20%, dHash 10% (replaces pHash), Dominant 10%
# Content density is a gating multiplier, not a weighted metric
WEIGHTS = {
    "ssim": 0.35,
    "edge": 0.25,
    "spatial_color": 0.20,
    "dhash": 0.10,
    "dominant_color": 0.10,
}


# --- Pydantic Models ---

class SimilarityResponse(BaseModel):
    combined: float
    ssim: float
    edge: float
    spatial_color: float
    dhash: float
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
    """Resize the larger image to match the smaller one."""
    ha, wa = img_a.shape[:2]
    hb, wb = img_b.shape[:2]
    if (ha, wa) != (hb, wb):
        target_h, target_w = min(ha, hb), min(wa, wb)
        img_a = cv2.resize(img_a, (target_w, target_h), interpolation=cv2.INTER_AREA)
        img_b = cv2.resize(img_b, (target_w, target_h), interpolation=cv2.INTER_AREA)
    return img_a, img_b


# --- Phase 3: Content-aware SSIM ---

def compute_content_mask(img: np.ndarray) -> np.ndarray:
    """
    Detect content (textured/edge-rich) vs background (uniform) regions.
    Returns binary mask: 255 = content, 0 = background.

    Strategy: Sobel gradient magnitude → threshold → morphological cleanup.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float64)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2)

    # Threshold: pixels with gradient magnitude > 10 are "content"
    mask = (mag > 10.0).astype(np.uint8) * 255

    # Morphological operations: dilate to capture full elements, then erode noise
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=2)
    mask = cv2.erode(mask, np.ones((2, 2), np.uint8), iterations=1)

    return mask


def compute_ssim(img_a: np.ndarray, img_b: np.ndarray) -> tuple[float, Optional[np.ndarray]]:
    """
    Compute content-masked SSIM score.
    Uses Sobel gradient to detect background regions, sets them to neutral gray (128),
    then computes grayscale SSIM. This prevents large uniform backgrounds from inflating the score.

    Returns (score_0_to_100, diff_map_or_None).
    """
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)

    # Build content masks
    mask_a = compute_content_mask(img_a)
    mask_b = compute_content_mask(img_b)

    # Union mask: a pixel is "content" if EITHER image has content there
    # This ensures we compare regions where at least one image has content
    content_mask = np.maximum(mask_a, mask_b)

    # Apply mask: background pixels set to 128 (neutral gray)
    masked_a = gray_a.copy()
    masked_b = gray_b.copy()
    masked_a[content_mask == 0] = 128
    masked_b[content_mask == 0] = 128

    # Compute content density for logging
    total_pixels = gray_a.shape[0] * gray_a.shape[1]
    density_a = float(np.sum(mask_a > 0)) / total_pixels
    density_b = float(np.sum(mask_b > 0)) / total_pixels
    logger.info(f"Content density: A={density_a:.2%}, B={density_b:.2%}")

    # Compute SSIM on masked images
    score, _ = ssim(masked_a, masked_b, full=True, data_range=255)
    score_pct = max(0, min(100, float(score) * 100))

    # Generate diff_map from grayscale (for heatmap visualization)
    _, diff_map = ssim(gray_a, gray_b, full=True)

    return round(score_pct, 1), diff_map


# --- Phase 3: dHash replaces pHash ---

def compute_dhash(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """
    Compute difference hash (dHash) at 16x16 resolution.
    dHash compares adjacent pixel gradients (pixel[i] > pixel[i+1]), making it
    sensitive to UI element boundaries and text lines rather than flat color regions.

    Unlike pHash (DCT-based), dHash directly captures positional gradient patterns,
    which distinguishes different UI layouts much better.
    """
    hash_a = imagehash.dhash(Image.fromarray(img_a), hash_size=16)
    hash_b = imagehash.dhash(Image.fromarray(img_b), hash_size=16)
    max_bits = 256  # 16x16
    hamming = int(hash_a - hash_b)
    similarity = (max_bits - hamming) / max_bits * 100
    return round(max(0, min(100, similarity)), 1)


# --- Phase 3: Edge similarity upgraded to 8x8 + orientation ---

def compute_edge_similarity(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """
    Canny edge detection + 8x8 spatial histogram + 4-bin orientation histogram.

    8x8 grid (64 cells) provides enough resolution to distinguish:
    - Full-screen list (edges in all cells) vs small popup (edges only in center)
    - Top-heavy page vs bottom-heavy page
    - Grid layout (album) vs linear list

    Orientation histogram (4 bins) distinguishes:
    - List views (predominantly horizontal edges) vs popups (mixed orientations)
    """
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)

    blur_a = cv2.GaussianBlur(gray_a, (5, 5), 0)
    blur_b = cv2.GaussianBlur(gray_b, (5, 5), 0)

    edges_a = cv2.Canny(blur_a, 50, 150)
    edges_b = cv2.Canny(blur_b, 50, 150)

    # --- 8x8 spatial histogram ---
    h, w = edges_a.shape
    grid_h, grid_w = 8, 8
    cell_h, cell_w = h // grid_h, w // grid_w

    hist_a = np.zeros(grid_h * grid_w, dtype=np.float32)
    hist_b = np.zeros(grid_h * grid_w, dtype=np.float32)

    for i in range(grid_h):
        for j in range(grid_w):
            y1, y2 = i * cell_h, (i + 1) * cell_h
            x1, x2 = j * cell_w, (j + 1) * cell_w
            hist_a[i * grid_w + j] = float(np.sum(edges_a[y1:y2, x1:x2]))
            hist_b[i * grid_w + j] = float(np.sum(edges_b[y1:y2, x1:x2]))

    norm_a = np.linalg.norm(hist_a)
    norm_b = np.linalg.norm(hist_b)
    spatial_sim = 0.0
    if norm_a > 0 and norm_b > 0:
        spatial_sim = float(np.dot(hist_a, hist_b) / (norm_a * norm_b))

    # --- Edge orientation histogram (4 bins: -pi..pi) ---
    sobel_x_a = cv2.Sobel(blur_a, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y_a = cv2.Sobel(blur_a, cv2.CV_64F, 0, 1, ksize=3)
    sobel_x_b = cv2.Sobel(blur_b, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y_b = cv2.Sobel(blur_b, cv2.CV_64F, 0, 1, ksize=3)

    angles_a = np.arctan2(sobel_y_a[edges_a > 0], sobel_x_a[edges_a > 0])
    angles_b = np.arctan2(sobel_y_b[edges_b > 0], sobel_x_b[edges_b > 0])

    orient_sim = 0.0
    if len(angles_a) > 0 and len(angles_b) > 0:
        hist_orient_a, _ = np.histogram(angles_a, bins=4, range=(-np.pi, np.pi))
        hist_orient_b, _ = np.histogram(angles_b, bins=4, range=(-np.pi, np.pi))
        hist_orient_a = hist_orient_a.astype(np.float32)
        hist_orient_b = hist_orient_b.astype(np.float32)
        norm_oa = np.linalg.norm(hist_orient_a)
        norm_ob = np.linalg.norm(hist_orient_b)
        if norm_oa > 0 and norm_ob > 0:
            orient_sim = float(np.dot(hist_orient_a, hist_orient_b) / (norm_oa * norm_ob))

    # Combined: 70% spatial position + 30% orientation
    combined = 0.7 * spatial_sim + 0.3 * orient_sim
    return round(max(0, min(100, combined * 100)), 1)


# --- Spatial color histogram (unchanged from Phase 2) ---

def compute_spatial_color_histogram(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """
    4x4 grid, per-cell H-S histogram, CHI-SQUARE distance, averaged.
    Captures both color AND spatial distribution.
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

            hist_a = cv2.calcHist([cell_a], [0, 1], None, [30, 32], [0, 180, 0, 256])
            hist_b = cv2.calcHist([cell_b], [0, 1], None, [30, 32], [0, 180, 0, 256])

            chi2 = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CHISQR)
            sim = float(max(0, 1 - chi2 / 10.0) * 100)
            similarities.append(sim)

    return round(float(np.mean(similarities)), 1)


# --- Dominant color (unchanged from Phase 2) ---

def compute_dominant_color_similarity(img_a: np.ndarray, img_b: np.ndarray, k: int = 5) -> float:
    """
    K-means top-k dominant colors, CIELAB bidirectional distance.
    """
    pixels_a = img_a[::4, ::4].reshape(-1, 3).astype(np.float32)
    pixels_b = img_b[::4, ::4].reshape(-1, 3).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels_a, centers_a = cv2.kmeans(
        pixels_a, k, None, criteria, 3, cv2.KMEANS_RANDOM_CENTERS
    )
    _, labels_b, centers_b = cv2.kmeans(
        pixels_b, k, None, criteria, 3, cv2.KMEANS_RANDOM_CENTERS
    )

    centers_a_lab = cv2.cvtColor(np.uint8([centers_a]), cv2.COLOR_RGB2LAB)[0]
    centers_b_lab = cv2.cvtColor(np.uint8([centers_b]), cv2.COLOR_RGB2LAB)[0]

    weights_a = np.bincount(labels_a.flatten(), minlength=k).astype(np.float32)
    weights_b = np.bincount(labels_b.flatten(), minlength=k).astype(np.float32)
    weights_a /= weights_a.sum()
    weights_b /= weights_b.sum()

    max_lab_dist = 442.0
    total_sim = 0.0
    for i in range(k):
        if weights_a[i] == 0:
            continue
        distances = np.linalg.norm(centers_a_lab[i] - centers_b_lab, axis=1)
        min_dist = distances.min()
        sim = max(0, 1 - min_dist / max_lab_dist)
        total_sim += float(sim * weights_a[i])

    total_sim_b = 0.0
    for i in range(k):
        if weights_b[i] == 0:
            continue
        distances = np.linalg.norm(centers_b_lab[i] - centers_a_lab, axis=1)
        min_dist = distances.min()
        sim = max(0, 1 - min_dist / max_lab_dist)
        total_sim_b += float(sim * weights_b[i])

    return round(float((total_sim + total_sim_b) / 2 * 100), 1)


# --- Phase 3: Content density gating ---

def compute_content_density(img: np.ndarray) -> float:
    """
    Compute mean gradient magnitude as a proxy for "content density".
    Higher value = more text/icons/edges. Lower value = more illustration/blank space.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float64)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return float(np.mean(np.sqrt(gx ** 2 + gy ** 2)))


def apply_density_gate(combined: float, density_a: float, density_b: float) -> float:
    """
    If two images have fundamentally different content complexity, penalize the score.
    Content density is a structural precondition, not a similarity dimension.
    """
    if density_a == 0 and density_b == 0:
        return combined
    if density_a == 0 or density_b == 0:
        return combined * 0.3

    ratio = min(density_a, density_b) / max(density_a, density_b)
    if ratio < 0.5:
        # Significant complexity mismatch: scale down
        gate = max(0.2, ratio * 1.5)  # ratio=0.5 → gate=0.75, ratio=0.2 → gate=0.3
        return combined * gate
    return combined


# --- Phase 3: Disagreement penalty ---

def apply_disagreement_penalty(combined: float, scores: list[float]) -> float:
    """
    When individual metrics disagree significantly (high std dev), penalize the combined score.
    This prevents cases where one metric is high and another is near zero from averaging out to a misleading middle value.
    """
    if len(scores) < 2:
        return combined

    std_dev = float(np.std(scores))
    if std_dev > 30:
        # Strong disagreement: apply penalty factor
        # std_dev=30 → factor=1.0, std_dev=50 → factor=0.5, std_dev=70 → factor=0.25
        factor = max(0.25, 1.0 - (std_dev - 30) / 50.0)
        return combined * factor

    return combined


# --- Heatmap (unchanged) ---

def generate_heatmap(diff_map: Optional[np.ndarray]) -> Optional[str]:
    if diff_map is None:
        return None

    diff_norm = np.clip(1.0 - diff_map, 0, 1)
    diff_uint8 = (diff_norm * 255).astype(np.uint8)
    heatmap = cv2.applyColorMap(diff_uint8, cv2.COLORMAP_JET)
    _, buf = cv2.imencode(".png", heatmap)
    return base64.b64encode(buf.tobytes()).decode("utf-8")


# --- Insight ---

def generate_insight(
    ssim: float, edge: float, spatial_color: float, dhash: float, dominant_color: float, combined: float
) -> str:
    """Generate human-readable insight based on 5-level similarity spec."""
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


# --- Label ---

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
    return HealthResponse(status="ok", version="3.0.0")


@app.post("/api/compare", response_model=SimilarityResponse)
async def compare(
    image_a: UploadFile = File(..., description="First UI image"),
    image_b: UploadFile = File(..., description="Second UI image"),
):
    """
    Compare two UI images and return similarity scores.

    Phase 3 metrics:
    - ssim: content-masked structural similarity (35%)
    - edge: Canny edge 8x8 spatial + orientation (25%)
    - spatial_color: 4x4 grid color histogram (20%)
    - dhash: difference hash 16x16 (10%)
    - dominant_color: K-means palette similarity (10%)
    + Content density gating (structural precondition)
    + Disagreement penalty (cross-metric consistency)
    """
    start = time.time()

    try:
        validate_file(image_a)
        validate_file(image_b)

        arr_a = load_image(image_a)
        arr_b = load_image(image_b)
        arr_a, arr_b = resize_to_match(arr_a, arr_b)

        logger.info(f"Image sizes after resize: {arr_a.shape}")

        # Compute Phase 3 similarity metrics
        ssim_score, diff_map = compute_ssim(arr_a, arr_b)
        edge_score = compute_edge_similarity(arr_a, arr_b)
        spatial_color_score = compute_spatial_color_histogram(arr_a, arr_b)
        dhash_score = compute_dhash(arr_a, arr_b)
        dominant_color_score = compute_dominant_color_similarity(arr_a, arr_b)

        # Weighted fusion
        combined = (
            WEIGHTS["ssim"] * ssim_score
            + WEIGHTS["edge"] * edge_score
            + WEIGHTS["spatial_color"] * spatial_color_score
            + WEIGHTS["dhash"] * dhash_score
            + WEIGHTS["dominant_color"] * dominant_color_score
        )

        # Content density gating
        density_a = compute_content_density(arr_a)
        density_b = compute_content_density(arr_b)
        combined = apply_density_gate(combined, density_a, density_b)

        # Disagreement penalty
        scores = [ssim_score, edge_score, spatial_color_score, dhash_score, dominant_color_score]
        combined = apply_disagreement_penalty(combined, scores)

        # Theme change detection (edge high + color low = skin/theme swap)
        if edge_score > 75 and spatial_color_score < 40 and dominant_color_score < 60:
            theme_score = spatial_color_score * 0.5 + edge_score * 0.3 + (100 - edge_score) * 0.2
            combined = combined * 0.6 + theme_score * 0.4

        combined = round(combined, 1)

        elapsed_ms = round((time.time() - start) * 1000, 1)

        logger.info(
            f"Scores: combined={combined}, ssim={ssim_score}, "
            f"edge={edge_score}, spatial_color={spatial_color_score}, "
            f"dhash={dhash_score}, dominant={dominant_color_score} in {elapsed_ms}ms"
        )

        heatmap_b64 = generate_heatmap(diff_map)

        return JSONResponse(content={
            "combined": combined,
            "ssim": ssim_score,
            "edge": edge_score,
            "spatial_color": spatial_color_score,
            "dhash": dhash_score,
            "dominant_color": dominant_color_score,
            "insight": generate_insight(
                ssim_score, edge_score, spatial_color_score, dhash_score, dominant_color_score, combined
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
    """Compare multiple pairs of images at once."""
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
        dhash_score = compute_dhash(arr_a, arr_b)
        dominant_color_score = compute_dominant_color_similarity(arr_a, arr_b)

        scores = [ssim_score, edge_score, spatial_color_score, dhash_score, dominant_color_score]
        combined = (
            WEIGHTS["ssim"] * ssim_score
            + WEIGHTS["edge"] * edge_score
            + WEIGHTS["spatial_color"] * spatial_color_score
            + WEIGHTS["dhash"] * dhash_score
            + WEIGHTS["dominant_color"] * dominant_color_score
        )
        combined = apply_disagreement_penalty(combined, scores)
        combined = round(combined, 1)

        results.append({
            "pair": f"{i // 2 + 1}",
            "file_a": img_a.filename,
            "file_b": img_b.filename,
            "combined": combined,
            "ssim": ssim_score,
            "edge": edge_score,
            "spatial_color": spatial_color_score,
            "dhash": dhash_score,
            "dominant_color": dominant_color_score,
            "label": get_label(combined),
        })

    return {"results": results, "total_pairs": len(results)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
