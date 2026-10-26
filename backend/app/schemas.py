from typing import Any, Literal
from pydantic import BaseModel

Risk=Literal["LOW","MEDIUM","HIGH"]

class TokenView(BaseModel):
    access_token:str
    token_type:Literal["bearer"]

class RepositoryView(BaseModel):
    id:int
    name:str
    url:str
    branch:str
    commit:str
    updated_at:str
    kind:str
    status:str
    file_count:int
    edge_count:int
    history_commits:int
    commits_scanned:int
    parse_errors:list[dict[str,str]]

class FileView(BaseModel):
    path:str
    content:str
    base_commit:str

class GraphView(BaseModel):
    nodes:list[dict[str,Any]]
    edges:list[dict[str,Any]]
    historical:list[dict[str,Any]]
    bindings:dict[str,Any]
    history_commits:int
    commits_scanned:int
    feature_schema:list[str]

class ImpactView(BaseModel):
    file:str
    score:float
    risk:Risk
    distance:int|None
    reasons:list[str]

class ReportView(BaseModel):
    id:int
    repository_id:int
    repository:str
    status:str
    created_at:str
    changed_file:str
    base_commit:str
    risk:Risk
    summary:dict[str,Any]
    violations:list[dict[str,str]]
    diff:str
    semantic_change:bool
    impacted_files:list[ImpactView]
    message:str
    score_label:str
    risk_method:str
    history_available:bool
    model_version:str
    direct_count:int
    indirect_count:int
    original:str
    modified:str
    graph:GraphView|None=None

class HistoryView(BaseModel):
    id:int
    repository_id:int
    created_at:str
    status:str
    repository:str
    changed_file:str
    risk:Risk
    base_commit:str
    model_version:str
    affected_count:int

class ModelView(BaseModel):
    loaded:bool
    metadata:dict[str,Any]|None
    calibrated:bool
    arbitrary_test_execution:bool

