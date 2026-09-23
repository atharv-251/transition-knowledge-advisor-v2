import os

import uvicorn
from dotenv import load_dotenv

# Load .env before importing/starting the app so module-level os.getenv()
# reads (e.g. app.kt_tracker.scheduler's KT_GRAPH_SYNC_ENABLED/KT_GRAPH_MODE)
# see values from .env instead of only real process environment variables.
load_dotenv()


def main():
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8088")),
        reload=False,
    )


if __name__ == "__main__":
    main()
