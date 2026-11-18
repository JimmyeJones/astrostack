from rl import *
s = wait(lambda s: s["authed"] and s["settings"] and s["view"]["state"], 50, "studio reconnected"); brief(s)
S = s["settings"]; print("settings: exp", S["exp_ms"], "lp", S["stack_lenhance"], "dither", S["stack_dither"], "auto_af", S["auto_af"], "wide_cam", S["wide_cam"], "gohome", S["viewplan_gohome"], "wheel", s["wheel"], "heater", s["heater"])
t0 = time.strftime('%H:%M:%S')
now = time.localtime(); m0 = now.tm_hour * 60 + now.tm_min
plan = {"name": "Plan", "list": [
    {"name": "M 33", "alias": "M 33", "ra": 1.56286, "dec": 30.719128, "lp": False, "start_min": m0, "duration_min": 1270 - m0},
    {"name": "M 45", "alias": "M 45", "ra": 3.778396, "dec": 24.160034, "lp": False, "start_min": 1270, "duration_min": 170, "mosaic": {"scale": 1.9, "angle": 0.0}},
    {"name": "IC 410", "alias": "IC 410", "ra": 5.379168, "dec": 33.413334, "lp": True, "start_min": 1440, "duration_min": 170},
    {"name": "IC 443", "alias": "IC 443", "ra": 6.276667, "dec": 22.516666, "lp": True, "start_min": 1610, "duration_min": 210}]}
act("plan_start", plan)
s = wait(lambda s: s["plan"] and s["plan"]["state"] == "working" and s["view"]["stage"] == "Stack" and (s["stack"]["stacked_frame"] or 0) >= 2, 600, "plan stacking M 33")
print("     plan", s["plan"]["state"], [(i["target_name"], i["state"], i["start_min"], i["duration_min"], i.get("mosaic")) for i in s["plan"]["plan"]["list"]]); brief(s)
log(14)
