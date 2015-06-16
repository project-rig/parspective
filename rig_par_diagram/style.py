"""Style definitions data structures.

Various elements of Rig P&R Diagram's output can have their appearence
customised, for examlpe changing colours or line styles. It is also useful to be
able to make exceptions to these styles, for example, to highlight a certain net
or colour code cores in the diagram. The Style object helps facilitate this
functionality.  """

from six import iteritems

class Style(object):
    """Defines the style of a polygon to be drawn.
    
    Thie Style object defines a set of Cairo drawing parameters (see
    :py:meth:`.FIELDS`) for the drawing of certain elements in Rig P&R Diagram
    diagrams. For example, :py:class:`.Style`s are used to define how chips,
    links cores and nets are drawn. Exceptions can be added to the style to
    allow individual instances to have their style options altered.
    
    Style options can be set using the constructor or via the :py:meth:`.set`
    method like so::
    
        >>> # Define a style with a red 50% transparent fill and black stroke
        >>> # 0.1 units wide.
        >>> s = Style(fill=(1.0, 0.0, 0.0, 0.5))
        >>> s.set("stroke", (0.0, 0.0, 0.0, 1.0)
        >>> s.set("line_width", 0.1)
    
    The value of these style options can be read back using the ;py:class:`.get`
    method::
    
        >>> s.get("fill")
        (1.0, 0.0, 0.0, 1.0)
    
    Exceptions can also be defined. For example when defining the drawing style
    of a chip, exceptions are made on a chip by chip basis. Here we can cause
    chip (2, 4) to be drawn with a thicker outline::
    
        >>> s.set((2, 4), "line_width", 0.3)
    
    When fetching styles, possible exceptions are provided to the
    :py:class:`.get` method and if a matching exception exists its value is
    returned, otherwise the default value is produced. For example:
    
        >>> s.get((2, 4), "line_width")
        0.3
        >>> s.get((2, 4), "stroke")
        (0.0, 0.0, 0.0, 1.0)
        >>> s.get((0, 0), "line_width")
        0.1
    
    The :py:class:`.Style` object also acts as a context manager which on entry
    will push the current Cairo state onto the stack and on exit stroke and fill
    any paths according to the Style's definition. For example::
    
        # Draws a triangle with whatever style and colour of fill and stroke the
        # Style defines.
        >>> with s(ctx):
        ...     ctx.move_to(1.0, 1.0)
        ...     ctx.line_to(2.0, 2.0)
        ...     ctx.line_to(2.0, 1.0)
        ...     ctx.close_path()
    
    See the :py:class:`.__call__` special method for more details.
    """
    
    """The set of style options which can be controlled.
    
    * ``fill``: None or (r, g, b, a). If not None, defines the colour fill which
      should be applied.
    * ``stroke``: None or (r, g, b, a). If not None, defines the colour of the
      stroke to draw around the polygon. Should be used in combination with
      ``line_width``. The stroke will be applied after the fill.
    * ``line_width`` (None or float). The width of the stroke to use (or no
      stroke if 0).
    * ``dash`` (None or list). If not None, specifies the dash pattern to use.
    * ``line_cap`` (None or cairo.LINE_CAP_*). If not None, the style of line
      cap to use when stroking lines.
    * ``line_join`` (None or cairo.LINE_JOIN_*). If not None, the style of line
      join to use when stroking lines.
    """
    FIELDS = ["fill", "stroke", "line_width", "dash", "line_cap", "line_join"]
    
    def __init__(self, *args, **kwargs):
        """Define a new style.
        
        Initial default values can be set by positional arguments in the same
        order as :py:meth:`.FIELDS` or via named keyword arguments. Unless
        given, all fields will default to None.
        """
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
        """Create a copy of this style."""
        s = type(self)()
        s._defaults = self._defaults.copy()
        s._exceptions = {e: v.copy() for e, v in iteritems(self._exceptions)}
        return s
    
    def set(self, *args):
        """Set the value of a particular style parameter.
        
        Usage examples::
        
            >>> # Set the default line_width to 0.1
            >>> s.set("line_width", 0.1)
            >>> # Set an exception for the line_width of (3, 2)
            >>> s.set((3, 2), "line_width", 0.3)
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
        """Get the value of a particular style parameter.
        
        Usage::
            >>> # Get the default line_width
            >>> line_width = s.get("line_width")
            >>> # Get the line width for (3, 2), returning the default value if
            >>> # no exception to the style exists.
            >>> line_width = s.get((3, 2), "line_width")
        """
        if len(args) == 1:
            return self._defaults[args[0]]
        elif len(args) == 2:
            exception, field = args
            return self._exceptions.get(exception, {}).get(
                field, self._defaults[field])
        else:
            raise ValueError("get expects 2 or 3 arguments")
    
    def __contains__(self, exception):
        """Test whether the style has any exceptions for a given object."""
        return exception in self._exceptions
    
    def __call__(self, ctx, *exception, **kwargs):
        """Create a context manager object which applies this Style to any Cairo
        paths drawn within the context.
        
        A basic example which draws a triangle using the style specified by
        ``s``::
        
            >>> with s(ctx):
            ...     ctx.move_to(1.0, 1.0)
            ...     ctx.line_to(2.0, 2.0)
            ...     ctx.line_to(2.0, 1.0)
            ...     ctx.close_path()
        
        In this example, the triangle is drawn with the style exception
        (3, 2). Additionally, a new object ``s_`` is defined which has a get
        function which behaves like a :py:class:`.Style`'s getter except it
        gets the style for the supplied style exception.
        
            >>> with s(ctx, (3, 2)) as s_:
            ...     ctx.move_to(1.0, 1.0)
            ...     ctx.line_to(2.0 + s_.get("line_width"),
            ...                 2.0 + s_.get("line_width"))
            ...     ctx.line_to(2.0 + s_.get("line_width"), 1.0)
            ...     ctx.close_path()
        
        Note: if the code within the block raises an exception, the Cairo state
        will be restored but the path will not be filled/stroked.
        
        Parameters
        ----------
        ctx : Cairo context
            A cairo context into which all paths will be drawn. At the start of
            the context the Cairo state is saved. At the end of the context it
            is restored.
        exception : object
            An optional object which specifies what styling exception should be
            used. If not specified, the default is used.
        no_fill_stroke : bool
            By default when the context is exited, the current Cairo path is
            filled and stroked as specified. If this named argument is given as
            True, the Cairo path is not stroked. This is useful when the
            fill/stroke operations required are non-trivial (e.g. when gradients
            are in use) but where having a getter with a particular exception
            predefined is convenient.
        """
        if len(exception) > 1:
            raise ValueError("expected 2 or 3 arguments")
        return self.ContextMgr(self, ctx, *exception,
                               no_fill_stroke=
                                   kwargs.get("no_fill_stroke", False))
    
    class ContextMgr(object):
        """The context manager returned by calling a PolygonStyle instance."""
        
        def __init__(self, style, ctx, *exception, **kwargs):
            self.style = style
            self.ctx = ctx
            self.exception = list(exception)
            self.no_fill_stroke = kwargs.get("no_fill_stroke", False)
        
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

