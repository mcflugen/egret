import contextlib
import os
import pathlib
import subprocess
import textwrap

import pytest

import egret


@contextlib.contextmanager
def as_cwd(path):
    """Change directory context."""
    prev_cwd = pathlib.Path.cwd()
    os.chdir(path)
    yield prev_cwd
    os.chdir(prev_cwd)


FILES = {
    ".git/foo.py": "import bar",
    "bar.toml": textwrap.dedent(
        """\
        [tool.egret]
        include-type = "ini"
        """
    ),
    "foo.py": "import bar",
    "foobar/__init__.py": "#! /usr/bin/python",
}


@pytest.fixture(scope="session")
def git_dir(tmp_path_factory):
    path = tmp_path_factory.mktemp("repo")
    subprocess.check_output(["git", "init", str(path)])
    with as_cwd(path):
        for filename, contents in FILES.items():
            pathlib.Path(filename).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(filename).write_text(contents)

        subprocess.check_output(["git", "add", "foo.py"])

    return path


def test_in_dot_git(git_dir):
    with pytest.raises(RuntimeError):
        egret.GitFiles(git_dir / ".git")


@pytest.mark.parametrize(
    "file_type,expected",
    (
        ("python", ["foo.py"]),
        ("toml", []),
    ),
)
def test_git_files(git_dir, file_type, expected):
    with as_cwd(git_dir):
        assert sorted(egret.GitFiles(include_types=(file_type,)).collect()) == expected


@pytest.mark.parametrize(
    "file_type,expected",
    (
        ("python", ["foo.py", "foobar/__init__.py"]),
        ("toml", ["bar.toml"]),
    ),
)
def test_walk_files(git_dir, file_type, expected):
    with as_cwd(git_dir):
        assert sorted(egret.WalkFiles(include_types=(file_type,)).collect()) == expected
