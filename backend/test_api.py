"""
Test suite for UI Image Compare API - Phase 3 (FastAPI backend).

Phase 3 metrics: Content-masked SSIM + dHash(16x16) + Edge 8x8+orientation + Spatial color + Dominant color.
Weights: SSIM 35%, Edge 25%, SpatialColor 20%, dHash 10%, Dominant 10%.
Content density gating + disagreement penalty applied.

Run: cd backend && source venv/bin/activate && pytest test_api.py -v
"""

from __future__ import annotations

import io
import base64
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

import pytest


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Image helpers: create test images in-memory using Pillow
# ---------------------------------------------------------------------------

def make_solid_color(rgb: tuple[int, int, int], size: tuple[int, int] = (200, 200)) -> bytes:
    """Return PNG bytes for a solid-color image."""
    img = Image.new("RGB", size, rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def make_gradient(size: tuple[int, int] = (200, 200)) -> bytes:
    """Return PNG bytes for a horizontal gradient image."""
    img = Image.new("RGB", size)
    pixels = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            pixels[x, y] = (int(x / size[0] * 255), 128, 128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def make_inverted(data: bytes) -> bytes:
    """Return PNG bytes that is the color-inverted version of the input."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    inverted = Image.new("RGB", img.size)
    pixels = inverted.load()
    orig = img.load()
    for x in range(img.size[0]):
        for y in range(img.size[1]):
            pixels[x, y] = tuple(255 - c for c in orig[x, y])
    buf = io.BytesIO()
    inverted.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def make_brightened(data: bytes, factor: float = 1.3) -> bytes:
    """Return PNG bytes with increased brightness."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    brightened = Image.new("RGB", img.size)
    pixels = brightened.load()
    orig = img.load()
    for x in range(img.size[0]):
        for y in range(img.size[1]):
            pixels[x, y] = tuple(min(255, int(c * factor)) for c in orig[x, y])
    buf = io.BytesIO()
    brightened.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def make_resized(data: bytes, new_size: tuple[int, int]) -> bytes:
    """Return PNG bytes resized to new_size."""
    img = Image.open(io.BytesIO(data)).convert("RGB").resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def make_checkerboard(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int],
                      size: tuple[int, int] = (200, 200), cell: int = 20) -> bytes:
    """Return PNG bytes for a checkerboard pattern."""
    img = Image.new("RGB", size)
    pixels = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            if ((x // cell) + (y // cell)) % 2 == 0:
                pixels[x, y] = rgb1
            else:
                pixels[x, y] = rgb2
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def make_gradient_color(rgb_end: tuple[int, int, int], size: tuple[int, int] = (200, 200)) -> bytes:
    """Return PNG bytes for a black->color horizontal gradient."""
    img = Image.new("RGB", size)
    pixels = img.load()
    for x in range(size[0]):
        r_val = int(rgb_end[0] * x / size[0])
        g_val = int(rgb_end[1] * x / size[0])
        b_val = int(rgb_end[2] * x / size[0])
        for y in range(size[1]):
            pixels[x, y] = (r_val, g_val, b_val)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def make_random_noise(seed: int = 42, size: tuple[int, int] = (200, 200)) -> bytes:
    """Return PNG bytes for a random noise image (deterministic via seed)."""
    rng = np.random.RandomState(seed)
    arr = rng.randint(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def image_bytes_to_file(bytes_data: bytes, filename: str = "test.png") -> tuple:
    """Convert bytes to a tuple suitable for TestClient file upload."""
    return (filename, bytes_data, "image/png")


# ---------------------------------------------------------------------------
# A. Health Check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    """Health check endpoint tests."""

    def test_health_check(self, client):
        """GET /api/health should return status=ok."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "3.0.0"


# ---------------------------------------------------------------------------
# B. Normal Functionality Tests
# ---------------------------------------------------------------------------

class TestCompare:
    """Core compare endpoint tests."""

    def test_identical_images(self, client):
        """Two identical UI-like images should return ~100% combined score."""
        # Phase 3: use a UI-like image with structure (not solid color)
        img_bytes = make_solid_color((100, 150, 200))
        # Add some "UI structure" - a rectangle pattern
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 180, 50], fill=(255, 255, 255))
        draw.rectangle([20, 60, 180, 180], fill=(240, 240, 240))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        ui_bytes = buf.read()

        resp = client.post(
            "/api/compare",
            files={"image_a": image_bytes_to_file(ui_bytes, "a.png"),
                   "image_b": image_bytes_to_file(ui_bytes, "b.png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["combined"] == pytest.approx(100.0, abs=2.0)
        assert data["ssim"] == pytest.approx(100.0, abs=2.0)
        assert data["dhash"] == pytest.approx(100.0, abs=2.0)
        assert data["dominant_color"] == pytest.approx(100.0, abs=2.0)

    def test_different_images(self, client):
        """Two completely different random-noise images should return a low combined score."""
        img_a = make_random_noise(seed=1, size=(32, 32))
        img_b = make_random_noise(seed=999, size=(32, 32))
        resp = client.post(
            "/api/compare",
            files={"image_a": image_bytes_to_file(img_a, "noise_a.png"),
                   "image_b": image_bytes_to_file(img_b, "noise_b.png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["combined"] < 40, f"Expected low score for different noise, got {data['combined']}"

    def test_color_shift(self, client):
        """Same gradient structure with different hues (theme change scenario).

        Black->red vs black->blue gradient:
        - Grayscale SSIM stays high (same luminance structure)
        - Edge similarity depends on gradient structure
        - Spatial color drops significantly (colors differ per grid cell)
        - Dominant color drops (red vs blue)
        - Combined should fall to Level 2-3 range (slightly to moderately similar)
        """
        grad_red = make_gradient_color((255, 0, 0))
        grad_blue = make_gradient_color((0, 0, 255))
        resp = client.post(
            "/api/compare",
            files={"image_a": image_bytes_to_file(grad_red, "red_grad.png"),
                   "image_b": image_bytes_to_file(grad_blue, "blue_grad.png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Grayscale SSIM sees same luminance structure
        assert data["ssim"] > 50, f"Grayscale SSIM should be reasonable, got {data['ssim']}"
        # Spatial color should be low (different colors)
        assert data["spatial_color"] < 60, f"Spatial color should be low, got {data['spatial_color']}"
        # Combined should reflect theme change
        assert data["combined"] < 70, f"Theme change combined should be < 70, got {data['combined']}"

    def test_brightness_change(self, client):
        """Brightness-changed images should still have relatively high SSIM and edge scores."""
        original = make_gradient()
        brightened = make_brightened(original, factor=1.3)
        resp = client.post(
            "/api/compare",
            files={"image_a": image_bytes_to_file(original, "orig.png"),
                   "image_b": image_bytes_to_file(brightened, "bright.png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ssim"] > 50, f"SSIM should be reasonable for brightness changes, got {data['ssim']}"

    def test_resize_tolerance(self, client):
        """Different-sized images should be auto-resized and compared."""
        # Create high-contrast UI-like images with structure
        img_a = make_checkerboard((0, 0, 0), (255, 255, 255), size=(200, 200), cell=20)
        img_b = make_checkerboard((0, 0, 0), (255, 255, 255), size=(300, 300), cell=30)
        resp = client.post(
            "/api/compare",
            files={"image_a": image_bytes_to_file(img_a, "small.png"),
                   "image_b": image_bytes_to_file(img_b, "large.png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["combined"] > 70, "Same pattern at different sizes should score high after resize"

    def test_response_fields(self, client):
        """Response must contain all Phase 3 required fields."""
        img_bytes = make_solid_color((80, 80, 80))
        resp = client.post(
            "/api/compare",
            files={"image_a": image_bytes_to_file(img_bytes, "a.png"),
                   "image_b": image_bytes_to_file(img_bytes, "b.png")},
        )
        data = resp.json()
        required_fields = {"combined", "ssim", "edge", "spatial_color", "dhash",
                           "dominant_color", "insight", "label", "processing_time_ms", "heatmap"}
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# C. Format Support
# ---------------------------------------------------------------------------

class TestFormatSupport:
    """Test various image format uploads."""

    @pytest.fixture(params=["png", "jpg", "bmp"])
    def format_and_ext(self, request):
        return request.param

    def test_format_upload(self, client, format_and_ext):
        """PNG, JPG, BMP formats should be accepted."""
        fmt = format_and_ext
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        buf = io.BytesIO()
        if fmt == "jpg":
            img.save(buf, format="JPEG")
            mime = "image/jpeg"
        elif fmt == "bmp":
            img.save(buf, format="BMP")
            mime = "image/bmp"
        else:
            img.save(buf, format="PNG")
            mime = "image/png"
        buf.seek(0)
        data = buf.read()

        resp = client.post(
            "/api/compare",
            files={"image_a": (f"a.{fmt}", data, mime),
                   "image_b": (f"b.{fmt}", data, mime)},
        )
        assert resp.status_code == 200

    def test_webp_format(self, client):
        """WebP format should be accepted if Pillow supports it."""
        try:
            img = Image.new("RGB", (100, 100), (64, 128, 192))
            buf = io.BytesIO()
            img.save(buf, format="WEBP")
            buf.seek(0)
            data = buf.read()
        except Exception:
            pytest.skip("WebP not supported by Pillow in this environment")

        resp = client.post(
            "/api/compare",
            files={"image_a": ("a.webp", data, "image/webp"),
                   "image_b": ("b.webp", data, "image/webp")},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# D. Error Handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Error handling tests."""

    def test_unsupported_format(self, client):
        """Uploading a .txt file should return 400."""
        txt_data = b"This is not an image file."
        img_png = make_solid_color((1, 2, 3))
        resp = client.post(
            "/api/compare",
            files={"image_a": ("bad.txt", txt_data, "text/plain"),
                   "image_b": ("good.png", img_png, "image/png")},
        )
        assert resp.status_code == 400

    def test_missing_file(self, client):
        """Uploading only one image should return 422 (FastAPI validation)."""
        img_bytes = make_solid_color((50, 50, 50))
        resp = client.post(
            "/api/compare",
            files={"image_a": image_bytes_to_file(img_bytes, "only.png")},
        )
        assert resp.status_code == 422

    def test_both_empty(self, client):
        """Two empty files should be handled gracefully (error or low scores)."""
        empty = b""
        resp = client.post(
            "/api/compare",
            files={"image_a": ("empty_a.png", empty, "image/png"),
                   "image_b": ("empty_b.png", empty, "image/png")},
        )
        assert resp.status_code in (200, 400, 500)


# ---------------------------------------------------------------------------
# E. Algorithm Validation
# ---------------------------------------------------------------------------

class TestAlgorithmValidation:
    """Verify algorithm score ranges, fusion, and consistency."""

    def _compare(self, client, bytes_a, bytes_b):
        """Helper to perform a compare and return parsed JSON."""
        resp = client.post(
            "/api/compare",
            files={"image_a": image_bytes_to_file(bytes_a, "a.png"),
                   "image_b": image_bytes_to_file(bytes_b, "b.png")},
        )
        assert resp.status_code == 200
        return resp.json()

    def _in_range(self, value, name):
        assert 0 <= value <= 100, f"{name}={value} is outside [0, 100]"

    def test_ssim_range(self, client):
        """SSIM score must be in [0, 100]."""
        a = make_solid_color((200, 100, 50))
        b = make_solid_color((50, 100, 200))
        data = self._compare(client, a, b)
        self._in_range(data["ssim"], "ssim")

    def test_edge_range(self, client):
        """Edge score must be in [0, 100]."""
        a = make_solid_color((200, 100, 50))
        b = make_solid_color((50, 100, 200))
        data = self._compare(client, a, b)
        self._in_range(data["edge"], "edge")

    def test_spatial_color_range(self, client):
        """Spatial color score must be in [0, 100]."""
        a = make_solid_color((200, 100, 50))
        b = make_solid_color((50, 100, 200))
        data = self._compare(client, a, b)
        self._in_range(data["spatial_color"], "spatial_color")

    def test_dhash_range(self, client):
        """dHash score must be in [0, 100]."""
        a = make_solid_color((200, 100, 50))
        b = make_solid_color((50, 100, 200))
        data = self._compare(client, a, b)
        self._in_range(data["dhash"], "dhash")

    def test_dominant_color_range(self, client):
        """Dominant color score must be in [0, 100]."""
        a = make_solid_color((200, 100, 50))
        b = make_solid_color((50, 100, 200))
        data = self._compare(client, a, b)
        self._in_range(data["dominant_color"], "dominant_color")

    def test_combined_range(self, client):
        """Combined score must be in [0, 100]."""
        a = make_solid_color((200, 100, 50))
        b = make_solid_color((50, 100, 200))
        data = self._compare(client, a, b)
        self._in_range(data["combined"], "combined")

    def test_label_consistency(self, client):
        """Label must match the combined score 5-level thresholds."""
        # Case 1: identical high-contrast UI-like images => Level 4-5 (>= 75)
        img = make_checkerboard((0, 0, 0), (255, 255, 255), size=(200, 200), cell=20)
        data = self._compare(client, img, img)
        assert data["combined"] >= 75, f"Expected high score for identical, got {data['combined']}"
        assert data["label"] in ("高度相似", "几乎一致")

        # Case 2: very different (random noise) => "完全不同" or "略有相似" (Level 1-2: < 40)
        a = make_random_noise(seed=100)
        b = make_random_noise(seed=200)
        data = self._compare(client, a, b)
        assert data["combined"] < 40, (
            f"Expected combined < 40 for different noise images, got {data['combined']}"
        )
        assert data["label"] in ("完全不同", "略有相似")

    def test_weighted_fusion(self, client):
        """Combined score must approximately equal the Phase 3 weighted fusion formula."""
        a = make_gradient()
        b = make_brightened(a, factor=1.2)
        data = self._compare(client, a, b)

        expected_base = round(
            0.35 * data["ssim"]
            + 0.25 * data["edge"]
            + 0.20 * data["spatial_color"]
            + 0.10 * data["dhash"]
            + 0.10 * data["dominant_color"],
            1,
        )

        # Allow for density gate and disagreement penalty adjustments
        assert data["combined"] == pytest.approx(expected_base, abs=20.0), (
            f"combined={data['combined']} != base weighted fusion = {expected_base}"
        )

    def test_heatmap_exists(self, client):
        """Response must contain a heatmap base64 string."""
        img = make_solid_color((30, 60, 90))
        data = self._compare(client, img, img)
        assert "heatmap" in data
        assert data["heatmap"] is not None
        # Verify it is valid base64
        decoded = base64.b64decode(data["heatmap"])
        assert len(decoded) > 0

    def test_theme_change_level2(self, client):
        """Theme change (same structure, different color) should score in Level 2-3 range."""
        grad_red = make_gradient_color((255, 0, 0))
        grad_blue = make_gradient_color((0, 0, 255))
        data = self._compare(client, grad_red, grad_blue)
        # Theme change should be detected and scored ~20-50 (Level 2-3 boundary)
        assert data["combined"] < 60, (
            f"Theme change combined should be < 60, got {data['combined']}"
        )
        assert data["label"] in ("略有相似", "中度相似")
        # Spatial color should drop significantly (different colors)
        assert data["spatial_color"] < 50, f"Spatial color should be low, got {data['spatial_color']}"

    def test_pixel_tweak_level5(self, client):
        """Minor visual tweaks on a UI-like image should score in Level 4-5 range."""
        # Use high-contrast checkerboard so Canny detects edges
        original = make_checkerboard((0, 0, 0), (255, 255, 255), size=(200, 200), cell=20)
        slight_bright = make_brightened(original, factor=1.05)
        data = self._compare(client, original, slight_bright)
        assert data["combined"] >= 70, (
            f"Minor brightness tweak should be Level 4-5 (>=70), got {data['combined']}"
        )
        assert data["label"] in ("高度相似", "几乎一致")


# ---------------------------------------------------------------------------
# F. Batch Compare
# ---------------------------------------------------------------------------

class TestBatchCompare:
    """Batch compare endpoint tests."""

    def test_batch_odd_images(self, client):
        """Odd number of images should return 400."""
        img = make_solid_color((10, 20, 30))
        resp = client.post(
            "/api/compare/batch",
            files=[
                ("images", image_bytes_to_file(img, "1.png")),
                ("images", image_bytes_to_file(img, "2.png")),
                ("images", image_bytes_to_file(img, "3.png")),
            ],
        )
        assert resp.status_code == 400
        assert "even number" in resp.json()["detail"].lower()

    def test_batch_two_pairs(self, client):
        """4 images (2 pairs) should return 2 results."""
        img_same = make_checkerboard((0, 0, 0), (255, 255, 255), size=(200, 200), cell=20)
        img_diff = make_checkerboard((255, 0, 0), (0, 255, 0), size=(200, 200), cell=20)
        resp = client.post(
            "/api/compare/batch",
            files=[
                ("images", image_bytes_to_file(img_same, "pair1_a.png")),
                ("images", image_bytes_to_file(img_same, "pair1_b.png")),
                ("images", image_bytes_to_file(img_diff, "pair2_a.png")),
                ("images", image_bytes_to_file(img_diff, "pair2_b.png")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_pairs"] == 2
        assert len(data["results"]) == 2
        # Both pairs are identical to each other
        assert data["results"][0]["combined"] > 85
        assert data["results"][1]["combined"] > 85

    def test_batch_empty(self, client):
        """0 images should be handled (odd check fires or empty result)."""
        resp = client.post("/api/compare/batch", files=[])
        assert resp.status_code in (400, 422)
