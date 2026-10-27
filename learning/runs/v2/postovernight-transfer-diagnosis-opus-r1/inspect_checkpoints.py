"""CPU-only safe (weights_only=True) deserialization; no forward passes, no gradients.
Measures which typed-embedding rows / global-input columns changed during D1 (i.e. ever
received gradient) and how far they moved during D2."""
import sys, json, hashlib, resource, torch, numpy
SAFE = [numpy._core.multiarray._reconstruct, numpy.ndarray, numpy.dtype, type(numpy.dtype("uint32")), type(numpy.dtype("int64")), type(numpy.dtype("float64")), type(numpy.dtype("uint64")), type(numpy.dtype("bool")), type(numpy.dtype("float32")), type(numpy.dtype("int32"))]
root = sys.argv[1]
P = {
 "pilot_initial": "learning/runs/v2/milestone3-D1-pilot-r1/checkpoint-000001-pilot_initial.pt",
 "pilot_end": "learning/runs/v2/milestone3-D1-pilot-r1/checkpoint-000004-candidate.pt",
 "D1_final": "learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt",
 "D2_entry": "learning/runs/v2/milestone3-D2-curriculum-r1/checkpoint-000010-candidate.pt",
 "D2_phase48": "learning/runs/v2/milestone3-D2-curriculum-r1/checkpoint-000016-candidate.pt",
 "D2_phase96": "learning/runs/v2/milestone3-D2-curriculum-r1/checkpoint-000022-candidate.pt",
}
def sha(p): return hashlib.sha256(open(f"{root}/{p}","rb").read()).hexdigest()
out = {"sha256": {k: sha(v) for k,v in P.items()}, "paths": P}
sd = {}
for k,p in P.items():
    with torch.serialization.safe_globals(SAFE):
        st = torch.load(f"{root}/{p}", map_location="cpu", weights_only=True)
    if k == "pilot_initial": out["top_level_keys"] = sorted(st.keys())
    m = st.get("model") or st.get("model_state") or st.get("model_state_dict")
    sd[k] = {n: t.clone() for n,t in m.items()}
    if k == "D2_phase96": out["param_names"] = [n for n in m]
names = out["param_names"]
emb = [n for n in names if "type_embedding" in n][0]
gp = [n for n in names if "global_projection" in n and n.endswith("weight")][0]
ep = [n for n in names if "entity_projection" in n and n.endswith("weight")][0]
def rowdiff(a, b, name, dim):
    d = (sd[b][name] - sd[a][name])
    if dim == 0: return [float(x) for x in d.norm(dim=1)]
    return [float(x) for x in d.norm(dim=0)]
pairs = [("pilot_initial","D1_final"),("D1_final","D2_entry"),("D2_entry","D2_phase48"),("D2_phase48","D2_phase96"),("D2_entry","D2_phase96")]
out["type_embedding_row_change_l2"] = {f"{a}->{b}": rowdiff(a,b,emb,0) for a,b in pairs}
out["type_embedding_row_norm"] = {k: [float(x) for x in sd[k][emb].norm(dim=1)] for k in P}
out["global_projection_column_change_l2"] = {f"{a}->{b}": rowdiff(a,b,gp,1) for a,b in pairs}
out["entity_projection_column_change_l2"] = {f"{a}->{b}": rowdiff(a,b,ep,1) for a,b in pairs}
out["D1_final_equals_D2_entry_all_params"] = all(torch.equal(sd["D1_final"][n], sd["D2_entry"][n]) for n in names)
out["total_param_change_l2"] = {f"{a}->{b}": float(sum(((sd[b][n]-sd[a][n]).float()**2).sum() for n in names)**0.5) for a,b in pairs}
out["max_rss_bytes_macos"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
json.dump(out, open(f"{root}/learning/runs/v2/postovernight-transfer-diagnosis-opus-r1/checkpoint-introspection.json","w"), indent=1)
r = lambda xs: [round(x,4) for x in xs]
print("keys", out["top_level_keys"]); print(emb, gp, ep)
for k,v in out["type_embedding_row_change_l2"].items(): print("emb", k, r(v))
for k,v in out["global_projection_column_change_l2"].items(): print("gcol", k, r(v))
for k,v in out["entity_projection_column_change_l2"].items(): print("ecol", k, r(v))
print("norms", {k: r(v) for k,v in out["type_embedding_row_norm"].items()})
print("equal", out["D1_final_equals_D2_entry_all_params"], out["total_param_change_l2"], out["max_rss_bytes_macos"])
