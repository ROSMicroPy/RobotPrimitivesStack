import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from rpstack.ros_bridge import RosTransport


class String:
    def __init__(self): self.data = ''


class RosTests(unittest.IsolatedAsyncioTestCase):
    async def test_rclpy_cooperative_spin_mailbox_and_cleanup(self):
        calls = []
        node = types.SimpleNamespace(
            create_publisher=lambda *args: types.SimpleNamespace(publish=lambda msg: calls.append(msg.data)),
            create_subscription=lambda *args: args[2], destroy_node=lambda: calls.append('destroy'))
        ros = types.SimpleNamespace(ok=lambda:False, init=lambda **kw: calls.append('init'),
            create_node=lambda name:node, spin_once=lambda node,timeout_sec:calls.append(timeout_sec),
            shutdown=lambda:calls.append('shutdown'))
        with patch.dict(sys.modules, {'rclpy':ros,'std_msgs':types.ModuleType('std_msgs'),
                                    'std_msgs.msg':types.SimpleNamespace(String=String)}):
            transport = RosTransport('Robie1','arm',queue_limit=1)
            await transport.start()
            message=String();message.data='signal'
            transport._receive(message); transport._receive(message)
            self.assertEqual(transport.dropped,1)
            self.assertEqual(await transport.recv(),'signal')
            self.assertIn(0,calls)
            await transport.send(b'out')
            self.assertIn('out',calls)
            await transport.stop()
            transport._receive(message)
            self.assertFalse(transport.queue)
            self.assertEqual(calls[-2:],['destroy','shutdown'])

    async def test_reference_rosmicropy_firmware_interface(self):
        # Exercise the actual included Python shim, replacing only its native module.
        root=Path(__file__).resolve().parents[4]
        firmware=root/'ROSMicroPy/components/libROSMicroPy/py'
        calls=[]
        native=types.ModuleType('ROSMicroPy')
        def stub(name):
            def invoke(*args,**kwargs):
                calls.append((name,args,kwargs))
                return None
            return invoke
        native.__getattr__=lambda name:stub(name)
        original={key:value for key,value in sys.modules.items() if key=='rclpy' or key.startswith('rclpy.') or key=='std_msgs' or key.startswith('std_msgs.')}
        for key in original: sys.modules.pop(key)
        old_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        sys.path.insert(0,str(firmware))
        try:
            with patch.dict(sys.modules,{'ROSMicroPy':native}):
                transport=RosTransport('Robie1','arm',backend='rosmicropy')
                await transport.start()
                await transport.send(b'hello')
                self.assertEqual(sum(name=='run_ROS_Stack' for name,_,_ in calls),1)
                message=transport.message_type();message.data='incoming'
                transport._receive(message)
                self.assertEqual(await transport.recv(),'incoming')
                await transport.stop()
                with self.assertRaisesRegex(RuntimeError,'ownership'):
                    await RosTransport('Robie1','arm',backend='rosmicropy').start()
        finally:
            sys.dont_write_bytecode = old_bytecode
            sys.path.remove(str(firmware))
            for key in tuple(sys.modules):
                if key=='rclpy' or key.startswith('rclpy.') or key=='std_msgs' or key.startswith('std_msgs.'):
                    sys.modules.pop(key)
            sys.modules.update(original)
