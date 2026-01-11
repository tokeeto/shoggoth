#!/usr/bin/env python3
"""
Simple run script for Shoggoth PySide6 version
"""
import sys
from pathlib import Path

# Add the parent directory to Python path so we can import shoggoth modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Now we can import and run the Qt version
from shoggoth.main_qt import main

if __name__ == "__main__":
    main()