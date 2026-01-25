import pytest
from grist import FilenameSelector
from grist import LineSelector
from grist import Selector


@pytest.mark.parametrize("filename", ("_foobar.txt", "foobar", "*foobar"))
def test_filename_selector(filename):
    select = FilenameSelector(".*foobar.*")
    actual = select.select_from_path(filename)
    assert len(actual) == 1
    assert actual[0] == (0, filename)


@pytest.mark.parametrize("filename", ("_fooBAR.txt", "FOOBAR", "*FoObAr"))
def test_filename_selector_ignore_case(filename):
    select = FilenameSelector(".*fOObar.*", ignore_case=True)
    actual = select.select_from_path(filename)
    assert len(actual) == 1
    assert actual[0] == (0, filename)


@pytest.mark.parametrize("filename", ("_foobar.txt", "foobar", "*foobar"))
def test_filename_selector_invert_match(filename):
    select = FilenameSelector(".*baz.*", invert_match=True)
    actual = select.select_from_path(filename)
    assert len(actual) == 1
    assert actual[0] == (0, filename)


def test_selector_not_implemented():
    select = Selector(".*")
    with pytest.raises(NotImplementedError, match="select_from_path"):
        select.select_from_path("foo.txt")


def test_line_selector(tmpdir):
    (tmpdir / "foo.py").write_text("foobar", encoding="utf-8")
    select = LineSelector(".*foobar.*")
    with tmpdir.as_cwd():
        actual = select.select_from_path("foo.py")
        assert actual
