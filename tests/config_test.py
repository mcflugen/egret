import pytest

import egret


def test_find_config_file(monkeypatch):
    with monkeypatch.context() as mp:
        mp.setenv("XDG_CONFIG_HOME", "/not/a/real/dir")
        path_to_config = egret.find_user_config_file()

    assert path_to_config == "/not/a/real/dir/egret.toml"


@pytest.mark.parametrize(
    "option",
    (
        "--include-type",
        "--include_type",
        "include_type",
        "include-type",
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

    assert config == {"include_type": "ini"}


@pytest.mark.parametrize("contents", ("", "[tool.egret]"))
def test_parse_config_empty_contents(tmpdir, contents):
    with tmpdir.as_cwd():
        with open("egret.toml", "w") as fp:
            print(contents, file=fp)
        assert egret.parse_config_toml("egret.toml") == {}


@pytest.mark.parametrize("arg", (None, "/not/a/file.toml"))
def test_parse_config_empty(arg):
    assert egret.parse_config_toml(arg) == {}
