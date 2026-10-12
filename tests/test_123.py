import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import hashlib

sys.path.insert(0, str(Path(__file__).parent))
import test_app_improvements as regression
import main
import sim
import update
import release_access
import modeling
import vcmx_import

class Features(regression.Improvements):
    def test_modeling_creation_and_project_roundtrip(self):
        w=self.make_window()
        panel=w.modeling_panel
        panel.model_name.setText('Eigener Zylinder')
        panel.model_kind.setCurrentIndex(1)
        panel.model_fields[0].setValue(120)
        panel.model_fields[2].setValue(450)
        panel.model_create.click()
        obj=w.sim.scene[-1]
        self.assertEqual(obj.name,'Eigener Zylinder')
        self.assertEqual(obj.size,[120,120,450])
        other=sim.Simulation(); other.from_dict(w.sim.to_dict())
        self.assertEqual(other.scene[-1].to_dict(),obj.to_dict())

    def test_untitled_cell_error_is_fixed_by_bundle(self):
        p=Path(r'C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models\Untitled.vcmx')
        if not p.is_file(): self.skipTest('Lokale VCMX-Testdatei fehlt')
        s=sim.Simulation(); r=vcmx_import.import_file(s,str(p))
        self.assertEqual(r['main_name'],'program/main')
        s.load_program(r['programs']['cell']); s.start(); s.tick(.1)
        self.assertEqual((s.state,s.cur_line),('error',29))
        s.load_program(vcmx_import.program_source(r,'cell')); s.start(); s.tick(.1)
        self.assertNotEqual(s.state,'error')
        s.load_program(r['main_program']); s.start(); s.tick(.1)
        self.assertEqual(s.state,'wait')
        self.assertIn('$IN[1]',s.message)

    def test_dpapi_storage_and_redirect_does_not_leak_access(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            secret='test-credential-do-not-log'
            p=Path(d)/'access.dpapi'
            with patch.object(release_access,'credential_path',return_value=p), patch.object(release_access,'_TOKEN',None):
                release_access.save_token(secret)
                self.assertNotIn(secret.encode(),p.read_bytes())
                release_access._TOKEN=None
                self.assertEqual(release_access.token(),secret)
                release_access.save_token('')
                self.assertFalse(p.exists())
        req=urllib.request.Request('https://api.github.com/repos/test/repo/releases/assets/1',headers={'Authorization':'Bearer test'})
        redirected=release_access.SafeRedirect().redirect_request(req,None,302,'Found',{},'https://release-assets.githubusercontent.com/file')
        self.assertIsNone(redirected.get_header('Authorization'))

    def test_previous_stable_setup_is_prepared_without_browser(self):
        def release(version,prerelease=False):
            name=f'XimajRoboSim-Setup-{version}.exe'
            return {'tag_name':'v'+version,'prerelease':prerelease,'assets':[
                {'name':name,'url':'https://api.github.com/repos/test/repo/releases/assets/1','browser_download_url':'https://test/setup'},
                {'name':name+'.sha256','url':'https://api.github.com/repos/test/repo/releases/assets/2','browser_download_url':'https://test/sha'}]}
        data=[release('1.2.2'),release('1.2.1'),release('1.2.9',True)]
        with patch.object(update,'_get',return_value=io.BytesIO(json.dumps(data).encode())),patch.object(update,'download') as download:
            version=update.prepare_rollback()
        self.assertEqual(version,'1.2.2')
        self.assertEqual(download.call_args.args[0]['kind'],'setup')
        self.assertIn('api.github.com',download.call_args.args[0]['url'])

    def test_setup_targets_current_install_directory(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            marker=Path(d)/'pending.json'; marker.write_text(json.dumps({'setup':'C:/cache/setup.exe'}))
            with patch.object(update,'FROZEN',True),patch.object(update,'PENDING',str(marker)),patch.object(update,'APP_DIR','C:/test app'),patch('subprocess.Popen') as spawn:
                update.restart_and_apply()
            args=spawn.call_args.args[0]
            self.assertIn('/DIR=C:/test app',args)
            self.assertIn('/VERYSILENT',args)

    def test_checked_setup_is_preserved_on_failed_redownload(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            class Response(io.BytesIO):
                headers={}
            good=b'valid test setup'
            checksum=hashlib.sha256(good).hexdigest()
            info={'kind':'setup','name':'XimajRoboSim-Setup-1.2.2.exe','latest':'1.2.2','url':'https://test/setup','sha_url':'https://test/sha'}
            payload=[good]
            def get(url,timeout=15):
                return Response(checksum.encode() if url.endswith('/sha') else payload[0])
            marker=Path(d)/'pending.json'
            with patch.dict(os.environ,{'APPDATA':d}),patch.object(update,'PENDING',str(marker)),patch.object(update,'_get',side_effect=get):
                update.download(info)
                setup=Path(json.loads(marker.read_text())['setup'])
                self.assertEqual(setup.read_bytes(),good)
                payload[0]=b'corrupted'
                with self.assertRaises(RuntimeError): update.download(info)
                self.assertEqual(setup.read_bytes(),good)

    def test_postponed_install_can_be_started_without_redownload(self):
        w=self.make_window()
        with patch.object(main.QMessageBox,'question',return_value=main.QMessageBox.StandardButton.No),patch.object(update,'download') as download:
            w.on_update_done('')
            self.assertTrue(w._package_ready)
            self.assertTrue(w.up_install.isEnabled())
            w.start_download()
            download.assert_not_called()

    def test_failed_installer_launch_keeps_app_usable(self):
        w=self.make_window(); w.timer.start(16)
        with patch.object(update,'restart_and_apply',side_effect=OSError('Start fehlgeschlagen')):
            w.restart_for_update()
        self.assertTrue(w.timer.isActive())
        self.assertIn('Start fehlgeschlagen',w.up_notes.toPlainText())
        w.timer.stop()

if __name__=='__main__': unittest.main(verbosity=2)
