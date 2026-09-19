"""Process-local launcher; no installation or changes to the legacy package."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "src"), str(HERE.parents[1] / "src")]

if __name__ == "__main__":
    from ams_evidence_views.cli import main

    main()
