"""QA launcher must never rewrite a remote or already-isolated database URL."""
from pathlib import Path
import runpy

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "start-isolated-coding-qa.py"
isolated_url = runpy.run_path(str(SCRIPT))["isolated_url"]


def test_qa_url_preserves_credentials_and_targets_only_named_local_db():
    result = isolated_url("postgresql://tester:secret@127.0.0.1:5432/asteria?sslmode=disable",
                          "asteria_qa_coding_20260927")
    assert result == ("postgresql://tester:secret@127.0.0.1:5432/"
                      "asteria_qa_coding_20260927?sslmode=disable")


@pytest.mark.parametrize("source,database", [
    ("postgresql://tester@remote.example/asteria", "asteria_qa_coding_20260927"),
    ("postgresql://tester@localhost/asteria_qa_coding_20260927", "asteria_qa_coding_20260927"),
    ("postgresql://tester@localhost/asteria", "asteria"),
])
def test_qa_url_rejects_unsafe_targets(source, database):
    with pytest.raises(ValueError):
        isolated_url(source, database)
