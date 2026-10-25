"""Identical real-provider public surface cases for pre-W9 and W9 sources."""
import json
from pathlib import Path
import numpy as np
import pytest
from qgis.core import QgsApplication, QgsMeshLayer, QgsProviderRegistry
from pytuflow import NCMesh
from pytuflow._outputs.pymesh.mesh_geom.qgismesh_geom import QgisMeshGeometry
from tests.test_numerical_fv_reader import _write_fv

@pytest.fixture(scope='module')
def qapp():
    app=QgsApplication.instance() or QgsApplication([],False)
    app.initQgis()
    assert 'mdal' in QgsProviderRegistry.instance().providerList()
    yield app

@pytest.fixture
def mesh(qapp,tmp_path):
    path=tmp_path/'generated.nc'
    _write_fv(path)
    layer=QgsMeshLayer(str(path),'generated','mdal')
    assert layer.isValid() and layer.dataProvider().faceCount()==4
    return path

def test_native_centroid(mesh):
    geom=QgisMeshGeometry(mesh)
    actual=geom.cell_position(slice(None))
    np.testing.assert_allclose(actual[:,:2],[[.5,.5],[2.5,.5],[4.5,.5],[6.5,.5]],rtol=0,atol=1e-12)

@pytest.mark.parametrize('driver',['qgis geometry data extractor','qgis geometry netcdf4','qgis geometry h5py'])
@pytest.mark.parametrize('data_type,columns,first,average',[
    ('salinity',['value'],[15.],'sigma&0&1'),
    ('tracer',['value'],[10.],'sigma&0&1'),
    ('velocity',['value-x','value-y'],[3.,4.],'sigma&0&1'),
    ('water surface elevation',['value'],[0.],None),
])
def test_public_surface(mesh,driver,data_type,columns,first,average,record_property):
    result=NCMesh(mesh,driver=driver)
    kwargs={'averaging_method':average} if average else {}
    frame=result.surface(data_type,0.,to_vertex=False,**kwargs)
    assert frame.shape==(4,3+len(columns))
    np.testing.assert_allclose(frame[['x','y']],[[.5,.5],[2.5,.5],[4.5,.5],[6.5,.5]],rtol=0,atol=1e-12)
    np.testing.assert_array_equal(frame['active'],[True,True,True,False])
    np.testing.assert_allclose(frame.loc[0,columns],first,rtol=0,atol=1e-12)
    if average:
        assert frame.loc[1,columns].isna().all()
        np.testing.assert_allclose(frame.loc[2:3,columns],0.,rtol=0,atol=1e-12)
    else:
        np.testing.assert_allclose(frame['value'],0.,rtol=0,atol=1e-12)
    record_property('surface',frame.to_json(orient='split'))
