"""A stand-alone command-line front end to Rig P&R Diagram.

The principle input format to the program is pickled Rig netlists and other
relevant metadata.

The netlist should be provided in the form of a pickled dictionary containing a
subset of the following:
  * 'vertices_resources': Chip resources used.
  * 'nets': Nets in the network.
  * 'machine': The machine to place/route within.
  * 'constraints': Placement/routing constraints.
  * 'placements': A valid set of placements.
  * 'allocations': A valid set of allocations.
  * 'routes': A valid set of routes.
  * 'chip_style': A Rig P&R Diagram Style object.
  * 'link_style': A Rig P&R Diagram Style object.
  * 'core_style': A Rig P&R Diagram Style object.
  * 'net_style': A Rig P&R Diagram Style object.
"""

import argparse

import pickle

import sys

import time

from importlib import import_module

import logging

import cairocffi as cairo

from rig.machine import Machine, Links, Cores

from rig.place_and_route.constraints import ReserveResourceConstraint

from rig_par_diagram import \
    Diagram, \
    default_chip_style, \
    default_link_style, \
    default_core_style, \
    default_net_style


logger = logging.getLogger(__name__)


def read_netlist(filename):
    """Returns a netlist on success and exits on failure."""
    # Read the netlist
    try:
        netlist = pickle.load(open(filename, "rb"))
    except IOError:
        sys.stdout.write("Netlist file not found\n")
        sys.exit(1)
    except (pickle.PickleError, AttributeError, EOFError, IndexError):
        sys.stdout.write("Netlist could not be unpickled\n")
        sys.exit(1)
    
    # Check the netlist contains the bare minimum of information
    if not isinstance(netlist, dict):
        sys.stdout.write(
            "Netlist must be defined in a dictionary\n")
        sys.exit(1)
    
    logger.info("Loaded netlist with fields: {}".format(
        ", ".join(netlist)))
    
    return netlist


def get_machine(spec=None, core_resource=Cores):
    """Get a rig Machine object based on the supplied specification."""
    if spec is None:
        # Default to a SpiNN-5 board
        return get_machine("spinn5", core_resource)
    elif spec == "spinn3":
        machine = Machine(2, 2)
        if core_resource is not Cores:
            machine.chip_resources[core_resource] = machine.chip_resources[Cores]
            del machine.chip_resources[Cores]
        
        machine.dead_links.add((0, 0, Links.south_west))
        machine.dead_links.add((1, 1, Links.north_east))
        
        machine.dead_links.add((0, 1, Links.south_west))
        machine.dead_links.add((1, 0, Links.north_east))
        
        machine.dead_links.add((0, 0, Links.west))
        machine.dead_links.add((1, 0, Links.east))
        
        machine.dead_links.add((0, 1, Links.west))
        machine.dead_links.add((1, 1, Links.east))
        
        return machine
    elif spec == "spinn5":
        machine = Machine(8, 8)
        if core_resource is not Cores:
            machine.chip_resources[core_resource] = machine.chip_resources[Cores]
            del machine.chip_resources[Cores]
        
        # Kill all chips outside the board
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
        
        # Kill all any-around links which remain.
        for x in range(machine.width):
            machine.dead_links.add((x, 0, Links.south))
            machine.dead_links.add((x, 0, Links.south_west))
            machine.dead_links.add((x, machine.height - 1, Links.north))
            machine.dead_links.add((x, machine.height - 1, Links.north_east))
        for y in range(machine.height):
            machine.dead_links.add((0, y, Links.west))
            machine.dead_links.add((0, y, Links.south_west))
            machine.dead_links.add((machine.width - 1, y, Links.east))
            machine.dead_links.add((machine.width - 1, y, Links.north_east))
        
        return machine
    else:
        # Specification of the form "XxY"
        
        if "x" not in spec:
            sys.stderr.write(
                "Machine must be of the form NxM or spinn3 or spinn5.")
            sys.exit(1)
        
        x, _, y = spec.partition("x")
        x = int(x)
        y = int(y)
        
        machine = Machine(x, y)
        if core_resource is not Cores:
            machine.chip_resources[core_resource] = machine.chip_resources[Cores]
            del machine.chip_resources[Cores]
        
        return machine


