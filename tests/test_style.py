import pytest

from mock import Mock, call

from rig_par_diagram.style import Style

import cairocffi as cairo

class MyException(Exception):
    pass


def test_style_init():
    # Default values should be None
    s = Style()
    assert s.get("fill") is None
    assert s.get("stroke") is None
    
    # Positional initial values should work
    s = Style("fill value", "stroke value")
    assert s.get("fill") == "fill value"
    assert s.get("stroke") == "stroke value"
    
    # Keyword initial values should work
    s = Style(fill="fill value", stroke="stroke value")
    assert s.get("fill") == "fill value"
    assert s.get("stroke") == "stroke value"
    
    # Mixed positional and keyword initial values should work
    s = Style("fill value", stroke="stroke value")
    assert s.get("fill") == "fill value"
    assert s.get("stroke") == "stroke value"
    
    # Providing too many positional arguments should cause an error
    with pytest.raises(ValueError):
        Style("fill", "stroke", "line_width", "dash", "line_cap", "line_join", "xxx")
    
    # Providing a value by both positional and keyword arguments should fail.
    with pytest.raises(ValueError):
        Style("fill value", fill="fill value again")
    
    # Providing a non-existant field should fail
    with pytest.raises(ValueError):
        Style(baz="xxx")


def test_style_get_set_exceptions():
    s = Style("fill style", "stroke style")
    
    # Initially shouldn't have any exceptions
    assert None not in s
    assert 123 not in s
    
    # Should be able to change the values
    s.set("fill", "new fill style")
    s.set("stroke", "new stroke style")
    assert s.get("fill") == "new fill style"
    assert s.get("stroke") == "new stroke style"
    
    # Should be able to add exceptions
    s.set(None, "fill", "None's fill style")
    s.set(123, "fill", "123's fill style")
    
    assert s.get("fill") == "new fill style"
    assert s.get(None, "fill") == "None's fill style"
    assert s.get(123, "fill") == "123's fill style"
    
    assert None in s
    assert 123in s
    
    # Exceptions need not have all values defined uniquely and those not set
    # should fall through to the default types
    assert s.get(None, "stroke") == "new stroke style"
    assert s.get(123, "stroke") == "new stroke style"
    
    # Changing the underlying value should still shine through those unset
    # exception fields too
    s.set("fill", "newer fill style")
    s.set("stroke", "newer stroke style")
    
    assert s.get("fill") == "newer fill style"
    assert s.get(None, "fill") == "None's fill style"
    assert s.get(123, "fill") == "123's fill style"
    
    assert s.get("stroke") == "newer stroke style"
    assert s.get(None, "stroke") == "newer stroke style"
    assert s.get(123, "stroke") == "newer stroke style"
    
    # If no exceptions are present, the default values should appear
    assert s.get(321, "fill") == "newer fill style"
    assert s.get(321, "stroke") == "newer stroke style"
    
    # Get/Set should fail with too many/not enoguh arguments
    with pytest.raises(ValueError):
        s.get()
    with pytest.raises(ValueError):
        s.set()
    with pytest.raises(ValueError):
        s.get("too", "many", "arguments")
    with pytest.raises(ValueError):
        s.set("far", "too", "many", "arguments")


def test_style_copy():
    s1 = Style("fill style", "stroke style")
    s1.set(123, "fill", "123's fill style")
    
    s2 = s1.copy()
    
    # The copy should be of the correct type
    assert type(s2) is type(s1) is Style
    
    # The copy should initially match the copy
    assert s2.get("fill") == s1.get("fill")
    assert s2.get("stroke") == s1.get("stroke")
    assert s2.get(123, "fill") == s1.get(123, "fill")
    assert s2.get(123, "stroke") == s1.get(123, "stroke")
    
    # When modified, the copies should nolonger match
    s2.set("fill", "new fill style")
    assert s1.get("fill") == "fill style"
    assert s2.get("fill") == "new fill style"
    
    s1.set("stroke", "new stroke style")
    assert s1.get("stroke") == "new stroke style"
    assert s2.get("stroke") == "stroke style"
    
    s2.set(123, "fill", "123's new fill style")
    assert s1.get(123, "fill") == "123's fill style"
    assert s2.get(123, "fill") == "123's new fill style"


