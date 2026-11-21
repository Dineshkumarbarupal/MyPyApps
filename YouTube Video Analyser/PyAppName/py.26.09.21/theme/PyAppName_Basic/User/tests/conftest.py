import sys
from pathlib import Path
USER=Path(__file__).resolve().parents[1]
for folder in (USER/"py",USER/"db",USER/"core"/"py"):sys.path.insert(0,str(folder))
