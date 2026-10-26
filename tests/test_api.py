import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db import Session,Repository,User
from backend.app.config import CIPHER

@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client

def account(client):
    email=uuid.uuid4().hex+"@example.com"
    body={"name":"Test Engineer","email":email,"password":"LongPassword2026!"}
    r=client.post("/api/auth/register",json=body);assert r.status_code==201
    token=client.post("/api/auth/login",json=body).json()["access_token"]
    return {"Authorization":"Bearer "+token},body

def test_registration_login_and_auth(client):
    headers,body=account(client)
    assert client.get("/api/auth/me",headers=headers).json()["email"]==body["email"]
    assert client.post("/api/auth/register",json=body).status_code==409
    assert client.post("/api/auth/login",json={**body,"password":"wrong"}).status_code==401
    assert client.get("/api/repositories").status_code==401
    assert client.get("/api/repositories",headers={"Authorization":"Bearer bad"}).status_code==401
    with Session() as db:
        assert db.query(User).filter_by(email=body["email"]).first().password.startswith("$argon2")

def test_full_prediction_history_and_ownership(client):
    headers,_=account(client)
    repo=client.post("/api/repositories/demo",headers=headers);assert repo.status_code==201
    r=repo.json();rid=r["id"];base=f"/api/repositories/{rid}"
    assert "path" not in r and "token" not in r
    files=client.get(base+"/files",headers=headers).json()
    assert "auth.py" in files and len(files)==8
    source=client.get(base+"/file",params={"path":"auth.py"},headers=headers).json()
    for proposed,expected in [(source["content"]+"\n# comment","LOW"),(source["content"].replace("username","email"),"HIGH")]:
        response=client.post(base+"/predictions",headers=headers,json={"file":"auth.py","modified":proposed,"base_commit":r["commit"]})
        assert response.status_code==201,response.text
        report=response.json();assert report["risk"]==expected
        assert {p["file"] for p in report["impacted_files"]}=={"services.py","main.py","tests/test_auth.py"}
        assert client.get(f"/api/predictions/{report['id']}",headers=headers).json()["graph"]["nodes"]
    assert len(client.get("/api/predictions",headers=headers).json())==2
    assert client.get(base+"/file",headers=headers,params={"path":"auth.py"}).json()==source
    other,_=account(client)
    for url in [base,base+"/files",base+"/graph",f"/api/predictions/{report['id']}"]:
        assert client.get(url,headers=other).status_code==404
    assert client.get("/api/predictions",headers=other).json()==[]
    assert client.post(base+"/predictions",headers=headers,json={"file":"auth.py","modified":"x=1","base_commit":"stale"}).status_code==409
    assert client.get(base+"/file",headers=headers,params={"path":"../../secret.py"}).status_code==400
    assert client.post(base+"/refresh",headers=headers).status_code==200
    assert client.get(f"/api/predictions/{report['id']}",headers=headers).json()["base_commit"]==source["base_commit"]
    assert client.delete(base,headers=headers).status_code==204
    assert client.get(base,headers=headers).status_code==404
    assert client.get("/api/predictions",headers=headers).json()==[]

def test_token_encryption_and_github_connection_contract(client,monkeypatch):
    from backend.app.repositories import demo_workspace
    headers,_=account(client)
    captured={}
    def local_clone(url,token):
        captured.update(url=url,token=token)
        return demo_workspace()
    monkeypatch.setattr("backend.app.main.clone",local_clone)
    response=client.post("/api/repositories",headers=headers,json={"url":"https://github.com/test/project","token":"sensitive-token"})
    assert response.status_code==201
    assert "sensitive-token" not in response.text
    with Session() as db:
        row=db.get(Repository,response.json()["id"])
        assert row.token!="sensitive-token"
        assert CIPHER.decrypt(row.token.encode()).decode()=="sensitive-token"
    assert captured["token"]=="sensitive-token"

def test_model_endpoint(client):
    headers,_=account(client)
    response=client.get("/api/model",headers=headers).json()
    assert response["loaded"] and response["metadata"]["evaluation"]["test"]["graphsage"]["pairs"]>0
    assert not response["calibrated"]

def test_url_and_payload_validation(client):
    headers,_=account(client)
    assert client.post("/api/repositories",headers=headers,json={"url":"file:///etc/passwd"}).status_code==400
    assert client.post("/api/auth/register",json={"name":"x","email":"not-email","password":"tiny"}).status_code==422
    invalid_secret="secret"*100
    invalid=client.post("/api/repositories",headers=headers,json={"url":"https://github.com/a/b","token":invalid_secret})
    assert invalid.status_code==422 and invalid_secret not in invalid.text
    response=client.post("/api/auth/login",content="x"*1_000_001)
    assert response.status_code==413

