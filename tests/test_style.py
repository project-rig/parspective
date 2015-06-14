import pytest

from mock import Mock, call

from parspective.style import Style, PolygonStyle

import cairocffi as cairo

class MyStyle(Style):
    FIELDS = ["foo", "bar"]


class MyException(Exception):
    pass


def test_style_init():
    # Default values should be None
    s = MyStyle()
    assert s.get("foo") is None
    assert s.get("bar") is None
    
    # Positional initial values should work
    s = MyStyle("foo value", "bar value")
    assert s.get("foo") == "foo value"
    assert s.get("bar") == "bar value"
    
    # Keyword initial values should work
    s = MyStyle(foo="foo value", bar="bar value")
    assert s.get("foo") == "foo value"
    assert s.get("bar") == "bar value"
    
    # Mixed positional and keyword initial values should work
    s = MyStyle("foo value", bar="bar value")
    assert s.get("foo") == "foo value"
    assert s.get("bar") == "bar value"
    
    # Providing too many positional arguments should cause an error
    with pytest.raises(ValueError):
        MyStyle("foo value", "bar value", "xxx")
    
    # Providing a value by both positional and keyword arguments should fail.
    with pytest.raises(ValueError):
        MyStyle("foo value", foo="foo value again")
    
    # Providing a non-existant field should fail
    with pytest.raises(ValueError):
        MyStyle(baz="xxx")


def test_style_get_set_exceptions():
    s = MyStyle("foo style", "bar style")
    
    # Should be able to change the values
    s.set("foo", "new foo style")
    s.set("bar", "new bar style")
    assert s.get("foo") == "new foo style"
    assert s.get("bar") == "new bar style"
    
    # Should be able to add exceptions
    s.set(None, "foo", "None's foo style")
    s.set(123, "foo", "123's foo style")
    
    assert s.get("foo") == "new foo style"
    assert s.get(None, "foo") == "None's foo style"
    assert s.get(123, "foo") == "123's foo style"
    
    # Exceptions need not have all values defined uniquely and those not set
    # should fall through to the default types
    assert s.get(None, "bar") == "new bar style"
    assert s.get(123, "bar") == "new bar style"
    
    # Changing the underlying value should still shine through those unset
    # exception fields too
    s.set("foo", "newer foo style")
    s.set("bar", "newer bar style")
    
    assert s.get("foo") == "newer foo style"
    assert s.get(None, "foo") == "None's foo style"
    assert s.get(123, "foo") == "123's foo style"
    
    assert s.get("bar") == "newer bar style"
    assert s.get(None, "bar") == "newer bar style"
    assert s.get(123, "bar") == "newer bar style"
    
    # If no exceptions are present, the default values should appear
    assert s.get(321, "foo") == "newer foo style"
    assert s.get(321, "bar") == "newer bar style"
    
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
    s1 = MyStyle("foo style", "bar style")
    s1.set(123, "foo", "123's foo style")
    
    s2 = s1.copy()
    
    # The copy should be of the correct type
    assert type(s2) is type(s1) is MyStyle
    
    # The copy should initially match the copy
    assert s2.get("foo") == s1.get("foo")
    assert s2.get("bar") == s1.get("bar")
    assert s2.get(123, "foo") == s1.get(123, "foo")
    assert s2.get(123, "bar") == s1.get(123, "bar")
    
    # When modified, the copies should nolonger match
    s2.set("foo", "new foo style")
    assert s1.get("foo") == "foo style"
    assert s2.get("foo") == "new foo style"
    
    s1.set("bar", "new bar style")
    assert s1.get("bar") == "new bar style"
    assert s2.get("bar") == "bar style"
    
    s2.set(123, "foo", "123's new foo style")
    assert s1.get(123, "foo") == "123's foo style"
    assert s2.get(123, "foo") == "123's new foo style"


def test_polygon_style():
    p = PolygonStyle()
    
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
