"""Compatibility entry point for the expanded 15x15 schema checks."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('test_vision15.py')),run_name='__main__')
