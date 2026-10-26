import base64
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
import httpx
from git import Repo
from backend.app.config import WORKSPACES, ROOT
from ml.graph import read_sources, build_graph, history

MAX_CLONE_BYTES = 150 * 1024 * 1024

def safe_path(root, relative):
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root or Path(relative).is_absolute() or ":" in relative:
        raise ValueError("Invalid repository path.")
    if target.suffix != ".py" or not target.is_file() or target.is_symlink():
        raise ValueError("Python source file not found.")
    if target.stat().st_size > 256_000:
        raise ValueError("File exceeds the 256 KB source limit.")
    return target

def remove_workspace(path):
    p = Path(path).resolve()
    if p == WORKSPACES or not p.is_relative_to(WORKSPACES):
        raise ValueError("Refusing to remove a path outside managed workspaces.")
    def retry(func, name, exc):
        os.chmod(name,0o700)
        func(name)
    if p.exists():
        shutil.rmtree(p,onerror=retry)

def clone(url, token=None):
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?",url)
    if not match or any(x in {".",".."} for x in match.groups()):
        raise ValueError("Use an HTTPS github.com/owner/repository URL.")
    owner,name = match.groups()
    headers = {"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
    if token:
        headers["Authorization"]="Bearer "+token
    try:
        response = httpx.get(f"https://api.github.com/repos/{owner}/{name}",headers=headers,timeout=20)
    except httpx.HTTPError:
        raise ValueError("GitHub could not be reached. Check network access.") from None
    if response.status_code != 200:
        raise ValueError("GitHub access failed. Check repository URL, token permissions, and API rate limits.")
    info = response.json()
    if info.get("size",0)>150_000:
        raise ValueError("Repository exceeds the 150 MB clone budget.")
    destination = WORKSPACES / uuid.uuid4().hex
    env = os.environ.copy()
    env.update({"GIT_TERMINAL_PROMPT":"0","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull,
                "GIT_LFS_SKIP_SMUDGE":"1","GIT_CONFIG_COUNT":"2",
                "GIT_CONFIG_KEY_0":"core.hooksPath","GIT_CONFIG_VALUE_0":str(WORKSPACES/"disabled-hooks"),
                "GIT_CONFIG_KEY_1":"protocol.file.allow","GIT_CONFIG_VALUE_1":"never"})
    if token:
        env.update({"GIT_CONFIG_COUNT":"3","GIT_CONFIG_KEY_2":"http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_2":"AUTHORIZATION: basic "+base64.b64encode(("x-access-token:"+token).encode()).decode()})
    # No token in arguments, remotes, error text, or persisted git configuration.
    process = subprocess.Popen(["git","clone","--depth","250","--single-branch","--no-tags",
                                f"https://github.com/{owner}/{name}.git",str(destination)],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
    start = time.monotonic()
    try:
        while process.poll() is None:
            size = sum(p.stat().st_size for p in destination.rglob("*") if p.is_file()) if destination.exists() else 0
            if time.monotonic()-start>120 or size>MAX_CLONE_BYTES:
                if os.name=="nt":
                    subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                else:
                    process.kill()
                process.wait()
                raise ValueError("Clone exceeded the 120-second / 150 MB resource limit.")
            time.sleep(.3)
        if process.returncode:
            raise ValueError("Git clone failed. Verify Git installation, network, and token access.")
        if sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())>MAX_CLONE_BYTES:
            raise ValueError("Clone exceeded the 150 MB resource limit.")
        return destination,info["full_name"],info["default_branch"]
    except Exception:
        remove_workspace(destination)
        raise

def demo_workspace():
    destination = WORKSPACES / uuid.uuid4().hex
    shutil.copytree(ROOT/"demo/sample_repo",destination,ignore=shutil.ignore_patterns(".git","__pycache__", ".pytest_cache"))
    repo = Repo.init(destination)
    repo.index.add([str(p.relative_to(destination)) for p in destination.rglob("*.py")])
    from git import Actor
    actor=Actor("SPILL Demo","demo@spill.local")
    repo.index.commit("Initial trusted demonstration",author=actor,committer=actor)
    repo.close()
    return destination, "spill/demo-service", "master"

def snapshot(path):
    sources=read_sources(path)
    if not sources:
        raise ValueError("SPILL currently supports Python codebases. No supported Python files found.")
    with Repo(path) as repo:
        commit=repo.head.commit.hexsha
        data=build_graph(sources,history(repo))
    return commit,data

