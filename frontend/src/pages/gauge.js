import{store}from'../stores/business.js';
import{esc,num,pvalue}from'../utils/format.js';
import{table}from'../components/common/table.js';
import{field,options}from'../components/common/fields.js';
import{readonly}from'../components/common/notice.js';
import{DEVICE_STATUS,DISPOSITION}from'../constants/enums.js';

function deviceBadge(status){return `<span class="badge" data-state=${status==='qualified'?'approved':status==='requalifying'?'failed':''}>${DEVICE_STATUS[status]||status}</span>`;}
function studyBadge(s){
  const state=s.published?'approved':s.status;
  const label=s.published?(s.result?.qualified?'资格已发布':'发布未达标'):({queued:'待分解',running:'分解中',completed:'待发布',failed:'分解失败'}[s.status]||s.status);
  return `<span class="badge" data-state=${state}>${label}</span>`;
}
export function devicesPanel(){
  return `<section><div class=section-title><h2>量测设备台账</h2><span>资格状态随试验发布原子切换</span></div>
  ${table(['设备编号','名称','资格状态','说明'],store.devices.map(d=>[esc(d.code),esc(d.name),deviceBadge(d.status),esc(d.note||'—')]))}
  ${store.user.role==='viewer'?'':`<h3 class=form-subhead>登记设备</h3><form id=device-form>
    ${field('设备编号','code','text','required maxlength=50')}
    ${field('设备名称','name','text','required minlength=2')}
    <label>说明<textarea name=note rows=2></textarea></label>
    <button class=primary>保存设备</button></form>`}</section>`;
}
export function studyForm(){
  if(store.user.role==='viewer')return readonly();
  return `<form id=gauge-form>
    ${field('试验编号','code','text','required maxlength=50 value=GRR-2026-01')}
    ${field('试验标题','title','text','required minlength=2 value=季度量测资格试验')}
    <label>受测设备<select name=device_id required>${options(store.devices.map(d=>[d.id,d.code+' / '+d.name]))}</select></label>
    <div class=form-two>
      ${field('标准件数','standard_count','number','required min=2 max=20 step=1 value=5')}
      ${field('重复次数','replicate_count','number','required min=2 max=10 step=1 value=3')}
    </div>
    <label>操作员（逗号分隔，至少2人）<input name=operators_text required value="王工,李工,周工"></label>
    <fieldset><legend>判定阈值（留空用默认 10% / NDC 5 / 缺测 10%）</legend>
      <div class=form-two>
        ${field('%GRR 上限','grr_percent_max','number','min=0.01 max=100 step=0.1 placeholder=10')}
        ${field('NDC 下限','ndc_min','number','min=1 max=50 step=1 placeholder=5')}
      </div>
      ${field('缺测比例上限','max_missing_ratio','number','min=0 max=0.99 step=0.01 placeholder=0.1')}
    </fieldset>
    <button class=primary>建试验并发起重测 →</button>
    <p class=small>建试验即把设备置为「重测暂停」：生产样本照常收，但隔离留存、暂缓入评议，直到达标发布。</p>
  </form>`;
}
export function studyList(onSelect){
  return store.studies.map(s=>{const d=store.devices.find(x=>x.id===s.device_id);
    return `<button class=history-row data-study=${s.id}><span>#${s.id}　${esc(s.code)} · ${esc(s.title)}<small>${esc(d?.code||'')} ｜ ${s.standard_count}标准件 × ${s.operators.length}操作员 × ${s.replicate_count}重复</small></span>${studyBadge(s)}</button>`;
  }).join('')||'<p class=empty>尚无量测资格试验。</p>';
}
function readingMatrix(s,detail){
  const existing={};
  for(const r of detail.readings||[])existing[`${r.standard_index}|${r.operator}|${r.replicate}`]=r.value;
  const rows=[];
  for(let i=1;i<=s.standard_count;i++){
    for(const op of s.operators){
      for(let k=1;k<=s.replicate_count;k++){
        const key=`${i}|${op}|${k}`,v=existing[key];
        rows.push(`<tr><td>STD-${i}</td><td>${esc(op)}</td><td>${k}</td>
          <td><input class=cell-input data-i=${i} data-op="${esc(op)}" data-k=${k} type=number min=0.01 max=200 step=0.001 value="${v??''}" placeholder="空=缺测"></td></tr>`);
      }
    }
  }
  return `<form id=reading-form data-id=${s.id}><p class=small>每个标准件 × 操作员 × 重复次数一格；留空即按缺测（null）登记，不插补、不删格。</p>
    <div class=table-scroll><table><thead><tr><th>标准件</th><th>操作员</th><th>重复</th><th>读数 N（留空=缺测）</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>
    <button class=primary>保存读数并重新分解</button></form>`;
}
function grrResult(s){
  const r=s.result;if(!r)return `<p class=empty>分解完成后展示方差分量与判定。${s.error?esc(s.error):''}</p>`;
  const m=r.metrics;
  const checkRow=c=>`<span class="check-pill ${c.pass?'pass':'fail'}">${c.pass?'✓':'✕'} 实测 ${num(c.value,c.value<1?4:2)} / 阈值 ${num(c.limit,c.limit<1?4:2)}</span>`;
  const vc=r.variance_components;
  return `<div class=grr-result>
    <div class=verdict><span class="${r.qualified?'ok':'no'}">${r.qualified?'满足资格阈值，可发布':'未达资格阈值，不得发布'}</span>
      <p>${r.verdict_reasons.length?r.verdict_reasons.map(esc).join('；'):'三项阈值全部通过。'}</p>
      ${r.handling_notes.map(x=>`<p class=notice>${esc(x)}</p>`).join('')}
      <div class=pills>${checkRow(r.checks.missing_ratio)}${checkRow(r.checks.grr_percent)}${checkRow(r.checks.ndc)}</div>
    </div>
    <h3>双因素有重复 ANOVA 分解${r.balanced?'':'（含缺测 · Type III）'}</h3>
    ${table(['变异来源','平方和 SS','df','均方 MS','F','p'],r.anova.map(x=>[esc(x.source),num(x.ss),x.df,x.ms===null?'—':num(x.ms),x.f===null?'不成立':num(x.f,3),x.p===null?'—':pvalue(x.p)]))}
    <h3>方差分量与研究变异（6σ 口径）</h3>
    ${table(['分量','方差估计','说明'],[
      ['重复性（设备内 EV）',num(vc.repeatability),'同一操作员重复测量波动'],
      ['再现性（操作员 AV）',num(vc.operator),'操作员间系统差异'],
      ['交互（标准件×操作员）',num(vc.interaction),'负值为估计噪声，汇总截断为0'],
      ['标准件（零件间 PV）',num(vc.part),'真实工艺/标准件差异，非量测误差'],
      ['GR&R 合计',num(vc.grr),'EV+AV+交互（负分量零截断）'],
      ['总变异',num(vc.total),'GR&R + 零件间'],
    ])}
    <div class=stats>
      <div><small>%GRR 研究变异占比</small><b>${num(m.pct_grr,2)}%</b></div>
      <div><small>NDC 可区分类别数</small><b>${num(m.ndc,2)}</b></div>
      <div><small>有效读数 / 缺测</small><b>${r.n_observed} / ${r.n_missing}</b></div>
      <div><small>缺测比例</small><b>${num(r.missing_ratio*100,2)}%</b></div>
    </div>
    <p class=method>${esc(r.method)}</p>
    <p class=checksum>输入 SHA-256：${esc(r.checksum)}</p>
  </div>`;
}
export function studyDetail(s,detail){
  if(!s)return '<p class=empty>选择左侧试验查看分解与录数。</p>';
  const canEdit=store.user.role!=='viewer'&&!s.published;
  return `<div class=review-head><div><span class=eyebrow>GAUGE STUDY #${s.id}</span><h2>${esc(s.title)}</h2>
    <p class=small>阈值：%GRR ≤ ${s.thresholds.grr_percent_max} ｜ NDC ≥ ${s.thresholds.ndc_min} ｜ 缺测 ≤ ${num(s.thresholds.max_missing_ratio*100,1)}%</p></div>${studyBadge(s)}</div>
    ${grrResult(s)}
    <h3 class=form-subhead>${s.published?'试验已发布冻结，重测请新建试验':'读数矩阵录数'}</h3>
    ${canEdit?readingMatrix(s,detail):'<p class=notice>只读账号或试验已冻结；缺测与读数矩阵仍可在上方结果中核对。</p>'}
    ${store.user.role==='admin'&&!s.published&&s.status==='completed'?`<button class=approve data-publish=${s.id}>发布资格${s.result?.qualified?'并放行隔离样本':'（不达标：仅留痕，不放行）'}</button>`:''}
    ${s.published?`<p class=small>发布人 ${esc(s.published_by)} ｜ ${esc(s.published_at.slice(0,19).replace('T',' '))} UTC</p>`:''}`;
}
export function isolationPanel(){
  const rows=store.held;
  return `<section><div class=section-title><h2>隔离与放行去向</h2><span>不合格设备的样本留存不删，达标发布后放行</span></div>
  ${table(['样本编号','批次','设备','去向','隔离依据'],(rows.length?rows:[]).map(x=>[esc(x.sample_code),esc(x.lot),esc(x.device_code),
    `<span class="badge" data-state=${x.disposition==='released'?'approved':'failed'}>${DISPOSITION[x.disposition]||x.disposition}</span>`,esc(x.hold_reason||'—')]))}
  ${rows.length?'':'<p class=empty>当前无隔离或放行留痕样本。</p>'}</section>`;
}
export function gaugePage(studyDetailHtml){
  return `<header class=page-head><div><span class=eyebrow>05 / GAUGE R&amp;R QUALIFICATION</span><h1>设备量测资格试验</h1>
    <p>按标准件 × 操作员 × 重复次数录数，分解重复性、再现性与交互变异；把设备波动与工艺差异分开。</p></div>
    <span class=folio>${store.studies.length}<small>资格试验</small></span></header>
    <div class=split><div>
      <div class=section-title><h2>试验档案</h2><span>点击查看分解</span></div>
      <div id=study-list>${studyList()}</div>
      <div id=study-detail class=study-detail>${studyDetailHtml||''}</div>
      ${isolationPanel()}
    </div>
    <aside class=form-panel><h2>新建资格试验</h2>${studyForm()}<h3 class=form-subhead>设备台账</h3>${devicesPanel()}</aside></div>`;
}
