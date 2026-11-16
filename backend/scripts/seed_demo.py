import random,json
from datetime import datetime,timezone
from sqlalchemy import select,func
from src.config.database import Base,engine,SessionLocal
from src.models.entities import User,Process,Sample,Assessment,Device,GaugeStudy,GaugeReading
from src.utils.security import hash_password
from src.services.assessments import snapshot_for
from src.services.grr import grr_analysis,normalize_thresholds

def _readings_rows(db,study_id):
    return db.scalars(select(GaugeReading).where(GaugeReading.study_id==study_id).order_by(GaugeReading.id)).all()

def _readings_payload(db,study_id):
    return [{'standard_index':rd.standard_index,'standard_label':rd.standard_label,'operator':rd.operator,
             'replicate':rd.replicate,'value':rd.value} for rd in _readings_rows(db,study_id)]

def seed():
    Base.metadata.create_all(engine);rng=random.Random(3105);grng=random.Random(7702)
    with SessionLocal() as db:
        for role in ('admin','analyst','viewer'):
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,role=role,password_hash=hash_password('Demo123!')))
        db.commit()
        for j,(name,temp,dwell,pressure,mean) in enumerate([('稳温基线',160,.8,.32,22.5),('延时封合',160,1.2,.32,25.8),('升温短封',175,.65,.32,24.1)],1):
            code=f'HC-S{j}';process=db.scalar(select(Process).where(Process.code==code))
            if not process:
                process=Process(code=code,name=name,temperature=temp,dwell=dwell,pressure=pressure,note='BOPP/PE复合膜，批号HC-1115，同批独立取样');db.add(process);db.flush()
            for i in range(35):
                code=f'HC-S{j}-{i+1:03}';value=round(max(1,rng.gauss(mean,1.7)),2)
                if not db.scalar(select(Sample).where(Sample.code==code)):db.add(Sample(code=code,process_id=process.id,lot='HC-1115',force=value,flagged=i==0,note='首件标记，保留纳入分析' if i==0 else ''))
        db.commit()
        # ---- 量测设备与资格试验（Gauge R&R）----
        d1=db.scalar(select(Device).where(Device.code=='GR-01'))
        if not d1:
            d1=Device(code='GR-01',name='数显拉力机 A（在线）',status='unqualified',note='封口车间主力拉力设备，每日首件校准');db.add(d1);db.flush()
        d2=db.scalar(select(Device).where(Device.code=='GR-02'))
        if not d2:
            d2=Device(code='GR-02',name='备用拉力机 B（离线）',status='requalifying',note='夹具更换后重测，暂停期间样本隔离');db.add(d2);db.flush()
        # GR-01：5 标准件 × 3 操作员 × 3 重复，零件间差异大、量测噪声小 -> 达标发布
        s1=db.scalar(select(GaugeStudy).where(GaugeStudy.code=='GRR-GR01-01'))
        if not s1:
            thresholds=normalize_thresholds(None)
            s1=GaugeStudy(code='GRR-GR01-01',device_id=d1.id,title='GR-01 季度量测资格试验',standard_count=5,
                          operators=['王工','李工','周工'],replicate_count=3,thresholds=thresholds,
                          status='queued',created_at=datetime.now(timezone.utc).isoformat());db.add(s1);db.flush()
            part_means=[16.0,19.5,22.0,24.2,26.8];op_offset={'王工':0.0,'李工':0.05,'周工':-0.04}
            for i in range(5):
                for op in s1.operators:
                    for k in range(3):
                        value=round(part_means[i]+op_offset[op]+grng.gauss(0,0.08),3)
                        db.add(GaugeReading(study_id=s1.id,standard_index=i+1,standard_label=f'STD-{i+1}',operator=op,replicate=k+1,value=value))
            db.flush()
            meta={'standard_count':s1.standard_count,'operators':s1.operators,'replicate_count':s1.replicate_count}
            readings=_readings_payload(db,s1.id)
            s1.result=grr_analysis(meta,readings,thresholds)
            if s1.result['qualified']:
                s1.status='completed';s1.published=True;s1.published_by='admin@demo.local';s1.published_at=datetime.now(timezone.utc).isoformat();d1.status='qualified'
            else:s1.status='failed';s1.error='seed 数据未达标，请人工复核'
        # GR-02：3 标准件 × 2 操作员 × 2 重复，2 格缺测登记 null，噪声大 -> 不达标，设备保持重测暂停
        s2=db.scalar(select(GaugeStudy).where(GaugeStudy.code=='GRR-GR02-01'))
        if not s2:
            thresholds=normalize_thresholds(None)
            s2=GaugeStudy(code='GRR-GR02-01',device_id=d2.id,title='GR-02 夹具更换后重测',standard_count=3,
                          operators=['王工','陈工'],replicate_count=2,thresholds=thresholds,
                          status='queued',created_at=datetime.now(timezone.utc).isoformat());db.add(s2);db.flush()
            part_means=[20.0,23.0,26.0];missing_cells={(2,'陈工',1),(3,'王工',2)}
            for i in range(3):
                for op in s2.operators:
                    for k in range(2):
                        value=None if (i+1,op,k+1) in missing_cells else round(part_means[i]+grng.gauss(0,1.6),3)
                        db.add(GaugeReading(study_id=s2.id,standard_index=i+1,standard_label=f'STD-{i+1}',operator=op,replicate=k+1,value=value))
            db.flush()
            meta2={'standard_count':s2.standard_count,'operators':s2.operators,'replicate_count':s2.replicate_count}
            s2.result=grr_analysis(meta2,_readings_payload(db,s2.id),thresholds);s2.status='completed'
        # 样本关联设备：既有样本挂 GR-01（资格有效，放行态）；新增 2 条 GR-02 隔离样本
        for s in db.scalars(select(Sample)).all():
            if s.device_id is None:s.device_id=d1.id;s.disposition='released'
        for idx,proc_code in enumerate(['HC-S2','HC-S3'],1):
            code=f'HC-HOLD-{idx:02}'
            if not db.scalar(select(Sample).where(Sample.code==code)):
                proc=db.scalar(select(Process).where(Process.code==proc_code))
                db.add(Sample(code=code,process_id=proc.id,lot='HC-1116',force=round(24+grng.gauss(0,1.2),2),
                              flagged=False,note='重测期间照常收样，暂缓入评议',device_id=d2.id,
                              disposition='quarantined',hold_reason=f"设备 {d2.code} 资格状态为「requalifying」，重测达标发布后放行"))
        db.commit()
        title='HC-1115 三方案首轮复核'
        if not db.scalar(select(Assessment).where(Assessment.title==title)):
            ids=db.scalars(select(Process.id).where(Process.code.in_(['HC-S1','HC-S2','HC-S3'])).order_by(Process.id)).all()
            db.add(Assessment(title=title,lot='HC-1115',snapshot=snapshot_for(db,ids,'HC-1115'),status='queued',created_at=datetime.now(timezone.utc).isoformat()));db.commit()
        counts={t.__tablename__:db.scalar(select(func.count()).select_from(t)) for t in [User,Process,Device,Sample,GaugeStudy,GaugeReading,Assessment]};print(json.dumps(counts));return counts
if __name__=='__main__':seed()
