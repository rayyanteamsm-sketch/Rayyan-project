"""Refresh statistics only; authored Arabic guides remain unchanged."""
from pathlib import Path
import json
import pandas as pd
P=Path(__file__).resolve().parents[1]
q=json.loads((P/"quality/quality_summary.json").read_text(encoding="utf-8"))
catalog=pd.read_csv(P/"metadata/table_catalog.csv")
text=f"# إحصاءات الحزمة المنفذة\n\nعدد الفحوص: {q['checks']}. الحالات: {q['status_counts']}.\n\n"
text+="| الجدول | عدد الصفوف | نوع البيانات |\n|---|---:|---|\n"
text+="\n".join(f"| `{r.table}` | {r.row_count:,} | {r.data_type} |" for r in catalog.itertuples(index=False))
(P/"quality/dataset_statistics_AR.md").write_text(text+"\n",encoding="utf-8")
print("Statistics refreshed")
