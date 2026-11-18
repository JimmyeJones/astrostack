import json, time, urllib.request, sys
B = "http://127.0.0.1:5599"
def get(p):
    return json.loads(urllib.request.urlopen(B + p, timeout=10).read())
def post(p, body, ctype="application/json", origin=None):
    h = {"Content-Type": ctype}
    if origin: h["Origin"] = origin
    r = urllib.request.Request(B + p, json.dumps(body).encode(), h)
    try:
        return json.loads(urllib.request.urlopen(r, timeout=25).read())
    except urllib.error.HTTPError as e:
        return {"http": e.code, **json.loads(e.read() or b"{}")}
def act(a, p=None):
    r = post("/api/action", {"action": a, "params": p or {}})
    print(f"  {a:16s} ok={r.get('ok')} method={r.get('method')} code={r.get('code')} {r.get('error','')}")
    return r
for i in range(20):
    try:
        s = get("/api/state")
        if s["authed"] and s["stack"]["stacked_frame"]: break
    except Exception as e: pass
    time.sleep(1)
s = get("/api/state")
print("connected", s["connected"], "authed", s["authed"], "demo", s["demo"], "target", s["target"], "stack", s["stack"])
print("power", s["power"], "loc", s["location"], "view", s["view"], "alerts", s["alerts"])
print("CSRF text/plain:", post("/api/action", {"action": "park"}, ctype="text/plain"))
print("CSRF bad origin:", post("/api/action", {"action": "park"}, origin="http://evil.example"))
print("actions:")
for a, p in [("set_gain", {"value": 120}), ("set_exposure", {"value": 20000}), ("lp_filter", {"on": False}),
             ("dew_heater", {"on": True, "value": 80}), ("focus_move", {"step": 10}), ("autofocus_start", None),
             ("autofocus_stop", None), ("mount_move", {"speed": 500, "angle": 90, "dur_sec": 3}),
             ("mount_move", {"speed": 0, "angle": 0, "dur_sec": 0}), ("save_image", None), ("dark_frame", None),
             ("goto", {"target_name": "M 42", "ra": 5.588, "dec": -5.39, "lp": True}), ("stop_goto", None)]:
    act(a, p)
print("rpc unknown:", post("/api/rpc", {"method": "nope"}))
time.sleep(12)
s = get("/api/state")
print("after: target", s["target"]["name"], "gain", s["exposure"]["gain"], "exp", s["exposure"]["exp_ms"], "lp", s["filter"], "heater", s["heater"], "focus", s["focus"], "view", s["view"], "stack", s["stack"])
print("image", s["image"])
img = urllib.request.urlopen(B + "/api/image?kind=thumb", timeout=10)
b = img.read(); print("thumb", img.status, img.headers["Content-Type"], len(b))
print("save_now", post("/api/save_now", {}))
print("captures", [c["file"] for c in get("/api/captures")["captures"]])
print("traversal", end=" ")
try: urllib.request.urlopen(B + "/api/capture?f=../data/last_state.json"); print("LEAK")
except urllib.error.HTTPError as e: print(e.code)
print("history pts", len(get("/api/history?h=1")["points"]))
print("albums", len(get("/api/albums")["albums"]))
print("low battery test:", post("/api/rpc", {"method": "sim_set", "params": {"battery": 8}}).get("ok"))
time.sleep(7)
print("alerts", get("/api/state")["alerts"])
