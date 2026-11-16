from .conftest import make_study_payload,full_readings
from src.config.database import SessionLocal
from src.models.entities import Device,Sample,GaugeStudy,GaugeReading,ReleaseLedger,Process,Assessment
from src.services.gauge import compute_study

def _device(client,h,code='GR-X',name='试验拉力机'):
    r=client.post('/devices',json={'code':code,'name':name,'note':'测试设备'},headers=h['analyst'])
    assert r.status_code==201,r.text
    return r.json()

def _study_id(db,code):
    return db.query(GaugeStudy).filter(GaugeStudy.code==code).first().id

def _seed_study(db,device_id,code,qualified=True,missing=(),noise=0.05):
    # 达标：零件间跨度 12 N、噪声 0.05 N；不达标：噪声放大到 3 N
    thresholds={'grr_percent_max':10.0,'ndc_min':5,'max_missing_ratio':0.1}
    study=GaugeStudy(code=code,device_id=device_id,title=code+' 标题',standard_count=3,
                     operators=['王工','李工'],replicate_count=3,thresholds=thresholds,
                     status='queued',created_at='2026-11-16T00:00:00+00:00')
    db.add(study);db.flush()
    for rd in full_readings(3,['王工','李工'],3,noise=noise,part_gap=6.0,missing=missing):
        db.add(GaugeReading(study_id=study.id,**rd))
    db.flush();compute_study(db,study);study.status='completed';db.commit()
    assert study.result['qualified'] is qualified,(code,study.result['verdict_reasons'])
    return study

def test_device_permissions_and_study_lifecycle(client,auth):
    h=auth
    assert client.post('/devices',json={'code':'GR-V','name':'只读不能建'},headers=h['viewer']).status_code==403
    dev=_device(client,h)
    assert dev['status']=='unqualified'
    # 建试验后设备进入重测暂停；放宽缺测阈值使 1 格缺测仍可达标发布
    payload=make_study_payload(dev['id'],'GRR-L1','生命周期试验',
                               thresholds={'grr_percent_max':10.0,'ndc_min':5,'max_missing_ratio':0.2})
    r=client.post('/gauge-studies',json=payload,headers=h['analyst'])
    assert r.status_code==202
    with SessionLocal() as db:
        sid=_study_id(db,'GRR-L1');study=db.get(GaugeStudy,sid)
        assert study.status=='queued'
        assert db.get(Device,dev['id']).status=='requalifying'
        # 读数矩阵含 1 个缺测（null 显式登记）
        rows=full_readings(3,['王工','李工'],3,missing={(2,'李工',2)})
    r=client.put(f'/gauge-studies/{sid}/readings',json={'readings':rows},headers=h['analyst'])
    assert r.status_code==202
    with SessionLocal() as db:
        study=db.get(GaugeStudy,sid);compute_study(db,study);study.status='completed';db.commit()
        result=study.result
        assert result['n_missing']==1 and result['balanced'] is False
    # viewer 不能录数、analyst 不能发布
    assert client.put(f'/gauge-studies/{sid}/readings',json={'readings':rows[:1]},headers=h['viewer']).status_code==403
    assert client.post(f'/gauge-studies/{sid}/publish',headers=h['analyst']).status_code==403
    r=client.post(f'/gauge-studies/{sid}/publish',headers=h['admin'])
    assert r.status_code==200
    with SessionLocal() as db:
        assert db.get(GaugeStudy,sid).published is True
        assert db.get(Device,dev['id']).status==('qualified' if result['qualified'] else 'unqualified')

def test_quarantine_release_and_no_duplicate_release(client,auth):
    h=auth;dev=_device(client,h,code='GR-Q',name='隔离设备')
    with SessionLocal() as db:
        # 先有一台已发布达标的设备，使隔离样本具备“前序资格后失效”的留痕语义
        prior=_seed_study(db,dev['id'],'GRR-Q-PRIOR',qualified=True)
        assert prior.result['qualified']
        proc=db.query(Process).filter(Process.code=='P-A').first();pid=proc.id;did=dev['id']
        # 设备重测暂停期间收样 -> 隔离留存
        db.get(Device,did).status='requalifying'
        db.add(Sample(code='Q-1',process_id=pid,lot='L1',force=22.0,device_id=did,disposition='quarantined',hold_reason='x'))
        db.add(Sample(code='Q-2',process_id=pid,lot='L1',force=23.0,device_id=did,disposition='quarantined',hold_reason='x'))
        db.commit()
        good=_seed_study(db,did,'GRR-Q-OK',qualified=True)
        sid=good.id
    # 隔离去向可查
    r=client.get('/isolation',headers=h['viewer'])
    assert r.status_code==200 and {x['sample_code'] for x in r.json()}>={'Q-1','Q-2'}
    r=client.post(f'/gauge-studies/{sid}/publish',headers=h['admin'])
    assert r.status_code==200 and set(r.json()['released_sample_ids'])
    with SessionLocal() as db:
        assert all(s.disposition=='released' for s in db.query(Sample).filter(Sample.code.in_(['Q-1','Q-2'])).all())
        assert db.query(ReleaseLedger).join(Sample,ReleaseLedger.sample_id==Sample.id).filter(Sample.code.in_(['Q-1','Q-2'])).count()==2
    # 重试发布：幂等，不重复放行、不重复记账
    r=client.post(f'/gauge-studies/{sid}/publish',headers=h['admin'])
    assert r.status_code==409
    with SessionLocal() as db:
        assert db.query(ReleaseLedger).join(Sample,ReleaseLedger.sample_id==Sample.id).filter(Sample.code.in_(['Q-1','Q-2'])).count()==2
    # 达标后新收样直接放行
    r=client.post('/samples',json={'code':'Q-3','process_id':pid,'lot':'L1','force':24.0,'device_id':did},headers=h['analyst'])
    assert r.status_code==201 and r.json()['disposition']=='released'

