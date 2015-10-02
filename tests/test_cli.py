import pytest

import tempfile

import os

import pickle

from mock import Mock

from rig.machine import Machine, Cores

from rig.place_and_route.constraints import ReserveResourceConstraint

from rig_par_diagram.cli import \
    main, read_netlist, get_machine, place, allocate, route

from rig_par_diagram import default_core_style

@pytest.yield_fixture
def filename():
    fno, fname = tempfile.mkstemp()
    
    yield fname
    
    os.remove(fname)


def test_read_netlist(filename):
    # Passing a directory name or non-existant file should fail
    with pytest.raises(SystemExit):
        read_netlist("/")
    with pytest.raises(SystemExit):
        read_netlist("/doesnotexistonmostsystems")
    
    # Passing an empty file should fail
    with pytest.raises(SystemExit):
        read_netlist("/dev/null")
    
    # Passing in a pickled onion should fail
    with open(filename, "wb") as f:
        pickle.dump("onion", f)
    with pytest.raises(SystemExit):
        read_netlist(filename)
    
    # Passing in a dictionary should work fine!
    with open(filename, "wb") as f:
        pickle.dump({"just": "fine"}, f)
    assert read_netlist(filename) == {"just": "fine"}


def test_get_machine():
    # Default should be a SpiNN-5 board
    assert len(list(get_machine())) == 48
    
    # Should be able to get specially named machines
    assert len(list(get_machine("spinn5"))) == 48
    assert len(list(get_machine("spinn3"))) == 4
    
    # Should be able to specify a size
    m = get_machine("4x3")
    assert m.width == 4
    assert m.height == 3
    
    # Shouldn't be able to pass in anything invalid
    with pytest.raises(SystemExit):
        get_machine("foo")
    
    # Should have the right types of core resource
    for spec in [None, "spinn3", "spinn5", "8x8"]:
        m = get_machine(spec, "cores")
        assert "cores" in m.chip_resources
        assert Cores not in m.chip_resources


def test_place(monkeypatch):
    from rig.place_and_route.place import sa as sa_module
    import rig.place_and_route as par_module
    mock_default = Mock()
    mock_sa = Mock()
    monkeypatch.setattr(sa_module, "place", mock_sa)
    monkeypatch.setattr(par_module, "place", mock_default)
    
    # Should default to the default algorithm
    place(None, None, None, None)
    assert mock_default.called
    assert not mock_sa.called
    mock_default.reset_mock()
    
    # Should default to the default algorithm when asked for the default
    place(None, None, None, None, "default")
    assert mock_default.called
    assert not mock_sa.called
    mock_default.reset_mock()
    
    # Should use an alternative when asked
    place(None, None, None, None, "sa")
    assert not mock_default.called
    assert mock_sa.called
    mock_sa.reset_mock()
    
    # Should fail if unknown
    with pytest.raises(SystemExit):
        place(None, None, None, None, "doesnotexist")


def test_allocate(monkeypatch):
    from rig.place_and_route.allocate import greedy as greedy_module
    import rig.place_and_route as par_module
    mock_default = Mock()
    mock_greedy = Mock()
    monkeypatch.setattr(greedy_module, "allocate", mock_greedy)
    monkeypatch.setattr(par_module, "allocate", mock_default)
    
    # Should default to the default algorithm
    allocate(None, None, None, None, None)
    assert mock_default.called
    assert not mock_greedy.called
    mock_default.reset_mock()
    
    # Should default to the default algorithm when asked for the default
    allocate(None, None, None, None, None, "default")
    assert mock_default.called
    assert not mock_greedy.called
    mock_default.reset_mock()
    
    # Should use an alternative when asked
    allocate(None, None, None, None, None, "greedy")
    assert not mock_default.called
    assert mock_greedy.called
    mock_greedy.reset_mock()
    
    # Should fail if unknown
    with pytest.raises(SystemExit):
        allocate(None, None, None, None, None, "doesnotexist")


