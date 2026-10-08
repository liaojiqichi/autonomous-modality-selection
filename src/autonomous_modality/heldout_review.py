"""Contact sheets for explicit technical visual review, never model evidence."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from autonomous_modality.heldout import Cohort


def make_sheets(root: Path, output: Path) -> None:
    """Show two targets per sheet, preserving original images read-only."""
    cohort = Cohort.model_validate_json((root / "cohort.json").read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    for start in range(0, len(cohort.targets), 2):
        sheet = Image.new("RGB", (2200, 1100), "white")
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(cohort.targets[start : start + 2]):
            y = i * 550
            draw.text((10, y + 5), f"{row.id} {row.name}: original overview and DEM", fill="black")
            for name, box, x in [
                ("overview.png", (1650, 515), 0),
                ("dem_local.png", (550, 515), 1650),
            ]:
                with Image.open(root / "core-crops" / f"crater-{row.id}" / name) as im:
                    view = ImageOps.contain(im.convert("RGB"), box)
                    sheet.paste(view, (x, y + 30))
        sheet.save(output / f"core-{start // 2 + 1:02d}.png")