def test_publish_failure_keeps_hold_and_recovery_publishes(client,auth):
    h=auth;dev=_device(client,h,code='GR-F',name='发布失败设备')
    with SessionLocal() as db:
        proc=db.query(Process).first();pid=proc.id;did=dev['id']
        db.add(Sample(code='F-1',process_id=pid,lot='L2',force=22.0,device_id=did,disposition='quarantined',hold_reason='x'))
        db.commit()
        bad=_seed_study(db,did,'GRR-F-BAD',qualified=False,noise=3.0)
        sid=bad.id
        assert bad.result['qualified'] is False
    r=client.post(f'/gauge-studies/{sid}/publish',headers=h['admin'])
    assert r.status_code==200 and r.json()['released_sample_ids']==[]
    with SessionLocal() as db:
        # 发布失败：样本留存隔离，设备未获资格
        s=db.query(Sample).filter(Sample.code=='F-1').one()
        assert s.disposition=='quarantined' and db.get(Device,did).status=='unqualified'
        assert db.query(ReleaseLedger).filter(ReleaseLedger.sample_id==s.id).count()==0
        # 恢复：新建重测试验达标后发布，隔离样本放行
        good=_seed_study(db,did,'GRR-F-GOOD',qualified=True)
        gid=good.id
    r=client.post(f'/gauge-studies/{gid}/publish',headers=h['admin'])
    assert r.status_code==200 and r.json()['released_sample_ids']
    with SessionLocal() as db:
        assert db.query(Sample).filter(Sample.code=='F-1').one().disposition=='released'
        assert db.get(Device,did).status=='qualified'

def test_requalifying_samples_held_from_assessment_snapshot(client,auth):
    h=auth;dev=_device(client,h,code='GR-H',name='暂停取样设备')
    with SessionLocal() as db:
        pa=db.query(Process).filter(Process.code=='P-A').first()
        pb=db.query(Process).filter(Process.code=='P-B').first()
        did=dev['id']
        db.add_all([
            Sample(code='H-IN',process_id=pa.id,lot='LX',force=22.0,device_id=did,disposition='quarantined',hold_reason='暂停'),
            Sample(code='H-OK',process_id=pa.id,lot='LX',force=22.5),  # 无设备历史样本
            Sample(code='H-IN2',process_id=pb.id,lot='LX',force=23.0,device_id=did,disposition='quarantined',hold_reason='暂停'),
        ]);db.commit()
    with SessionLocal() as db:
        pa=db.query(Process).filter(Process.code=='P-A').first()
        pb=db.query(Process).filter(Process.code=='P-B').first()
        ids=[pa.id,pb.id]
    r=client.post('/assessments',json={'title':'并发资格取样评议','process_ids':ids,'lot':'LX'},headers=h['analyst'])
    assert r.status_code==202
    with SessionLocal() as db:
        a=db.query(Assessment).filter(Assessment.title=='并发资格取样评议').one()
        codes=[s['code'] for g in a.snapshot['groups'] for s in g['samples']]
        held=[s['code'] for g in a.snapshot['groups'] for s in g['held_out']]
        assert 'H-OK' in codes and 'H-IN' not in codes and 'H-IN2' not in codes
        assert set(held)=={'H-IN','H-IN2'}
        dev_states={d['code']:d['status'] for d in a.snapshot['device_qualification']['devices']}
        assert dev_states['GR-H']=='unqualified'  # 取样时该设备未获资格，快照留痕同一资格状态
        assert 'rule' in a.snapshot['device_qualification']
    # 重测期间照常收样：可录入但自动隔离
    r=client.post('/samples',json={'code':'H-NEW','process_id':ids[0],'lot':'LX','force':21.0,'device_id':dev['id']},headers=h['analyst'])
    assert r.status_code==201 and r.json()['disposition']=='quarantined'

