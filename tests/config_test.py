import pathlib
import sys

import egret
import pytest


def test_find_config_file(monkeypatch):
    if sys.platform == "win32":
        path_to_config = egret.find_user_config_file()
        assert (
            pathlib.Path(path_to_config) == pathlib.Path("~/.egret.toml").expanduser()
        )
    else:
        with monkeypatch.context() as mp:
            mp.setenv("XDG_CONFIG_HOME", "/not/a/real/dir")
            path_to_config = egret.find_user_config_file()

        assert path_to_config == "/not/a/real/dir/egret.toml"


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
        with open("egret.toml", "w") as fp:
            print(
                f"""
[tool.egret]
{option} = "ini"
                """,
                file=fp,
            )
        config = egret.parse_config_toml("egret.toml")

    assert config == {"extend_types_or": "ini"}


@pytest.mark.parametrize("contents", ("", "[tool.egret]"))
def test_parse_config_empty_contents(tmpdir, contents):
    with tmpdir.as_cwd():
        with open("egret.toml", "w") as fp:
            print(contents, file=fp)
        assert egret.parse_config_toml("egret.toml") == {}


@pytest.mark.parametrize("arg", (None, "/not/a/file.toml"))
def test_parse_config_empty(arg):
    assert egret.parse_config_toml(arg) == {}
