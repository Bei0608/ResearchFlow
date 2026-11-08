from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.dependencies import get_current_user, provide_identity_repository, provide_reporting_repository
from app.api.report_schemas import ReportListResponse, ReportResponse, RunSummaryResponse
from app.evaluation.reporting import ReportService, ReportingRepository
from app.security import IdentityRepository, UserRecord
from app.security.audit import record_audit_event


router = APIRouter(tags=["statistics-and-reports"])


def _report(item):
    value = asdict(item)
    value["content_url"] = (
        f"/api/v1/reports/{item.report_id}/content"
        if item.status == "completed" else None
    )
    return value


@router.get("/evaluation-runs/{run_id}/summary", response_model=RunSummaryResponse)
def run_summary(
    run_id: str,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ReportingRepository, Depends(provide_reporting_repository)],
):
    summary = ReportService(repository).summary(run_id, user.user_id)
    if summary is None:
        raise HTTPException(404, "评测运行不存在或无统计权限")
    return summary


@router.post("/evaluation-runs/{run_id}/reports", response_model=ReportListResponse, status_code=201)
def generate_reports(
    run_id: str,
    request: Request,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ReportingRepository, Depends(provide_reporting_repository)],
    identity: Annotated[IdentityRepository, Depends(provide_identity_repository)],
):
    items = ReportService(repository).generate(run_id, user.user_id)
    if items is None:
        raise HTTPException(404, "评测运行不存在或无报告权限")
    record_audit_event(
        identity, request, user_id=user.user_id,
        event_type="evaluation_report.generated", resource=run_id,
        metadata={"report_ids": [x.report_id for x in items], "formats": [x.format for x in items]},
    )
    return {"reports": [_report(x) for x in items]}


@router.get("/evaluation-runs/{run_id}/reports", response_model=ReportListResponse)
def list_reports(
    run_id: str,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ReportingRepository, Depends(provide_reporting_repository)],
):
    if repository.load_snapshot(run_id, user.user_id) is None:
        raise HTTPException(404, "评测运行不存在或无报告权限")
    return {"reports": [_report(x) for x in repository.list_reports(run_id, user.user_id)]}


@router.get("/reports/{report_id}", response_model=ReportResponse)
def report_detail(
    report_id: str,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ReportingRepository, Depends(provide_reporting_repository)],
):
    item = repository.get_report(report_id, user.user_id)
    if item is None:
        raise HTTPException(404, "报告不存在")
    return _report(item)


@router.get("/reports/{report_id}/content", response_class=FileResponse)
def report_content(
    report_id: str,
    user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ReportingRepository, Depends(provide_reporting_repository)],
):
    item = repository.get_report(report_id, user.user_id)
    if item is None:
        raise HTTPException(404, "报告不存在")
    path = ReportService(repository).resolve_content(item)
    if path is None:
        raise HTTPException(409, "报告内容尚不可用")
    media_type = "application/json" if item.format == "json" else "text/html"
    return FileResponse(path, media_type=media_type, filename=path.name)
