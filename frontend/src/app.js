import{request,post}from'./api/client.js';
import{save as saveProcess}from'./api/processes.js';
import{save as saveSample}from'./api/samples.js';
import{create,recommend,approve}from'./api/assessments.js';
import{save as saveDevice}from'./api/devices.js';
import{create as createStudy,saveReadings,publish as publishStudy,detail as studyDetailApi}from'./api/gauge.js';
import{store,refresh}from'./stores/business.js';
import{routes,route}from'./router/index.js';
import{ROLES}from'./constants/enums.js';
import{loginPage}from'./pages/login.js';
import{processesPage}from'./pages/processes.js';
import{samplesPage,sampleTable}from'./pages/samples.js';
import{analysisPage}from'./pages/analysis.js';
import{gaugePage,studyDetail as studyDetailView}from'./pages/gauge.js';
import{reviewsPage,reviewDetail}from'./pages/reviews.js';
import{flash}from'./components/common/notice.js';
import{table}from'./components/common/table.js';
import{esc}from'./utils/format.js';
import{values,busy}from'./hooks/forms.js';
import{polling}from'./hooks/poll.js';
const app=document.querySelector('#app');let stop=()=>{};
async function renderGauge(){
  let detailHtml='';
  const sid=store.study||store.studies[0]?.id;
  if(sid){try{const d=await studyDetailApi(sid);detailHtml=studyDetailView(d,d);}catch(e){detailHtml='';}}
  return gaugePage(detailHtml);
}
function render(){
  stop();
  if(!store.user){app.innerHTML=loginPage()+'<div id=flash class=flash hidden></div>';return;}
  let page=route();if(!routes[page])page='processes';
  const pages={processes:processesPage,samples:samplesPage,analysis:analysis,gauge:null,reviews:reviewsPage};
  app.innerHTML=`<header class=topbar><a href=#processes class=brand>和川包装<small>SEAL / MATERIAL STUDIES</small></a><nav>${Object.entries(routes).map(([k,v],i)=>`<a href=#${k} class=${page===k?'active':''}><small>0${i+1}</small>${v}</a>`).join('')}</nav><div class=identity><b>${ROLES[store.user.role]}</b><small>${esc(store.user.email)}</small></div><button id=logout>退出</button></header><main class=workspace id=workspace>${page==='gauge'?'<p class=empty>加载量测档案…</p>':({processes:processesPage,samples:samplesPage,analysis:analysisPage,reviews:reviewsPage}[page])()}</main><footer class=page-footer>HC · 工艺研究册 05<span>封口完整性 / 拉力测量 / 证据留痕</span></footer><div id=flash class=flash hidden></div>`;
  if(page==='gauge'){renderGauge().then(html=>{const w=document.querySelector('#workspace');if(w&&route()==='gauge')w.innerHTML=html;});}
  const select=document.querySelector('#review-select');if(select&&store.review)select.value=store.review;
  const recommendSelect=document.querySelector('#recommendation-form select');
  if(recommendSelect){const a=store.assessments.find(a=>a.id===+recommendSelect.form.dataset.id);if(a.selected_process_id)recommendSelect.value=a.selected_process_id;}
  if(page==='analysis')stop=polling(async()=>{if(store.assessments.some(a=>['queued','running'].includes(a.status))){await refresh();render();}});
  if(page==='gauge')stop=polling(async()=>{
    if(store.studies.some(s=>['queued','running'].includes(s.status))){
      await refresh();
      if(route()==='gauge'){const w=document.querySelector('#workspace');if(w)w.innerHTML=await renderGauge();}
    }
  });
}
async function init(){
  if(sessionStorage.getItem('seal-token')){
    try{store.user=await request('/auth/me');await refresh();}catch(e){sessionStorage.removeItem('seal-token');}
  }
  render();
}
window.addEventListener('hashchange',()=>{render();window.scrollTo(0,0);});
document.addEventListener('submit',async e=>{
  e.preventDefault();const f=e.target;busy(f,true);
  try{
    const d=values(f);
    if(f.id==='login-form'){const r=await post('/auth/login',d);sessionStorage.setItem('seal-token',r.access_token);store.user=r.user;await refresh();render();return;}
    if(f.id==='process-form'){await saveProcess({code:d.code,name:d.name,temperature:+d.temperature,dwell:+d.dwell,pressure:+d.pressure,note:d.note},d.id||null);await refresh();render();flash('工艺方案已保存，历史评议保留原始参数。');}
    if(f.id==='sample-form'){
      await saveSample({code:d.code,process_id:+d.process_id,lot:d.lot,force:+d.force,flagged:!!d.flagged,note:d.note,device_id:d.device_id?+d.device_id:null},d.id||null);
      await refresh();render();flash('拉力测量已保存；设备未获资格时已自动隔离留存。');
    }
    if(f.id==='device-form'){await saveDevice({code:d.code,name:d.name,note:d.note});await refresh();render();flash('量测设备已登记，初始状态为未获资格。');}
    if(f.id==='assessment-form'){
      const ids=[...f.querySelectorAll('[name=process_ids]:checked')].map(x=>+x.value);
      if(ids.length<2)throw new Error('请至少选择两种工艺');
      const a=await create({title:d.title,lot:d.lot,process_ids:ids});store.active=a.id;await refresh();render();flash('评估已提交后台，计算结果将自动刷新。');
    }
    if(f.id==='gauge-form'){
      const operators=d.operators_text.split(/[,，]/).map(x=>x.trim()).filter(Boolean);
      const thresholds={};
      if(d.grr_percent_max)thresholds.grr_percent_max=+d.grr_percent_max;
      if(d.ndc_min)thresholds.ndc_min=+d.ndc_min;
      if(d.max_missing_ratio)thresholds.max_missing_ratio=+d.max_missing_ratio;
      const s=await createStudy({code:d.code,title:d.title,device_id:+d.device_id,standard_count:+d.standard_count,replicate_count:+d.replicate_count,operators,thresholds});
      store.study=s.id;await refresh();render();flash('试验已建立，设备进入重测暂停；请在读数矩阵录数。');
    }
    if(f.id==='reading-form'){
      const sid=+f.dataset.id;
      const readings=[...f.querySelectorAll('.cell-input')].map(inp=>({
        standard_index:+inp.dataset.i,operator:inp.dataset.op,replicate:+inp.dataset.k,
        standard_label:'STD-'+inp.dataset.i,value:inp.value===''?null:+inp.value,
      }));
      const s=await saveReadings(sid,readings);store.study=sid;await refresh();
      if(s.status==='failed')flash('分解失败：'+(s.error||'读数矩阵不完整'),true);else{render();flash('读数已保存，后台重新分解中。');}
    }
    if(f.id==='recommendation-form'){await recommend(f.dataset.id,{selected_process_id:+d.selected_process_id,recommendation:d.recommendation});store.review=+f.dataset.id;await refresh();render();flash('工艺评议已保存，等待负责人签核。');}
  }catch(err){flash(err.message,true);}finally{if(f.isConnected)busy(f,false);}
});
document.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  try{
    if(b.id==='logout'){sessionStorage.removeItem('seal-token');store.user=null;render();}
    if(b.dataset.editProcess){const p=store.processes.find(x=>x.id===+b.dataset.editProcess),f=document.querySelector('#process-form');for(const k of['id','code','name','temperature','dwell','pressure','note'])f.elements[k].value=p[k];f.scrollIntoView({behavior:'smooth',block:'center'});flash('正在修订 '+p.code);}
    if(b.dataset.editSample){const s=store.samples.find(x=>x.id===+b.dataset.editSample),f=document.querySelector('#sample-form');for(const k of['id','code','process_id','lot','force','note'])f.elements[k].value=s[k];f.elements.flagged.checked=s.flagged;f.elements.device_id.value=s.device_id??'';f.scrollIntoView({behavior:'smooth',block:'center'});flash('正在修订 '+s.code);}
    if(b.dataset.assessment){store.active=+b.dataset.assessment;render();document.querySelector('#result-panel').scrollIntoView({behavior:'smooth',block:'start'});}
    if(b.dataset.study){store.study=+b.dataset.study;render();}
    if(b.dataset.export){const id=b.dataset.export;const r=await fetch('/api/assessments/'+id+'/export',{headers:{Authorization:'Bearer '+sessionStorage.getItem('seal-token')}});if(!r.ok)throw new Error('导出失败，请确认计算已完成');const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download='seal-variance-'+id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
    if(b.dataset.approve){await approve(b.dataset.approve);store.review=+b.dataset.approve;await refresh();render();flash('负责人已签核；本次评议已冻结。');}
    if(b.dataset.publish){
      const r=await publishStudy(+b.dataset.publish);
      await refresh();render();
      flash(r.released_sample_ids.length?`资格已发布，${r.released_sample_ids.length} 条隔离样本已放行。`:'资格发布完成；无达标放行样本（不达标时样本继续隔离）。');
    }
    if(b.id==='audit-button'){const rows=await request('/audit');document.querySelector('#audit-panel').innerHTML='<h2>操作审计</h2>'+table(['时间 UTC','操作人','动作','HTTP'],rows.map(x=>[esc(x.created_at.slice(0,19)),esc(x.actor),esc(x.action),x.status]));}
  }catch(err){flash(err.message,true);}
});
document.addEventListener('change',e=>{
  if(e.target.id==='sample-filter')document.querySelector('#sample-table').innerHTML=sampleTable(store.samples.filter(s=>!e.target.value||s.process_id===+e.target.value));
  if(e.target.id==='review-select'){store.review=+e.target.value;document.querySelector('#review-detail').innerHTML=reviewDetail(store.assessments.find(a=>a.id===store.review));const a=store.assessments.find(a=>a.id===store.review),s=document.querySelector('#recommendation-form select');if(s&&a.selected_process_id)s.value=a.selected_process_id;}
});
init();
