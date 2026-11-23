"""Verify the delivered files without modifying them. Run from any working directory."""
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[1]
lines=(ROOT/"SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
failed=[]
for line in lines:
    expected,relative=line.split("  ",1)
    path=(ROOT/relative).resolve()
    if not path.is_relative_to(ROOT): raise ValueError("Unsafe manifest path")
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected: failed.append(relative)
print("files",len(lines),"failed",len(failed))
if failed: raise SystemExit("Changed/missing files: "+", ".join(failed))
