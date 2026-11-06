"""Release artifact tests: portable, deterministic, checksummed skill package."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def builder():
    spec=importlib.util.spec_from_file_location('skill_package',ROOT/'scripts/skill_package.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def source(parent):
    root=Path(parent)/'source';root.mkdir()
    (root/'SKILL.md').write_text('---\nname: sample-caddie\ndescription: Test package.\nmetadata:\n  version: "0.1.1"\n---\n\nTest artifact.\n')
    (root/'references').mkdir();(root/'references/info.md').write_text('Test reference.\n')
    (root/'scripts').mkdir();(root/'scripts/example.py').write_text('print("demo")\n')
    return root


class SkillPackageTests(unittest.TestCase):
    def test_stable_root_and_standard_entry(self):
        m=builder()
        with tempfile.TemporaryDirectory() as tmp:
            r=m.build_package(source(tmp),Path(tmp)/'dist')
            self.assertEqual(Path(r['archive']).name,'sample-caddie.zip')
            self.assertTrue((Path(r['directory'])/'SKILL.md').is_file())
            with zipfile.ZipFile(r['archive']) as z:
                self.assertIn('sample-caddie/SKILL.md',z.namelist())
                self.assertNotIn('SKILL-v0.1.1.md',z.namelist())
            self.assertTrue(m.verify_archive(r['archive'],r['sha256'])['valid'])

    def test_hidden_files_caches_and_unrelated_user_files_excluded(self):
        m=builder()
        with tempfile.TemporaryDirectory() as tmp:
            src=source(tmp);(src/'.env').write_text('SECRET=not-for-release')
            (src/'.DS_Store').write_bytes(b'metadata')
            (src/'scripts/__pycache__').mkdir();(src/'scripts/__pycache__/x.pyc').write_bytes(b'cache')
            (src/'private-user-history.json').write_text('{"private":true}')
            r=m.build_package(src,Path(tmp)/'dist')
            with zipfile.ZipFile(r['archive']) as z:
                names=z.namelist()
            self.assertFalse(any('.env' in n or '__pycache__' in n or '.DS_Store' in n or 'private-user' in n for n in names))

    def test_identical_sources_produce_identical_archives(self):
        m=builder()
        with tempfile.TemporaryDirectory() as tmp:
            src=source(tmp)
            a=m.build_package(src,Path(tmp)/'one');b=m.build_package(src,Path(tmp)/'two')
            self.assertEqual(Path(a['archive']).read_bytes(),Path(b['archive']).read_bytes())

    def test_manifest_contains_payload_hash_and_size(self):
        m=builder()
        with tempfile.TemporaryDirectory() as tmp:
            r=m.build_package(source(tmp),Path(tmp)/'dist')
            manifest=json.loads((Path(r['directory'])/'manifest.json').read_text())
            row=next(x for x in manifest['files'] if x['path']=='SKILL.md')
            self.assertEqual(len(row['sha256']),64)
            self.assertEqual(row['bytes'],(Path(r['directory'])/'SKILL.md').stat().st_size)
            self.assertEqual(manifest['skill_version'],'0.1.1')

    def test_symlink_cannot_import_files_outside_skill(self):
        m=builder()
        with tempfile.TemporaryDirectory() as tmp:
            src=source(tmp);private=Path(tmp)/'private.json';private.write_text('{"secret":1}')
            (src/'references/outside.json').symlink_to(private)
            with self.assertRaises(m.PackageError):m.build_package(src,Path(tmp)/'dist')

    def test_tampered_archive_is_rejected(self):
        m=builder()
        with tempfile.TemporaryDirectory() as tmp:
            r=m.build_package(source(tmp),Path(tmp)/'dist');bad=Path(tmp)/'tampered.zip'
            with zipfile.ZipFile(r['archive']) as src,zipfile.ZipFile(bad,'w') as dst:
                for info in src.infolist():
                    dst.writestr(info.filename,b'changed' if info.filename.endswith('/SKILL.md') else src.read(info))
            with self.assertRaises(m.PackageError):m.verify_archive(bad)
            with self.assertRaises(m.PackageError):m.verify_archive(bad,r['sha256'])

    def test_unsafe_or_undeclared_members_rejected_without_extracting(self):
        m=builder()
        with tempfile.TemporaryDirectory() as tmp:
            r=m.build_package(source(tmp),Path(tmp)/'dist')
            for name in ('../outside','sample-caddie/extra.json'):
                bad=Path(tmp)/'invalid.zip'
                with zipfile.ZipFile(r['archive']) as src,zipfile.ZipFile(bad,'w') as dst:
                    for i in src.infolist():dst.writestr(i.filename,src.read(i))
                    dst.writestr(name,b'invalid')
                with self.assertRaises(m.PackageError):m.verify_archive(bad)
            self.assertFalse((Path(tmp)/'outside').exists())

    def test_existing_different_release_not_overwritten(self):
        m=builder()
        with tempfile.TemporaryDirectory() as tmp:
            src=source(tmp);dist=Path(tmp)/'dist';a=m.build_package(src,dist)
            old=Path(a['archive']).read_bytes()
            (src/'references/info.md').write_text('changed content')
            with self.assertRaises(m.PackageError):m.build_package(src,dist)
            self.assertEqual(Path(a['archive']).read_bytes(),old)


if __name__=='__main__':unittest.main()
