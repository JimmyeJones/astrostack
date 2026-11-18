import json, os, time, urllib.request, sys
B="http://127.0.0.1:5599"
def get(p): return json.loads(urllib.request.urlopen(B+p,timeout=10).read())
def post(p,b):
    r=urllib.request.Request(B+p,json.dumps(b).encode(),{"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=30).read())
    except urllib.error.HTTPError as e: return {"http":e.code, **json.loads(e.read() or b"{}")}
end=time.time()+30
while time.time()<end:
    s=get("/api/state")
    if s["authed"] and s["settings"]: break
    time.sleep(1)
print("view",s["view"],"mount",s["mount"])
if s["view"]["state"]=="working":
    print(post("/api/action",{"action":"stop_view","params":{}}).get("ok")); time.sleep(6)
if len(sys.argv)>1 and sys.argv[1]=="eq":
    print("eq", post("/api/action",{"action":"eq_mode","params":{"on":True}}).get("ok")); time.sleep(6)
print("start", post("/api/skyline",{"action":"start","max_alt":40}))
last=""; t0=time.time()
while time.time()-t0<1500:
    sc=get("/api/state")["skyline"]["scan"]
    line=f'{sc["state"]} {sc["step"]}/{sc["steps"]} wind={sc.get("wind")} max={sc.get("wind_max")} :: {sc["msg"]}'
    if sc["msg"]!=last and (sc["step"]%12==0 or "picture" not in sc["msg"]): print(round(time.time()-t0), line, flush=True)
    last=sc["msg"]
    if sc["state"]!="running": break
    time.sleep(1)
print("FINAL", line)
h=get("/api/horizon"); doc=h["horizon"]
if doc:
    import math
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    from seestar_sim import sim_horizon
    prof=doc["profile"]; errs=[abs(prof[a]-sim_horizon(a+0.5)) for a in range(360) if prof[a] is not None]
    print("known",doc["known_deg"],"hfov",doc["hfov"],"vfov",doc["vfov"],"shots",doc["shots"],"skipped",doc["skipped"],"max_turn",doc["max_turn"])
    errs.sort(); print("abs error deg: median %.2f  p90 %.2f  max %.2f"%(errs[len(errs)//2],errs[int(len(errs)*.9)],errs[-1]))
    print("camera", [[round(v,1) for v in r] for r in doc["camera"]])
s=get("/api/state"); print("after: view",s["view"],"mount",s["mount"])
for l in s["log"][-6:]: print("  ",l["t"],l["kind"],l["text"][:150])
