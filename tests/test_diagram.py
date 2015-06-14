"""Basic sanity checks for diagram generation.

Unfortunately testing graphics generation code is a meaningful way is fairly
tough. These tests can broadly be split into two categories:

* Sanity checking general data structure generation.
* Running various example designs and checking nothing crashes.
"""

import pytest

import random

from six import iteritems

import cairocffi as cairo

from parspective.diagram import Diagram

from parspective.style import PolygonStyle

import rig

from rig.machine import Machine, Cores, Links

from rig.netlist import Net

from rig.place_and_route.routing_tree import RoutingTree

from rig.routing_table import Routes

from rig.place_and_route.constraints import \
    ReserveResourceConstraint, RouteEndpointConstraint


@pytest.fixture
def width():
    return 10

@pytest.fixture
def height():
    return 10


@pytest.yield_fixture
def ctx(width, height):
    """A tiny cairo context to render into."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                 width,
                                 height)
    ctx = cairo.Context(surface)
    yield ctx
    surface.write_to_png("/dev/null")


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
    don't cause a crash."""
    
    def test_no_vertices(self, ctx, width, height):
        # The diagram generator shouldn't fail when given no vertices
        machine = Machine(2, 2)
        Diagram(machine=machine).draw(ctx, width, height)
        
    
    def test_no_nets(self, ctx, width, height):
        # Shouldn't crash when the diagram has no nets
        core_resource = object()
        
        machine = Machine(2, 2)
        vertex = object()
        vertices_resources = {vertex: {Cores: 2}}
        
        placements = {vertex: (0, 0)}
        allocations = {vertex: {Cores: slice(0, 2)}}
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                placements=placements,
                allocations=allocations).draw(ctx, width, height)
    
    def test_zero_weight_nets(self, ctx, width, height):
        # Shouldn't crash when the diagram has a net which has zero weight
        core_resource = object()
        
        machine = Machine(2, 2)
        vertex = object()
        vertices_resources = {vertex: {Cores: 2}}
        nets = [Net(vertex, vertex, weight=0.0)]
        
        placements = {vertex: (0, 0)}
        allocations = {vertex: {Cores: slice(0, 2)}}
        routes = rig.place_and_route.route(
            vertices_resources, nets, machine, [],
            placements, allocations)
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                placements=placements,
                allocations=allocations,
                routes=routes).draw(ctx, width, height)
    
    def test_null_nets(self, ctx, width, height):
        # Shouldn't crash when the diagram has a net going to nowhere
        core_resource = object()
        
        machine = Machine(2, 2)
        vertex = object()
        vertices_resources = {vertex: {Cores: 2}}
        nets = [Net(vertex, [])]
        
        placements = {vertex: (0, 0)}
        allocations = {vertex: {Cores: slice(0, 2)}}
        routes = rig.place_and_route.route(
            vertices_resources, nets, machine, [],
            placements, allocations)
        
        Diagram(machine=machine,
                vertices_resources=vertices_resources,
                nets=nets,
                placements=placements,
                allocations=allocations,
                routes=routes).draw(ctx, width, height)
    
    @pytest.mark.parametrize("ratsnest", [True, False])
    def test_non_core_endpoints_nets(self, ctx, width, height, ratsnest):
        # Shouldn't crash when nets have vertices with no cores allocated at
        # either or both ends of the net.
        core_resource = object()
        
        machine = Machine(3, 3)
        core_vertex = object()
        no_core_vertex = object()
        vertices_resources = {core_vertex: {Cores: 1}, no_core_vertex: {}}
        nets = [Net(core_vertex, no_core_vertex),
                Net(no_core_vertex, core_vertex),
                Net(no_core_vertex, no_core_vertex)]
        
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
                routes=routes).draw(ctx, width, height)
        print("eh?")
    
    def test_single_board(self, ctx, width, height):
        # Shouldn't crash when the machine has missing cores and links.
        core_resource = object()
        
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
        Diagram(machine=machine).draw(ctx, width, height)
    
    @pytest.mark.parametrize("w,h", [(3, 3), (3, 6), (6, 3)])
    @pytest.mark.parametrize("wrap_around", [True, False])
    @pytest.mark.parametrize("ratsnest", [True, False])
    @pytest.mark.parametrize("kwargs", [
            # Default options
            {},
            # Override the net weight
            {"net_weight_scale": 0.1},
            # Hide links
            {"link_style": PolygonStyle()},
            # Hide chips
            {"chip_style": PolygonStyle()},
            # Hide cores
            {"core_style": PolygonStyle()},
            # Hide nets
            {"net_style": PolygonStyle()},
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
