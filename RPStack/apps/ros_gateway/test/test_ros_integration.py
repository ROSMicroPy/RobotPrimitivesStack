"""Real rclpy action/topic smoke tests; run after colcon builds rpstack_interfaces."""
import asyncio
import unittest

from test_gateway import documents, NodeRuntime, MemoryTransport

try:
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import qos_profile_sensor_data
    from rpstack_interfaces.action import MoveLinear
    from rpstack_interfaces.msg import LinearPosition
    from diagnostic_msgs.msg import DiagnosticArray
    from action_msgs.msg import GoalStatus
    ROS_AVAILABLE = True
except ImportError:
    ROS_AVAILABLE = False


@unittest.skipUnless(ROS_AVAILABLE, 'requires desktop ROS 2 and built rpstack_interfaces')
class RosIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        host, worker = documents()
        host['apps'] = [{'id': 'ros', 'entry_point': 'rpstack.apps.ros_gateway:SlideRosGateway',
                         'config': {'target_node': 'worker', 'health_timeout_s': 0.5,
                                    'move_timeout_s': 2.0, 'cancel_timeout_s': 0.5}}]
        self.worker, self.host = NodeRuntime(worker), NodeRuntime(host)
        await self.worker.boot()
        await self.host.boot()
        self.gateway = self.host.apps['ros']
        self.context = Context()
        rclpy.init(context=self.context, args=[])
        self.client_node = rclpy.create_node('gateway_test_client', context=self.context)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.client_node)
        self.client = ActionClient(self.client_node, MoveLinear, '/rpstack/slide/move')
        self.positions, self.diagnostics, self.feedback = [], [], []
        self.position_sub = self.client_node.create_subscription(LinearPosition,
            '/rpstack/slide/position', self.positions.append, qos_profile_sensor_data)
        self.diagnostic_sub = self.client_node.create_subscription(DiagnosticArray,
            '/rpstack/slide/diagnostics', self.diagnostics.append, 10)
        await self.until(lambda: self.gateway.controller.ready and self.client.server_is_ready())

    async def asyncTearDown(self):
        await self.host.shutdown()
        await self.worker.shutdown()
        self.client.destroy()
        self.executor.shutdown(timeout_sec=0)
        self.client_node.destroy_node()
        self.context.shutdown()
        self.assertFalse(MemoryTransport.links)

    async def until(self, predicate, timeout=5):
        async def wait():
            while not predicate():
                self.executor.spin_once(timeout_sec=0)
                await asyncio.sleep(0.005)
        await asyncio.wait_for(wait(), timeout)

    async def resolve(self, future):
        await self.until(future.done)
        return future.result()

    async def goal(self, target=0.2):
        message = MoveLinear.Goal()
        message.target_m = target
        return await self.resolve(self.client.send_goal_async(message, feedback_callback=self.feedback.append))

    async def test_typed_position_action_feedback_result_and_diagnostics(self):
        goal = await self.goal()
        self.assertTrue(goal.accepted)
        response = await self.resolve(goal.get_result_async())
        self.assertEqual(response.status, GoalStatus.STATUS_SUCCEEDED)
        self.assertTrue(response.result.outcome_confirmed)
        self.assertAlmostEqual(response.result.final_position_m, 0.2)
        await self.until(lambda: self.feedback and self.positions and self.diagnostics)
        self.assertEqual(self.positions[-1].header.frame_id, 'slide')
        self.assertTrue(self.positions[-1].source_timestamp_valid)
        self.assertEqual(self.positions[-1].source_timestamp_ns, 123)

    async def test_cancel_is_terminal_only_after_device_cleanup(self):
        slide = self.worker.instance('slide')
        slide.duration = 5
        goal = await self.goal()
        await self.until(lambda: slide.moving)
        cancellation = await self.resolve(goal.cancel_goal_async())
        self.assertTrue(cancellation.goals_canceling)
        result = await self.resolve(goal.get_result_async())
        self.assertEqual(result.status, GoalStatus.STATUS_CANCELED)
        self.assertTrue(slide.cleaned)
        self.assertTrue(result.result.outcome_confirmed)

    async def test_lost_result_aborts_and_blocks_next_goal(self):
        self.worker._signal_transports[0][1].drop.add('_rp.result')
        goal = await self.goal()
        result = await self.resolve(goal.get_result_async())
        self.assertEqual(result.status, GoalStatus.STATUS_ABORTED)
        self.assertFalse(result.result.outcome_confirmed)
        self.assertFalse((await self.goal(0.1)).accepted)
        self.assertEqual(self.worker.instance('slide').calls, 1)

    async def test_nonfinite_goal_rejected(self):
        self.assertFalse((await self.goal(float('nan'))).accepted)

    async def test_gateway_node_stop_cancels_motion_and_rejects_goals(self):
        slide = self.worker.instance('slide')
        slide.duration = 5
        goal = await self.goal()
        await self.until(lambda: slide.moving)
        await self.host.stop()
        result = await self.resolve(goal.get_result_async())
        self.assertEqual(result.status, GoalStatus.STATUS_ABORTED)
        await self.until(lambda: slide.cleaned)
        self.assertFalse((await self.goal()).accepted)
