import os
import re
import stat

import pygments
import pytest
from grist import SelectionFormatterSyntaxHighlight
from pygments.util import ClassNotFound


@pytest.mark.parametrize("ext", ("", ".unknown_extension"))
def test_unknown_file_type(ext):
    highlight = SelectionFormatterSyntaxHighlight()
    actual = highlight.format(f"t{ext}", ((42, "a = 'foobar'"),))

    assert "foobar" in actual
    assert not re.search(r"\x1b\[[0-9;]*m", actual)


def test_lexer_not_found(monkeypatch):
    highlight = SelectionFormatterSyntaxHighlight()

    def no_lexers(*args):
        raise ClassNotFound("unable to find lexer")

    monkeypatch.setattr(pygments.lexers, "find_lexer_class_by_name", no_lexers)

    actual = highlight.format("t.py", ((42, "a = 'foobar'"),))
    assert "foobar" in actual
    assert not re.search(r"\x1b\[[0-9;]*m", actual)


@pytest.mark.parametrize(
    "ext,line",
    (
        (".py", "a = 'foobar'"),
        (".html", "<a>a = 'foobar'</a>"),
        (".md", "**foobar**"),
    ),
)
def test_known_file_type(ext, line):
    highlight = SelectionFormatterSyntaxHighlight()
    actual = highlight.format(f"t{ext}", ((42, line),))

    assert "foobar" in actual
    assert re.search(r"\x1b\[[0-9;]*m", actual)


@pytest.mark.parametrize(
    "ext,line",
    (
        (".py", "a = 'foobar'"),
        (".html", "<a>a = 'foobar'</a>"),
        (".md", "**foobar**"),
    ),
)
def test_known_existing_file(tmpdir, ext, line):
    highlight = SelectionFormatterSyntaxHighlight()
    filename = f"t{ext}"
    with tmpdir.as_cwd():
        with open(filename, "w") as fp:
            print(line, file=fp)
        st = os.stat(filename)
        os.chmod(filename, st.st_mode | stat.S_IEXEC)

        actual = highlight.format(filename, ((42, line),))

    assert "foobar" in actual
    assert re.search(r"\x1b\[[0-9;]*m", actual)
