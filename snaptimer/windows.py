"""Windows shell integration. Tk owns the message loop for both windows."""

import ctypes as ct
from ctypes import wintypes as wt
from collections import deque
from collections.abc import Callable, Sequence
from time import monotonic
from uuid import uuid4

from .settings import ASSETS
from .timer import State

user32 = ct.WinDLL("user32", use_last_error=True)
shell32 = ct.WinDLL("shell32", use_last_error=True)
kernel32 = ct.WinDLL("kernel32", use_last_error=True)
winmm = ct.WinDLL("winmm")
LRESULT = ct.c_ssize_t
WNDPROC = ct.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WindowClass(ct.Structure):
    _fields_ = [
        ("style", wt.UINT), ("procedure", WNDPROC),
        ("class_extra", ct.c_int), ("window_extra", ct.c_int),
        ("instance", wt.HINSTANCE), ("icon", wt.HICON), ("cursor", wt.HANDLE),
        ("background", wt.HBRUSH), ("menu_name", wt.LPCWSTR), ("name", wt.LPCWSTR),
    ]


class NotifyIconData(ct.Structure):
    _fields_ = [
        ("size", wt.DWORD), ("window", wt.HWND), ("icon_id", wt.UINT),
        ("flags", wt.UINT), ("callback_message", wt.UINT), ("icon", wt.HICON),
        ("tip", wt.WCHAR * 128), ("state", wt.DWORD), ("state_mask", wt.DWORD),
        ("info", wt.WCHAR * 256), ("version_or_timeout", wt.UINT),
        ("info_title", wt.WCHAR * 64), ("info_flags", wt.DWORD),
        ("guid", ct.c_ubyte * 16), ("balloon_icon", wt.HICON),
    ]


class MonitorInfo(ct.Structure):
    _fields_ = [
        ("size", wt.DWORD), ("monitor", wt.RECT), ("work", wt.RECT),
        ("flags", wt.DWORD),
    ]


class TitleBarInfo(ct.Structure):
    _fields_ = [
        ("size", wt.DWORD), ("bounds", wt.RECT),
        ("states", wt.DWORD * 6), ("buttons", wt.RECT * 6),
    ]


def _api(dll, name, result, *arguments):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = arguments
    return function


