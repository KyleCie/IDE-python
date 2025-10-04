"""
A simple Notepad-like text editor.
"""

import datetime
from asyncio import Future, ensure_future
import pyfiglet

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    Float,
    HSplit,
    VSplit,
    Window,
    WindowAlign,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import DynamicLexer, PygmentsLexer
from prompt_toolkit.styles.pygments import style_from_pygments_cls
from prompt_toolkit.search import start_search
from prompt_toolkit.styles import Style, merge_styles
from prompt_toolkit.widgets import (
    Button,
    Dialog,
    Label,
    MenuContainer,
    MenuItem,
    SearchToolbar,
    TextArea,
)

from pygments.style import Style as PygmentsStyle
from pygments.lexers.python import PythonLexer
from pygments.token import Keyword, Name, Comment, String, Number


class MyPythonStyle(PygmentsStyle):
    default_style = ""
    styles = {
        Keyword: "#9549eb",
        Keyword.Constant: "#c08300",
        Keyword.Type: "#babd00",
        Name: "#C7C7C7",
        Name.Namespace: "#189200",
        Name.Function: "bold #d1ab01",
        Name.Function.Magic: "bold italic #d1ab01",
        Name.Variable.Parameter: "bold #CE0000",
        Name.Variable.Magic: "bold italic #46b2e3",
        Name.Variable.Instance: "bold #CE0000",
        Name.Variable.Class: "bold #CE0000",
        Name.Variable: "bold #CE0000",
        Name.Class: 'bold italic #d1ab01', 
        Name.Builtin: " bold italic #46b2e3",
        Name.Exception: "bold italic #d1ab01",
        Name.Decorator: "bold #d1ab01",
        Comment: '#888888',
        String: "italic #1ea311",
        String.Doc: "#6B6B6B",
        Number: "#c08300",
    }


pt_style = style_from_pygments_cls(MyPythonStyle)


class ApplicationState:
    """
    Application state.

    For the simplicity, we store this as a global, but better would be to
    instantiate this as an object and pass at around.
    """

    # parameters
    show_status_bar = True
    current_path: str = None

    # contents
    status_bar: str = " Press Ctrl-E to open menu. "

def get_statusbar_text():
    return ApplicationState.status_bar


def get_statusbar_right_text():
    return f" {text_field.document.cursor_position_row + 1}:{text_field.document.cursor_position_col + 1}  "


ascii_text = pyfiglet.figlet_format("Hello, Kyle.", font="roman")
hello_window = Window(
    content=FormattedTextControl("\n\n"+ascii_text, focusable=False),
    align=WindowAlign.CENTER,
    style="class:hello"
)


search_toolbar = SearchToolbar()
text_field = TextArea(
    lexer=PygmentsLexer(PythonLexer),
    scrollbar=True,
    line_numbers=True,
    style="class:text-area",
    focus_on_click=True
)


class TextInputDialog:
    def __init__(self, title="", label_text="", completer=None):
        self.future = Future()

        def accept_text(buf):
            get_app().layout.focus(ok_button)
            buf.complete_state = None
            return True

        def accept():
            self.future.set_result(self.text_area.text)

        def cancel():
            self.future.set_result(None)

        self.text_area = TextArea(
            completer=completer,
            multiline=False,
            width=D(preferred=40),
            accept_handler=accept_text,
        )

        ok_button = Button(text="OK", handler=accept)
        cancel_button = Button(text="Cancel", handler=cancel)

        self.dialog = Dialog(
            title=title,
            body=HSplit([Label(text=label_text), self.text_area]),
            buttons=[ok_button, cancel_button],
            width=D(preferred=80),
            modal=True,
        )

    def __pt_container__(self):
        return self.dialog


class MessageDialog:
    def __init__(self, title, text):
        self.future = Future()

        def set_done():
            self.future.set_result(None)

        ok_button = Button(text="OK", handler=(lambda: set_done()))

        self.dialog = Dialog(
            title=title,
            body=HSplit([Label(text=text)]),
            buttons=[ok_button],
            width=D(preferred=80),
            modal=True,
        )

    def __pt_container__(self):
        return self.dialog


