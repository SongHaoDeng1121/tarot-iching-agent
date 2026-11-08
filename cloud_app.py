"""Community Cloud entry point: forces private deployment defaults."""
import os
import runpy
from pathlib import Path

os.environ["APP_MODE"] = "cloud"
runpy.run_path(str(Path(__file__).with_name("web_app.py")), run_name="__main__")
