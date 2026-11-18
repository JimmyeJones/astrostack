from rl import *
t0 = time.strftime('%H:%M:%S'); brief()
print("--- open arm"); act("open_arm")
s = wait(lambda s: s["mount"].get("close") is False and s["mount"].get("move_type") in ("none", None), 90, "arm open"); brief(s)
print("--- short slew"); a0 = st()["altaz"]
act("mount_move", {"speed": 800, "angle": 0, "dur_sec": 3}); time.sleep(5)
act("mount_move", {"speed": 0, "angle": 0, "dur_sec": 0}); time.sleep(12)
a1 = st()["altaz"]; print("     altaz", a0, "->", a1)
act("mount_move", {"speed": 800, "angle": 90, "dur_sec": 3}); time.sleep(16)
print("     altaz ->", st()["altaz"])
print("--- tracking"); act("tracking", {"on": True}); wait(lambda s: s["tracking"] is True, 25, "tracking on")
act("tracking", {"on": False}); wait(lambda s: s["tracking"] is False, 25, "tracking off")
brief(); log(40, t0)
