"""عمليات المصفوفات على الصور (NumPy). كل الدوال تأخذ مصفوفة وتعيد مصفوفة جديدة ولا تعدل المدخلات."""
from __future__ import annotations

import numpy as np
from PIL import Image


def to_grayscale(rgb: np.ndarray) -> np.ndarray:
    """تدرج رمادي بأوزان ITU-R BT.601، يعيد uint8 بشكل (H, W)."""
    gray = rgb[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    return np.clip(gray, 0, 255).astype(np.uint8)


def normalize(rgb: np.ndarray) -> np.ndarray:
    """تحويل القيم من 0–255 إلى 0–1 بنوع float32."""
    return rgb.astype(np.float32) / 255.0


def fit_to_square(rgb: np.ndarray, size: int = 512) -> np.ndarray:
    """توحيد الأبعاد: تصغير مع الحفاظ على النسبة ثم حشو بالأسود حتى (size, size, 3).
    يسمح بجمع صور مختلفة الأبعاد في مصفوفة واحدة دون تشويه."""
    h, w = rgb.shape[:2]
    scale = size / max(h, w)
    nh, nw = max(1, round(h * scale)), max(1, round(w * scale))
    small = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.LANCZOS))
    out = np.zeros((size, size, 3), dtype=np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    out[top:top + nh, left:left + nw] = small
    return out


def green_mask(rgb: np.ndarray, threshold: float = 0.10) -> np.ndarray:
    """قناع الغطاء الأخضر بمؤشر Excess Green: ExG = 2g − r − b على الإحداثيات اللونية المطبَّعة.
    الحد 0.10 اختير بمقارنة بصرية على صور المجلد: 0.05 كان يعدّ الطريق والرصيف أخضر.
    يعيد مصفوفة منطقية (H, W): True = بكسل نباتي."""
    x = rgb.astype(np.float32)
    total = x.sum(axis=2) + 1e-6
    r, g, b = (x[..., i] / total for i in range(3))
    return (2 * g - r - b) > threshold


def sobel_edges(gray: np.ndarray) -> np.ndarray:
    """كشف الحواف بمرشح Sobel مكتوب بعمليات المصفوفات فقط. يعيد uint8 (H, W)."""
    g = np.pad(gray.astype(np.float32), 1, mode="edge")
    gx = (g[:-2, 2:] + 2 * g[1:-1, 2:] + g[2:, 2:]) - (g[:-2, :-2] + 2 * g[1:-1, :-2] + g[2:, :-2])
    gy = (g[2:, :-2] + 2 * g[2:, 1:-1] + g[2:, 2:]) - (g[:-2, :-2] + 2 * g[:-2, 1:-1] + g[:-2, 2:])
    mag = np.hypot(gx, gy)
    return (mag / (mag.max() + 1e-6) * 255).astype(np.uint8)


def image_stats(rgb: np.ndarray) -> dict:
    """إحصاءات المصفوفة: الأبعاد، متوسط وانحراف كل قناة، السطوع، التباين، نسبة الغطاء الأخضر."""
    x = rgb.astype(np.float32)
    gray = to_grayscale(rgb).astype(np.float32)
    mean, std = x.mean(axis=(0, 1)), x.std(axis=(0, 1))
    return {
        "height": int(rgb.shape[0]), "width": int(rgb.shape[1]),
        "mean_r": round(float(mean[0]), 2), "mean_g": round(float(mean[1]), 2), "mean_b": round(float(mean[2]), 2),
        "std_r": round(float(std[0]), 2), "std_g": round(float(std[1]), 2), "std_b": round(float(std[2]), 2),
        "brightness": round(float(gray.mean()), 2), "contrast": round(float(gray.std()), 2),
        "green_cover_pct": round(float(green_mask(rgb).mean() * 100), 2),
    }
