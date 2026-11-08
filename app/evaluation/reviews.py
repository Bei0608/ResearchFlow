from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from threading import RLock
from typing import Any, Literal, Protocol
from uuid import uuid4

from psycopg.errors import UniqueViolation

from app.memory.checkpointer import get_postgres_pool


ReviewStatus = Literal["pending", "draft", "submitted"]
RevisionStatus = Literal["draft", "submitted", "superseded"]


class DuplicateReviewTaskError(ValueError): pass
class RevisionConflictError(ValueError): pass
class ReviewValidationError(ValueError): pass
class SubmittedReviewError(ValueError): pass


@dataclass(frozen=True)
class ReviewTaskRecord:
    task_id: str
    run_id: str
    rubric_version_id: str
    name: str
    status: Literal["open", "completed"]
    assignment_id: str
    reviewer_id: str
    assignment_status: Literal["assigned", "in_progress", "completed"]
    created_by: str
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class ReviewCaseRecord:
    review_id: str
    case_result_id: str
    external_id: str
    input_json: dict[str, Any]
    expected_json: dict[str, Any]
    output_json: dict[str, Any]
    evidence_json: list[dict[str, Any]]
    review_status: ReviewStatus
    latest_revision: int


@dataclass(frozen=True)
class HumanScoreRecord:
    criterion_id: str
    score: float
    comment: str


@dataclass(frozen=True)
class ReviewRevisionRecord:
    revision_id: str
    review_id: str
    revision: int
    status: RevisionStatus
    overall_comment: str
    reason: str | None
    idempotency_key: str | None
    created_by: str
    created_at: datetime
    submitted_at: datetime | None
    scores: list[HumanScoreRecord]


@dataclass(frozen=True)
class ReviewCriterionRecord:
    criterion_id: str
    key: str
    title: str
    description: str
    min_score: float
    max_score: float
    weight: float
    required: bool


class ReviewRepository(Protocol):
    def create_task(self, **kwargs: Any) -> ReviewTaskRecord | None: ...
    def list_tasks(self, user_id: str) -> list[ReviewTaskRecord]: ...
    def get_task(self, task_id: str, user_id: str) -> ReviewTaskRecord | None: ...
    def list_cases(self, task_id: str, user_id: str) -> list[ReviewCaseRecord]: ...
    def get_criteria(self, task_id: str, user_id: str) -> list[ReviewCriterionRecord]: ...
    def list_revisions(self, task_id: str, case_result_id: str, user_id: str) -> list[ReviewRevisionRecord]: ...
    def save_review(self, **kwargs: Any) -> ReviewRevisionRecord | None: ...
    def start_revision(self, **kwargs: Any) -> ReviewRevisionRecord | None: ...


