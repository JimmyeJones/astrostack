from rl import *
t0 = time.strftime('%H:%M:%S')
print("--- goto M 33"); act("goto", {"target_name": "M 33", "ra": 1.56286, "dec": 30.719128, "lp": False})
s = wait(lambda s: s["view"]["stage"] not in (None,), 30, "view started"); brief(s)
s = wait(lambda s: s["view"]["stage"] == "Stack" and (s["stack"]["stacked_frame"] or 0) >= 2 and s["stack"]["state"] == "working", 420, "stacking 2+ frames"); brief(s)
log(60, t0)
print(json.dumps(rpc("get_view_state"))[:1500])
