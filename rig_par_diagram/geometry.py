"""Generic geometry function used by the diagram generator."""

def get_core_ring_position(num_cores, core_num):
    """When arranging cores in concentric rings of hexagons, this function
    calculates the position of a given core within that arrangement.
    
    Cores are arranged in layers like concentric hexagons like so::
    
          2 2 2
         2 1 1 2
        2 1 0 1 2
         2 1 1 2
          2 2 2
    
    Parameters
    ----------
    num_cores : int
        The total number of cores which are arranged in the concentric rings of
        hexagons.
    core_num : int
        The index of the core who's position in the concentric rings we're
        interested in.
    
    Returns
    -------
    (layer, core_num, num_in_layer)
        * layer is the layer number the core is on (starting at 0 for the
          central core).
        * core_num is the index of the core within the layer.
        * num_in_layer is the total number of cores in the same layer.
    """
    if core_num == 0:
        return (0, 0, 1)
    
    layer = 0
    num_in_full_layer = 1
    while core_num >= num_in_full_layer:
        core_num -= num_in_full_layer
        num_cores -= num_in_full_layer
        
        layer += 1
        num_in_full_layer = (layer * 6)
    
    num_in_layer = min(num_cores, num_in_full_layer)
    
    return (layer, core_num, num_in_layer)

