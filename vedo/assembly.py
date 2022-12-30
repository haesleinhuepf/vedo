#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np

try:
    import vedo.vtkclasses as vtk
except ImportError:
    import vtkmodules.all as vtk

import vedo

__doc__ = """
Submodule for managing groups of vedo objects
"""

__all__ = [
    "Group",
    "Assembly",
    "procrustes_alignment",
]


#################################################
def procrustes_alignment(sources, rigid=False):
    """
    Return an ``Assembly`` of aligned source meshes with the `Procrustes` algorithm.
    The output ``Assembly`` is normalized in size.

    The `Procrustes` algorithm takes N set of points and aligns them in a least-squares sense
    to their mutual mean. The algorithm is iterated until convergence,
    as the mean must be recomputed after each alignment.

    The set of average points generated by the algorithm can be accessed with
    ``algoutput.info['mean']`` as a numpy array.

    Parameters
    ----------
    rigid : bool
        if `True` scaling is disabled.

    .. hint:: examples/basic/align4.py
        .. image:: https://vedo.embl.es/images/basic/align4.png
    """

    group = vtk.vtkMultiBlockDataGroupFilter()
    for source in sources:
        if sources[0].npoints != source.npoints:
            vedo.logger.error("sources have different nr of points")
            raise RuntimeError()
        group.AddInputData(source.polydata())
    procrustes = vtk.vtkProcrustesAlignmentFilter()
    procrustes.StartFromCentroidOn()
    procrustes.SetInputConnection(group.GetOutputPort())
    if rigid:
        procrustes.GetLandmarkTransform().SetModeToRigidBody()
    procrustes.Update()

    acts = []
    for i, s in enumerate(sources):
        poly = procrustes.GetOutput().GetBlock(i)
        mesh = vedo.mesh.Mesh(poly)
        mesh.SetProperty(s.GetProperty())
        if hasattr(s, "name"):
            mesh.name = s.name
        acts.append(mesh)
    assem = Assembly(acts)
    assem.transform = procrustes.GetLandmarkTransform()
    assem.info["mean"] = vedo.utils.vtk2numpy(procrustes.GetMeanPoints().GetData())
    return assem


#################################################
class Group(vtk.vtkPropAssembly):

    def __init__(self, objects=()):

        vtk.vtkPropAssembly.__init__(self)

        self.name = ""
        self.created = ""
        self.trail = None
        self.trail_points = []
        self.trail_segment_size = 0
        self.trail_offset = None
        self.shadows = []
        self.info = {}
        self.rendered_at = set()
        self.transform = None
        self.scalarbar = None

        for a in objects:
            if a:
                self.AddPart(a)
            
        self.PickableOff()

    def __iadd__(self, obj):
        """
        Add an object to the group
        """
        if not vedo.utils.is_sequence(obj):
            obj = [obj]
        for a in obj:
            if a:
                self.AddPart(a)
        return self

    def unpack(self):
        elements = []
        self.InitPathTraversal()
        parts = self.GetParts()
        parts.InitTraversal()
        for i in range(parts.GetNumberOfItems()):
            ele = parts.GetItemAsObject(i)
            elements.append(ele)
                
        # gr.InitPathTraversal()
        # for _ in range(gr.GetNumberOfPaths()):
        #     path  = gr.GetNextPath()
        #     print([path])
        #     path.InitTraversal()
        #     for i in range(path.GetNumberOfItems()):
        #         a = path.GetItemAsObject(i).GetViewProp()
        #         print([a])

        return elements

    def clear(self):
        for a in self.unpack():
            self.RemovePart(a)
        return self

    def on(self):
        self.VisibilityOn()
        return self

    def off(self):
        self.VisibilityOff()
        return self

    def pickable(self, value=None):
        """Set/get the pickability property of an object."""
        if value is None:
            return self.GetPickable()
        self.SetPickable(value)
        return self

    def draggable(self, value=None):
        """Set/get the draggability property of an object."""
        if value is None:
            return self.GetDragable()
        self.SetDragable(value)
        return self


    def pos(self, x=None, y=None):
        """Set/Get object position."""
        if x is None:  # get functionality
            return np.array(self.GetPosition())

        if y is None:  # assume x is of the form (x,y)
            x, y = x
        self.SetPosition(x, y)
        return self

    def shift(self, ds):
        """Add a shift to the current object position."""
        p = np.array(self.GetPosition())

        self.SetPosition(p + ds)
        return self

    def bounds(self):
        """
        Get the object bounds.
        Returns a list in format [xmin,xmax, ymin,ymax].
        """
        return self.GetBounds()

    def diagonal_size(self):
        """Get the length of the diagonal"""
        b = self.GetBounds()
        return np.sqrt((b[1] - b[0]) ** 2 + (b[3] - b[2]) ** 2)


    def show(self, **options):
        """
        Create on the fly an instance of class ``Plotter`` or use the last existing one to
        show one single object.

        This method is meant as a shortcut. If more than one object needs to be visualised
        please use the syntax `show(mesh1, mesh2, volume, ..., options)`.

        Returns the ``Plotter`` class instance.
        """
        return vedo.plotter.show(self, **options)


#################################################
class Assembly(vtk.vtkAssembly, vedo.base.Base3DProp):
    """
    Group many objects and treat them as a single new object.

    .. hint:: examples/simulations/gyroscope1.py
        .. image:: https://vedo.embl.es/images/simulations/39766016-85c1c1d6-52e3-11e8-8575-d167b7ce5217.gif
    """

    def __init__(self, *meshs):

        vtk.vtkAssembly.__init__(self)
        vedo.base.Base3DProp.__init__(self)

        if len(meshs) == 1:
            meshs = meshs[0]
        else:
            meshs = vedo.utils.flatten(meshs)

        self.actors = meshs

        if meshs and hasattr(meshs[0], "top"):
            self.base = meshs[0].base
            self.top = meshs[0].top
        else:
            self.base = None
            self.top = None

        for a in meshs:
            if isinstance(a, vtk.vtkProp3D):  # and a.GetNumberOfPoints():
                self.AddPart(a)

    def __add__(self, obj):
        """
        Add an object to the assembly
        """
        self.AddPart(obj)
        self.actors.append(obj)
        return self

    def __contains__(self, obj):
        """Allows to use ``in`` to check if an object is in the Assembly."""
        return obj in self.actors

    def clone(self):
        """Make a clone copy of the object."""
        newlist = []
        for a in self.actors:
            newlist.append(a.clone())
        return Assembly(newlist)

    def unpack(self, i=None):
        """Unpack the list of objects from a ``Assembly``.

        If `i` is given, get `i-th` object from a ``Assembly``.
        Input can be a string, in this case returns the first object
        whose name contains the given string.

        .. hint:: examples/pyplot/custom_axes4.py
        """
        if i is None:
            return self.actors
        elif isinstance(i, int):
            return self.actors[i]
        elif isinstance(i, str):
            for m in self.actors:
                if i in m.name:
                    return m

