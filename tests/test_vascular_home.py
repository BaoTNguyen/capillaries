"""Everything capillaries writes outside the checkout lands under VASCULAR_HOME,
resolved at call time so setting it after import still counts."""
import hashlib
import subprocess
from pathlib import Path

from capillaries import daemon, spine
from capillaries.config import paths

ROOT = Path(__file__).resolve().parents[1]


def test_every_default_path_follows_vascular_home(monkeypatch, tmp_path):
    monkeypatch.setenv("VASCULAR_HOME", str(tmp_path))
    for var in ("PROMPTS_PATH", "SKILLS_PATH", "OBSIDIAN_VAULT_PATH", "EVENT_JOURNAL_DIR"):
        monkeypatch.delenv(var, raising=False)

    assert paths._resolve_path("PROMPTS_PATH", "Areas/AI/Prompts", "prompts") == tmp_path / "data" / "capillaries" / "prompts"
    assert paths._resolve_path("SKILLS_PATH", "Areas/AI/Skills", "skills") == tmp_path / "data" / "capillaries" / "skills"
    assert daemon.state_dir() == tmp_path / "state" / "capillaries"

    spine.emit("vascular.check")
    assert len(list((tmp_path / "spool" / "events").glob("*.ndjson"))) == 1


def test_vendored_module_is_unmodified():
    digest = hashlib.sha256((ROOT / "src" / "capillaries" / "vascular_paths.py").read_bytes()).hexdigest()
    assert digest == "15d668c51d5e881fa7a9bf5a9908ba3d7bba796ebb76499cd2216ebf4f05f758"


def test_install_scripts_parse():
    for script in ("setup.sh", "teardown.sh"):
        assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / script)]).returncode == 0, script
