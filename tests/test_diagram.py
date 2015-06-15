"""Basic sanity checks for diagram generation.

Unfortunately testing graphics generation code is a meaningful way is fairly
tough. These tests can broadly be split into two categories:

* Sanity checking general data structure generation.
* Running various example designs and checking nothing crashes.
"""

import pytest

import random

import os

from distutils.dir_util import mkpath

from six import iteritems

import cairocffi as cairo

from parspective.diagram import \
    Diagram, \
    default_chip_style, \
    default_link_style, \
    default_core_style, \
    default_net_style

from parspective.style import Style

import rig

from rig.machine import Machine, Cores, Links

from rig.netlist import Net

from rig.place_and_route.routing_tree import RoutingTree

from rig.routing_table import Routes

from rig.place_and_route.constraints import \
    ReserveResourceConstraint, RouteEndpointConstraint


@pytest.fixture
def filename(request):
    path, _, test = request.node.nodeid.partition("::")
    dirname, filename = os.path.split(path)
    
    out_dir = os.path.join(dirname, "test_images", filename)
    out_name = "".join(
        c if c in "abcdefghijklmnopqrstuvwxyz0123456789"
                  "ABCDEFGHIJKLMNOPQRSTUVWXYZ_+-"
        else "_"
        for c in test)
    out_name += ".png"
    
    mkpath(out_dir)
    return os.path.join(out_dir, out_name)

@pytest.fixture
def width():
    return 400

@pytest.fixture
def height():
    return 300

@pytest.fixture
def ctx(width, height):
    """A Cairo context to render into whose output is just ignored."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 3, 6)
    return cairo.Context(surface)


@pytest.yield_fixture
def checked_ctx(width, height, filename):
    """Like ctx but after the test the image will be diffed against a reference
    image."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                 width,
                                 height)
    ctx = cairo.Context(surface)
    
    # The image should be drawn with a white background since diffing becomes
    # difficult otherwise.
    with ctx:
        ctx.rectangle(0, 0, width, height)
        ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        ctx.fill()
    
    yield ctx
    
    surface.flush()
    surface.write_to_png(filename + ".last.png")
    
    # Get the difference with the reference image
    try:
        ref_surface = cairo.ImageSurface.create_from_png(filename)
        ctx.set_operator(cairo.OPERATOR_DIFFERENCE)
        ctx.set_source_surface(ref_surface)
        ctx.rectangle(0, 0, width, height)
        ctx.fill()
    except FileNotFoundError:  # pragma: no cover
        # No reference image available, the diff is thus equal to the image
        pass
    
    surface.flush()
    surface.write_to_png(filename + ".diff.png")
    
    # Diff only the non-alpha channels
    different = any(p != b"\0" and n % 4 != 3
                    for n, p in enumerate(surface.get_data()))
    
    assert not different, "Doesn't match reference image {}".format(filename)


def test_init_core_map():
    # Given a simple scenario where:
    # * 2x2 system
    # * Chips have 18 cores.
    # * Chip (1, 0) is dead
    # * Chip (0, 1) only has 10 cores
    # * A 2-core vertex is placed on 0, 0 and given cores 10 & 11
    # * A 0-core vertex is placed on 0, 0
    # * Core 0 is reserved on all chips
    # * Cores 1 and 2 are reserved on chip (1, 1)
    # Make sure the core map comes out correctly
    core_resource = object()
    
    machine = Machine(2, 2,
                      dead_chips=set([(1, 0)]),
                      chip_resources={core_resource: 18},
                      chip_resource_exceptions={(0, 1): {core_resource: 10}})
    
    vertex = object()
    no_core_vertex = object()
    vertices_resources = {vertex: {core_resource: 2},
                          no_core_vertex: {core_resource: 0}}
    nets = []
    
    local_constraint = ReserveResourceConstraint(core_resource, slice(1, 3), (1, 1))
    global_constraint = ReserveResourceConstraint(core_resource, slice(0, 1))
    constraints = [local_constraint, global_constraint]
    
    placements = {vertex: (0, 0), no_core_vertex: (0, 0)}
    allocations = {vertex: {core_resource: slice(10, 12)},
                   no_core_vertex: {}}
    
    d = Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                constraints=constraints,
                placements=placements,
                allocations=allocations,
                core_resource=core_resource)
    
    assert d._core_map == {
        (0, 0): {
            0: global_constraint,
            1: None, 2: None, 3: None, 4: None, 5: None, 6: None, 7: None,
            8: None, 9: None,
            10: vertex,
            11: vertex,
            12: None, 13: None, 14: None, 15: None, 16: None, 17: None,
        },
        (0, 1): {
            0: global_constraint,
            1: None, 2: None, 3: None, 4: None, 5: None, 6: None, 7: None,
            8: None, 9: None,
        },
        (1, 1): {
            0: global_constraint,
            1: local_constraint,
            2: local_constraint,
            3: None, 4: None, 5: None, 6: None, 7: None, 8: None, 9: None,
            10: None, 11: None, 12: None, 13: None, 14: None, 15: None,
            16: None, 17: None,
        },
    }


