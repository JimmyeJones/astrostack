import json, time, urllib.request, urllib.error
B = "http://127.0.0.1:5556"
def st(): return json.loads(urllib.request.urlopen(B + "/api/state", timeout=10).read())
def post(p, body):
    r = urllib.request.Request(B + p, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try: return json.loads(urllib.request.urlopen(r, timeout=30).read())
    except urllib.error.HTTPError as e: return {"http": e.code, **json.loads(e.read() or b"{}")}
def act(a, p=None):
    r = post("/api/action", {"action": a, "params": p or {}})
    rep = r.get("reply") or {}
    print(f"  {a:16s} {json.dumps(p or {})[:60]:60s} ok={r.get('ok')!s:5} {r.get('method') or '':20s} code={rep.get('code', r.get('code'))} {r.get('error') or rep.get('error') or ''} result={json.dumps(rep.get('result'))[:80]}")
    return r
def settle(f, want, label, t=25):
    end = time.time() + t
    while time.time() < end:
        v = f(st())
        if v == want: print(f"     -> {label} = {v}  CONFIRMED"); return True
        time.sleep(2)
    print(f"     -> {label} = {f(st())}  (wanted {want})  NOT CONFIRMED"); return False
s0 = st(); S = s0["settings"]
print("before: exp", S["exp_ms"], "lp", S["stack_lenhance"], "dither", S["stack_dither"], "dbe", S["stack"]["dbe"], "auto_af", S["auto_af"],
      "wheel", s0["wheel"], "focus", s0["focus"], "heater", s0["heater"], "gain", s0["exposure"]["gain"], "view", s0["view"], "mount", s0["mount"])
print("--- sound"); act("play_sound", {"num": 80})
print("--- exposure"); act("set_exposure", {"value": 10000}); settle(lambda s: s["settings"]["exp_ms"]["stack_l"], 10000, "stack_l")
act("set_exposure", {"value": 20000}); settle(lambda s: s["settings"]["exp_ms"]["stack_l"], 20000, "stack_l")
print("--- LP filter setting"); act("lp_filter", {"on": True}); settle(lambda s: s["settings"]["stack_lenhance"], True, "stack_lenhance")
act("lp_filter", {"on": False}); settle(lambda s: s["settings"]["stack_lenhance"], False, "stack_lenhance")
print("--- toggles")
act("setting", {"key": "auto_af", "value": False}); settle(lambda s: s["settings"]["auto_af"], False, "auto_af")
act("setting", {"key": "auto_af", "value": True}); settle(lambda s: s["settings"]["auto_af"], True, "auto_af")
act("setting", {"key": "stack", "value": {"dbe": False}}); settle(lambda s: s["settings"]["stack"]["dbe"], False, "stack.dbe")
act("setting", {"key": "stack", "value": {"dbe": True}}); settle(lambda s: s["settings"]["stack"]["dbe"], True, "stack.dbe")
d0 = S["stack_dither"]
act("setting", {"key": "stack_dither", "value": {"pix": 50, "interval": 3, "enable": True}}); settle(lambda s: s["settings"]["stack_dither"]["pix"], 50, "dither.pix")
act("setting", {"key": "stack_dither", "value": d0}); settle(lambda s: s["settings"]["stack_dither"], d0, "dither")
print("--- dew heater"); act("dew_heater", {"on": True, "value": 30}); settle(lambda s: s["heater"], True, "heater")
act("dew_heater", {"on": False, "value": 0}); settle(lambda s: s["heater"], False, "heater")
print("--- filter wheel"); w0 = s0["wheel"]
act("wheel", {"pos": 2}); settle(lambda s: s["wheel"], 2, "wheel")
act("wheel", {"pos": w0}); settle(lambda s: s["wheel"], w0, "wheel")
print("--- focus"); f0 = s0["focus"]["position"]
act("focus_to", {"pos": f0 + 10}); settle(lambda s: s["focus"]["position"], f0 + 10, "focus")
act("focus_to", {"pos": f0}); settle(lambda s: s["focus"]["position"], f0, "focus")
print("--- gain"); g0 = s0["exposure"]["gain"]
act("set_gain", {"value": g0})
print("--- location / clock")
loc = s0["location"]; act("set_location", {"lat": loc["lat"], "lon": loc["lon"]})
act("sync_time", {"tz": "America/New_York"})
s1 = st(); S = s1["settings"]
print("after : exp", S["exp_ms"], "lp", S["stack_lenhance"], "dither", S["stack_dither"], "dbe", S["stack"]["dbe"], "auto_af", S["auto_af"],
      "wheel", s1["wheel"], "focus", s1["focus"], "heater", s1["heater"], "view", s1["view"], "mount", s1["mount"], "loc", s1["location"])
for l in s1["log"][-25:]: print(l["t"], l["kind"], str(l["text"])[:170])
