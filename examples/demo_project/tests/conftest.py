import sys
from pathlib import Path

# Make the src folder importable when running pytest from this demo folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
