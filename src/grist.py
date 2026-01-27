from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from collections import ChainMap
from collections.abc import Callable
from collections.abc import Collection
from collections.abc import Generator
from collections.abc import Iterable
from collections.abc import Sequence
from functools import cached_property
from multiprocessing import Pool
from typing import Any

import pygments.lexers
from identify import identify
from pygments import highlight
from pygments.formatters import TerminalTrueColorFormatter
from pygments.lexers import TextLexer
from pygments.util import ClassNotFound


def err(*args, **kwds):
    print(*args, file=sys.stderr, **kwds)


out = err

__version__ = "0.1.0"


ALL_TAGS = frozenset(identify.ALL_TAGS - identify.TYPE_TAGS - identify.MODE_TAGS)


def _build_pre_parser():
    pre_parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    pre_parser.add_argument("--config", help="Specify config file", metavar="FILE")
    pre_parser.add_argument(
        "--version", action="version", version=f"grist {__version__}"
    )
    pre_parser.add_argument(
        "--print-types", action="store_true", help="Print all valid file types."
    )

    return pre_parser


def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    DEFAULTS = {
        "color": "auto",
        "exclude": "^$",
        "extend_types": [],
        "extend_types_or": [],
        "include": ".*",
        "jobs": 0,
        "types": [],
        "no_types": [],
        "search_text": True,
        "search_binary": False,
    }

    pre_parser = _build_pre_parser()

    early_args, _ = pre_parser.parse_known_args(argv)

    defaults = ChainMap(
        parse_config_toml(early_args.config),
        parse_config_toml(find_user_config_file()),
        DEFAULTS,
    )

    parser = argparse.ArgumentParser(prog="grist", parents=[pre_parser])
    parser.set_defaults(**defaults)

    parser.add_argument("pattern", metavar="PATTERN")
    parser.add_argument("dir", default=["."], nargs="*", metavar="DIR")

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Be verbose",
    )
    parser.add_argument(
        "--ignore-case",
        "-i",
        action="store_true",
        help="Perform case insensitive matching.",
    )
    parser.add_argument(
        "--find-files",
        action="store_true",
        help="Apply pattern to filenames.",
    )
    parser.add_argument(
        "--files-with-matches",
        "-l",
        action="store_true",
        help=(
            "Only the names of files containing selected lines are written to standard"
            " output."
        ),
    )
    parser.add_argument(
        "--invert-match",
        "-v",
        action="store_true",
        help="Selected lines are those *not* matching any of the specified patterns.",
    )

    group = parser.add_argument_group(
        "Formatting", description="Options for formatting output."
    )
    group.add_argument(
        "--line-number",
        "-n",
        action="store_true",
        help=(
            "Each output line is preceded by its relative line number in the file,"
            " starting at line 0."
        ),
    )
    group.add_argument(
        "--color",
        choices=("always", "auto", "never"),
        help="When to use syntax highlighting on the matched text.",
    )

    group = parser.add_argument_group(
        "Filtering",
        description="Options that control how files are filtered by name and by type.",
    )
    group.add_argument(
        "--include",
        help="Files to include from the search",
    )
    group.add_argument(
        "--exclude",
        help="Files to exclude from the search",
    )
    group.add_argument(
        "--type",
        dest="types",
        action="append",
        metavar="TYPE",
        default=None,
        type=_validate_type,
        help=(
            "Restrict search to this file type (repeatable). If specified, replaces"
            " the default type set."
        ),
    )
    group.add_argument(
        "--add-type",
        dest="add_types",
        action="append",
        metavar="TYPE",
        default=None,
        type=_validate_type,
        help="add this type (repeatable) to the current type set",
    )
    group.add_argument(
        "--no-type",
        dest="no_types",
        action="append",
        metavar="TYPE",
        default=None,
        type=_validate_type,
        help="Remove a file type from the search set.",
    )
    group.add_argument(
        "--text",
        dest="search_text",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Search text files",
    )
    group.add_argument(
        "--binary",
        dest="search_binary",
        default=False,
        action=argparse.BooleanOptionalAction,
        help="Search binary files",
    )

    parser.add_argument(
        "--walk",
        "-w",
        action="store_true",
        help=(
            "Recusively walk a directory tree looking for files. The default is to"
            " search files tracked by git."
        ),
    )

    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        help=(
            "The number of worker processes. A value of 0 means to use the available"
            " processors."
        ),
    )

    if early_args.print_types:
        print_pipe_safe(sorted(ALL_TAGS))
        return 0

    args = parser.parse_args(argv)

    all_types = set(args.types if args.types is not None else defaults["types"]) | set(
        args.add_types if args.add_types else {}
    )
    no_types = set(args.no_types if args.no_types is not None else defaults["no_types"])

    encoding = set()
    if args.search_text:
        encoding.add("text")
    if args.search_binary:
        encoding.add("binary")

    if args.verbose:
        out(f"encoding: {' | '.join(sorted(encoding))}")
        out(f"types: {' | '.join(sorted(all_types - no_types))}")

    max_count = 1 if args.files_with_matches else -1

    if args.color == "always" or (args.color == "auto" and sys.stdout.isatty()):
        Formatter: type[SelectionFormatter] = SelectionFormatterSyntaxHighlight
    else:
        Formatter = SelectionFormatter

    if args.walk:
        FileCollector: type[CollectFiles] = WalkFiles
    else:
        FileCollector = GitFiles

    SelectorCls: type[Selector]

    if args.find_files:
        SelectorCls = FilenameSelector
    else:
        SelectorCls = LineSelector

    select = SelectorCls(
        args.pattern,
        max_count=max_count,
        invert_match=args.invert_match,
        ignore_case=args.ignore_case,
    )

    process_files = ProcessFiles(
        select.select_from_path,
        Formatter(
            with_line_numbers=args.line_number,
            files_with_matches=args.files_with_matches,
        ).format,
        workers=args.jobs,
    )

    matches: list[str] = []
    for dir_ in args.dir:
        files = FileCollector(
            base=dir_,
            include=args.include,
            exclude=args.exclude,
            types=all_types,
            exclude_types=no_types,
            encoding=encoding,
        )
        collected_files = files.collect()
        matches += process_files(collected_files)

    files_matched = print_pipe_safe(matches)

    return 0 if files_matched else 1


