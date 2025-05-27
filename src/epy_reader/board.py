import curses
import re
from typing import Optional, Tuple, Union

from epy_reader.models import Direction, InlineStyle, Key, NoUpdate
from epy_reader.settings import DoubleSpreadPadding


class InfiniBoard:
    """
    Wrapper for curses screen to render infinite texts.
    The idea is instead of pre render all the text before reading,
    this will only renders part of text on demand by which available
    page on screen.

    And what this does is only drawing text/string on curses screen
    without .clear() or .refresh() to optimize performance.
    """

    def __init__(
        self,
        screen,
        settings,
        text: Tuple[str, ...],
        textwidth: int = 80,
        default_style: Tuple[InlineStyle, ...] = tuple(),
        spread: int = 1,
    ):
        self.settings = settings
        self.screen = screen
        self.screen_rows, self.screen_cols = self.screen.getmaxyx()
        self.textwidth = textwidth
        self.x = ((self.screen_cols - self.textwidth) // 2) + 1
        self.text = text
        self.total_lines = len(text)
        self.default_style: Tuple[InlineStyle, ...] = default_style
        self.temporary_style: Tuple[InlineStyle, ...] = ()
        self.spread = spread
        # Color initialization is moved to reader.py for a central control.
        # However, we still need to manage color pairs here based on the setting.
        # Only define if colors are enabled
        if curses.has_colors() and not self.settings.NoColors:
            # These pairs should match those defined in reader.py if you want them to be used
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Default app colors
            curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLUE)  # Alternate colors

        if self.spread == 2:
            self.x = DoubleSpreadPadding.LEFT.value
            self.x_alt = (
                DoubleSpreadPadding.LEFT.value + self.textwidth + DoubleSpreadPadding.MIDDLE.value
            )

    def feed_temporary_style(self, styles: Optional[Tuple[InlineStyle, ...]] = None) -> None:
        """Reset styling if `styles` is None"""
        self.temporary_style = styles if styles else ()

    def render_styles(
        self, row: int, styles: Tuple[InlineStyle, ...] = (), bottom_padding: int = 0
    ) -> None:
        for i in styles:
            if i.row in range(row, row + self.screen_rows - bottom_padding):
                # When NoColors is true, use A_NORMAL to respect terminal.
                # When NoColors is false, use the screen's current background color pair.
                base_attr = curses.A_NORMAL if self.settings.NoColors else self.screen.getbkgd()
                self.chgat(row, i.row, i.col, i.n_letters, base_attr | i.attr)

            if self.spread == 2 and i.row in range(
                row + self.screen_rows - bottom_padding,
                row + 2 * (self.screen_rows - bottom_padding),
            ):
                self.chgat(
                    row,
                    i.row - (self.screen_rows - bottom_padding),
                    -self.x + self.x_alt + i.col,
                    i.n_letters,
                    (curses.A_NORMAL if self.settings.NoColors else self.screen.getbkgd()) | i.attr,
                )

    def getch(self) -> Union[NoUpdate, Key]:
        input = self.screen.getch()
        if input == -1:
            return NoUpdate()
        return Key(input)

    def getbkgd(self):
        # Return A_NORMAL for no colors, or the screen's actual background for colors
        # Now this reflects the actual current background
        return curses.A_NORMAL if self.settings.NoColors else self.screen.getbkgd()

    def chgat(self, row: int, y: int, x: int, n: int, attr: int) -> None:
        # Ensure the change is within the visible window boundaries
        if (
            y - row >= 0
            and y - row < self.screen_rows
            and self.x + x >= 0
            and self.x + x < self.screen_cols
        ):
            try:
                self.screen.chgat(y - row, self.x + x, n, attr)
            except curses.error:
                # Catch error if chgat goes out of bounds, especially common with large `n` values
                # or near window edges. This prevents a crash but might result in incomplete highlighting
                pass

    def write(self, row: int, bottom_padding: int = 0) -> None:
        for n_row in range(min(self.screen_rows - bottom_padding, self.total_lines - row)):
            text_line = self.text[row + n_row]
            # NOTE: A bug with python itself: https://bugs.python.org/issue8243
            # It's stated in python docs:
            # > Attempting to write to the lower right corner of a window, subwindow,
            # > or pad will cause an exception to be raised after the character is printed.
            # https://github.com/python/cpython/commit/ef5ce884a41c8553a7eff66ebace908c1dcc1f89#diff-cb5622768373b8c93cc8eee30dfb041108783bb419d9eaf205501989cea0049fR691-R692
            #
            # Since the exception is raised "after the character is printed"
            # then it seems to be safe to catch it.
            try:
                # If colors are enabled, use the currently set background
                # color pair (color_pair(1) or color_pair(2))
                # If no specific pair is set, it defaults to color_pair(0)
                # which is white on black if not use_default_colors()
                # but since we set color_pair(1) in Reader, we could use that.
                # Use the default color pair for the app
                self.screen.addstr(
                    n_row,
                    self.x,
                    text_line,
                    curses.A_NORMAL if self.settings.NoColors else curses.color_pair(1),
                )
            except curses.error:
                pass

            if (
                self.spread == 2
                and row + self.screen_rows - bottom_padding + n_row < self.total_lines
            ):
                text_line = self.text[row + self.screen_rows - bottom_padding + n_row]
                if re.search(r"\[IMG:[0-9]+\]", text_line):  # Raw string for regex
                    attr = curses.A_BOLD | (
                        curses.A_NORMAL if self.settings.NoColors else curses.color_pair(1)
                    )
                    self.screen.addstr(n_row, self.x_alt, text_line.center(self.textwidth), attr)
                else:
                    self.screen.addstr(
                        n_row,
                        self.x_alt,
                        text_line,
                        curses.A_NORMAL if self.settings.NoColors else curses.color_pair(1),
                    )
        self.render_styles(row, self.default_style, bottom_padding)
        self.render_styles(row, self.temporary_style, bottom_padding)
        # self.screen.refresh()

    def write_n(
        self,
        row: int,
        n: int = 1,
        direction: Direction = Direction.FORWARD,
        bottom_padding: int = 0,
    ) -> None:
        assert n > 0
        for n_row in range(min(self.screen_rows - bottom_padding, self.total_lines - row)):
            text_line = self.text[row + n_row]
            if direction == Direction.FORWARD:
                self.screen.addnstr(
                    n_row,
                    self.x + self.textwidth - n,
                    text_line + " " * (self.textwidth - len(text_line)),
                    n,
                    curses.A_NORMAL if self.settings.NoColors else curses.color_pair(1),
                )

                if (
                    self.spread == 2
                    and row + self.screen_rows - bottom_padding + n_row < self.total_lines
                ):
                    text_line_alt = self.text[row + n_row + self.screen_rows - bottom_padding]
                    self.screen.addnstr(
                        n_row,
                        self.x_alt + self.textwidth - n,
                        text_line_alt + " " * (self.textwidth - len(text_line_alt)),
                        n,
                        curses.A_NORMAL if self.settings.NoColors else curses.color_pair(1),
                    )

            else:
                if text_line[self.textwidth - n :]:
                    self.screen.addnstr(
                        n_row,
                        self.x,
                        text_line[self.textwidth - n :],
                        n,
                        curses.A_NORMAL if self.settings.NoColors else curses.color_pair(1),
                    )

                if (
                    self.spread == 2
                    and row + self.screen_rows - bottom_padding + n_row < self.total_lines
                ):
                    text_line_alt = self.text[row + n_row + self.screen_rows - bottom_padding]
                    self.screen.addnstr(
                        n_row,
                        self.x_alt,
                        text_line_alt[self.textwidth - n :],
                        n,
                        curses.A_NORMAL if self.settings.NoColors else curses.color_pair(1),
                    )