def place(vertices_resources, nets, machine, constraints, algorithm="default"):
    """Place the specified netlist."""
    if algorithm == "default":
        module = "rig.place_and_route"
        algorithm = "default"
    else:
        module = "rig.place_and_route.place.{}".format(algorithm)
    
    try:
        placer = getattr(import_module(module), "place")
    except (ImportError, AttributeError):
        sys.stderr.write(
            "Placement algorithm {} does not exist\n".format(algorithm))
        sys.exit(1)
    
    logger.info("Placing netlist using '{}'...".format(algorithm))
    
    before = time.time()
    placements = placer(vertices_resources, nets, machine, constraints)
    after = time.time()
    
    logger.info("Placed netlist in {:.2f}s".format(after - before))
    
    return placements


def allocate(vertices_resources, nets, machine, constraints,
             placements, algorithm="default"):
    """Allocate resources for the specified netlist."""
    if algorithm == "default":
        module = "rig.place_and_route"
        algorithm = "default"
    else:
        module = "rig.place_and_route.allocate.{}".format(algorithm)
    
    try:
        allocator = getattr(import_module(module), "allocate")
    except (ImportError, AttributeError):
        sys.stderr.write(
            "Allocation algorithm {} does not exist\n".format(algorithm))
        sys.exit(1)
    
    logger.info("Allocating netlist using '{}'...".format(algorithm))
    
    before = time.time()
    allocations = allocator(vertices_resources, nets, machine, constraints,
                            placements)
    after = time.time()
    
    logger.info("Allocated netlist in {:.2f}s".format(after - before))
    
    return allocations


