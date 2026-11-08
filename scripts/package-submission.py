"""Prepare an untagged, hashed source snapshot without committing or including secrets."""
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    listed = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT)
    root_files = {".dockerignore", ".env.example", ".gitignore", "AGENTS.md", "README.md", "Dockerfile", "compose.yaml"}
    directories = {"backend", "frontend", "simulator", "scripts", "docs", "config", "tests"}
    files = {}
    for name in sorted(set(listed.decode("utf-8").split("\0")) - {""}):
        relative = Path(name)
        if name not in root_files and relative.parts[0] not in directories:
            continue
        if any(part in {"node_modules", "__pycache__", ".pytest_cache", "dist", ".env", ".venv"} for part in relative.parts):
            continue
        source = ROOT / relative
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"Unexpected source path: {name}")
        files[name] = source.read_bytes()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    fingerprint = hashlib.sha256(encoded).hexdigest()
    folder = ROOT / "artifacts" / "submission" / ("m7-untagged-" + fingerprint[:12])
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / "source.zip"
    metadata = {"label": folder.name, "source_manifest_sha256": fingerprint,
                "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "git_tag": None, "status": "Untagged working-tree snapshot; Git-tag acceptance criterion pending",
                "files": len(files)}
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for name, data in sorted((files | {"SOURCE_MANIFEST.json": encoded,
                                         "SUBMISSION.json": (json.dumps(metadata, indent=2) + "\n").encode()}).items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, data)
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        for name, digest in manifest.items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == digest
    (folder / "SOURCE_MANIFEST.json").write_bytes(encoded)
    metadata["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (folder / "SUBMISSION.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive), **metadata}, indent=2))


if __name__ == "__main__":
    main()