def test_route(monkeypatch):
    from rig.place_and_route.route import ner as ner_module
    import rig.place_and_route as par_module
    mock_default = Mock()
    mock_ner = Mock()
    monkeypatch.setattr(ner_module, "route", mock_ner)
    monkeypatch.setattr(par_module, "route", mock_default)
    
    # Should default to the default algorithm
    route(None, None, None, None, None, None, "default", Cores)
    assert mock_default.called
    assert not mock_ner.called
    mock_default.reset_mock()
    
    # Should default to the default algorithm when asked for the default
    route(None, None, None, None, None, None, "default", Cores)
    assert mock_default.called
    assert not mock_ner.called
    mock_default.reset_mock()
    
    # Should use an alternative when asked
    route(None, None, None, None, None, None, "ner", Cores)
    assert not mock_default.called
    assert mock_ner.called
    mock_ner.reset_mock()
    
    # Should fail if unknown
    with pytest.raises(SystemExit):
        route(None, None, None, None, None, None, "doesnotexist", Cores)


@pytest.mark.parametrize(
    "args, given_machine,placed,allocated,routed,should_place,should_allocate,should_route",
    [("", True, False, False, False, True, True, True),
     ("", True, True, False, False, False, True, True),
     ("", True, True, True, False, False, False, True),
     ("", True, True, True, True, False, False, False),
     # When machine is not provided, should re-run everything regardless.
     ("", False, True, True, True, True, True, True),
     # With ratsnest the router should never get used
     ("-R", True, True, True, True, False, False, False),
     ("-R", True, True, True, False, False, False, False),
     ("-R", True, True, False, False, False, True, False),
     ("-R", True, False, False, False, True, True, False),
     ("-R", False, True, True, True, True, True, False),
     ("-R", False, False, False, False, True, True, False),
     # When forcing a new machine everything should run
     ("-m 4x4", True, False, False, False, True, True, True),
     ("-m 4x4", True, True, False, False, True, True, True),
     ("-m 4x4", True, True, True, False, True, True, True),
     ("-m 4x4", True, True, True, True, True, True, True),
     # When forcing placement, everything should run
     ("-p", True, False, False, False, True, True, True),
     ("-p", True, True, False, False, True, True, True),
     ("-p", True, True, True, False, True, True, True),
     ("-p", True, True, True, True, True, True, True),
     # When forcing allocate, routing should also run
     ("-a", True, False, False, False, True, True, True),
     ("-a", True, True, False, False, False, True, True),
     ("-a", True, True, True, False, False, True, True),
     ("-a", True, True, True, True, False, True, True),
     # When forcing routing, it should run
     ("-r", True, False, False, False, True, True, True),
     ("-r", True, True, False, False, False, True, True),
     ("-r", True, True, True, False, False, False, True),
     ("-r", True, True, True, True, False, False, True),
    ])
def test_auto_par(filename, args, given_machine, placed, allocated, routed,
                  should_place, should_allocate, should_route, monkeypatch):
    # Test whether the tool automatically places allocates and routes netlists
    # correctly.
    with open(filename, "wb") as f:
        netlist = {
            "vertices_resources": {},
            "nets": [],
            "constraints": [],
        }
        if given_machine:
            netlist["machine"] = Machine(2, 2)
        if placed:
            netlist["placements"] = {}
        if allocated:
            netlist["allocations"] = {}
        if routed:
            netlist["routes"] = {}
        pickle.dump(netlist, f)
    
    from rig_par_diagram import cli
    monkeypatch.setattr(cli, "place", Mock(side_effect=cli.place))
    monkeypatch.setattr(cli, "allocate", Mock(side_effect=cli.allocate))
    monkeypatch.setattr(cli, "route", Mock(side_effect=cli.route))
    
    assert main("app {} /dev/null 10 10 {}".format(filename, args).strip().split()) == 0
    
    assert cli.place.called == should_place
    assert cli.allocate.called == should_allocate
    assert cli.route.called == should_route


