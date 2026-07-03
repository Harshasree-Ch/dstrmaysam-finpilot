from pathlib import Path

from finpilot.core.runtime import add_workspace_venv_site_packages


def test_add_workspace_venv_site_packages_adds_windows_layout(tmp_path, monkeypatch):
    site_packages = tmp_path / ".venv" / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    monkeypatch.setattr("sys.path", [])

    add_workspace_venv_site_packages(tmp_path)

    assert str(site_packages) in __import__("sys").path


def test_add_workspace_venv_site_packages_adds_posix_layout(tmp_path, monkeypatch):
    site_packages = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True)
    monkeypatch.setattr("sys.path", [])

    add_workspace_venv_site_packages(Path(tmp_path))

    assert str(site_packages) in __import__("sys").path
