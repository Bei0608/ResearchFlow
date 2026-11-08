from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_current_user, provide_evaluation_run_repository, provide_identity_repository, provide_workspace_repository
from app.api.evaluation_run_schemas import EvaluationRunCreate, EvaluationRunDetailResponse, EvaluationRunListResponse, EvaluationRunResponse
from app.applications import SensitiveConfigError, prepare_config_snapshot
from app.evaluation.runs import EvaluationRunRepository
from app.security import IdentityRepository, UserRecord
from app.security.audit import record_audit_event
from app.workspaces import WorkspaceRepository


router=APIRouter(tags=["evaluation-runs"])


def _run(item):return asdict(item)
def _result(item):
    return {"case_result_id":item.case_result_id,"run_id":item.run_id,"case_id":item.case_id,"status":item.status,"output":item.output_json,"evidence":item.evidence_json,"trace":item.trace_json,"latency_ms":item.latency_ms,"token_usage":item.token_usage_json,"error":item.error,"created_at":item.created_at}
def _metric(item):
    value=asdict(item);value["details"]=value.pop("details_json");return value


@router.post("/workspaces/{workspace_id}/evaluation-runs",response_model=EvaluationRunResponse,status_code=201)
def create_run(workspace_id:str,payload:EvaluationRunCreate,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],workspaces:Annotated[WorkspaceRepository,Depends(provide_workspace_repository)],repository:Annotated[EvaluationRunRepository,Depends(provide_evaluation_run_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    workspace=workspaces.get_workspace_for_user(workspace_id,user.user_id)
    if workspace is None or workspace.role!="owner":raise HTTPException(404,"Workspace或已发布版本不存在")
    try:snapshot=prepare_config_snapshot(payload.config_snapshot)
    except SensitiveConfigError as exc:raise HTTPException(422,str(exc)) from None
    item=repository.create_run(workspace_id=workspace_id,agent_version_id=payload.agent_version_id,dataset_version_id=payload.dataset_version_id,trigger_type=payload.trigger_type,config_snapshot=snapshot,git_commit=payload.git_commit,user_id=user.user_id)
    if item is None:raise HTTPException(404,"Workspace或已发布版本不存在")
    record_audit_event(identity,request,user_id=user.user_id,event_type="evaluation_run.created",resource=item.run_id,metadata={"workspace_id":workspace_id,"agent_version_id":payload.agent_version_id,"dataset_version_id":payload.dataset_version_id})
    return _run(item)


@router.get("/workspaces/{workspace_id}/evaluation-runs",response_model=EvaluationRunListResponse)
def list_runs(workspace_id:str,user:Annotated[UserRecord,Depends(get_current_user)],workspaces:Annotated[WorkspaceRepository,Depends(provide_workspace_repository)],repository:Annotated[EvaluationRunRepository,Depends(provide_evaluation_run_repository)]):
    if workspaces.get_workspace_for_user(workspace_id,user.user_id) is None:raise HTTPException(404,"Workspace不存在")
    return {"runs":[_run(x) for x in repository.list_runs(workspace_id,user.user_id)]}


@router.get("/evaluation-runs/{run_id}",response_model=EvaluationRunDetailResponse)
def get_run(run_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationRunRepository,Depends(provide_evaluation_run_repository)]):
    item=repository.get_run(run_id,user.user_id)
    if item is None:raise HTTPException(404,"评测运行不存在")
    return {"run":_run(item),"results":[_result(x) for x in repository.list_case_results(run_id,user.user_id)],"metrics":[_metric(x) for x in repository.list_metrics(run_id,user.user_id)]}
