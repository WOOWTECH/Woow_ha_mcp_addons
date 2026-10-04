"""Loaded only by the private test subprocess environment."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from owned_network import install, install_subprocess_guard
    install()
    install_subprocess_guard()
except BaseException:
    # CPython otherwise logs a sitecustomize import error and continues startup.
    # A private sentinel that could not load must fail closed before target code.
    import os
    os._exit(121)
