"""Cairo-based diagram generation of placement/routing information."""

import random

import cairocffi as cairo

from collections import defaultdict

from math import sin, cos, atan2, pi, sqrt

from six import iteritems, itervalues, next

from rig.geometry import shortest_torus_path

from rig.machine import Links, Cores

from rig.netlist import Net

from rig.place_and_route.route.utils import links_between

from rig.place_and_route.routing_tree import RoutingTree


class Diagram(object):
    """Generate diagrams of placement and routing solutions in a SpiNNaker
    system.
    
    Within the drawing, dimensions are given in terms of hexagon widths.
    """
    
    def __init__(self, machine, vertices_resources={}, nets=[], placements={},
                 allocations={}, routes={}, core_resource=Cores):
        """Initialise a new set of parameters to diagram."""
        self.machine = machine
        self.vertices_resources = vertices_resources
        self.nets = nets
        self.placements = placements
        self.allocations = allocations
        self.routes = routes
        
        self.has_wrap_around_links = self.machine.has_wrap_around_links()
        
        # Lookup from (x, y) to [vertex, ...] where a vertex may be repeated
        # several times, once per core.
        self.l2v = defaultdict(list)
        for vertex, xy in iteritems(placements):
            # XXX TODO: Sort by allocation(?)
            self.l2v[xy].extend([vertex] *
                                vertices_resources[vertex].get(core_resource,
                                                               0))
        
        # RGBA for each chip's fill/stroke colour
        self.chip_fill = defaultdict(lambda: (0.0, 0.0, 0.0, 0.0))
        self.chip_stroke = defaultdict(lambda: (0.0, 0.0, 0.0, 1.0))
        
        # Space between each chip in hexagon-widths
        self.chip_spacing = 0.3
        
        # Width of the stroke around each chip
        self.chip_stroke_width = 0.05
        
        # RGBA for each chip-to-chip link's fill/stroke colour. Note that both
        # directions should be set identically for predictable behaviour...
        self.link_fill = defaultdict(lambda: (0.5, 0.5, 0.5, 0.2))
        self.link_stroke = defaultdict(lambda: (0.5, 0.5, 0.5, 0.25))
        
        # Width of the stroke along a link boundry
        self.link_stroke_width = 0.025
        
        # Width of a link between a pair of chips.
        self.link_width = 1.0 * (sin(pi / 6.0) -
                                 (self.link_stroke_width / 2.0))
        
        # Minimum gap to leave between cores and the surrounding hexagon
        self.core_gap = 0.06
        
        # Maximum diameter of a core
        self.max_core_diameter = 0.5 - self.chip_stroke_width
        
        # The diameter of a circle representing a core. This is chosen to be
        # large enough to accomodate the specified number of rings of cores,
        # spaced core_gap appart.
        max_num_cores = max(map(len, itervalues(self.l2v)))
        rings = self._get_layer(max_num_cores, max_num_cores - 1)[0] + 1
        self.core_diameter = (  # Radius of a chip
                              (((1.0 - self.chip_stroke_width) * cos(pi / 6.0)) -
                               (self.core_gap * rings * 2)) /  # Total gaps
                              ((rings * 2) - 1))  # Number of cores along
                                                  # the diameter.
        self.core_diameter = min(self.core_diameter, self.max_core_diameter)
        
        # RGBA for each core's (x, y, p) fill/stroke colour.
        self.core_fill = defaultdict(lambda: (0.0, 0.0, 1.0, 1.0))
        self.core_stroke = defaultdict(lambda: (0.0, 0.0, 0.0, 0.0))
        
        # Width of the stroke around a core
        self.core_stroke_width = 0.0
        
        # A lookup {num_cores: {core_num: (x, y), ...}, ...} for previously
        # requested value to self._core_offset.
        self._core_offsets = {}
        
        # RGBA for each net
        self.net_stroke = defaultdict(lambda: (1.0, 0.0, 0.0, 1.0))
        
        # Scale net weight by this amount to get their stroke thickness
        self.net_stroke_width_scale = 0.005  # XXX: Scale if weights are large
        
        # The spacing to add between nets. Note, this value is scaled by
        # net_stroke_width_scale and thus is in the same units as used to
        # specify weights.
        self.net_spacing = min((n.weight for n in nets), default=1.0)
        
        # Alpha channel for ratsnest
        self.ratsnest_alpha = 0.5
        
        # When nets are drawn as a ratsnest, how high should the arc formed by
        # the wires be?
        self.ratswire_arc_height = 0.1
        
        # The height and angle of a self-loop ratsnest wire.
        self.ratswire_loop_height = 1.0
        self.ratswire_loop_angle = pi/5.0
        
        # For each chip-to-chip link (x, y, direction), gives an ordered list of
        # Nets giving the ordering of the nets in the link. Note that
        # complementrary end-points will have duplicate entries.
        self._net_allocations = defaultdict(list)
        for net, tree in iteritems(routes):
            for node in tree:
                if isinstance(node, RoutingTree):
                    for child in node.children:
                        if isinstance(child, RoutingTree):
                            link = next(iter(links_between(node.chip,
                                                           child.chip,
                                                           self.machine)))
                            self._allocate_net_on_link(net,
                                                       node.chip[0],
                                                       node.chip[1],
                                                       link)
    
    
    def _opposite_link(self, x, y, direction):
        """Given a link, return the opposite end of the link."""
        dx, dy = direction.to_vector()
        x = (x + dx) % self.machine.width
        y = (y + dy) % self.machine.height
        direction = direction.opposite
        
        return (x, y, direction)
    
    
    def _allocate_net_on_link(self, net, x1, y1, direction1):
        """Allocate space on the specified link for the given net."""
        x2, y2, direction2 = self._opposite_link(x1, y1, direction1)
        
        link_nets_1 = self._net_allocations[(x1, y1, direction1)]
        link_nets_2 = self._net_allocations[(x2, y2, direction2)]
        
        # Nets are added to the end of North, East, South-West links and to the
        # start of South, West and North-East links, keeping the order
        # consistent.
        if direction2 in (Links.north, Links.east, Links.south_west):
            link_nets_2, link_nets_1 = link_nets_1, link_nets_2
        link_nets_1.append(net)
        link_nets_2.insert(0, net)
    
    
    def _get_layer(self, num_cores, core_num):
        """Given a total number of cores and a core number, calculate the layer,
        index within that layer and the size of the layer the core sits in."""
        if core_num == 0:
            return (0, 0, 1)
        
        layer = 0
        num_in_full_layer = 1
        if core_num != 0:
            while True:
                core_num -= num_in_full_layer
                num_cores -= num_in_full_layer
                
                layer += 1
                num_in_full_layer = (layer * 6)
                
                if core_num < num_in_full_layer:
                    break
        
        num_in_layer = min(num_cores, num_in_full_layer)
        
        return (layer, core_num, num_in_layer)
    
    def _core_offset(self, num_cores, core_num):
        """Given the total number of cores in a chip and a specific core
        number, get the canvas offset of a core from the chip center."""
        # Get memoised value
        if num_cores in self._core_offsets:
            return self._core_offsets[num_cores][core_num]
        
        # If unavailable, work out positions for all cores when there are
        # num_cores
        offsets = {}
        for num in range(num_cores):
            # For each core, work out its position. First determine which layer
            # of hexagons it is in and how many hexagons are in that layer.
            layer, index, num_in_layer = self._get_layer(num_cores, num)
            
            # Map that to a point around a circle
            # XXX: Should probably be a point around a hexagon...
            radius = layer * (self.core_diameter + self.core_gap)
            angle = 2.0 * pi * (float(index) / num_in_layer)
            x = radius * sin(angle)
            y = radius * cos(angle)
            
            offsets[num] = (x, y)
        
        self._core_offsets[num_cores] = offsets
        
        # Return the newly calculated answer
        return self._core_offsets[num_cores][core_num]
    
    
    def _chip(self, x, y):
        """Get the canvas coordinates of the center of the supplied chip in the
        system."""
        # Cairo coordinates are top-to-bottom, chip coordinates are given
        # bottom-to-top.
        y = self.machine.height - y - 1
        
        # Add spacing between nodes
        x *= (1.0 + self.chip_spacing)
        y *= (1.0 + self.chip_spacing)
        
        # Draw the diagram on skewwed coordinates
        x += y * sin(pi / 6.0)
        y = y * cos(pi / 6.0)
        
        return (x, y)
    
    
    def _link(self, x, y, direction):
        """Get the canvas coordinates of the beginning and end of a chip's link
        band. The two coordinates are for the two sides of the link in clockwise
        order."""
        # Center of chip
        x, y = self._chip(x, y)
        
        # The angle the link leaves the chip with respect to the X-axis (note
        # that 0 is east and the values progress in counter-clockwise order).
        angle = -direction * (pi / 3.0)
        
        # Move to the center of the given edge
        offset = (0.5 * cos(pi / 6.0)) + (self.chip_stroke_width / 2.0)
        x += offset * cos(angle)
        y += offset * sin(angle)
        
        # Get positions of the two edges of the link
        x1 = x + (self.link_width / 2.0) * cos(angle - (pi / 2.0))
        y1 = y + (self.link_width / 2.0) * sin(angle - (pi / 2.0))
        x2 = x + (self.link_width / 2.0) * cos(angle + (pi / 2.0))
        y2 = y + (self.link_width / 2.0) * sin(angle + (pi / 2.0))
        
        return x1, y1, x2, y2
    
    
    def _link_net(self, x, y, direction, net):
        """Get the canvas coordinates of the end of the supplied net at the end
        of the given link."""
        x1, y1, x2, y2 = self._link(x, y, direction)
        
        # Get the set of nets which pass through this link
        nets = self._net_allocations[(x % self.machine.width,
                                      y % self.machine.height,
                                      direction)]
        assert net in nets
        
        # Find the total width of this set of nets along with the offset of the
        # net of interest.
        nets_width = 0.0
        net_offset = 0.0
        for n in nets:
            if n == net:
                net_offset = nets_width
            nets_width += n.weight + self.net_spacing
        nets_width -= n.weight + self.net_spacing
        
        nets_width *= self.net_stroke_width_scale
        net_offset *= self.net_stroke_width_scale
        
        # Convert net offset to range 0.0 - 1.0 (ratio of link width)
        nets_width /= self.link_width
        net_offset /= self.link_width
        
        # Center the nets within the link
        net_offset += (1.0 - nets_width) / 2.0
        
        return (x1 + ((x2 - x1) * net_offset), y1 + ((y2 - y1) * net_offset))
    
    def _core(self, x, y, core):
        """Get the canvas coordinates of the specified core."""
        num_cores = len(self.l2v[(x, y)])
        
        cx, cy = self._chip(x, y)
        dx, dy = self._core_offset(num_cores, core)
        
        return cx + dx, cy + dy
    
    
    @property
    def _bbox(self):
        """The bounding box of the image (x1, y1, x2, y2)."""
        # Calculate the size of the bounding box around the live chips in the
        # diagram
        points = [self._chip(x, y) for x, y in self._chips]
        
        x1 = min(x for x, y in points)
        x2 = max(x for x, y in points)
        y1 = min(y for x, y in points)
        y2 = max(y for x, y in points)
        
        # Expand to fit half a chip-to-chip gap plus the fade-out-distance on
        # all sides of the diagram.
        spacing = ((1.0 + self.chip_stroke_width) / 2.0) + self.chip_spacing
        x1 -= spacing
        y1 -= spacing
        x2 += spacing
        y2 += spacing
        
        return x1, y1, x2, y2
    
    
    @property
    def _chips(self):
        """An iterator over the chips in the machine."""
        for x in range(machine.width):
            for y in range(machine.height):
                if (x, y) in self.machine:
                    yield (x, y)
    
    
    @property
    def _links(self):
        """An iterator over the set of links in the machine.
        
        This iterator will list links from only one direction. If a link is a
        wrap-around link, it will be listed on both sides of the machine and
        from the perspective of the chip at the edge of the diagram.
        """
        for x in range(machine.width):
            for y in range(machine.height):
                if (x, y) in self.machine:
                    for direction in Links:
                        if (x, y, direction) in machine:
                            # Determine if the other chip is at the other end of
                            # a wrap-around.
                            dx, dy = direction.to_vector()
                            x2 = x + dx
                            y2 = y + dy
                            wraps_around = (x2, y2) not in machine
                            
                            destination_exists = (x2 % machine.width,
                                                  y2 % machine.height) in machine
                            
                            # Don't list links from both ends (unless wrapping
                            # around) and don't list links to dead chips.
                            if (destination_exists and
                                    (wraps_around or (x, y) < (x2, y2))):
                                yield (x, y, direction)
    
    
    def _draw_chip(self, ctx, x, y):
        """Draw a single chip in the machine."""
        ctx.save()
        
        cx, cy = self._chip(x, y)
        ctx.translate(cx, cy)
        
        # Draw the chip as a hexagon
        ctx.move_to(0, 0.5)
        for step in range(1, 6):
            ctx.line_to(0.5 * sin(step * pi / 3.0),
                        0.5 * cos(step * pi / 3.0))
        ctx.close_path()
        
        
        ctx.set_source_rgba(*self.chip_fill[(x, y)])
        ctx.fill_preserve()
        
        ctx.set_line_width(self.chip_stroke_width)
        ctx.set_source_rgba(*self.chip_stroke[(x, y)])
        ctx.stroke()
        
        ctx.restore()
    
    
    def _draw_link(self, ctx, x, y, direction):
        """Draw a the link between two chips."""
        ctx.save()
        
        # Get the positions of the end of the link
        ax1, ay1, ax2, ay2 = self._link(x, y, direction)
        
        # Get the position of the opposite end of the link
        dx, dy = direction.to_vector()
        x2, y2 = x + dx, y + dy
        bx1, by1, bx2, by2 = self._link(x2, y2, direction.opposite)
        
        # Determine if the link is a wrap-around
        wraps_around = (x2, y2) not in machine
        
        # Draw link fill
        ctx.move_to(ax1, ay1)
        ctx.line_to(bx2, by2)
        ctx.line_to(bx1, by1)
        ctx.line_to(ax2, ay2)
        ctx.close_path()
        
        # Fade-out wrap-around links
        r, g, b, a = self.link_fill[(x, y, direction)]
        if wraps_around:
            gradient = cairo.LinearGradient(ax1, ay1, bx2, by2)
            gradient.add_color_stop_rgba(0.0, r, g, b, a)
            gradient.add_color_stop_rgba(0.5, r, g, b, a)
            gradient.add_color_stop_rgba(1.0, r, g, b, 0.0)
            ctx.set_source(gradient)
        else:
            ctx.set_source_rgba(r, g, b, a)
        ctx.fill()
        
        # Draw link boundaries
        ctx.move_to(ax1, ay1)
        ctx.line_to(bx2, by2)
        
        ctx.move_to(ax2, ay2)
        ctx.line_to(bx1, by1)
        
        # Fade-out wrap-around links
        r, g, b, a = self.link_stroke[(x, y, direction)]
        if wraps_around:
            gradient = cairo.LinearGradient(ax1, ay1, bx2, by2)
            gradient.add_color_stop_rgba(0.0, r, g, b, a)
            gradient.add_color_stop_rgba(0.5, r, g, b, 0.0)
            ctx.set_source(gradient)
        else:
            ctx.set_source_rgba(r, g, b, a)
        ctx.set_line_width(self.link_stroke_width)
        ctx.stroke()
        
        ctx.restore()
    
    
    def _draw_vertex(self, ctx, vertex):
        """Draw all the cores of a vertex in the system."""
        x, y = self.placements[vertex]
        for core, v in enumerate(self.l2v[(x, y)]):
            if v != vertex:
                continue
            
            cx, cy = self._core(x, y, core)
            
            ctx.save()
            
            ctx.arc(cx, cy, self.core_diameter / 2.0, 0.0, 2.0 * pi)
            
            ctx.set_source_rgba(*self.core_fill[(x, y, core)])
            ctx.fill_preserve()
            
            ctx.set_line_width(self.core_stroke_width)
            ctx.set_source_rgba(*self.core_stroke[(x, y, core)])
            ctx.stroke()
            
            ctx.restore()
    
    
    def _draw_ratswire(self, sx, sy, sc, dx, dy, dc, rgba, width):
        """Draw a wire between the specified cores."""
        # Work out what route would be taken when wrap-around links are
        # available.
        vx, vy, vz = shortest_torus_path((sx, sy, 0), (dx, dy, 0),
                                         machine.width, machine.height)
        # Convert to XY only
        vx -= vz
        vy -= vz
        
        wraps_x = not (0 <= sx + vx < machine.width)
        wraps_y = not (0 <= sy + vy < machine.height)
        
        # A list of ((x1, y1), (x2, y2)) tuples giving the set of lines to be drawn
        # for this net.
        lines = []
        
        if not self.has_wrap_around_links or (not wraps_x and not wraps_y):
            # Just draw a straight-line path
            lines.append((self._core(sx, sy, sc), self._core(dx, dy, dc)))
        else:
            # This link wraps around. We draw it in two parts
            
            # First we draw the part going off the edge
            sxc, syc = self._chip(sx, sy)
            sxo, syo = self._core_offset(len(self.l2v[(sx, sy)]), sc)
            
            dxc, dyc = self._chip(sx + vx, sy + vy)
            dxo, dyo = self._core_offset(len(self.l2v[(dx, dy)]), dc)
            
            lines.append(((sxc + sxo, syc + syo), (dxc + dxo, dyc + dyo)))
            
            # Second we draw the part coming back in again
            sxc, syc = self._chip(dx - vx, dy - vy)
            sxo, syo = self._core_offset(len(self.l2v[(sx, sy)]), sc)
            
            dxc, dyc = self._chip(dx, dy)
            dxo, dyo = self._core_offset(len(self.l2v[(dx, dy)]), dc)
            
            lines.append(((sxc + sxo, syc + syo), (dxc + dxo, dyc + dyo)))
        
        # Draw the set of lines defined above
        with ctx:
            ctx.set_source_rgba(*rgba)
            ctx.set_line_width(width)
            
            for (x1, y1), (x2, y2) in lines:
                # Add a curve to the wire
                if x1 != x2 or y1 != y2:
                    # Find the midpoint
                    mx = (x2 - x1) / 2.0
                    my = (y2 - y1) / 2.0
                    
                    # Adjust to add a curve
                    alpha = atan2(my, mx)
                    alpha += pi / 2.0
                    mx += x1 + self.ratswire_arc_height * cos(alpha)
                    my += y1 + self.ratswire_arc_height * sin(alpha)
                    
                    mx1 = mx2 = mx
                    my1 = my2 = my
                else:
                    # Add a loop to this self-loop net
                    alpha = self.ratswire_loop_angle
                    mx1 = x1 + self.ratswire_loop_height * cos(-pi / 2.0 - alpha)
                    my1 = y1 + self.ratswire_loop_height * sin(-pi / 2.0 - alpha)
                    
                    mx2 = x2 + self.ratswire_loop_height * cos(-pi / 2.0 + alpha)
                    my2 = y2 + self.ratswire_loop_height * sin(-pi / 2.0 + alpha)
                
                ctx.move_to(x1, y1)
                ctx.curve_to(mx1, my1, mx2, my2, x2, y2)
                ctx.stroke()
    
    
    def _draw_ratsnest(self, ctx, net):
        """Draw the ratsnest for a given vertex."""
        sx, sy = self.placements[net.source]
        for sc in (c for c, v in enumerate(self.l2v[(sx, sy)]) if v == net.source):
            for dst in net.sinks:
                dx, dy = self.placements[dst]
                for dc in (c for c, v in enumerate(self.l2v[(dx, dy)]) if v == dst):
                    self._draw_ratswire(sx, sy, sc, dx, dy, dc,
                                        self.net_stroke[net],
                                        (net.weight *
                                         self.net_stroke_width_scale))
    
    
    def _draw_routing_tree_internal(self, ctx, net, origin, node, recurse=True):
        """Draw the wires for a given RoutingTree which are internal to
        chips."""
        cx1, cy1 = origin
        
        for child in node.children:
            if isinstance(child, RoutingTree):
                # The route goes to another chip
                direction = next(iter(links_between(node.chip,
                                                    child.chip,
                                                    self.machine)))
                cx2, cy2 = self._link_net(node.chip[0],
                                          node.chip[1],
                                          direction, net)
                
                if recurse:
                    x, y, direction = self._opposite_link(node.chip[0],
                                                          node.chip[1],
                                                          direction)
                    origin = self._link_net(x, y, direction, net)
                    self._draw_routing_tree_internal(ctx, net, origin, child)
            elif child.is_link:
                cx2, cy2 = self._link_net(node.chip[0], node.chip[1], child)
            elif child.is_core:
                # XXX: Core numbers...
                cx2, cy2 = self._core(node.chip[0], node.chip[1], child - 6)
            else:
                # XXX Shouldn't get here...
                assert False
            
            # Draw the link
            with ctx:
                ctx.move_to(cx1, cy1)
                ctx.line_to(cx2, cy2)
                ctx.set_line_width(net.weight * self.net_stroke_width_scale)
                ctx.set_source_rgba(*self.net_stroke[net])
                ctx.stroke()
            
    
    
    def _draw_routes(self, ctx):
        """Draw all routes in the system."""
        # First draw the sections of the routes between chips.
        for x1, y1, direction1 in self._links:
            nets = self._net_allocations[(x1, y1, direction1)]
            
            x2, y2, direction2 = self._opposite_link(x1, y1, direction1)
            for net in nets:
                dx, dy = direction1.to_vector()
                # Work-out the endpoints of the nets
                if x1 + dx != x2 or y1 + dy != y2:
                    # Wrap-around links will be drawn in two halves (note that
                    # the other half will be drawn when the _links iterator
                    # reaches the (x, y, direction) at the other end of the
                    # wrap-around link.
                    cx1, cy1 = self._link_net(x1, y1, direction1, net)
                    cx2, cy2 = self._link_net(x1 + dx, y1 + dy, direction2, net)
                else:
                    # Non-wrap-around links can be drawn directly
                    cx1, cy1 = self._link_net(x1, y1, direction1, net)
                    cx2, cy2 = self._link_net(x2, y2, direction2, net)
                
                # Draw the lines
                with ctx:
                    ctx.move_to(cx1, cy1)
                    ctx.line_to(cx2, cy2)
                    ctx.set_line_width(net.weight * self.net_stroke_width_scale)
                    ctx.set_source_rgba(*self.net_stroke[net])
                    ctx.stroke()
        
        # Next draw routes between links/cores within a chip.
        for net, route in iteritems(self.routes):
            x, y = self.placements[net.source]
            num_drawn = 0
            for core, v in enumerate(self.l2v[(x, y)]):
                if v != net.source:
                    continue
                cx, cy = self._core(x, y, core)
                self._draw_routing_tree_internal(ctx, net, (cx, cy), route,
                                                 num_drawn == 0)
                num_drawn += 1
    
    def _draw_wire_mask(self, ctx):
        """Draw the mask for wires within the system.
        
        This mask fades out wires moving towards wrap-aroudnd links.
        """
        gradient = cairo.RadialGradient(0.0, 0.0,
                                        0.5 + (self.chip_spacing / 2.0),
                                        0.0, 0.0,
                                        0.5 + self.chip_spacing)
        gradient.add_color_stop_rgba(0.0, 0, 0, 0, 1.0)
        gradient.add_color_stop_rgba(1.0, 0, 0, 0, 0.0)
        
        # Around the edge of the system, fade out along the radius of the chips
        # at the edge.
        for x in range(machine.width):
            for y in [0, machine.height - 1]:
                cx, cy = self._chip(x, y)
                with ctx:
                    ctx.translate(cx, cy)
                    ctx.set_source(gradient)
                    ctx.paint()
        for y in range(1, machine.height - 1):
            for x in [0, machine.width - 1]:
                cx, cy = self._chip(x, y)
                with ctx:
                    ctx.translate(cx, cy)
                    ctx.set_source(gradient)
                    ctx.paint()
        
        # Within the bounds of the system, keep all wires
        ctx.move_to(*self._chip(0, 0))
        ctx.line_to(*self._chip(machine.width - 1, 0))
        ctx.line_to(*self._chip(machine.width - 1, machine.height - 1))
        ctx.line_to(*self._chip(0, machine.height - 1))
        ctx.close_path()
        ctx.set_source_rgba(0,0,0,1)
        ctx.fill()
    
    
    def draw(self, ctx, width, height):
        """Draw the diagram onto the supplied Cairo context, centered in a rectangle
        from 0, 0 at the given width and height."""
        ctx.save()
        x1, y1, x2, y2 = self._bbox
        
        # Scale the drawing such that it fits the image perfectly.
        bbox_width = x2 - x1
        bbox_height = y2 - y1
        scale = min(width / bbox_width, height / bbox_height)
        ctx.scale(scale, scale)
        
        # Center the diagram in the allotted space
        x1 -= ((width / scale) - bbox_width) / 2.0
        y1 -= ((height / scale) - bbox_height) / 2.0
        ctx.translate(-x1, -y1)
        
        # Draw the chips
        for x, y in self._chips:
            self._draw_chip(ctx, x, y)
        
        # Draw the links
        for x, y, direction in self._links:
            self._draw_link(ctx, x, y, direction)
        
        if self.routes == {}:
            # Draw the ratsnest
            ctx.push_group()
            for net in self.nets:
                self._draw_ratsnest(ctx, net)
            ctx.pop_group_to_source()
            ctx.push_group()
            ctx.paint_with_alpha(self.ratsnest_alpha)
            net_surface = ctx.pop_group()
        else:
            ctx.push_group()
            self._draw_routes(ctx)
            net_surface = ctx.pop_group()
        
        # Get the mask for the wires
        ctx.push_group()
        self._draw_wire_mask(ctx)
        net_mask = ctx.pop_group()
        
        # Mask off the nets going beyond the system boundry
        ctx.set_source(net_surface)
        ctx.mask(net_mask)
        
        # Draw the vertices
        for vertex in self.vertices_resources:
            self._draw_vertex(ctx, vertex)
        
        ctx.restore()
        


