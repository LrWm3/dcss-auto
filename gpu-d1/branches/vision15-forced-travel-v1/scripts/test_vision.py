"""Compatibility entry point for the forced-travel checks."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name("test_forced_travel.py")), run_name="__main__")
