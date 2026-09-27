"""ROS String envelopes; ROS callbacks hand data to the asyncio receive loop."""
from rpstack.support import asyncio


class RosTransport:
    # Choose the ROS backend/topic and prepare a bounded incoming signal mailbox.
    def __init__(self, entity, node_id, backend='rclpy', topic=None, qos=10,
                 poll_ms=10, queue_limit=32, max_bytes=2048, init=None, publishers=None):
        if backend not in ('rclpy', 'rosmicropy') or poll_ms < 1 or queue_limit < 1:
            raise ValueError('invalid ROS transport configuration')
        self.backend, self.topic = backend, topic or '/rpstack/' + entity + '/signals'
        self.node_name = 'rpstack_' + node_id.replace('-', '_')
        self.qos, self.poll_ms, self.queue_limit = qos, poll_ms, queue_limit
        self.max_bytes, self.init_args = max_bytes, init or {}
        self.queue, self.dropped = [], 0
        self.active, self.node, self.owns_context = False, None, False
        self.lock = None
        self.source = node_id
        self.publisher_specs = publishers or []
        self.typed_publishers = []
        self.projection_dropped = 0

    # Create ROS publishers/subscribers and start native firmware processing when required.
    async def start(self):
        import rclpy
        from std_msgs.msg import String
        self.rclpy, self.message_type = rclpy, String
        if self.backend == 'rosmicropy':
            # Firmware callbacks arrive from its native ROS task. Only this mailbox
            # is shared; no asyncio objects are accessed by that task.
            import _thread
            self.lock = _thread.allocate_lock()
            if getattr(rclpy, '_ros_stack_started', False):
                raise RuntimeError('ROSMicroPy transport requires ownership of the native ROS stack')
        if not rclpy.ok():
            rclpy.init(**self.init_args)
            self.owns_context = True
        self.node = rclpy.create_node(self.node_name)
        self.publisher = self.node.create_publisher(String, self.topic, self.qos)
        self.subscription = self.node.create_subscription(String, self.topic, self._receive, self.qos)
        # Register all native publishers before the firmware worker starts.
        from .typed import JointPositionPublisher
        self.typed_publishers = [JointPositionPublisher(self.node, spec, self.backend, self.source)
                                 for spec in self.publisher_specs]
        self.active = True
        if self.backend == 'rosmicropy':
            # The reference firmware's spin_once is a stub; run_ROS_Stack starts
            # the firmware worker and returns. It cannot currently be stopped.
            import ROSMicroPy
            ROSMicroPy.run_ROS_Stack()
            rclpy._ros_stack_started = True

    # Copy valid ROS text into the bounded mailbox, locking across native callback threads.
    def _receive(self, message):
        data = message.data
        if not self.active or not isinstance(data, str) or len(data) > self.max_bytes:
            return
        if self.lock:
            self.lock.acquire()
        try:
            if not self.active or len(data.encode("utf-8")) > self.max_bytes:
                return
            if len(self.queue) >= self.queue_limit:
                self.dropped += 1
            else:
                self.queue.append(data)
        finally:
            if self.lock:
                self.lock.release()

    # Poll host ROS callbacks when needed and await the next queued message.
    async def recv(self):
        while True:
            if self.backend == 'rclpy':
                self.rclpy.spin_once(self.node, timeout_sec=0)
            if self.lock:
                self.lock.acquire()
            try:
                data = self.queue.pop(0) if self.queue else None
            finally:
                if self.lock:
                    self.lock.release()
            if data is not None:
                return data
            await asyncio.sleep(self.poll_ms / 1000)

    # Publish encoded signal bytes as a ROS String and yield to other tasks.
    async def send(self, data):
        message = self.message_type()
        message.data = data.decode('utf-8')
        self.publisher.publish(message)
        if self.typed_publishers:
            from rpstack.signals import decode
            signal = decode(data, self.max_bytes)
            for publisher in self.typed_publishers:
                try:
                    publisher.send(signal)
                except (ValueError, RuntimeError):
                    self.projection_dropped += 1
        await asyncio.sleep(0)

    # Disable callbacks, release host ROS resources, and clear queued data.
    async def stop(self):
        self.active = False
        self.typed_publishers = []
        if self.node is not None and self.backend == 'rclpy':
            self.node.destroy_node()
            if self.owns_context:
                self.rclpy.shutdown()
        # ROSMicroPy has no native unregister/shutdown. Keep the callback inert
        # and refuse a second transport until a device reboot.
        if self.lock:
            self.lock.acquire()
        try:
            self.queue.clear()
        finally:
            if self.lock:
                self.lock.release()