def print_pipe_safe(lines: Iterable[str]) -> int:
    line_count = 0
    for line in lines:
        line_count += 1
        try:
            print(line)
        except BrokenPipeError:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            break
    return line_count


def _validate_type(value: str) -> str:
    if value not in identify.ALL_TAGS:
        raise argparse.ArgumentTypeError(
            f"unknown file type {value!r}. Use --print-types to get a list"
            " of valid types"
        )
    return value


def find_user_config_file() -> str:
    if sys.platform == "win32":
        user_config_path = pathlib.Path.home() / ".grist.toml"
    else:
        config_root = os.environ.get("XDG_CONFIG_HOME", "~/.config")
        user_config_path = pathlib.Path(config_root).expanduser() / "grist.toml"
    return str(user_config_path.resolve())


def parse_config_toml(path_to_config: str | None) -> dict[str, Any]:
    if path_to_config is not None and pathlib.Path(path_to_config).is_file():
        with open(path_to_config, "rb") as fp:
            config_toml = tomllib.load(fp)
        config: dict[str, Any] = config_toml.get("tool", {}).get("grist", {})
        config = {k.replace("--", "").replace("-", "_"): v for k, v in config.items()}
    else:
        config = {}

    return config


def _tags_for(filename: str) -> set[str]:
    return (
        identify.tags_from_path(filename)
        if os.path.exists(filename)
        else identify.tags_from_filename(filename)
    )


