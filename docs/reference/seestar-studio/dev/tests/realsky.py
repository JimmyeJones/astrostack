import json, time, urllib.request, urllib.error, sys
B="http://127.0.0.1:5556"
def get(p): return json.loads(urllib.request.urlopen(B+p,timeout=10).read())
def post(p,b):
    r=urllib.request.Request(B+p,json.dumps(b).encode(),{"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=30).read())
    except urllib.error.HTTPError as e: return {"http":e.code, **json.loads(e.read() or b"{}")}
end=time.time()+40
while time.time()<end:
    try:
        s=get("/api/state")
        if s["authed"] and s["settings"] and s["view"]["state"]: break
    except Exception: pass
    time.sleep(1)
print("view",s["view"],"mount",s["mount"],"sun",s["skyline"]["sun_alt"],"plan",(s["plan"] or {}).get("state"))
if len(sys.argv)>1 and sys.argv[1]=="start":
    print("start", post("/api/skyline",{"action":"start","max_alt":25}))
last=""; t0=time.time(); limit=float(sys.argv[2]) if len(sys.argv)>2 else 150
while time.time()-t0<limit:
    s=get("/api/state"); sc=s["skyline"]["scan"]
    line=f'{sc["state"]} {sc["step"]}/{sc["steps"]} wind={sc.get("wind")} sun={sc.get("sun_alt")} :: {sc["msg"]}'
    if line!=last: print(time.strftime("%H:%M:%S"), line, "| altaz", s["altaz"], "| view", s["view"]["stage"], "| wide", s["video_wide"]["live"], flush=True)
    last=line
    if sc["state"]!="running": break
    time.sleep(2)
print("--- log")
for l in get("/api/state")["log"][-45:]:
    if l["kind"]!="cmd" or "horiz" not in str(l["text"]): print("  ",l["t"],l["kind"],str(l["text"])[:170])
