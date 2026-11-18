import json, time, urllib.request, urllib.error
B = "http://127.0.0.1:5599"
def get(p):
    return json.loads(urllib.request.urlopen(B + p, timeout=10).read())
def post(p, body):
    r = urllib.request.Request(B + p, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=25).read())
    except urllib.error.HTTPError as e:
        return {"http": e.code, **json.loads(e.read() or b"{}")}
fails = []
def act(a, p=None, expect=True):
    r = post("/api/action", {"action": a, "params": p or {}})
    ok = bool(r.get("ok"))
    flag = "" if ok == expect else "   <<<<< UNEXPECTED"
    if ok != expect: fails.append(a)
    err = r.get("error") or (r.get("reply") or {}).get("error") or ""
    print(f"  {a:18s} ok={ok!s:5} {r.get('method') or '':22s} code={r.get('code')} {err}{flag}")
    return r
def st(): return get("/api/state")
def wait(cond, t=20, label=""):
    end = time.time() + t
    while time.time() < end:
        s = st()
        if cond(s): return s
        time.sleep(1)
    fails.append("wait:" + label); print("   <<<<< TIMEOUT waiting for", label); return st()

s = wait(lambda s: s["authed"] and s["settings"], 25, "auth+settings")
print("auth", s["authed"], "| stage", s["view"], "| settings keys", len(s["settings"]), "| mount", s["mount"], "| wheel", s["wheel"],
      "| altaz", s["altaz"], "| level", s["level"], "| wifi", (s["wifi"] or {}).get("ssid"), "| video", s["video"])
print("--- camera / settings")
act("set_exposure", {"value": 20000}); act("set_gain", {"value": 120})
act("lp_filter", {"on": False}); act("wheel", {"pos": 2})
act("setting", {"key": "stack_dither", "value": {"pix": 30, "interval": 3, "enable": True}})
act("setting", {"key": "stack", "value": {"dbe": True}}); act("setting", {"key": "auto_af", "value": True})
act("setting", {"key": "lang", "value": "xx"}, expect=False)
act("dew_heater", {"on": True, "value": 80})
print("--- focus")
f0 = st()["focus"]["position"]
act("focus_move", {"step": 10}); act("focus_to", {"pos": 1700}); act("focus_to", {"pos": 99}, expect=False)
act("autofocus_start"); act("autofocus_stop")
print("--- mount")
act("tracking", {"on": False}); act("mount_move", {"speed": 500, "angle": 90, "dur_sec": 3}); act("mount_move", {"speed": 0, "angle": 0, "dur_sec": 0})
act("solve"); act("sync", {"ra": 5.5, "dec": -5.0}); act("slew", {"ra": 5.6, "dec": -5.4})
act("polar_align", expect=False)   # not in EQ mode
act("set_location", {"lat": 51.5, "lon": -0.13}); act("sync_time", {"tz": "Europe/London"}); act("play_sound", {"num": 80})
print("--- goto / stacking")
act("goto", {"target_name": "M 42", "ra": 5.588, "dec": -5.39, "lp": True, "mosaic": {"scale": 1.5, "angle": 30}})
s = wait(lambda s: s["view"]["stage"] == "AutoGoto", 12, "AutoGoto"); print("   stage", s["view"]["stage"], "target", s["target"]["name"])
s = wait(lambda s: s["view"]["stage"] == "Stack" and (s["stack"]["stacked_frame"] or 0) >= 1, 30, "Stack"); print("   stage", s["view"]["stage"], "frames", s["stack"]["stacked_frame"])
act("stop_stack")
s = wait(lambda s: s["view"]["stage"] == "ContinuousExposure", 12, "ContinuousExposure"); print("   stage", s["view"]["stage"], "video", s["video"])
# preview frames over the binary port
urllib.request.urlopen(B + "/api/video_frame", timeout=5).read()
s = wait(lambda s: s["video"]["live"], 20, "preview video live"); print("   video", s["video"])
fr = urllib.request.urlopen(B + "/api/video_frame", timeout=5).read(); print("   preview frame bytes", len(fr), fr[:2] == b"\xff\xd8")
act("start_stack", {"restart": True})
wait(lambda s: s["view"]["stage"] == "Stack", 12, "Stack again")
print("--- video modes")
act("start_view", {"mode": "moon", "target_name": "Moon", "ra": 3.2, "dec": 18.0})
wait(lambda s: s["view"]["stage"] == "AutoGoto", 10, "moon goto")
act("start_view", {"mode": "moon"})
s = wait(lambda s: s["view"]["stage"] == "RTSP", 12, "RTSP"); print("   stage", s["view"]["stage"], "mode", s["target"]["mode"])
try: urllib.request.urlopen(B + "/api/video_frame", timeout=5).read()
except Exception as e: print(e)
s = wait(lambda s: s["video"]["live"] and s["video"]["source"] == "video", 25, "rtsp video live"); print("   video", s["video"])
fr = urllib.request.urlopen(B + "/api/video_frame", timeout=5).read(); print("   video frame bytes", len(fr))
print("   snapshot", post("/api/snapshot", {}))
act("record_start", {"raw": False, "timelapse": 5}); act("record_stop"); act("scan_planet")
print("--- plan")
now = time.localtime(); m0 = now.tm_hour * 60 + now.tm_min
act("plan_start", {"name": "Test", "list": []}, expect=False)
act("plan_start", {"name": "Test night", "list": [
    {"name": "M 31", "ra": 0.712, "dec": 41.27, "lp": False, "start_min": m0, "duration_min": 10},
    {"name": "M 45", "ra": 3.79, "dec": 24.12, "lp": False, "start_min": m0 + 10, "duration_min": 9}]})
