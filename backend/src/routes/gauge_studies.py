from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.security import current_user,editor,admin
from src.schemas.business import GaugeStudyInput,GaugeReadingsInput
from src.services import gauge
from src.controllers.business import serialize,serialize_many
router=APIRouter()
@router.get('/gauge-studies')
def listing(db=Depends(get_db),user=Depends(current_user)):return serialize_many(gauge.list_studies(db))
@router.post('/gauge-studies',status_code=202)
def create(data:GaugeStudyInput,db=Depends(get_db),user=Depends(editor)):return serialize(gauge.create_study(db,data))
@router.get('/gauge-studies/{id}')
def detail(id:int,db=Depends(get_db),user=Depends(current_user)):
    item=gauge.get_study(db,id)
    payload=serialize(item);payload['readings']=serialize_many(gauge.readings_of(db,id));return payload
@router.put('/gauge-studies/{id}/readings',status_code=202)
def readings(id:int,data:GaugeReadingsInput,db=Depends(get_db),user=Depends(editor)):return serialize(gauge.save_readings(db,id,data,user))
@router.post('/gauge-studies/{id}/publish')
def publish(id:int,db=Depends(get_db),user=Depends(admin)):
    study,released=gauge.publish(db,id,user)
    return {'study':serialize(study),'released_sample_ids':released}
@router.get('/isolation')
def isolation(db=Depends(get_db),user=Depends(current_user)):return gauge.isolation_overview(db)
