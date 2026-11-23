"""
معالجة صور مشروع ريّان كمصفوفات NumPy.

    python main.py                                   # الصور من data/processed/images/originals والنتائج في ./output
    python main.py "مسار مجلد صور آخر" -o results --size 256

لكل صورة: تحميل → مصفوفة RGB → رمادي، قناع الغطاء الأخضر، الحواف، نسخة موحدة المقاس.
النتائج في مجلد الإخراج فقط؛ الملفات الأصلية تُقرأ ولا تُعدَّل أبدًا (يُتحقق من بصمتها SHA-256 قبل وبعد).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from loader import HEIF_BACKEND, load_image  # noqa: E402
from processing import fit_to_square, green_mask, image_stats, normalize, sobel_edges, to_grayscale  # noqa: E402
from scanner import SUPPORTED, scan  # noqa: E402

DEFAULT_SOURCE = HERE.parent / "data" / "processed" / "images" / "originals"
DEFAULT_OUTPUT = HERE / "output"


def fingerprints(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def save_png(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path)


def run(src: Path, out: Path, size: int = 512) -> dict:
    src, out = src.resolve(), out.resolve()
    if out == src or src in out.parents:
        raise ValueError("مجلد الإخراج يجب أن يكون خارج مجلد الصور الأصلية حتى لا يُعدَّل")
    t0 = time.time()
    found = scan(src)
    before = fingerprints(src)
    print(f"وُجدت {len(found.images)} صورة و{len(found.skipped)} ملفًا غير مدعوم في {src.name}")

    rows, batch, names, errors = [], [], [], []
    for i, path in enumerate(found.images, 1):
        rel = path.relative_to(src)
        try:
            rgb, how = load_image(path, found.derived.get(path))
        except ValueError as e:
            errors.append({"file": str(rel), "error": str(e)})
            print(f"  [{i}] ✗ {rel} — {e}")
            continue
        base = out / "processed" / rel.parent / path.stem
        gray = to_grayscale(rgb)
        square = fit_to_square(rgb, size)
        save_png(gray, base / "gray.png")
        save_png(green_mask(rgb).astype(np.uint8) * 255, base / "green_mask.png")
        save_png(sobel_edges(gray), base / "edges.png")
        save_png(square, base / f"resized_{size}.png")
        batch.append(square)
        names.append(str(rel))
        rows.append({"file": str(rel), "group": found.groups.get(path.name, rel.parts[0] if len(rel.parts) > 1 else ""),
                     "format": SUPPORTED[path.suffix.lower()], "read_with": how, **image_stats(rgb)})
        print(f"  [{i}] ✓ {rel}  {rgb.shape[1]}×{rgb.shape[0]}  أخضر {rows[-1]['green_cover_pct']}%")

    out.mkdir(parents=True, exist_ok=True)
    if batch:
        stack = np.stack(batch)                                # (N, size, size, 3) uint8
        np.save(out / "images_uint8.npy", stack)
        np.save(out / "images_float32.npy", normalize(stack))  # (N, size, size, 3) بين 0 و1
        (out / "images_index.json").write_text(json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
    if rows:
        with open(out / "report.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    originals_unchanged = fingerprints(src) == before
    summary = {"source": str(src), "images_found": len(found.images), "processed": len(rows), "failed": errors,
               "unsupported_skipped": [str(p.relative_to(src)) for p in found.skipped],
               "heic_derived_copies": {str(k.relative_to(src)): str(v.relative_to(src)) for k, v in found.derived.items()},
               "heic_backend": HEIF_BACKEND, "batch_shape": list(stack.shape) if batch else None,
               "originals_unchanged": originals_unchanged, "seconds": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nعولجت {len(rows)} من {len(found.images)} صورة في {summary['seconds']} ث"
          f"{'، فشل ' + str(len(errors)) if errors else ''}. الأصول سليمة: {'نعم' if originals_unchanged else 'لا!'}."
          f" النتائج في: {out}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="معالجة صور مشروع ريّان كمصفوفات NumPy")
    ap.add_argument("source", type=Path, nargs="?", default=DEFAULT_SOURCE,
                    help="مجلد الصور الرئيسي (افتراضيًا data/processed/images/originals)")
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT, help="مجلد النتائج (افتراضيًا image_processing/output)")
    ap.add_argument("--size", type=int, default=512, help="المقاس الموحد للمصفوفة المجمعة (افتراضيًا 512)")
    a = ap.parse_args()
    try:
        run(a.source, a.output, a.size)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"خطأ: {e}")


if __name__ == "__main__":
    main()
