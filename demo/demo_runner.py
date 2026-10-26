"""Explicit trusted demo: never execute user-supplied proposals or external repository code."""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]

def test_trusted_variant(variant):
    if variant not in {"good","bad"}:raise ValueError("Only bundled good/bad variants are executable.")
    with tempfile.TemporaryDirectory(prefix="spill-trusted-demo-") as directory:
        path=Path(directory)/"repo"
        shutil.copytree(ROOT/"demo/sample_repo",path,ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        source=(ROOT/f"demo/{variant}_change/auth.py").read_text()
        (path/"auth.py").write_text(source)
        env=os.environ.copy()
        env["PYTHONPATH"]=str(path)
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"]="1"
        run=subprocess.run([sys.executable,"-m","pytest","-q","-p","no:cacheprovider"],cwd=path,env=env,
                           capture_output=True,text=True,timeout=30)
        return {"exit_code":run.returncode,"output":run.stdout+run.stderr}

def run(base_url):
    creds_path=ROOT/"runtime/demo-login.json"
    creds_path.parent.mkdir(exist_ok=True)
    if creds_path.exists():credentials=json.loads(creds_path.read_text())
    else:
        credentials={"name":"Demo Engineer","email":"demo@example.com","password":secrets.token_urlsafe(20)}
        creds_path.write_text(json.dumps(credentials,indent=2))
    with httpx.Client(base_url=base_url,timeout=180) as client:
        registered=client.post("/api/auth/register",json=credentials)
        if registered.status_code not in (201,409):registered.raise_for_status()
        login=client.post("/api/auth/login",json=credentials);login.raise_for_status()
        client.headers["Authorization"]="Bearer "+login.json()["access_token"]
        repo_response=client.post("/api/repositories/demo");repo_response.raise_for_status()
        repo=repo_response.json()
        result={"repository":repo,"variants":{}}
        for variant,expected in [("good","LOW"),("bad","HIGH")]:
            proposed=(ROOT/f"demo/{variant}_change/auth.py").read_text()
            response=client.post(f"/api/repositories/{repo['id']}/predictions",
                                 json={"file":"auth.py","modified":proposed,"base_commit":repo["commit"]})
            response.raise_for_status();prediction=response.json()
            tests=test_trusted_variant(variant)
            assert prediction["risk"]==expected,prediction
            assert (tests["exit_code"]==0)==(variant=="good"),tests
            assert {p["file"] for p in prediction["impacted_files"]}=={"services.py","main.py","tests/test_auth.py"}
            result["variants"][variant]={"prediction":prediction,"trusted_tests":tests}
        result["verification"]="Live HTTP API; trusted tests ran in temporary copies. UI verification is recorded separately."
    output=ROOT/"docs/demo-report.json"
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(f"Demo verified. Report: {output}. Local demo sign-in: {creds_path}")
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8000")
    run(parser.parse_args().url)

