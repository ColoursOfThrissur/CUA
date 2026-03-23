"""Launch the CUA API server in non-reload mode for unattended autonomy runs."""
from __future__ import annotations

import os

import uvicorn

from api.server import app
from core.config_manager import get_config


def main():
    config = get_config()
    os.environ["CUA_RELOAD_MODE"] = "0"
    uvicorn.run(app, host=config.api.host, port=config.api.port, log_level="info", reload=False)


if __name__ == "__main__":
    main()
