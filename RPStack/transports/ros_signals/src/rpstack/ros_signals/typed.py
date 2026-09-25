"""Explicit typed projections supported by desktop rclpy and ROSMicroPy."""
import math


class JointPositionPublisher:
    """Project a measured linear position to a single prismatic joint state."""
    def __init__(self, node, spec, backend, source):
        from sensor_msgs.msg import JointState
        if spec.get('kind') != 'linear_joint_state':
            raise ValueError('unsupported ROS projection kind')
        for key in ('topic', 'service', 'joint_name'):
            if not isinstance(spec.get(key), str) or not spec[key]:
                raise ValueError('ROS projection requires ' + key)
        if not isinstance(spec.get('frame_id', ''), str):
            raise ValueError('frame_id must be a string')
        self.node, self.spec, self.backend, self.source = node, spec, backend, source
        self.message_type = JointState
        self.publisher = node.create_publisher(JointState, spec['topic'], 10)

    def send(self, signal):
        # Do not re-export relayed peers under this device's joint identity.
        if signal['source'] != self.source or signal['name'] != 'motion.position.updated':
            return
        sample = signal['payload']
        if not isinstance(sample, dict) or sample.get('service') != self.spec['service']:
            return
        value = sample.get('value')
        if (sample.get('kind') != 'linear' or sample.get('unit') != 'm' or
                sample.get('valid') is not True or type(value) not in (int, float) or
                not math.isfinite(value)):
            return
        message = self.message_type()
        frame = self.spec.get('frame_id') or sample.get('reference_frame') or ''
        if self.backend == 'rosmicropy':
            # Firmware has no synchronized ROS clock API. Zero explicitly means
            # unspecified; never substitute the device's monotonic measurement time.
            message.header = {'stamp': {'sec': 0, 'nanosec': 0}, 'frame_id': frame}
        else:
            message.header.stamp = self.node.get_clock().now().to_msg()
            message.header.frame_id = frame
        message.name = [self.spec['joint_name']]
        message.position = [float(value)]
        message.velocity, message.effort = [], []
        self.publisher.publish(message)
