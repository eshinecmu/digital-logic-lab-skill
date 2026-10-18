"""Run with Python; uses only temporary files and the standard library."""
import copy
import tempfile
from pathlib import Path
import zipfile
from package_submission import build

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'design.v'
    source.write_bytes(b'module sample; endmodule\n')
    manifest = {'archives': [{'name': 'student-6.1_1.zip', 'layout': 'flat',
                              'files': [{'source': str(source), 'member': 'design.v'}]}]}
    out = root/'out'
    build(manifest, out, check=True)
    assert not out.exists()
    build(manifest, out)
    with zipfile.ZipFile(out/'student-6.1_1.zip') as z:
        assert z.namelist() == ['design.v']
        assert z.read('design.v') == source.read_bytes()
    try:
        build(manifest, out)
        raise AssertionError('Overwrite was allowed')
    except FileExistsError:
        pass
    for member in ('../escape.v', '/absolute.v', 'folder/design.v', 'C:/escape.v'):
        bad = copy.deepcopy(manifest)
        bad['archives'][0]['files'][0]['member'] = member
        try:
            build(bad, root/'invalid', check=True)
            raise AssertionError('Invalid path was accepted')
        except ValueError:
            pass
    tree = copy.deepcopy(manifest)
    tree['archives'][0]['layout'] = 'tree'
    tree['archives'][0]['files'][0]['member'] = 'src/design.v'
    build(tree, root/'tree')
    bad = copy.deepcopy(manifest)
    bad['archives'][0]['files'].append({'source': str(source), 'member': 'DESIGN.V'})
    try:
        build(bad, root/'duplicate', check=True)
        raise AssertionError('Case-insensitive duplicate was accepted')
    except ValueError:
        pass
print('PASS: flat/tree packaging, content preservation, dry run, overwrite and path guards')