body = HSplit(
    [
        text_field,
        search_toolbar,
        ConditionalContainer(
            content=VSplit(
                [
                    Window(
                        FormattedTextControl(get_statusbar_text), style="class:status"
                    ),
                    Window(
                        FormattedTextControl(get_statusbar_right_text),
                        style="class:status.right",
                        width=9,
                        align=WindowAlign.RIGHT,
                    ),
                ],
                height=1,
            ),
            filter=Condition(lambda: ApplicationState.show_status_bar),
        ),
    ]
)


menu_body = hello_window

# Global key bindings.
bindings = KeyBindings()


@bindings.add("c-e")
def _(event):
    "Focus menu."
    if event.app.layout.current_window == root_container.window:
        event.app.layout.focus(text_field)
    else:
        event.app.layout.focus(root_container.window)


@bindings.add("tab")
def _(event):
    "add a tab."
    event.app.current_buffer.insert_text("    ")


@bindings.add("s-tab")
def _(event):
    "remove automaticly the tab."
    buf = event.app.current_buffer
    line_start = buf.document.current_line_before_cursor
    if line_start.endswith("    "):
        for _ in range(4):
            buf.delete_before_cursor()


@bindings.add("c-s")
def _(event):
    "save."
    do_save_file()


@bindings.add("c-q")
def _(event):
    "quit."
    do_exit()


#
# Handlers for menu items.
#


def menu_new_file():
    get_app().exit()
    run_app()
    do_new_file()


def menu_open_file():
    get_app().exit()
    run_app()
    do_open_file()


def do_open_file():
    async def coroutine():
        open_dialog = TextInputDialog(
            title="Open file",
            label_text="Enter the path of a file:",
            completer=PathCompleter(),
        )

        path = await show_dialog_as_float(open_dialog)
        ApplicationState.current_path = path

        if path is not None:
            try:
                with open(path, "rb") as f:
                    text_field.text = f.read().decode("utf-8", errors="ignore")

            except FileNotFoundError as e:
                open_dialog = TextInputDialog(
                        title="Problem while opening the file",
                        label_text="The file don't exist, you want to create one ? (Y/n) :",
                    )

                result = await show_dialog_as_float(open_dialog)
                
                if result.lower() in ["y", "yes", "ye", "yse", ""]:

                    with open(path, "wb") as f:
                        f.close()
                    text_field.text = ""
                    ApplicationState.status_bar = f"Press Ctrl-E to open menu, new file created: '{path}'."
                else:
                    show_message("Error", f"{e}")
            except OSError as e:
                show_message("Error", f"{e}")

    ensure_future(coroutine())


def do_about():
    show_message("About", "Text editor made by a french man.\nCreated by Kyle Ciechowicz.")


def show_message(title, text):
    async def coroutine():
        dialog = MessageDialog(title, text)
        await show_dialog_as_float(dialog)

    ensure_future(coroutine())


async def show_dialog_as_float(dialog):
    "Coroutine."
    float_ = Float(content=dialog)
    root_container.floats.insert(0, float_)

    app = get_app()

    focused_before = app.layout.current_window
    app.layout.focus(dialog)
    result = await dialog.future
    app.layout.focus(focused_before)

    if float_ in root_container.floats:
        root_container.floats.remove(float_)

    return result


def do_new_file():
    text_field.text = ""


def do_exit():
    get_app().exit()


def do_time_date():
    text = datetime.datetime.now().isoformat(sep=" ")
    text_field.buffer.insert_text(text)


def do_go_to():
    async def coroutine():
        dialog = TextInputDialog(title="Go to line", label_text="Line number:")

        line_number = await show_dialog_as_float(dialog)

        try:
            line_number = int(line_number)
        except ValueError:
            show_message("Invalid line number")
        else:
            text_field.buffer.cursor_position = (
                text_field.buffer.document.translate_row_col_to_index(
                    line_number - 1, 0
                )
            )

    ensure_future(coroutine())


def do_undo():
    text_field.buffer.undo()


def do_cut():
    data = text_field.buffer.cut_selection()
    get_app().clipboard.set_data(data)


def do_copy():
    data = text_field.buffer.copy_selection()
    get_app().clipboard.set_data(data)


def do_delete():
    text_field.buffer.cut_selection()


def do_find():
    start_search(text_field.control)


def do_find_next():
    search_state = get_app().current_search_state

    cursor_position = text_field.buffer.get_search_position(
        search_state, include_current_position=False
    )
    text_field.buffer.cursor_position = cursor_position


