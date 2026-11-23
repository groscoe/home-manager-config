import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT=Path(__file__).parent
def load(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
audio=load('audio_controls','audio.py');palette=load('action_palette','palette.py')

def dev(name='speaker',mute=False):return {'name':name,'index':1,'description':name,'mute':mute,'volume':{'left':{'value':65000},'right':{'value':32768}},'ports':[],'properties':{}}
class AudioTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(audio.os.environ,{'XDG_STATE_HOME':self.tmp.name});self.env.start();self.addCleanup(self.env.stop);self.addCleanup(self.tmp.cleanup)
  self.a=audio.Audio({'notify':'notify','pactl':'pactl','rofi':'rofi','paplay':'paplay','mixer':'mixer'})
 def test_disconnected_hdmi_hidden(self):
  self.assertFalse(audio.available({**dev(),'ports':[{'name':'hdmi','availability':'not available'}],'active_port':'hdmi'}))
  self.assertTrue(audio.available(dev()))
 def test_monitor_is_not_a_microphone(self):
  self.assertTrue(audio.monitor(dev('speaker.monitor')))
  self.assertTrue(audio.monitor({**dev(),'properties':{'device.class':'monitor'}}))
  self.assertFalse(audio.monitor(dev('microphone')))
 def test_volume_clamped_and_balance_retained_no_unmute(self):
  with patch.object(self.a,'default',return_value='speaker'),patch.object(self.a,'listing',return_value=[dev()]),patch.object(self.a,'pa') as pa,patch.object(self.a,'notice'):
   self.a.adjust('output',5)
   self.assertEqual(pa.call_args.args,('set-sink-volume','speaker','65536','36045'))
   self.assertEqual(pa.call_count,1)
 def test_output_switch_moves_existing_streams(self):
  with patch.object(self.a,'listing',side_effect=[[dev()], [{'index':7}]]),patch.object(self.a,'pa') as pa:
   self.a.switch('output','speaker')
   self.assertEqual(pa.call_args_list[0].args,('set-default-sink','speaker'))
   self.assertEqual(pa.call_args_list[1].args,('move-sink-input',7,'speaker'))
   self.assertEqual(self.a.prefs()['output'],'speaker')
 def test_stale_device_selection_does_not_change_default(self):
  with patch.object(self.a,'listing',return_value=[]),patch.object(self.a,'pa') as pa:
   with self.assertRaises(RuntimeError):self.a.switch('output','gone')
   pa.assert_not_called()
 def test_mic_mute_latch_persisted_for_new_devices(self):
  with patch.object(self.a,'inventory',return_value=([],[dev('mic')])),patch.object(self.a,'pa') as pa,patch.object(self.a,'notice'):
   self.a.mute_mics();self.assertTrue(self.a.prefs()['mic_muted']);pa.assert_called_with('set-source-mute','mic','1')
 def test_new_input_carries_global_mute(self):
  self.a.save('preferences.json',{'mic_muted':True})
  with patch.object(self.a,'listing',side_effect=[[dev('mic')],[]]),patch.object(self.a,'pa') as pa:
   self.a.switch('input','mic');self.assertIn(('set-source-mute','mic','1'),[c.args for c in pa.call_args_list])
 def test_reconnect_restores_explicit_preference(self):
  self.a.save('preferences.json',{'output':'headphones'})
  with patch.object(self.a,'inventory',return_value=([dev(),dev('headphones')],[dev('mic')])),patch.object(self.a,'default',side_effect=lambda k:'speaker' if k=='output' else 'mic'),patch.object(self.a,'listing',return_value=[]),patch.object(self.a,'switch') as switch:
   self.a.reconcile({'output_devices':['speaker'],'input_devices':['mic']})
   switch.assert_called_once_with('output','headphones',remember=False)
 def test_existing_preference_does_not_fight_manual_mixer_change(self):
  self.a.save('preferences.json',{'output':'headphones'})
  with patch.object(self.a,'inventory',return_value=([dev(),dev('headphones')],[dev('mic')])),patch.object(self.a,'default',side_effect=lambda k:'speaker' if k=='output' else 'mic'),patch.object(self.a,'listing',return_value=[]),patch.object(self.a,'switch') as switch:
   self.a.reconcile({'output_devices':['speaker','headphones'],'input_devices':['mic']});switch.assert_not_called()
 def test_missing_default_has_available_fallback(self):
  with patch.object(self.a,'inventory',return_value=([dev()],[dev('mic')])),patch.object(self.a,'default',side_effect=lambda k:'gone' if k=='output' else 'mic'),patch.object(self.a,'listing',return_value=[]),patch.object(self.a,'switch') as switch:
   self.a.reconcile({'output_devices':['gone']});switch.assert_called_once_with('output','speaker',remember=False)
 def test_test_tone_never_unmutes_output(self):
  with patch.object(self.a,'default',return_value='speaker'),patch.object(self.a,'pa',return_value='Mute: yes') as pa:
   with self.assertRaises(RuntimeError):self.a.test()
   pa.assert_called_once_with('get-sink-mute','speaker')
 def test_tone_has_isolated_stereo_channels_and_no_global_volume_change(self):
  import wave,struct
  def playback(*argv):
   self.assertIn('--device=speaker',argv)
   with wave.open(argv[-1],'rb') as wav:
    self.assertEqual(wav.getnchannels(),2)
    values=struct.unpack('<'+str(wav.getnframes()*2)+'h',wav.readframes(wav.getnframes()))
   first=values[:36000*2];second=values[36000*2:]
   self.assertTrue(any(first[::2]));self.assertFalse(any(first[1::2]))
   self.assertFalse(any(second[::2]));self.assertTrue(any(second[1::2]))
   self.assertLessEqual(max(map(abs,values)),8000)
  with patch.object(self.a,'default',return_value='speaker'),patch.object(self.a,'pa',return_value='Mute: no') as pa,patch.object(audio,'run',side_effect=playback):
   self.a.test()
   pa.assert_called_once_with('get-sink-mute','speaker')
 def test_cancel_and_bad_index(self):
  for code,text in [(1,''),(0,'-1'),(0,'999'),(0,'sh -c command')]:
   with patch.object(audio.subprocess,'run',return_value=subprocess.CompletedProcess([],code,text,'')):
    self.assertIsNone(audio.choose(self.a.cfg,'test',['speaker']))
 def test_untrusted_device_description_cannot_make_rofi_row_or_markup(self):
  self.assertNotIn('\n',audio.safe('bad\nrow%{A:evil:}'))
  self.assertNotIn('%{',audio.safe('bad\nrow%{A:evil:}'))

class PaletteTests(unittest.TestCase):
 def test_cancel_does_not_select_anything(self):
  with patch.object(palette.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','')):
   self.assertIsNone(palette.select({'rofi':'rofi'},[{'label':'Camera'}]))
 def test_execution_uses_literal_argv(self):
  with patch.object(palette.subprocess,'Popen') as launch:
   palette.launch({}, {'argv':['/bin/tool','$(never-execute)']})
   self.assertEqual(launch.call_args.args[0],['/bin/tool','$(never-execute)'])
   self.assertNotIn('shell',launch.call_args.kwargs)
 def test_relative_command_refused(self):
  with self.assertRaises(ValueError):palette.launch({}, {'argv':['tool']})
 def test_report_runs_in_managed_terminal(self):
  with patch.object(palette.subprocess,'Popen') as launch:
   palette.launch({'terminal':'/profile/bin/alacritty'},{'argv':['/bin/report','--status'],'terminal':True})
   self.assertEqual(launch.call_args.args[0],['/profile/bin/alacritty','--hold','-e','/bin/report','--status'])

if __name__=='__main__':unittest.main()
