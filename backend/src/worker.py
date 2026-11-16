import time,traceback,json
from pathlib import Path
from sqlalchemy import select
from src.config.database import SessionLocal
from src.models.entities import Assessment,GaugeStudy
from src.services.assessments import queue
from src.services.statistics import anova
from src.services.gauge import compute_study
def run_assessment(db,task):
    task.result=anova(task.snapshot);task.status='completed'
    Path('/app/artifacts/assessment-'+str(task.id)+'.json').write_text(json.dumps(task.result,ensure_ascii=False))
def run_gauge(db,task):
    compute_study(db,task);task.status='completed'
    Path('/app/artifacts/gauge-'+str(task.id)+'.json').write_text(json.dumps(task.result,ensure_ascii=False))
JOBS=[('seal:assessments',Assessment,run_assessment),('seal:gauge',GaugeStudy,run_gauge)]
def reset_interrupted():
    # worker 重启时把中断在 running 的任务恢复为待执行
    with SessionLocal() as db:
        db.query(Assessment).filter(Assessment.status=='running').update({'status':'queued'})
        db.query(GaugeStudy).filter(GaugeStudy.status=='running').update({'status':'queued'})
        db.commit()
def main():
    reset_interrupted()
    print('seal variance worker started',flush=True)
    while True:
        Path('/tmp/worker-heartbeat').touch()
        try:
            popped=queue.brpop([name for name,_,_ in JOBS],timeout=2)
            if not popped:continue
            key=popped[0].decode() if isinstance(popped[0],bytes) else popped[0]
            name,model,runner=next(job for job in JOBS if job[0]==key)
            with SessionLocal() as db:
                task=db.scalar(select(model).where(model.status=='queued').order_by(model.id).with_for_update(skip_locked=True))
                if not task:continue
                task.status='running';db.commit()
                try:runner(db,task)
                except Exception as e:task.error=str(e);task.status='failed'
                db.commit();print(f'{name}={task.id} status={task.status}',flush=True)
        except Exception:traceback.print_exc();time.sleep(2)
if __name__=='__main__':main()
