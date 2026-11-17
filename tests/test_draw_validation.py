import pytest

from autocad_mcp import cad, tools_draw


@pytest.mark.parametrize("call", [
    lambda: tools_draw.draw_circle([0, 0], 0),
    lambda: tools_draw.draw_circle([0, "x"], 1),
    lambda: tools_draw.draw_rectangle([0, 0], -1, 2),
    lambda: tools_draw.draw_polyline([[0, 0]]),
    lambda: tools_draw.draw_polyline([[0, 0]] * 10_001),
    lambda: tools_draw.draw_line([0], [1, 1]),
    lambda: tools_draw.add_text([0, 0], "", 1),
    lambda: tools_draw.add_text([0, 0], "a", float("nan")),
    lambda: tools_draw.create_layer(" "),
    lambda: tools_draw.create_layer("A", 999),
])
def test_invalid_input_rejected_before_touching_cad(call):
    with pytest.raises(cad.CadError):
        call()
