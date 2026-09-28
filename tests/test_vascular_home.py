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
    assert len(list((tmp_path / "state" / "heart" / "events").glob("*.ndjson"))) == 1


def test_vendored_module_is_unmodified():
    digest = hashlib.sha256((ROOT / "src" / "capillaries" / "vascular_paths.py").read_bytes()).hexdigest()
    assert digest == "e2da9c91a10831ed001c198a74deec77272b634542766a094e52a872b37836c4"


def test_install_scripts_parse():
    for script in ("setup.sh", "teardown.sh"):
        assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / script)]).returncode == 0, script
