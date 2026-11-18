# Seestar Studio — protocol reference for AstroStack's Seestar page

Supplied by the owner on 2026-11-18. **Seestar Studio** is his own local control
and monitoring app for his ZWO Seestar S30, built and verified against the real
scope on firmware 9.75. It is kept here as **reference material only**: it is not
imported, packaged or run by AstroStack. Read `AGENTS_GUIDE.md` first: it lists
what was verified on the real scope and what was not, and it describes the
skyline-scan incident. Read that incident before writing any code that moves the mount.

Left out on purpose: the interop key (`seestar.pem`, which must never be committed),
the reverse-engineering probes, the 3D model, the Windows launchers, and all of the
owner's data. The one location in `dev/tests/t2.py` was replaced with an example.

Ruff and pytest ignore this folder (`pyproject.toml`); it is not app code.
