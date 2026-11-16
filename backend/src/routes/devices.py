from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.security import current_user,editor
from src.schemas.business import DeviceInput
from src.services import gauge
from src.controllers.business import serialize,serialize_many
router=APIRouter()
@router.get('/devices')
def listing(db=Depends(get_db),user=Depends(current_user)):return serialize_many(gauge.list_devices(db))
@router.post('/devices',status_code=201)
def create(data:DeviceInput,db=Depends(get_db),user=Depends(editor)):return serialize(gauge.save_device(db,data))
@router.put('/devices/{id}')
def update(id:int,data:DeviceInput,db=Depends(get_db),user=Depends(editor)):return serialize(gauge.save_device(db,data,id))
