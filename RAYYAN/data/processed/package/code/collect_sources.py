"""Download primary source snapshots. No synthetic fallback disguised as weather."""
from pathlib import Path
import argparse, hashlib, json, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def fetch(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=45) as response:
        body = response.read()
    path.write_bytes(body)
    return {"url": url, "file": str(path.relative_to(ROOT)), "bytes": len(body),
            "sha256": sha(path), "accessed_at": datetime.now(timezone.utc).isoformat(), "status": "downloaded"}

def collect(refresh=False):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    hourly = "temperature_2m,relative_humidity_2m,precipitation,et0_fao_evapotranspiration,shortwave_radiation,wind_speed_10m"
    q = dict(latitude=cfg["weather_request_latitude"], longitude=cfg["weather_request_longitude"],
             start_date=cfg["start_date"], end_date=(datetime.fromisoformat(cfg["end_date"])+timedelta(days=1)).date().isoformat(), timezone=cfg["timezone"],
             hourly=hourly, models=cfg["weather_model"], wind_speed_unit="ms", elevation="nan")
    sources = {
      "weather": ("https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(q, safe=","), "weather_era5.json"),
      "paper": ("https://journals.ajsrp.com/index.php/jnslas/en/article/download/989/937/1869", "saeed_2018.pdf"),
      "fao56": ("https://www.fao.org/4/X0490E/x0490e0e.htm", "fao56_ch8.html"),
      "weather_docs": ("https://open-meteo.com/en/docs/historical-weather-api", "open_meteo_docs.html"),
      "weather_terms": ("https://open-meteo.com/en/terms", "open_meteo_terms.html"),
      "paper_landing": ("https://journals.ajsrp.com/index.php/jnslas/en/article/view/989", "paper_landing.html")
    }
    mpath = ROOT / "raw" / "source_manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    for sid, (url, name) in sources.items():
        path = ROOT / "raw" / name
        if path.exists() and not refresh:
            if sid in manifest and manifest[sid].get("sha256") and manifest[sid]["sha256"] != sha(path):
                raise ValueError("Cached source checksum mismatch: " + sid)
            if sid not in manifest or manifest[sid].get("status") != "downloaded":
                manifest[sid] = {"url": url, "file": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                    "sha256": sha(path), "accessed_at": datetime.now(timezone.utc).isoformat(), "status": "downloaded"}
                mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            print(sid, "cached", path.stat().st_size, flush=True)
            continue
        try:
            manifest[sid] = fetch(url, path)
            print(sid, "downloaded", path.stat().st_size, flush=True)
        except Exception as exc:
            manifest[sid] = {"url": url, "file": str(path.relative_to(ROOT)), "status": "unavailable", "error": str(exc)}
            print(sid, "UNAVAILABLE", str(exc), flush=True)
            if sid == "weather":
                mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                raise RuntimeError("Weather collection failed. No observed/reanalysis records were invented.") from exc
        mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    obj = json.loads((ROOT / "raw/weather_era5.json").read_text(encoding="utf-8"))
    if obj.get("error") or "hourly" not in obj:
        raise ValueError(obj)
    print("hours", len(obj["hourly"]["time"]), "grid", obj["latitude"], obj["longitude"], "units", obj["hourly_units"], flush=True)
    return manifest

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--refresh", action="store_true")
    collect(ap.parse_args().refresh)
