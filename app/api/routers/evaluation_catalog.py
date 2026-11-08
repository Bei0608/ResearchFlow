from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies import get_current_user, provide_evaluation_catalog_repository, provide_identity_repository, provide_workspace_repository
from app.api.evaluation_catalog_schemas import *
from app.evaluation.catalog import CatalogValidationError, DuplicateCatalogError, DuplicateContentError, EvaluationCatalogRepository, ImmutableCatalogError
from app.security import IdentityRepository, UserRecord
from app.security.audit import record_audit_event
from app.workspaces import WorkspaceRepository


router = APIRouter(tags=["evaluation-catalog"])


def _audit(repo: IdentityRepository, request: Request, user: UserRecord, event: str, resource: str, metadata: dict) -> None:
    record_audit_event(repo, request, user_id=user.user_id, event_type=event, resource=resource, metadata=metadata)


def _translate(exc: ValueError) -> HTTPException:
    if isinstance(exc, (DuplicateCatalogError, DuplicateContentError, ImmutableCatalogError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post("/workspaces/{workspace_id}/evaluation-datasets", response_model=DatasetResponse, status_code=201)
def create_dataset(workspace_id: str, payload: NamedResourceCreate, request: Request, user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[EvaluationCatalogRepository, Depends(provide_evaluation_catalog_repository)], identity: Annotated[IdentityRepository, Depends(provide_identity_repository)]):
    try: item=repository.create_dataset(workspace_id=workspace_id,user_id=user.user_id,name=payload.name,description=payload.description)
    except ValueError as exc: raise _translate(exc) from None
    if item is None: raise HTTPException(404,"Workspace不存在")
    _audit(identity,request,user,"evaluation_dataset.created",item.dataset_id,{"workspace_id":workspace_id});return asdict(item)


@router.get("/workspaces/{workspace_id}/evaluation-datasets", response_model=DatasetListResponse)
def list_datasets(workspace_id: str, user: Annotated[UserRecord, Depends(get_current_user)], workspaces: Annotated[WorkspaceRepository, Depends(provide_workspace_repository)], repository: Annotated[EvaluationCatalogRepository, Depends(provide_evaluation_catalog_repository)]):
    if workspaces.get_workspace_for_user(workspace_id,user.user_id) is None: raise HTTPException(404,"Workspace不存在")
    return {"datasets":[asdict(x) for x in repository.list_datasets(workspace_id,user.user_id)]}


@router.post("/evaluation-datasets/{dataset_id}/versions", response_model=DatasetVersionResponse, status_code=201)
def create_dataset_version(dataset_id: str,payload:VersionCreate,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    try:item=repository.create_dataset_version(dataset_id=dataset_id,user_id=user.user_id,version=payload.version,schema_version=payload.schema_version,environment=payload.environment)
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"评测集不存在")
    _audit(identity,request,user,"evaluation_dataset_version.created",item.dataset_version_id,{"dataset_id":dataset_id});return asdict(item)


@router.get("/evaluation-datasets/{dataset_id}/versions",response_model=DatasetVersionListResponse)
def list_dataset_versions(dataset_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    if repository.get_dataset(dataset_id,user.user_id) is None:raise HTTPException(404,"评测集不存在")
    return {"versions":[asdict(x) for x in repository.list_dataset_versions(dataset_id,user.user_id)]}


def _case_response(item):
    return {"case_id":item.case_id,"dataset_version_id":item.dataset_version_id,"external_id":item.external_id,"input":item.input_json,"expected":item.expected_json,"metadata":item.metadata_json,"created_at":item.created_at}


@router.post("/evaluation-datasets/{dataset_id}/versions/{version_id}/cases",response_model=EvaluationCaseResponse,status_code=201)
def add_case(dataset_id:str,version_id:str,payload:EvaluationCaseWrite,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    try:item=repository.add_case(dataset_id=dataset_id,version_id=version_id,user_id=user.user_id,external_id=payload.external_id,input_json=payload.input,expected_json=payload.expected,metadata_json=payload.metadata)
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"评测集版本不存在")
    _audit(identity,request,user,"evaluation_case.created",item.case_id,{"dataset_version_id":version_id});return _case_response(item)


@router.get("/evaluation-datasets/{dataset_id}/versions/{version_id}/cases",response_model=EvaluationCaseListResponse)
def list_cases(dataset_id:str,version_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    if repository.get_dataset_version(dataset_id,version_id,user.user_id) is None:raise HTTPException(404,"评测集版本不存在")
    return {"cases":[_case_response(x) for x in repository.list_cases(dataset_id,version_id,user.user_id)]}


@router.put("/evaluation-datasets/{dataset_id}/versions/{version_id}/cases/{case_id}",response_model=EvaluationCaseResponse)
def update_case(dataset_id:str,version_id:str,case_id:str,payload:EvaluationCaseWrite,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    try:item=repository.update_case(dataset_id=dataset_id,version_id=version_id,case_id=case_id,user_id=user.user_id,external_id=payload.external_id,input_json=payload.input,expected_json=payload.expected,metadata_json=payload.metadata)
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"案例不存在")
    return _case_response(item)


@router.delete("/evaluation-datasets/{dataset_id}/versions/{version_id}/cases/{case_id}",status_code=204)
def delete_case(dataset_id:str,version_id:str,case_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    try:deleted=repository.delete_case(dataset_id,version_id,case_id,user.user_id)
    except ValueError as exc:raise _translate(exc) from None
    if not deleted:raise HTTPException(404,"案例不存在")
    return Response(status_code=204)


@router.post("/evaluation-datasets/{dataset_id}/versions/{version_id}/publish",response_model=DatasetVersionResponse)
def publish_dataset(dataset_id:str,version_id:str,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    try:item=repository.publish_dataset_version(dataset_id,version_id,user.user_id)
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"评测集版本不存在")
    _audit(identity,request,user,"evaluation_dataset_version.published",version_id,{"dataset_id":dataset_id,"content_hash":item.content_hash});return asdict(item)


@router.post("/workspaces/{workspace_id}/rubrics",response_model=RubricResponse,status_code=201)
def create_rubric(workspace_id:str,payload:RubricCreate,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    try:item=repository.create_rubric(workspace_id=workspace_id,user_id=user.user_id,name=payload.name,description=payload.description)
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"Workspace不存在")
    _audit(identity,request,user,"rubric.created",item.rubric_id,{"workspace_id":workspace_id});return asdict(item)


@router.get("/workspaces/{workspace_id}/rubrics",response_model=RubricListResponse)
def list_rubrics(workspace_id:str,user:Annotated[UserRecord,Depends(get_current_user)],workspaces:Annotated[WorkspaceRepository,Depends(provide_workspace_repository)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    if workspaces.get_workspace_for_user(workspace_id,user.user_id) is None:raise HTTPException(404,"Workspace不存在")
    return {"rubrics":[asdict(x) for x in repository.list_rubrics(workspace_id,user.user_id)]}


@router.post("/rubrics/{rubric_id}/versions",response_model=RubricVersionResponse,status_code=201)
def create_rubric_version(rubric_id:str,payload:RubricVersionCreate,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    try:item=repository.create_rubric_version(rubric_id=rubric_id,user_id=user.user_id,version=payload.version,schema_version=payload.schema_version,environment=payload.environment,instructions=payload.instructions)
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"量表不存在")
    _audit(identity,request,user,"rubric_version.created",item.rubric_version_id,{"rubric_id":rubric_id});return asdict(item)


@router.get("/rubrics/{rubric_id}/versions",response_model=RubricVersionListResponse)
def list_rubric_versions(rubric_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    if repository.get_rubric(rubric_id,user.user_id) is None:raise HTTPException(404,"量表不存在")
    return {"versions":[asdict(x) for x in repository.list_rubric_versions(rubric_id,user.user_id)]}


def _criterion_response(x):return {"criterion_id":x.criterion_id,"rubric_version_id":x.rubric_version_id,"key":x.key,"title":x.title,"description":x.description,"min_score":x.min_score,"max_score":x.max_score,"weight":x.weight,"required":x.required,"created_at":x.created_at}


@router.post("/rubrics/{rubric_id}/versions/{version_id}/criteria",response_model=CriterionResponse,status_code=201)
def add_criterion(rubric_id:str,version_id:str,payload:CriterionWrite,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    try:item=repository.add_criterion(rubric_id=rubric_id,version_id=version_id,user_id=user.user_id,**payload.model_dump())
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"量表版本不存在")
    return _criterion_response(item)


@router.get("/rubrics/{rubric_id}/versions/{version_id}/criteria",response_model=CriterionListResponse)
def list_criteria(rubric_id:str,version_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    if repository.get_rubric_version(rubric_id,version_id,user.user_id) is None:raise HTTPException(404,"量表版本不存在")
    return {"criteria":[_criterion_response(x) for x in repository.list_criteria(rubric_id,version_id,user.user_id)]}


@router.put("/rubrics/{rubric_id}/versions/{version_id}/criteria/{criterion_id}",response_model=CriterionResponse)
def update_criterion(rubric_id:str,version_id:str,criterion_id:str,payload:CriterionWrite,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    try:item=repository.update_criterion(rubric_id=rubric_id,version_id=version_id,criterion_id=criterion_id,user_id=user.user_id,**payload.model_dump())
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"评分准则不存在")
    return _criterion_response(item)


@router.delete("/rubrics/{rubric_id}/versions/{version_id}/criteria/{criterion_id}",status_code=204)
def delete_criterion(rubric_id:str,version_id:str,criterion_id:str,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)]):
    try:deleted=repository.delete_criterion(rubric_id,version_id,criterion_id,user.user_id)
    except ValueError as exc:raise _translate(exc) from None
    if not deleted:raise HTTPException(404,"评分准则不存在")
    return Response(status_code=204)


@router.post("/rubrics/{rubric_id}/versions/{version_id}/publish",response_model=RubricVersionResponse)
def publish_rubric(rubric_id:str,version_id:str,request:Request,user:Annotated[UserRecord,Depends(get_current_user)],repository:Annotated[EvaluationCatalogRepository,Depends(provide_evaluation_catalog_repository)],identity:Annotated[IdentityRepository,Depends(provide_identity_repository)]):
    try:item=repository.publish_rubric_version(rubric_id,version_id,user.user_id)
    except ValueError as exc:raise _translate(exc) from None
    if item is None:raise HTTPException(404,"量表版本不存在")
    _audit(identity,request,user,"rubric_version.published",version_id,{"rubric_id":rubric_id,"content_hash":item.content_hash});return asdict(item)
