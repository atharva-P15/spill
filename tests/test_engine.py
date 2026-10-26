import ast
from pathlib import Path
import pytest
import torch
from git import Repo, Actor
from ml.graph import build_graph, candidates, history, read_sources, pair_features, FEATURES
from ml.model import GraphSAGE, Predictor, tensors
from backend.app.changes import analyze_change, predict
from backend.app.repositories import safe_path
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def sources():
    return read_sources(ROOT/"demo/sample_repo")

def test_absolute_and_relative_imports():
    s={"pkg/__init__.py":"","pkg/auth.py":"def auth(): pass","pkg/service.py":"from .auth import auth",
       "main.py":"from pkg import service\nimport requests","src/other/__init__.py":"","src/other/a.py":"from . import b","src/other/b.py":""}
    g=build_graph(s);edges={(e["source"],e["target"]) for e in g["edges"]}
    assert ("pkg/service.py","pkg/auth.py") in edges
    assert ("main.py","pkg/service.py") in edges
    assert ("src/other/a.py","src/other/b.py") in edges
    assert len(edges)==3

def test_transitive_and_cold_start(sources):
    g=build_graph(sources)
    assert {"services.py","main.py","tests/test_auth.py"}<=set(candidates(g,"auth.py"))
    assert g["history_commits"]==0
    assert all(n["features"][-2:]==[0,0] for n in g["nodes"])
    assert pair_features(g,"auth.py",["main.py"])[0][1]==.5
    assert pair_features(g,"auth.py",["services.py"])[0][0]==1

def test_history_normalization_and_bulk_exclusion(sources):
    history_data=[{"files":["auth.py","services.py"]},{"files":["auth.py","services.py"]},
                  {"files":list(sources),"initial":True}]
    g=build_graph(sources,history_data)
    assert g["history_commits"]==2
    assert g["historical"]==[{"source":"auth.py","target":"services.py","count":2,"weight":1.0}]

def test_real_git_history(tmp_path):
    repo=Repo.init(tmp_path);actor=Actor("Test","test@example.com")
    for i in range(3):
        for name in ["a.py","b.py"]:(tmp_path/name).write_text(f"x={i}\n")
        repo.index.add(["a.py","b.py"]);repo.index.commit(str(i),author=actor,committer=actor)
    events=history(repo);repo.close()
    assert events[0]["initial"]
    assert events[1]["files"]==["a.py","b.py"]
    g=build_graph(read_sources(tmp_path),events)
    assert g["history_commits"]==2 and g["historical"][0]["count"]==2

@pytest.mark.parametrize("change,risk",[
    (lambda s:s+"\n# documentation only\n","LOW"),
    (lambda s:s.replace("bool(user and","bool(False and"),"MEDIUM"),
    (lambda s:"def broken(\n","HIGH"),
    (lambda s:s.replace("authenticate_user","renamed_user"),"HIGH"),
    (lambda s:s.replace("username","email"),"HIGH"),
    (lambda s:s.replace("username, password","username, password, otp"),"HIGH")])
def test_changes(sources,change,risk):
    result=analyze_change(sources["auth.py"],change(sources["auth.py"]),"auth.py",sources,build_graph(sources))
    assert result["risk"]==risk
    if risk=="HIGH":assert result["violations"]

def test_positional_rename_is_not_incompatible():
    sources={"a.py":"def f(x): return x","b.py":"from a import f\ny=f(1)"}
    r=analyze_change(sources["a.py"],"def f(y): return y","a.py",sources,build_graph(sources))
    assert r["risk"]=="MEDIUM" and not r["violations"]

def test_docstring_only_low():
    s={"a.py":'def f():\n    """Old."""\n    return 1'}
    assert analyze_change(s["a.py"],s["a.py"].replace("Old.","New."),"a.py",s,build_graph(s))["risk"]=="LOW"

def test_removed_constant():
    s={"a.py":"KEY=42","b.py":"from a import KEY\nprint(KEY)"}
    assert analyze_change(s["a.py"],"OTHER=42","a.py",s,build_graph(s))["risk"]=="HIGH"

def test_graphsage_trainable_and_checkpoint(sources):
    g=build_graph(sources);model=GraphSAGE()
    args=tensors(g,"auth.py",["services.py","main.py"],[0]*len(FEATURES),[1]*len(FEATURES))
    logits=model(*args);assert logits.shape==(2,)
    logits.sum().backward()
    assert model.sage1.linear.weight.grad.abs().sum()>0
    predictor=Predictor(ROOT/"ml/checkpoints/graphsage.pt")
    result=predict(predictor,sources,g,"auth.py",sources["auth.py"]+"\n# comment")
    assert result["risk"]=="LOW" and len(result["impacted_files"])==3
    assert result["impacted_files"]==sorted(result["impacted_files"],key=lambda x:x["score"],reverse=True)

@pytest.mark.parametrize("path",["../secrets.py","C:/Windows/system.py","../../other.py","a.py:stream"])
def test_path_traversal(tmp_path,path):
    with pytest.raises(ValueError):safe_path(tmp_path,path)

def test_feature_windows_are_disjoint():
    import json
    data=json.loads((ROOT/"ml/data/dataset.json").read_text())
    for e in data:
        assert not set(e["feature_commits"])&set(e["window"])
        assert e["base_commit"]==e["feature_commits"][-1]
    by_repo={}
    for e in data:by_repo.setdefault(e["repository"],{}).setdefault(e["split"],set()).update(e["window"])
    for splits in by_repo.values():
        for a in splits:
            for b in splits:
                if a!=b:assert not splits[a]&splits[b]
    assert all(e["split"]=="heldout" for e in data if e["repository"]=="itsdangerous")

@pytest.mark.parametrize("variant,expected",[("good",0),("bad",1)])
def test_trusted_demo_execution(variant,expected):
    from demo.demo_runner import test_trusted_variant
    result=test_trusted_variant(variant)
    assert result["exit_code"]==expected
    assert ("5 passed" if variant=="good" else "3 failed, 2 passed") in result["output"]

