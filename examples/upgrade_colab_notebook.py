"""Export a clean English experiment notebook from the maintained template.

The legacy --source argument records provenance only. Local settings and source
cells are not migrated: review paths, model settings and RUN_LABEL in the export.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "notebooks"
    / "autonomous_modality_selection_iterative.ipynb"
)


def export_notebook(output: Path, source: Path | None = None) -> None:
    """Create an output-free template copy, preserving the source and prior outputs."""
    template_bytes = TEMPLATE.read_bytes()
    notebook: dict[str, Any] = copy.deepcopy(json.loads(template_bytes))
    metadata = notebook["metadata"]
    metadata.pop("widgets", None)
    metadata.pop("source_notebook_sha256", None)
    metadata["template_sha256"] = hashlib.sha256(template_bytes).hexdigest()
    metadata["export_protocol"] = "english-template-1.0"
    if source is not None:
        source_bytes = source.read_bytes()
        original = json.loads(source_bytes)
        if not isinstance(original, dict) or not isinstance(original.get("cells"), list):
            raise ValueError("Source must be a notebook JSON object with a cells list")
        metadata["source_notebook_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    for cell in notebook["cells"]:
        cell["metadata"] = {}
        if cell["cell_type"] == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(notebook, stream, ensure_ascii=False, indent=1)
        stream.write("\n")


def main() -> None:
    """Export the current English template without copying source notebook settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, help="Optional original notebook; hash-only provenance"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_notebook(args.output, args.source)
    print(f"Created {args.output}; source unchanged; outputs removed.")
    print("Review paths, model settings and RUN_LABEL. Source settings were not migrated.")


if __name__ == "__main__":
    main()
