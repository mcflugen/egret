import pytest
from grist import ALL_TAGS
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


def test_print_types(capsys):
    main(["--print-types"])
    lines = capsys.readouterr().out.splitlines()
    assert {line.strip() for line in lines} == ALL_TAGS


def test_bad_tag(capsys):
    assert main(["--walk", "foobar", "--types=foobar"]) == 1
    assert capsys.readouterr().err.startswith("unrecognized tag")