def test_existing_assessments_keep_basis_after_qualification_change(client,auth):
    h=auth;dev=_device(client,h,code='GR-K',name='依据保留设备')
    with SessionLocal() as db:
        pa=db.query(Process).filter(Process.code=='P-A').first();pb=db.query(Process).filter(Process.code=='P-B').first()
        did=dev['id']
        db.add(Sample(code='K-1',process_id=pa.id,lot='LK',force=22.0))
        db.add(Sample(code='K-2',process_id=pb.id,lot='LK',force=23.0));db.commit()
    r=client.post('/assessments',json={'title':'依据保留评议','process_ids':[pa.id,pb.id],'lot':'LK'},headers=h['analyst'])
    aid=r.json()['id']
    with SessionLocal() as db:
        a=db.get(Assessment,aid)
        before=dict(a.snapshot)
        # 之后设备资格切换、样本被隔离/放行，不影响已冻结快照
        s=db.query(Sample).filter(Sample.code=='K-1').one()
        s.device_id=did;s.disposition='quarantined';s.hold_reason='后补挂设备'
        db.commit()
        db.expire_all()
        a2=db.get(Assessment,aid)
        assert a2.snapshot==before
        assert [x['code'] for x in a2.snapshot['groups'][0]['samples']]==['K-1']

def test_reading_matrix_validation(client,auth):
    h=auth;dev=_device(client,h,code='GR-V2',name='校验设备')
    r=client.post('/gauge-studies',json=make_study_payload(dev['id'],'GRR-V1','矩阵校验'),headers=h['analyst'])
    sid=r.json()['id']
    bad=[{'standard_index':1,'standard_label':'STD-1','operator':'外人','replicate':1,'value':12.0}]
    assert client.put(f'/gauge-studies/{sid}/readings',json={'readings':bad},headers=h['analyst']).status_code==422
    dup=full_readings(3,['王工','李工'],3)[:2]
    dup[1]=dict(dup[0])  # 同坐标重复
    assert client.put(f'/gauge-studies/{sid}/readings',json={'readings':dup},headers=h['analyst']).status_code==422
    # 读数不完整时分解失败并给出明确口径
    with SessionLocal() as db:
        study=db.get(GaugeStudy,sid)
        import pytest
        import src.services.gauge as g
        with pytest.raises(ValueError,match='读数矩阵不完整'):
            g.compute_study(db,study)

def test_sample_enters_assessment_only_after_release(client,auth):
    # 资格时间线：隔离期样本不进评议 -> 达标发布放行 -> 新评议才纳入；旧评议依据不变
    h=auth;dev=_device(client,h,code='GR-T',name='时间线设备')
    with SessionLocal() as db:
        pa=db.query(Process).filter(Process.code=='P-A').first();pb=db.query(Process).filter(Process.code=='P-B').first()
        did=dev['id']
        db.add(Sample(code='T-1',process_id=pa.id,lot='LT',force=22.0,device_id=did,disposition='quarantined',hold_reason='暂停'))
        db.add(Sample(code='T-2',process_id=pb.id,lot='LT',force=23.0))
        db.commit();ids=[pa.id,pb.id]
    r=client.post('/assessments',json={'title':'时间线-隔离期','process_ids':ids,'lot':'LT'},headers=h['analyst'])
    aid1=r.json()['id']
    with SessionLocal() as db:
        good=_seed_study(db,dev['id'],'GRR-T-OK',qualified=True);sid=good.id
    r=client.post(f'/gauge-studies/{sid}/publish',headers=h['admin'])
    assert r.status_code==200 and r.json()['released_sample_ids']
    r=client.post('/assessments',json={'title':'时间线-放行后','process_ids':ids,'lot':'LT'},headers=h['analyst'])
    aid2=r.json()['id']
    with SessionLocal() as db:
        a1=db.get(Assessment,aid1);a2=db.get(Assessment,aid2)
        c1=[s['code'] for g in a1.snapshot['groups'] for s in g['samples']]
        c2=[s['code'] for g in a2.snapshot['groups'] for s in g['samples']]
        assert 'T-1' not in c1 and 'T-1' in c2  # 放行后才可进入新评议
        assert 'T-2' in c1 and 'T-2' in c2
        held1=[s['code'] for g in a1.snapshot['groups'] for s in g['held_out']]
        assert held1==['T-1']
        assert len(a1.snapshot['groups'])==len(a2.snapshot['groups'])  # 旧评议依据保留不变

def test_worker_resume_interrupted_study(client,auth):
    dev=_device(client,auth,code='GR-W',name='恢复设备')
    r=client.post('/gauge-studies',json=make_study_payload(dev['id'],'GRR-W1','中断试验'),headers=auth['analyst'])
    sid=r.json()['id']
    with SessionLocal() as db:
        study=db.get(GaugeStudy,sid);study.status='running';db.commit()
    from src.worker import JOBS,reset_interrupted
    assert [name for name,_,_ in JOBS]==['seal:assessments','seal:gauge']
    with SessionLocal() as db:
        study=db.get(GaugeStudy,sid);study.status='running';db.commit()
    reset_interrupted()
    with SessionLocal() as db:
        assert db.get(GaugeStudy,sid).status=='queued'
