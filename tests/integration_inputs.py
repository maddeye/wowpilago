"""Optional source/archive prerequisites, never a substitute for validation."""
from pathlib import Path
import unittest


def require_inputs(*paths):
    for value in paths:
        path = Path(value)
        try:
            path.lstat()
        except FileNotFoundError:
            raise unittest.SkipTest(f'Integration prerequisite missing: {path}')
        # Existing but unreadable, malformed, or dangling inputs must still fail.
        path.stat()
