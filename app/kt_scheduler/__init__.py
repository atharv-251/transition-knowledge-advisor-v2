"""KT Scheduler Bot package.

This package is intentionally separate from ``app.kt_tracker``. It follows
the same lightweight FastAPI/Pydantic/service-module style, but remains
loosely coupled so the current CSV/XLSX input source can later be replaced by
another bot/API without rewriting scheduling logic.
"""

