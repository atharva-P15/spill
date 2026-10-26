import ast
import difflib
import inspect
import networkx as nx
from ml.graph import describe, network, candidates

MESSAGES = {
    "LOW": "Low estimated risk. No breaking changes detected by the available checks.",
    "MEDIUM": "Potential downstream impact detected. Review the highlighted dependencies and run relevant tests.",
    "HIGH": "Potential breaking change detected. One or more dependent files may fail."
}

def signatures(tree):
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

def callable_signature(node):
    a = node.args
    positional = a.posonlyargs + a.args
    defaults = [inspect.Parameter.empty] * (len(positional)-len(a.defaults)) + [None] * len(a.defaults)
    params = [inspect.Parameter(p.arg, inspect.Parameter.POSITIONAL_ONLY if i < len(a.posonlyargs)
                                else inspect.Parameter.POSITIONAL_OR_KEYWORD, default=defaults[i])
              for i,p in enumerate(positional)]
    if a.vararg:
        params.append(inspect.Parameter(a.vararg.arg, inspect.Parameter.VAR_POSITIONAL))
    params.extend(inspect.Parameter(p.arg, inspect.Parameter.KEYWORD_ONLY,
                                    default=None if d else inspect.Parameter.empty) for p,d in zip(a.kwonlyargs,a.kw_defaults))
    if a.kwarg:
        params.append(inspect.Parameter(a.kwarg.arg, inspect.Parameter.VAR_KEYWORD))
    return inspect.Signature(params)

def analyze_change(original, modified, changed, sources, data):
    old = ast.parse(original)
    old_info, new_info = describe(original), describe(modified)
    delta = list(difflib.unified_diff(original.splitlines(), modified.splitlines(), fromfile=changed, tofile=changed+" (proposed)", lineterm=""))
    summary = {"lines_added": sum(l.startswith("+") and not l.startswith("+++") for l in delta),
               "lines_removed": sum(l.startswith("-") and not l.startswith("---") for l in delta),
               "functions_added": sorted(set(new_info["functions"])-set(old_info["functions"])),
               "functions_removed": sorted(set(old_info["functions"])-set(new_info["functions"])),
               "signatures_changed": sorted(k for k in old_info["functions"].keys() & new_info["functions"].keys()
                                            if old_info["functions"][k] != new_info["functions"][k]),
               "imports_added": sorted(set(new_info["imports"])-set(old_info["imports"])),
               "imports_removed": sorted(set(old_info["imports"])-set(new_info["imports"])),
               "syntax_error": new_info["error"]}
    violations = []
    if new_info["error"]:
        violations.append({"file": changed, "reason": new_info["error"]})
        return {"risk":"HIGH", "summary":summary, "violations":violations, "diff":"\n".join(delta), "semantic_change":True}
    new = ast.parse(modified)
    def exports(tree):
        names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for n in tree.body:
            if isinstance(n, (ast.Assign, ast.AnnAssign)):
                for t in n.targets if isinstance(n, ast.Assign) else [n.target]:
                    names.update(x.id for x in ast.walk(t) if isinstance(x, ast.Name))
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names.update(a.asname or a.name.split(".")[0] for a in n.names)
        return names
    removed = exports(old) - exports(new)
    new_functions = signatures(new)
    for file, bindings in data["bindings"].items():
        try:
            tree = ast.parse(sources[file])
        except SyntaxError:
            continue
        for alias, (target, symbol) in bindings.items():
            if target != changed:
                continue
            if symbol in removed:
                violations.append({"file":file, "reason":f"Imports removed symbol {symbol} from {changed}."})
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == alias and symbol == "*" and node.attr in removed:
                    violations.append({"file":file, "reason":f"References removed symbol {node.attr}."})
                if not isinstance(node, ast.Call):
                    continue
                name = None
                if isinstance(node.func, ast.Name) and node.func.id == alias:
                    name = symbol
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == alias and symbol == "*":
                    name = node.func.attr
                if name not in new_functions or name not in summary["signatures_changed"]:
                    continue
                if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                    continue
                try:
                    callable_signature(new_functions[name]).bind(*([None]*len(node.args)), **{k.arg:None for k in node.keywords})
                except TypeError as e:
                    violations.append({"file":file, "reason":f"Call to {name} at line {node.lineno} is incompatible: {e}."})
    old_classes={n.name:ast.dump(n) for n in old.body if isinstance(n,ast.ClassDef)}
    new_classes={n.name:ast.dump(n) for n in new.body if isinstance(n,ast.ClassDef)}
    summary["classes_modified"] = sorted(k for k in old_classes.keys() | new_classes.keys() if old_classes.get(k)!=new_classes.get(k))
    semantic = ast.dump(old, include_attributes=False) != ast.dump(new, include_attributes=False)
    # Strip docstrings before comparison: literal module/function/class documentation has no runtime interface effect.
    class StripDocs(ast.NodeTransformer):
        def generic_visit(self,node):
            super().generic_visit(node)
            if isinstance(node,(ast.Module,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.body:
                if isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str):
                    node.body=node.body[1:]
            return node
    semantic = ast.dump(StripDocs().visit(old)) != ast.dump(StripDocs().visit(new))
    risk = "HIGH" if violations else ("MEDIUM" if semantic else "LOW")
    return {"risk":risk, "summary":summary, "violations":violations, "diff":"\n".join(delta), "semantic_change":semantic}

def predict(predictor, sources, data, changed, modified):
    result = analyze_change(sources[changed], modified, changed, sources, data)
    g = network(data)
    rows = []
    for path, score in predictor.rank(data, changed, candidates(data,changed)):
        reasons = []
        distance = None
        if nx.has_path(g,path,changed):
            route = nx.shortest_path(g,path,changed)
            distance = len(route)-1
            reasons.append("Directly imports the modified module." if distance == 1 else f"Transitive dependency via {' → '.join(route)}.")
        for edge in data["historical"]:
            if {edge["source"],edge["target"]} == {path,changed}:
                reasons.append(f"Changed together in {edge['count']} prior commits; supporting evidence, not a runtime dependency.")
        reasons.extend(v["reason"] for v in result["violations"] if v["file"] == path)
        risk = "HIGH" if any(v["file"] == path for v in result["violations"]) else ("MEDIUM" if result["semantic_change"] else "LOW")
        rows.append({"file":path, "score":round(score,6), "risk":risk, "distance":distance, "reasons":reasons})
    result.update({"changed_file":changed,"impacted_files":rows,"message":MESSAGES[result["risk"]],
                   "score_label":"Uncalibrated learned impact score (not a breaking probability)",
                   "risk_method":"Deterministic AST and compatibility checks",
                   "history_available":data["history_commits"]>0,"model_version":predictor.metadata["version"],
                   "direct_count":sum(r["distance"]==1 for r in rows),
                   "indirect_count":sum(r["distance"] is not None and r["distance"]>1 for r in rows)})
    return result

