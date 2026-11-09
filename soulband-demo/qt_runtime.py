"""Load Windows' ICU before Qt, avoiding Anaconda/Poppler DLL name clashes."""
import ctypes
import os
import sys
from pathlib import Path

_SYSTEM_ICU = []


def prepare_qt_runtime():
    if sys.platform != "win32" or _SYSTEM_ICU:
        return
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    for name in ("icuuc.dll", "icuin.dll"):
        path = system32 / name
        if path.is_file():
            # These system APIs use unversioned ICU exports. Conda's DLLs use
            # version suffixes and cannot satisfy Qt 6.10's imports.
            _SYSTEM_ICU.append(ctypes.WinDLL(str(path), winmode=0x00000800))
