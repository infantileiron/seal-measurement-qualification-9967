from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import Sample,Process,Device
def listing(db):return db.scalars(select(Sample).order_by(Sample.id)).all()
def _disposition_for(db,data):
    # 关联设备的样本按当前资格状态定去向：未获资格/重测暂停 -> 隔离留存；资格有效 -> 放行。
    # 重测期间照常收样但暂缓入评议；无设备历史样本保持 normal。
    if not data.device_id:return 'normal',''
    device=db.get(Device,data.device_id)
    if not device:raise HTTPException(404,'量测设备不存在')
    if device.status=='qualified':return 'released',''
    return 'quarantined',f"设备 {device.code} 资格状态为「{device.status}」，重测达标发布后放行"
def save(db,data,id=None):
    if not db.get(Process,data.process_id):raise HTTPException(404,'工艺方案不存在')
    disposition,reason=_disposition_for(db,data)
    item=db.get(Sample,id) if id else Sample()
    if not item:raise HTTPException(404,'拉力样本不存在')
    payload=data.model_dump()
    payload['disposition']=disposition;payload['hold_reason']=reason
    for k,v in payload.items():setattr(item,k,v)
    db.add(item);db.commit();db.refresh(item);return item
