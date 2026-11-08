from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import (
    get_current_user, provide_gate_repository, provide_identity_repository,
    provide_reporting_repository,
    provide_workspace_repository,
)
from app.api.gate_schemas import (
    BaselineResponse, BaselineSetRequest, GateEvaluationListResponse,
    GateEvaluationRequest, GateEvaluationResponse, GatePolicyCreate,
    GatePolicyListResponse, GatePolicyResponse,
)
from app.evaluation.gates import GateRepository, GateService, GateValidationError
from app.evaluation.reporting import ReportingRepository
from app.security import IdentityRepository, UserRecord
from app.security.audit import record_audit_event
from app.workspaces import WorkspaceRepository


router = APIRouter(tags=["quality-gates"])


@router.put("/applications/{application_id}/baseline", response_model=BaselineResponse)
def set_baseline(application_id: str, payload: BaselineSetRequest, request: Request,
                 user: Annotated[UserRecord, Depends(get_current_user)],
                 repository: Annotated[GateRepository, Depends(provide_gate_repository)],
                 identity: Annotated[IdentityRepository, Depends(provide_identity_repository)]):
    item=repository.set_baseline(application_id,payload.run_id,user.user_id)
    if item is None:raise HTTPException(404,"应用或可用Baseline运行不存在")
    record_audit_event(identity,request,user_id=user.user_id,event_type="baseline.activated",
                       resource=item.baseline_id,metadata={"application_id":application_id,"run_id":payload.run_id})
    return asdict(item)


@router.get("/applications/{application_id}/baseline", response_model=BaselineResponse)
def active_baseline(application_id: str,
                    user: Annotated[UserRecord, Depends(get_current_user)],
                    repository: Annotated[GateRepository, Depends(provide_gate_repository)]):
    item=repository.get_active_baseline(application_id,user.user_id)
    if item is None:raise HTTPException(404,"活动Baseline不存在")
    return asdict(item)


@router.post("/workspaces/{workspace_id}/gate-policies",response_model=GatePolicyResponse,status_code=201)
def create_policy(workspace_id:str,payload:GatePolicyCreate,request:Request,
                  user:Annotated[UserRecord,Depends(get_current_user)],
                  repository:Annotated[GateRepository,Depends(provide_gate_repository)],
                  identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    try:item=repository.create_policy(workspace_id,payload.name,payload.version,[x.model_dump(exclude_none=True) for x in payload.rules],user.user_id)
    except GateValidationError as exc:raise HTTPException(422,str(exc)) from None
    if item is None:raise HTTPException(404,"Workspace不存在或无创建权限")
    record_audit_event(identity,request,user_id=user.user_id,event_type="gate_policy.created",resource=item.policy_id,metadata={"workspace_id":workspace_id})
    return asdict(item)


@router.get("/workspaces/{workspace_id}/gate-policies",response_model=GatePolicyListResponse)
def list_policies(workspace_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[GateRepository,Depends(provide_gate_repository)],workspaces:Annotated[WorkspaceRepository,Depends(provide_workspace_repository)]):
    workspace=workspaces.get_workspace_for_user(workspace_id,user.user_id)
    if workspace is None or workspace.role!="owner":raise HTTPException(404,"Workspace不存在或无读取权限")
    return {"policies":[asdict(x) for x in repository.list_policies(workspace_id,user.user_id)]}


@router.post("/gate-policies/{policy_id}/publish",response_model=GatePolicyResponse)
def publish_policy(policy_id:str,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[GateRepository,Depends(provide_gate_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    item=repository.publish_policy(policy_id,user.user_id)
    if item is None:raise HTTPException(404,"Gate Policy不存在、无权限或已经发布")
    record_audit_event(identity,request,user_id=user.user_id,event_type="gate_policy.published",resource=policy_id,metadata={"version":item.version})
    return asdict(item)


@router.post("/evaluation-runs/{run_id}/gate-evaluations",response_model=GateEvaluationResponse,status_code=201)
def evaluate_gate(run_id:str,payload:GateEvaluationRequest,request:Request,
                  user:Annotated[UserRecord,Depends(get_current_user)],
                  gates:Annotated[GateRepository,Depends(provide_gate_repository)],
                  reporting:Annotated[ReportingRepository,Depends(provide_reporting_repository)],
                  identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    item=GateService(gates,reporting).evaluate(run_id,payload.policy_id,user.user_id)
    if item is None:raise HTTPException(404,"运行或已发布Gate Policy不存在")
    record_audit_event(identity,request,user_id=user.user_id,event_type="gate_evaluation.created",resource=item.gate_evaluation_id,metadata={"run_id":run_id,"status":item.status})
    return asdict(item)


@router.get("/evaluation-runs/{run_id}/gate-evaluations",response_model=GateEvaluationListResponse)
def list_evaluations(run_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[GateRepository,Depends(provide_gate_repository)],reporting:Annotated[ReportingRepository,Depends(provide_reporting_repository)]):
    if reporting.load_snapshot(run_id,user.user_id) is None:raise HTTPException(404,"评测运行不存在或无读取权限")
    return {"evaluations":[asdict(x) for x in repository.list_evaluations(run_id,user.user_id)]}
