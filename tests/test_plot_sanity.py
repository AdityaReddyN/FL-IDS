import pandas as pd

from scripts.plot_attack_v3_sanity import render_track_svg


def test_track_plot_shows_original_and_modified_tracks_on_shared_scale():
    rows = pd.DataFrame({
        "orig_lat": [0.0, 1.0], "orig_lon": [0.0, 1.0],
        "mod_lat": [10.0, 11.0], "mod_lon": [10.0, 11.0],
    })
    svg = render_track_svg(rows, "constant_deviation", 5)
    assert "stroke=\"#3569a8\"" in svg
    assert "stroke=\"#d04a3a\"" in svg
    assert "original" in svg and "modified" in svg
    lines = [line for line in svg.splitlines() if "<polyline" in line]
    assert len(lines) == 2
    assert lines[0] != lines[1]
