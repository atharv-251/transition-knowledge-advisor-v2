import os

import uvicorn


def main():
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8088")),
        reload=False,
    )


if __name__ == "__main__":
    main()