def test_cairo_polygon_styling():
    p = Style()
    
    ctx = Mock()
    
    # The context should initially do nothing but start and end a cairo context
    with p(ctx):
        pass
    ctx.save.assert_called_once_with()
    ctx.restore.assert_called_once_with()
    assert not ctx.set_line_width.called
    assert not ctx.set_source_rgba.called
    assert not ctx.set_dash.called
    assert not ctx.set_line_cap.called
    assert not ctx.set_line_join.called
    assert not ctx.fill.called
    assert not ctx.fill_preserve.called
    assert not ctx.stroke.called
    ctx.reset_mock()
    
    # The context should still be saved/restored even if an exception is raised
    # within it.
    with pytest.raises(MyException):
        with p(ctx):
            raise MyException()
    ctx.save.assert_called_once_with()
    ctx.restore.assert_called_once_with()
    ctx.reset_mock()
    
    # If a fill style is specified, a fill should be performed
    p.set("fill", (1.0, 1.0, 1.0, 0.5))
    with p(ctx):
        pass
    ctx.set_source_rgba.assert_called_once_with(1.0, 1.0, 1.0, 0.5)
    ctx.fill.assert_called_once_with()
    ctx.reset_mock()
    
    # If the contents of the block raises an exception, no fill should be
    # performed
    with pytest.raises(MyException):
        with p(ctx):
            raise MyException()
    assert not ctx.set_source_rgba.called
    assert not ctx.fill.called
    ctx.reset_mock()
    
    # If a stroke style is specified too, a fill then stroke should be performed
    p.set("stroke", (0.5, 0.5, 0.5, 0.5))
    with p(ctx):
        pass
    ctx.set_source_rgba.assert_has_calls([
        call(1.0, 1.0, 1.0, 0.5),
        call(0.5, 0.5, 0.5, 0.5),
    ])
    ctx.fill_preserve.assert_called_once_with()
    ctx.stroke.assert_called_once_with()
    ctx.reset_mock()
    
    # If only a stroke style is specified a fill should not occur.
    p.set("fill", None)
    with p(ctx):
        pass
    ctx.set_source_rgba.assert_called_once_with(0.5, 0.5, 0.5, 0.5)
    assert not ctx.fill_preserve.called
    assert not ctx.fill.called
    ctx.stroke.assert_called_once_with()
    ctx.reset_mock()
    
    # Line width should be set if provided
    p.set("line_width", 1.23)
    with p(ctx):
        pass
    ctx.set_line_width.assert_called_once_with(1.23)
    ctx.reset_mock()
    
    # Dash style should be set if provided
    p.set("dash", [1, 2, 3])
    with p(ctx):
        pass
    ctx.set_dash.assert_called_once_with([1, 2, 3])
    ctx.reset_mock()
    
    # Line cap style should be set if provided
    p.set("line_cap", cairo.LINE_CAP_ROUND)
    with p(ctx):
        pass
    ctx.set_line_cap.assert_called_once_with(cairo.LINE_CAP_ROUND)
    ctx.reset_mock()
    
    # Line cap style should be set if provided
    p.set("line_join", cairo.LINE_JOIN_ROUND)
    with p(ctx):
        pass
    ctx.set_line_join.assert_called_once_with(cairo.LINE_CAP_ROUND)
    ctx.reset_mock()
    
    # Style exceptions should be obayed
    p.set(None, "fill", (0.0, 0.0, 0.0, 0.0))
    p.set(None, "stroke", (0.0, 0.0, 0.0, 0.0))
    p.set(None, "line_width", 3.21)
    p.set(None, "dash", [3, 2, 1])
    p.set(None, "line_cap", cairo.LINE_CAP_BUTT)
    p.set(None, "line_join", cairo.LINE_JOIN_MITER)
    with p(ctx, None):
        pass
    ctx.set_line_width.assert_called_once_with(3.21)
    ctx.set_source_rgba.assert_has_calls([
        call(0.0, 0.0, 0.0, 0.0),
        call(0.0, 0.0, 0.0, 0.0),
    ])
    ctx.set_dash.assert_called_once_with([3, 2, 1])
    ctx.set_line_cap.assert_called_once_with(cairo.LINE_CAP_BUTT)
    ctx.set_line_join.assert_called_once_with(cairo.LINE_JOIN_MITER)
    ctx.fill_preserve.assert_called_once_with()
    ctx.stroke.assert_called_once_with()
    ctx.reset_mock()
    
    # Should be able to opt-out of fill/stroke
    with p(ctx, None, no_fill_stroke=True):
        pass
    assert not ctx.set_source_rgba.called
    assert not ctx.fill_preserve.called
    assert not ctx.stroke.called
    ctx.reset_mock()
    
    # The context manager's entry value should provide get/set with the
    # exception set.
    with p(ctx, None) as s:
        assert s.get("fill") == (0.0, 0.0, 0.0, 0.0)
        assert p.get("fill") is None
    with p(ctx) as s:
        assert s.get("fill") is None
        assert p.get("fill") is None
    ctx.reset_mock()
    
    # Should fail if given too many arguments
    with pytest.raises(ValueError):
        p(ctx, None, 123)
