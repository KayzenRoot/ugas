"""Materialize the v0.4.2 review evidence from one real pilot asset."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from ugas.master_assets import verify_asset_integrity


ROOT = Path(__file__).resolve().parents[2]
ASSET_ID = "asset-6802db1284dd4b4ba25c6987e5b26ddb"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def flatten(path: Path) -> Image.Image:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (196, 196, 196, 255))
    return Image.alpha_composite(background, rgba).convert("RGB")


def main() -> None:
    evidence_dir = ROOT / "docs" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    asset_path = ROOT / "tmp" / "assets" / ASSET_ID / "asset.json"
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    revisions = {item["revision_number"]: item for item in asset["revisions"]}
    if set(revisions) != {1, 2, 3, 4}:
        raise RuntimeError(f"expected R1-R4, got {sorted(revisions)}")

    def output(number: int) -> Path:
        path = Path(revisions[number]["output_path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    shutil.copy2(ROOT / "tmp" / "quality-benchmark" / "quality-benchmark-contact-sheet.png", evidence_dir / "quality-benchmark-contact-sheet.png")
    candidate_set_path = Path(asset["candidate_set"])
    candidates = json.loads(candidate_set_path.read_text(encoding="utf-8"))
    candidates["pilot_id"] = f"v0.4.2-{ASSET_ID}"
    write_json(candidate_set_path, candidates)
    write_json(evidence_dir / "candidates.json", candidates)

    shutil.copy2(output(1), evidence_dir / "master-selected-before-bg.png")
    shutil.copy2(output(2), evidence_dir / "master-selected-transparent.png")
    shutil.copy2(Path(revisions[2]["checkerboard_path"]), evidence_dir / "master-selected-checkerboard.png")
    shutil.copy2(output(4), evidence_dir / "reference-edit-transparent.png")
    shutil.copy2(Path(revisions[4]["checkerboard_path"]), evidence_dir / "reference-edit-checkerboard.png")

    before = flatten(output(2))
    with Image.open(output(3)) as after_source:
        after = after_source.convert("RGB")
    comparison = Image.new("RGB", (before.width * 2, before.height), (230, 230, 230))
    comparison.paste(before, (0, 0))
    comparison.paste(after, (before.width, 0))
    comparison.save(evidence_dir / "reference-edit-before-after.png", format="PNG")

    r1 = revisions[1]
    master_meta = json.loads(Path(r1["metadata_path"]).read_text(encoding="utf-8"))
    master_meta["evidence_role"] = "master-selected-before-bg"
    write_json(evidence_dir / "master-before-bg-removal.json", master_meta)

    integrity = verify_asset_integrity(ROOT, ASSET_ID)
    chain_revisions = []
    for number in range(1, 5):
        item = revisions[number]
        parent = revisions.get(number - 1)
        chain_revisions.append(
            {
                "revision_id": f"R{number}",
                "asset_revision_id": item["revision_id"],
                "revision_number": number,
                "immutable_output_path": item["output_path"],
                "output_path": item["output_path"],
                "archive_path": f"docs/evidence/{'master-selected-before-bg.png' if number == 1 else 'master-selected-transparent.png' if number == 2 else 'reference-edit-before-after.png' if number == 3 else 'reference-edit-transparent.png'}",
                "output_sha256": item["output_sha256"],
                "derived_from": None if parent is None else {"revision_id": f"R{number - 1}", "asset_revision_id": parent["revision_id"], "output_sha256": parent["output_sha256"]},
            }
        )
    chain = {
        "schema_version": "0.4.2",
        "asset_id": ASSET_ID,
        "chain": "R1 RGB -> R2 transparent -> R3 edited RGB -> R4 transparent",
        "revisions": chain_revisions,
        "r2_path_distinct_from_r4": revisions[2]["output_path"] != revisions[4]["output_path"],
        "r2_sha256_distinct_from_r4": revisions[2]["output_sha256"] != revisions[4]["output_sha256"],
        "revision_integrity": "PASS" if integrity["status"] == "REVISION_INTEGRITY_PASSED" else "FAIL",
        "integrity_evidence": {"status": integrity["status"], "checks": integrity["checks"], "failures": integrity["failures"], "production_ready_recomputed": integrity["production_ready_recomputed"]},
        "visual_approval": "pending",
    }
    write_json(evidence_dir / "revision-chain.json", chain)

    metadata = {
        "quality-benchmark-contact-sheet.png": ("quality-benchmark.json", None),
        "quality-benchmark.json": ("quality-benchmark.json", None),
        "master-selected-before-bg.png": ("master-before-bg-removal.json", "R1"),
        "master-selected-transparent.png": ("transparency-qa-master.json", "R2"),
        "master-selected-checkerboard.png": ("transparency-qa-master.json", "R2"),
        "reference-edit-before-after.png": ("reference-edit.json", "R3"),
        "reference-edit-transparent.png": ("transparency-qa-reference-edit.json", "R4"),
        "reference-edit-checkerboard.png": ("transparency-qa-reference-edit.json", "R4"),
        "revision-chain.json": ("revision-chain.json", None),
        "reference-edit-qa.json": ("reference-edit-qa.json", None),
        "transparency-qa-master.json": ("transparency-qa-master.json", "R2"),
        "transparency-qa-reference-edit.json": ("transparency-qa-reference-edit.json", "R4"),
    }
    items = []
    for archive_name, (metadata_name, revision_id) in metadata.items():
        source = evidence_dir / archive_name
        item = {"archive_name": archive_name, "source_path": f"docs/evidence/{archive_name}", "sha256": digest(source), "metadata_path": f"docs/evidence/{metadata_name}", "metadata_archive_name": metadata_name}
        if revision_id:
            item["revision_id"] = revision_id
        items.append(item)
    write_json(evidence_dir / "review-visuals.json", {"schema_version": "0.4.2", "asset_id": ASSET_ID, "images": items, "all_image_hashes": {item["archive_name"]: item["sha256"] for item in items}, "visual_review": "required", "human_approval": "pending"})


if __name__ == "__main__":
    main()
