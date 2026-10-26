"""Static graphs and bounded history; importer -> imported module."""
import ast
import itertools
import math
from collections import Counter
from pathlib import Path
import networkx as nx

IGNORE = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build"}
MAX_FILE = 256_000
MAX_FILES = 1200
FEATURES = ["log_loc", "log_functions", "log_classes", "log_imports", "log_dependents",
            "log_dependencies", "log_complexity", "history_frequency", "history_available"]

def allowed(path):
    p = Path(path)
    return p.suffix == ".py" and not (set(p.parts) & IGNORE)

def read_sources(root):
    root = Path(root).resolve()
    sources = {}
    for p in root.rglob("*.py"):
        if not allowed(p.relative_to(root)) or p.is_symlink() or not p.resolve().is_relative_to(root):
            continue
        if p.stat().st_size <= MAX_FILE:
            sources[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8-sig", errors="replace")
        if len(sources) > MAX_FILES:
            raise ValueError(f"Repository exceeds {MAX_FILES} Python files.")
    return sources

def parse(source):
    return ast.parse(source)

def module_name(path):
    parts = path.removesuffix(".py").split("/")
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)

def describe(source):
    try:
        tree = parse(source)
    except SyntaxError as e:
        return {"error": f"Line {e.lineno}: {e.msg}", "functions": {}, "classes": [], "imports": [], "complexity": 0}
    functions = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[n.name] = ast.unparse(n.args)
    return {"error": None, "functions": functions,
            "classes": [n.name for n in tree.body if isinstance(n, ast.ClassDef)],
            "imports": [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))],
            "complexity": sum(isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.IfExp, ast.Match)) for n in ast.walk(tree))}

def build_graph(sources, commits=None):
    commits = commits or []
    modules = {module_name(p): p for p in sources}
    # Non-src standalone scripts inside a directory can resolve sibling imports.
    graph = nx.DiGraph()
    details = {p: describe(s) for p, s in sources.items()}
    graph.add_nodes_from(sources)
    bindings = {p: {} for p in sources}
    for path, source in sources.items():
        try:
            tree = parse(source)
        except SyntaxError:
            continue
        current = module_name(path)
        package = current if path.endswith("__init__.py") else current.rpartition(".")[0]
        def resolve(name):
            return modules.get(name) or modules.get((package + "." + name).strip("."))
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for alias in n.names:
                    target = resolve(alias.name)
                    if target and target != path:
                        graph.add_edge(path, target)
                        bindings[path][alias.asname or alias.name.split(".")[0]] = [target, "*"]
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    parts = package.split(".") if package else []
                    if n.level > len(parts) + 1:
                        continue
                    base = ".".join(parts[:len(parts) - n.level + 1] + ([base] if base else []))
                for alias in n.names:
                    child = resolve((base + "." + alias.name).strip("."))
                    target = child or resolve(base)
                    if target and target != path:
                        graph.add_edge(path, target)
                        bindings[path][alias.asname or alias.name] = [target, "*" if child else alias.name]
    freq, pairs = Counter(), Counter()
    useful = 0
    for c in commits:
        paths = sorted(set(c["files"]) & set(sources))
        if not paths or len(paths) > 30 or c.get("initial"):
            continue
        useful += 1
        freq.update(paths)
        pairs.update(itertools.combinations(paths, 2))
    historical = [{"source": a, "target": b, "count": count,
                   "weight": count / math.sqrt(freq[a] * freq[b])}
                  for (a, b), count in pairs.items() if count >= 2]
    nodes = []
    for p in sorted(sources):
        d = details[p]
        values = [len(sources[p].splitlines()), len(d["functions"]), len(d["classes"]),
                  len(d["imports"]), graph.in_degree(p), graph.out_degree(p), d["complexity"]]
        nodes.append({"id": p, "features": [math.log1p(v) for v in values] +
                      [freq[p] / max(useful, 1), float(useful > 0)], **d})
    return {"nodes": nodes, "edges": [{"source": a, "target": b, "kind": "import"} for a, b in sorted(graph.edges)],
            "historical": historical, "bindings": bindings, "history_commits": useful,
            "commits_scanned": len(commits), "feature_schema": FEATURES}

def history(repo, ref="HEAD", limit=250):
    result = []
    for c in repo.iter_commits(ref, max_count=limit, first_parent=True):
        if not c.parents:
            result.append({"sha": c.hexsha, "timestamp": c.committed_date, "files": [], "initial": True})
            continue
        paths = [d.b_path or d.a_path for d in c.parents[0].diff(c) if allowed(d.b_path or d.a_path)]
        result.append({"sha": c.hexsha, "timestamp": c.committed_date, "files": paths, "initial": False})
    return list(reversed(result))

def network(data):
    g = nx.DiGraph()
    g.add_nodes_from(n["id"] for n in data["nodes"])
    g.add_edges_from((e["source"], e["target"]) for e in data["edges"])
    return g

def pair_features(data, changed, candidates):
    g = network(data)
    distances = nx.single_source_shortest_path_length(g.reverse(), changed)
    hist = {frozenset((e["source"], e["target"])): e["weight"] for e in data["historical"]}
    features = []
    for p in candidates:
        distance = distances.get(p, 0)
        common = len(set(g.successors(p)) & set(g.successors(changed)))
        features.append([float(distance == 1), 1 / distance if distance else 0,
                         hist.get(frozenset((p, changed)), 0), math.log1p(common)])
    return features

def candidates(data, changed):
    g = network(data)
    result = set(nx.ancestors(g, changed))
    for e in data["historical"]:
        if changed in (e["source"], e["target"]):
            result.update([e["source"], e["target"]])
    return sorted(result - {changed})

