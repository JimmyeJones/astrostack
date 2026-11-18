from rl import *
t0 = time.strftime('%H:%M:%S')
s = st(); print("wide_cam now:", s["settings"].get("wide_cam"), "| view raw:", json.dumps(rpc("get_view_state"))[:200])
eq = rpc("scope_get_equ_coord").get("result"); print("equ", eq)
print("--- sync (to current coords)"); act("sync", {"ra": eq["ra"], "dec": eq["dec"]}); time.sleep(3); print("     equ", rpc("scope_get_equ_coord").get("result"))
print("--- slew only"); act("slew", {"ra": (eq["ra"] + 0.2) % 24, "dec": eq["dec"] - 2}); time.sleep(20); print("     equ", rpc("scope_get_equ_coord").get("result")); brief()
print("--- dark frame"); act("dark_frame"); time.sleep(10); print("     ops", {k: v for k, v in st()["ops"].items() if "ark" in k}); act("dark_stop"); time.sleep(6)
print("--- polar align"); act("polar_align"); time.sleep(25); print("     PA", st()["ops"].get("EqModePA")); act("polar_align_stop"); time.sleep(8); brief()
log(45, t0)
