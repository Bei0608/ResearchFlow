from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.dependencies import get_current_user, provide_evaluation_run_repository, provide_identity_repository, provide_review_repository
from app.api.review_schemas import *
from app.evaluation.reviews import DuplicateReviewTaskError, HumanScoreRecord, ReviewRepository, ReviewValidationError, RevisionConflictError, SubmittedReviewError
from app.evaluation.runs import EvaluationRunRepository
from app.security import IdentityRepository, UserRecord
from app.security.audit import record_audit_event


router=APIRouter(tags=["human-reviews"])


def _case(x):return {"review_id":x.review_id,"case_result_id":x.case_result_id,"external_id":x.external_id,"input":x.input_json,"expected":x.expected_json,"output":x.output_json,"evidence":x.evidence_json,"review_status":x.review_status,"latest_revision":x.latest_revision}
def _revision(x):
    value=asdict(x);value.pop("idempotency_key",None);return value
def _task(repository,task):
    cases=repository.list_cases(task.task_id,task.reviewer_id);statuses=[x.review_status for x in cases]
    return {**asdict(task),"total_count":len(cases),"draft_count":statuses.count("draft"),"submitted_count":statuses.count("submitted"),"pending_count":statuses.count("pending")}
def _error(exc):
    if isinstance(exc,(RevisionConflictError,SubmittedReviewError,DuplicateReviewTaskError)):return HTTPException(409,str(exc))
    return HTTPException(422,str(exc))


@router.post("/evaluation-runs/{run_id}/review-tasks",response_model=ReviewTaskResponse,status_code=201)
def create_task(run_id:str,payload:ReviewTaskCreate,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[ReviewRepository,Depends(provide_review_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    reviewer_id=payload.reviewer_id or user.user_id
    try:item=repository.create_task(run_id=run_id,rubric_version_id=payload.rubric_version_id,name=payload.name,reviewer_id=reviewer_id,user_id=user.user_id)
    except ValueError as exc:raise _error(exc) from None
    if item is None:raise HTTPException(404,"运行、量表版本或评审人不存在")
    record_audit_event(identity,request,user_id=user.user_id,event_type="review_task.created",resource=item.task_id,metadata={"run_id":run_id,"reviewer_id":reviewer_id});return _task(repository,item)


@router.get("/review-tasks/mine",response_model=ReviewTaskListResponse)
def my_tasks(user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[ReviewRepository,Depends(provide_review_repository)]):return {"tasks":[_task(repository,x) for x in repository.list_tasks(user.user_id)]}


@router.get("/review-tasks/{task_id}",response_model=ReviewTaskDetailResponse)
def task_detail(task_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[ReviewRepository,Depends(provide_review_repository)]):
    task=repository.get_task(task_id,user.user_id)
    if not task:raise HTTPException(404,"评审任务不存在")
    return {"task":_task(repository,task),"cases":[_case(x) for x in repository.list_cases(task_id,user.user_id)],"criteria":[asdict(x) for x in repository.get_criteria(task_id,user.user_id)]}


@router.get("/review-tasks/{task_id}/cases/{case_result_id}",response_model=ReviewCaseDetailResponse)
def case_detail(task_id:str,case_result_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[ReviewRepository,Depends(provide_review_repository)],runs:Annotated[EvaluationRunRepository,Depends(provide_evaluation_run_repository)]):
    task=repository.get_task(task_id,user.user_id)
    case=next((x for x in repository.list_cases(task_id,user.user_id) if x.case_result_id==case_result_id),None)
    if not task or not case:raise HTTPException(404,"评审案例不存在")
    metrics=[asdict(x) for x in runs.list_metrics(task.run_id,user.user_id) if x.case_result_id==case_result_id]
    return {"task":_task(repository,task),"case":_case(case),"criteria":[asdict(x) for x in repository.get_criteria(task_id,user.user_id)],"revisions":[_revision(x) for x in repository.list_revisions(task_id,case_result_id,user.user_id)],"program_metrics":metrics}


def _write(status_value,task_id,case_result_id,payload,request,user,repository,identity,idempotency_key):
    scores=[HumanScoreRecord(x.criterion_id,x.score,x.comment) for x in payload.scores]
    try:item=repository.save_review(task_id=task_id,case_result_id=case_result_id,user_id=user.user_id,expected_revision=payload.expected_revision,status=status_value,overall_comment=payload.overall_comment,reason=payload.reason,scores=scores,idempotency_key=idempotency_key)
    except ValueError as exc:raise _error(exc) from None
    if item is None:raise HTTPException(404,"评审案例不存在")
    record_audit_event(identity,request,user_id=user.user_id,event_type=f"review.{status_value}",resource=item.review_id,metadata={"task_id":task_id,"case_result_id":case_result_id,"revision":item.revision});return _revision(item)


@router.put("/review-tasks/{task_id}/cases/{case_result_id}/draft",response_model=ReviewRevisionResponse)
def save_draft(task_id:str,case_result_id:str,payload:ReviewWrite,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[ReviewRepository,Depends(provide_review_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)],idempotency_key:Annotated[str|None,Header(alias="Idempotency-Key")]=None):return _write("draft",task_id,case_result_id,payload,request,user,repository,identity,idempotency_key)


@router.post("/review-tasks/{task_id}/cases/{case_result_id}/submit",response_model=ReviewRevisionResponse)
def submit_review(task_id:str,case_result_id:str,payload:ReviewWrite,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[ReviewRepository,Depends(provide_review_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)],idempotency_key:Annotated[str|None,Header(alias="Idempotency-Key")]=None):return _write("submitted",task_id,case_result_id,payload,request,user,repository,identity,idempotency_key)


@router.post("/review-tasks/{task_id}/cases/{case_result_id}/revisions",response_model=ReviewRevisionResponse,status_code=201)
def start_revision(task_id:str,case_result_id:str,payload:StartRevisionRequest,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[ReviewRepository,Depends(provide_review_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)],idempotency_key:Annotated[str|None,Header(alias="Idempotency-Key")]=None):
    try:item=repository.start_revision(task_id=task_id,case_result_id=case_result_id,user_id=user.user_id,expected_revision=payload.expected_revision,reason=payload.reason,idempotency_key=idempotency_key)
    except ValueError as exc:raise _error(exc) from None
    if item is None:raise HTTPException(404,"评审案例不存在")
    record_audit_event(identity,request,user_id=user.user_id,event_type="review.revision_started",resource=item.review_id,metadata={"revision":item.revision});return _revision(item)
