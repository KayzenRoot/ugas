"""Build deterministic, test-only asymmetric direction identities for review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from ugas.direction_runtime import CANONICAL_DIRECTIONS


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/multi-direction-runtime-v0160"
FIXTURES = OUT / "synthetic-fixtures"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(direction: str, index: int) -> Image.Image:
    image = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = ((37 * (index + 2)) % 220 + 20, (71 * (index + 3)) % 220 + 20, (113 * (index + 4)) % 220 + 20, 255)
    # The intentionally off-centre fin, notch and direction index make every
    # identity asymmetric and distinguishable without representing real art.
    draw.ellipse((35, 28, 125, 130), fill=color, outline=(255, 255, 255, 255), width=3)
    draw.polygon([(80, 18), (103 + index, 48), (80, 40), (57, 48)], fill=(255, 220, 60, 255))
    draw.polygon([(106, 88), (145, 100 + index), (112, 116), (96, 101)], fill=(230, 65, 65, 255))
    draw.rectangle((42 + index, 106, 55 + index, 122), fill=(35, 35, 35, 255))
    draw.text((8, 138), f"{index}:{direction}", fill=(255, 255, 255, 255))
    return image


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, direction in enumerate(CANONICAL_DIRECTIONS):
        path = FIXTURES / f"fixture-{index:02d}-{direction}.png"
        _fixture(direction, index).save(path, format="PNG", optimize=False)
        entries.append({"fixture_id": f"TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE-{direction}", "direction": direction, "path": path.relative_to(ROOT).as_posix(), "sha256": _digest(path), "synthetic_fixture": True, "production_registry": False})

    sheet = Image.new("RGBA", (640, 480), (26, 31, 43, 255))
    for index, entry in enumerate(entries):
        with Image.open(ROOT / entry["path"]) as fixture:
            tile = fixture.convert("RGBA").resize((160, 160), Image.Resampling.NEAREST)
            x, y = (index % 4) * 160, (index // 4) * 240
            sheet.alpha_composite(tile, (x, y))
            ImageDraw.Draw(sheet).text((x + 8, y + 170), entry["direction"], fill=(255, 255, 255, 255))
    sheet_path = OUT / "synthetic-direction-contact-sheet-v0160.png"
    sheet.save(sheet_path, format="PNG", optimize=False)
    manifest = {"schema_version": "0.16.0", "manifest_type": "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE", "production_registry": False, "direction_count": len(entries), "unique_identity_count": len({entry["sha256"] for entry in entries}), "fixtures": entries, "contact_sheet": {"path": sheet_path.relative_to(ROOT).as_posix(), "sha256": _digest(sheet_path)}, "non_production_assertion": "never copied into providers or production asset registry"}
    (OUT / "synthetic-fixture-manifest-v0160.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE_BUILT", "direction_count": len(entries), "unique_identity_count": manifest["unique_identity_count"], "contact_sheet": manifest["contact_sheet"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
