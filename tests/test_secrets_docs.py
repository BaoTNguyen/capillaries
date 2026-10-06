from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = "~/.vascular/secrets/capillaries/env"


def test_env_example_points_to_secrets_file():
    text = (ROOT / ".env.example").read_text()
    assert SECRETS in text
    for key in ("DB_PASSWORD", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        assert key not in text, key


def test_readme_names_secrets_file():
    assert SECRETS in (ROOT / "README.md").read_text()
