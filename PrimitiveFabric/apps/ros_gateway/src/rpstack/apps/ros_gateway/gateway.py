"""Typed rclpy facade running beside RPStack on one CPython asyncio loop."""
import asyncio
import time

from .controller import SlideController


class SlideRosGateway:
    """Resident NodeRuntime app. ROS imports and context are owned only at start."""
    def __init__(self, node, target_node, service='slide', namespace='rpstack/slide',
                 frame_id='', poll_ms=10, health_timeout_s=1.0,
                 inventory_interval_s=5.0, move_timeout_s=60.0, cancel_timeout_s=3.0):
        if type(poll_ms) is not int or poll_ms < 1:
            raise ValueError('poll_ms must be positive')
        self.node, self.namespace, self.frame_id = node, namespace, frame_id
        self.poll_ms = poll_ms
        self.controller = SlideController(node, target_node, service, health_timeout_s,
            inventory_interval_s, move_timeout_s, cancel_timeout_s)
        self.context = self.ros = self.executor = self.server = self.subscription = None
        self.work = set()
        self.goal = self.cancel_event = None

    async def start(self):
        import rclpy
        from rclpy.action import ActionServer, GoalResponse, CancelResponse
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from rpstack_interfaces.action import MoveLinear
        from rpstack_interfaces.msg import LinearPosition
        from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue

        self.rclpy = rclpy
        self.MoveLinear, self.LinearPosition = MoveLinear, LinearPosition
        self.DiagnosticArray, self.DiagnosticStatus, self.KeyValue = DiagnosticArray, DiagnosticStatus, KeyValue
        self.GoalResponse, self.CancelResponse = GoalResponse, CancelResponse
        self.context = Context()
        rclpy.init(context=self.context, args=[])
        self.ros = rclpy.create_node('slide_gateway', namespace=self.namespace, context=self.context)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.ros)
        self.position_pub = self.ros.create_publisher(LinearPosition, 'position', qos_profile_sensor_data)
        # Volatile diagnostics prevent a late reader mistaking retained health for liveness.
        self.diagnostics_pub = self.ros.create_publisher(DiagnosticArray, 'diagnostics', 10)
        self.server = ActionServer(self.ros, MoveLinear, 'move', self._execute,
            goal_callback=self._accept, cancel_callback=self._cancel,
            callback_group=ReentrantCallbackGroup(), result_timeout=60)
        self.subscription = self.node.signals.subscribe('motion.position.updated',
                                                       source=self.controller.target)
        self.controller.on_sample = self._position

    def _accept(self, request):
        return (self.GoalResponse.ACCEPT if self.goal is None and self.controller.reserve(request.target_m)
                else self.GoalResponse.REJECT)

    def _cancel(self, goal):
        # The execute callback may not have run yet. It also checks is_cancel_requested.
        if self.goal is goal and self.cancel_event is not None:
            self.cancel_event.set()
        return self.CancelResponse.ACCEPT

    async def _execute(self, goal):
        # ROS executor coroutines must await rclpy Futures, not asyncio Futures.
        from rclpy.task import Future
        completion = Future(executor=self.executor)
        self.goal, self.cancel_event = goal, asyncio.Event()
        if goal.is_cancel_requested:
            self.cancel_event.set()

        async def perform():
            try:
                outcome = await self.controller.move(goal.request.target_m, self.cancel_event)
            except asyncio.CancelledError:
                outcome = {'state': 'aborted', 'message': 'gateway stopped; outcome unconfirmed', 'confirmed': False}
            except Exception as error:
                outcome = {'state': 'aborted', 'message': str(error), 'confirmed': False}
            completion.set_result(outcome)
            self.work.discard(task_id)

        try:
            # Node stop/reset must cancel gateway goals just like ordinary flows.
            task_id = self.node.tasks.spawn('ros:move', perform, kind='flow', owner=self.controller.service)
            self.work.add(task_id)
        except RuntimeError as error:
            self.controller.reserved = False
            completion.set_result({'state': 'aborted', 'message': str(error), 'confirmed': False})
        try:
            outcome = await completion
            result = self.MoveLinear.Result()
            result.message = outcome['message']
            result.outcome_confirmed = outcome['confirmed']
            # Cancellation without a fresh measurement does not invent a final position.
            sample = self.controller.sample
            result.position_valid = bool(sample and sample['valid'] and outcome['state'] == 'succeeded')
            result.final_position_m = float(sample['value']) if result.position_valid else float('nan')
            if outcome['state'] == 'succeeded':
                goal.succeed()
            elif outcome['state'] == 'cancelled' and goal.is_cancel_requested:
                goal.canceled()
            else:
                goal.abort()
            return result
        finally:
            self.goal = self.cancel_event = None

    def _position(self, sample):
        message = self.LinearPosition()
        # Header uses gateway receipt time, never the device's unrelated monotonic clock.
        message.header.stamp = self.ros.get_clock().now().to_msg()
        message.header.frame_id = self.frame_id or sample.get('reference_frame') or ''
        message.position_m = float(sample['value'])
        message.valid, message.quality = sample['valid'], float(sample['quality'])
        stamp = sample.get('timestamp_ns')
        message.source_timestamp_valid = stamp is not None
        message.source_timestamp_ns = stamp or 0
        self.position_pub.publish(message)
        if self.goal is not None and self.goal.is_active:
            feedback = self.MoveLinear.Feedback()
            feedback.position = message
            self.goal.publish_feedback(feedback)

    def _diagnostics(self):
        level, summary = self.controller.diagnostic()
        status = self.DiagnosticStatus()
        status.level = (self.DiagnosticStatus.OK, self.DiagnosticStatus.WARN,
                        self.DiagnosticStatus.ERROR, self.DiagnosticStatus.STALE)[level]
        status.message = summary
        status.name = self.ros.get_namespace() + '/slide'
        status.hardware_id = self.controller.target
        status.values = [self.KeyValue(key='service', value=self.controller.service),
                         self.KeyValue(key='worker_epoch', value=self.controller.epoch or ''),
                         self.KeyValue(key='ready', value=str(self.controller.ready).lower())]
        message = self.DiagnosticArray()
        message.header.stamp = self.ros.get_clock().now().to_msg()
        message.status = [status]
        self.diagnostics_pub.publish(message)

    async def run(self):
        async def monitor():
            while True:
                await self.controller.refresh()
                await asyncio.sleep(0.5)

        async def measurements():
            while True:
                signal = await self.subscription.get()
                payload = signal['payload']
                if isinstance(payload, dict) and payload.get('service') == self.controller.service:
                    self.controller.receive_sample(payload)

        workers = [asyncio.create_task(monitor()), asyncio.create_task(measurements())]
        last_diagnostic = 0
        try:
            while self.context.ok():
                for task in workers:
                    if task.done():
                        task.result()
                        raise RuntimeError('gateway listener stopped')
                self.executor.spin_once(timeout_sec=0)
                if time.monotonic() - last_diagnostic >= 0.5:
                    self._diagnostics()
                    last_diagnostic = time.monotonic()
                await asyncio.sleep(self.poll_ms / 1000)
            raise RuntimeError('ROS context stopped')
        finally:
            self.controller.closed = True
            self.controller.fail('gateway listener stopped')
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    async def stop(self):
        self.controller.closed = True
        self.controller.fail('gateway stopping')
        if self.subscription:
            self.subscription.close()
        # Keep spinning long enough to deliver a terminal ROS result. The device's
        # lease remains the fallback when transport teardown precedes app shutdown.
        deadline = time.monotonic() + self.controller.cancel_timeout + 0.2
        while (self.work or self.goal is not None) and self.executor and time.monotonic() < deadline:
            self.executor.spin_once(timeout_sec=0)
            await asyncio.sleep(self.poll_ms / 1000)
        for task_id in list(self.work):
            if task_id in self.node.tasks.records:
                await self.node.tasks.cancel(task_id)
        self.work.clear()
        if self.server:
            self.server.destroy()
            self.server = None
        if self.executor:
            self.executor.shutdown(timeout_sec=0)
            self.executor = None
        if self.ros:
            self.ros.destroy_node()
            self.ros = None
        if self.context and self.context.ok():
            self.context.shutdown()
