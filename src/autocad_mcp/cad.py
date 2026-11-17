"""Thin wrapper over AutoCAD COM: connection, retry, point helpers, undo groups."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator, TypeVar

from . import config

log = logging.getLogger(__name__)
T = TypeVar("T")

# RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER
_BUSY_HRESULTS = {-2147418111, -2147417846}


class CadError(RuntimeError):
    """Error with a short, user-safe message."""


def _is_busy(exc: BaseException) -> bool:
    args = getattr(exc, "args", ())
    return bool(args) and args[0] in _BUSY_HRESULTS


def with_retry(fn: Callable[[], T], attempts: int | None = None,
               delay: float | None = None) -> T:
    """Call fn, retrying while AutoCAD is busy (RPC_E_CALL_REJECTED)."""
    attempts = attempts or config.RETRY_ATTEMPTS
    delay = config.RETRY_DELAY_S if delay is None else delay
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not _is_busy(exc):
                raise
            if i < attempts - 1:
                log.warning("AutoCAD busy, retry %d/%d", i + 1, attempts - 1)
                time.sleep(delay)
                continue
            raise CadError("AutoCAD is busy (a dialog or command may be open)") from exc
    raise AssertionError("unreachable")


def get_app() -> Any:
    try:
        import win32com.client
        return win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception as exc:  # noqa: BLE001
        raise CadError("AutoCAD is not running") from exc


def get_doc() -> Any:
    app = get_app()
    try:
        doc = with_retry(lambda: app.ActiveDocument)
    except CadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CadError("No active drawing in AutoCAD") from exc
    if doc is None:
        raise CadError("No active drawing in AutoCAD")
    return doc


def get_modelspace() -> Any:
    return with_retry(lambda: get_doc().ModelSpace)


def to_point(x: float, y: float, z: float = 0.0) -> Any:
    """3-double VARIANT array, as AutoCAD COM requires."""
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                                   (float(x), float(y), float(z)))


def to_flat_2d(points: Iterable[tuple[float, float]]) -> Any:
    """[x1,y1,x2,y2,...] VARIANT for AddLightWeightPolyline."""
    import pythoncom
    import win32com.client
    flat: list[float] = []
    for p in points:
        flat.extend((float(p[0]), float(p[1])))
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)


def ensure_layer(name: str, color: int | None = None) -> str:
    doc = get_doc()
    layers = doc.Layers
    try:
        layer = with_retry(lambda: layers.Item(name))
    except Exception:  # noqa: BLE001 - not found
        layer = with_retry(lambda: layers.Add(name))
    if color is not None:
        layer.Color = int(color)
    return name


@contextmanager
def undo_group() -> Iterator[None]:
    """One Undo step for everything inside. No-op if StartUndoMark is unavailable."""
    doc = get_doc()
    started = False
    try:
        doc.StartUndoMark()
        started = True
    except Exception:  # noqa: BLE001
        log.warning("StartUndoMark unavailable; continuing without undo group")
    try:
        yield
    finally:
        if started:
            try:
                doc.EndUndoMark()
            except Exception:  # noqa: BLE001
                log.warning("EndUndoMark failed")