def route(vertices_resources, nets, machine, constraints,
          placements, allocations, algorithm="default"):
    """Route all nets in the specified netlist."""
    if algorithm == "default":
        module = "rig.place_and_route"
        algorithm = "default"
    else:
        module = "rig.place_and_route.route.{}".format(algorithm)
    
    try:
        router = getattr(import_module(module), "route")
    except (ImportError, AttributeError):
        sys.stderr.write(
            "Routing algorithm {} does not exist\n".format(algorithm))
        sys.exit(1)
    
    logger.info("Routing netlist using '{}'...".format(algorithm))
    
    before = time.time()
    routes = router(vertices_resources, nets, machine, constraints,
                    placements, allocations)
    after = time.time()
    
    logger.info("Routed netlist in {:.2f}s".format(after - before))
    
    return routes


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(
        description="Generate a placement and routing diagram for a "
                    "Rig netlist.")
    
    parser.add_argument("netlist", metavar="NETLIST",
                        help="The filename of the netlist to present (a "
                             "pickled dictionary), or - to just generate."
                             "an empty machine diagram.")
    
    parser.add_argument("output", metavar="OUTPUT",
                        help="The output PNG filename.")
    
    parser.add_argument("width", metavar="WIDTH", nargs="?", default=1000,
                        type=int,
                        help="The width of the output image in pixels.")
    parser.add_argument("height", metavar="HEIGHT", nargs="?",
                        type=int,
                        help="The height of the output image in pixels.")
    
    parser.add_argument("--machine", "-m", metavar="MACHINE",
                        help="A SpiNNaker machine to place/route the "
                             "netlist into e.g. 48x24 or spinn5.")
    
    parser.add_argument("--no-reserve-monitor", "-M", action="store_true",
                        help="If no constraints are supplied in the netlist, "
                             "do not automatically reserve core 0 (the "
                             "default).")
    
    parser.add_argument("--place", "-p", metavar="ALGORITHM", nargs="?",
                        const="default",
                        help="Place the netlist using a Rig placement "
                             "algorithm.")
    
    parser.add_argument("--allocate", "-a", metavar="ALGORITHM", nargs="?",
                        const="default",
                        help="Allocate the netlist using a Rig placement "
                             "algorithm.")
    
    parser.add_argument("--route", "-r", metavar="ALGORITHM", nargs="?",
                        const="default",
                        help="Route the netlist using a Rig routing "
                             "algorithm.")
    
    parser.add_argument("--ratsnest", "-R", action="store_true",
                        help="Shows nets as a ratsnest (not the actual routes "
                             "used).")
    
    parser.add_argument("--no-colour-constraints", "-C", action="store_true",
                        help="Do not automatically colour cores reserved by "
                             "ReserveResourceConstraints.")
    
    parser.add_argument("--transparent", "-t", action="store_true",
                        help="Generate a transparent PNG.")
    
    parser.add_argument("--verbose", "-v", action="count", default=0,
                        help="Show verbose information.")
    
    args = parser.parse_args(argv[1:])
    
    global logger
    logger = logging.getLogger(argv[0])
    if args.verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose >= 1:
        logging.basicConfig(level=logging.INFO)
    
    # Parse the netlist (if provided)
    if args.netlist is not None and args.netlist != "-":
        netlist = read_netlist(args.netlist)
    else:
        netlist = {}
    
    # Work out what resource type cores are represented by
    core_resource = netlist.get("core_resource", Cores)
    
    vertices_resources = netlist.get("vertices_resources", {})
    nets = netlist.get("nets", [])
    
    # Get the machine from the netlist if possible, otherwise get it from the
    # command-line (defaulting to a SpiNN-5 board).
    machine = netlist.get("machine", None)
    machine_overridden = False
    if machine is None or args.machine:
        machine = get_machine(args.machine, core_resource)
        machine_overridden = True
    
    # If no constraints are supplied, reserve the monitor processor
    if "constraints" in netlist:
        constraints = netlist["constraints"]
    elif not args.no_reserve_monitor:
        constraints = [
            ReserveResourceConstraint(core_resource, slice(0, 1)),
        ]
    else:
        constraints = []
    
    # Get the placement solution if provided, otherwise place using the
    # algorithm specified on the command line.
    placements = netlist.get("placements", None)
    placements_overridden = False
    if placements is None or args.place or machine_overridden:
        placements = place(vertices_resources, nets, machine, constraints,
                           args.place or "default")
        placements_overridden = True
    
    # Get the allocation solution if provided, otherwise allocate using the
    # algorithm specified on the command line.
    allocations = netlist.get("allocations", None)
    allocations_overridden = False
    if allocations is None or args.allocate or placements_overridden:
        allocations = allocate(vertices_resources, nets, machine, constraints,
                               placements, args.allocate or "default")
        allocations_overridden = True
    
    # Get the routing solution if provided. If a routing algorithm is specified,
    # use that.
    routes = netlist.get("routes", None)
    if (routes is None or args.route or allocations_overridden) and not args.ratsnest:
        routes = route(vertices_resources, nets, machine, constraints,
                       placements, allocations, args.route or "default")
    
    # Delete the routes if a ratsnest is required
    if args.ratsnest:
        routes = {}
    
    # Load colour schemes
    chip_style = netlist.get("chip_style", default_chip_style.copy())
    link_style = netlist.get("link_style", default_link_style.copy())
    core_style = netlist.get("core_style", default_core_style.copy())
    net_style = netlist.get("net_style", default_net_style.copy())
    
    # Automatically make resource constraint cores grey and translucent.
    if not args.no_colour_constraints:
        for constraint in constraints:
            if constraint not in core_style:
                core_style.set(constraint, "fill",
                               (0.0, 0.0, 0.0, 0.3))
                core_style.set(constraint, "stroke", None)
    
    # Set up the diagram
    d = Diagram(machine=machine, vertices_resources=vertices_resources,
                nets=nets, constraints=constraints, placements=placements,
                allocations=allocations, routes=routes,
                core_resource=core_resource,
                chip_style=chip_style, link_style=link_style,
                core_style=core_style, net_style=net_style)
    
    # Work out the aspect ratio to allow automatic calculation of image
    # dimensions
    if args.height is None:
        x1, y1, x2, y2 = d.bbox
        w = x2 - x1
        h = y2 - y1
        ratio = h / w
        
        if ratio < 1.0:
            args.height = int(args.width * ratio)
        else:
            args.height, args.width = args.width, int(args.width / ratio)
    
    # Generate the image itself
    logging.info("Generating {}x{} diagram...".format(
        args.width, args.height))
    
    before = time.time()
    if args.transparent:
        mode = cairo.FORMAT_ARGB32
    else:
        mode = cairo.FORMAT_RGB24
    surface = cairo.ImageSurface(mode, args.width, args.height)
    
    ctx = cairo.Context(surface)
    
    # Draw opaque diagrams with a white background.
    if not args.transparent:
        with ctx:
            ctx.rectangle(0, 0, args.width, args.height)
            ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
            ctx.fill()
    
    d.draw(ctx, args.width, args.height)
    surface.write_to_png(args.output)
    after = time.time()
    
    logging.info("Generated diagram in {:.2f}s".format(after-before))
    
    return 0


if __name__=="__main__":  # pragma: no cover
    sys.exit(main(sys.argv))
