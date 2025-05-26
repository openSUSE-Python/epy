import datetime
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Mapping, NamedTuple, Optional, Tuple, Union


class Direction(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"


@dataclass(frozen=True)
class BookMetadata:
    title: Optional[str] = None
    creator: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None
    format: Optional[str] = None
    identifier: Optional[str] = None
    source: Optional[str] = None


@dataclass(frozen=True)
class LibraryItem:
    last_read: datetime.datetime
    filepath: str
    title: Optional[str] = None
    author: Optional[str] = None
    reading_progress: Optional[float] = None

    def __str__(self) -> str:
        if self.reading_progress is None:
            reading_progress_str = "N/A"
        else:
            reading_progress_str = f"{int(self.reading_progress * 100)}%"
        reading_progress_str = reading_progress_str.rjust(4)

        book_name: str
        filename = self.filepath.replace(os.path.expanduser("~"), "~", 1)
        if self.title is not None and self.author is not None:
            book_name = f"{self.title} - {self.author} ({filename})"
        elif self.title is None and self.author:
            book_name = f"{filename} - {self.author}"
        else:
            book_name = filename

        last_read_str = self.last_read.strftime("%I:%M%p %b %d")

        return f"{reading_progress_str} {last_read_str}: {book_name}"


@dataclass(frozen=True)
class ReadingState:
    """
    Data model for reading state.

    `row` has to be explicitly assigned with value
    because Seamless feature needs it to adjust from
    relative (to book's content index) row to absolute
    (to book's entire content) row.

    `rel_pctg` and `section` default to None and if
    either of them is assigned with value, then it
    will be overriding the `row` value.
    """

    content_index: int
    textwidth: int
    row: int
    rel_pctg: Optional[float] = None
    section: Optional[str] = None


@dataclass(frozen=True)
class SearchData:
    direction: Direction = Direction.FORWARD
    value: str = ""


@dataclass(frozen=True)
class LettersCount:
    """
    all: total letters in book
    cumulative: list of total letters for previous contents
                eg. let's say cumulative = (0, 50, 89, ...) it means
                    0  is total cumulative letters of book contents[-1] to contents[0]
                    50 is total cumulative letters of book contents[0] to contents[1]
                    89 is total cumulative letters of book contents[0] to contents[2]
    """

    all: int
    cumulative: Tuple[int, ...]


@dataclass(frozen=True)
class CharPos:
    """
    Describes character position in text.
    eg. ["Lorem ipsum dolor sit amet,",  # row=0
         "consectetur adipiscing elit."]  # row=1
             ^CharPos(row=1, col=3)
    """

    row: int
    col: int


@dataclass(frozen=True)
class TextMark:
    """
    Describes marking in text.
    eg. Interval [CharPos(row=0, col=3), CharPos(row=1, col=4)]
    notice the marking inclusive [] for both side instead of right exclusive [)
    """

    start: CharPos
    end: Optional[CharPos] = None

    def is_valid(self) -> bool:
        """
        Assert validity and check if the mark is unterminated
        eg. <div><i>This is italic text</div>
        Missing </i> tag
        """
        if self.end is not None:
            if self.start.row == self.end.row:
                return self.start.col <= self.end.col
            else:
                return self.start.row < self.end.row

        return False


@dataclass(frozen=True)
class TextSpan:
    """
    Like TextMark but using span of letters (n_letters)
    """

    start: CharPos
    n_letters: int


@dataclass(frozen=True)
class InlineStyle:
    """
    eg. InlineStyle(attr=curses.A_BOLD, row=3, cols=4, n_letters=3)
    """

    row: int
    col: int
    n_letters: int
    attr: int


@dataclass(frozen=True)
class TocEntry:
    label: str
    content_index: int
    section: Optional[str]


@dataclass(frozen=True)
class TextStructure:
    """
    Object that describes how the text
    should be displayed in screen.

    text_lines: ("list of lines", "of text", ...)
    image_maps: {line_num: path/to/image/in/ebook/zip}
    section_rows: {section_id: line_num}
    formatting: (InlineStyle, ...)
    """

    text_lines: Tuple[str, ...]
    image_maps: Mapping[int, str]
    section_rows: Mapping[str, int]
    formatting: Tuple[InlineStyle, ...]


@dataclass(frozen=True)
class NoUpdate:
    pass


class Key:
    """
    Because ord("k") chr(34) are confusing
    """

    def __init__(self, char_or_int: Union[str, int]):
        self.value: int = char_or_int if isinstance(char_or_int, int) else ord(char_or_int)
        self.char: str = char_or_int if isinstance(char_or_int, str) else chr(char_or_int)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Key):
            return self.value == other.value
        return False

    def __ne__(self, other: Any) -> bool:
        return self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)


class AppData:
    @property
    def prefix(self) -> Optional[str]:
        """Return None if there exists no homedir | userdir"""
        prefix: Optional[str] = None

        # UNIX filesystem
        homedir = os.getenv("HOME")
        # WIN filesystem
        userdir = os.getenv("USERPROFILE")

        if homedir:
            if os.path.isdir(os.path.join(homedir, ".config")):
                prefix = os.path.join(homedir, ".config", "epy")
            else:
                prefix = os.path.join(homedir, ".epy")
        elif userdir:
            prefix = os.path.join(userdir, ".epy")

        if prefix:
            os.makedirs(prefix, exist_ok=True)

        return prefix


# Define the NamedTuple for history entries
class HistoryEntry(NamedTuple):
    command: str
    timestamp: datetime.datetime


