from __future__ import annotations

import logging
import threading
import time
import struct
from collections.abc import Callable

import ctypes
from ctypes import wintypes

import win32clipboard
import win32con

logger = logging.getLogger(__name__)

# --- Definiciones de Win32 via ctypes ---
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

IS_64BIT = ctypes.sizeof(ctypes.c_void_p) == 8
if IS_64BIT:
    LRESULT = ctypes.c_int64
    WPARAM = ctypes.c_uint64
    LPARAM = ctypes.c_int64
    ULONG_PTR = ctypes.c_uint64
else:
    LRESULT = ctypes.c_int32
    WPARAM = ctypes.c_uint32
    LPARAM = ctypes.c_int32
    ULONG_PTR = ctypes.c_uint32

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

# Estructuras para SendInput
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class INPUT_I(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("ii", INPUT_I)]

# Firmas
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

# Constantes
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
PM_REMOVE = 0x0001
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_RETURN = 0x0D
VK_V = 0x56
VK_MEDIA_PLAY_PAUSE = 0xB3

MODIFIER_VKS = (
    VK_SHIFT, VK_LSHIFT, VK_RSHIFT,
    VK_CONTROL, VK_LCONTROL, VK_RCONTROL,
    VK_MENU, VK_LMENU, VK_RMENU,
    VK_LWIN, VK_RWIN,
)

MODIFIER_NAMES = {
    VK_SHIFT: "Shift", VK_LSHIFT: "Left Shift", VK_RSHIFT: "Right Shift",
    VK_CONTROL: "Ctrl", VK_LCONTROL: "Left Ctrl", VK_RCONTROL: "Right Ctrl",
    VK_MENU: "Alt", VK_LMENU: "Left Alt", VK_RMENU: "Right Alt",
    VK_LWIN: "Left Win", VK_RWIN: "Right Win",
}

# Enviar KEYUP para variantes genéricas y laterales es intencional: si Windows
# o la app destino quedaron con un modificador lógicamente activo, esto sanea
# el estado antes del Ctrl+V. KEYUP sobre una tecla que no está pulsada es inocuo.
MODIFIER_RELEASE_VKS = (
    VK_LSHIFT, VK_RSHIFT, VK_SHIFT,
    VK_LCONTROL, VK_RCONTROL, VK_CONTROL,
    VK_LMENU, VK_RMENU, VK_MENU,
    VK_LWIN, VK_RWIN,
)

# --- Utilidades de Inyección ---

def set_clipboard_text(text: str, exclude_from_history: bool = True) -> None:
    """Pone texto en el portapapeles con opción de excluirlo del historial de Windows."""
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        
        # 1. Poner el texto Unicode
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        
        # 2. Metadatos para excluir del historial y la nube (Win+V)
        if exclude_from_history:
            fmt_history = win32clipboard.RegisterClipboardFormat("CanIncludeInClipboardHistory")
            fmt_cloud = win32clipboard.RegisterClipboardFormat("CanUploadToCloudClipboard")
            
            # 0 como DWORD (4 bytes)
            data_no = struct.pack("I", 0)
            win32clipboard.SetClipboardData(fmt_history, data_no)
            win32clipboard.SetClipboardData(fmt_cloud, data_no)
            
        win32clipboard.CloseClipboard()
    except Exception as e:
        logger.error("Error al manipular portapapeles: %s", e)
        try: win32clipboard.CloseClipboard()
        except: pass

def _is_key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _pressed_modifier_names() -> list[str]:
    return [MODIFIER_NAMES.get(vk, hex(vk)) for vk in MODIFIER_VKS if _is_key_down(vk)]


def wait_for_modifier_keys_released(timeout: float = 1.0, poll_interval: float = 0.01) -> bool:
    """Espera a que Ctrl/Alt/Shift/Win estén liberadas físicamente antes de pegar.

    Esto evita que el hotkey usado para detener el dictado contamine el Ctrl+V
    siguiente, por ejemplo convirtiéndolo en Ctrl+Alt+V.
    """
    deadline = time.monotonic() + timeout
    while True:
        pressed = _pressed_modifier_names()
        if not pressed:
            return True
        if time.monotonic() >= deadline:
            logger.warning("Timeout esperando liberación física de modificadores antes de pegar: %s", pressed)
            return False
        time.sleep(poll_interval)


