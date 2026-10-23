"""Exercise talent borders and both tooltip paths in Lua 5.1."""
import pytest

import build_era_addon as B
from test_build_era_addon import lua_runtime, load_outputs


@pytest.fixture(scope="module")
def outputs():
    return B.build(check=True)


@pytest.fixture(params=["enUS", "ruRU"])
def ui(request, outputs):
    lua = lua_runtime()
    lua.globals().GetLocale = lambda: request.param
    lua.execute((B.ROOT / "tools/fixtures/era_talentui_render.lua").read_text(encoding="utf-8"))
    load_outputs(lua, outputs)
    return lua


def rgb(texture):
    return tuple(texture.color.values())


def test_visible_border_tracks_available_locked_and_maxed_states(ui):
    view, state, buttons = ui.globals().TestTalentView(False)
    et = ui.globals().EraTalents
    assert rgb(buttons[1].normal) == (0.1, 1, 0.1)
    assert rgb(buttons[2].normal) == (1, 1, 1)
    state.ranks[1] = 5
    et.RenderView(view, state, 8)
    assert rgb(buttons[1].normal) == (1, 0.82, 0)
    assert rgb(buttons[2].normal) == (0.1, 1, 0.1)
    state.availPts = 0
    et.RenderView(view, state, 8)
    assert rgb(buttons[2].normal) == (1, 1, 1)
    view.readOnly = True
    state.availPts = 1
    et.RenderView(view, state, 8)
    assert rgb(buttons[2].normal) == (1, 1, 1)


@pytest.mark.parametrize("node_id", [2, 3])
def test_both_tooltip_paths_explain_requirements_and_refresh(ui, node_id):
    view, state, buttons = ui.globals().TestTalentView(False)
    et = ui.globals().EraTalents
    tooltip = ui.globals().GameTooltip
    buttons[node_id].scripts.OnEnter(buttons[node_id])
    expected_points = ui.eval("string.format")(et.L.REQUIRES_TREE_POINTS, 5, "Test tree", 5)
    expected_talent = ui.eval("string.format")(et.L.REQUIRES_TALENT, 5, "Foundation")
    lines = [tuple(line.values()) for line in tooltip.lines.values()]
    assert (expected_points, 1, 0.2, 0.2, True) in lines
    assert (expected_talent, 1, 0.2, 0.2, True) in lines
    # Repainting after SYNC must refresh the hovered tooltip, including the deficit.
    state.ranks[1] = 4
    et.RenderView(view, state, 8)
    texts = [line[1] for line in tooltip.lines.values()]
    assert ui.eval("string.format")(et.L.REQUIRES_TREE_POINTS, 5, "Test tree", 1) in texts
    state.ranks[1] = 5
    et.RenderView(view, state, 8)
    texts = [line[1] for line in tooltip.lines.values()]
    assert expected_talent not in texts
    assert not any(tuple(line.values())[1:] == (1, 0.2, 0.2, True)
                   for line in tooltip.lines.values())


@pytest.mark.parametrize("node_id", [2, 3])
def test_inspect_has_no_learning_requirements(ui, node_id):
    _, _, buttons = ui.globals().TestTalentView(True)
    buttons[node_id].scripts.OnEnter(buttons[node_id])
    assert not any(tuple(line.values())[1:] == (1, 0.2, 0.2, True)
                   for line in ui.globals().GameTooltip.lines.values())
