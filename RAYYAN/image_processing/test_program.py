"""اختبارات البرنامج:  python -m pytest test_program.py -v
اختبار المجلد الحقيقي يعمل تلقائيًا على data/processed/images/originals (أو IMAGES_DIR إن ضُبط)."""
import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loader  # noqa: E402
from loader import load_image  # noqa: E402
from main import DEFAULT_SOURCE, run  # noqa: E402
from processing import fit_to_square, green_mask, image_stats, normalize, sobel_edges, to_grayscale  # noqa: E402
from scanner import scan  # noqa: E402


def hashes(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


# ---------------------------------------------------------------- عمليات المصفوفات
def test_grayscale_weights():
    rgb = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]], dtype=np.uint8)
    assert to_grayscale(rgb).tolist() == [[76, 149, 29, 255]]


@pytest.mark.parametrize("h,w", [(2293, 1290), (1124, 1290), (300, 900), (10, 10)])
def test_fit_to_square_unifies_any_shape(h, w):
    out = fit_to_square(np.full((h, w, 3), 200, np.uint8), 256)
    assert out.shape == (256, 256, 3) and out.dtype == np.uint8
    assert out.max() == 200  # الصورة نفسها موجودة والحشو أسود


def test_normalize_range():
    n = normalize(np.array([[[0, 128, 255]]], dtype=np.uint8))
    assert n.dtype == np.float32 and n.min() == 0 and n.max() == 1


def test_green_mask_separates_grass_from_gray_and_sky():
    grass, road, sky = [60, 140, 50], [120, 128, 120], [110, 170, 230]
    img = np.array([[grass, road, sky]], dtype=np.uint8)
    assert green_mask(img).tolist() == [[True, False, False]]


def test_sobel_detects_step_edge():
    g = np.zeros((20, 20), np.uint8); g[:, 10:] = 255
    e = sobel_edges(g)
    assert e[:, 9:11].min() > 200 and e[:, :5].max() == 0


def test_stats_keys():
    s = image_stats(np.zeros((4, 6, 3), np.uint8))
    assert (s["height"], s["width"], s["green_cover_pct"]) == (4, 6, 0.0)


# ---------------------------------------------------------------- الأخطاء وحماية الأصول
@pytest.fixture()
def mixed_folder(tmp_path):
    src = tmp_path / "صور"; (src / "فرعي" / "أعمق").mkdir(parents=True)
    Image.new("RGB", (40, 80), (60, 140, 50)).save(src / "a.png")
    Image.new("RGB", (90, 30), (120, 120, 120)).save(src / "فرعي" / "أعمق" / "b.JPG")
    (src / "فرعي" / "تالف.png").write_bytes(b"not an image")
    (src / "ملاحظات.txt").write_text("x")
    return src


def test_scan_finds_nested_images_and_skips_others(mixed_folder):
    r = scan(mixed_folder)
    assert sorted(p.name for p in r.images) == ["a.png", "b.JPG", "تالف.png"]
    assert [p.name for p in r.skipped] == ["ملاحظات.txt"]


def test_run_handles_errors_and_keeps_originals(mixed_folder, tmp_path):
    before = hashes(mixed_folder)
    out = tmp_path / "output"
    s = run(mixed_folder, out, size=64)
    assert s["processed"] == 2 and len(s["failed"]) == 1 and "تالف.png" in s["failed"][0]["file"]
    assert s["unsupported_skipped"] == ["ملاحظات.txt"] and s["originals_unchanged"]
    assert np.load(out / "images_uint8.npy").shape == (2, 64, 64, 3)
    assert (out / "processed" / "فرعي" / "أعمق" / "b" / "edges.png").exists()
    assert hashes(mixed_folder) == before  # لم يتغير أي ملف أصلي
    assert not any(p.parts[-1] == "output" for p in mixed_folder.rglob("*"))


def test_output_inside_source_is_refused(mixed_folder):
    with pytest.raises(ValueError):
        run(mixed_folder, mixed_folder / "output")


def test_missing_folder():
    with pytest.raises(FileNotFoundError):
        scan(Path("/لا/يوجد/مجلد"))


def test_corrupt_file_raises_clear_error(mixed_folder):
    with pytest.raises(ValueError, match="تعذرت قراءة"):
        load_image(mixed_folder / "فرعي" / "تالف.png")


# ---------------------------------------------------------------- HEIC والنسخ المحوّلة
def test_heic_converted_copy_is_fallback_not_extra_image(tmp_path, monkeypatch):
    src = tmp_path / "u"; src.mkdir()
    (src / "IMG_1.HEIC").write_bytes(b"fake heic")
    Image.new("RGB", (30, 50), (60, 140, 50)).save(src / "IMG_1_converted.jpg")
    r = scan(src)
    assert [p.name for p in r.images] == ["IMG_1.HEIC"] and r.skipped == []
    assert r.derived[src / "IMG_1.HEIC"].name == "IMG_1_converted.jpg"
    monkeypatch.setattr(loader, "HEIF_BACKEND", "converted-jpg")
    arr, how = loader.load_image(src / "IMG_1.HEIC", r.derived[src / "IMG_1.HEIC"])
    assert arr.shape == (50, 30, 3) and how.startswith("converted-jpg")


def test_heic_without_any_decoder_fails_clearly(tmp_path, monkeypatch):
    p = tmp_path / "x.heic"; p.write_bytes(b"fake")
    monkeypatch.setattr(loader, "HEIF_BACKEND", "converted-jpg")
    with pytest.raises(ValueError, match="pillow-heif"):
        loader.load_image(p)


# ---------------------------------------------------------------- المجلد الحقيقي
REAL = Path(os.environ.get("IMAGES_DIR") or DEFAULT_SOURCE)


@pytest.mark.skipif(not REAL.is_dir(), reason="مجلد الصور الأصلية غير موجود")
def test_real_folder_all_images(tmp_path):
    before = hashes(REAL)
    s = run(REAL, tmp_path / "out", size=128)
    assert s["failed"] == [] and s["processed"] == s["images_found"] > 0 and s["originals_unchanged"]
    arr = np.load(tmp_path / "out" / "images_uint8.npy")
    assert arr.shape == (s["processed"], 128, 128, 3)
    found = scan(REAL)
    for p in (p for p in found.images if p.suffix.lower() == ".heic"):  # HEIC يُقرأ بأبعاده الكاملة
        a, _ = load_image(p, found.derived.get(p))
        assert a.ndim == 3 and min(a.shape[:2]) > 1000
    assert hashes(REAL) == before
