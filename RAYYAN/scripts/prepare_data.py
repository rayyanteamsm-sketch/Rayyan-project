"""
تجهيز بيانات ريّان من الملف الأصلي — قابل لإعادة التشغيل.

1. يتحقق من بصمة الملف الأصلي data/raw/original_upload.zip (لا يُعدَّل أبدًا).
2. يفك الصور والمدخلات وحزمة البيانات إلى data/processed/ بأسماء عربية صحيحة.
3. يتحقق من بصمات ملفات الحزمة مقابل SHA256SUMS.txt الأصلي.
4. يحوّل نسخ HEIC إلى JPEG (الأصل يبقى)، وينشئ نسخ عرض ويب ومصغرات بنفس النسب.
5. ينسخ قاعدة SQLite الأصلية إلى data/database/rayyan.sqlite ويضيف جداول التطبيق فقط.

التشغيل:
    python scripts/prepare_data.py            # يتخطى ما هو جاهز
    python scripts/prepare_data.py --rebuild  # يعيد كل شيء من الأصل
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RAW_ZIP = ROOT / "data/raw/original_upload.zip"
RAW_V2 = ROOT / "data/raw/RAYYAN_ML_Ready.xlsx"   # مجموعة v2 (4 مناطق) — مرفوعة لاحقًا، اختيارية
PROC = ROOT / "data/processed"
PKG = PROC / "package"
IMG = PROC / "images"
DB_DIR = ROOT / "data/database"
DB = DB_DIR / "rayyan.sqlite"
sys.path.insert(0, str(ROOT / "scripts"))
from heic_to_jpeg import convert as heic_convert  # noqa: E402

# مجموعات الصور كما وردت في مجلدات الملف الأصلي فقط — لا ننسب صورة لموقع لم يذكره الملف.
GROUPS = {
    "rabigh_kaec": {"folder": "صور _برابغ _ ومدينة الملك عبدالله ",
                     "label": "مجلد «صور برابغ ومدينة الملك عبدالله»",
                     "note": "الملف الأصلي يجمع هذه الصور في مجلد واحد لرابغ ومدينة الملك عبدالله الاقتصادية، دون تحديد موقع كل صورة."},
    "unlabeled": {"folder": "",
                  "label": "صور مرفقة دون تحديد موقع",
                  "note": "صور في المجلد الرئيسي للمشروع؛ لا يحدد الملف موقعها."},
}
HIDDEN_CACHE = re.compile(r"(^|/)\.")  # ملفات مخفية في الحزمة (كاش فحص Excel)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fix_name(n: str) -> str:
    return re.sub(r"#U([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), n)


def extract_upload(rebuild: bool):
    if (PROC / "inputs").exists() and not rebuild:
        print("• inputs موجودة"); return
    z = zipfile.ZipFile(RAW_ZIP)
    (PROC / "inputs").mkdir(parents=True, exist_ok=True)
    for g in GROUPS:
        (IMG / "originals" / g).mkdir(parents=True, exist_ok=True)
    for info in z.infolist():
        if info.is_dir():
            continue
        name = fix_name(info.filename)
        parts = name.split("/")
        data = z.read(info)
        fname = parts[-1]
        if fname.lower().endswith((".png", ".jpg", ".jpeg", ".heic")):
            group = "rabigh_kaec" if len(parts) > 2 and parts[1] == GROUPS["rabigh_kaec"]["folder"] else "unlabeled"
            (IMG / "originals" / group / fname).write_bytes(data)
        else:
            (PROC / "inputs" / fname).write_bytes(data)
    print("• فُكّ الملف الأصلي")


def extract_package(rebuild: bool):
    if PKG.exists() and not rebuild:
        print("• الحزمة موجودة"); return
    if PKG.exists():
        shutil.rmtree(PKG)
    z = zipfile.ZipFile(PROC / "inputs/Rayyan_Data_Package_2024_2025.zip")
    prefix = "Rayyan_Data_Package_2024_2025/"
    for info in z.infolist():
        rel = info.filename[len(prefix):] if info.filename.startswith(prefix) else info.filename
        if info.is_dir() or not rel or HIDDEN_CACHE.search(rel):
            continue
        out = PKG / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(z.read(info))
    print("• فُكّت حزمة البيانات (دون ملفي الكاش المخفيين)")


def verify_package() -> dict:
    ok, bad, skipped = 0, [], []
    for line in (PKG / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        rel = rel.strip().lstrip("*")
        if HIDDEN_CACHE.search(rel):
            skipped.append(rel); continue
        p = PKG / rel
        if p.exists() and sha256(p) == digest:
            ok += 1
        else:
            bad.append(rel)
    res = {"verified": ok, "failed": bad, "skipped_hidden_cache": skipped}
    print(f"• تحقق البصمات: {ok} مطابق، {len(bad)} مختلف، {len(skipped)} كاش مستبعد")
    if bad:
        raise SystemExit(f"ملفات الحزمة لا تطابق البصمة: {bad}")
    return res


def _convert_heic(src: Path, dst: Path) -> None:
    """HEIC ← JPEG بدقته الكاملة: pillow-heif إن كانت مثبتة، وإلا محلل المشروع مع ffmpeg؛ وإلا رسالة واضحة."""
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
        from PIL import ImageOps
        with Image.open(src) as im:
            ImageOps.exif_transpose(im).convert("RGB").save(dst, "JPEG", quality=92, optimize=True)
        return
    except ImportError:
        pass
    import shutil as _sh
    if not _sh.which("ffmpeg"):
        raise SystemExit(f"تعذر تحويل {src.name}: إعادة البناء من الملف الأصلي تحتاج مفكك HEIC. "
                         "ثبّتي أحدهما: py -3 -m pip install pillow-heif   أو   ffmpeg (https://ffmpeg.org). "
                         "التشغيل العادي لا يحتاجهما لأن النسخ المحولة موجودة في data/processed/images.")
    heic_convert(src, dst)


def build_images(rebuild: bool) -> list[dict]:
    web = IMG / "web"; thumbs = IMG / "thumbs"
    web.mkdir(parents=True, exist_ok=True); thumbs.mkdir(parents=True, exist_ok=True)
    manifest = []
    for group, meta in GROUPS.items():
        for src in sorted((IMG / "originals" / group).iterdir()):
            if src.name.endswith("_converted.jpg"):
                continue
            ext = src.suffix.lower()
            if ext == ".heic":
                conv = src.with_name(src.stem + "_converted.jpg")
                if rebuild or not conv.exists():
                    _convert_heic(src, conv)
                display_src, converted = conv, True
            else:
                display_src, converted = src, False
            stem = src.stem
            wp, tp = web / f"{stem}.jpg", thumbs / f"{stem}.jpg"
            im = Image.open(display_src)
            w, h = im.size
            if rebuild or not wp.exists():
                rgb = im.convert("RGB")
                a = rgb.copy(); a.thumbnail((2000, 2000), Image.LANCZOS); a.save(wp, "JPEG", quality=88, optimize=True, progressive=True)
                b = rgb.copy(); b.thumbnail((640, 640), Image.LANCZOS); b.save(tp, "JPEG", quality=82, optimize=True, progressive=True)
            manifest.append({
                "id": stem, "group": group, "group_label": meta["label"], "group_note": meta["note"],
                "original_file": f"originals/{group}/{src.name}", "original_format": ext.lstrip(".").upper(),
                "display_original": f"originals/{group}/{display_src.name}",
                "converted_from_heic": converted, "web": f"web/{stem}.jpg", "thumb": f"thumbs/{stem}.jpg",
                "width": w, "height": h, "bytes_original": src.stat().st_size,
                "used_for_training": False,
            })
    (IMG / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"• الصور: {len(manifest)} صورة، منها {sum(m['converted_from_heic'] for m in manifest)} محولة من HEIC")
    return manifest


def build_database(rebuild: bool):
    DB_DIR.mkdir(parents=True, exist_ok=True)
    if DB.exists() and not rebuild:
        print("• قاعدة التطوير موجودة")
    else:
        shutil.copy2(PKG / "Rayyan_Bermuda_2024_2025.sqlite", DB)
        print("• نُسخت قاعدة SQLite الأصلية إلى نسخة تطوير")
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript((ROOT / "backend/database/schema_app.sql").read_text(encoding="utf-8"))
    con.commit()
    n_orig = con.execute("select count(*) from sqlite_master where type='table' and name not like 'app_%' and name not like 'v2_%' and name != 'sqlite_sequence'").fetchone()[0]
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    print(f"• جداول الحزمة الأصلية: {n_orig}، فحص المفاتيح الأجنبية: {'سليم' if not fk else fk[:3]}")


# ------------------------------------------------------------------ مجموعة v2
V2_TABLES = [  # (الورقة، الجدول، المفتاح الأساسي، المفاتيح الأجنبية)
    ("Zones", "v2_zones", "zone_id", []),
    ("Weather", "v2_weather", "weather_id", []),
    ("ML_Ready", "v2_ml_ready", "event_id", [("zone_id", "v2_zones", "zone_id"), ("weather_id", "v2_weather", "weather_id")]),
    ("Outcomes", "v2_outcomes", "event_id", [("event_id", "v2_ml_ready", "event_id"), ("zone_id", "v2_zones", "zone_id")]),
    ("Simulation_Audit", "v2_simulation_audit", "event_id", [("event_id", "v2_ml_ready", "event_id")]),
    ("Baseline_Metrics", "v2_reported_baselines", None, []),
    ("Dictionary", "v2_dictionary", None, []),
    ("ReadMe", "v2_readme", None, []),
]


def import_v2() -> dict | None:
    """يستورد أوراق RAYYAN_ML_Ready.xlsx كما هي إلى جداول v2_ منفصلة. لا يمس جداول الحزمة الأصلية."""
    if not RAW_V2.exists():
        print("• لا يوجد ملف v2؛ تخطي"); return None
    import pandas as pd
    x = pd.ExcelFile(RAW_V2)
    con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys=ON")
    for _, t, _, _ in reversed(V2_TABLES):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    counts = {}
    for sheet, table, pk, fks in V2_TABLES:
        df = x.parse(sheet)
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # كل التواريخ في الملف UTC
        def sqltype(c):
            if pd.api.types.is_integer_dtype(df[c]): return "INTEGER"
            if pd.api.types.is_float_dtype(df[c]): return "REAL"
            return "TEXT"
        cols = [f'"{c}" {sqltype(c)}' + (" NOT NULL" if c == pk else "") for c in df.columns]
        if pk: cols.append(f'PRIMARY KEY("{pk}")')
        cols += [f'FOREIGN KEY("{a}") REFERENCES {rt}("{rc}")' for a, rt, rc in fks]
        con.execute(f"CREATE TABLE {table} ({', '.join(cols)})")
        rows = [tuple(None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in r) for r in df.itertuples(index=False)]
        con.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(df.columns))})", rows)
        counts[table] = len(rows)
    con.commit()
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    if fk:
        raise SystemExit(f"مفاتيح v2 غير سليمة: {fk[:3]}")
    print("• استيراد v2:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if not RAW_ZIP.exists():
        raise SystemExit(f"الملف الأصلي غير موجود: {RAW_ZIP}")
    raw_sha = sha256(RAW_ZIP)
    sums = [f"{raw_sha}  original_upload.zip"] + ([f"{sha256(RAW_V2)}  {RAW_V2.name}"] if RAW_V2.exists() else [])
    (ROOT / "data/raw/SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print("• بصمة الملف الأصلي:", raw_sha[:16], "…")
    extract_upload(a.rebuild)
    extract_package(a.rebuild)
    ver = verify_package()
    imgs = build_images(a.rebuild)
    build_database(a.rebuild)
    v2 = import_v2()
    (PROC / "prepare_report.json").write_text(json.dumps({
        "original_upload_sha256": raw_sha, "package_verification": ver, "images": len(imgs),
        "database": str(DB.relative_to(ROOT)), "v2_tables": v2}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("✓ التجهيز اكتمل")


if __name__ == "__main__":
    main()
