import pathlib
import sys

import grist
import pytest


def test_find_config_file(monkeypatch):
    if sys.platform == "win32":
        path_to_config = grist.find_user_config_file()
        assert (
            pathlib.Path(path_to_config) == pathlib.Path("~/.grist.toml").expanduser()
        )
    else:
        with monkeypatch.context() as mp:
            mp.setenv("XDG_CONFIG_HOME", "/not/a/real/dir")
            path_to_config = grist.find_user_config_file()

        assert path_to_config == "/not/a/real/dir/grist.toml"


@pytest.mark.parametrize(
    "option",
    (
        "--extend-types-or",
        "--extend_types_or",
        "extend_types_or",
        "extend-types-or",
    ),
)
def test_parse_config(tmpdir, option):
    with tmpdir.as_cwd():
        with open("grist.toml", "w") as fp:
            print(
                f"""
[tool.grist]
{option} = "ini"
                """,
                file=fp,
            )
        config = grist.parse_config_toml("grist.toml")

    assert config == {"extend_types_or": "ini"}


@pytest.mark.parametrize("contents", ("", "[tool.grist]"))
def test_parse_config_empty_contents(tmpdir, contents):
    with tmpdir.as_cwd():
        with open("grist.toml", "w") as fp:
            print(contents, file=fp)
        assert grist.parse_config_toml("grist.toml") == {}


@pytest.mark.parametrize("arg", (None, "/not/a/file.toml"))
def test_parse_config_empty(arg):
    assert grist.parse_config_toml(arg) == {}