class FileHistory:
    """
    Manages input history for curses-based prompts, including loading from
    and saving to a file, with timestamps.
    """

    def __init__(self, file_name: str):
        self.file_path = file_name
        self._history: List[HistoryEntry] = []
        # Index in _history. When equal to len(_history), it means we're typing
        # a new command, not navigating history.
        self._current_index: int = -1
        # Stores the input typed before the user started navigating history up.
        self._current_input_before_history: str = ""
        self.MAX_HISTORY_SIZE = 100  # Limit history to prevent excessive memory usage
        self.TRUNCATION_PERCENTAGE = 0.10  # 10% of MAX_HISTORY_SIZE to remove

        self._load_history()

    def _load_history(self):
        """Loads history from the specified file in readline-like format."""
        self._history = []
        current_timestamp: Optional[datetime.datetime] = None
        current_command_lines: List[str] = []

        try:
            with open(self.file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:  # Blank line indicates end of a record
                        if current_timestamp and current_command_lines:
                            self._history.append(
                                HistoryEntry(
                                    command="".join(
                                        current_command_lines
                                    ),  # Join lines if multi-line input is ever supported
                                    timestamp=current_timestamp,
                                )
                            )
                        current_timestamp = None
                        current_command_lines = []
                    elif line.startswith("#"):
                        try:
                            # Attempt to parse the timestamp
                            # Example format: #1716709841 (Unix timestamp)
                            timestamp_str = line[1:].strip()
                            current_timestamp = datetime.datetime.fromtimestamp(
                                int(timestamp_str),
                                tz=datetime.timezone.utc,  # Assuming UTC for timestamp storage
                            )
                        except (ValueError, TypeError):
                            # Ignore malformed timestamp lines
                            current_timestamp = None
                    elif line.startswith("+") and current_timestamp:
                        # Only add command if we have a valid timestamp preceding it
                        current_command_lines.append(line[1:].strip())
                    # else: Ignore lines that don't match the format or have no timestamp yet

            # Add any remaining command if the file doesn't end with a blank line
            if current_timestamp and current_command_lines:
                self._history.append(
                    HistoryEntry(
                        command="".join(current_command_lines), timestamp=current_timestamp
                    )
                )

            # Apply truncation on load if history is too large
            if len(self._history) > self.MAX_HISTORY_SIZE:
                num_to_remove = int(self.MAX_HISTORY_SIZE * self.TRUNCATION_PERCENTAGE)
                self._history = self._history[num_to_remove:]

        except FileNotFoundError:
            self._history = []
        except Exception as e:
            # Log this in a real application instead of print
            print(f"Warning: Could not load history from {self.file_path}: {e}")
            self._history = []  # Clear history if there's a parsing error
        self.reset_index()  # Initialize index to point to the end of history

    def save_history(self):
        """Saves current history to the specified file in readline-like format."""
        try:
            with open(self.file_path, "w") as f:
                for entry in self._history:
                    # Write timestamp line
                    f.write(f"#{int(entry.timestamp.timestamp())}\n")
                    # Write command line(s)
                    # For now, we assume single-line commands
                    f.write(f"+{entry.command}\n")
                    # Write blank line separator
                    f.write("\n")
        except IOError as e:
            print(f"Warning: Could not save command history to {self.file_path}: {e}")

    def add_command(self, command: str):
        """Adds a command to the history, preventing duplicates at the end, with a timestamp.
        Removes a batch of oldest items if MAX_HISTORY_SIZE is exceeded.
        """
        if command and (not self._history or self._history[-1].command != command):
            self._history.append(
                HistoryEntry(
                    command=command,
                    timestamp=datetime.datetime.now(
                        datetime.timezone.utc
                    ),  # Store current UTC time
                )
            )

            # Check if history size exceeds the limit
            if len(self._history) > self.MAX_HISTORY_SIZE:
                num_to_remove = int(self.MAX_HISTORY_SIZE * self.TRUNCATION_PERCENTAGE)
                # Ensure we remove at least 1 item if we're over the limit
                if num_to_remove == 0 and self.MAX_HISTORY_SIZE > 0:
                    num_to_remove = 1

                self._history = self._history[num_to_remove:]
                # After removal, the history index might become invalid if it was
                # pointing to an item that was removed. Reset it.
                self.reset_index()

        self.reset_index()  # Always reset index after adding a new command (or if history wasn't full)

    def navigate_up(self, current_input: str) -> Optional[str]:
        """
        Navigates up through history. Stores current_input if starting navigation.
        Returns the command string of the history item or None if at the top.
        """
        if not self._history:
            return None

        if self._current_index == len(self._history):
            # Store current input only if we're starting to navigate history
            self._current_input_before_history = current_input

        if self._current_index > 0:
            self._current_index -= 1
            return self._history[self._current_index].command
        return None  # Already at the oldest entry

    def navigate_down(self) -> Optional[str]:
        """
        Navigates down through history. Returns the command string of the history item or the
        stored current input if at the newest entry. Returns empty string if no history.
        """
        if not self._history:
            return ""  # Return empty string for consistency with new input

        if self._current_index < len(self._history) - 1:
            self._current_index += 1
            return self._history[self._current_index].command
        elif self._current_index == len(self._history) - 1:
            # At the newest history item, going down means returning to the current input
            self.reset_index()
            return self._current_input_before_history
        # If _current_index is already past the last history item (e.g., after new command)
        # or if history is empty, return stored current input
        self.reset_index()
        return self._current_input_before_history

    def reset_index(self):
        """Resets the history index to point after the last history item, for new input."""
        self._current_index = len(self._history)
        self._current_input_before_history = ""  # Clear stored input on reset
