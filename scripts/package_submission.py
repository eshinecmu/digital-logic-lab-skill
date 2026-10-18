"""Build ZIPs from an explicitly reviewed submission manifest; never overwrite."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile


def prepare(manifest, out):
    archives = manifest.get('archives')
    if not isinstance(archives, list) or not archives:
        raise ValueError('archives must be a non-empty list')
    plans, names = [], set()
    for archive in archives:
        name = archive['name']
        if (not isinstance(name, str) or not name.lower().endswith('.zip')
                or any(c in name for c in '/\\:<>"|?*') or name in ('.', '..')):
            raise ValueError(f'Invalid archive name: {name}')
        if name.casefold() in names:
            raise ValueError(f'Duplicate archive name: {name}')
        names.add(name.casefold())
        target = out / name
        if target.exists():
            raise FileExistsError(target)
        layout = archive.get('layout')
        if layout not in ('flat', 'tree'):
            raise ValueError('layout must be flat or tree')
        members, entries = set(), []
        if not archive.get('files'):
            raise ValueError(f'Empty archive: {name}')
        for item in archive['files']:
            source = Path(item['source'])
            if not source.is_absolute() or not source.is_file():
                raise ValueError(f'Expected absolute file path: {source}')
            member = item['member']
            parts = member.split('/')
            if (not member or '\\' in member or any(c in member for c in ':<>"|?*')
                    or PurePosixPath(member).is_absolute()
                    or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts)
                    or (layout == 'flat' and len(parts) != 1)):
                raise ValueError(f'Unsafe or invalid member path: {member}')
            if member.casefold() in members:
                raise ValueError(f'Duplicate member: {member}')
            members.add(member.casefold())
            data = source.read_bytes()
            if not data:
                raise ValueError(f'Empty file: {source}')
            entries.append((member, data))
        plans.append((target, entries))
    return plans


def build(manifest, out, check=False):
    plans = prepare(manifest, out)
    if check:
        return [(str(p), [n for n, _ in entries]) for p, entries in plans]
    out.mkdir(parents=True, exist_ok=True)
    # ponytail: snapshot small lab submissions in memory to prevent source changes
    # during packing; for multi-GB projects upgrade to streamed, hashed staging.
    for target, entries in plans:
        with tempfile.TemporaryDirectory(prefix='lab-pack-', dir=out) as temp:
            staged = Path(temp) / 'archive.zip'
            with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED) as z:
                for name, data in entries:
                    z.writestr(name, data)
            with zipfile.ZipFile(staged) as z:
                if z.testzip() is not None or z.namelist() != [n for n, _ in entries]:
                    raise ValueError(f'Archive validation failed: {target}')
                for name, data in entries:
                    if hashlib.sha256(z.read(name)).digest() != hashlib.sha256(data).digest():
                        raise ValueError(f'Content mismatch: {name}')
            # Exclusive creation also protects a target created after preflight.
            with target.open('xb') as dest:
                dest.write(staged.read_bytes())
        print(json.dumps({'archive': str(target), 'files': [n for n, _ in entries]}, ensure_ascii=False))
    return [str(p) for p, _ in plans]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = build(json.loads(args.manifest.read_text(encoding='utf-8-sig')), args.out, args.check)
    if args.check:
        print(json.dumps(result, ensure_ascii=False, indent=2))
