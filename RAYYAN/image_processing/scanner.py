"""فحص المجلد الرئيسي وكل المجلدات الفرعية وحصر الصور. قراءة فقط — لا يغيّر أي ملف.

ملف «X_converted.jpg» الموجود بجانب «X.HEIC» نسخة مشتقة أنشأها المشروع سابقًا (scripts/heic_to_jpeg.py)،
فلا يُعدّ صورة مستقلة؛ يُحفظ كبديل لقراءة HEIC إن لم تتوفر pillow-heif أو ffmpeg.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".heic": "HEIC", ".heif": "HEIC"}
CONVERTED_SUFFIX = "_converted.jpg"


@dataclass
class ScanResult:
    images: list[Path]                                      # الصور الأصلية المدعومة
    skipped: list[Path]                                     # ملفات أخرى — تُذكر في التقرير فقط
    derived: dict[Path, Path] = field(default_factory=dict)  # HEIC ← نسخته JPEG المحوّلة سابقًا
    groups: dict[str, str] = field(default_factory=dict)     # اسم الصورة ← المجموعة (من manifest.json)


def _heic_sibling(p: Path) -> Path | None:
    if not p.name.lower().endswith(CONVERTED_SUFFIX):
        return None
    stem = p.name[: -len(CONVERTED_SUFFIX)]
    for ext in (".HEIC", ".heic", ".HEIF", ".heif"):
        if (p.parent / (stem + ext)).is_file():
            return p.parent / (stem + ext)
    return None


def load_groups(root: Path) -> dict[str, str]:
    """يقرأ manifest.json (إن وُجد في المجلد أو أعلاه مباشرة) لربط كل صورة بمجموعتها."""
    for m in (root / "manifest.json", root.parent / "manifest.json"):
        if m.is_file():
            try:
                return {Path(e["original_file"]).name: e.get("group", "") for e in json.loads(m.read_text(encoding="utf-8"))}
            except (ValueError, KeyError, TypeError):
                return {}
    return {}


def scan(root: Path) -> ScanResult:
    if not root.is_dir():
        raise FileNotFoundError(f"المجلد غير موجود: {root}")
    images, skipped, derived = [], [], {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        heic = _heic_sibling(p)
        if heic is not None:
            derived[heic] = p
        elif p.suffix.lower() in SUPPORTED:
            images.append(p)
        else:
            skipped.append(p)
    return ScanResult(images, skipped, derived, load_groups(root))
