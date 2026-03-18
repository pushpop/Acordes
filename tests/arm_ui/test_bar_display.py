# ABOUTME: Unit tests for BarDisplay widget (Sprint 2).
# ABOUTME: Verifies fill width proportional to value and clamp behavior.

import pygame
import pytest
from unittest.mock import patch, call


def _make_bar(value=0.5):
    from arm_ui.widgets.bar_display import BarDisplay
    rect = pygame.Rect(0, 0, 300, 40)
    return BarDisplay(rect, "Test", value)


def test_initial_value_stored():
    bar = _make_bar(0.75)
    assert bar.value == pytest.approx(0.75)


def test_set_value_updates():
    bar = _make_bar(0.0)
    bar.set_value(0.6)
    assert bar.value == pytest.approx(0.6)


def test_value_clamps_above_one():
    bar = _make_bar(1.5)
    assert bar.value == pytest.approx(1.0)


def test_value_clamps_below_zero():
    bar = _make_bar(-0.5)
    assert bar.value == pytest.approx(0.0)


def test_set_value_clamps_above_one():
    bar = _make_bar()
    bar.set_value(2.0)
    assert bar.value == pytest.approx(1.0)


def test_set_value_clamps_below_zero():
    bar = _make_bar()
    bar.set_value(-1.0)
    assert bar.value == pytest.approx(0.0)


def test_draw_calls_rect_for_background(pygame_session):
    bar = _make_bar(0.5)
    surf = pygame.Surface((300, 40))
    with patch("pygame.draw.rect") as mock_rect:
        bar.draw(surf)
    # Should be called at least twice: background and fill
    assert mock_rect.call_count >= 2


def test_draw_fill_width_proportional_to_value(pygame_session):
    """Fill rect width should equal bar_total * value."""
    from arm_ui.widgets.bar_display import BarDisplay
    bar = BarDisplay(pygame.Rect(0, 0, 300, 40), "X", 0.5)
    surf = pygame.Surface((300, 40))

    drawn_rects = []
    with patch("pygame.draw.rect", side_effect=lambda s, c, r, *a, **kw: drawn_rects.append(r)):
        bar.draw(surf)

    # Find the fill rect (no width arg = filled rect)
    bar_total = 300 - bar._LABEL_WIDTH - bar._PCT_WIDTH - 4
    expected_fill_w = int(bar_total * 0.5)

    fill_rects = [r for r in drawn_rects if isinstance(r, (tuple, list)) and r[2] == expected_fill_w]
    assert len(fill_rects) >= 1, (
        f"Expected fill rect with width {expected_fill_w}, got rects: {drawn_rects}"
    )


def test_draw_zero_value_no_fill_rect(pygame_session):
    """A value of 0.0 should not draw any fill rect."""
    from arm_ui.widgets.bar_display import BarDisplay
    bar = BarDisplay(pygame.Rect(0, 0, 300, 40), "X", 0.0)
    surf = pygame.Surface((300, 40))

    call_count = 0
    orig_draw = pygame.draw.rect.__wrapped__ if hasattr(pygame.draw.rect, "__wrapped__") else None

    drawn_rects = []
    with patch("pygame.draw.rect", side_effect=lambda s, c, r, *a, **kw: drawn_rects.append(r)):
        bar.draw(surf)

    bar_total = 300 - bar._LABEL_WIDTH - bar._PCT_WIDTH - 4
    # Background + border outline are drawn; fill rect is skipped when fill_w == 0
    # (2 rects: background fill, then border outline)
    assert len(drawn_rects) == 2
