import argparse
import copy
import hashlib
import json
import random
from pathlib import Path
import numpy as np
import torch
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, average_precision_score
from ml.graph import FEATURES, pair_features
from ml.model import GraphSAGE,tensors,Predictor

ROOT=Path(__file__).resolve().parents[1]

def metrics(labels,scores,groups):
    y=np.asarray(labels);s=np.asarray(scores);pred=s>=.5
    pk=[];rk=[]
    for yy,ss in groups:
        k=min(5,len(yy)); order=np.argsort(-np.asarray(ss))[:k]
        hits=sum(np.asarray(yy)[order])
        pk.append(float(hits/max(k,1)))
        if sum(yy):rk.append(float(hits/sum(yy)))
    return {"precision":float(precision_score(y,pred,zero_division=0)) if len(y) else None,
            "recall":float(recall_score(y,pred,zero_division=0)) if len(y) else None,
            "f1":float(f1_score(y,pred,zero_division=0)) if len(y) else None,
            "roc_auc":float(roc_auc_score(y,s)) if len(set(labels))==2 else None,
            "pr_auc":float(average_precision_score(y,s)) if len(set(labels))==2 else None,
            "precision_at_5":float(np.mean(pk)) if pk else None,"recall_at_5":float(np.mean(rk)) if rk else None,
            "pairs":len(y),"positives":int(y.sum())}

def evaluate(model,examples,mean,std,cold=False):
    collected={k:[[],[],[]] for k in ["graphsage","structural","historical"]}
    model.eval()
    with torch.no_grad():
        for e in examples:
            scores=torch.sigmoid(model(*tensors(e["graph"],e["changed"],e["candidates"],mean,std,cold))).tolist()
            px=pair_features(e["graph"],e["changed"],e["candidates"])
            for name,values in [("graphsage",scores),("structural",[p[1] for p in px]),
                                ("historical",[0 if cold else p[2] for p in px])]:
                dest=collected[name];dest[0].extend(e["labels"]);dest[1].extend(values);dest[2].append((e["labels"],values))
    return {name:metrics(*v) for name,v in collected.items()}

def train(dataset,epochs=60):
    random.seed(42);np.random.seed(42);torch.manual_seed(42)
    torch.use_deterministic_algorithms(True)
    examples=json.loads(dataset.read_text(encoding="utf-8"))
    splits={s:[e for e in examples if e["split"]==s] for s in ["train","validation","test","heldout"]}
    raw=np.asarray([n["features"] for e in splits["train"] for n in e["graph"]["nodes"]],dtype=np.float32)
    mean=raw.mean(0).tolist();std=np.maximum(raw.std(0),.1).tolist()
    model=GraphSAGE();optimizer=torch.optim.Adam(model.parameters(),lr=.001,weight_decay=.0001)
    best=-1;patience=0;best_state=None;trace=[]
    batches=[(tensors(e["graph"],e["changed"],e["candidates"],mean,std,cold),torch.tensor(e["labels"],dtype=torch.float32))
             for e in splits["train"] for cold in [False,True]]
    for epoch in range(epochs):
        model.train();random.shuffle(batches);losses=[]
        for batch,y in batches:
            optimizer.zero_grad()
            logits=model(*batch)
            # Unobserved pairs are uncertain negatives, assigned one quarter the positive weight.
            weights=torch.where(y>0,torch.ones_like(y),torch.full_like(y,.25))
            loss=(torch.nn.functional.binary_cross_entropy_with_logits(logits,y,reduction="none")*weights).mean()
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),2);optimizer.step()
            losses.append(float(loss.detach()))
        validation=evaluate(model,splits["validation"],mean,std)["graphsage"]
        score=validation["pr_auc"] or 0
        trace.append({"epoch":epoch+1,"loss":float(np.mean(losses)),"validation_pr_auc":score})
        print(trace[-1],flush=True)
        if score>best+1e-5:
            best=score;best_state=copy.deepcopy(model.state_dict());patience=0;best_epoch=epoch+1
        else:patience+=1
        if patience>=8:break
    model.load_state_dict(best_state)
    evaluation={s:evaluate(model,splits[s],mean,std) for s in ["validation","test","heldout"]}
    evaluation["cold_start_test"]=evaluate(model,splits["test"],mean,std,cold=True)
    digest=hashlib.sha256(dataset.read_bytes()).hexdigest()
    metadata={"version":"graphsage-"+digest[:10],"dataset_sha256":digest,"seed":42,"best_epoch":best_epoch,
              "training_examples":len(splits["train"]),"validation_selection":"PR-AUC, patience 8",
              "supervision":"Future modifications within three commits; weak proxy for impact, not confirmed failures.",
              "score":"Uncalibrated sigmoid score, not probability of breakage.",
              "evaluation":evaluation,"trace":trace}
    checkpoint={"weights":model.state_dict(),"feature_schema":FEATURES,"hidden":64,"mean":mean,"std":std,"metadata":metadata}
    out=ROOT/"ml/checkpoints";out.mkdir(exist_ok=True)
    torch.save(checkpoint,out/"graphsage.pt")
    (out/"evaluation.json").write_text(json.dumps(evaluation,indent=2),encoding="utf-8")
    (out/"metadata.json").write_text(json.dumps({**metadata,"feature_schema":FEATURES,"mean":mean,"std":std},indent=2),encoding="utf-8")
    reloaded=Predictor(out/"graphsage.pt")
    first=splits["test"][0]
    assert reloaded.rank(first["graph"],first["changed"],first["candidates"])
    print("Checkpoint saved and reloaded.",flush=True)
    print(json.dumps(evaluation["test"],indent=2),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--dataset",type=Path,default=ROOT/"ml/data/dataset.json")
    p.add_argument("--epochs",type=int,default=60)
    args=p.parse_args();train(args.dataset,args.epochs)

