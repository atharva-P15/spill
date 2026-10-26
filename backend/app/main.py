import logging
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from threading import Lock
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from backend.app.config import JWT_SECRET, CIPHER, MODEL_PATH, CORS
from backend.app.db import Session, init_db, User, Repository, Snapshot, GraphNode, GraphEdge, Analysis, Impact, ModelMetadata, now
from backend.app.repositories import clone, demo_workspace, snapshot, safe_path, remove_workspace
from backend.app.changes import predict
from ml.graph import read_sources
from ml.model import Predictor
from backend.app.schemas import TokenView,RepositoryView,FileView,GraphView,ReportView,HistoryView,ModelView

class JsonFormatter(logging.Formatter):
    def format(self,record):
        return json.dumps({"time":self.formatTime(record),"level":record.levelname,"message":record.getMessage()})
handler=logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO,handlers=[handler])
log=logging.getLogger("spill")
hasher=PasswordHasher()
auth=HTTPBearer(auto_error=False)
mutation_lock=Lock()

@asynccontextmanager
async def lifespan(app):
    init_db()
    app.state.predictor=Predictor(MODEL_PATH) if MODEL_PATH.exists() else None
    if app.state.predictor:
        with Session() as db:
            meta=app.state.predictor.metadata
            db.merge(ModelMetadata(version=meta["version"],data=meta))
            db.commit()
    yield

app=FastAPI(title="SPILL — Code Change Impact Predictor",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=CORS,allow_credentials=False,allow_methods=["GET","POST","DELETE"],allow_headers=["Authorization","Content-Type"])

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    # Pydantic's default response echoes invalid inputs, which may include credentials.
    return JSONResponse(status_code=422,content={"detail":[{"loc":e["loc"],"msg":e["msg"],"type":e["type"]} for e in exc.errors()]})

@app.exception_handler(ValueError)
async def value_error(request,exc):
    return JSONResponse(status_code=400,content={"detail":str(exc)})
@app.exception_handler(Exception)
async def internal_error(request,exc):
    log.error("request_failed type=%s path=%s",type(exc).__name__,request.url.path)
    return JSONResponse(status_code=500,content={"detail":"The operation failed. Check the local server logs and retry."})

@app.middleware("http")
async def size_limit(request: Request,call_next):
    if int(request.headers.get("content-length","0") or 0)>1_000_000:
        return JSONResponse(status_code=413,content={"detail":"Request exceeds 1 MB."})
    if request.method in {"POST","PUT","PATCH"}:
        chunks=[]; size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>1_000_000:
                return JSONResponse(status_code=413,content={"detail":"Request exceeds 1 MB."})
            chunks.append(chunk)
        request._body=b"".join(chunks)
    return await call_next(request)

def database():
    with Session() as db:
        yield db

def current_user(credentials: HTTPAuthorizationCredentials=Depends(auth),db=Depends(database)):
    try:
        payload=jwt.decode(credentials.credentials,JWT_SECRET,algorithms=["HS256"],issuer="spill",options={"require":["exp","sub","iss"]})
        user=db.get(User,int(payload["sub"]))
        if user is None:
            raise ValueError()
        return user
    except (jwt.PyJWTError,ValueError,AttributeError):
        raise HTTPException(401,"Please sign in.") from None

def owned(db,user,repo_id):
    repo=db.query(Repository).filter_by(id=repo_id,user_id=user.id).first()
    if not repo:
        raise HTTPException(404,"Repository not found.")
    return repo

def repo_view(repo,db):
    snap=db.get(Snapshot,repo.snapshot_id)
    return {"id":repo.id,"name":repo.name,"url":repo.url,"branch":repo.branch,"commit":repo.commit,
            "updated_at":repo.updated_at,"kind":repo.kind,"status":"ready",
            "file_count":len(snap.data["nodes"]),"edge_count":len(snap.data["edges"]),
            "history_commits":snap.data["history_commits"],"commits_scanned":snap.data["commits_scanned"],
            "parse_errors":[{"file":n["id"],"error":n["error"]} for n in snap.data["nodes"] if n["error"]]}

