import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const payload=JSON.parse(await fs.readFile(root+'/metadata/workbook_payload.json','utf8'));
// Full CSVs are canonical. The default review workbook keeps all functional
// tables, all decision/outcome sensor references and all injected data defects.
// Only the four large telemetry tables are reduced, with an explicit index.
const reviewMode=process.env.RAYYAN_EXCEL_FULL!=='1';
const reviewIndex=[];
if(reviewMode){
 const t=payload.tables;
 const selected=new Set(t.decisions.rows.map(r=>r[7]).filter(Boolean));
 for(const r of t.event_outcomes.rows){selected.add(r[3]);for(const id of r[5].split(';'))selected.add(id);}
 const badMessages=new Set(t.injection_audit.rows.map(r=>r[1]));
 for(const r of t.measurements_raw.rows)if(badMessages.has(r[0]))selected.add(r[1]);
 const takeEven=(rows,n)=>{const ids=new Set();for(let i=0;i<Math.min(n,rows.length);i++)ids.add(Math.floor(i*(rows.length-1)/(Math.min(n,rows.length)-1)));return rows.filter((r,i)=>ids.has(i));};
 for(const r of takeEven(t.measurements_clean.rows,700))selected.add(r[0]);
 for(const [name,tab]of Object.entries(t)){
  const full=tab.rows.length;let policy='complete';
  if(name==='measurements_clean'){tab.rows=tab.rows.filter(r=>selected.has(r[0]));policy='all_decision_and_outcome_samples_all_defects_plus_even_time_sample';}
  if(name==='measurements_raw'){tab.rows=tab.rows.filter(r=>selected.has(r[1]));policy='all_messages_for_selected_samples_including_duplicate_defects';}
  if(name==='weather_reanalysis'){tab.rows=takeEven(tab.rows,1000);policy='even_time_review_only_full_hourly_series_in_CSV_SQLite';}
  if(name==='flow_measurements'){
   const groups=new Map();for(const r of tab.rows){if(!groups.has(r[1]))groups.set(r[1],[]);groups.get(r[1]).push(r);}
   const faulty=new Set(t.irrigation_events.rows.filter(r=>r[13]!==null).map(r=>r[0]));
   tab.rows=[];for(const [id,g]of groups){tab.rows.push(...(faulty.has(id)?g:g.filter((r,i)=>i<=5||i===g.length-1)));}
   policy='first5minute_readings_and_endpoints_each_event_full_fault_events';
  }
  tab.meta.csv_row_count=full;tab.meta.excel_row_count=tab.rows.length;tab.meta.review_policy=policy;
  reviewIndex.push([name,full,tab.rows.length,policy,tab.meta.file]);
 }
 const columns=['table','rows_csv','rows_excel','coverage_policy','complete_file'];
 const encode=v=>'"'+String(v??'').replaceAll('"','""')+'"';
 await fs.writeFile(root+'/quality/excel_review_manifest.csv',[columns,...reviewIndex].map(r=>r.map(encode).join(',')).join('\n')+'\n','utf8');
 t.excel_review_index={columns,rows:reviewIndex,meta:{data_type:'documentation',file:'quality/excel_review_manifest.csv'}};
}
const previewDir=process.env.RAYYAN_PREVIEW_DIR || root+'/../../tmp/rayyan_package_previews';
await fs.mkdir(previewDir,{recursive:true});
const wb=Workbook.create();
const C={teal:'#154B50',ink:'#19343E',pale:'#E8F3F0',purple:'#765C99',lav:'#F0ECF7',gold:'#9C7022',cream:'#FFF5DF',blue:'#1C5D87',red:'#A83538'};
const col=n=>{let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
const guide=wb.worksheets.add('Read_Me');
const summary=wb.worksheets.add('Summary');
const names=Object.keys(payload.tables);
for(const name of names) wb.worksheets.add(name);
const dict=payload.tables.data_dictionary;
const definitions=new Map(dict.rows.map(r=>[r[0]+'.'+r[1],{type:r[3],unit:r[4]}]));
const docs=new Set(['sources','assumptions','field_collection_plan','function_readiness','data_dictionary','quality_checks','table_catalog','excel_review_index']);
const inspections=[];

for(const name of names){
 const sh=wb.worksheets.getItem(name); const t=payload.tables[name]; const columns=t.columns;
 const n=t.rows.length; const last=col(columns.length-1); const end=n+4;
 sh.showGridLines=false; sh.tabColor=t.meta.data_type==='reference'?C.blue:docs.has(name)?C.gold:C.purple;
 sh.getRange(`A1:${last}1`).merge(); sh.getRange('A1').values=[[name]];
 sh.getRange(`A1:${last}1`).format={fill:C.teal,font:{name:'Arial',size:16,bold:true,color:'#FFFFFF'},rowHeight:34};
 sh.getRange(`A2:${last}2`).merge();
 const origin=t.meta.data_type||'documentation';
 const reviewNote=t.meta.csv_row_count>n?`REVIEW SUBSET ${n}/${t.meta.csv_row_count}; full CSV/SQLite. معاينة جزئية؛ الكامل في CSV وSQLite. `:'';
 const note=reviewNote+(origin.includes('simulation')?'SIMULATION / محاكاة — لا قياسات ميدانية. ':origin==='reference'?'REFERENCE / مرجع — راجع حدود المصدر. ':origin==='observed_aggregate'?'PUBLISHED AGGREGATES / متوسطات مرصودة منشورة1985–2010. ':'DOCUMENTATION / توثيق. ')+(t.meta.grain_ar||t.meta.file||'');
 sh.getRange('A2').values=[[note]];
 sh.getRange(`A2:${last}2`).format={fill:origin.includes('simulation')?C.lav:C.cream,font:{name:'Arial',size:11,color:C.ink},rowHeight:40,wrapText:true,horizontalAlignment:'right'};
 sh.getRange(`A4:${last}4`).values=[columns];
 sh.getRange(`A4:${last}4`).format={fill:C.teal,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:42,wrapText:true,verticalAlignment:'center'};
 for(let i=0;i<n;i+=4000){
   const rows=t.rows.slice(i,i+4000).map(row=>row.map((v,j)=>{
     const def=definitions.get(name+'.'+columns[j]);
     // Explicit UTC Excel serials avoid renderer timezone conversion of Date objects.
     if(v!==null && def?.type==='Datetime' && n<10000)return (Date.parse(v)-Date.UTC(1899,11,30))/86400000;
     if(v!==null && def?.type==='Date' && n<10000)return (Date.parse(v+'T00:00:00Z')-Date.UTC(1899,11,30))/86400000;
     if(typeof v==='string' && v.startsWith('='))return "'"+v;
     return v;
   }));
   sh.getRange(`A${i+5}:${last}${i+4+rows.length}`).values=rows;
 }
 if(n && n<10000){
   const all=sh.getRange(`A5:${last}${end}`);
   all.format.font={name:'Arial',size:10,color:C.ink};all.format.rowHeight=docs.has(name)?58:20;
   all.format.verticalAlignment='center';
   if(docs.has(name)){all.format.wrapText=true;all.format.horizontalAlignment='right';}
   // Native Excel tables provide filters and alternating bands without per-row API operations.
   sh.tables.add(`A4:${last}${end}`,true,'T_'+name);
 }
 columns.forEach((c,j)=>{
   const letter=col(j);const def=definitions.get(name+'.'+c);
   let width=22;
   if(def?.type==='Datetime')width=n>=10000?35:25;
   else if(c.endsWith('_ar')||['definition_ar','source_or_derivation','limitation_ar','description_ar'].includes(c))width=55;
   else if(['url','locator','foreign_keys','source_or_derivation','license_restrictions'].includes(c))width=65;
   else if(c.endsWith('_id'))width=25;
   else if(def?.type==='Float')width=20;
   sh.getRange(`${letter}1:${letter}4`).format.columnWidth=width;
   if(n && n<10000 && def?.type==='Datetime')sh.getRange(`${letter}5:${letter}${end}`).setNumberFormat('yyyy-mm-dd hh:mm:ss');
   else if(n && n<10000 && def?.type==='Date')sh.getRange(`${letter}5:${letter}${end}`).setNumberFormat('yyyy-mm-dd');
   else if(n && n<10000 && def?.type==='Float')sh.getRange(`${letter}5:${letter}${end}`).setNumberFormat(name.startsWith('study_')?'0.0000000000':(c.includes('vwc')?'0.000000':'0.0000'));
   else if(n && n<10000 && def?.type==='Integer')sh.getRange(`${letter}5:${letter}${end}`).setNumberFormat('0');
 });
 sh.freezePanes.freezeRows(4);sh.freezePanes.freezeColumns(1);
 if(name==='quality_checks'){
   const statusCol=col(columns.indexOf('status'));
   t.rows.forEach((r,i)=>{const status=r[columns.indexOf('status')];sh.getRange(`${statusCol}${i+5}`).format.fill=status==='PASS'?'#E2F0E9':status==='FAIL'?'#FCE0DF':'#FFF0CC';});
 }
 console.log('sheet',name,n);
}

guide.showGridLines=false;guide.tabColor=C.teal;
guide.getRange('A1:H36').format.font={name:'Arial',size:12,color:C.ink};
guide.getRange('A1:H36').format.rowHeight=28;
for(let j=0;j<8;j++)guide.getRange(`${col(j)}1:${col(j)}36`).format.columnWidth=17;
function banner(range,text,fill=C.teal,size=16){guide.getRange(range).merge();guide.getRange(range.split(':')[0]).values=[[text]];guide.getRange(range).format={fill,font:{name:'Arial',size,bold:true,color:fill===C.teal?'#FFFFFF':C.ink},wrapText:true,horizontalAlignment:'right',verticalAlignment:'center'};}
banner('A1:H2','ريّان | RAYYAN — حزمة بيانات البرمودا',C.teal,22);
banner('A4:H5','الرياض | منطقتان | 2024–2025 | الثيل البرمودا Cynodon dactylon',C.pale,16);
banner('A7:H9','ملف مراجعة: الجداول الوظيفية كاملة، ومعاينات معلّمة للسلاسل الأربع الكبيرة. البيانات الكاملة في CSV وSQLite. القياسات التشغيلية محاكاة. راجعي excel_review_index.',C.cream,13);
const qs=payload.qc_summary;
const notes=[
 ['ابدئي من','table_catalog لفهرس الملفات؛ data_dictionary لتعريف الأعمدة؛ sources للمصادر والقيود.'],
 ['بيانات الطقس','weather_reanalysis: عدد17,544ساعة منERA5؛ منتج شبكي مرجعي، وليس حساسًا داخل الحديقة.'],
 ['بيانات الدراسة','study_climate متوسطات1985–2010؛ study_crop وstudy_parameters قيم وحسابات مرجعية منشورة.'],
 ['البيانات التشغيلية','جميع الحساسات والتوقعات والأوامر والريات والنتائج بالحزمة افتراضية ومحددة المصدرSIM01.'],
 ['الرابط الأساسي','sites → zones → decisions → irrigation_events → event_outcomes؛ الأجهزة تربط الخام والمعايرة والتدفق.'],
 ['التوقيت والوحدات','كل أوقات Excel معروضةUTC؛ أضيفي3ساعات للرياض. CSV يحفظISO8601. VWC بوحدةm³/m³؛ الماءL أوmmمع وحدة الحقل.'],
 ['الخام والنظيف','measurements_raw محفوظ مع التكرارات؛ measurements_clean عينة واحدة، وأصل القيمة المحولة مع قيمة صالحة أوNULL.'],
 ['التعلم الآلي','ml_features منفصلة عنml_targets؛ تقسيم زمني محفوظ. Target فرق الرطوبة، وليس الجرعة المثلى.'],
 ['صلاحية النموذج','نتائجdemo_model_metrics لمحاكاة فقط؛ لا دقة ميدانية ولا إثبات توفير. نماذج التجربة لا تنفذ أوامر حقيقية.'],
 ['نتائج الجودة',`${qs.checks}فحصًا: ${qs.status_counts.PASS||0}ناجح؛ ${qs.status_counts.EXPECTED_ISSUE||0}مجموعات أخطاء اختبار؛ ${qs.status_counts.OPEN_GAP||0}فجوات معلنة؛ ${qs.status_counts.FAIL||0}فشل اتساق.`],
 ['ما يحتاج الميدان','field_collection_plan وfield_templates فيZIP: معايرة، خصائص تربة، قياسات قبل/بعد الري، نبات، حدود الماء وتكلفة فعلية.'],
 ['إعادة الإنتاج','README_AR.md وcode/*.py وconfig.json وraw/weather_era5.json داخل الحزمة؛ seed=20261107.'],
];
notes.forEach((r,i)=>{
 const k=12+i*2;guide.getRange(`A${k}:B${k+1}`).merge();guide.getRange(`A${k}`).values=[[r[0]]];guide.getRange(`C${k}:H${k+1}`).merge();guide.getRange(`C${k}`).values=[[r[1]]];
 guide.getRange(`A${k}:B${k+1}`).format={fill:C.pale,font:{name:'Arial',size:12,bold:true,color:C.ink},wrapText:true,horizontalAlignment:'right',verticalAlignment:'center'};
 guide.getRange(`C${k}:H${k+1}`).format={font:{name:'Arial',size:12,color:C.ink},wrapText:true,horizontalAlignment:'right',verticalAlignment:'center'};
});
guide.freezePanes.freezeRows(5);

summary.showGridLines=false;summary.tabColor=C.purple;
summary.getRange('A1:G2').merge();summary.getRange('A1').values=[['ملخص محاكاة — لا يمثل نتائج ميدانية']];
summary.getRange('A1:G2').format={fill:C.purple,font:{name:'Arial',size:19,bold:true,color:'#FFFFFF'},rowHeight:30,horizontalAlignment:'right'};
summary.getRange('A4:G5').merge();summary.getRange('A4').values=[['المقارنة بين منطقتين افتراضيتين واحدة لكل ذراع. أرقام الماء والإجهاد ناتجة عن الافتراضات؛ لا يصح استخدامها لإثبات توفير واقعي أو صلاحية زراعية.']];
summary.getRange('A4:G5').format={fill:C.cream,font:{name:'Arial',size:12,color:C.ink},wrapText:true,rowHeight:28,horizontalAlignment:'right'};
summary.getRange('A7:G7').values=[['zone_id','trial_arm','event_count','delivered_volume_l','delivered_mm_2yr','valid_ML_labels','area_m2_assumed']];
summary.getRange('A7:G7').format={fill:C.teal,font:{name:'Arial',size:11,bold:true,color:'#FFFFFF'},rowHeight:46,wrapText:true};
for(let i=0;i<2;i++){
 const r=8+i;const z='Z0'+(i+1);summary.getRange(`A${r}:B${r}`).values=[[z,i===0?'conventional':'rayyan']];
 const ec=payload.tables.irrigation_events.rows.length+4;const dc=payload.tables.decisions.rows.length+4;const oc=payload.tables.event_outcomes.rows.length+4;
 summary.getRange(`C${r}`).formulas=[[`=COUNTIF(irrigation_events!C5:C${ec},A${r})`]];
 summary.getRange(`D${r}`).formulas=[[`=SUMIF(irrigation_events!C5:C${ec},A${r},irrigation_events!L5:L${ec})`]];
 summary.getRange(`G${r}`).values=[[payload.config.zone_area_m2]];
 summary.getRange(`E${r}`).formulas=[[`=D${r}/G${r}`]];
 const features=payload.tables.ml_features;const tar=payload.tables.ml_targets;const vals=new Map(tar.rows.map(x=>[x[0],x[4]]));
 summary.getRange(`F${r}`).values=[[features.rows.filter(x=>x[1]===z && vals.get(x[0])==='valid_simulation_only').length]];
}
summary.getRange('A8:G9').format={font:{name:'Arial',size:12,color:C.ink},rowHeight:32};summary.getRange('D8:G9').setNumberFormat('0.00');
summary.getRange('A12:G14').merge();summary.getRange('A12').values=[['قراءة صحيحة: delivered_volume_l حجم منفذ في سيناريو. delta_vwc استجابة محاكاة. cover_pct مؤشرProxy غير متحقق. water_tariff_sar_m3 سعر خيالي2ر.س/م³. energy_kwh غير متاح. الإقرار بالفتح لا يثبت وضع صمام فيزيائي.']];
summary.getRange('A12:G14').format={fill:C.lav,font:{name:'Arial',size:12,color:C.ink},wrapText:true,rowHeight:28,horizontalAlignment:'right'};
for(let j=0;j<7;j++)summary.getRange(`${col(j)}1:${col(j)}18`).format.columnWidth=j===1?24:23;
summary.freezePanes.freezeRows(7);
wb.recalculate();
for(const name of ['Read_Me','Summary',...names]){
 const t=payload.tables[name];const end=t?Math.min(10,t.rows.length+4):name==='Summary'?14:9;
 const last=t?col(Math.min(t.columns.length-1,5)):name==='Summary'?'G':'H';
 const render=await wb.render({sheetName:name,range:`A${t?4:1}:${last}${end}`,scale:1,format:'png'});
 await fs.writeFile(previewDir+'/'+name+'.png',new Uint8Array(await render.arrayBuffer()));
 if(global.gc && ['Read_Me','measurements_clean','data_dictionary'].includes(name))global.gc();
}
for(const name of ['Summary','quality_checks','data_dictionary','weather_reanalysis','ml_targets']){
 inspections.push(await wb.inspect({kind:'region',sheetId:name,range:name==='Summary'?'A7:G9':'A4:F8',maxChars:1800,tableMaxRows:5,tableMaxCols:6}));
}
await fs.writeFile(previewDir+'/inspect.json',JSON.stringify(inspections,null,2));
const file=await SpreadsheetFile.exportXlsx(wb);
await file.save(root+'/Rayyan_Bermuda_2024_2025.xlsx');
await fs.writeFile(root+'/quality/excel_expected_review.json',JSON.stringify({tables:payload.tables},null,0),'utf8');
console.log('saved',root+'/Rayyan_Bermuda_2024_2025.xlsx');
