"""Build deterministic APWorld and client-addon archives from current validated catalogs."""
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def write_archive(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        files = {path.relative_to(source.parent).as_posix(): path for path in source.rglob("*")
                 if path.is_file() and path.suffix in {".py", ".json", ".lua", ".toc"}
                 and "__pycache__" not in path.parts}
        for path in [ROOT / "LICENSE", ROOT / "THIRD_PARTY_NOTICES.md", *sorted((ROOT / "LICENSES").glob("*.txt"))]:
            files[f"{source.name}/{path.relative_to(ROOT).as_posix()}"] = path
        for name, path in sorted(files.items()):
            entry = zipfile.ZipInfo(name)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())
    temporary.replace(destination)
    print(f"Built {destination}")


def main():
    subprocess.run([sys.executable, str(ROOT / "tools/build_catalog.py"), "--check"], check=True)
    write_archive(ROOT / "apworld/wowpilago", ROOT / "dist/wowpilago.apworld")
    write_archive(ROOT / "addon/WoWPilago", ROOT / "dist/WoWPilago.zip")


if __name__ == "__main__":
    main()
