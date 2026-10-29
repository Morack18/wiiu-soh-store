import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

builder = import_file('builder', ROOT / 'scripts' / 'build_repo.py')
setup = import_file('setup', ROOT / 'scripts' / 'add_repo_to_sd.py')


def fake_asset(add_user_data=False, extra_runtime=False):
    f = io.BytesIO()
    with zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('wiiu/apps/soh.wuhb', b'FAKE WUHB bytes')
        z.writestr('wiiu/apps/soh923/soh.o2r', b'FAKE ENGINE bytes')
        z.writestr('README.md', b'upstream readme')
        if add_user_data:
            z.writestr('wiiu/apps/soh923/oot.o2r', b'bad')
        if extra_runtime:
            z.writestr('wiiu/apps/soh923/surprise.rpx', b'extra')
    return f.getvalue()


def releases(blob):
    return [{'tag_name': 'wiiu-9.2.3-r2', 'draft': False, 'prerelease': False,
             'published_at': '2026-10-04T01:00:00Z', 'html_url': 'https://example.com/r2',
             'assets': [{'name': 'soh-wiiu-9.2.3-r2.zip'}]},
            {'tag_name': '9.3.1', 'draft': False, 'prerelease': False,
             'assets': [{'name': 'soh-dewey-linux.zip'}]},
            {'tag_name': 'wiiu-9.2.3-r3', 'draft': False, 'prerelease': False,
             'published_at': '2026-10-11T21:17:59Z', 'html_url': 'https://example.com/r3',
             'assets': [{'name': 'soh-wiiu-9.2.3-r3-extras.zip'},
                        {'name': 'soh-wiiu-9.2.3-r3.zip', 'digest': 'sha256:' + hashlib.sha256(blob).hexdigest()}]}]


class BuildTests(unittest.TestCase):
    def test_end_to_end_package_and_repo_metadata(self):
        blob = fake_asset()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'public'
            repo = builder.build(releases(blob), blob, dest, '9.2.3', ROOT / 'assets/icon.png')
            e = repo['packages'][0]
            self.assertEqual(e['version'], '9.2.3-r3')
            self.assertEqual(e['name'], builder.PKG)
            self.assertTrue((dest / 'packages' / builder.PKG / 'icon.png').exists())
            self.assertEqual(json.loads((dest/'repo.json').read_text()), repo)
            with zipfile.ZipFile(dest/'zips'/f'{builder.PKG}.zip') as z:
                self.assertEqual(set(z.namelist()),
                                 {'info.json', 'manifest.install', *builder.RUNTIME_FILES})
                self.assertEqual(z.read('manifest.install').decode(),
                                 ''.join(f'U: {n}\n' for n in builder.RUNTIME_FILES))
                self.assertEqual(json.loads(z.read('info.json'))['version'], e['version'])
                self.assertNotIn('oot.o2r', '\n'.join(z.namelist()))

    def test_reject_corrupted_asset(self):
        blob = fake_asset()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                builder.build(releases(blob), b'corrupt', Path(d), '9.2.3', ROOT/'assets/icon.png')

    def test_reject_game_data(self):
        with self.assertRaisesRegex(ValueError, 'game data'):
            builder.extract_expected(fake_asset(add_user_data=True))

    def test_reject_new_unreviewed_runtime(self):
        with self.assertRaisesRegex(ValueError, 'Unreviewed'):
            builder.extract_expected(fake_asset(extra_runtime=True))

    def test_reject_unreviewed_new_base_version(self):
        with self.assertRaisesRegex(ValueError, 'No Wii U releases'):
            builder.choose_release(releases(fake_asset()), '9.3.0')


class SdSetupTests(unittest.TestCase):
    def test_merge_backup_and_idempotency(self):
        with tempfile.TemporaryDirectory() as temp:
            sd = Path(temp)
            p = sd/'wiiu/apps/appstore/.get/repos.json'
            p.parent.mkdir(parents=True)
            old = {'repos': [{'name': 'Stock', 'url': 'https://wiiu.cdn.fortheusers.org',
                              'type': 'get', 'enabled': True},
                             {'name': 'Extra', 'url': 'https://example.com/custom',
                              'type': 'get', 'enabled': False}]}
            p.write_text(json.dumps(old))
            url = 'https://example.github.io/wiiu-soh-store'
            setup.install(sd, url, verify=False)
            updated = json.loads(p.read_text())
            self.assertEqual(updated['repos'][:2], old['repos'])
            self.assertEqual(len(updated['repos']), 3)
            self.assertEqual(updated['repos'][2]['url'], url)
            self.assertEqual(len(list(p.parent.glob('repos.json.backup-*'))), 1)
            setup.install(sd, url, verify=False)
            self.assertEqual(len(json.loads(p.read_text())['repos']), 3)
            self.assertEqual(len(list(p.parent.glob('repos.json.backup-*'))), 1)

    def test_refuse_without_app_store_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'directory not found'):
                setup.install(Path(temp), 'https://example.github.io/wiiu-soh-store', verify=False)

    def test_offline_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as temp:
            sd = Path(temp)
            (sd/'wiiu/apps/appstore').mkdir(parents=True)
            setup.install(sd, 'https://example.github.io/wiiu-soh-store', verify=False, dry_run=True)
            self.assertFalse((sd/'wiiu/apps/appstore/.get/repos.json').exists())


if __name__ == '__main__':
    unittest.main()
