import json, time, urllib.request, urllib.error
B = "http://127.0.0.1:5556"
def st(): return json.loads(urllib.request.urlopen(B + "/api/state", timeout=10).read())
def post(p, body, t=40):
    r = urllib.request.Request(B + p, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try: return json.loads(urllib.request.urlopen(r, timeout=t).read())
    except urllib.error.HTTPError as e: return {"http": e.code, **json.loads(e.read() or b"{}")}
    except Exception as e: return {"exc": str(e)}
def act(a, p=None):
    r = post("/api/action", {"action": a, "params": p or {}})
    rep = r.get("reply") or {}
    print(f"  {time.strftime('%H:%M:%S')} {a:14s} {json.dumps(p or {})[:70]:70s} ok={r.get('ok')!s:5} {r.get('method') or '':20s} code={rep.get('code', r.get('code'))} {r.get('error') or rep.get('error') or r.get('exc') or ''} res={json.dumps(rep.get('result'))[:90]}", flush=True)
    return r
def rpc(m, p=None):
    b = {"method": m}
    if p is not None: b["params"] = p
    return (post("/api/rpc", b).get("reply") or {})
def wait(cond, t, label):
    end = time.time() + t
    while time.time() < end:
        s = st()
        try:
            if cond(s): print(f"     -> {label}: OK", flush=True); return s
        except Exception: pass
        time.sleep(2)
    print(f"     -> {label}: TIMEOUT", flush=True); return st()
def brief(s=None):
    s = s or st()
    print("     state: view", s["view"], "| mount", s["mount"], "| trk", s["tracking"], "| altaz", s["altaz"], "| radec", round(s["target"]["ra"] or 0, 3), round(s["target"]["dec"] or 0, 2),
          "| tgt", s["target"]["name"], "| stack", s["stack"]["state"], s["stack"]["stacked_frame"], "| bat", s["power"]["battery"], "| video", s["video"], flush=True)
def log(n=25, since=None):
    for l in st()["log"][-n:]:
        if since and l["t"] < since: continue
        print("    ", l["t"], l["kind"], str(l["text"])[:200], flush=True)
