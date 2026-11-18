from rl import *
s = wait(lambda s: s["authed"] and s["settings"] and s["view"]["state"], 50, "studio reconnected"); brief(s)
t0 = time.strftime('%H:%M:%S')
now = time.localtime(); m0 = now.tm_hour * 60 + now.tm_min
print("--- test plan"); act("plan_start", {"name": "Studio test", "list": [
    {"name": "M 33", "ra": 1.56286, "dec": 30.719128, "lp": False, "start_min": m0, "duration_min": 10}]})
s = wait(lambda s: s["plan"] and s["plan"]["state"] == "working" and s["view"]["stage"] in ("AutoGoto", "Stack", "AutoFocus"), 90, "plan working + view started")
print("     plan", s["plan"]["state"], [(i["target_name"], i["state"]) for i in s["plan"]["plan"]["list"]]); brief(s)
time.sleep(15)
print("--- stop plan"); act("plan_stop")
s = wait(lambda s: s["plan"] and s["plan"]["state"] in ("cancel", "complete") and s["view"]["state"] == "idle", 120, "plan stopped, view idle"); brief(s)
time.sleep(20); brief()
print("--- park"); act("park")
s = wait(lambda s: s["mount"].get("close") is True, 120, "parked"); brief(s)
log(45, t0)
