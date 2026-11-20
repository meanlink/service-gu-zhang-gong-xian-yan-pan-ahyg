import {datasets,jobs,gaps} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
const fmtMin=v=>Number(v).toLocaleString('zh-CN',{maximumFractionDigits:2});
export async function gapPage(){
 const [allDatasets,allJobs]=await Promise.all([datasets.list(),jobs.list()]);
 workspace.datasets=allDatasets;workspace.jobs=allJobs;
 const datasetId=workspace.gapDataset&&allDatasets.some(d=>d.id===workspace.gapDataset)?workspace.gapDataset:(allDatasets[0]?.id??null);
 workspace.gapDataset=datasetId;
 const detail=datasetId?await datasets.get(datasetId):null;
 const services=detail?[...new Set(detail.records.map(r=>String(r.service)))].sort():[];
 const gapList=datasetId?await gaps.list(datasetId):[];
 const jobId=workspace.gapJob&&allJobs.some(j=>j.id===workspace.gapJob)?workspace.gapJob:(allJobs.find(j=>j.invalidated)||allJobs[0])?.id??null;
 workspace.gapJob=jobId;
 let basis=null,basisError='';
 if(jobId){try{basis=await jobs.exclusions(jobId);}catch(e){basisError=e.message;}}
 workspace.gapBasis=basis;
 const job=allJobs.find(j=>j.id===jobId);
 return heading('05 / GAP REGISTRY','断档补登与剔除依据','按服务登记缺测区间：源事件跟随窗内任一方缺测，即从该方向跟随率的分子与分母一并剔除。补登后取样受影响的试验失效并拒绝批准，其他试验照常出简报。')+'<div class="report-grid"><section class="panel"><div class="section-title"><h2>补登缺测区间</h2><span>登记幂等 · 重试不重复留档</span></div><form id="gap-form"><label>数据批次<select name="dataset_id" id="gap-dataset">'+allDatasets.map(d=>'<option value="'+d.id+'" '+(d.id===datasetId?'selected':'')+'>'+esc(d.name)+' · '+d.rows+' 条</option>').join('')+'</select></label><label>缺测服务<input name="service" list="service-options" required placeholder="例如 cache"><datalist id="service-options">'+services.map(s=>'<option value="'+esc(s)+'">').join('')+'</datalist></label><div class="parameter-grid"><label>区间起点（周内累计分钟）<input type="number" step="any" min="0" name="start_min" required placeholder="例如 1200"></label><label>区间终点<input type="number" step="any" min="0" name="end_min" required placeholder="例如 1260"></label></div><label>断档原因<textarea name="reason" rows="2" placeholder="例如：采集代理重启，告警未入档"></textarea></label><button type="submit" class="primary" '+(session.user.role==='viewer'||!allDatasets.length?'disabled':'')+'>登记缺测区间</button><p class="hint">登记即刻生效：受影响试验失效并撤回批准，进行中的分发按登记先后拦截；已发出的归档保留原取样依据。</p></form><div class="section-title"><h2>已登记断档</h2><span>'+gapList.length+' 段</span></div><div class="schedule-list">'+gapList.map(g=>'<article><div><strong>'+esc(g.service)+' · ['+fmtMin(g.start_min)+' → '+fmtMin(g.end_min)+'] 分钟</strong><p>'+esc(g.reason||'未填写原因')+'</p><small>'+esc(g.registered_by)+' · '+date(g.registered_at)+' · '+(g.applied?'失效标记已完成':'失效标记待恢复')+'</small></div></article>').join('')+(!gapList.length?'<p class="empty">该批次尚无缺测登记。</p>':'')+'</div></section><section><div class="section-title"><h2>剔除依据查询</h2><span>逐方向剔除明细</span></div><div class="result-selector"><label>分析记录<select id="gap-job">'+allJobs.map(j=>'<option value="'+j.id+'" '+(j.id===jobId?'selected':'')+'>'+esc(j.name)+' · '+esc(j.status)+(j.invalidated?' · 已失效':'')+'</option>').join('')+'</select></label></div>'+(basis?renderBasis(job,basis):'<p class="empty">'+(basisError?'无法计算剔除依据：'+esc(basisError):'尚无分析任务可查询。')+'</p>')+'</section></div>';
}
function renderBasis(job,basis){
 let html='';
 if(job&&job.invalidated)html+='<p class="warning">该试验已因断档补登失效，不能批准、不再出简报。失效依据：'+basis.invalidations.map(v=>'缺测 #'+v.gap_id+' · '+esc(v.detail.service)+' ['+fmtMin(v.detail.start_min)+' → '+fmtMin(v.detail.end_min)+'] 分钟 · '+date(v.created_at)).join('；')+'</p>';
 html+='<p class="hint">跟随窗口 '+esc(basis.window_min)+' 分钟 · 已登记缺测 '+basis.gaps.length+' 段</p>';
 if(!basis.directions.length)return html+'<p class="empty">当前登记下没有源事件被剔除。</p>';
 html+='<div class="table-wrap"><table><thead><tr><th>方向</th><th>剔除事件数</th><th>有效事件数</th><th>剔除样本</th></tr></thead><tbody>'+basis.directions.map((d,i)=>'<tr><td>'+esc(d.source)+' → '+esc(d.target)+'</td><td>'+d.excluded_events+'</td><td>'+d.eligible_events+'</td><td><button class="text-button" data-direction="'+i+'">查看样本 ↓</button></td></tr>').join('')+'</tbody></table></div><div id="direction-sample"></div>';
 return html;
}
function renderSample(direction){
 const basis=workspace.gapBasis;
 if(!basis)return;
 const d=basis.directions[direction];
 document.querySelector('#direction-sample').innerHTML='<div class="section-title"><h2>'+esc(d.source)+' → '+esc(d.target)+' 被剔除源事件</h2><span>样本 '+d.sample.length+' 条'+(d.sample_truncated?' · 另有 '+d.sample_truncated+' 条未展开':'')+'</span></div><div class="table-wrap"><table><thead><tr><th>事件ID</th><th>发生分钟</th><th>跟随窗止</th><th>命中缺测区间</th></tr></thead><tbody>'+d.sample.map(e=>'<tr><td>'+esc(e.event_id)+'</td><td>'+fmtMin(e.occurred_min)+'</td><td>'+fmtMin(e.window_end)+'</td><td>'+e.gaps.map(g=>'#'+g.gap_id+' '+esc(g.service)+' ['+fmtMin(g.start_min)+' → '+fmtMin(g.end_min)+']').join('<br>')+'</td></tr>').join('')+'</tbody></table></div>';
}
export function bindGaps(refresh){
 document.querySelector('#gap-dataset')?.addEventListener('change',e=>{workspace.gapDataset=Number(e.target.value);refresh();});
 document.querySelector('#gap-job')?.addEventListener('change',e=>{workspace.gapJob=Number(e.target.value);refresh();});
 document.querySelectorAll('[data-direction]').forEach(b=>b.onclick=()=>renderSample(Number(b.dataset.direction)));
 submit(document.querySelector('#gap-form'),async f=>{
   const datasetId=Number(f.get('dataset_id'));
   const result=await gaps.create(datasetId,{service:f.get('service'),start_min:Number(f.get('start_min')),end_min:Number(f.get('end_min')),reason:f.get('reason')||''});
   notify(result.created?('缺测区间已登记，'+result.invalidated_jobs.length+' 个试验失效'):'相同区间已登记过，未重复留档');
   await refresh();
 });
}