def force_release_modifier_keys() -> bool:
    """Sanea modificadores atascados enviando KEYUP explícito para Ctrl/Alt/Shift/Win.

    GetAsyncKeyState detecta estado físico, pero el síntoma reportado es que Alt
    puede quedar lógicamente activo en Windows o en la app destino. Por eso,
    además de esperar a que el usuario suelte las teclas, emitimos KEYUP para los
    modificadores antes de inyectar Ctrl+V.
    """
    inputs = []
    for vk in MODIFIER_RELEASE_VKS:
        ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        inputs.append(INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=ki)))

    n = len(inputs)
    buffer = (INPUT * n)(*inputs)

    ctypes.set_last_error(0)
    sent = user32.SendInput(n, buffer, ctypes.sizeof(INPUT))
    err = ctypes.get_last_error()

    if sent != n:
        logger.warning(
            "No se pudieron liberar todos los modificadores. requested=%d sent=%d last_error=%d",
            n,
            sent,
            err,
        )
        return False

    logger.debug("Modificadores saneados antes del pegado. sent=%d", sent)
    return True


def send_paste_command(retries: int = 1, delay: float = 0.08) -> bool:
    """Simula Ctrl+V usando SendInput y reporta si Windows aceptó la inyección."""
    cmds = [
        (VK_CONTROL, 0),                       # Ctrl Down
        (VK_V, 0),                             # V Down
        (VK_V, KEYEVENTF_KEYUP),               # V Up
        (VK_CONTROL, KEYEVENTF_KEYUP),         # Ctrl Up
    ]

    inputs = []
    for vk, flags in cmds:
        ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
        inputs.append(INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=ki)))

    n = len(inputs)
    buffer = (INPUT * n)(*inputs)

    for attempt in range(retries + 1):
        # Dos pasos distintos:
        # 1. esperar a que el usuario suelte físicamente Ctrl/Alt/Shift/Win;
        # 2. emitir KEYUP para limpiar estados lógicos atascados, sobre todo Alt.
        wait_for_modifier_keys_released()
        force_release_modifier_keys()
        time.sleep(0.04)

        ctypes.set_last_error(0)
        sent = user32.SendInput(n, buffer, ctypes.sizeof(INPUT))
        err = ctypes.get_last_error()

        if sent == n:
            logger.info("Ctrl+V enviado por SendInput. attempt=%d sent=%d", attempt + 1, sent)
            return True

        logger.warning(
            "SendInput no envió todos los eventos de Ctrl+V. attempt=%d requested=%d sent=%d last_error=%d",
            attempt + 1, n, sent, err,
        )
        if attempt < retries:
            time.sleep(delay)

    return False


def send_media_play_pause_key() -> bool:
    """Envía la tecla multimedia Play/Pause mediante SendInput."""
    cmds = [
        (VK_MEDIA_PLAY_PAUSE, 0),
        (VK_MEDIA_PLAY_PAUSE, KEYEVENTF_KEYUP),
    ]
    inputs = []
    for vk, flags in cmds:
        ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
        inputs.append(INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=ki)))

    n = len(inputs)
    buffer = (INPUT * n)(*inputs)
    ctypes.set_last_error(0)
    sent = user32.SendInput(n, buffer, ctypes.sizeof(INPUT))
    return sent == n

class ClipboardGuard:
    """Context Manager para respaldar y restaurar el portapapeles."""
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.backup = {}

    def __enter__(self):
        if not self.enabled:
            return self
            
        try:
            win32clipboard.OpenClipboard()
            # Iterar todos los formatos disponibles y guardar su contenido
            fmt = win32clipboard.EnumClipboardFormats(0)
            while fmt:
                try:
                    data = win32clipboard.GetClipboardData(fmt)
                    # Solo guardamos si el dato es serializable o manejable (bytes/str)
                    # Algunos formatos complejos pueden fallar
                    self.backup[fmt] = data
                except Exception:
                    pass
                fmt = win32clipboard.EnumClipboardFormats(fmt)
            win32clipboard.CloseClipboard()
        except Exception as e:
            logger.warning("No se pudo respaldar el portapapeles: %s", e)
            try: win32clipboard.CloseClipboard()
            except: pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.enabled or not self.backup:
            return
            
        try:
            # Pequeña pausa para que la app destino procese el Pegado antes de restaurar
            time.sleep(0.08)
            
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            for fmt, data in self.backup.items():
                try:
                    win32clipboard.SetClipboardData(fmt, data)
                except Exception:
                    pass
            win32clipboard.CloseClipboard()
        except Exception as e:
            logger.warning("No se pudo restaurar el portapapeles: %s", e)
            try: win32clipboard.CloseClipboard()
            except: pass


