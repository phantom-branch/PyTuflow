from pathlib import Path

import pandas as pd
import pytest

from pytuflow._tmf.db.mat import MatDatabaseTMF
from pytuflow._tmf.utils.text_to_db_parser import text_to_db_parser


def test_final_boss_material_values():
    path = Path(__file__).parent / 'test_datasets' / 'the_final_boss.tmf'
    db = MatDatabaseTMF(path)
    assert db.df.shape == (22, 7)
    assert db.df.index.name == 'Material ID'
    assert db.df.index.tolist() == list(range(1, 23))
    assert db.df.columns.tolist() == ["Manning's n", 'IL', 'CL', 'y1', 'n1', 'y2', 'n2']
    assert db.value(6) == 0.03
    assert db.df.loc[1:21, 'IL':].isna().all().all()
    pd.testing.assert_frame_equal(
        db.value(22),
        pd.DataFrame({'Depth': [0.65, 0.7], "Manning's n": [0.08, 0.05]}),
    )


@pytest.mark.parametrize('rows', [
    '1,0.03\n2,0.04,1,2\n3,0.05\n',
    '2,0.04,1,2\n1,0.03\n3,0.05\n',
])
def test_free_form_parser_pads_only_missing_trailing_fields(tmp_path, rows):
    path = tmp_path / 'materials.tmf'
    path.write_text('! Comment, with, commas\n' + rows + '! End\n')
    result = text_to_db_parser(path)
    ids = [int(line.split(',')[0]) for line in rows.splitlines()]
    expected = pd.DataFrame(
        [[0.04, 1., 2.] if key == 2 else [0.03 if key == 1 else 0.05, float('nan'), float('nan')]
         for key in ids],
        index=pd.Index(ids, name=0), columns=[1, 2, 3],
    )
    pd.testing.assert_frame_equal(result, expected)
