import pytest
from grist import ProcessFiles


def _select_all_lines(filename):
    with open(filename, encoding="utf-8") as fp:
        return enumerate(fp.readlines())


def _select_no_lines(filename):
    return []


def _just_filename(filename, lines):
    return filename


def test_unicode_error(capsys, tmpdir):
    process = ProcessFiles(_select_all_lines, _just_filename)

    with tmpdir.as_cwd():
        with open("foo.bin", "wb") as fp:
            fp.write(b"\xff\x00\xbar")
        process.one("foo.bin")

    assert capsys.readouterr().err.startswith("unable to process")


def test_process_file_with_match(tmpdir):
    (tmpdir / "foo.txt").write("foobar")
    process = ProcessFiles(_select_all_lines, _just_filename)

    with tmpdir.as_cwd():
        actual = process.one("foo.txt")
    assert actual == "foo.txt"


def test_process_file_no_match(tmpdir):
    (tmpdir / "foo.txt").write("foobar")
    process = ProcessFiles(_select_no_lines, _just_filename)

    with tmpdir.as_cwd():
        actual = process.one("foo.txt")
    assert actual == ""


@pytest.mark.parametrize("workers", (1, None))
def test_process_multiple_files(tmpdir, workers):
    (tmpdir / "foo.txt").write("foobar")
    (tmpdir / "bar.py").write("foobar = 2")
    process = ProcessFiles(_select_all_lines, _just_filename, workers=workers)

    with tmpdir.as_cwd():
        actual = list(process(["foo.txt", "bar.py"]))
    assert actual == ["foo.txt", "bar.py"]
