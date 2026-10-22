"""Build the three internal submission ZIPs. Never place them in candidate/."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.examples import build_examples

if __name__ == '__main__':
    print(json.dumps(build_examples(), ensure_ascii=False, indent=2))
