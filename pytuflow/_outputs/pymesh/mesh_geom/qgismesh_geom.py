import operator
import typing
from collections import OrderedDict
from pathlib import Path

import numpy as np
try:
    import pandas as pd
except ImportError:
    from ..stubs import pandas as pd

try:
    from qgis.core import (QgsApplication, QgsMesh, QgsMeshLayer, QgsMeshSpatialIndex, QgsPoint,
                           QgsPointXY, QgsGeometry, QgsMeshDatasetIndex, QgsProject, QgsDistanceArea)
except ImportError:
    from ..stubs.qgis.core import (QgsApplication, QgsMesh, QgsMeshLayer, QgsMeshSpatialIndex, QgsPoint,
                                   QgsPointXY, QgsGeometry, QgsMeshDatasetIndex, QgsProject, QgsDistanceArea)

from . import PyMeshGeometry
from .. import ellipsoid_distance, Transform2D, PointMixin, PointLike



def _face_centroid(vertices: np.ndarray) -> np.ndarray:
    """Area-weighted native-mesh face centroid with optional native vertex Z."""
    coords = np.asarray(vertices, dtype=np.float64)
    if coords.ndim != 2 or coords.shape[0] < 3 or coords.shape[1] != 3:
        raise ValueError("A mesh face needs at least three XYZ vertices")
    if not np.isfinite(coords[:, :2]).all():
        raise ValueError("Mesh face has non-finite XY coordinates")

    # Shift first to avoid cancellation for large projected CRS coordinates.
    xy = coords[:, :2] - coords[0, :2]
    shifted = np.roll(xy, -1, axis=0)
    cross = xy[:, 0] * shifted[:, 1] - shifted[:, 0] * xy[:, 1]
    twice_area = float(np.sum(cross))
    extent = float(np.max(np.abs(xy)))
    if not np.isfinite(twice_area) or abs(twice_area) <= np.finfo(float).eps * extent**2:
        raise ValueError("Mesh face has zero or invalid signed area")
    centroid_xy = coords[0, :2] + np.sum((xy + shifted) * cross[:, None], axis=0) / (3. * twice_area)

    z = np.nan
    if np.isfinite(coords[:, 2]).all():
        # Integrate piecewise-linear native Z over a signed triangle fan.
        triangles = xy[1:-1, 0] * xy[2:, 1] - xy[2:, 0] * xy[1:-1, 1]
        z_means = (coords[0, 2] + coords[1:-1, 2] + coords[2:, 2]) / 3.
        z = float(np.dot(triangles, z_means) / twice_area)
    return np.array([centroid_xy[0], centroid_xy[1], z], dtype=np.float64)



def _angle_weights(vertices: np.ndarray, cell_nodes: np.ndarray, is_triangle: np.ndarray) -> np.ndarray:
    """Normalised native-cell corner-angle weights (the PyNCMesh convention).

    Triangle slot four repeats corner three for safe indexing but has zero weight.
    Geometry is independent of wet/dry state and of the requested result type.
    """
    coords = np.asarray(vertices, dtype=np.float64)
    nodes = np.asarray(cell_nodes, dtype=np.int64)
    triangles = np.asarray(is_triangle, dtype=bool)
    if nodes.ndim != 2 or nodes.shape[1] != 4 or triangles.shape != (nodes.shape[0],):
        raise ValueError("Expected an N x 4 cell-node array and one triangle flag per cell")
    if nodes.size == 0:
        return np.empty((0, 4), dtype=np.float64)
    if (nodes < 0).any() or (nodes >= coords.shape[0]).any():
        raise ValueError("Mesh face refers to a nonexistent vertex")
    xy = coords[nodes[:, [3, 0, 1, 2, 3, 0]], :2].copy()
    xy[triangles, 4:6] = xy[triangles, 1:3]
    edges = np.diff(xy, axis=1)
    lengths = np.linalg.norm(edges, axis=-1)
    left = edges[:, :-1]
    right = edges[:, 1:]
    denominator = lengths[:, :-1] * lengths[:, 1:]
    cosine = np.divide(-np.sum(left * right, axis=-1), denominator,
                       out=np.ones_like(denominator), where=denominator > 0)
    angles = np.arccos(np.clip(cosine, -1., 1.))
    angles[denominator <= 0] = 0.
    angles[triangles, 3] = 0.
    total = np.bincount(nodes.ravel(), weights=angles.ravel(), minlength=coords.shape[0])
    return np.divide(angles, total[nodes], out=np.zeros_like(angles),
                     where=total[nodes] > 0)


