"""Consumer project inspection with conservative, explainable heuristics."""

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectContext:
    root: str
    engine: str
    language: str
    dimension: str
    detected_files: list[str]
    confidence: str

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_project_context(root: Path, requested_dimension: str | None = None) -> ProjectContext:
    root = root.resolve()
    files = {p.name for p in root.iterdir()} if root.exists() else set()
    relative = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} if root.exists() else set()

    if "project.godot" in files:
        engine, language, confidence = "godot", "GDScript", "high"
    elif any(name.endswith(".uproject") for name in files):
        engine, language, confidence = "unreal", "C++/Blueprints", "high"
    elif "Assets/ProjectSettings/ProjectVersion.txt" in relative:
        engine, language, confidence = "unity", "C#", "high"
    elif "package.json" in files:
        engine, language, confidence = "web-or-custom", "JavaScript/TypeScript", "medium"
    elif "Cargo.toml" in files:
        engine, language, confidence = "custom", "Rust", "medium"
    elif "pyproject.toml" in files:
        engine, language, confidence = "custom", "Python", "medium"
    else:
        engine, language, confidence = "unknown", "unknown", "low"

    dimension = requested_dimension or ("2d" if engine == "godot" else "unknown")
    if dimension not in {"2d", "3d", "unknown"}:
        raise ValueError("dimension must be one of: 2d, 3d, unknown")
    return ProjectContext(
        root=str(root),
        engine=engine,
        language=language,
        dimension=dimension,
        detected_files=sorted(relative),
        confidence=confidence,
    )
