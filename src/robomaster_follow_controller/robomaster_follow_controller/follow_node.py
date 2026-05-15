import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, String

from robomaster_perception_msgs.msg import (
    PeopleDepth,
    PeopleIdentities,
    TrackedPeople,
)


STATE_FOLLOWING = 'FOLLOWING'
STATE_FOLLOWING_AUTHORIZED = 'FOLLOWING_AUTHORIZED'
STATE_APPROACHING = 'APPROACHING'
DEFAULT_AUTHORIZED_IDENTITY_STATUSES = ('recognized', 'cached')


def is_authorized_identity(identity, authorized_statuses):
    if identity is None:
        return False

    name = (identity.name or '').strip().lower()
    if not name or name == 'unknown':
        return False

    allowed_statuses = {
        str(status).strip().lower()
        for status in authorized_statuses
    }
    status = (identity.status or '').strip().lower()
    return status in allowed_statuses


def depth_scaled_linear_limit(
    depth_error,
    base_limit,
    far_limit,
    start_error,
    full_error,
    enabled=True,
):
    base_limit = abs(float(base_limit))
    far_limit = max(base_limit, abs(float(far_limit)))
    if not enabled:
        return base_limit

    depth_error = float(depth_error)
    if not math.isfinite(depth_error):
        return base_limit

    start_error = max(0.0, float(start_error))
    full_error = max(start_error + 1e-6, float(full_error))
    if depth_error <= start_error:
        return base_limit

    ratio = min(1.0, (depth_error - start_error) / (full_error - start_error))
    return base_limit + ratio * (far_limit - base_limit)


class PID:
    def __init__(self, kp, ki, kd, integral_limit):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.integral_limit = abs(float(integral_limit))
        self.integral = 0.0
        self.prev_error = None

    def reset(self):
        self.integral = 0.0
        self.prev_error = None

    def update(self, error, dt):
        if dt <= 0.0:
            return 0.0

        self.integral += error * dt
        self.integral = max(-self.integral_limit, min(self.integral, self.integral_limit))

        derivative = 0.0
        if self.prev_error is not None:
            derivative = (error - self.prev_error) / dt
        self.prev_error = error

        return self.kp * error + self.ki * self.integral + self.kd * derivative


