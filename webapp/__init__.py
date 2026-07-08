"""AstroStack web service — a headless, TrueNAS-friendly web layer around the
``seestack`` processing engine.

The engine (ingest, QC, plate-solve, stack) is reused unchanged; this package
adds a FastAPI server, a single-worker job manager, a folder watcher that
auto-runs the ingest→QC→solve pipeline, and a built React SPA.
"""

__version__ = "0.94.2"