SetDllDirectory = _api(kernel32, "SetDllDirectoryW", wt.BOOL, wt.LPCWSTR)
SendMediaCommand = _api(winmm, "mciSendStringW", wt.DWORD, wt.LPCWSTR, wt.LPWSTR, wt.UINT, wt.HWND)
GetMediaError = _api(winmm, "mciGetErrorStringW", wt.BOOL, wt.DWORD, wt.LPWSTR, wt.UINT)
GetModuleHandle = _api(kernel32, "GetModuleHandleW", wt.HMODULE, wt.LPCWSTR)
RegisterClass = _api(user32, "RegisterClassW", wt.ATOM, ct.POINTER(WindowClass))
UnregisterClass = _api(user32, "UnregisterClassW", wt.BOOL, wt.LPCWSTR, wt.HINSTANCE)
CreateWindow = _api(
    user32, "CreateWindowExW", wt.HWND,
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ct.c_int, ct.c_int, ct.c_int, ct.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
)
DefWindowProc = _api(user32, "DefWindowProcW", LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
DestroyWindow = _api(user32, "DestroyWindow", wt.BOOL, wt.HWND)
RegisterMessage = _api(user32, "RegisterWindowMessageW", wt.UINT, wt.LPCWSTR)
LoadImage = _api(user32, "LoadImageW", wt.HANDLE, wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ct.c_int, ct.c_int, wt.UINT)
DestroyIcon = _api(user32, "DestroyIcon", wt.BOOL, wt.HICON)
NotifyIcon = _api(shell32, "Shell_NotifyIconW", wt.BOOL, wt.DWORD, ct.POINTER(NotifyIconData))
GetCursorPos = _api(user32, "GetCursorPos", wt.BOOL, ct.POINTER(wt.POINT))
CreatePopupMenu = _api(user32, "CreatePopupMenu", wt.HMENU)
AppendMenu = _api(user32, "AppendMenuW", wt.BOOL, wt.HMENU, wt.UINT, wt.WPARAM, wt.LPCWSTR)
TrackPopupMenu = _api(
    user32, "TrackPopupMenu", wt.UINT, wt.HMENU, wt.UINT, ct.c_int,
    ct.c_int, ct.c_int, wt.HWND, ct.POINTER(wt.RECT),
)
DestroyMenu = _api(user32, "DestroyMenu", wt.BOOL, wt.HMENU)
SetForegroundWindow = _api(user32, "SetForegroundWindow", wt.BOOL, wt.HWND)
PostMessage = _api(user32, "PostMessageW", wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
SendMessage = _api(user32, "SendMessageW", LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

GetAncestor = _api(user32, "GetAncestor", wt.HWND, wt.HWND, wt.UINT)
GetCapture = _api(user32, "GetCapture", wt.HWND)
GetClientRect = _api(user32, "GetClientRect", wt.BOOL, wt.HWND, ct.POINTER(wt.RECT))
GetSystemMetrics = _api(user32, "GetSystemMetrics", ct.c_int, ct.c_int)
GetWindowRect = _api(user32, "GetWindowRect", wt.BOOL, wt.HWND, ct.POINTER(wt.RECT))
IsWindowEnabled = _api(user32, "IsWindowEnabled", wt.BOOL, wt.HWND)
ScreenToClient = _api(user32, "ScreenToClient", wt.BOOL, wt.HWND, ct.POINTER(wt.POINT))
WindowFromPoint = _api(user32, "WindowFromPoint", wt.HWND, wt.POINT)
MonitorFromPoint = _api(user32, "MonitorFromPoint", wt.HMONITOR, wt.POINT, wt.DWORD)
MonitorFromWindow = _api(user32, "MonitorFromWindow", wt.HMONITOR, wt.HWND, wt.DWORD)
GetMonitorInfo = _api(user32, "GetMonitorInfoW", wt.BOOL, wt.HMONITOR, ct.POINTER(MonitorInfo))
SetWindowPos = _api(
    user32, "SetWindowPos", wt.BOOL, wt.HWND, wt.HWND,
    ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.UINT,
)
SetProcessDPIAware = _api(user32, "SetProcessDPIAware", wt.BOOL)

GetDoubleClickTime = _api(user32, 'GetDoubleClickTime', wt.UINT)

NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETFOCUS, NIM_SETVERSION = range(5)
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_SHOWTIP = 1, 2, 4, 0x10, 0x80
WM_TRAY = 0x8001
WM_CONTEXTMENU = 0x007B
WM_GETTITLEBARINFOEX = 0x033F
SM_CXSIZE, SM_CXMINTRACK = 30, 34
WM_LBUTTONUP, WM_RBUTTONUP = 0x0202, 0x0205
NIN_SELECT, NIN_KEYSELECT = 0x0400, 0x0401

ICONS = {
    State.READY: "snaptimer.ico",
    State.RUNNING: "snaptimer_run.ico",
    State.PAUSED: "snaptimer_pause.ico",
    State.FINISHED: "snaptimer_done.ico",
}


class Tray:
    def __init__(self, activate: Callable, menu: Callable):
        self._pending: deque[Callable] = deque()
        self._activate = activate
        self._menu = menu
        self._state = State.READY
        self._tip = "SnapTimer"
        self._icons = {}
        self._version4 = False
        self._next_registration = 0.0
        self.available = False
        self._instance = GetModuleHandle(None)
        self._name = f"SnapTimer.Tray.{uuid4().hex}"
        self._taskbar_created = RegisterMessage("TaskbarCreated")
        self._procedure = WNDPROC(self._window_proc)
        window_class = WindowClass(
            instance=self._instance, name=self._name, procedure=self._procedure,
        )
        if not RegisterClass(ct.byref(window_class)):
            raise ct.WinError(ct.get_last_error())

        # A hidden top-level window receives the broadcast when Explorer restarts.
        self._window = CreateWindow(
            0, self._name, "", 0, 0, 0, 0, 0, None, None, self._instance, None,
        )
        if not self._window:
            error = ct.WinError(ct.get_last_error())
            UnregisterClass(self._name, self._instance)
            raise error

        try:
            for state, name in ICONS.items():
                image = LoadImage(None, str(ASSETS / "images" / name), 1, 0, 0, 0x10 | 0x40)
                if not image:
                    raise ct.WinError(ct.get_last_error())
                self._icons[state] = image
            self._register_icon()
        except OSError:
            self.close()
            raise

    def _data(self, flags=0) -> NotifyIconData:
        return NotifyIconData(
            size=ct.sizeof(NotifyIconData), window=self._window, icon_id=1, flags=flags,
        )

    def _appearance(self) -> NotifyIconData:
        data = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        data.callback_message = WM_TRAY
        data.icon = self._icons[self._state]
        data.tip = self._tip
        return data

    def _register_icon(self) -> None:
        self._next_registration = monotonic() + 2
        self.available = bool(NotifyIcon(NIM_ADD, ct.byref(self._appearance())))
        if self.available:
            data = self._data()
            data.version_or_timeout = 4
            self._version4 = bool(NotifyIcon(NIM_SETVERSION, ct.byref(data)))

    def update(self, state: State, tip: str) -> None:
        changed = (state, tip) != (self._state, self._tip)
        self._state, self._tip = state, tip
        if self.available and changed:
            self.available = bool(NotifyIcon(NIM_MODIFY, ct.byref(self._appearance())))
        if not self.available and monotonic() >= self._next_registration:
            self._register_icon()

    def notify(self, title: str, message: str) -> bool:
        data = self._data(NIF_INFO)
        # Native limits are expressed in UTF-16 code units.
        data.info_title = title.encode("utf-16-le")[:126].decode("utf-16-le", errors="ignore")
        data.info = message.encode("utf-16-le")[:510].decode("utf-16-le", errors="ignore")
        data.info_flags = 1
        return bool(self.available and NotifyIcon(NIM_MODIFY, ct.byref(data)))

    def _window_proc(self, window, message, wparam, lparam):
        if self._taskbar_created and message == self._taskbar_created:
            self._pending.append(self._register_icon)
            return 0
        if message == WM_TRAY:
            event = lparam & 0xFFFF
            if self._version4:
                if event in (NIN_SELECT, NIN_KEYSELECT):
                    self._pending.append(self._activate)
                elif event == WM_CONTEXTMENU:
                    self._pending.append(self._menu)
            elif event == WM_LBUTTONUP:
                self._pending.append(self._activate)
            elif event == WM_RBUTTONUP:
                self._pending.append(self._menu)
            return 0
        return DefWindowProc(window, message, wparam, lparam)

    def dispatch(self) -> None:
        # Tk can be inside Tcl_DoOneEvent when Windows calls the window procedure.
        # Enter Tk only after control has returned to the scheduled Python callback.
        while self._pending:
            self._pending.popleft()()

    def show_menu(self, time_text: str, items: Sequence[tuple[str, Callable] | None]) -> None:
        menu = CreatePopupMenu()
        if not menu:
            return
        selected = 0
        try:
            AppendMenu(menu, 0x0003, 0, time_text)  # Disabled time heading
            AppendMenu(menu, 0x0800, 0, None)      # Separator
            for index, item in enumerate(items, 1):
                if item is None:
                    AppendMenu(menu, 0x0800, 0, None)
                else:
                    AppendMenu(menu, 0, index, item[0])
            point = wt.POINT()
            GetCursorPos(ct.byref(point))
            SetForegroundWindow(self._window)
            selected = TrackPopupMenu(menu, 0x0100 | 0x0002, point.x, point.y, 0, self._window, None)
            PostMessage(self._window, 0, 0, 0)
            NotifyIcon(NIM_SETFOCUS, ct.byref(self._data()))
        finally:
            DestroyMenu(menu)
        if selected:
            item = items[selected - 1]
            if item is not None:
                item[1]()

    def close(self) -> None:
        self._pending.clear()
        if self.available:
            NotifyIcon(NIM_DELETE, ct.byref(self._data()))
            self.available = False
        DestroyWindow(self._window)
        UnregisterClass(self._name, self._instance)
        for icon in self._icons.values():
            DestroyIcon(icon)


def window_handle(widget_id: int) -> int:
    return GetAncestor(widget_id, 2)


def window_bounds(widget_id: int) -> wt.RECT:
    rect = wt.RECT()
    GetWindowRect(window_handle(widget_id), ct.byref(rect))
    return rect


def window_monitor(widget_id: int) -> int:
    return MonitorFromWindow(window_handle(widget_id), 2)


def minimum_caption_width(widget_id: int) -> int:
    window = window_handle(widget_id)
    info = TitleBarInfo(size=ct.sizeof(TitleBarInfo))
    SendMessage(window, WM_GETTITLEBARINFOEX, 0, ct.addressof(info))
    maximize, close = info.buttons[3], info.buttons[5]
    # Windows can clip the minimize button at narrow widths. Use the other two buttons to size the row.
    button_width = max(maximize.right - maximize.left, close.right - close.left)
    if button_width <= 0:
        return GetSystemMetrics(SM_CXMINTRACK) + GetSystemMetrics(SM_CXSIZE)
    client = wt.RECT()
    GetClientRect(window, ct.byref(client))
    # Leave a caption drag area about half as wide as a button, in addition to the icon and buttons.
    return client.right - (close.right - info.bounds.left) + 3 * button_width + button_width // 2


def pointer_over_window(widget_id: int) -> bool | None:
    window = window_handle(widget_id)
    point = wt.POINT()
    # Wait for mouse drags, native menus and modal dialogs to release the window.
    if GetCapture() or not IsWindowEnabled(window) or not GetCursorPos(ct.byref(point)):
        return None
    hovered = WindowFromPoint(point)
    if not hovered or window_handle(hovered) != window:
        return False
    client = wt.RECT()
    if not GetClientRect(window, ct.byref(client)) or not ScreenToClient(window, ct.byref(point)):
        return None
    if 0 <= point.x < client.right and 0 <= point.y < client.bottom:
        return True
    # Keep the current layout while the pointer uses the caption, menu, or resize border.
    return None


def place_window(widget_id: int, position: int, saved_x: int, saved_y: int) -> None:
    window = window_handle(widget_id)
    bounds = window_bounds(widget_id)
    target = wt.POINT()
    if position == 1:
        target.x, target.y = saved_x, saved_y
    else:
        GetCursorPos(ct.byref(target))
    monitor = MonitorFromPoint(target, 2)
    info = MonitorInfo(size=ct.sizeof(MonitorInfo))
    if not GetMonitorInfo(monitor, ct.byref(info)):
        return

    work = info.work
    right = max(work.left, work.right - (bounds.right - bounds.left))
    bottom = max(work.top, work.bottom - (bounds.bottom - bounds.top))
    position_coords = {
        0: ((work.left + right) // 2, (work.top + bottom) // 2),
        1: (min(right, max(work.left, saved_x)), min(bottom, max(work.top, saved_y))),
        2: (work.left, work.top),
        3: (right, work.top),
        4: (work.left, bottom),
        5: (right, bottom),
    }
    x, y = position_coords[position]
    SetWindowPos(window, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)

