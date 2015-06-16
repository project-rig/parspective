#!/usr/bin/env python

"""Print the path of the local Rig P&R Diagram installation."""

if __name__=="__main__":  # pragma: no cover
    import rig_par_diagram
    import os.path
    print(os.path.dirname(rig_par_diagram.__file__))