class PostgresReviewRepository:
    def __init__(self) -> None:self._pool=get_postgres_pool()

    @staticmethod
    def _task(row):
        return ReviewTaskRecord(**row) if row else None

    @staticmethod
    def _case(row):
        if not row:return None
        return ReviewCaseRecord(**{**row,"input_json":dict(row["input_json"]),"expected_json":dict(row["expected_json"]),"output_json":dict(row["output_json"]),"evidence_json":list(row["evidence_json"])})

    def create_task(self,*,run_id:str,rubric_version_id:str,name:str,reviewer_id:str,user_id:str)->ReviewTaskRecord|None:
        task_id=uuid4().hex;assignment_id=uuid4().hex
        try:
            with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
                cur.execute("""INSERT INTO researchflow_review_tasks (task_id,run_id,rubric_version_id,name,created_by)
                    SELECT %s,r.run_id,rv.rubric_version_id,%s,%s FROM researchflow_evaluation_runs r
                    JOIN researchflow_rubric_versions rv ON rv.rubric_version_id=%s
                    JOIN researchflow_rubrics rb ON rb.rubric_id=rv.rubric_id
                    JOIN researchflow_workspace_members owner ON owner.workspace_id=r.workspace_id
                    JOIN researchflow_workspace_members reviewer ON reviewer.workspace_id=r.workspace_id
                    WHERE r.run_id=%s AND r.status='ready_for_review' AND rv.status='published'
                      AND rb.workspace_id=r.workspace_id AND owner.user_id=%s AND owner.role='owner'
                      AND reviewer.user_id=%s
                      AND EXISTS (SELECT 1 FROM researchflow_case_results cr
                          WHERE cr.run_id=r.run_id AND cr.status='succeeded')
                    RETURNING task_id""",(task_id,name,user_id,rubric_version_id,run_id,user_id,reviewer_id))
                if cur.fetchone() is None:return None
                cur.execute("INSERT INTO researchflow_review_assignments (assignment_id,task_id,reviewer_id) VALUES (%s,%s,%s)",(assignment_id,task_id,reviewer_id))
                cur.execute("""INSERT INTO researchflow_reviews (review_id,assignment_id,case_result_id)
                    SELECT md5(random()::text || cr.case_result_id),%s,cr.case_result_id
                    FROM researchflow_case_results cr WHERE cr.run_id=%s AND cr.status='succeeded'""",(assignment_id,run_id))
        except UniqueViolation as exc:raise DuplicateReviewTaskError("运行中已存在同名评审任务") from exc
        return self.get_task(task_id,user_id)

    def _task_query(self,where:str,params:tuple)->list[ReviewTaskRecord]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(f"""SELECT t.task_id,t.run_id,t.rubric_version_id,t.name,t.status,
                a.assignment_id,a.reviewer_id,a.status AS assignment_status,t.created_by,t.created_at,t.completed_at
                FROM researchflow_review_tasks t JOIN researchflow_review_assignments a ON a.task_id=t.task_id
                WHERE {where} ORDER BY t.created_at,t.task_id""",params)
            return [self._task(x) for x in cur.fetchall()]

    def list_tasks(self,user_id):return self._task_query("a.reviewer_id=%s OR t.created_by=%s",(user_id,user_id))
    def get_task(self,task_id,user_id):
        rows=self._task_query("t.task_id=%s AND (a.reviewer_id=%s OR t.created_by=%s)",(task_id,user_id,user_id));return rows[0] if rows else None

    def list_cases(self,task_id,user_id):
        if not self.get_task(task_id,user_id):return []
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT r.review_id,cr.case_result_id,c.external_id,c.input_json,c.expected_json,
                cr.output_json,cr.evidence_json,r.status AS review_status,r.latest_revision
                FROM researchflow_reviews r JOIN researchflow_review_assignments a ON a.assignment_id=r.assignment_id
                JOIN researchflow_review_tasks t ON t.task_id=a.task_id JOIN researchflow_case_results cr ON cr.case_result_id=r.case_result_id
                JOIN researchflow_evaluation_cases c ON c.case_id=cr.case_id WHERE t.task_id=%s ORDER BY c.external_id""",(task_id,));return [self._case(x) for x in cur.fetchall()]

    def get_criteria(self,task_id,user_id):
        if not self.get_task(task_id,user_id):return []
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT c.criterion_id,c.criterion_key AS key,c.title,c.description,c.min_score,c.max_score,c.weight,c.required
                FROM researchflow_review_tasks t JOIN researchflow_rubric_criteria c ON c.rubric_version_id=t.rubric_version_id
                WHERE t.task_id=%s ORDER BY c.criterion_key""",(task_id,));return [ReviewCriterionRecord(x["criterion_id"],x["key"],x["title"],x["description"],float(x["min_score"]),float(x["max_score"]),float(x["weight"]),x["required"]) for x in cur.fetchall()]

    def _bundle(self,cur,revision_id):
        cur.execute("""SELECT revision_id,review_id,revision,status,overall_comment,reason,idempotency_key,created_by,created_at,submitted_at
            FROM researchflow_review_revisions WHERE revision_id=%s""",(revision_id,));row=cur.fetchone()
        if not row:return None
        cur.execute("SELECT criterion_id,score,comment FROM researchflow_human_scores WHERE revision_id=%s ORDER BY criterion_id",(revision_id,));scores=[HumanScoreRecord(x["criterion_id"],float(x["score"]),x["comment"]) for x in cur.fetchall()]
        return ReviewRevisionRecord(**row,scores=scores)

    def list_revisions(self,task_id,case_result_id,user_id):
        if not self.get_task(task_id,user_id):return []
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT rr.revision_id FROM researchflow_review_revisions rr JOIN researchflow_reviews r ON r.review_id=rr.review_id
                JOIN researchflow_review_assignments a ON a.assignment_id=r.assignment_id WHERE a.task_id=%s AND r.case_result_id=%s ORDER BY rr.revision""",(task_id,case_result_id));return [self._bundle(cur,x["revision_id"]) for x in cur.fetchall()]

    def save_review(self,*,task_id,case_result_id,user_id,expected_revision,status,overall_comment,reason,scores,idempotency_key):
        with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute("""SELECT r.review_id,r.latest_revision,r.status,a.assignment_id FROM researchflow_reviews r
                JOIN researchflow_review_assignments a ON a.assignment_id=r.assignment_id WHERE a.task_id=%s AND r.case_result_id=%s AND a.reviewer_id=%s FOR UPDATE""",(task_id,case_result_id,user_id));ctx=cur.fetchone()
            if not ctx:return None
            if idempotency_key:
                cur.execute("SELECT revision_id FROM researchflow_review_revisions WHERE review_id=%s AND idempotency_key=%s",(ctx["review_id"],idempotency_key));existing=cur.fetchone()
                if existing:return self._bundle(cur,existing["revision_id"])
            if ctx["latest_revision"]!=expected_revision:raise RevisionConflictError(f"revision冲突：当前为{ctx['latest_revision']}")
            if ctx["status"]=="submitted":raise SubmittedReviewError("已提交评审必须先创建修订")
            criteria=self._criteria_for_update(cur,task_id);self._validate_scores(criteria,scores,status=="submitted")
            revision=expected_revision+1;revision_id=uuid4().hex
            cur.execute("UPDATE researchflow_review_revisions SET status='superseded' WHERE review_id=%s AND status='draft'",(ctx["review_id"],))
            if status=="submitted":cur.execute("UPDATE researchflow_review_revisions SET status='superseded' WHERE review_id=%s AND status='submitted'",(ctx["review_id"],))
            cur.execute("""INSERT INTO researchflow_review_revisions (revision_id,review_id,revision,status,overall_comment,reason,idempotency_key,created_by,submitted_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='submitted' THEN NOW() END)""",(revision_id,ctx["review_id"],revision,status,overall_comment,reason,idempotency_key,user_id,status))
            self._insert_scores(cur,revision_id,scores)
            cur.execute("UPDATE researchflow_reviews SET latest_revision=%s,status=%s WHERE review_id=%s",(revision,status,ctx["review_id"]))
            cur.execute("UPDATE researchflow_review_assignments SET status='in_progress',completed_at=NULL WHERE assignment_id=%s",(ctx["assignment_id"],))
            if status=="submitted":self._complete_if_ready(cur,task_id,ctx["assignment_id"])
            return self._bundle(cur,revision_id)

    def start_revision(self,*,task_id,case_result_id,user_id,expected_revision,reason,idempotency_key):
        with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute("""SELECT r.review_id,r.latest_revision,r.status,a.assignment_id FROM researchflow_reviews r JOIN researchflow_review_assignments a ON a.assignment_id=r.assignment_id
                WHERE a.task_id=%s AND r.case_result_id=%s AND a.reviewer_id=%s FOR UPDATE""",(task_id,case_result_id,user_id));ctx=cur.fetchone()
            if not ctx:return None
            if idempotency_key:
                cur.execute("SELECT revision_id FROM researchflow_review_revisions WHERE review_id=%s AND idempotency_key=%s",(ctx["review_id"],idempotency_key));existing=cur.fetchone()
                if existing:return self._bundle(cur,existing["revision_id"])
            if ctx["latest_revision"]!=expected_revision:raise RevisionConflictError(f"revision冲突：当前为{ctx['latest_revision']}")
            if ctx["status"]!="submitted":raise ReviewValidationError("只有已提交评审可以创建纠错修订")
            cur.execute("SELECT revision_id,overall_comment FROM researchflow_review_revisions WHERE review_id=%s AND revision=%s",(ctx["review_id"],expected_revision));previous=cur.fetchone();new_id=uuid4().hex;revision=expected_revision+1
            cur.execute("""INSERT INTO researchflow_review_revisions (revision_id,review_id,revision,status,overall_comment,reason,idempotency_key,created_by)
                VALUES (%s,%s,%s,'draft',%s,%s,%s,%s)""",(new_id,ctx["review_id"],revision,previous["overall_comment"],reason,idempotency_key,user_id))
            cur.execute("""INSERT INTO researchflow_human_scores (score_id,revision_id,criterion_id,score,comment)
                SELECT md5(random()::text || criterion_id),%s,criterion_id,score,comment FROM researchflow_human_scores WHERE revision_id=%s""",(new_id,previous["revision_id"]))
            cur.execute("UPDATE researchflow_reviews SET latest_revision=%s,status='draft' WHERE review_id=%s",(revision,ctx["review_id"]))
            cur.execute("UPDATE researchflow_review_assignments SET status='in_progress',completed_at=NULL WHERE assignment_id=%s",(ctx["assignment_id"],));cur.execute("UPDATE researchflow_review_tasks SET status='open',completed_at=NULL WHERE task_id=%s",(task_id,))
            return self._bundle(cur,new_id)

    def _criteria_for_update(self,cur,task_id):
        cur.execute("""SELECT c.criterion_id,c.min_score,c.max_score,c.required FROM researchflow_review_tasks t
            JOIN researchflow_rubric_criteria c ON c.rubric_version_id=t.rubric_version_id WHERE t.task_id=%s""",(task_id,));return {x["criterion_id"]:x for x in cur.fetchall()}
    def _validate_scores(self,criteria,scores,submitting):
        ids=[x.criterion_id for x in scores]
        if len(ids)!=len(set(ids)):raise ReviewValidationError("评分准则不能重复")
        if any(x not in criteria for x in ids):raise ReviewValidationError("评分包含不属于当前量表的准则")
        for score in scores:
            rule=criteria[score.criterion_id]
            if not float(rule["min_score"])<=score.score<=float(rule["max_score"]):raise ReviewValidationError(f"准则{score.criterion_id}分数超出范围")
        required={x for x,v in criteria.items() if v["required"]}
        if submitting and not required.issubset(ids):raise ReviewValidationError("提交时必须填写所有必填评分准则")
    def _insert_scores(self,cur,revision_id,scores):
        for x in scores:cur.execute("INSERT INTO researchflow_human_scores (score_id,revision_id,criterion_id,score,comment) VALUES (%s,%s,%s,%s,%s)",(uuid4().hex,revision_id,x.criterion_id,x.score,x.comment))
    def _complete_if_ready(self,cur,task_id,assignment_id):
        cur.execute("SELECT COUNT(*) AS missing FROM researchflow_reviews WHERE assignment_id=%s AND status<>'submitted'",(assignment_id,));missing=cur.fetchone()["missing"]
        if missing==0:
            cur.execute("UPDATE researchflow_review_assignments SET status='completed',completed_at=NOW() WHERE assignment_id=%s",(assignment_id,));cur.execute("UPDATE researchflow_review_tasks SET status='completed',completed_at=NOW() WHERE task_id=%s",(task_id,))


class InMemoryReviewRepository:
    def __init__(self) -> None:
        self.tasks={};self.cases={};self.criteria={};self.revisions={};self._lock=RLock()
    def seed_context(self,*,run_id,rubric_version_id,case_results,criteria):self._seed=(run_id,rubric_version_id,deepcopy(case_results),deepcopy(criteria))
    def create_task(self,*,run_id,rubric_version_id,name,reviewer_id,user_id):
        if not hasattr(self,"_seed") or self._seed[0]!=run_id or self._seed[1]!=rubric_version_id or not self._seed[2]:return None
        if any(x.run_id==run_id and x.name==name for x in self.tasks.values()):raise DuplicateReviewTaskError("运行中已存在同名评审任务")
        t=ReviewTaskRecord(uuid4().hex,run_id,rubric_version_id,name,"open",uuid4().hex,reviewer_id,"assigned",user_id,datetime.now(timezone.utc),None);self.tasks[t.task_id]=t
        self.criteria[t.task_id]=self._seed[3]
        self.cases[t.task_id]=deepcopy(self._seed[2])
        return t
    def list_tasks(self,user_id):return [x for x in self.tasks.values() if x.reviewer_id==user_id or x.created_by==user_id]
    def get_task(self,task_id,user_id):
        x=self.tasks.get(task_id);return x if x and (x.reviewer_id==user_id or x.created_by==user_id) else None
    def list_cases(self,task_id,user_id):return deepcopy(self.cases.get(task_id,[])) if self.get_task(task_id,user_id) else []
    def get_criteria(self,task_id,user_id):return deepcopy(self.criteria.get(task_id,[])) if self.get_task(task_id,user_id) else []
    def list_revisions(self,task_id,case_result_id,user_id):
        if not self.get_task(task_id,user_id):return []
        case=next((x for x in self.cases.get(task_id,[]) if x.case_result_id==case_result_id),None)
        return deepcopy(self.revisions.get(case.review_id,[])) if case else []
    def save_review(self,*,task_id,case_result_id,user_id,expected_revision,status,overall_comment,reason,scores,idempotency_key):
        t=self.tasks.get(task_id)
        if not t or t.reviewer_id!=user_id:return None
        case=next((x for x in self.cases[task_id] if x.case_result_id==case_result_id),None)
        if not case:return None
        rows=self.revisions.setdefault(case.review_id,[])
        if idempotency_key:
            existing=next((x for x in rows if getattr(x,"idempotency_key",None)==idempotency_key),None)
            if existing:return existing
        if case.latest_revision!=expected_revision:raise RevisionConflictError(f"revision冲突：当前为{case.latest_revision}")
        if case.review_status=="submitted":raise SubmittedReviewError("已提交评审必须先创建修订")
        rules={x.criterion_id:x for x in self.criteria[task_id]};self._validate(rules,scores,status=="submitted")
        for i,x in enumerate(rows):
            if x.status=="draft":rows[i]=replace(x,status="superseded")
            if status=="submitted" and x.status=="submitted":rows[i]=replace(x,status="superseded")
        now=datetime.now(timezone.utc);record=ReviewRevisionRecord(uuid4().hex,case.review_id,expected_revision+1,status,overall_comment,reason,idempotency_key,user_id,now,now if status=="submitted" else None,deepcopy(scores));rows.append(record)
        self._set_case(task_id,case_result_id,expected_revision+1,status);self.tasks[task_id]=replace(t,assignment_status="in_progress")
        if status=="submitted" and all(x.review_status=="submitted" for x in self.cases[task_id]):self.tasks[task_id]=replace(self.tasks[task_id],status="completed",assignment_status="completed",completed_at=now)
        return record
    def start_revision(self,*,task_id,case_result_id,user_id,expected_revision,reason,idempotency_key):
        t=self.tasks.get(task_id)
        if not t or t.reviewer_id!=user_id:return None
        case=next((x for x in self.cases[task_id] if x.case_result_id==case_result_id),None)
        if not case:return None
        if idempotency_key:
            existing=next((x for x in self.revisions.get(case.review_id,[]) if x.idempotency_key==idempotency_key),None)
            if existing:return existing
        if case.latest_revision!=expected_revision:raise RevisionConflictError(f"revision冲突：当前为{case.latest_revision}")
        if case.review_status!="submitted":raise ReviewValidationError("只有已提交评审可以创建纠错修订")
        previous=self.revisions[case.review_id][-1];now=datetime.now(timezone.utc);record=ReviewRevisionRecord(uuid4().hex,case.review_id,expected_revision+1,"draft",previous.overall_comment,reason,idempotency_key,user_id,now,None,deepcopy(previous.scores));self.revisions[case.review_id].append(record);self._set_case(task_id,case_result_id,record.revision,"draft");self.tasks[task_id]=replace(t,status="open",assignment_status="in_progress",completed_at=None);return record
    def _set_case(self,task_id,case_result_id,revision,status):self.cases[task_id]=[replace(x,latest_revision=revision,review_status=status) if x.case_result_id==case_result_id else x for x in self.cases[task_id]]
    def _validate(self,rules,scores,submit):
        ids=[x.criterion_id for x in scores]
        if len(ids)!=len(set(ids)):raise ReviewValidationError("评分准则不能重复")
        if any(x not in rules for x in ids):raise ReviewValidationError("评分包含不属于当前量表的准则")
        for x in scores:
            if not rules[x.criterion_id].min_score<=x.score<=rules[x.criterion_id].max_score:raise ReviewValidationError("评分超出范围")
        if submit and not {x.criterion_id for x in rules.values() if x.required}.issubset(ids):raise ReviewValidationError("提交时必须填写所有必填评分准则")


@lru_cache(maxsize=1)
def get_review_repository()->PostgresReviewRepository:return PostgresReviewRepository()
