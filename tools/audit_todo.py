"""Keep TODO checkmarks tied to named, inspectable evidence records."""

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def requirements(text):
    section = ""
    result = []
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:]
        match = re.fullmatch(r"- \[([ xX])\] (.+)", line)
        if match:
            description = match[2]
            identity = hashlib.sha256(description.encode()).hexdigest()[:12]
            result.append({"id": identity, "section": section, "text": description, "checked": match[1] != " "})
    if len({entry["id"] for entry in result}) != len(result):
        raise ValueError("Duplicate TODO requirement descriptions")
    return result


def audit(todo, evidence, root):
    entries = requirements(todo)
    known = {entry["id"] for entry in entries}
    errors = []
    for identity, record in evidence.items():
        if identity not in known:
            errors.append(f"Unknown requirement {identity}")
        if record.get("status") == "verified":
            artifacts = record.get("artifacts", [])
            if not artifacts or not record.get("verification"):
                errors.append(f"{identity} has no verification command or artifact")
            for artifact in artifacts:
                path = root / artifact
                if not path.is_file():
                    errors.append(f"{identity} missing artifact {artifact}")
    for entry in entries:
        verified = evidence.get(entry["id"], {}).get("status") == "verified"
        if entry["checked"] and not verified:
            errors.append(f"Checked without verified evidence: {entry['id']} {entry['text']}")
    return entries, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Set checkmarks from verified evidence, leave everything else open")
    args = parser.parse_args()
    path = ROOT / "TODO.md"
    text = path.read_text()
    evidence_path = ROOT / "docs" / "requirements-evidence.json"
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    entries, errors = audit(text, evidence, ROOT)
    if args.apply and errors:
        raise SystemExit("Refusing to change TODO.md with invalid evidence: " + "; ".join(errors))
    if args.apply:
        verified = {identity for identity, record in evidence.items() if record.get("status") == "verified"}
        lines = []
        for line in text.splitlines(keepends=True):
            match = re.fullmatch(r"- \[([ xX])\] (.+?)(\n?)", line)
            if match:
                identity = hashlib.sha256(match[2].encode()).hexdigest()[:12]
                line = f"- [{'x' if identity in verified else ' '}] {match[2]}{match[3]}"
            lines.append(line)
        path.write_text("".join(lines))
        entries, errors = audit(path.read_text(), evidence, ROOT)
    report = {"total": len(entries), "verified": sum(entry["checked"] for entry in entries),
              "remaining": [entry for entry in entries if not entry["checked"]], "errors": errors}
    (ROOT / "docs" / "requirements-status.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['verified']}/{report['total']} verified requirements")
    for error in errors:
        print(error)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
