from sqlalchemy import String, Double, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class GapInterval(Base):
    """按服务登记的缺测区间；applied_at 为空表示失效标记尚未完成，待恢复。"""
    __tablename__ = 'gap_intervals'
    __table_args__ = (UniqueConstraint('dataset_id', 'service', 'start_min', 'end_min', name='uq_gap_interval'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    service: Mapped[str] = mapped_column(String(160))
    start_min: Mapped[float] = mapped_column(Double)
    end_min: Mapped[float] = mapped_column(Double)
    reason: Mapped[str] = mapped_column(String(500), default='')
    registered_by: Mapped[str] = mapped_column(String(150))
    registered_at: Mapped[float] = mapped_column(Double)
    applied_at: Mapped[float | None] = mapped_column(Double, nullable=True)
class JobInvalidation(Base):
    """断档补登导致的试验失效留档；(job_id, gap_id) 唯一，重试不重复留档。"""
    __tablename__ = 'job_invalidations'
    __table_args__ = (UniqueConstraint('job_id', 'gap_id', name='uq_job_gap'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    gap_id: Mapped[int] = mapped_column(ForeignKey('gap_intervals.id'))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Double)