class FollowNode(Node):
    def __init__(self):
        super().__init__('follow_node')

        self.declare_parameter('debug_image_topic', '/perception/tracking_debug_image')
        self.declare_parameter('people_depth_topic', '/people/depth')
        self.declare_parameter('people_tracks_topic', '/people/tracks')
        self.declare_parameter('people_identities_topic', '/people/identities')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('follow_active_topic', '/follow_target_active')
        self.declare_parameter('behavior_state_topic', '/behavior_state')
        self.declare_parameter('target_track_id', -1)
        self.declare_parameter('target_distance_m', 1.5)
        self.declare_parameter('follow_distance_m', 1.5)
        self.declare_parameter('approach_distance_m', 0.8)
        self.declare_parameter('control_rate_hz', 20.0)
        self.declare_parameter('stale_timeout_sec', 0.75)
        self.declare_parameter('track_stale_timeout_sec', 0.35)
        self.declare_parameter('linear_kp', 0.45)
        self.declare_parameter('linear_ki', 0.0)
        self.declare_parameter('linear_kd', 0.12)
        self.declare_parameter('angular_kp', 1.2)
        self.declare_parameter('angular_ki', 0.0)
        self.declare_parameter('angular_kd', 0.08)
        self.declare_parameter('integral_limit', 0.5)
        self.declare_parameter('max_linear_mps', 0.18)
        self.declare_parameter('far_max_linear_mps', 0.30)
        self.declare_parameter('depth_scaled_speed_enabled', True)
        self.declare_parameter('speed_scale_start_error_m', 0.25)
        self.declare_parameter('speed_scale_full_error_m', 0.90)
        self.declare_parameter('max_angular_radps', 0.6)
        self.declare_parameter('deadband_distance_m', 0.08)
        self.declare_parameter('deadband_center_norm', 0.04)
        self.declare_parameter('angular_only_error_norm', 0.18)
        self.declare_parameter('angular_sign', -1.0)
        self.declare_parameter('enable_motion', True)
        self.declare_parameter('require_fsm_active', True)
        self.declare_parameter(
            'authorized_identity_statuses',
            list(DEFAULT_AUTHORIZED_IDENTITY_STATUSES),
        )
        self.declare_parameter('identity_stale_timeout_sec', 2.5)

        self.target = None
        self.image_width = None
        self.image_height = None
        self.authorized_only = False
        self.latest_track_by_id = {}
        self.latest_identity_by_id = {}
        self.last_track_time = None
        self.last_identity_time = None
        self.last_target_time = None
        self.last_control_time = self.get_clock().now()
        self.sent_stop = True
        self.fsm_active = not bool(self.get_parameter('require_fsm_active').value)
        self.behavior_state = 'IDLE'

        integral_limit = self.get_parameter('integral_limit').value
        self.pid_dist = PID(
            self.get_parameter('linear_kp').value,
            self.get_parameter('linear_ki').value,
            self.get_parameter('linear_kd').value,
            integral_limit,
        )
        self.pid_center = PID(
            self.get_parameter('angular_kp').value,
            self.get_parameter('angular_ki').value,
            self.get_parameter('angular_kd').value,
            integral_limit,
        )

        self.cmd_pub = self.create_publisher(
            Twist,
            self.get_parameter('cmd_vel_topic').value,
            10,
        )
        self.create_subscription(
            Image,
            self.get_parameter('debug_image_topic').value,
            self.image_cb,
            10,
        )
        self.create_subscription(
            PeopleDepth,
            self.get_parameter('people_depth_topic').value,
            self.people_depth_cb,
            10,
        )
        self.create_subscription(
            TrackedPeople,
            self.get_parameter('people_tracks_topic').value,
            self.people_tracks_cb,
            10,
        )
        self.create_subscription(
            PeopleIdentities,
            self.get_parameter('people_identities_topic').value,
            self.people_identities_cb,
            10,
        )
        self.create_subscription(
            Bool,
            self.get_parameter('follow_active_topic').value,
            self.follow_active_cb,
            10,
        )
        self.create_subscription(
            String,
            self.get_parameter('behavior_state_topic').value,
            self.behavior_state_cb,
            10,
        )

        rate = max(1.0, float(self.get_parameter('control_rate_hz').value))
        self.create_timer(1.0 / rate, self.control_loop)

        self.get_logger().info(
            'Follow node started: subscribing to '
            f"{self.get_parameter('debug_image_topic').value} and "
            f"{self.get_parameter('people_depth_topic').value}; "
            f"tracks={self.get_parameter('people_tracks_topic').value}; "
            f"identities={self.get_parameter('people_identities_topic').value}; "
            f"FSM active required={self.get_parameter('require_fsm_active').value}"
        )

    def image_cb(self, msg):
        self.image_width = int(msg.width)
        self.image_height = int(msg.height)

    def people_tracks_cb(self, msg):
        self.latest_track_by_id = {
            int(track.track_id): track for track in msg.tracks
        }
        self.last_track_time = self.get_clock().now()

    def people_identities_cb(self, msg):
        self.latest_identity_by_id = {
            int(identity.track_id): identity for identity in msg.identities
        }
        now = self.get_clock().now()
        self.last_identity_time = now
        if (
            self.authorized_only
            and self.target is not None
            and not self.is_authorized_track(self.target.track_id, now)
        ):
            self.target = None
            self.last_target_time = None
            self.publish_stop()

    def identity_data_is_fresh(self, now):
        if self.last_identity_time is None:
            return False

        age = (now - self.last_identity_time).nanoseconds * 1e-9
        stale_timeout = float(
            self.get_parameter('identity_stale_timeout_sec').value
        )
        return age <= stale_timeout

    def is_authorized_track(self, track_id, now):
        if not self.identity_data_is_fresh(now):
            return False

        return is_authorized_identity(
            self.latest_identity_by_id.get(int(track_id)),
            self.get_parameter('authorized_identity_statuses').value,
        )

    def track_data_is_fresh(self, now):
        if self.last_track_time is None:
            return False

        age = (now - self.last_track_time).nanoseconds * 1e-9
        stale_timeout = float(
            self.get_parameter('track_stale_timeout_sec').value
        )
        return age <= stale_timeout

    def target_roi(self, now):
        if self.target is None:
            return None

        if self.track_data_is_fresh(now):
            track = self.latest_track_by_id.get(int(self.target.track_id))
            if track is not None:
                return track.roi

        return self.target.roi

    def people_depth_cb(self, msg):
        valid_people = [
            person for person in msg.people
            if math.isfinite(person.depth_m) and person.depth_m > 0.0
        ]
        if self.authorized_only:
            now = self.get_clock().now()
            valid_people = [
                person for person in valid_people
                if self.is_authorized_track(person.track_id, now)
            ]

        if not valid_people:
            self.target = None
            return

        target_track_id = int(self.get_parameter('target_track_id').value)
        if target_track_id >= 0:
            matches = [person for person in valid_people if person.track_id == target_track_id]
            self.target = matches[0] if matches else None
        else:
            self.target = min(valid_people, key=lambda person: person.depth_m)

        if self.target is not None:
            self.last_target_time = self.get_clock().now()

    def follow_active_cb(self, msg):
        was_active = self.fsm_active
        self.fsm_active = bool(msg.data)
        if was_active and not self.fsm_active:
            self.publish_stop()

    def behavior_state_cb(self, msg):
        state = (msg.data or '').strip()
        authorized_only = state == STATE_FOLLOWING_AUTHORIZED
        if authorized_only != self.authorized_only:
            self.target = None
            self.last_target_time = None
            self.publish_stop()
        self.authorized_only = authorized_only
        self.behavior_state = state
        if state in (STATE_FOLLOWING, STATE_FOLLOWING_AUTHORIZED):
            self.set_parameters([
                Parameter(
                    'target_distance_m',
                    Parameter.Type.DOUBLE,
                    float(self.get_parameter('follow_distance_m').value),
                )
            ])
        elif state == STATE_APPROACHING:
            self.set_parameters([
                Parameter(
                    'target_distance_m',
                    Parameter.Type.DOUBLE,
                    float(self.get_parameter('approach_distance_m').value),
                )
            ])
        elif state:
            self.publish_stop()

    def clamp(self, value, limit):
        limit = abs(float(limit))
        return max(-limit, min(limit, value))

    def publish_stop(self):
        if not self.sent_stop:
            self.cmd_pub.publish(Twist())
            self.sent_stop = True
        self.pid_dist.reset()
        self.pid_center.reset()

    def control_loop(self):
        now = self.get_clock().now()
        dt = (now - self.last_control_time).nanoseconds * 1e-9
        self.last_control_time = now

        if not self.fsm_active:
            self.publish_stop()
            return

        if self.target is None or self.last_target_time is None:
            self.publish_stop()
            return

        age = (now - self.last_target_time).nanoseconds * 1e-9
        if age > float(self.get_parameter('stale_timeout_sec').value):
            self.publish_stop()
            return

        depth_error = self.target.depth_m - float(self.get_parameter('target_distance_m').value)
        target_roi = self.target_roi(now)
        if target_roi is None:
            self.publish_stop()
            return

        center_error = target_roi.x_offset - 0.5

        if abs(depth_error) < float(self.get_parameter('deadband_distance_m').value):
            depth_error = 0.0
        if abs(center_error) < float(self.get_parameter('deadband_center_norm').value):
            center_error = 0.0

        linear_x = self.pid_dist.update(depth_error, dt)
        angular_z = (
            float(self.get_parameter('angular_sign').value)
            * self.pid_center.update(center_error, dt)
        )

        if abs(center_error) > float(self.get_parameter('angular_only_error_norm').value):
            linear_x = 0.0

        base_linear_limit = abs(float(self.get_parameter('max_linear_mps').value))
        forward_linear_limit = depth_scaled_linear_limit(
            depth_error,
            base_linear_limit,
            self.get_parameter('far_max_linear_mps').value,
            self.get_parameter('speed_scale_start_error_m').value,
            self.get_parameter('speed_scale_full_error_m').value,
            bool(self.get_parameter('depth_scaled_speed_enabled').value),
        )
        linear_x = max(-base_linear_limit, min(forward_linear_limit, linear_x))
        angular_z = self.clamp(angular_z, self.get_parameter('max_angular_radps').value)

        cmd = Twist()
        if bool(self.get_parameter('enable_motion').value):
            cmd.linear.x = float(linear_x)
            cmd.angular.z = float(angular_z)

        self.cmd_pub.publish(cmd)
        self.sent_stop = False


def main(args=None):
    rclpy.init(args=args)
    node = FollowNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