def _pick_best_lexer(tags: set[str]) -> type[pygments.lexers.Lexer]:
    for tag in sorted(tags):
        try:
            lexer = pygments.lexers.find_lexer_class_by_name(tag)
        except ClassNotFound:
            continue
        else:
            return lexer

    return TextLexer


class ProcessFiles:
    def __init__(
        self,
        select_lines: Callable[[str], list[tuple[int, str]]],
        format_selection: Callable[[str, list[tuple[int, str]]], str],
        workers: int | None = None,
    ) -> None:
        self._select_lines = select_lines
        self._format_selection = format_selection
        self._workers = workers or os.cpu_count() or 1

    def one(self, filename: str) -> str:
        if selected_lines := self._select_lines(filename):
            formatted_lines = self._format_selection(filename, selected_lines)
            return formatted_lines
        return ""

    def __call__(self, files: Sequence[str] | Generator[str]) -> Generator[str]:
        with Pool(processes=self._workers) as pool:
            formatted_lines = pool.map(self.one, files)
        return (line for line in formatted_lines if line)


class Selector:
    def __init__(
        self,
        pattern: str,
        max_count: int = -1,
        invert_match: bool = False,
        ignore_case: bool = False,
    ) -> None:
        flags = re.NOFLAG
        if ignore_case:
            flags |= re.IGNORECASE

        self._pattern = re.compile(pattern, flags=flags)
        self._max_count = max_count
        self._invert_match = invert_match

    def select_from_path(self, filename: str) -> list[tuple[int, str]]:
        raise NotImplementedError("select_from_path")

    def match_line(self, line: str) -> bool:
        if self._invert_match:
            return not self._pattern.search(line)
        else:
            return bool(self._pattern.search(line))


class LineSelector(Selector):
    def select_from_path(self, filename: str) -> list[tuple[int, str]]:
        with open(filename) as fp:
            return self._select_from_filelike(fp)

    def _select_from_filelike(self, filelike) -> list[tuple[int, str]]:
        count = 0
        selected = []
        for lineno, line in enumerate(filelike):
            if self.match_line(line):
                selected.append((lineno, line.rstrip(os.linesep)))
                count += 1
                if count == self._max_count:
                    break
        return selected


class FilenameSelector(Selector):
    def select_from_path(self, filename: str) -> list[tuple[int, str]]:
        return [(0, filename)] if self.match_line(filename) else []


class SelectionFormatter:
    def __init__(
        self, with_line_numbers: bool = True, files_with_matches: bool = False
    ) -> None:
        self._with_line_numbers = with_line_numbers
        self._files_with_matches = files_with_matches
        self._ignore_tags = frozenset(identify.TYPE_TAGS | identify.MODE_TAGS)

    def format(self, filename: str, selections: Sequence[tuple[int, str]]) -> str:
        if selections and self._files_with_matches:
            return filename

        return os.linesep.join(
            [
                self.format_prefix(filename, selection)
                + self.format_selection(selection)
                for selection in selections
            ]
        )

    def format_prefix(self, filename: str, selection: tuple[int, str]) -> str:
        lineno, line = selection

        formatted = f"{filename}:"
        if self._with_line_numbers:
            formatted += f"{lineno}:"

        return formatted

    def format_selection(self, selection: tuple[int, str]) -> str:
        return selection[1]


class SelectionFormatterSyntaxHighlight(SelectionFormatter):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._lexer = TextLexer(ensurenl=False)

    def format(self, filename: str, selections: Sequence[tuple[int, str]]) -> str:
        tags = _tags_for(filename) - self._ignore_tags

        self._lexer = _pick_best_lexer(tags)(ensurenl=False)

        return super().format(filename, selections)

    def format_selection(self, selection: tuple[int, str]) -> str:
        return highlight(selection[1], self._lexer, TerminalTrueColorFormatter())