@pytest.mark.parametrize("args,should_colour",[("", True),
                                               ("-C", False)])
def test_auto_colour_constraints(filename, args, should_colour, monkeypatch):
    # Test whether the tool automatically places allocates and routes netlists
    # correctly.
    with open(filename, "wb") as f:
        netlist = {
            "vertices_resources": {},
            "nets": [],
            "constraints": [ReserveResourceConstraint(Cores, slice(0, 1)),
                            ReserveResourceConstraint(Cores, slice(1, 2))],
        }
        netlist["core_style"] = default_core_style.copy()
        netlist["core_style"].set(netlist["constraints"][1], "fill", None)
        pickle.dump(netlist, f)
    
    from rig_par_diagram import cli
    monkeypatch.setattr(cli, "Diagram",
        Mock(side_effect=cli.Diagram))
    
    assert main("app {} /dev/null 10 10 {}".format(filename, args).strip().split()) == 0
    
    call_kwargs = cli.Diagram.mock_calls[0][2]
    
    # Constraint style should have been added if requested.
    assert len(call_kwargs["core_style"]._exceptions) == 3 if should_colour else 2


def test_core_resource(filename, monkeypatch):
    # Test that the core_resource option actually gets taken into account.
    with open(filename, "wb") as f:
        netlist = {
            "vertices_resources": {},
            "nets": [],
            "core_resource": "cores",
        }
        pickle.dump(netlist, f)
    
    from rig_par_diagram import cli
    monkeypatch.setattr(cli, "Diagram",
        Mock(side_effect=cli.Diagram))
    
    assert main("app {} /dev/null 10 10".format(filename).split()) == 0
    
    call_kwargs = cli.Diagram.mock_calls[0][2]
    
    assert "cores" in call_kwargs["machine"].chip_resources
    assert Cores not in call_kwargs["machine"].chip_resources
    assert call_kwargs["core_resource"] == "cores"


@pytest.mark.parametrize("args,has_constraints,should_reserve", [
        # With no constraints added, one should be added to reserve the monitor.
        ("", False, True),
        # If requested not to, no resource should be added
        ("-M", False, False),
        # With some constraints specified, no additional reservation should be
        # added.
        ("", True, False),
        ("-M", True, False),
    ])
def test_auto_monitor_constraint(filename, args, has_constraints,
                                 should_reserve, monkeypatch):
    # Test whether the tool automatically places allocates and routes netlists
    # correctly.
    with open(filename, "wb") as f:
        netlist = {
            "vertices_resources": {},
            "nets": [],
        }
        if has_constraints:
            netlist["constraints"] = []
        pickle.dump(netlist, f)
    
    from rig_par_diagram import cli
    monkeypatch.setattr(cli, "Diagram",
        Mock(side_effect=cli.Diagram))
    
    assert main("app {} /dev/null 10 10 {}".format(filename, args).strip().split()) == 0
    
    call_kwargs = cli.Diagram.mock_calls[0][2]
    
    # Constraint should have been added if requested.
    if should_reserve:
        assert len(call_kwargs["constraints"]) == 1
        constraint = call_kwargs["constraints"][0]
        assert isinstance(constraint, ReserveResourceConstraint)
        assert constraint.resource == Cores
        assert constraint.reservation == slice(0, 1)
        assert constraint.location is None
    else:
        assert len(call_kwargs["constraints"]) == 0


@pytest.mark.parametrize("args", [
        # Verbosity
        "-v", "-vv", "-vvv",
        # Transparent background
        "-t",
        # Taller machines
        "-m 2x16",
        # Wider machines
        "-m 16x2",
    ])
def test_sanity_check(args):
    # Sanity check that other options don't fail but don't check their output.
    assert main("app - /dev/null {}".format(args).strip().split()) == 0
