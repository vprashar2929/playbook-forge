"""Run Ansible with a private, controller-side record of all selected hosts."""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.umask(0o077)
(root / ".run").mkdir(exist_ok=True)
lock = (root / ".run/os-window.lock").open("a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit("Another patch window is open from this checkout.")
window = Path(tempfile.mkdtemp(prefix="window-", dir=root / ".run"))
args = sys.argv[1:]
recovery = args[:1] == ["--recover"]
play = "recover.yml" if recovery else "patch.yml"
command = [root / ".venv/bin/ansible-playbook", root / "playbooks" / play, *(args[1:] if recovery else args)]
env = dict(os.environ, FORGE_WINDOW=str(window), ANSIBLE_LOG_PATH=str(window / "ansible.log"), ANSIBLE_NOCOLOR="1")
selection = subprocess.run([*command, "--list-hosts"], env=env, text=True, stdout=subprocess.PIPE)
hosts = re.findall(r"^      (\S+)\s*$", selection.stdout, re.MULTILINE)
if selection.returncode or not hosts or (recovery and len(hosts) != 1):
    sys.exit("Select at least one patch target, or exactly one target for recovery.")
(window / "targets.json").write_text(json.dumps(hosts, indent=2))
print(f"Window evidence: {window}", flush=True)
try:
    result = subprocess.run(command, env=env)
finally:
    outcomes = {host: {"host": host, "outcome": "unverified"} for host in hosts}
    for record in window.glob("host-*.json"):
        entry = json.loads(record.read_text())
        if entry["outcome"] in ("in progress - verify if interrupted", "packages verified - awaiting boot and platform checks"):
            entry["last_step"] = entry["outcome"]
            entry["outcome"] = "unverified"
        outcomes[entry["host"]] = entry
    (window / "summary.json").write_text(json.dumps(list(outcomes.values()), indent=2) + "\n")
    with (window / "SHA256SUMS").open("w") as sums:
        for path in sorted(window.iterdir()):
            if path.name != "SHA256SUMS" and path.is_file():
                sums.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
sys.exit(result.returncode or int(any(e["outcome"] == "unverified" for e in outcomes.values())))
