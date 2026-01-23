import pytest
from grist import main


def test_help():
    with pytest.raises(SystemExit):
        main(["--help"])


def test_version():
    with pytest.raises(SystemExit):
        main(["--version"])


def test_walk(capsys, tmpdir):
    with tmpdir.as_cwd():
        with open("baz.txt", "w") as fp:
            print("foobar", file=fp)
        main(["--walk", "foobar", "--types-or=text"])
        out = capsys.readouterr().out.strip()
        assert out.partition(":") == ("baz.txt", ":", "foobar")
