"""Basic drawing style definition containers."""

from six import iteritems

class Style(object):
    """Base type for definitions of visual style."""
    
    """The set of style options which can be controlled."""
    FIELDS = []
    
    def __init__(self, *args, **kwargs):
        # A lookup from field to default value
        self._defaults = {f: None for f in self.FIELDS}
        
        # A lookup from exception to value
        self._exceptions = {}
        
        if len(args) > len(self.FIELDS):
            raise ValueError("More options specified than exist.")
        
        # Set positional style values
        for arg_num, value in enumerate(args):
            field = self.FIELDS[arg_num]
            self._defaults[field] = value
        
        # Set named style values
        for field, value in iteritems(kwargs):
            if field not in self._defaults:
                raise ValueError("Unknown style field {}".format(repr(field)))
            elif self._defaults[field] is not None:
                raise ValueError(
                    "Field {} already set by positional argument.".format(
                        repr(field)))
            else:
                self._defaults[field] = value
    
    def copy(self):
        s = type(self)()
        s._defaults = self._defaults.copy()
        s._exceptions = {e: v.copy() for e, v in iteritems(self._exceptions)}
        return s
    
    def set(self, *args):
        """Set the value of a particular field.
        
        Usage::
        
            s.set("field", value)
            s.set(exception, "field", value)
        """
        if len(args) == 2:
            field, value = args
            self._defaults[field] = value
        elif len(args) == 3:
            exception, field, value = args
            self._exceptions.setdefault(exception, {})[field] = value
        else:
            raise ValueError("set expects 3 or 4 arguments")
    
    def get(self, *args):
        """Get the value of a particular field.
        
        Usage::
            v = s.get("field")
            v = s.get(exception, "field")
        """
        if len(args) == 1:
            return self._defaults[args[0]]
        elif len(args) == 2:
            exception, field = args
            return self._exceptions.get(exception, {}).get(
                field, self._defaults[field])
        else:
            raise ValueError("get expects 2 or 3 arguments")


class PolygonStyle(Style):
    """Defines the style of a polygon.
    
    When called with a cairo context and optionally an exception, produces a
    context manager which saves the cairo context and on exit, strokes and fills
    the polygon using the style defined.
    """
    
    FIELDS = ["fill", "stroke", "line_width", "dash", "line_cap", "line_join"]
    
    def __call__(self, ctx, *exception, no_fill_stroke=False):
        """Create a context manager which will render the current path using the
        specified style. If no_fill_stroke is set to True, the context manager
        will not fill/stroke the underlying shape but will set the other styles.
        """
        if len(exception) > 1:
            raise ValueError("expected 2 or 3 arguments")
        return self.ContextMgr(self, ctx, *exception,
                               no_fill_stroke=no_fill_stroke)
    
    class ContextMgr(object):
        """The context manager returned by calling a PolygonStyle instance."""
        
        def __init__(self, style, ctx, *exception, no_fill_stroke=False):
            self.style = style
            self.ctx = ctx
            self.exception = list(exception)
            self.no_fill_stroke = no_fill_stroke
        
        def __enter__(self):
            self.ctx.save()
            return self
        
        def __exit__(self, exc_type, value, traceback):
            try:
                if value is None:
                    # Nothing went wrong in the with block! Proceed with drawing the
                    # polygon.
                    line_width = self.style.get(*self.exception + ["line_width"])
                    if line_width is not None:
                        self.ctx.set_line_width(line_width)
                    
                    dash = self.style.get(*self.exception + ["dash"])
                    if dash is not None:
                        self.ctx.set_dash(dash)
                    
                    line_cap = self.style.get(*self.exception + ["line_cap"])
                    if line_cap is not None:
                        self.ctx.set_line_cap(line_cap)
                    
                    line_join = self.style.get(*self.exception + ["line_join"])
                    if line_join is not None:
                        self.ctx.set_line_join(line_join)
                    
                    fill = self.style.get(*self.exception + ["fill"])
                    stroke = self.style.get(*self.exception + ["stroke"])
                    
                    if not self.no_fill_stroke:
                        if fill and stroke:
                            self.ctx.set_source_rgba(*fill)
                            self.ctx.fill_preserve()
                            self.ctx.set_source_rgba(*stroke)
                            self.ctx.stroke()
                        elif fill:
                            self.ctx.set_source_rgba(*fill)
                            self.ctx.fill()
                        elif stroke:
                            self.ctx.set_source_rgba(*stroke)
                            self.ctx.stroke()
            finally:
                self.ctx.restore()
        
        def get(self, *args):
            return self.style.get(*self.exception + list(args))

