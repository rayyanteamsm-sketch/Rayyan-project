"""Create checksums and a deterministic archive after all actual validation succeeds."""
from pathlib import Path
import hashlib,json,zipfile

ROOT=Path(__file__).resolve().parents[1]
for file,field,expected in [('quality/workbook_validation.json','all_values_match',True),
                            ('quality/sqlite_validation.json','integrity_check','ok'),
                            ('quality/reproducibility_report.json','all_identical',True)]:
    obj=json.loads((ROOT/file).read_text(encoding='utf-8'))
    assert obj[field]==expected,(file,field)
q=json.loads((ROOT/'quality/quality_summary.json').read_text(encoding='utf-8'))
assert q['status_counts'].get('FAIL',0)==0
def included(p):
    return p.is_file() and not p.is_symlink() and not any(x in p.parts for x in ['node_modules','__pycache__']) and not p.name.endswith(('.pyc','.inspect.ndjson'))
files=sorted(p for p in ROOT.rglob('*') if included(p) and p.name!='SHA256SUMS.txt')
lines=[hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(ROOT).as_posix() for p in files]
(ROOT/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
files.append(ROOT/'SHA256SUMS.txt')
archive=ROOT.parent/'Rayyan_Data_Package_2024_2025.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(files):
        info=zipfile.ZipInfo('Rayyan_Data_Package_2024_2025/'+p.relative_to(ROOT).as_posix(),date_time=(2026,11,7,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,p.read_bytes())
with zipfile.ZipFile(archive) as z: assert z.testzip() is None
print(json.dumps({'archive':str(archive),'files':len(files),'MiB':round(archive.stat().st_size/1024**2,3),'zip_integrity':'PASS'}))
