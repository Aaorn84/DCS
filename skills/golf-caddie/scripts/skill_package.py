#!/usr/bin/env python3
"""Build/verify a deterministic versioned skill ZIP using only the stdlib."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile


class PackageError(ValueError):
    pass


DIRECTORIES = {'agents', 'references', 'scripts', 'tests', 'assets'}
SUFFIXES = {'.md', '.py', '.yaml', '.yml', '.json', '.png', '.jpg', '.jpeg', '.svg'}
MAX_FILES, MAX_TOTAL_BYTES = 500, 50_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def metadata(text):
    match = re.match(r'\A---\n(.*?)\n---(?:\n|$)', text, re.S)
    if not match:
        raise PackageError('SKILL.md requires YAML frontmatter')
    front = match.group(1)
    # These are the generated skill's deliberately narrow metadata conventions;
    # unsupported YAML layouts fail rather than guessing a version or using eval.
    name = re.search(r'^name:\s*["\']?([a-z0-9]+(?:-[a-z0-9]+)*)["\']?\s*$', front, re.M)
    version = re.search(r'^metadata:\s*\n(?:(?:[ ]{2}[^\n]*\n)*?)[ ]{2}version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$', front, re.M)
    if not name or not version:
        raise PackageError('skill name and metadata.version (x.y.z) required')
    return name.group(1), version.group(1)


def payload(source):
    source = Path(source)
    entry = source/'SKILL.md'
    if not entry.is_file() or entry.is_symlink():
        raise PackageError('regular SKILL.md required')
    files = {}
    for path in sorted(source.rglob('*')):
        rel = path.relative_to(source)
        if any(part.startswith('.') or part == '__pycache__' for part in rel.parts):
            continue
        if rel.as_posix() != 'SKILL.md' and rel.parts[0] not in DIRECTORIES:
            continue
        if path.is_symlink():
            raise PackageError(f'symlinks not allowed: {rel}')
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        files[rel.as_posix()] = path.read_bytes()
    if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise PackageError('skill exceeds package limits')
    return files


def verify_archive(archive, expected_sha256=None):
    archive = Path(archive)
    try:
        raw = archive.read_bytes()
        if expected_sha256 is not None and digest(raw) != expected_sha256:
            raise PackageError('archive SHA-256 mismatch')
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if not infos or len(infos) > MAX_FILES+1 or sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
                raise PackageError('archive size/member limit exceeded')
            names = [i.filename for i in infos]
            if len(names) != len(set(names)):
                raise PackageError('duplicate archive member')
            roots = set()
            for name in names:
                path = PurePosixPath(name)
                if '\\' in name or path.is_absolute() or '..' in path.parts or len(path.parts) < 2:
                    raise PackageError('unsafe archive path')
                if any(part.startswith('.') or part == '__pycache__' for part in path.parts):
                    raise PackageError('hidden/cached archive member')
                roots.add(path.parts[0])
            if len(roots) != 1:
                raise PackageError('exactly one versioned root required')
            root = roots.pop()
            manifest = json.loads(z.read(root+'/manifest.json'))
            if manifest.get('format') != 'codex-skill-bundle-v1':
                raise PackageError('unsupported manifest format')
            if root != f"{manifest['skill_name']}-v{manifest['skill_version']}":
                raise PackageError('root and manifest version mismatch')
            declared = manifest['files']
            if not isinstance(declared, list):
                raise PackageError('manifest files list required')
            listed = [f['path'] for f in declared]
            if len(listed) != len(set(listed)) or 'manifest.json' in listed:
                raise PackageError('duplicate/recursive manifest entries')
            expected = {root+'/'+path for path in listed} | {root+'/manifest.json'}
            if set(names) != expected:
                raise PackageError('undeclared or missing archive files')
            for row in declared:
                content = z.read(root+'/'+row['path'])
                if len(content) != row['bytes'] or digest(content) != row['sha256']:
                    raise PackageError(f"payload checksum mismatch: {row['path']}")
            actual_name, actual_version = metadata(z.read(root+'/SKILL.md').decode('utf-8'))
            if (actual_name,actual_version) != (manifest['skill_name'],manifest['skill_version']):
                raise PackageError('SKILL metadata and manifest disagree')
        return {'valid': True, 'sha256': digest(raw), 'root': root, 'file_count': len(declared)}
    except (OSError, zipfile.BadZipFile, KeyError, ValueError, TypeError, UnicodeError) as exc:
        if isinstance(exc, PackageError):
            raise
        raise PackageError(f'invalid skill archive: {exc}') from exc


def build_package(source, output):
    files = payload(source)
    name, version = metadata(files['SKILL.md'].decode('utf-8'))
    folder = f'{name}-v{version}'
    manifest = {'format': 'codex-skill-bundle-v1', 'skill_name': name, 'skill_version': version,
                'files': [{'path':path,'bytes':len(data),'sha256':digest(data)}
                          for path,data in sorted(files.items())]}
    files['manifest.json'] = (json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.skill-build-',dir=output) as tmp:
        tmp = Path(tmp)
        root = tmp/folder
        for path, data in files.items():
            target = root/path
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
        temporary_archive = tmp/(folder+'.zip')
        with zipfile.ZipFile(temporary_archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for path,data in sorted(files.items()):
                info=zipfile.ZipInfo(folder+'/'+path,date_time=(1980,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=0o100644 << 16
                z.writestr(info,data,compresslevel=9)
        verified = verify_archive(temporary_archive)
        destination, archive = output/folder, output/(folder+'.zip')
        checksum_path = output/(folder+'.zip.sha256')
        checksum_data = f"{verified['sha256']}  {archive.name}\n"
        if destination.exists():
            existing = {p.relative_to(destination).as_posix():p.read_bytes()
                        for p in destination.rglob('*') if p.is_file() and not p.is_symlink()}
            if existing != files or any(p.is_symlink() for p in destination.rglob('*')):
                raise PackageError('different existing release directory; increment version')
        if archive.exists() and archive.read_bytes() != temporary_archive.read_bytes():
            raise PackageError('different existing release archive; increment version')
        if checksum_path.exists() and checksum_path.read_text() != checksum_data:
            raise PackageError('different existing release checksum; increment version')
        if not destination.exists():
            shutil.move(str(root),str(destination))
        if not archive.exists():
            shutil.move(str(temporary_archive),str(archive))
        if not checksum_path.exists():
            checksum_path.write_text(checksum_data)
    return {'archive':str(archive),'directory':str(destination),'checksum_file':str(checksum_path),
            'sha256':verified['sha256'],'version':version,'file_count':len(files)-1}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    build=sub.add_parser('build');build.add_argument('--source',required=True);build.add_argument('--output',required=True)
    verify=sub.add_parser('verify');verify.add_argument('archive');verify.add_argument('--sha256')
    args=parser.parse_args()
    try:
        result=(build_package(args.source,args.output) if args.action=='build'
                else verify_archive(args.archive,args.sha256))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (PackageError,OSError) as exc:
        print(json.dumps({'status':'error','error':str(exc)},ensure_ascii=False));return 2


if __name__=='__main__':
    raise SystemExit(main())