def save_snapshot(db,repo,path):
    commit,data=snapshot(path)
    snap=Snapshot(repository_id=repo.id,commit=commit,data=data)
    db.add(snap); db.flush()
    db.add_all(GraphNode(snapshot_id=snap.id,path=n["id"],features=n["features"]) for n in data["nodes"])
    db.add_all(GraphEdge(snapshot_id=snap.id,source=e["source"],target=e["target"],kind=e.get("kind","historical"))
               for e in data["edges"]+data["historical"])
    repo.path=str(path);repo.commit=commit;repo.snapshot_id=snap.id;repo.updated_at=now()
    return snap

class Registration(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    email:EmailStr
    password:str=Field(min_length=10,max_length=128)
class Login(BaseModel):
    email:EmailStr
    password:str=Field(min_length=1,max_length=128)
class Connect(BaseModel):
    url:str=Field(max_length=250)
    token:str|None=Field(default=None,max_length=500)
class Proposal(BaseModel):
    file:str=Field(min_length=1,max_length=500)
    modified:str=Field(max_length=256_000)
    base_commit:str=Field(min_length=1,max_length=64)
class UserView(BaseModel):
    id:int
    name:str
    email:EmailStr

@app.get("/api/health")
def health():
    return {"status":"ok","model_loaded":getattr(app.state,"predictor",None) is not None}

@app.post("/api/auth/register",status_code=201,response_model=UserView)
def register(body:Registration,db=Depends(database)):
    user=User(name=body.name.strip(),email=str(body.email).lower(),password=hasher.hash(body.password))
    if not user.name:
        raise HTTPException(422,"Name is required.")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,"An account with this email already exists.") from None
    return UserView(id=user.id,name=user.name,email=user.email)

@app.post("/api/auth/login",response_model=TokenView)
def login(body:Login,db=Depends(database)):
    user=db.query(User).filter_by(email=str(body.email).lower()).first()
    try:
        hasher.verify(user.password if user else hasher.hash(secrets.token_hex(12)),body.password)
        if not user:raise VerifyMismatchError()
    except (VerifyMismatchError,InvalidHashError):
        raise HTTPException(401,"Email or password is incorrect.") from None
    token=jwt.encode({"sub":str(user.id),"exp":datetime.now(timezone.utc)+timedelta(hours=8),"iss":"spill"},JWT_SECRET,algorithm="HS256")
    return {"access_token":token,"token_type":"bearer"}

@app.get("/api/auth/me",response_model=UserView)
def me(user=Depends(current_user)):
    return UserView(id=user.id,name=user.name,email=user.email)

@app.get("/api/repositories",response_model=list[RepositoryView])
def list_repositories(user=Depends(current_user),db=Depends(database)):
    return [repo_view(r,db) for r in db.query(Repository).filter_by(user_id=user.id).all()]

def connect_repo(db,user,path,name,branch,url,token,kind):
    repo=Repository(user_id=user.id,name=name,branch=branch,url=url,kind=kind,
                    token=CIPHER.encrypt(token.encode()).decode() if token else None)
    try:
        db.add(repo);db.flush();save_snapshot(db,repo,path);db.commit()
    except Exception:
        db.rollback();remove_workspace(path);raise
    return repo_view(repo,db)

@app.post("/api/repositories",status_code=201,response_model=RepositoryView)
def connect_repository(body:Connect,user=Depends(current_user),db=Depends(database)):
    with mutation_lock:
        path,name,branch=clone(body.url,body.token)
        return connect_repo(db,user,path,name,branch,body.url,body.token,"github")

@app.post("/api/repositories/demo",status_code=201,response_model=RepositoryView)
def connect_demo(user=Depends(current_user),db=Depends(database)):
    with mutation_lock:
        path,name,branch=demo_workspace()
        return connect_repo(db,user,path,name,branch,"local:trusted-demo",None,"demo")

@app.get("/api/repositories/{repo_id}",response_model=RepositoryView)
def repository(repo_id:int,user=Depends(current_user),db=Depends(database)):
    return repo_view(owned(db,user,repo_id),db)

@app.post("/api/repositories/{repo_id}/refresh",response_model=RepositoryView)
def refresh(repo_id:int,user=Depends(current_user),db=Depends(database)):
    with mutation_lock:
        repo=owned(db,user,repo_id)
        old=repo.path
        path,name,branch=demo_workspace() if repo.kind=="demo" else clone(repo.url,CIPHER.decrypt(repo.token.encode()).decode() if repo.token else None)
        try:
            save_snapshot(db,repo,path);repo.branch=branch;db.commit()
        except Exception:
            db.rollback();remove_workspace(path);raise
        remove_workspace(old)
        return repo_view(repo,db)

