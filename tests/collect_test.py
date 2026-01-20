import contextlib
import os
import pathlib
import subprocess
import textwrap

import grist
import pytest


@contextlib.contextmanager
def as_cwd(path):
    """Change directory context."""
    prev_cwd = pathlib.Path.cwd()
    os.chdir(path)
    yield prev_cwd
    os.chdir(prev_cwd)


FILES = {
    ".git/foo.py": "import bar",
    "bar.toml": textwrap.dedent("""\
        [tool.grist]
        types = ["ini"]
        """),
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
        grist.GitFiles(git_dir / ".git")


@pytest.mark.parametrize(
    "file_type,expected",
    (
        ("python", ["foo.py"]),
        ("toml", []),
    ),
)
def test_git_files(git_dir, file_type, expected):
    with as_cwd(git_dir):
        assert sorted(grist.GitFiles(types_or=(file_type,)).collect()) == expected


@pytest.mark.parametrize(
    "file_type,expected",
    (
        ("python", ["foo.py", "foobar/__init__.py"]),
        ("toml", ["bar.toml"]),
    ),
)
def test_walk_files(git_dir, file_type, expected):
    with as_cwd(git_dir):
        assert [
            pathlib.Path(f)
            for f in sorted(grist.WalkFiles(types_or=(file_type,)).collect())
        ] == [pathlib.Path(f) for f in expected]
