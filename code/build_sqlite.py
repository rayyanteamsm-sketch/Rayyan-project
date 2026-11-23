"""Load ALL 36 canonical CSV tables into SQLite with typed columns, PKs and deferred FKs."""
from pathlib import Path
import argparse,json,sqlite3
import pandas as pd

def build(root):
    root=Path(root)
    meta=json.loads((root/"metadata/table_metadata.json").read_text(encoding="utf-8"))
    dictionary=pd.read_csv(root/"metadata/data_dictionary.csv",keep_default_na=False)
    path=root/"Rayyan_Bermuda_2024_2025.sqlite"
    if path.exists():path.unlink()
    con=sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    counts={}
    try:
        for name,m in meta.items():
            defs=[];d=dictionary[dictionary.table==name]
            for r in d.itertuples(index=False):
                sqltype={"Float":"REAL","Integer":"INTEGER","Boolean":"INTEGER"}.get(r.data_type,"TEXT")
                defs.append('"'+r.column+'" '+sqltype+(' NOT NULL' if r.nullable=="no" else ""))
            pk=','.join('"'+c+'"' for c in m["primary_key"].split(','))
            defs.append('PRIMARY KEY('+pk+')')
            for fk in m["foreign_keys"].split(';'):
                if not fk:continue
                child,parent=fk.split('->');pt,pc=parent.split('.')
                defs.append(f'FOREIGN KEY("{child}") REFERENCES "{pt}"("{pc}") DEFERRABLE INITIALLY DEFERRED')
            con.execute('CREATE TABLE "'+name+'" ('+','.join(defs)+')')
        con.commit();con.execute("BEGIN")
        for name,m in meta.items():
            df=pd.read_csv(root/m["file"],keep_default_na=False,na_values=[''])
            rows=df.astype(object).where(pd.notnull(df),None).values.tolist()
            cols=','.join('"'+c+'"' for c in df.columns)
            placeholders=','.join('?' for c in df.columns)
            con.executemany('INSERT INTO "'+name+'" ('+cols+') VALUES ('+placeholders+')',rows)
            counts[name]=len(rows)
        con.commit()
        for label,relative,primary in [("_table_catalog","metadata/table_catalog.csv",["table"]),("_data_dictionary","metadata/data_dictionary.csv",["table","column"])]:
            frame=pd.read_csv(root/relative,keep_default_na=False,na_values=[''])
            definitions=[f'"{c}" '+('INTEGER' if c in ['row_count','column_count'] else 'TEXT') for c in frame.columns]
            definitions.append('PRIMARY KEY('+','.join('"'+c+'"' for c in primary)+')')
            con.execute('CREATE TABLE "'+label+'" ('+','.join(definitions)+')')
            values=frame.astype(object).where(pd.notnull(frame),None).values.tolist()
            con.executemany('INSERT INTO "'+label+'" VALUES ('+','.join('?' for c in frame.columns)+')',values)
        con.execute('CREATE TABLE "_package_info" ("key" TEXT PRIMARY KEY,"value" TEXT NOT NULL)')
        con.executemany('INSERT INTO "_package_info" VALUES (?,?)',[
            ('project','RAYYAN Bermuda 2024-2025;two hypothetical5m2zones'),
            ('origin_warning','Operational sensor/irrigation/plant records are SIMULATION,not field observations'),
            ('weather','ERA5 via Open-Meteo:reference reanalysis,not local field sensors'),
            ('field_ground_truth','NONE;not ready for production model validation')])
        con.commit()
        fk=con.execute('PRAGMA foreign_key_check').fetchall()
        integrity=con.execute('PRAGMA integrity_check').fetchone()[0]
        assert not fk and integrity=='ok'
        actual={n:con.execute('SELECT COUNT(*) FROM "'+n+'"').fetchone()[0] for n in meta}
        assert actual==counts
        report={"data_tables":len(counts),"metadata_tables":3,"row_counts":counts,"all_counts_match_csv":True,"foreign_key_violations":len(fk),"integrity_check":integrity,
            "timestamps":"UTC ISO8601 text;date_local Asia/Riyadh","telemetry":"COMPLETE;no review sampling","origin":"same reference/simulation classification as CSV"}
        (root/"quality/sqlite_validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("SQLite",len(counts),"complete tables",sum(counts.values()),"rows;FK and integrity PASS")
    finally:con.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);build(ap.parse_args().root)
