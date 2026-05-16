#!/usr/bin/env python3
"""班级投屏 - 统信UOS班级大屏一体机手机投屏软件入口"""

import sys
import os

# Ensure the project root is in the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from classroom_cast.app import run

if __name__ == "__main__":
    run()
