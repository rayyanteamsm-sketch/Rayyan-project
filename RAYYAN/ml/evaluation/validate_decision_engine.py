"""
التحقق من محرك القرار: إعادة تشغيل كل قرار محفوظ بقواعد ريّان (rule_v1، المنطقة Z02)
بنفس مدخلاته الأصلية، ومقارنة القرار والحجم بما سجله المحاكي.

هذا اختبار اتساق مع قواعد المشروع، وليس "دقة" زراعية: يثبت أن المحرك ينفذ القواعد الموثقة كما هي.

التشغيل:  python ml/evaluation/validate_decision_engine.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.database.db import connect, rows  # noqa: E402
from backend.services.recommendation import SIM_ACTION, build, stored_inputs  # noqa: E402


def main():
    con = connect()
    ids = [r["decision_id"] for r in rows(con, "select decision_id from decisions where method_version='rule_v1' order by issued_at")]
    action_ok = vol_ok = 0
    confusion = Counter(); mismatches = []
    for did in ids:
        inp, st = stored_inputs(did, con)
        res = build(inp)
        a = res["decision"]["action"]; v = (res["water_plan"] or {}).get("volume_l") or 0.0
        sa = SIM_ACTION[st["action"]]
        confusion[(sa, a)] += 1
        ok_a = a == sa; ok_v = abs(v - st["planned_volume_l"]) < 1e-6
        action_ok += ok_a; vol_ok += ok_v
        if not (ok_a and ok_v):
            mismatches.append({"decision_id": did, "stored": [sa, st["planned_volume_l"]], "engine": [a, v]})
    con.close()
    rep = {"rule_version": "rule_v1", "decisions_compared": len(ids),
           "action_agreement": action_ok / len(ids), "volume_agreement": vol_ok / len(ids),
           "action_matches": action_ok, "volume_matches": vol_ok,
           "confusion": [{"stored": k[0], "engine": k[1], "n": n} for k, n in sorted(confusion.items())],
           "mismatches": mismatches[:20],
           "meaning": "اتساق المحرك مع قواعد المحاكي الموثقة؛ لا يقيس صحة القرار زراعيًا ولا توفير الماء."}
    out = ROOT / "ml/saved_models/decision_engine_validation.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"قرارات: {len(ids)} | تطابق القرار {action_ok}/{len(ids)} | تطابق الحجم {vol_ok}/{len(ids)}")
    for m in mismatches[:5]:
        print("  اختلاف:", m)


if __name__ == "__main__":
    main()