s = wait(lambda s: s["plan"] and s["plan"]["state"] == "working", 25, "plan working")
print("   plan", s["plan"]["state"], [(i["target_name"], i["state"]) for i in s["plan"]["plan"]["list"]], "target", s["target"]["name"])
s = wait(lambda s: s["plan"] and s["plan"]["plan"]["list"][1]["state"] in ("working", "complete"), 40, "plan 2nd target")
print("   plan", [(i["target_name"], i["state"]) for i in s["plan"]["plan"]["list"]], "target", s["target"]["name"])
act("plan_stop"); s = wait(lambda s: s["plan"] and s["plan"]["state"] == "cancel", 20, "plan cancel"); print("   plan state", s["plan"]["state"])
act("plan_clear"); s = wait(lambda s: not s["plan"], 20, "plan cleared"); print("   plan", s["plan"])
print("--- albums / park")
al = get("/api/albums")["albums"]; print("   albums", [a["name"] for a in al])
act("delete_image", {"names": [al[-1]["full"], al[-1]["thn"]]})
act("eq_mode", {"on": True}); s = wait(lambda s: s["mount"].get("equ_mode") is True, 12, "eq mode"); print("   mount", s["mount"])
act("polar_align"); s = wait(lambda s: "EqModePA" in s["ops"], 12, "PA event"); print("   PA", s["ops"].get("EqModePA"))
act("open_arm"); act("park")
s = wait(lambda s: s["mount"].get("close") is True and s["mount"].get("equ_mode") is True, 12, "parked (EQ mode kept)"); print("   mount", s["mount"], "view", s["view"])
s = st(); print("final: exp", s["settings"]["exp_ms"], "gain", s["exposure"]["gain"], "dither", s["settings"]["stack_dither"], "dbe", s["settings"]["stack"]["dbe"],
                "auto_af", s["settings"]["auto_af"], "focus", f0, "->", s["focus"]["position"], "tracking", s["tracking"], "loc", s["location"], "solve", bool(s["solve"]))
print("FAILS:", fails or "none")
