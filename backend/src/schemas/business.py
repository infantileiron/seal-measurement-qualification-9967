from typing import Optional
from pydantic import BaseModel,Field
class LoginInput(BaseModel):
    email:str=Field(max_length=120)
    password:str=Field(max_length=200)
class ProcessInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    name:str=Field(min_length=2,max_length=100)
    temperature:float=Field(ge=80,le=250,allow_inf_nan=False)
    dwell:float=Field(gt=0,le=10,allow_inf_nan=False)
    pressure:float=Field(gt=0,le=2,allow_inf_nan=False)
    note:str=Field(default='',max_length=2000)
class DeviceInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    name:str=Field(min_length=2,max_length=100)
    note:str=Field(default='',max_length=2000)
class SampleInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    process_id:int=Field(gt=0)
    lot:str=Field(min_length=1,max_length=60)
    force:float=Field(gt=0,le=200,allow_inf_nan=False)
    flagged:bool=False
    note:str=Field(default='',max_length=1000)
    device_id:Optional[int]=Field(default=None,gt=0)
class AssessmentInput(BaseModel):
    title:str=Field(min_length=2,max_length=120)
    process_ids:list[int]=Field(min_length=2,max_length=8)
    lot:str=Field(default='全部',min_length=1,max_length=60)
class RecommendationInput(BaseModel):
    selected_process_id:int=Field(gt=0)
    recommendation:str=Field(min_length=20,max_length=3000)
class GaugeThresholds(BaseModel):
    grr_percent_max:Optional[float]=Field(default=None,gt=0,le=100)
    ndc_min:Optional[float]=Field(default=None,ge=1,le=50)
    max_missing_ratio:Optional[float]=Field(default=None,ge=0,lt=1)
class GaugeStudyInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    title:str=Field(min_length=2,max_length=120)
    device_id:int=Field(gt=0)
    standard_count:int=Field(ge=2,le=20)
    operators:list[str]=Field(min_length=2,max_length=10)
    replicate_count:int=Field(ge=2,le=10)
    thresholds:Optional[GaugeThresholds]=None
class GaugeReadingInput(BaseModel):
    standard_index:int=Field(ge=1,le=20)
    standard_label:str=Field(min_length=1,max_length=60)
    operator:str=Field(min_length=1,max_length=60)
    replicate:int=Field(ge=1,le=10)
    value:Optional[float]=Field(default=None,gt=0,le=200,allow_inf_nan=False)
class GaugeReadingsInput(BaseModel):
    readings:list[GaugeReadingInput]=Field(min_length=1,max_length=2000)