class CollectFiles:
    def __init__(
        self,
        base: str = ".",
        include: str = ".*",
        exclude: str = "^$",
        types: Collection[str] = (),
        exclude_types: Collection[str] = (),
        encoding: Collection[str] = ("text",),
    ) -> None:
        self._include_pattern = re.compile(include)
        self._exclude_pattern = re.compile(exclude)
        self._types = frozenset(types)
        self._base = base
        self._exclude_types = frozenset(exclude_types)
        self._encoding = frozenset(encoding)

    def collect(self) -> Generator[str]:
        raise NotImplementedError("collect")

    def filter_file_by_type(self, filename: str) -> bool:
        tags = identify.tags_from_path(filename)

        if self._exclude_types & tags:
            return False

        if not (self._encoding & tags):
            return False

        if not self._types:
            return True

        return bool(tags & self._types)


class WalkFiles(CollectFiles):
    IGNORE_PATTERN = r"""(?x)
    (
        ^\.|
        __pycache__|
        egg-info$|
        lib\.
    )
    """

    def __init__(
        self,
        base: str = ".",
        include: str = ".*",
        exclude: str = "^$",
        types: Collection[str] = (),
        exclude_types: Collection[str] = (),
        encoding: Collection[str] = ("text",),
    ) -> None:
        super().__init__(
            base=base,
            include=include,
            exclude=exclude,
            types=types,
            exclude_types=exclude_types,
            encoding=encoding,
        )

        self._ignore_pattern = re.compile(WalkFiles.IGNORE_PATTERN)

    @cached_property
    def top_level(self) -> str:
        return str(pathlib.Path(self._base))

    def collect(self) -> Generator[str]:
        for filename in self.get_all_files():
            if (
                self._include_pattern.search(filename)
                and not self._exclude_pattern.search(filename)
                and self.filter_file_by_type(filename)
            ):
                yield filename

    def get_all_files(self) -> Generator[str]:
        file_list = []
        for root, dirs, files in pathlib.Path(self.top_level).walk():
            for file_path in (root / f for f in files):
                file_list.append(file_path)
            dirs[:] = [d for d in dirs if not self.ignore_path(d)]

        return (str(f) for f in file_list)

    def ignore_path(self, path) -> bool:
        return bool(self._ignore_pattern.search(path))


class GitFiles(CollectFiles):
    def __init__(
        self,
        base: str = ".",
        include: str = ".*",
        exclude: str = "^$",
        types: Collection[str] = (),
        exclude_types: Collection[str] = (),
        encoding: Collection[str] = ("text",),
    ) -> None:
        super().__init__(
            base=base,
            include=include,
            exclude=exclude,
            types=types,
            exclude_types=exclude_types,
            encoding=encoding,
        )

        GitFiles.validate_git(self._base)

    @staticmethod
    def validate_git(base):
        try:
            in_git_dir = (
                subprocess.check_output(
                    ["git", "rev-parse", "--is-inside-git-dir"],
                    stderr=subprocess.STDOUT,
                    cwd=base,
                )
                .decode()
                .strip()
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                "git failed. Is it installed and are you in a git repository?"
            ) from error
        else:
            if in_git_dir != "false":
                raise RuntimeError("are you in the .git directory of your repository?")

    @cached_property
    def top_level(self) -> str:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"], cwd=self._base
            )
            .decode()
            .strip()
        )

    def get_all_files(self, relative: bool = False) -> Generator[str]:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=self.top_level
        ).decode()

        all_files = (filename for filename in output.split("\0"))

        if relative:
            path_to_top = pathlib.Path(self.top_level).relative_to(
                pathlib.Path(".").absolute(), walk_up=True
            )

            all_files = (str(path_to_top / path) for path in all_files)
        return all_files

    def collect(self) -> Generator[str]:
        for filename in self.get_all_files(relative=True):
            if (
                self._include_pattern.search(filename)
                and not self._exclude_pattern.search(filename)
                and self.filter_file_by_type(filename)
            ):
                yield filename


if __name__ == "__main__":
    raise SystemExit(main())
