import unittest
from types import SimpleNamespace
from host_ui import apply_phase,show_message
import session_control as life
class Value:
 def __init__(self,value=''):self.value=value
 def set(self,value):self.value=value
class HostUiTests(unittest.TestCase):
 def app(self):return SimpleNamespace(active_request=None,displayed_request=None,connection_state=Value(),receiver_text=Value(),metrics=Value(),status=Value('连接正常'))
 def test_metrics_do_not_replace_connection_status(self):
  app=self.app();show_message(app,'显示 12 FPS | 解码 50 ms | 显示处理 80 ms | 帧确认 200 ms | 错误 0')
  self.assertEqual(app.status.value,'连接正常');self.assertIn('\n帧确认',app.metrics.value)
 def test_old_request_cannot_replace_active_session(self):
  app=self.app();app.active_request={'device_id':'new','action':2}
  apply_phase(app,life.FAILED,{'device_id':'old','action':1,'name':'旧设备'})
  self.assertEqual(app.connection_state.value,'')
 def test_phase_tracks_device_and_pause_keeps_it(self):
  app=self.app();request={'device_id':'new','action':2,'name':'我的 S3'}
  apply_phase(app,life.PREPARE,request);self.assertEqual(app.receiver_text.value,'我的 S3')
  show_message(app,'本地菜单已打开，投屏暂停');self.assertEqual(app.connection_state.value,'已暂停')
  show_message(app,'已继续桌面');self.assertEqual(app.connection_state.value,'正在串流')
