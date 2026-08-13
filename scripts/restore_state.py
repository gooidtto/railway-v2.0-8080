#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("usage: restore_state.py DATA_DIR BACKUP_ARCHIVE CONFIG")

root = Path(sys.argv[1]).resolve()
archive = Path(sys.argv[2]).resolve()
config = Path(sys.argv[3]).resolve()

if not archive.is_file():
    raise SystemExit("ERROR: backup archive not found")

with tempfile.TemporaryDirectory(prefix="restore-", dir=root) as tmp_name:
    tmp = Path(tmp_name)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        names = {m.name for m in members}
        if "manifest.json" not in names:
            raise SystemExit("ERROR: backup manifest missing")
        for member in members:
            target = (tmp / member.name).resolve()
            if not str(target).startswith(str(tmp) + os.sep):
                raise SystemExit("ERROR: unsafe backup path")
        tar.extractall(tmp)

    manifest = json.loads((tmp / "manifest.json").read_text())
    state_dir = tmp / "state"
    for name, meta in manifest["files"].items():
        source = tmp / name
        if not source.is_file():
            raise SystemExit(f"ERROR: missing backup file: {name}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            raise SystemExit(f"ERROR: checksum mismatch: {name}")

    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for source in sorted(state_dir.iterdir()):
        if source.name == "config.json":
            config.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            target = config
        else:
            target = root / source.name
        tmp_target = target.with_name(f".{target.name}.restore.tmp")
        shutil.copyfile(source, tmp_target)
        os.chmod(tmp_target, 0o600)
        os.replace(tmp_target, target)

print(f"state restore verified and applied: {archive.name}")
