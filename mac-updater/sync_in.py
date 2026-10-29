"""Mac side of the code sync, run at the start of every update (run.py): picks up new features and fixes that Claude
threads made in the cloud copy, so the Mac runs the same code.

1. Self-update: the updater's own scripts from the branch (mac-updater/*.py, *.sh, requirements.txt).
2. Every pack in the branch's sync/index.json newer than the last one applied: download its parts, check the
   sha256, decrypt with SYNC_PASS (settings.env), and copy the files into project/ (files marked missing-only are
   copied only if the Mac doesn't have them; the Mac's own logs and run outputs are never in the pack).
3. Paths written for the cloud (/mnt/project-files) are pointed at this Mac's project folder.
Nothing here ever stops the update: on any problem it prints why and the run carries on with the current copy.
Usage: python sync_in.py
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent
UPD, PROJ, LOGS = HOME / "updater", HOME / "project", HOME / "logs"
RAW = "https://raw.githubusercontent.com/Aledoij/Aibet/claude/project-thread-5w024f/"
SELF = ["fetch_news.py", "ufc_upcoming.py", "run.py", "run.sh", "nfl_refresh.py", "publish.sh", "schedule.py", "install.sh",
        "sync_in.py", "requirements.txt", "README.md"]


def get(path, timeout=120):
    req = urllib.request.Request(RAW + path, headers={"Cache-Control": "no-cache"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def fix_paths(p):
    if p.suffix in (".py", ".sh"):
        t = p.read_text(errors="ignore")
        if "/mnt/project-files" in t:
            p.write_text(t.replace("/mnt/project-files", str(PROJ)))


def self_update():
    changed = []
    for f in SELF:
        try:
            new = get("mac-updater/" + f)
        except Exception:  # noqa: BLE001  (e.g. requirements.txt not there yet)
            continue
        old = (UPD / f).read_bytes() if (UPD / f).exists() else b""
        if new and new != old:
            (UPD / f).write_bytes(new)
            if f.endswith(".sh"):
                os.chmod(UPD / f, 0o755)
            changed.append(f)
    if "requirements.txt" in changed:
        r = subprocess.run(["uv", "pip", "install", "--python", sys.executable, "-q", "-r", str(UPD / "requirements.txt")])
        print("packages updated" if r.returncode == 0 else "package update failed")
    print("updater scripts updated:", ", ".join(changed) if changed else "none")


def apply_pack(pk, pw):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        enc = td / "pack.enc"
        with open(enc, "wb") as out:
            for i in range(pk["parts"]):
                out.write(get(f"sync/{pk['version']}.part{i:02d}", timeout=600))
        if hashlib.sha256(enc.read_bytes()).hexdigest() != pk["sha256"]:
            raise RuntimeError("download check failed")
        r = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-md", "sha256", "-pass", f"pass:{pw}",
                            "-in", str(enc), "-out", str(td / "pack.tar.xz")], capture_output=True)
        if r.returncode:
            raise RuntimeError("could not decrypt (wrong SYNC_PASS?)")
        missing_only, n = set(pk.get("missing_only", [])), 0
        with tarfile.open(td / "pack.tar.xz") as t:
            for m in t.getmembers():
                if not m.isfile() or m.name.startswith("/") or ".." in Path(m.name).parts:
                    continue
                dest = PROJ / m.name
                if m.name in missing_only and dest.exists():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with t.extractfile(m) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                fix_paths(dest)
                n += 1
    return n


def code_sync():
    pw = os.environ.get("SYNC_PASS", "")
    if not pw:
        print("code sync: no SYNC_PASS in settings.env, skipped")
        return
    idx = json.loads(get("sync/index.json"))
    stamp = LOGS / "code_sync_version.txt"
    have = stamp.read_text().strip() if stamp.exists() else ""
    todo = [pk for pk in idx["packs"] if pk["version"] > have]
    if not todo:
        print(f"code sync: up to date ({have})")
        return
    for pk in todo:  # in order; stop at the first problem so a later pack never lands on a missing one
        n = apply_pack(pk, pw)
        stamp.write_text(pk["version"] + "\n")
        print(f"code sync: pack {pk['version']} applied, {n} files")


if __name__ == "__main__":
    for step in (self_update, code_sync):
        try:
            step()
        except Exception as e:  # noqa: BLE001  never block the update
            print(f"{step.__name__} skipped: {e}")
