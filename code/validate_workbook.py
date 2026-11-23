from pathlib import Path
from datetime import datetime,timezone
import json,math,zipfile
import openpyxl
import pandas as pd

P=Path(__file__).resolve().parents[1]
f=P/'Rayyan_Bermuda_2024_2025.xlsx'
payload=json.loads((P/'quality/excel_expected_review.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(f) as z: assert z.testzip() is None
wb=openpyxl.load_workbook(f,read_only=True,data_only=True)
d=payload['tables']['data_dictionary']; defs={(r[0],r[1]):r[3] for r in d['rows']}
issues=[];checked=0;date_checked=0;auto_dates=0
for name,t in payload['tables'].items():
 sh=wb[name]; cols=t['columns']
 if sh.max_row is None: sh.calculate_dimension(force=True)
 source=pd.read_csv(P/t['meta']['file'],keep_default_na=False,na_values=[''])
 if t['meta'].get('excel_row_count',len(source))<len(source):
  order=[str(r[0]) for r in t['rows']]
  source.index=source.iloc[:,0].astype(str)
  source=source.loc[order]
 rows=source.astype(object).where(pd.notnull(source),None).values.tolist()
 assert list(next(sh.iter_rows(min_row=4,max_row=4,values_only=True)))[:len(cols)]==cols,name
 assert sh.max_row==len(rows)+4,(name,sh.max_row,len(rows)+4)
 for i,(got,expected) in enumerate(zip(sh.iter_rows(min_row=5,max_row=len(rows)+4,max_col=len(cols),values_only=True),rows)):
  for j,(a,b) in enumerate(zip(got,expected)):
   checked+=1;dtype=defs.get((name,cols[j]))
   if b is None or b=='': ok=a is None or a==''
   elif dtype in ['Date','Datetime']:
    date_checked+=1
    if dtype=='Date': want=datetime.fromisoformat(b)
    else: want=datetime.fromisoformat(b.replace('Z','+00:00')).astimezone(timezone.utc).replace(tzinfo=None)
    if isinstance(a,str):
     if dtype=='Date': actual=datetime.fromisoformat(a)
     else: actual=datetime.fromisoformat(a.replace('Z','+00:00')).astimezone(timezone.utc).replace(tzinfo=None)
    else: actual=a
    ok=isinstance(actual,datetime) and abs((actual-want).total_seconds())<.002
   elif isinstance(a,datetime) and isinstance(b,str):
    try:
     want=datetime.fromisoformat(b.replace('Z','+00:00'))
     if want.tzinfo:want=want.astimezone(timezone.utc).replace(tzinfo=None)
     ok=abs((a-want).total_seconds())<.002;auto_dates+=1
    except ValueError:ok=False
   elif isinstance(b,str) and b.startswith('='):ok=a==b or a=="'"+b
   elif isinstance(b,(int,float)) and not isinstance(b,bool):ok=isinstance(a,(int,float)) and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-8)
   else:ok=a==b
   if not ok and len(issues)<25:issues.append(dict(sheet=name,row=i+5,column=cols[j],actual=str(a),expected=str(b)))
 errors=[]
 for row in sh.iter_rows(min_row=5,max_row=min(len(rows)+4,12),values_only=True):
  errors.extend(v for v in row if isinstance(v,str) and v in ['#REF!','#VALUE!','#DIV/0!','#NAME?','#NUM!','#N/A'])
 if errors:issues.append(dict(sheet=name,formula_errors=errors))
 print('verified',name,len(rows),flush=True)
summary=[]
events=payload['tables']['irrigation_events']['rows']
for i,z in enumerate(['Z01','Z02'],8):
 vals=[wb['Summary'].cell(i,c).value for c in range(1,8)]
 count=sum(r[2]==z for r in events);volume=sum(r[11] for r in events if r[2]==z)
 assert vals[2]==count and abs(vals[3]-volume)<1e-7 and abs(vals[4]-volume/5)<1e-7,vals
 summary.append(vals)
report=dict(workbook=f.name,sheets=len(wb.sheetnames),cells_compared=checked,datetime_cells_compared=date_checked,scope='REVIEW workbook;4telemetry subsets;allCSVandSQLitecomplete',
            mismatches=issues,all_values_match=not issues,source_text_dates_auto_converted=auto_dates,date_comparison_tolerance_seconds=.002,summary_formula_cache=summary,zip_integrity='PASS')
(P/'quality/workbook_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
if issues:raise AssertionError('Workbook differs from data payload')
