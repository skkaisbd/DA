"""
Admin endpoints for the in-process scheduler.
- List registered jobs and their next run.
- View run history (audit log of cron executions).
- Manually trigger a job NOW (e.g. demo / on-demand scan).
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from database import get_db
from auth import require_auth
from utils.scheduler import get_scheduler, JOB_REGISTRY

router = APIRouter(prefix='/api/dewi/scheduler', tags=['Dewi-Scheduler'])


def _clean(d):
    if not d:
        return d
    d.pop('_id', None)
    return d


@router.get('/jobs')
async def list_jobs(user: dict = Depends(require_auth)):
    sch = get_scheduler()
    out = []
    for jid, cfg in JOB_REGISTRY.items():
        job = sch.get_job(jid) if sch else None
        out.append({
            'id': jid,
            'description': cfg['description'],
            'cron_label': cfg['cron_label'],
            'next_run_at': job.next_run_time.isoformat() if job and job.next_run_time else None,
            'enabled': bool(job),
        })
    return {
        'scheduler_running': bool(sch and sch.running),
        'timezone': str(sch.timezone) if sch else None,
        'jobs': out,
    }


@router.get('/runs')
async def list_runs(
    job_id: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q = {}
    if job_id:
        q['job_id'] = job_id
    items = await db.dewi_scheduler_runs.find(q).sort('started_at', -1).to_list(
        length=min(max(limit, 1), 500)
    )
    return [_clean(i) for i in items]


@router.post('/jobs/{job_id}/run-now')
async def run_now(job_id: str, user: dict = Depends(require_auth)):
    cfg = JOB_REGISTRY.get(job_id)
    if not cfg:
        raise HTTPException(404, 'Job tidak terdaftar')
    fn = cfg['fn']
    try:
        result = await fn()
        return {'job_id': job_id, 'status': 'success', 'result': result}
    except Exception as e:
        raise HTTPException(500, f'Job gagal: {e}')
