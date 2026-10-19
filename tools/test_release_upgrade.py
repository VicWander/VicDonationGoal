from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'core')]
from tools import update_from_old as upgrade
from tools.test_portability import sample_project,write_json

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name); self.old=self.root/'old'; self.new=self.root/'new'
        self.old.mkdir(); self.new.mkdir(); sample_project(self.old); sample_project(self.new)
        (self.new/'VERSION').write_text('1.4.6\n')
        write_json(self.old/'integrations/tts/tts_sent.json',{'initialized':True,'seen':['previous']})
        write_json(self.old/'integrations/tts/tts_queue.json',[{'id':'old-speech','text':'do not replay'}])
        write_json(self.old/'integrations/tts/tts_control.json',{'commands':[{'id':'old-command','type':'replay'}]})
        write_json(self.old/'integrations/streamerbot/streamerbot_sent.json',{'sent':['previous']})
        self.no_process=patch.object(upgrade,'ensure_stopped'); self.no_process.start(); self.addCleanup(self.no_process.stop)

    def test_both_versions_keep_history_connections_and_seed_sent_markers(self):
        for version in ['1.4.4','1.4.5.1']:
            with self.subTest(version=version):
                (self.old/'VERSION').write_text(version)
                result=upgrade.migrate(self.old,self.new)
                self.assertEqual(result['donations'],1)
                for rel in ['core/data/donations.json','core/data/state.json','core/data/donor_profiles.json',
                            'integrations/donationalerts/donationalerts_tokens.json','integrations/streamerbot/streamerbot_config.json']:
                    self.assertEqual((self.old/rel).read_bytes(),(self.new/rel).read_bytes())
                sent=json.loads((self.new/'integrations/tts/tts_sent.json').read_text())
                self.assertTrue(sent['initialized']); self.assertIn('manual:1',sent['seen']); self.assertIn('previous',sent['seen'])
                sb=json.loads((self.new/'integrations/streamerbot/streamerbot_sent.json').read_text())
                self.assertIn('manual:1',sb['sent'])
                self.assertEqual(json.loads((self.new/'integrations/tts/tts_queue.json').read_text()),[])
                self.assertEqual(json.loads((self.new/'integrations/tts/tts_control.json').read_text()),{'commands':[]})
                self.assertEqual((self.new/'VERSION').read_text().strip(),'1.4.6')

    def test_migration_is_repeatable_without_duplicate_history(self):
        upgrade.migrate(self.old,self.new); upgrade.migrate(self.old,self.new)
        self.assertEqual(len(json.loads((self.new/'core/data/donations.json').read_text())),1)

    def test_failed_write_rolls_back_and_keeps_original_source(self):
        before=(self.new/'core/data/state.json').read_bytes()
        old=(self.old/'core/data/donations.json').read_bytes()
        with patch.object(upgrade.portability,'apply_payload',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError): upgrade.migrate(self.old,self.new)
        self.assertEqual((self.new/'core/data/state.json').read_bytes(),before)
        self.assertEqual((self.old/'core/data/donations.json').read_bytes(),old)

    def test_rejects_same_folder_or_newer_version(self):
        with self.assertRaises(ValueError): upgrade.migrate(self.old,self.old)
        (self.old/'VERSION').write_text('2.0.0')
        with self.assertRaises(ValueError): upgrade.migrate(self.old,self.new)

    def test_running_folder_is_rejected_before_any_writes(self):
        with patch.object(upgrade,'ensure_stopped',side_effect=RuntimeError('running')):
            with self.assertRaises(RuntimeError): upgrade.migrate(self.old,self.new)

    def test_new_donation_can_be_spoken_after_migration_but_old_one_cannot(self):
        upgrade.migrate(self.old,self.new)
        from integrations.tts import tts_hub as tts
        rows=json.loads((self.new/'core/data/donations.json').read_text())
        rows.append({'uniqueKey':'manual:new','source':'manual','externalId':'new','amount':50,'speakTTS':True,'message':'new'})
        markers=json.loads((self.new/'integrations/tts/tts_sent.json').read_text())
        sent={'initialized':True,'seen':set(markers['seen'])}
        with patch.object(tts,'core_get',return_value=rows),patch.object(tts,'core_post') as post,patch.object(tts,'save_sent'):
            tts.scan_donations({},sent)
            tts.scan_donations({},sent)
        self.assertEqual(post.call_count,1)
        self.assertEqual(post.call_args.args[1]['eventId'],'manual:new')

    def test_legacy_rule_ids_do_not_replay_old_streamerbot_events(self):
        from integrations.streamerbot import streamerbot_bridge as sb
        rule={'action_id':'legacy-action'}
        write_json(self.old/'integrations/streamerbot/donation_event_rules.json',{'enabled':True,'rules':[rule]})
        upgrade.migrate(self.old,self.new)
        rows=json.loads((self.new/'core/data/donations.json').read_text())
        rows.append({'uniqueKey':'manual:new','source':'manual','amount':50})
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name,rel in [('SENT_FILE','streamerbot_sent.json'),('EVENT_RULES_SENT_FILE','streamerbot_event_rules_sent.json')]:
                stack.enter_context(patch.object(sb,name,self.new/'integrations/streamerbot'/rel))
            stack.enter_context(patch.object(sb,'load_config',return_value={'enabled':True}))
            stack.enter_context(patch.object(sb,'load_event_rules',return_value={'enabled':True,'rules':[rule]}))
            stack.enter_context(patch.object(sb,'load_donations',return_value=rows))
            stack.enter_context(patch.object(sb,'should_send',return_value=True))
            stack.enter_context(patch.object(sb,'matching_event_rules',return_value=[rule]))
            main=stack.enter_context(patch.object(sb,'send_to_streamerbot',return_value=True))
            action=stack.enter_context(patch.object(sb,'send_event_rule_to_streamerbot',return_value=True))
            stack.enter_context(patch.object(sb,'write_status'))
            stack.enter_context(patch.object(sb.time,'sleep',side_effect=KeyboardInterrupt))
            sb.run_loop();sb.run_loop()
        self.assertEqual(main.call_count,1)
        self.assertEqual(action.call_count,1)
        self.assertEqual(action.call_args.args[0]['uniqueKey'],'manual:new')

    def test_relative_worker_command_is_not_missed(self):
        self.no_process.stop()
        with patch.object(upgrade,'process_inventory',return_value=[{'ProcessId':-1,'CommandLine':'python tts_hub.py'}]):
            with self.assertRaises(RuntimeError):upgrade.ensure_stopped(self.old,self.new)

    def test_config_only_import_keeps_target_history_baselined(self):
        existing={p.relative_to(self.new).as_posix():p.read_bytes() for p in upgrade.portability.collect_user_files(self.new)}
        existing['integrations/streamerbot/donation_event_rules.json']=upgrade.encode({'rules':[{'rule_id':'target-rule'}]})
        payload={'integrations/donatty/donatty_config.json':upgrade.encode({'enabled':False})}
        prepared,count=upgrade.prepare_payload(payload,existing=existing)
        self.assertNotIn('core/data/donations.json',prepared)
        self.assertEqual(count,1)
        self.assertIn('manual:1',json.loads(prepared['integrations/tts/tts_sent.json'])['seen'])
        self.assertIn('manual:1::rule::target-rule',json.loads(prepared['integrations/streamerbot/streamerbot_event_rules_sent.json'])['sent'])

    def test_windows_case_alias_uses_imported_history_for_baseline(self):
        existing={'core/data/donations.json':upgrade.encode([{'uniqueKey':'manual:old','amount':10}])}
        payload={'Core/Data/Donations.json':upgrade.encode([{'uniqueKey':'manual:imported','amount':20}])}
        prepared,count=upgrade.prepare_payload(payload,existing=existing)
        self.assertIn('manual:imported',json.loads(prepared['integrations/tts/tts_sent.json'])['seen'])

