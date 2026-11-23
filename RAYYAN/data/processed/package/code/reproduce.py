"""Rebuild numeric data from pinned cache and seed; compare all CSV bytes."""
from pathlib import Path
import argparse, hashlib, json, sys
from build_dataset import build
from train_demo import train

ROOT=Path(__file__).resolve().parents[1]
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def reproduce(output):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:
        raise ValueError("Choose a fresh directory OUTSIDE the delivered package to avoid overwriting its pinned baseline")
    if output.exists() and any(output.iterdir()): raise ValueError("Output must be empty")
    build(output); train(output)
    wanted=list((ROOT/"data").rglob("*.csv"))+[ROOT/"metadata/data_dictionary.csv",ROOT/"quality/quality_checks.csv",ROOT/"quality/demo_model_metrics.csv",ROOT/"quality/demo_predictions.csv"]
    rows=[]
    for p in sorted(wanted):
        rel=p.relative_to(ROOT); q=output/rel
        rows.append({"file":str(rel),"expected_sha256":digest(p),"reproduced_sha256":digest(q) if q.exists() else None,
                     "identical":q.exists() and digest(p)==digest(q)})
    result={"seed":20261107,"files_compared":len(rows),"identical_files":sum(r["identical"] for r in rows),
        "all_identical":all(r["identical"] for r in rows),"comparison":"byte_sha256;fixed_cached_weather;fixed_versions","files":rows}
    (ROOT/"quality/reproducibility_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2), encoding="utf-8")
    print("reproducibility",result["identical_files"],"/",result["files_compared"])
    if not result["all_identical"]: raise AssertionError("Reproduction mismatch;inspect report")
    return result

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path,required=True)
    reproduce(ap.parse_args().output)
