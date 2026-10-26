"""Build the former optical-ablation entry point with current unified descriptions."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = runpy.run_path(str(ROOT / "scripts/build_selector_development_notebook.py"))
DESTINATION = "notebooks/autonomous_modality_selection_three_target_optical_description_dev.ipynb"


def build_notebook() -> dict[str, Any]:
    """Keep the previous selector with v2 questions and remove obsolete asset variants."""
    notebook = BASE["build_notebook"]()
    for cell in notebook["cells"]:
        source = "".join(cell["source"])
        if "TARGET_IDS = [16604" in source:
            source = source.replace(
                'SELECTOR_VARIANT = "updated"  # @param ["updated", "previous"]',
                'SELECTOR_VARIANT = "previous"  # Original selector; current asset descriptions.',
            ).replace(
                "three-target-v2-unified-descriptions-001",
                "three-target-v2-original-selector-unified-001",
            )
            cell["source"] = source.splitlines(keepends=True)
    notebook["cells"][0] = BASE["cell"](
        "# Three-target original-selector development run\n\n"
        "The former optical-description switch has been retired. All four modalities use "
        "the current shared descriptions. This entry point keeps v2 questions and the "
        "original selector, and runs Eminescu, Nampeyo and Thoreau. Use a new run label; "
        "historical result files remain unchanged.",
        "markdown",
    )
    return notebook


if __name__ == "__main__":
    target = ROOT / DESTINATION
    target.write_text(
        json.dumps(build_notebook(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(target)