class BuildTests(unittest.TestCase):
    def test_windows_case_does_not_expose_user_directories(self):
        from tools import build_release as build
        self.assertFalse(build.allowed(Path('integrations/tts/Voices/private.png')))
        self.assertFalse(build.allowed(Path('core/Data/private.png')))

    def test_public_build_does_not_include_private_files_or_canaries(self):
        from tools import build_release as build
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir();sample_project(root)
            (root/'core/server.py').write_text('print("app")\n')
            write_json(root/'integrations/donationalerts/donationalerts_config.example.json',{'enabled':True,'client_id':'PASTE_ID'})
            (root/'README_PRIVATE.txt').write_text('private-canary-never-publish')
            (root/'runtime').mkdir();(root/'runtime/private.log').write_text('secret-canary-log')
            private_voice=root/'integrations/tts/voices/private-notes.md'
            private_voice.parent.mkdir(parents=True);private_voice.write_text('private-voice-canary')
            (root/'core/data/private-notes.md').write_text('private-data-canary')
            (root/'requirements.txt').write_text('requests\n')
            (root/'docs').mkdir();(root/'docs/MANUAL.md').write_text('Public manual')
            target=Path(tmp)/'public'
            build.build_public(root,target)
            self.assertFalse((target/'README_PRIVATE.txt').exists())
            self.assertFalse((target/'runtime').exists())
            self.assertTrue((target/'docs/MANUAL.md').exists())
            self.assertEqual(json.loads((target/'core/data/donations.json').read_text()),[])
            cfg=json.loads((target/'integrations/donationalerts/donationalerts_config.json').read_text())
            self.assertFalse(cfg['enabled'])
            self.assertFalse((target/'integrations/donationalerts/donationalerts_tokens.json').exists())
            self.assertEqual((target/'VERSION').read_text().strip(),'1.4.6')
            content=b''.join(p.read_bytes() for p in target.rglob('*') if p.is_file())
            self.assertNotIn(b'private-canary-never-publish',content)
            self.assertNotIn(b'secret-canary-log',content)
            self.assertNotIn(b'private-voice-canary',content)
            self.assertNotIn(b'private-data-canary',content)
            self.assertNotIn(b'"secret"',content)

    def test_existing_destination_is_never_overwritten(self):
        from tools import build_release as build
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dest=root/'exists';dest.mkdir()
            with self.assertRaises(FileExistsError):build.build_public(ROOT,dest)

if __name__=='__main__':unittest.main(verbosity=2)
