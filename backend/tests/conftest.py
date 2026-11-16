import os,sys,types,pathlib
# 测试隔离：在导入应用前注入假 redis，并把数据库指向临时 SQLite
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
DB_PATH=pathlib.Path('/tmp/seal_test.db')
if DB_PATH.exists():DB_PATH.unlink()
os.environ['DATABASE_URL']='sqlite:///'+str(DB_PATH)
os.environ['JWT_SECRET']='test-secret'
os.environ['SEED_DEMO']='false'
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
fake=types.ModuleType('redis')
class FakeRedis:
    def __init__(self,*a,**k):self.items=[]
    @classmethod
    def from_url(cls,*a,**k):return cls()
    def lpush(self,k,v):self.items.append((k,v));return 1
    def brpop(self,keys,timeout=2):return None
    def ping(self):return True
fake.Redis=FakeRedis
fake.RedisError=Exception
sys.modules['redis']=fake
import pytest
from fastapi.testclient import TestClient
from src.config.database import Base,engine,SessionLocal
from src.main import app
from src.models.entities import User,Process,Device,Sample,GaugeStudy,GaugeReading,ReleaseLedger,Assessment
from src.utils.security import hash_password
from src.services.grr import grr_analysis,normalize_thresholds

@pytest.fixture(scope='session')
def client():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for role in ('admin','analyst','viewer'):
            db.add(User(email=role+'@demo.local',role=role,password_hash=hash_password('Demo123!')))
        db.add(Process(code='P-A',name='工艺甲',temperature=160,dwell=0.8,pressure=0.32,note=''))
        db.add(Process(code='P-B',name='工艺乙',temperature=170,dwell=1.0,pressure=0.32,note=''))
        db.commit()
    return TestClient(app)

def token(client,role):
    r=client.post('/auth/login',json={'email':role+'@demo.local','password':'Demo123!'})
    assert r.status_code==200
    return r.headers.get('authorization') or ('Bearer '+r.json()['access_token'])

@pytest.fixture
def auth(client):
    return {role:{'Authorization':token(client,role)} for role in ('admin','analyst','viewer')}

def make_study_payload(device_id,code='GRR-T1',title='量测试验一',standards=3,operators=('王工','李工'),replicates=3,thresholds=None):
    return {'code':code,'title':title,'device_id':device_id,'standard_count':standards,
            'operators':list(operators),'replicate_count':replicates,'thresholds':thresholds}

def full_readings(standards,operators,replicates,noise=0.05,part_gap=4.0,op_bias=None,missing=(),seed=1):
    import random
    rng=random.Random(seed);out=[];op_bias=op_bias or {}
    for i in range(1,standards+1):
        for op in operators:
            for k in range(1,replicates+1):
                value=None if (i,op,k) in missing else round(15+part_gap*i+op_bias.get(op,0.0)+rng.gauss(0,noise),3)
                out.append({'standard_index':i,'standard_label':f'STD-{i}','operator':op,'replicate':k,'value':value})
    return out