def test_allocate_nets_to_links():
    # Given a simple scenario where:
    # * 2x1 system
    # * A vertex on (0, 0) is connected via two nets to one on (1, 1) and visa
    #   versa.
    # * A vertex on (0, 0) has a route-endpoint constraint which routes it to
    #   the south-west link.
    machine = Machine(2, 1)
    
    vertex0 = object()
    vertex1 = object()
    vertex2 = object()
    vertices_resources = {vertex0: {Cores: 1},
                          vertex1: {Cores: 0},
                          vertex2: {Cores: 0}}
    nets = [Net(vertex0, vertex1), Net(vertex0, vertex1),
            Net(vertex1, vertex0), Net(vertex1, vertex0),
            Net(vertex0, vertex2)]
    
    placements = {vertex0: (0, 0), vertex1: (1, 0), vertex2: (0, 0)}
    allocations = {vertex0: {Cores: slice(0, 1)},
                   vertex1: {}, vertex2: {}}
    
    constraints = [RouteEndpointConstraint(vertex2, Routes.south_west)]
    
    routes = {
        nets[0]: RoutingTree((0, 0), set([
            (Routes.east, RoutingTree((1, 0), set([
                (Routes.core(0), vertex1)])))])),
        nets[1]: RoutingTree((0, 0), set([
            (Routes.east, RoutingTree((1, 0), set([
                (Routes.core(0), vertex1)])))])),
            
        nets[2]: RoutingTree((1, 0), set([
            (Routes.west, RoutingTree((0, 0), set([
                (Routes.core(0), vertex0)])))])),
        nets[3]: RoutingTree((1, 0), set([
            (Routes.west, RoutingTree((0, 0), set([
                (Routes.core(0), vertex0)])))])),
        
        nets[4]: RoutingTree((0, 0), set([
            (Routes.south_west, vertex2)])),
    }
    
    d = Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                constraints=constraints,
                placements=placements,
                allocations=allocations,
                routes=routes)
    
    # Make sure only the links going west/east and south-west/north_east between
    # (0, 0) and (1, 0) have any nets in them.
    for (x, y, link), link_nets in iteritems(d._link_nets):
        if (x, y, link) not in [(0, 0, Links.east), (1, 0, Links.west),
                                (0, 0, Links.south_west),
                                (1, 0, Links.north_east)]:
            assert link_nets == []
    
    # Make sure both ends list all nets (and nothing else)
    from_00 = (d._link_nets[(0, 0, Links.east)] +
               d._link_nets[(0, 0, Links.south_west)])
    from_10 = (d._link_nets[(1, 0, Links.west)] +
               d._link_nets[(1, 0, Links.north_east)])
    assert len(nets) == len(from_00)
    assert len(nets) == len(from_10)
    assert set(nets) == set(from_00)
    assert set(nets) == set(from_10)
    
    # Make sure that the net listings are in opposite orders
    assert d._link_nets[(1, 0, Links.west)] == \
        d._link_nets[(0, 0, Links.east)][::-1]
    assert d._link_nets[(1, 0, Links.north_east)] == \
        d._link_nets[(0, 0, Links.south_west)][::-1]


