import pytest
from lab.materials import merge_sources


def test_complete_numeric_reference_and_method_are_preserved_without_a_small_context_cutoff():
    material={'id':'a'*32,'sha256':'b'*64,'name':'complete-method.md',
              'units':[{'location':'L1','text':'complete source '*4000+'END-OF-METHOD'}]}
    selected=merge_sources([], [material])
    assert selected[0]['units'][0]['text']==material['units'][0]['text']
    material['units'][0]['text']='x'*(128*1024)
    with pytest.raises(ValueError):merge_sources([], [material])