class PointMixinQgis(PointMixin):

    @staticmethod
    def _coerce_into_point(value: PointLike) -> np.ndarray:
        if isinstance(value, (QgsPoint, QgsPointXY)):
            return np.array([value.x(), value.y()])
        return PointMixin._coerce_into_point(value)

    @staticmethod
    def _coerce_into_qgs_point(value: PointLike) -> QgsPointXY:
        p = PointMixinQgis._coerce_into_point(value)
        return QgsPointXY(*p.tolist()[:2])



class QgisMeshGeometry(PyMeshGeometry, PointMixinQgis):

    def __init__(self, fpath: Path | str):
        super().__init__(fpath)
        self.has_z = True
        self.trans = Transform2D()
        self.lyr = None
        self._mesh = QgsMesh()
        self._si = None
        self._loaded = False

        self._cell2triangle = {}
        self._triangle2cell = {}
        self._triangles = {}
        self._tri_count = 0
        self._ibed = -1
        self._vertex_positions_cache = None
        self._cell_positions_cache: dict[int, np.ndarray] = {}
        self._corner_weights: np.ndarray | None = None
        self.dtype = np.float64

    @property
    def cells_df(self) -> pd.DataFrame:
        if self._cells_df.empty:
            self.init_spatial_index()
            cell_ids = np.arange(self.lyr.dataProvider().faceCount())
            d = OrderedDict()
            d['nnode'] = []
            d['n1'] = []
            d['n2'] = []
            d['n3'] = []
            d['n4'] = []
            for cid in cell_ids:
                verts = self._mesh.face(cid)
                d['nnode'].append(len(verts))
                for i in range(4):
                    if i < len(verts):
                        d[f'n{i+1}'].append(verts[i])
                    else:
                        d[f'n{i+1}'].append(-1)
            self._cells_df = pd.DataFrame(d, index=cell_ids)
        return self._cells_df

    @cells_df.setter
    def cells_df(self, value: pd.DataFrame):
        self._cells_df = value

    def init_spatial_index(self):
        if self._si is None:
            dp = self.lyr.dataProvider()
            dp.populateMesh(self._mesh)
            self._si = QgsMeshSpatialIndex(self._mesh)

    def load(self):
        if not QgsApplication.instance():
            raise RuntimeError('QGIS application instance not found.')
        if not self._loaded:
            if self.lyr is None:
                self.lyr = QgsMeshLayer(str(self.fpath), self.fpath.stem, 'mdal')
            if self._ibed == -1:
                for i in range(self.lyr.dataProvider().datasetGroupCount()):
                    if self.lyr.dataProvider().datasetGroupMetadata(i).name().lower() == 'bed elevation':
                        self._ibed = i
                        break
            self._loaded = True

    def cell_vertices(self, cell_id: int) -> list[int]:
        self.init_spatial_index()
        return list(self._mesh.face(cell_id))

    def cell_to_vertex_weights(self) -> np.ndarray:
        """Use the original non-QGIS angle scheme with native MDAL face IDs."""
        if not self._loaded:
            self.load()
        self.init_spatial_index()
        if self._corner_weights is None:
            face_df = self.cells_df
            node_ids = face_df[['n1', 'n2', 'n3', 'n4']].to_numpy(dtype=np.int64, copy=True)
            is_triangle = face_df['nnode'].to_numpy() == 3
            if np.any(~np.isin(face_df['nnode'].to_numpy(), [3, 4])):
                raise ValueError("Cell-to-vertex mapping supports triangle and quad faces")
            node_ids[is_triangle, 3] = node_ids[is_triangle, 2]
            # Unlike PyNCMeshGeometry, QGIS does not populate the base arrays.
            # Only allocate these when vertex interpolation is requested.
            coords = np.empty((self._mesh.vertexCount(), 3), dtype=np.float64)
            for i in range(coords.shape[0]):
                point = self._mesh.vertex(i)
                coords[i, 0:2] = point.x(), point.y()
                coords[i, 2] = point.z() if point.is3D() else np.nan
            weights = _angle_weights(coords, node_ids, is_triangle)
            self.cell_nodes = node_ids
            self.vertices = coords
            self._corner_weights = weights
        return self._corner_weights

    def cell_position(self, cell_id: int | typing.Iterable[int] | slice, scope: str = 'global') -> np.ndarray:
        """Return original-face centroids as N × 3 coordinates in face ID order.

        XY are planimetric polygon-area centroids in the native mesh CRS. Z is
        integrated from native mesh vertex elevations where *all* exist; it is
        NaN where native vertex Z is unavailable (not a fabricated bed level).
        QGIS geometry uses the native mesh CRS as global and the configured
        `self.trans` transform for local coordinates (identity by default).
        """
        if scope not in ('global', 'local'):
            raise ValueError("scope must be 'global' or 'local'")
        if not self._loaded:
            self.load()
        self.init_spatial_index()
        face_count = self._mesh.faceCount()

        if isinstance(cell_id, slice):
            face_ids = list(range(face_count)[cell_id])
        else:
            if isinstance(cell_id, (bool, np.bool_)):
                raise TypeError('Boolean cell indices are not supported')
            try:
                face_ids = [operator.index(cell_id)]
            except TypeError:
                try:
                    face_ids = list(cell_id)
                except TypeError as exc:
                    raise TypeError('cell_id must be an integer, iterable of integers, or slice') from exc
        validated = []
        for face_id in face_ids:
            if isinstance(face_id, (bool, np.bool_)):
                raise TypeError('Boolean cell indices are not supported')
            try:
                index = operator.index(face_id)
            except TypeError as exc:
                raise TypeError('Cell indices must be integers') from exc
            if index < 0 or index >= face_count:
                raise IndexError(f'Cell index {index} outside [0, {face_count})')
            validated.append(index)

        result = np.empty((len(validated), 3), dtype=np.float64)
        for i, index in enumerate(validated):
            if index not in self._cell_positions_cache:
                face = self._mesh.face(index)
                vertices = []
                for vertex_id in face:
                    vertex = self._mesh.vertex(vertex_id)
                    # QgsMeshVertex is a QgsPoint; 2-D meshes have no native Z.
                    has_z = vertex.is3D() if hasattr(vertex, 'is3D') else False
                    z = float(vertex.z()) if has_z else np.nan
                    vertices.append((vertex.x(), vertex.y(), z))
                self._cell_positions_cache[index] = _face_centroid(np.asarray(vertices))
            result[i, :] = self._cell_positions_cache[index]

        if scope == 'local' and len(result):
            return self.trans.transform(result)
        return result

    def vertex_position(self, vertex_id: int | typing.Iterable[int] | slice, get_z: bool = True, *args, **kwargs) -> np.ndarray:
        scope = kwargs.pop('scope', 'global')
        if isinstance(get_z, str):
            scope, get_z = get_z, True  # inherited positional scope convention
        if scope not in ('global', 'local'):
            raise ValueError("scope must be 'global' or 'local'")
        if not self._loaded:
            self.load()

        self.init_spatial_index()

        cache_result = False
        if isinstance(vertex_id, slice) and vertex_id == slice(None) and get_z:
            cache_result = True

        if isinstance(vertex_id, (list, tuple)):
            vertex_id = np.array(vertex_id).flatten().tolist()
        if isinstance(vertex_id, int):
            vertex_id = [vertex_id]
        if isinstance(vertex_id, np.ndarray):
            vertex_id = vertex_id.flatten().tolist()
        if isinstance(vertex_id, slice):
            vertex_id = list(range(self.lyr.dataProvider().vertexCount()))[vertex_id]

        if self._vertex_positions_cache is not None and get_z:
            cached = self._vertex_positions_cache[vertex_id]
            return self.trans.transform(cached) if scope == 'local' else cached

        a = np.full((len(vertex_id), 3), 0., dtype=np.float64)
        for i, vid in enumerate(vertex_id):
            v = self._mesh.vertex(vid)
            a[i, 0] = v.x()
            a[i, 1] = v.y()
        if get_z:
            if self._ibed == -1:
                # MDAL meshes need not have a separate Bed Elevation dataset.
                # Do not invent zero heights when the native vertices are 2-D.
                a[:, 2] = [
                    self._mesh.vertex(vid).z() if self._mesh.vertex(vid).is3D() else np.nan
                    for vid in vertex_id
                ]
            else:
                from .. import QgisDataExtractor
                a_vert_index, inverse = np.unique(vertex_id, return_inverse=True)
                values = []
                for vertid, count, idx in QgisDataExtractor.chunk_indexes(a_vert_index):
                    extracted = np.array(
                        self.lyr.dataProvider().datasetValues(QgsMeshDatasetIndex(self._ibed, 0), vertid, count).values()
                    )
                    values.append(extracted[idx])
                a[:, 2] = np.hstack(values)[inverse] if values else np.empty(0)
        if cache_result:
            self._vertex_positions_cache = a
        return self.trans.transform(a) if scope == 'local' and len(a) else a

    def triangle_vertices(self, triangle_id: int) -> np.ndarray:
        if triangle_id in self._triangles:
            return self._triangles[triangle_id]
        raise RuntimeError(f'Triangle index not found in cache: {triangle_id}')

    def triangle_cell(self, triangle_id: int) -> int:
        if triangle_id in self._triangle2cell:
            return self._triangle2cell[triangle_id]
        raise RuntimeError(f'Triangle index not found in cache: {triangle_id}')

    def find_containing_cell(self, point: PointLike, *args, **kwargs) -> int:
        self.init_spatial_index()
        p = self._coerce_into_qgs_point(point)
        p_ = self._coerce_into_point(point)  # numpy array
        cell_ids = self._si.nearestNeighbor(p, 2)
        for cell_id in cell_ids:
            vert_ids = np.array(self.cell_vertices(cell_id))
            if len(vert_ids) == 3:
                if self.point_in_triangle(p_, *self.vertex_position(vert_ids, get_z=False).tolist()):
                    if cell_id not in self._cell2triangle:
                        self._cell2triangle[cell_id] = [self._tri_count]
                        self._tri_count += 1
                    return cell_id
            elif len(vert_ids) == 4:
                if cell_id not in self._cell2triangle:
                    self._cell2triangle[cell_id] = [self._tri_count, self._tri_count + 1]
                    self._tri_count += 2
                for tri_idx in [[0, 1, 2], [2, 3, 0]]:
                    if self.point_in_triangle(p_, *self.vertex_position(vert_ids[tri_idx], get_z=False).tolist()):
                        return cell_id
        return -1

    def find_containing_triangle(self, point: PointLike, *args, **kwargs) -> int:
        self.init_spatial_index()
        p = self._coerce_into_qgs_point(point)
        p_ = self._coerce_into_point(point)  # numpy array
        cell_ids = self._si.nearestNeighbor(p, 2)
        for cell_id in cell_ids:
            vert_ids = np.array(self._mesh.face(cell_id))
            if len(vert_ids) == 3:
                if self.point_in_triangle(p_, *self.vertex_position(vert_ids, get_z=False).tolist()):
                    if cell_id in self._cell2triangle:
                        tri_id = self._cell2triangle[cell_id][0]
                    else:
                        tri_id = self._tri_count
                        self._cell2triangle[cell_id] = [tri_id]
                        self._tri_count += 1
                    if tri_id not in self._triangle2cell:
                        self._triangle2cell[tri_id] = cell_id
                    self._triangles[tri_id] = vert_ids.tolist()
                    return tri_id
            elif len(vert_ids) == 4:
                if cell_id in self._cell2triangle:
                    tri_ids = self._cell2triangle[cell_id]
                else:
                    tri_ids = [self._tri_count, self._tri_count + 1]
                    self._cell2triangle[cell_id] = tri_ids
                    self._tri_count += 2
                for tri_id, tri_idx in zip(tri_ids, [[0, 1, 2], [2, 3, 0]]):
                    if tri_id not in self._triangles:
                        self._triangles[tri_id] = vert_ids[tri_idx].tolist()
                    if tri_id not in self._triangle2cell:
                        self._triangle2cell[tri_id] = cell_id
                    if self.point_in_triangle(p_, *self.vertex_position(vert_ids[tri_idx], get_z=False).tolist()):
                        return tri_id
        return -1

    def cell_edge_intersections(self, cell_id: int, p0: np.ndarray, p1: np.ndarray, scope: str = 'global') -> np.ndarray:
        def cross2d(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            """2D cross product. Numpy 2.0 deprecates np.cross for 2D arrays."""
            return x[..., 0] * y[..., 1] - x[..., 1] * y[..., 0]

        def intersection(p1: np.ndarray, p2: np.ndarray, q1: np.ndarray, q2: np.ndarray) -> np.ndarray | None:
            """Finds the intersection between 2 lines (p1, p2) and (q1, q2)."""
            r = p2 - p1
            s = q2 - q1
            denom = cross2d(r, s)
            if abs(denom) < 1e-12:
                return None  # parallel
            t = cross2d((q1 - p1), s) / denom
            u = cross2d((q1 - p1), r) / denom
            if 0 <= t <= 1 and 0 <= u <= 1:
                return p1 + t * r
            return None

        edges = self.cell_edges(cell_id)
        pts = self.vertex_position(edges, get_z=False).reshape((-1, 3))
        intersections = []
        for i in range(0, pts.shape[0], 2):
            p0_ = pts[i, :2]
            p1_ = pts[i+1, :2]
            pt = intersection(p0[:2], p1[:2], p0_, p1_)
            if pt is not None:
                intersections.append(pt)
        return np.array(intersections)

    @staticmethod
    def point_in_triangle(pt, v1, v2, v3):
        def sign(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - \
                (p2[0] - p3[0]) * (p1[1] - p3[1])
        b1 = sign(pt, v1, v2) < 0.0
        b2 = sign(pt, v2, v3) < 0.0
        b3 = sign(pt, v3, v1) < 0.0
        return (b1 == b2) and (b2 == b3)

    def distance(self, p2: np.ndarray, p1: np.ndarray) -> np.ndarray:
        if not self.spherical:
            return super().distance(p2, p1)
        n1 = 1 if p1.ndim == 1 else p1.shape[0]
        n2 = 1 if p2.ndim == 1 else p2.shape[0]
        if n1 != n2:
            p1 = np.repeat(p1.reshape(1, -1), n2, axis=0)
        return ellipsoid_distance(p2.reshape(n2, -1), p1.reshape(n1, -1))

    def _line_direction(self, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
        if not self.spherical:
            return super()._line_direction(p1, p2)
        from pyproj import Geod
        az, _, _ = Geod(ellps='WGS84').inv(float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1]))
        az_rad = np.radians(az)
        return np.array([np.sin(az_rad), np.cos(az_rad)], dtype=self.dtype)

    def _mesh_intersects(self, p1: np.ndarray, p2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returns points and cell_ids where the line segment intersects the mesh. Last point is not returned."""
        self.init_spatial_index()
        tol = 1e-6
        interval = 1
        geom = QgsGeometry.fromPolylineXY([QgsPointXY(*p1.tolist()[:2]), QgsPointXY(*p2.tolist()[:2])])
        dense = geom.densifyByDistance(interval)
        first_cell = self.find_containing_cell(p1)
        ret_points, ret_cell_ids = [], []
        if first_cell != -1:
            ret_points = [p1[:2]]
            ret_cell_ids = [first_cell]
        last_cell_id = first_cell
        for i, p_start in enumerate(dense.vertices()):
            try:
                p_end = dense.vertexAt(i + 1)
                if p_end.isEmpty():
                    break
            except Exception:
                break
            points = {}
            cell_ids = self._si.intersects(QgsGeometry.fromPolylineXY([QgsPointXY(p_start), QgsPointXY(p_end)]).boundingBox())
            for cell_id in cell_ids:
                intersects = self.cell_edge_intersections(cell_id, self._coerce_into_point(p_start), self._coerce_into_point(p_end))
                for p in intersects:
                    vec = np.array([p[0] - p_start.x(), p[1] - p_start.y()])
                    offset = np.linalg.norm(vec)
                    if offset == 0:
                        continue
                    dir_ = vec / offset
                    nudge = p + dir_ * tol
                    cell_id = self.find_containing_cell(nudge)
                    if cell_id != -1 and cell_id not in points and cell_id != last_cell_id:
                        points[cell_id] = (offset, self._coerce_into_point(p)[:2])
            if points:
                sorted_points = sorted(points.items(), key=lambda x: x[1][0])
                for cell_id, (offset, p) in sorted_points:
                    ret_points.append(p)
                    ret_cell_ids.append(cell_id)
                    last_cell_id = cell_id

        return np.array(ret_points).reshape(-1, 2), np.array(ret_cell_ids)
