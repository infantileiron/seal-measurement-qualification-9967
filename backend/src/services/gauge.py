import os
from datetime import datetime,timezone
from sqlalchemy import select
from fastapi import HTTPException
import redis
from src.models.entities import Device,GaugeStudy,GaugeReading,Sample,ReleaseLedger
from src.services.grr import grr_analysis,normalize_thresholds
queue=redis.Redis.from_url(os.environ['REDIS_URL'])
def _now():return datetime.now(timezone.utc).isoformat()
# ---------- 设备 ----------
def list_devices(db):return db.scalars(select(Device).order_by(Device.id)).all()
def save_device(db,data,id=None):
    item=db.get(Device,id) if id else Device()
    if not item:raise HTTPException(404,'量测设备不存在')
    for k in ('code','name','note'):setattr(item,k,getattr(data,k))
    if id is None:item.status='unqualified'
    db.add(item);db.commit();db.refresh(item);return item
def require_device(db,id):
    device=db.get(Device,id)
    if not device:raise HTTPException(404,'量测设备不存在')
    return device
# ---------- 试验 ----------
def list_studies(db):return db.scalars(select(GaugeStudy).order_by(GaugeStudy.id.desc())).all()
def get_study(db,id):
    item=db.get(GaugeStudy,id)
    if not item:raise HTTPException(404,'量测资格试验不存在')
    return item
def readings_of(db,study_id):
    return db.scalars(select(GaugeReading).where(GaugeReading.study_id==study_id).order_by(GaugeReading.standard_index,GaugeReading.operator,GaugeReading.replicate)).all()
def create_study(db,data):
    if len(db.scalars(select(GaugeStudy).where(GaugeStudy.status.in_(['queued','running']))).all())>=10:
        raise HTTPException(429,'最多10个待执行量测试验，请稍后重试')
    device=require_device(db,data.device_id)
    thresholds=normalize_thresholds(data.thresholds)
    operators=[s.strip() for s in data.operators if s and s.strip()]
    if len(operators)<2 or len(operators)!=len(set(operators)):raise HTTPException(422,'至少2名不重复的操作员')
    if data.standard_count<2 or data.replicate_count<2:raise HTTPException(422,'标准件数与重复次数均至少为2')
    item=GaugeStudy(code=data.code,device_id=device.id,title=data.title,standard_count=data.standard_count,
                    operators=operators,replicate_count=data.replicate_count,thresholds=thresholds,
                    status='queued',created_at=_now())
    # 建试验即发起重测：设备进入暂停态（未获资格设备语义不变），并发切换资格均以这一行状态为准
    device.status='requalifying'
    db.add(item)
    try:db.commit()
    except Exception:db.rollback();raise
    db.refresh(item)
    try:queue.lpush('seal:gauge',item.id)
    except redis.RedisError:
        item.status='failed';item.error='队列不可用，请恢复后重新提交试验';db.commit()
        raise HTTPException(503,item.error)
    return item
def save_readings(db,study_id,data,user):
    study=get_study(db,study_id)
    if study.published:raise HTTPException(409,'试验已发布并冻结；如需调整请新建重测试验留痕')
    if study.status=='running':raise HTTPException(409,'试验正在分解计算，请完成后再录数')
    operators=study.operators
    # 坐标合法性在 schema 层已限界，这里复核操作员与标准件标签
    seen=set()
    for rd in data.readings:
        if rd.operator not in operators:raise HTTPException(422,f'操作员 {rd.operator} 不在试验名单内')
        key=(rd.standard_index,rd.operator,rd.replicate)
        if key in seen:raise HTTPException(422,'同一标准件/操作员/重复次数出现重复读数')
        seen.add(key)
    existing={ (rd.standard_index,rd.operator,rd.replicate):rd for rd in readings_of(db,study_id)}
    for rd in data.readings:
        key=(rd.standard_index,rd.operator,rd.replicate)
        row=existing.get(key) or GaugeReading(study_id=study.id)
        row.standard_index=rd.standard_index;row.standard_label=rd.standard_label
        row.operator=rd.operator;row.replicate=rd.replicate;row.value=rd.value
        db.add(row)
    # 录数后重新入队分解；已失败/已完成的试验同样可补数重算
    study.status='queued';study.error='';study.result=None
    db.commit();db.refresh(study)
    try:queue.lpush('seal:gauge',study.id)
    except redis.RedisError:
        study.status='failed';study.error='队列不可用，请恢复后重新提交';db.commit()
        raise HTTPException(503,study.error)
    return study
def compute_study(db,study):
    readings=[{'standard_index':rd.standard_index,'standard_label':rd.standard_label,'operator':rd.operator,
               'replicate':rd.replicate,'value':rd.value} for rd in readings_of(db,study.id)]
    expected=study.standard_count*len(study.operators)*study.replicate_count
    if len(readings)!=expected:raise ValueError(f'读数矩阵不完整：应为 {expected} 格，现有 {len(readings)} 格；缺测单元格也需以空值登记')
    meta={'standard_count':study.standard_count,'operators':study.operators,'replicate_count':study.replicate_count}
    study.result=grr_analysis(meta,readings,study.thresholds)
    return study.result
# ---------- 资格发布与样本放行（单事务，任一失败整体不生效） ----------
def publish(db,study_id,user):
    study=db.get(GaugeStudy,study_id)
    if not study:raise HTTPException(404,'量测资格试验不存在')
    if study.published:raise HTTPException(409,'该试验已发布；重试不重复放行样本')
    if study.status!='completed' or not study.result:raise HTTPException(409,'试验分解未成功完成，不能发布资格')
    device=db.query(Device).filter(Device.id==study.device_id).with_for_update().first()
    if not study.result['qualified']:
        # 资格不达标：设备维持暂停/未获资格，不产生任何放行；留存隔离样本
        device.status='unqualified'
        study.published=True;study.published_at=_now();study.published_by=user.email
        db.commit();db.refresh(study)
        return study,[]
    # 达标发布：设备转有效 + 隔离样本放行，同一事务提交；release_ledger 唯一约束保证重试不重复放行
    device.status='qualified'
    held=db.scalars(select(Sample).where(Sample.device_id==device.id,Sample.disposition=='quarantined').order_by(Sample.id)).all()
    released=[]
    for sample in held:
        exists=db.scalar(select(ReleaseLedger.id).where(ReleaseLedger.study_id==study.id,ReleaseLedger.sample_id==sample.id))
        if exists:continue  # 已被本试验放行过（重试路径），不重复放行
        sample.disposition='released';sample.hold_reason=''
        db.add(ReleaseLedger(study_id=study.id,sample_id=sample.id,device_id=device.id,
                             released_by=user.email,created_at=_now()))
        released.append(sample.id)
    study.published=True;study.published_at=_now();study.published_by=user.email
    db.commit();db.refresh(study)
    return study,released
def isolation_overview(db):
    rows=db.scalars(select(Sample).where(Sample.disposition!='normal').order_by(Sample.device_id,Sample.id)).all()
    devices={d.id:d for d in list_devices(db)}
    return [{'sample_id':s.id,'sample_code':s.code,'lot':s.lot,'device_id':s.device_id,
             'device_code':devices.get(s.device_id).code if devices.get(s.device_id) else '',
             'disposition':s.disposition,'hold_reason':s.hold_reason} for s in rows]
