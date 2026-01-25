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
        main(["--walk", "foobar", "--type=plain-text"])
        out = capsys.readouterr().out.strip()
        assert out.partition(":") == ("baz.txt", ":", "foobar")


def test_print_types(capsys):
    main(["--print-types"])
    lines = capsys.readouterr().out.splitlines()
    assert {line.strip() for line in lines} == ALL_TAGS


def test_bad_tag(capsys):
    with pytest.raises(SystemExit, match="2"):
        main(["--walk", "foobar", "--type=foobar"])


@pytest.mark.parametrize("python", (True, False))
@pytest.mark.parametrize("toml", (True, False))
def test_type(capsys, tmpdir, toml, python):
    (tmpdir / "baz.py").write_text("foobar\n", encoding="utf-8")
    (tmpdir / "baz.toml").write_text("foobar\n", encoding="utf-8")

    expected = {name for ok, name in ((python, "baz.py"), (toml, "baz.toml")) if ok}
    args = [
        "--no-type=python" if not python else "--type=python",
        "--no-type=toml" if not toml else "--type=toml",
    ]
    with tmpdir.as_cwd():
        main(["--walk", "foobar", "-l", *args])

    matches = {line.strip() for line in capsys.readouterr().out.splitlines()}
    assert matches == expected


@pytest.mark.parametrize("text", (True, False))
@pytest.mark.parametrize("binary", (True, False))
def test_encoding(capsys, tmpdir, text, binary):
    (tmpdir / "baz.txt").write_text("foobar\n", encoding="utf-8")
    (tmpdir / "baz.bin").write(b"foobar\x00")

    expected = {name for ok, name in ((text, "baz.txt"), (binary, "baz.bin")) if ok}
    args = ["--binary" if binary else "--no-binary", "--text" if text else "--no-text"]
    with tmpdir.as_cwd():
        main(["--walk", "foobar", "-l", *args])

    matches = {line.strip() for line in capsys.readouterr().out.splitlines()}
    assert matches == expected


def test_find_files(capsys, tmpdir):
    (tmpdir / "baz.py").write("foobar")
    (tmpdir / "foobar.py").write("baz")
    with tmpdir.as_cwd():
        main(["--walk", "foobar", "-l"])
        assert capsys.readouterr().out.strip() == "baz.py"

        main(["--walk", "foobar", "-l", "--find-files"])
        assert capsys.readouterr().out.strip() == "foobar.py"


@pytest.mark.parametrize("types", (("python", "json"), ("toml",)))
@pytest.mark.parametrize("binary", (True, False))
@pytest.mark.parametrize("text", (True, False))
def test_verbose(capsys, binary, text, types):
    args = [f"--type={t}" for t in types]
    args.append("--text" if text else "--no-text")
    args.append("--binary" if binary else "--no-binary")

    main(["--walk", "foobar", "-l", "--verbose", *args])
    lines = capsys.readouterr().err.splitlines()

    encodings = []
    if binary:
        encodings.append("binary")
    if text:
        encodings.append("text")

    assert lines[0] == f"encoding: {' | '.join(sorted(encodings))}"
    assert lines[1] == f"types: {' | '.join(sorted(types))}"
