from __future__ import annotations

from typing import Any

from app.evaluation.catalog import (
    DatasetVersionRecord,
    EvaluationCaseRecord,
    EvaluationCatalogRepository,
    RubricVersionRecord,
    CriterionRecord,
    dataset_content_hash,
    rubric_content_hash,
)


def import_dataset_payload(repository: EvaluationCatalogRepository, *, workspace_id: str, user_id: str, payload: dict[str, Any]) -> DatasetVersionRecord:
    name=str(payload["dataset_id"]); version=str(payload["version"])
    datasets=repository.list_datasets(workspace_id,user_id)
    dataset=next((x for x in datasets if x.name==name),None) or repository.create_dataset(workspace_id=workspace_id,user_id=user_id,name=name,description="Imported evaluation dataset")
    if dataset is None: raise ValueError("Workspace不存在或无写权限")
    rows=[]
    for case in payload["cases"]:
        rows.append(EvaluationCaseRecord("", "", str(case["case_id"]), {"question":case["question"]}, {k:v for k,v in case.items() if k not in {"case_id","question"}}, {}, dataset.created_at))
    digest=dataset_content_hash(rows)
    existing=repository.find_dataset_version_by_hash(dataset.dataset_id,digest,user_id)
    if existing:return existing
    item=repository.create_dataset_version(dataset_id=dataset.dataset_id,user_id=user_id,version=version,schema_version=str(payload["schema_version"]),environment=str(payload["environment"]))
    if item is None: raise ValueError("无法创建评测集版本")
    for row in rows: repository.add_case(dataset_id=dataset.dataset_id,version_id=item.dataset_version_id,user_id=user_id,external_id=row.external_id,input_json=row.input_json,expected_json=row.expected_json,metadata_json=row.metadata_json)
    result=repository.publish_dataset_version(dataset.dataset_id,item.dataset_version_id,user_id)
    if result is None: raise ValueError("无法发布评测集版本")
    return result


def import_rubric_payload(repository: EvaluationCatalogRepository, *, workspace_id: str, user_id: str, payload: dict[str, Any]) -> RubricVersionRecord:
    name=str(payload["rubric_id"]); version=str(payload["version"]); instructions=str(payload["instructions"])
    rubrics=repository.list_rubrics(workspace_id,user_id)
    rubric=next((x for x in rubrics if x.name==name),None) or repository.create_rubric(workspace_id=workspace_id,user_id=user_id,name=name,description="Imported evaluation rubric")
    if rubric is None: raise ValueError("Workspace不存在或无写权限")
    rows=[CriterionRecord("","",str(x["key"]),str(x["title"]),str(x.get("description","")),float(x["min_score"]),float(x["max_score"]),float(x["weight"]),bool(x.get("required",True)),rubric.created_at) for x in payload["criteria"]]
    digest=rubric_content_hash(instructions,rows)
    existing=repository.find_rubric_version_by_hash(rubric.rubric_id,digest,user_id)
    if existing:return existing
    item=repository.create_rubric_version(rubric_id=rubric.rubric_id,user_id=user_id,version=version,schema_version=str(payload["schema_version"]),environment=str(payload["environment"]),instructions=instructions)
    if item is None: raise ValueError("无法创建量表版本")
    for row in rows: repository.add_criterion(rubric_id=rubric.rubric_id,version_id=item.rubric_version_id,user_id=user_id,key=row.key,title=row.title,description=row.description,min_score=row.min_score,max_score=row.max_score,weight=row.weight,required=row.required)
    result=repository.publish_rubric_version(rubric.rubric_id,item.rubric_version_id,user_id)
    if result is None: raise ValueError("无法发布量表版本")
    return result
