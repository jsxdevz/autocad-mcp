from types import SimpleNamespace as NS

import pytest

from autocad_mcp import cad, tools_read


def busy():
    return Exception(-2147418111, "rejected")


def test_retry_succeeds_after_busy():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise busy()
        return "ok"

    assert cad.with_retry(fn, attempts=5, delay=0) == "ok"
    assert calls["n"] == 3


def test_retry_gives_up_with_clear_error():
    def fn():
        raise busy()

    with pytest.raises(cad.CadError, match="busy"):
        cad.with_retry(fn, attempts=3, delay=0)


def test_retry_does_not_swallow_other_errors():
    def fn():
        raise ValueError("x")

    with pytest.raises(ValueError):
        cad.with_retry(fn, attempts=3, delay=0)


def test_autocad_not_running(monkeypatch):
    win32com = pytest.importorskip("win32com.client")

    def boom(_):
        raise OSError("nope")

    monkeypatch.setattr(win32com, "GetActiveObject", boom)
    with pytest.raises(cad.CadError, match="not running"):
        cad.get_app()


class Coll:
    def __init__(self, items):
        self.items = items
        self.Count = len(items)

    def Item(self, i):
        return self.items[i]


def fake_doc():
    bb = lambda: ((0, 0, 0), (1, 1, 0))  # noqa: E731
    layers = Coll([NS(Name="0", Color=7, LayerOn=True, Lock=False),
                   NS(Name="WALL", Color=1, LayerOn=False, Lock=True)])
    ms = Coll([NS(Handle="A1", ObjectName="AcDbPolyline", Layer="WALL", GetBoundingBox=bb),
               NS(Handle="A2", ObjectName="AcDbText", Layer="TXT", TextString="hi",
                  InsertionPoint=(1, 2, 0), GetBoundingBox=bb)])
    poly = NS(ObjectName="AcDbPolyline", Coordinates=(0, 0, 4, 0, 4, 3, 0, 3),
              Closed=True, Area=12.0, Length=14.0)
    return NS(Name="a.dwg", FullName="C:/a.dwg", Saved=True, Layers=layers, ModelSpace=ms,
              GetVariable=lambda n: 4, HandleToObject=lambda h: poly)


@pytest.fixture
def doc(monkeypatch):
    d = fake_doc()
    monkeypatch.setattr(cad, "get_doc", lambda: d)
    monkeypatch.setattr(cad, "get_modelspace", lambda: d.ModelSpace)
    return d


def test_drawing_info(doc):
    info = tools_read.get_drawing_info()
    assert info["name"] == "a.dwg" and info["object_count"] == 2 and info["insunits"] == 4


def test_list_layers(doc):
    assert tools_read.list_layers()[1] == {"name": "WALL", "color": 1, "on": False, "locked": True}


def test_list_objects_filters(doc):
    assert len(tools_read.list_objects()["objects"]) == 2
    r = tools_read.list_objects(layer="WALL", type="polyline")["objects"]
    assert [o["handle"] for o in r] == ["A1"]


def test_get_polyline(doc):
    p = tools_read.get_polyline("A1")
    assert p["points"] == [[0, 0], [4, 0], [4, 3], [0, 3]] and p["area"] == 12.0 and p["closed"]


def test_get_text(doc):
    assert tools_read.get_text_in_layer("TXT")[0]["text"] == "hi"
