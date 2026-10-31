"""Workspace configuration and the external-source diagnostics."""
import json

import pytest

from modularcv import config, external


def test_defaults_when_no_config_file(tmp_path):
    cfg = config.load(tmp_path)
    assert cfg["facts"] == "facts.md" and cfg["provenance_files"] == []
    assert config.provenance_files(tmp_path) == ("facts.md",)


def test_the_config_file_overrides_defaults_and_keeps_facts_in_provenance(tmp_path):
    (tmp_path / "modularcv.json").write_text(json.dumps(
        {"facts": "my-facts.md", "provenance_files": ["master/cv.tex"]}), encoding="utf-8")
    assert config.provenance_files(tmp_path) == ("master/cv.tex", "my-facts.md")


def test_unknown_keys_and_invalid_json_are_refused(tmp_path):
    (tmp_path / "modularcv.json").write_text(json.dumps({"oops": 1}), encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)
    (tmp_path / "modularcv.json").write_text("{", encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)


def test_the_workspace_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ROOT_ENV, str(tmp_path))
    assert config.workspace_root() == tmp_path


def test_an_unset_external_source_is_a_diagnostic_naming_the_variable(monkeypatch):
    monkeypatch.delenv(external.ENV_VAR, raising=False)
    with pytest.raises(external.HandoffSourceUnavailable) as caught:
        external.handoff_root()
    assert external.ENV_VAR in str(caught.value)
    assert external.private_data_available() is False


def test_a_missing_directory_is_a_diagnostic_not_an_empty_result(tmp_path, monkeypatch):
    monkeypatch.setenv(external.ENV_VAR, str(tmp_path / "absent"))
    with pytest.raises(external.HandoffSourceUnavailable):
        external.handoff_root()


def test_a_configured_directory_is_returned(tmp_path, monkeypatch):
    monkeypatch.setenv(external.ENV_VAR, str(tmp_path))
    assert external.handoff_root() == tmp_path
    assert external.private_data_available() is True
