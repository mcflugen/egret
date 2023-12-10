from __future__ import annotations

import argparse
import functools
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from collections import ChainMap
from collections.abc import Generator, Sequence
from functools import cached_property
from multiprocessing import Pool
from typing import Any

import pygments.lexers
from identify import identify
from pygments import highlight
from pygments.formatters import TerminalTrueColorFormatter
from pygments.lexers import TextLexer

err = functools.partial(print, file=sys.stderr)
out = functools.partial(print, file=sys.stderr)

__version__ = "0.1.0"


def main() -> int:
    DEFAULTS = {
        "color": "auto",
        "exclude": "^$",
        "extend_include_type": [],
        "include": ".*",
        "include_type": [],
        "jobs": 0,
    }

    config_parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False
    )
    config_parser.add_argument("--config", help="Specify config file", metavar="FILE")
    args, _ = config_parser.parse_known_args()

    defaults = ChainMap(
        DEFAULTS,
        parse_config_toml(find_user_config_file()),
        parse_config_toml(args.config),
    )

    parser = argparse.ArgumentParser(prog="egret", parents=[config_parser])
    parser.set_defaults(**defaults)

    parser.add_argument("pattern", metavar="PATTERN")
    parser.add_argument("--version", action="version", version=f"egret {__version__}")
    parser.add_argument("dir", default=["."], nargs="*", metavar="DIR")
    parser.add_argument(
        "--ignore-case",
        "-i",
        action="store_true",
        help="Perform case insensitive matching.",
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
        "--line-number",
        "-n",
        action="store_true",
        help=(
            "Each output line is preceded by its relative line number in the file,"
            " starting at line 0."
        ),
    )
    parser.add_argument(
        "--include",
        help="Files to include from the search",
    )
    parser.add_argument(
        "--exclude",
        help="Files to exclude from the search",
    )
    parser.add_argument(
        "--invert-match",
        "-v",
        action="store_true",
        help="Selected lines are those *not* matching any of the specified patterns.",
    )
    parser.add_argument(
        "--extend-include-type",
        action="append",
        help="Extend the list of file types to search.",
    )
    parser.add_argument(
        "--include-type",
        action="append",
        help="Specify the file type to search.",
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
    parser.add_argument(
        "--color",
        choices=("always", "auto", "never"),
        help="When to use syntax highlighting on the matched text.",
    )

    args = parser.parse_args()

    max_count = 1 if args.files_with_matches else -1
    include_types = (
        ["cython", "python"] if not args.include_type else args.include_type
    ) + args.extend_include_type
    if args.color == "always" or (args.color == "auto" and sys.stdout.isatty()):
        Formatter: type[SelectionFormatter] = SelectionFormatterSyntaxHighlight
    else:
        Formatter = SelectionFormatter

    if args.walk:
        FileCollector: type[CollectFiles] = WalkFiles
    else:
        FileCollector = GitFiles

    process_files = ProcessFiles(
        LineSelector(args.pattern, max_count=max_count, invert_match=args.invert_match),
        Formatter(
            with_line_numbers=args.line_number,
            files_with_matches=args.files_with_matches,
        ),
        workers=args.jobs,
    )

    matches: list[str] = []
    for dir_ in args.dir:
        files = FileCollector(
            base=dir_,
            include=args.include,
            exclude=args.exclude,
            include_types=include_types,
        )
        matches += process_files(files.collect())

    files_matched = 0
    for match in matches:
        files_matched += 1
        try:
            print(match)
        except BrokenPipeError:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            break

    if unknown := set(include_types) - identify.ALL_TAGS:
        err(f"ignored unknown tags: {', '.join(sorted(unknown))}", file=sys.stderr)

    return 0 if files_matched else 1


def find_user_config_file() -> str:
    if sys.platform == "win32":
        user_config_path = pathlib.Path.home() / ".egret"
    else:
        config_root = os.environ.get("XDG_CONFIG_HOME", "~/.config")
        user_config_path = pathlib.Path(config_root).expanduser() / "egret.toml"
    return str(user_config_path.resolve())


def parse_config_toml(path_to_config: str | None) -> dict[str, Any]:
    if path_to_config is not None and pathlib.Path(path_to_config).is_file():
        with open(path_to_config, "rb") as fp:
            config_toml = tomllib.load(fp)
        config: dict[str, Any] = config_toml.get("tool", {}).get("egret", {})
        config = {k.replace("--", "").replace("-", "_"): v for k, v in config.items()}
    else:
        config = {}

    return config


class ProcessFiles:
    def __init__(
        self, select_lines, format_selection, workers: int | None = None
    ) -> None:
        self._select_lines = select_lines
        self._format_selection = format_selection
        self._workers = workers or os.cpu_count() or 1

    def one(self, filename: str) -> str:
        if selected_lines := self._select_lines.select_from_path(filename):
            formatted_lines = self._format_selection.format(filename, selected_lines)
            return formatted_lines
        return ""

    def __call__(
        self, files: Sequence[str] | Generator[str, None, None]
    ) -> Generator[str, None, None]:
        with Pool(processes=self._workers) as pool:
            formatted_lines = pool.map(self.one, files)
        return (line for line in formatted_lines if line)


class LineSelector:
    def __init__(
        self, pattern: str, max_count: int = -1, invert_match: bool = False
    ) -> None:
        self._pattern = re.compile(pattern)
        self._max_count = max_count
        self._invert_match = invert_match

    def select_from_path(self, filename: str) -> list[tuple[int, str]]:
        with open(filename) as fp:
            return self.select_from_filelike(fp)

    def select_from_filelike(self, filelike) -> list[tuple[int, str]]:
        count = 0
        selected = []
        for lineno, line in enumerate(filelike):
            if self.match_line(line):
                selected.append((lineno, line.rstrip(os.linesep)))
                count += 1
                if count == self._max_count:
                    break
        return selected

    def match_line(self, line: str) -> bool:
        if self._invert_match:
            return not self._pattern.search(line)
        else:
            return bool(self._pattern.search(line))


class SelectionFormatter:
    def __init__(
        self, with_line_numbers: bool = True, files_with_matches: bool = False
    ) -> None:
        self._with_line_numbers = with_line_numbers
        self._files_with_matches = files_with_matches
        self._ignore_tags = frozenset(
            identify.TYPE_TAGS | identify.MODE_TAGS | identify.ENCODING_TAGS
        )

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
        tags = identify.tags_from_path(filename) - self._ignore_tags

        try:
            self._lexer = pygments.lexers.find_lexer_class_by_name(sorted(tags)[0])(
                ensurenl=False
            )
        except IndexError:
            self._lexer = TextLexer()

        return super().format(filename, selections)

    def format_selection(self, selection: tuple[int, str]) -> str:
        return highlight(selection[1], self._lexer, TerminalTrueColorFormatter())


class CollectFiles:
    def __init__(
        self,
        base: str = ".",
        include: str = ".*",
        exclude: str = "^$",
        include_types: Sequence[str] = ("python",),
    ) -> None:
        self._include_pattern = re.compile(include)
        self._exclude_pattern = re.compile(exclude)
        self._include_types = frozenset(include_types)
        self._base = base

    def collect(self) -> Generator[str, None, None]:
        raise NotImplementedError("collect")


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
        include_types: Sequence[str] = ("python",),
    ) -> None:
        super().__init__(
            base=base,
            include=include,
            exclude=exclude,
            include_types=include_types,
        )

        self._ignore_pattern = re.compile(WalkFiles.IGNORE_PATTERN)

    @cached_property
    def top_level(self) -> str:
        return str(pathlib.Path(self._base))

    def collect(self) -> Generator[str, None, None]:
        for filename in self.get_all_files():
            if (
                self._include_pattern.search(filename)
                and not self._exclude_pattern.search(filename)
                and self._include_types & identify.tags_from_path(filename)
            ):
                yield filename

    def get_all_files(self) -> Generator[str, None, None]:
        file_list = []
        for root, dirs, files in pathlib.Path(self.top_level).walk():
            for file_path in (pathlib.Path(root) / f for f in files):
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
        include_types: Sequence[str] = ("python",),
    ) -> None:
        super().__init__(
            base=base,
            include=include,
            exclude=exclude,
            include_types=include_types,
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

    def get_all_files(self, relative: bool = False) -> Generator[str, None, None]:
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

    def collect(self) -> Generator[str, None, None]:
        for filename in self.get_all_files(relative=True):
            if (
                self._include_pattern.search(filename)
                and not self._exclude_pattern.search(filename)
                and self._include_types & identify.tags_from_path(filename)
            ):
                yield filename


if __name__ == "__main__":
    raise SystemExit(main())
