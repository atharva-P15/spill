"""Re-evaluate the saved checkpoint against its prepared chronological dataset."""
import json
from pathlib import Path
from ml.model import Predictor
from ml.train import evaluate
ROOT=Path(__file__).resolve().parents[1]

if __name__=="__main__":
    predictor=Predictor(ROOT/"ml/checkpoints/graphsage.pt")
    records=json.loads((ROOT/"ml/data/dataset.json").read_text(encoding="utf-8"))
    result={split:evaluate(predictor.model,[e for e in records if e["split"]==split],
                           predictor.mean,predictor.std)
            for split in ["validation","test","heldout"]}
    result["cold_start_test"]=evaluate(predictor.model,[e for e in records if e["split"]=="test"],
                                      predictor.mean,predictor.std,cold=True)
    (ROOT/"ml/checkpoints/evaluation.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