class TestDoesntCrash():
    """These tests simply check that various simples sets of input arguments
    don't cause a crash and for some of them checks the output against a known
    correct rendering."""
    
    def test_no_vertices(self, checked_ctx, width, height):
        # A full machine with wrap-around links and cores on every chip should
        # be drawn.
        machine = Machine(2, 2)
        Diagram(machine=machine).draw(checked_ctx, width, height)
    
    def test_broken_machine(self, checked_ctx, width, height):
        # Each of the breakages below should be recorded
        machine = Machine(2, 2)
        machine.dead_chips.add((1, 1))
        machine.dead_links.add((0, 1, Links.north))
        
        machine.chip_resource_exceptions[(0, 0)] = {Cores:1}
        machine.chip_resource_exceptions[(1, 0)] = {Cores:7}
        machine.chip_resource_exceptions[(0, 1)] = {Cores:10}
        
        Diagram(machine=machine).draw(checked_ctx, width, height)
    
    def test_no_nets(self, checked_ctx, width, height):
        # Should draw a diagram with two vertices allocated on 0, 0
        machine = Machine(2, 2)
        vertex = object()
        vertices_resources = {vertex: {Cores: 2}}
        
        placements = {vertex: (0, 0)}
        allocations = {vertex: {Cores: slice(0, 2)}}
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                placements=placements,
                allocations=allocations).draw(checked_ctx, width, height)
    
    @pytest.mark.parametrize("ratsnest", [True, False])
    def test_custom_styles(self, checked_ctx, width, height, ratsnest):
        # Check that style exceptions work
        machine = Machine(3, 3)
        vertex0 = object()
        vertex1 = object()
        vertices_resources = {vertex0: {Cores: 1}, vertex1: {Cores: 1}}
        nets = [Net(vertex0, vertex0),
                Net(vertex1, vertex1),
                Net(vertex0, vertex1),
                Net(vertex1, vertex0)]
        
        placements = {vertex0: (0, 0), vertex1: (1, 1)}
        allocations = {vertex0: {Cores: slice(0, 1)},
                       vertex1: {Cores: slice(0, 1)}}
        if ratsnest:
            routes = {}
        else:
            routes = rig.place_and_route.route(
                vertices_resources, nets, machine, [],
                placements, allocations)
        
        chip_style = default_chip_style.copy()
        link_style = default_link_style.copy()
        core_style = default_core_style.copy()
        net_style = default_net_style.copy()
        
        chip_style.set((2, 2), "stroke", (1.0, 0.0, 0.0, 1.0))
        
        for link in [(2, 2, Links.north), (2, 0, Links.south)]:
            link_style.set(link, "stroke", (1.0, 0.0, 0.0, 1.0))
            link_style.set(link, "fill", (0.0, 1.0, 0.0, 1.0))
        
        core_style.set(vertex0, "fill", (1.0, 0.0, 1.0, 1.0))
        
        net_style.set(nets[0], "stroke", (0.0, 1.0, 1.0, 1.0))
        net_style.set(nets[2], "stroke", (0.0, 1.0, 1.0, 1.0))
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                placements=placements,
                allocations=allocations,
                chip_style=chip_style,
                link_style=link_style,
                core_style=core_style,
                net_style=net_style,
                routes=routes).draw(checked_ctx, width, height)
    
    @pytest.mark.parametrize("ratsnest", [True, False])
    def test_zero_weight_nets(self, checked_ctx, width, height, ratsnest):
        # Should draw the nets but faintly. Both for self-loops and direct hops.
        machine = Machine(3, 3)
        vertex0 = object()
        vertex1 = object()
        vertices_resources = {vertex0: {Cores: 1}, vertex1: {Cores: 1}}
        nets = [Net(vertex0, vertex0, weight=0.0),
                Net(vertex0, vertex1, weight=0.0)]
        
        placements = {vertex0: (0, 0), vertex1: (1, 1)}
        allocations = {vertex0: {Cores: slice(0, 1)},
                       vertex1: {Cores: slice(0, 1)}}
        if ratsnest:
            routes = {}
        else:
            routes = rig.place_and_route.route(
                vertices_resources, nets, machine, [],
                placements, allocations)
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                placements=placements,
                allocations=allocations,
                routes=routes).draw(checked_ctx, width, height)
    
    @pytest.mark.parametrize("ratsnest", [True, False])
    def test_null_nets(self, checked_ctx, width, height, ratsnest):
        # Nets which don't have any sinks should not be drawn.
        machine = Machine(2, 2)
        vertex = object()
        vertices_resources = {vertex: {Cores: 2}}
        nets = [Net(vertex, [])]
        
        placements = {vertex: (0, 0)}
        allocations = {vertex: {Cores: slice(0, 2)}}
        if ratsnest:
            routes = {}
        else:
            routes = rig.place_and_route.route(
                vertices_resources, nets, machine, [],
                placements, allocations)
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                placements=placements,
                allocations=allocations,
                routes=routes).draw(checked_ctx, width, height)
    
    @pytest.mark.parametrize("ratsnest", [True, False])
    def test_non_core_endpoints_nets(self, checked_ctx, width, height, ratsnest):
        # Should be able to draw nets between vertices with and without cores.
        machine = Machine(3, 3)
        core_vertex = object()
        no_core_vertex = object()
        vertices_resources = {core_vertex: {Cores: 1}, no_core_vertex: {}}
        nets = [Net(core_vertex, no_core_vertex),
                Net(no_core_vertex, core_vertex)]
        
        placements = {core_vertex: (0, 0), no_core_vertex: (1, 1)}
        allocations = {core_vertex: {Cores: slice(0, 1)}, no_core_vertex: {}}
        
        if ratsnest:
            routes = {}
        else:
            routes = rig.place_and_route.route(
                vertices_resources, nets, machine, [],
                placements, allocations)
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                placements=placements,
                allocations=allocations,
                routes=routes).draw(checked_ctx, width, height)
    
    def test_single_board(self, checked_ctx, width, height):
        # Should be able to render a 48 node board.
        machine = Machine(8, 8)
        nominal_live_chips = set([  # noqa
                                            (4, 7), (5, 7), (6, 7), (7, 7),
                                    (3, 6), (4, 6), (5, 6), (6, 6), (7, 6),
                            (2, 5), (3, 5), (4, 5), (5, 5), (6, 5), (7, 5),
                    (1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 4), (7, 4),
            (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3), (7, 3),
            (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
            (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
            (0, 0), (1, 0), (2, 0), (3, 0), (4, 0),
        ])
        machine.dead_chips = set((x, y)
                                 for x in range(8)
                                 for y in range(8)) - nominal_live_chips
        Diagram(machine=machine).draw(checked_ctx, width, height)
    
    @pytest.mark.parametrize("w,h", [(3, 3), (3, 6), (6, 3)])
    @pytest.mark.parametrize("wrap_around", [True, False])
    @pytest.mark.parametrize("ratsnest", [True, False])
    @pytest.mark.parametrize("kwargs", [
            # Default options
            {},
            # Override the net weight
            {"net_weight_scale": 0.1},
            # Hide links
            {"link_style": Style()},
            # Hide chips
            {"chip_style": Style()},
            # Hide cores
            {"core_style": Style()},
            # Hide nets
            {"net_style": Style()},
        ])
    def test_network(self, ctx, width, height, w, h, wrap_around, ratsnest,
                     kwargs):
        # Shouldn't crash when being told to plot a simple network both with and
        # without wrap-around and with and without routes.
        
        # In this network, each chip has two core with one vertex using up both
        # cores on each chip. Each vertex is connected to its eight
        # immediate neighbours (if thought of as a square grid) and itself by a
        # net with a random weight. Finally, there is a zero-weight net
        # connecting all nodes.
        
        machine = Machine(w, h, chip_resources={Cores: 4})
        
        # Remove all wrap-around links if wrap-around disabled
        if not wrap_around:
            for x in range(w):
                machine.dead_links.add((x, 0, Links.south))
                machine.dead_links.add((x, 0, Links.south_west))
                machine.dead_links.add((x, h - 1, Links.north))
                machine.dead_links.add((x, h - 1, Links.north_east))
            for y in range(h):
                machine.dead_links.add((0, y, Links.west))
                machine.dead_links.add((0, y, Links.south_west))
                machine.dead_links.add((w - 1, y, Links.east))
                machine.dead_links.add((w - 1, y, Links.north_east))
        
        vertices = {(x, y): object() for x in range(w) for y in range(h)}
        placements = {v: xy for xy, v in iteritems(vertices)}
        vertices_resources = {v: {Cores: 2} for v in placements}
        allocations = {v: {Cores: slice(0, 2)} for v in placements}
        constraints = []
        
        def i(x, y):
            return vertices[(x % w, y % h)]
        nets = [Net(i(x, y),
                    [i(x+1,y+1),  # Top
                     i(x+0,y+1),
                     i(x-1,y+1),  # Left
                     i(x-1,y+0),
                     i(x-1,y-1),  # Bottom
                     i(x+0,y-1),
                     i(x+1,y-1),  # Right
                     i(x+1,y+0),
                     i(x+0,y+0),  # Self-loop
                     ], weight=0.3 + random.random()*0.7)
                for x in range(w)
                for y in range(h)]
        
        # Use rig's router to route the example network
        if ratsnest:
            routes = {}
        else:
            routes = rig.place_and_route.route(
                vertices_resources, nets, machine, constraints,
                placements, allocations)
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                constraints=constraints,
                placements=placements,
                allocations=allocations,
                routes=routes, **kwargs).draw(ctx, width, height)
