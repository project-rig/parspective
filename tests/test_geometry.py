import pytest

from rig_par_diagram.geometry import get_core_ring_position

def test_get_core_ring_position():
    # Single-core case
    assert get_core_ring_position(1, 0) == (0, 0, 1)
    
    # Exhaustively test a three-layer example
    #      6 5 4
    #     7 5 4 3
    #    8 6 0 3 2
    #     7 1 2 1
    #      8 9 0
    assert get_core_ring_position(19, 0) == (0, 0, 1)
    
    assert get_core_ring_position(19, 1) == (1, 0, 6)
    assert get_core_ring_position(19, 2) == (1, 1, 6)
    assert get_core_ring_position(19, 3) == (1, 2, 6)
    assert get_core_ring_position(19, 4) == (1, 3, 6)
    assert get_core_ring_position(19, 5) == (1, 4, 6)
    assert get_core_ring_position(19, 6) == (1, 5, 6)
    
    assert get_core_ring_position(19, 7) == (2, 0, 12)
    assert get_core_ring_position(19, 8) == (2, 1, 12)
    assert get_core_ring_position(19, 9) == (2, 2, 12)
    assert get_core_ring_position(19, 10) == (2, 3, 12)
    assert get_core_ring_position(19, 11) == (2, 4, 12)
    assert get_core_ring_position(19, 12) == (2, 5, 12)
    assert get_core_ring_position(19, 13) == (2, 6, 12)
    assert get_core_ring_position(19, 14) == (2, 7, 12)
    assert get_core_ring_position(19, 15) == (2, 8, 12)
    assert get_core_ring_position(19, 16) == (2, 9, 12)
    assert get_core_ring_position(19, 17) == (2, 10, 12)
    assert get_core_ring_position(19, 18) == (2, 11, 12)
    
    # Exhaustively test an example where the outer ring is not full
    # Exhaustively test a three-layer example
    #     3
    #      0 2
    #     1
    assert get_core_ring_position(4, 0) == (0, 0, 1)
    
    assert get_core_ring_position(4, 1) == (1, 0, 3)
    assert get_core_ring_position(4, 2) == (1, 1, 3)
    assert get_core_ring_position(4, 3) == (1, 2, 3)
