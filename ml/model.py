"""Two relation-aware mean GraphSAGE layers, implemented in CPU PyTorch."""
import torch
from torch import nn
from ml.graph import FEATURES, pair_features
torch.set_num_threads(2)

class SageLayer(nn.Module):
    def __init__(self, inputs, outputs):
        super().__init__()
        self.linear = nn.Linear(inputs * 3, outputs)

    def forward(self, x, structural, historical):
        return self.linear(torch.cat([x, structural @ x, historical @ x], dim=1))

class GraphSAGE(nn.Module):
    def __init__(self, inputs=len(FEATURES), hidden=64):
        super().__init__()
        self.sage1 = SageLayer(inputs, hidden)
        self.sage2 = SageLayer(hidden, hidden)
        self.dropout = nn.Dropout(0.2)
        self.head = nn.Sequential(nn.Linear(hidden * 3 + 4, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 1))

    def forward(self, x, structural, historical, pairs, pair_x):
        h = self.dropout(torch.relu(self.sage1(x, structural, historical)))
        h = torch.relu(self.sage2(h, structural, historical))
        a, b = h[pairs[:, 0]], h[pairs[:, 1]]
        return self.head(torch.cat([a, b, torch.abs(a-b), pair_x], dim=1)).squeeze(-1)

def tensors(data, changed, candidates, mean, std, cold=False):
    ids = [n["id"] for n in data["nodes"]]
    index = {p: i for i, p in enumerate(ids)}
    x = torch.tensor([n["features"] for n in data["nodes"]], dtype=torch.float32)
    if cold:
        x[:, -2:] = 0
    x = (x - torch.tensor(mean)) / torch.tensor(std)
    structural = torch.zeros((len(ids), len(ids)))
    historical = torch.zeros_like(structural)
    for edge in data["edges"]:
        a, b = index[edge["source"]], index[edge["target"]]
        structural[a,b] = structural[b,a] = 1
    if not cold:
        for edge in data["historical"]:
            a,b = index[edge["source"]], index[edge["target"]]
            historical[a,b] = historical[b,a] = edge["weight"]
    structural = structural / structural.sum(1, keepdim=True).clamp(min=1)
    historical = historical / historical.sum(1, keepdim=True).clamp(min=1)
    pairs = torch.tensor([[index[changed], index[p]] for p in candidates], dtype=torch.long).reshape(-1,2)
    px = torch.tensor(pair_features(data, changed, candidates), dtype=torch.float32).reshape(-1,4)
    if cold:
        px[:,2] = 0
    return x, structural, historical, pairs, px

class Predictor:
    def __init__(self, path):
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        if checkpoint["feature_schema"] != FEATURES:
            raise ValueError("Model feature schema mismatch; retrain the model.")
        self.model = GraphSAGE(hidden=checkpoint["hidden"])
        self.model.load_state_dict(checkpoint["weights"])
        self.model.eval()
        self.metadata = checkpoint["metadata"]
        self.mean, self.std = checkpoint["mean"], checkpoint["std"]

    def rank(self, data, changed, candidates):
        if not candidates:
            return []
        with torch.no_grad():
            scores = torch.sigmoid(self.model(*tensors(data, changed, candidates, self.mean, self.std))).tolist()
        return sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)

