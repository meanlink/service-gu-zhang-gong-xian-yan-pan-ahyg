"""缺测区间登记与试验失效标记。

- 登记幂等：同一批次+服务+区间只留一档，重试返回原记录。
- 失效标记两阶段：先持久化缺测区间（applied_at 为空），再标记受影响试验；
  中断后由 recover_pending 恢复未完的标记，标记本身幂等。
- 受影响判定：批次内任一事件的跟随窗 [t, t+window] 与缺测区间相交，
  且缺测服务属于该批次服务集合（任一方缺测即剔除该方向取样）。
"""
import time
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.models import Dataset, Job, Report, GapInterval, JobInvalidation
from src.services import business
from src.services.audit import record


def _validate(dataset, data):
    service = data.service.strip()
    if not service:
        raise HTTPException(422, '缺测服务不能为空')
    start, end = float(data.start_min), float(data.end_min)
    if end < start:
        raise HTTPException(422, '缺测区间终点不能早于起点')
    services = {str(row.get('service', '')).strip() for row in dataset.records}
    if service not in services:
        raise HTTPException(422, f'服务 {service} 不在该数据批次中，请核对服务名')
    return service, start, end


def register(db, dataset, data, user):
    """登记缺测区间；已存在相同区间时不重复留档，返回原记录。返回 (gap, created, 新失效试验ID列表)。"""
    service, start, end = _validate(dataset, data)
    existing = db.scalar(select(GapInterval).where(GapInterval.dataset_id == dataset.id, GapInterval.service == service, GapInterval.start_min == start, GapInterval.end_min == end))
    if existing:
        gap, created = existing, False
    else:
        gap = GapInterval(dataset_id=dataset.id, service=service, start_min=start, end_min=end, reason=(data.reason or '').strip(), registered_by=user.email, registered_at=time.time(), applied_at=None)
        db.add(gap)
        try:
            with db.begin_nested():
                db.flush()
            created = True
        except IntegrityError:
            gap = db.scalar(select(GapInterval).where(GapInterval.dataset_id == dataset.id, GapInterval.service == service, GapInterval.start_min == start, GapInterval.end_min == end))
            created = False
    db.commit()  # 第一阶段：登记先落库，分发侧以此判定先后
    marked = apply_marks(db, gap, actor=user.email)  # 第二阶段：标记受影响试验
    db.commit()
    return gap, created, marked


def is_affected(records, window_min, gap):
    """该试验口径下，缺测区间是否会剔除任一源事件。"""
    services = {str(row.get('service', '')).strip() for row in records}
    if gap.service not in services or len(services) < 2:
        return False
    for row in records:
        try:
            minute = float(row.get('occurred_min'))
        except (TypeError, ValueError):
            continue
        if minute <= gap.end_min and gap.start_min <= minute + window_min:
            return True
    return False


def apply_marks(db, gap, actor):
    """把缺测区间影响的试验标记为失效；幂等，可重复调用。返回本次新失效的试验ID。"""
    marked = []
    candidates = db.scalars(select(Job).where(Job.dataset_id == gap.dataset_id, Job.created_at <= gap.registered_at, Job.status != 'failed').with_for_update()).all()
    dataset = db.get(Dataset, gap.dataset_id)
    for job in candidates:
        try:
            window_min = float((job.params or {}).get('window_min', 5))
        except (TypeError, ValueError):
            continue
        if not is_affected(dataset.records, window_min, gap):
            continue
        known = db.scalar(select(JobInvalidation).where(JobInvalidation.job_id == job.id, JobInvalidation.gap_id == gap.id))
        if not known:
            try:
                with db.begin_nested():
                    db.add(JobInvalidation(job_id=job.id, gap_id=gap.id, detail={'service': gap.service, 'start_min': gap.start_min, 'end_min': gap.end_min, 'window_min': window_min}, created_at=time.time()))
                    db.flush()
            except IntegrityError:
                pass  # 并发补登已留档，不重复
        first = not job.invalidated
        job.invalidated = True
        job.approved = False  # 失效即撤回批准，且不允许再次批准
        for report in db.scalars(select(Report).where(Report.job_id == job.id, Report.enabled == True)):
            report.enabled = False
            record(db, actor, 'report.disabled', {'id': report.id, 'job': job.id, 'gap': gap.id})
        if first:
            marked.append(job.id)
            record(db, actor, 'job.invalidated', {'id': job.id, 'gap': gap.id})
    if gap.applied_at is None:
        gap.applied_at = time.time()
    return marked


def recover_pending(db, actor='worker'):
    """中断恢复：补做登记后未完成的失效标记。返回恢复的缺测区间数。"""
    recovered = 0
    for gap in db.scalars(select(GapInterval).where(GapInterval.applied_at == None)).all():
        apply_marks(db, gap, actor=actor)
        recovered += 1
        record(db, actor, 'gap.marks.recovered', {'id': gap.id})
    return recovered


def exclusion_detail(db, job):
    """剔除依据：该试验当前已登记缺测、失效留档与逐方向剔除明细。"""
    dataset = db.get(Dataset, job.dataset_id)
    if not dataset:
        raise HTTPException(404, '数据批次不存在')
    gaps = db.scalars(select(GapInterval).where(GapInterval.dataset_id == dataset.id).order_by(GapInterval.id)).all()
    invalidations = db.scalars(select(JobInvalidation).where(JobInvalidation.job_id == job.id).order_by(JobInvalidation.id)).all()
    gap_payload = [{'id': g.id, 'service': g.service, 'start_min': g.start_min, 'end_min': g.end_min, 'registered_at': g.registered_at} for g in gaps]
    try:
        detail = business.exclusions(dataset.records, job.params or {}, gap_payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        'job_id': job.id,
        'invalidated': job.invalidated,
        'invalidations': [{'id': v.id, 'gap_id': v.gap_id, 'detail': v.detail, 'created_at': v.created_at} for v in invalidations],
        **detail,
    }
