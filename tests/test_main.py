from pathlib import Path

from shadowfolio.main import resolve_config_path


def test_relative_config_paths_are_resolved_from_the_config_folder_not_the_current_one() -> None:
    assert resolve_config_path("data/shadowfolio.db", Path("/repo")) == Path("/repo/data/shadowfolio.db")


def test_absolute_config_paths_are_kept() -> None:
    assert resolve_config_path("/srv/shadowfolio.db", Path("/repo")) == Path("/srv/shadowfolio.db")
