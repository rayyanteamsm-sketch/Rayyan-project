"""تحميل صورة كمصفوفة NumPy بشكل (الارتفاع، العرض، 3) ونوع uint8.

PNG و JPG عبر Pillow. HEIC بالترتيب: pillow-heif إن كانت مثبتة ← heic.py عبر ffmpeg ←
النسخة «_converted.jpg» التي أنشأها المشروع سابقًا بجانب الأصل (بنفس الأبعاد الكاملة).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

try:  # الطريقة المفضلة لـ HEIC
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_BACKEND = "pillow-heif"
except ImportError:
    HEIF_BACKEND = "ffmpeg" if shutil.which("ffmpeg") else "converted-jpg"


def _open(path: Path) -> Image.Image:
    with Image.open(path) as im:
        img = ImageOps.exif_transpose(im)  # تصحيح اتجاه صور الجوال
        img.load()
    return img


def load_image(path: Path, fallback: Path | None = None) -> tuple[np.ndarray, str]:
    """يعيد (مصفوفة RGB uint8، طريقة القراءة). يرفع ValueError إن تعذرت القراءة.
    fallback: نسخة JPEG محوّلة سابقًا تُستخدم لـ HEIC إن لم تتوفر طريقة فك مباشرة."""
    is_heic = path.suffix.lower() in (".heic", ".heif")
    try:
        if not is_heic or HEIF_BACKEND == "pillow-heif":
            img, how = _open(path), ("pillow-heif" if is_heic else "pillow")
        elif HEIF_BACKEND == "ffmpeg":
            from heic import read_heic
            img, how = read_heic(path), "ffmpeg"
        elif fallback is not None:
            img, how = _open(fallback), f"converted-jpg ({fallback.name})"
        else:
            raise RuntimeError("صيغة HEIC تحتاج pillow-heif (pip install pillow-heif) أو ffmpeg أو نسخة _converted.jpg")
        return np.asarray(img.convert("RGB"), dtype=np.uint8), how
    except Exception as e:  # أي ملف تالف أو صيغة لا تُقرأ
        raise ValueError(f"تعذرت قراءة {path.name}: {e}") from e