@app.delete("/api/repositories/{repo_id}",status_code=204)
def disconnect(repo_id:int,user=Depends(current_user),db=Depends(database)):
    with mutation_lock:
        repo=owned(db,user,repo_id)
        remove_workspace(repo.path);db.delete(repo);db.commit()

@app.get("/api/repositories/{repo_id}/files",response_model=list[str])
def files(repo_id:int,user=Depends(current_user),db=Depends(database)):
    repo=owned(db,user,repo_id)
    return [n["id"] for n in db.get(Snapshot,repo.snapshot_id).data["nodes"]]

@app.get("/api/repositories/{repo_id}/file",response_model=FileView)
def file(repo_id:int,path:str,user=Depends(current_user),db=Depends(database)):
    repo=owned(db,user,repo_id)
    return {"path":path,"content":safe_path(repo.path,path).read_text(encoding="utf-8-sig",errors="replace"),"base_commit":repo.commit}

@app.get("/api/repositories/{repo_id}/graph",response_model=GraphView)
def graph(repo_id:int,user=Depends(current_user),db=Depends(database)):
    repo=owned(db,user,repo_id)
    return db.get(Snapshot,repo.snapshot_id).data

@app.post("/api/repositories/{repo_id}/predictions",status_code=201,response_model=ReportView)
def prediction(repo_id:int,body:Proposal,user=Depends(current_user),db=Depends(database)):
    with mutation_lock:
        repo=owned(db,user,repo_id)
        if body.base_commit!=repo.commit:
            raise HTTPException(409,"Repository refreshed. Reload the file before predicting.")
        if not app.state.predictor:
            raise HTTPException(503,"No trained model. Run the preparation and training commands in README.")
        target=safe_path(repo.path,body.file)
        changed=target.relative_to(__import__("pathlib").Path(repo.path)).as_posix()
        sources=read_sources(repo.path)
        if changed not in sources:raise HTTPException(404,"File is excluded from analysis.")
        if sources[changed]==body.modified:raise HTTPException(422,"Modify the source before predicting.")
        if next(n for n in db.get(Snapshot,repo.snapshot_id).data["nodes"] if n["id"]==changed)["error"]:
            raise HTTPException(422,"The original file has invalid Python syntax; choose a parseable file.")
        report=predict(app.state.predictor,sources,db.get(Snapshot,repo.snapshot_id).data,changed,body.modified)
        report.update({"base_commit":repo.commit,"repository":repo.name,"original":sources[changed],"modified":body.modified})
        row=Analysis(repository_id=repo.id,snapshot_id=repo.snapshot_id,user_id=user.id,report=report)
        db.add(row);db.flush()
        db.add_all(Impact(analysis_id=row.id,data=r) for r in report["impacted_files"]);db.commit()
        return {**report,"id":row.id,"repository_id":repo.id,"created_at":row.created_at,"status":row.status}

@app.get("/api/predictions",response_model=list[HistoryView])
def analyses(user=Depends(current_user),db=Depends(database)):
    return [{"id":a.id,"repository_id":a.repository_id,"created_at":a.created_at,"status":a.status,
             **{k:a.report[k] for k in ["repository","changed_file","risk","base_commit","model_version"]},
             "affected_count":len(a.report["impacted_files"])}
            for a in db.query(Analysis).filter_by(user_id=user.id).order_by(Analysis.id.desc()).all()]

@app.get("/api/predictions/{analysis_id}",response_model=ReportView)
def report(analysis_id:int,user=Depends(current_user),db=Depends(database)):
    a=db.query(Analysis).filter_by(id=analysis_id,user_id=user.id).first()
    if not a:raise HTTPException(404,"Analysis not found.")
    return {**a.report,"id":a.id,"repository_id":a.repository_id,"created_at":a.created_at,"status":a.status,
            "graph":db.get(Snapshot,a.snapshot_id).data}

@app.get("/api/model",response_model=ModelView)
def model(user=Depends(current_user)):
    p=app.state.predictor
    return {"loaded":p is not None,"metadata":p.metadata if p else None,
            "calibrated":False,"arbitrary_test_execution":False}