def do_paste():
    text_field.buffer.paste_clipboard_data(get_app().clipboard.get_data())


def do_save_file():
    async def coroutine():
        
        path = ApplicationState.current_path

        if path is not None:
            try:
                txt = text_field.text.encode("utf-8")
                with open(path, "wb") as f:
                    f.write(txt)

                ApplicationState.status_bar = f"Press Ctrl-E to open menu, {len(txt)}B written. "
            except OSError as e:
                show_message("Error", f"{e}")

    ensure_future(coroutine())


def do_save_as_file():
    async def coroutine():
        open_dialog = TextInputDialog(
            title="Save as file",
            label_text="Enter the path of the new file:",
        )

        path = await show_dialog_as_float(open_dialog)

        if path is not None:
            try:
                txt = text_field.text.encode("utf-8")
                with open(path, "wb") as f:
                    f.write(txt)

                ApplicationState.status_bar = f"Press Ctrl-E to open menu, {len(txt)}B written, New file created: '{path}'. "
            except OSError as e:
                show_message("Error", f"{e}")

    ensure_future(coroutine())


def do_select_all():
    text_field.buffer.cursor_position = 0
    text_field.buffer.start_selection()
    text_field.buffer.cursor_position = len(text_field.buffer.text)


def do_status_bar():
    ApplicationState.show_status_bar = not ApplicationState.show_status_bar


#
# The menu container.
#


root_container = MenuContainer(
    body=body,
    menu_items=[
        MenuItem(
            "File",
            children=[
                MenuItem("New...", handler=do_new_file),
                MenuItem("Open...", handler=do_open_file),
                MenuItem("Save", handler=do_save_file),
                MenuItem("Save as...", handler=do_save_as_file),
                MenuItem("-", disabled=True),
                MenuItem("Exit", handler=do_exit),
            ],
        ),
        MenuItem(
            "Edit",
            children=[
                MenuItem("Undo", handler=do_undo),
                MenuItem("Cut", handler=do_cut),
                MenuItem("Copy", handler=do_copy),
                MenuItem("Paste", handler=do_paste),
                MenuItem("Delete", handler=do_delete),
                MenuItem("-", disabled=True),
                MenuItem("Find", handler=do_find),
                MenuItem("Find next", handler=do_find_next),
                MenuItem("Replace"),
                MenuItem("Go To", handler=do_go_to),
                MenuItem("Select All", handler=do_select_all),
                MenuItem("Time/Date", handler=do_time_date),
            ],
        ),
        MenuItem(
            "View",
            children=[MenuItem("Status Bar", handler=do_status_bar)],
        ),
        MenuItem(
            "Info",
            children=[MenuItem("About", handler=do_about)],
        ),
    ],
    floats=[
        Float(
            xcursor=True,
            ycursor=True,
            content=CompletionsMenu(max_height=16, scroll_offset=1),
        ),
    ],
    key_bindings=bindings,
)


menu_container = MenuContainer(
    body=menu_body,
    menu_items=[
        MenuItem(
            "File",
            children=[
                MenuItem("New...", handler=menu_new_file),
                MenuItem("Open...", handler=menu_open_file),
                MenuItem("-", disabled=True),
                MenuItem("Exit", handler=do_exit),
            ],
        ),
        MenuItem(
            "View",
            children=[MenuItem("Status Bar", handler=do_status_bar)],
        ),
        MenuItem(
            "Info",
            children=[MenuItem("About", handler=do_about)],
        ),
    ],
    floats=[
        Float(
            xcursor=True,
            ycursor=True,
            content=CompletionsMenu(max_height=16, scroll_offset=1),
        ),
    ],
    key_bindings=bindings,
)


style = Style.from_dict(
    {
        "status": "reverse",
        "shadow": "bg:#5E0035",
    }
)


combined_style = merge_styles([pt_style, style])

layout = Layout(root_container, focused_element=text_field)
menu_layout = Layout(menu_container, focused_element=menu_container)

application = Application(
    layout=layout,
    enable_page_navigation_bindings=True,
    style=combined_style,
    mouse_support=True,
    full_screen=True,
)

menu_app = Application(
    layout=menu_layout,
    enable_page_navigation_bindings=True,
    style=combined_style,
    mouse_support=True,
    full_screen=True,
)

def run_menu():
    menu_app.run()

def run_app():
    application.run()


if __name__ == "__main__":
    run_menu()