# --- Gestión de Hotkeys (WH_KEYBOARD_LL) ---

class Win32HotkeyManager:
    MODIFIERS = {
        "ctrl": VK_CONTROL, "control": VK_CONTROL,
        "alt": VK_MENU, "shift": VK_SHIFT,
        "win": VK_LWIN, "windows": VK_LWIN, "cmd": VK_LWIN,
    }

    def __init__(self, hotkey_str: str, on_press: Callable[[], None], on_release: Callable[[], None] | None = None):
        self.hotkey_str = hotkey_str.lower()
        self.on_press = on_press
        self.on_release = on_release
        self._target_vk, self._target_modifiers = self._parse_hotkey(self.hotkey_str)
        self._active_modifiers = set()
        self._is_pressed = False
        self._hook = None
        self._thread = None
        self._stop_event = threading.Event()
        self._hook_proc_ptr = None
        logger.info("Win32HotkeyManager inicializado para: %s", self.hotkey_str)

    def _parse_hotkey(self, hotkey_str: str) -> tuple[int, set[int]]:
        parts = [p.strip() for p in hotkey_str.split("+")]
        modifiers = set()
        vk = 0
        for part in parts:
            if part in self.MODIFIERS:
                modifiers.add(self.MODIFIERS[part])
            else:
                res = user32.VkKeyScanW(ord(part[0]))
                if res != -1: vk = res & 0xFF
        return vk, modifiers

    def _get_modifier_vk(self, vk: int) -> int | None:
        if vk in (0x11, 0xA2, 0xA3): return VK_CONTROL
        if vk in (0x12, 0xA4, 0xA5): return VK_MENU
        if vk in (0x10, 0xA0, 0xA1): return VK_SHIFT
        if vk in (0x5B, 0x5C): return VK_LWIN
        return None

    def _hook_proc(self, nCode, wParam, lParam):
        if nCode >= 0:
            vk_code = ctypes.c_uint32.from_address(lParam).value
            is_down = wParam in (0x0100, 0x0104) # WM_KEYDOWN/SYSKEYDOWN
            is_up = wParam in (0x0101, 0x0105)   # WM_KEYUP/SYSKEYUP
            mod_vk = self._get_modifier_vk(vk_code)
            if is_down:
                if mod_vk: self._active_modifiers.add(mod_vk)
                elif vk_code == self._target_vk:
                    if all(m in self._active_modifiers for m in self._target_modifiers):
                        if not self._is_pressed:
                            self._is_pressed = True
                            threading.Thread(target=self.on_press, daemon=True).start()
            elif is_up:
                if mod_vk: self._active_modifiers.discard(mod_vk)
                elif vk_code == self._target_vk:
                    if self._is_pressed:
                        self._is_pressed = False
                        if self.on_release: threading.Thread(target=self.on_release, daemon=True).start()
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _run(self):
        self._hook_proc_ptr = HOOKPROC(self._hook_proc)
        h_mod = 0
        self._hook = user32.SetWindowsHookExW(13, self._hook_proc_ptr, h_mod, 0) # 13 = WH_KEYBOARD_LL
        if not self._hook: return
        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1): # 1 = PM_REMOVE
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else: time.sleep(0.01)
        user32.UnhookWindowsHookEx(self._hook)

    def register(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def unregister(self) -> None:
        self._stop_event.set()
        if self._thread: self._thread.join(timeout=1.0)

class HotkeyManager(Win32HotkeyManager):
    def __init__(self, hotkey: str, callback: Callable[[], None]):
        super().__init__(hotkey, on_press=callback)
