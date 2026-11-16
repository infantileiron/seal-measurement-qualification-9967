from sqlalchemy import String,Float,Boolean,Integer,ForeignKey,JSON,Text,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True)
    email:Mapped[str]=mapped_column(String(120),unique=True)
    role:Mapped[str]=mapped_column(String(20))
    password_hash:Mapped[str]=mapped_column(String(200))
class Process(Base):
    __tablename__='processes'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    name:Mapped[str]=mapped_column(String(100))
    temperature:Mapped[float]=mapped_column(Float)
    dwell:Mapped[float]=mapped_column(Float)
    pressure:Mapped[float]=mapped_column(Float)
    note:Mapped[str]=mapped_column(Text,default='')
class Device(Base):
    __tablename__='devices'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    name:Mapped[str]=mapped_column(String(100))
    status:Mapped[str]=mapped_column(String(20),default='unqualified')
    note:Mapped[str]=mapped_column(Text,default='')
class Sample(Base):
    __tablename__='samples'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    process_id:Mapped[int]=mapped_column(ForeignKey('processes.id'))
    lot:Mapped[str]=mapped_column(String(60))
    force:Mapped[float]=mapped_column(Float)
    flagged:Mapped[bool]=mapped_column(Boolean,default=False)
    note:Mapped[str]=mapped_column(Text,default='')
    # 量测设备关联与处置去向；历史样本 device_id 为空，按无设备正常样本处理
    device_id:Mapped[int|None]=mapped_column(ForeignKey('devices.id'),nullable=True)
    disposition:Mapped[str]=mapped_column(String(20),default='normal')
    hold_reason:Mapped[str]=mapped_column(Text,default='')
class GaugeStudy(Base):
    __tablename__='gauge_studies'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    device_id:Mapped[int]=mapped_column(ForeignKey('devices.id'))
    title:Mapped[str]=mapped_column(String(120),unique=True)
    standard_count:Mapped[int]=mapped_column(Integer)
    operators:Mapped[list]=mapped_column(JSON)
    replicate_count:Mapped[int]=mapped_column(Integer)
    thresholds:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(20),default='queued')
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')
    published:Mapped[bool]=mapped_column(Boolean,default=False)
    published_at:Mapped[str]=mapped_column(String(40),default='')
    published_by:Mapped[str]=mapped_column(String(120),default='')
    created_at:Mapped[str]=mapped_column(String(40))
class GaugeReading(Base):
    __tablename__='gauge_readings'
    __table_args__=(UniqueConstraint('study_id','standard_index','operator','replicate',name='uq_gauge_reading_cell'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    study_id:Mapped[int]=mapped_column(ForeignKey('gauge_studies.id'))
    standard_index:Mapped[int]=mapped_column(Integer)
    standard_label:Mapped[str]=mapped_column(String(60))
    operator:Mapped[str]=mapped_column(String(60))
    replicate:Mapped[int]=mapped_column(Integer)
    # 缺测写 null（非零、不删除），分解时按缺测口径处理并说明
    value:Mapped[float|None]=mapped_column(Float,nullable=True)
class ReleaseLedger(Base):
    __tablename__='release_ledger'
    __table_args__=(UniqueConstraint('study_id','sample_id',name='uq_release_study_sample'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    study_id:Mapped[int]=mapped_column(ForeignKey('gauge_studies.id'))
    sample_id:Mapped[int]=mapped_column(ForeignKey('samples.id'))
    device_id:Mapped[int]=mapped_column(ForeignKey('devices.id'))
    released_by:Mapped[str]=mapped_column(String(120))
    created_at:Mapped[str]=mapped_column(String(40))
class Assessment(Base):
    __tablename__='assessments'
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(String(120),unique=True)
    lot:Mapped[str]=mapped_column(String(60),default='全部')
    status:Mapped[str]=mapped_column(String(20),default='queued')
    snapshot:Mapped[dict]=mapped_column(JSON)
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')
    recommendation:Mapped[str]=mapped_column(Text,default='')
    selected_process_id:Mapped[int|None]=mapped_column(ForeignKey('processes.id'),nullable=True)
    approved:Mapped[bool]=mapped_column(Boolean,default=False)
    approved_by:Mapped[str]=mapped_column(String(120),default='')
    created_at:Mapped[str]=mapped_column(String(40))
class Audit(Base):
    __tablename__='audit_logs'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor:Mapped[str]=mapped_column(String(120))
    action:Mapped[str]=mapped_column(String(200))
    status:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[str]=mapped_column(String(40))
