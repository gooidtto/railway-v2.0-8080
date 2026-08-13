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

# Extract outside DATA_DIR so the temporary extraction tree can never be
# confused with the destination state and so a restore cannot accidentally
# consume its own temporary files.
with tempfile.TemporaryDirectory(prefix="restore-state-") as tmp_name:
    tmp = Path(tmp_name)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        names = {m.name for m in members}
        if "manifest.json" not in names:
            raise SystemExit("ERROR: backup manifest missing")
        for member in members:
            if member.issym() or member.islnk():
                raise SystemExit("ERROR: links are not allowed in backup")
            target = (tmp / member.name).resolve()
            if not str(target).startswith(str(tmp) + os.sep):
                raise SystemExit("ERROR: unsafe backup path")
        tar.extractall(tmp)

    manifest = json.loads((tmp / "manifest.json").read_text())
    state_dir = tmp / "state"
    if not state_dir.is_dir():
        raise SystemExit("ERROR: backup state directory missing")

    for name, meta in manifest["files"].items():
        source = tmp / name
        if not source.is_file():
            raise SystemExit(f"ERROR: missing backup file: {name}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            raise SystemExit(f"ERROR: checksum mismatch: {name}")

    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    config.parent.mkdir(mode=0o755, parents=True, exist_ok=True)

    restored_targets = []
    for name in manifest["files"]:
        source = tmp / name
        if source.name == "config.json":
            target = config
        else:
            target = root / source.name
        tmp_target = target.with_name(f".{target.name}.restore.tmp")
        shutil.copyfile(source, tmp_target)
        os.chmod(tmp_target, 0o600)
        os.replace(tmp_target, target)
        restored_targets.append(target)

    if not restored_targets:
        raise SystemExit("ERROR: backup contains no restorable state")

print(f"state restore verified and applied: {archive.name}")