if __name__=="__main__":
    width = 2000
    height = 1600
    
    from rig.machine import Machine
    
    w, h = 96, 60
    w, h = 12, 12
    
    machine = Machine(w, h, chip_resources={Cores: 17})
    ## SpiNN-5
    #nominal_live_chips = set([  # noqa
    #                                    (4, 7), (5, 7), (6, 7), (7, 7),
    #                            (3, 6), (4, 6), (5, 6), (6, 6), (7, 6),
    #                    (2, 5), (3, 5), (4, 5), (5, 5), (6, 5), (7, 5),
    #            (1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 4), (7, 4),
    #    (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3), (7, 3),
    #    (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
    #    (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
    #    (0, 0), (1, 0), (2, 0), (3, 0), (4, 0),
    #])
    #machine.dead_chips = set((x, y)
    #                         for x in range(8)
    #                         for y in range(8)) - nominal_live_chips
    #
    
    from collections import OrderedDict
    ideal_placement = OrderedDict(((x, y), object())
                                  for x in range(w)
                                  for y in range(h))
    vertices = list(itervalues(ideal_placement))
    vertices_resources = {v: {Cores: 1} for v in vertices}
    
    def i(x, y):
        #if x >= w or x < 0 or y >= h or y < 0:
        #    return None
        #else:
        return ideal_placement[(x%w, y%h)]
    nets = []
    
    # Nearest-neighbour connectivity
    nets += [Net(i(x, y),
                 [xy for xy in [i(x+1,y+1), # Top
                                i(x+0,y+1),
                                i(x-1,y+1), # Left
                                i(x-1,y+0),
                                i(x-1,y-1), # Bottom
                                i(x+0,y-1),
                                i(x+1,y-1), # Right
                                i(x+1,y+0),
                                ]
                  if xy is not None])
             for x in range(w)
             for y in range(h)]
    
    # Self-loop connectivity
    nets += [Net(v, v) for v in vertices]
    
    ## Random connectivity
    #fan_out = 1, 4
    #net_prob = 0.05
    #nets += [Net(v, random.sample(vertices, random.randint(*fan_out)))
    #         for v in vertices
    #         if random.random() < net_prob]
    
    # Thick pipeline connectivity
    #n_vertices = len(vertices)
    #thickness = 12
    #nets += [Net(vertices[i],
    #             vertices[(i//thickness + 1)*thickness: (i//thickness + 2)*thickness])
    #         for i in range(n_vertices)
    #         if i + thickness < n_vertices]
    
    ## Nengo-style pipeline of ensemble arrays
    #n_vertices = len(vertices)
    #thickness = 10
    #vertex_iter = iter(vertices)
    #last_node = None
    #try:
    #    while True:
    #        node = next(vertex_iter)
    #        if last_node is not None:
    #            nets.append(Net(last_node, node))
    #        
    #        ensemble_array = []
    #        try:
    #            for _ in range(thickness):
    #                ensemble_array.append(next(vertex_iter))
    #        except StopIteration:
    #            pass
    #        nets.append(Net(node, ensemble_array))
    #        
    #        last_node = next(vertex_iter)
    #        for v in ensemble_array:
    #            nets.append(Net(v, last_node))
    #except StopIteration:
    #    pass
    
    placements = {v: xy for xy, v in iteritems(ideal_placement)}
    
    import pickle
    with open("/tmp/placement.pickle", "rb") as f:
        data = pickle.load(f)
        
        machine = data["machine"]
        vertices_resources = data["vertices_resources"]
        nets = data["nets"]
        placements = data["placements"]
        allocations = data["allocations"]
        routes = data["routes"]
    
    d = Diagram(machine, vertices_resources, nets, placements, allocations, routes)
    
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                 width,
                                 height)
    ctx = cairo.Context(surface)
    d.draw(ctx, width, height)
    surface.write_to_png("/tmp/out.png")
