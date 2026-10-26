"""Prepare chronological weak supervision without checking out or executing repository code."""
import argparse
import json
from pathlib import Path
from git import Repo
from ml.graph import allowed, build_graph, history, MAX_FILE

ROOT=Path(__file__).resolve().parents[1]
DEFAULTS=["click","flask","itsdangerous"]

def sources_at(commit):
    sources={}
    for blob in commit.tree.traverse():
        if blob.type=="blob" and blob.mode != 0o120000 and allowed(blob.path) and blob.size<=MAX_FILE:
            sources[blob.path]=blob.data_stream.read().decode("utf-8-sig",errors="replace")
    return sources

def prepare(paths, output, limit=300):
    examples=[]; manifests=[]
    for path in paths:
        with Repo(path) as repo:
            commits=list(reversed(list(repo.iter_commits(max_count=limit,first_parent=True))))
            timeline=history(repo,limit=limit)
            events={c["sha"]:c for c in timeline}
            manifests.append({"name":Path(path).name,"remote":next(iter(repo.remotes)).url if repo.remotes else "local",
                              "head":repo.head.commit.hexsha,"first":commits[0].hexsha,"commits":len(commits),
                              "license":"See original repository LICENSE; source is not redistributed in dataset."})
            counts={}
            for i in range(24,len(commits)-3,4):
                # A proposal at i uses the tree and history at i-1; the outcome window is i..i+2.
                base=commits[i-1]
                before=[events[c.hexsha] for c in commits[:i]]
                sources=sources_at(base)
                if len(sources)<3 or len(sources)>500:continue
                anchor=events[commits[i].hexsha]
                if len(anchor["files"])>30:continue
                future=set()
                for c in commits[i:i+3]:
                    event=events[c.hexsha]
                    if len(event["files"])<=30:future.update(event["files"])
                graph=None
                for changed in sorted(set(anchor["files"]) & set(sources))[:2]:
                    candidates=sorted(set(sources)-{changed})
                    labels=[int(p in future) for p in candidates]
                    if not any(labels):continue
                    if graph is None:graph=build_graph(sources,before)
                    split="train" if i<int(len(commits)*.6) else ("validation" if i<int(len(commits)*.8) else "test")
                    # Entire ItsDangerous repository is held out from optimization and selection.
                    if Path(path).name=="itsdangerous":split="heldout"
                    item={"repository":Path(path).name,"split":split,"base_commit":base.hexsha,
                          "base_timestamp":base.committed_date,"window":[c.hexsha for c in commits[i:i+3]],
                          "feature_commits":[c["sha"] for c in before],"changed":changed,
                          "candidates":candidates,"labels":labels,"graph":graph}
                    examples.append(item);counts[split]=counts.get(split,0)+1
            print(Path(path).name,counts,flush=True)
    if not all(any(e["split"]==s for e in examples) for s in ("train","validation","test")):
        raise RuntimeError("Insufficient chronological examples; supply repositories with more usable history.")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(examples),encoding="utf-8")
    manifest={"repositories":manifests,"window_commits":3,"stride":4,"warmup_commits":24,
              "labels":"Weak future modification labels, not observed runtime failures. Unobserved candidates are unlabeled controls with downweighted loss.",
              "splits":{s:sum(e["split"]==s for e in examples) for s in ["train","validation","test","heldout"]}}
    (output.parent/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(manifest["splits"]),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--repos",nargs="+",default=[str(ROOT/"ml/data/repos"/p) for p in DEFAULTS])
    parser.add_argument("--output",type=Path,default=ROOT/"ml/data/dataset.json")
    parser.add_argument("--limit",type=int,default=300)
    args=parser.parse_args()
    prepare(args.repos,args.output,args.limit)

