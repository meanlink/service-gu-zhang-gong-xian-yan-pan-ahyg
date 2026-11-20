from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Dataset, Job, GapInterval
from src.schemas.gap import GapInput
from src.middlewares.auth import current_user, can_write
from src.services import gaps
from src.services.audit import record
from src.utils.serialization import gap_dict
router=APIRouter()
@router.get('/datasets/{dataset_id}/gaps')
def listing(dataset_id:int,db=Depends(get_db),u=Depends(current_user)):
    if not db.get(Dataset,dataset_id): raise HTTPException(404,'数据批次不存在')
    return [gap_dict(g) for g in db.scalars(select(GapInterval).where(GapInterval.dataset_id==dataset_id).order_by(GapInterval.id.desc()))]
@router.post('/datasets/{dataset_id}/gaps',status_code=201)
def create(dataset_id:int,data:GapInput,db=Depends(get_db),u=Depends(can_write)):
    d=db.get(Dataset,dataset_id)
    if not d: raise HTTPException(404,'数据批次不存在')
    gap,created,marked=gaps.register(db,d,data,u)
    record(db,u.email,'gap.register',{'id':gap.id,'dataset':d.id,'service':gap.service,'created':created,'invalidated':marked})
    db.commit()
    return {**gap_dict(gap),'created':created,'invalidated_jobs':marked}
@router.get('/jobs/{id}/exclusions')
def exclusions(id:int,db=Depends(get_db),u=Depends(current_user)):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    return gaps.exclusion_detail(db,j)
