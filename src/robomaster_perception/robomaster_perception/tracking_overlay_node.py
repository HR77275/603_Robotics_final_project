import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from robomaster_perception_msgs.msg import PeopleDepth, PeopleIdentities, TrackedPeople


class TrackingOverlayNode(Node):
    def __init__(self):
        super().__init__("tracking_overlay_node")

        self.bridge = CvBridge()
        self.latest_tracks = None
        self.latest_depth_by_id = {}
        self.latest_identity_by_id = {}

        self.create_subscription(Image, "/camera/image_color", self.image_cb, 10)
        self.create_subscription(TrackedPeople, "/people/tracks", self.tracks_cb, 10)
        self.create_subscription(PeopleDepth, "/people/depth", self.depth_cb, 10)
        self.create_subscription(PeopleIdentities, "/people/identities", self.identity_cb, 10)

        self.pub = self.create_publisher(Image, "/perception/tracking_debug_image", 10)

        self.get_logger().info("Tracking overlay node started")

    def tracks_cb(self, msg):
        self.latest_tracks = msg

    def depth_cb(self, msg):
        self.latest_depth_by_id = {person.track_id: person for person in msg.people}

    def identity_cb(self, msg):
        self.latest_identity_by_id = {identity.track_id: identity for identity in msg.identities}

    def draw_roi(self, img, roi, label):
        h, w = img.shape[:2]

        cx = int(roi.x_offset * w)
        cy = int(roi.y_offset * h)
        bw = int(roi.width * w)
        bh = int(roi.height * h)

        x1 = max(0, cx - bw // 2)
        y1 = max(0, cy - bh // 2)
        x2 = min(w - 1, cx + bw // 2)
        y2 = min(h - 1, cy + bh // 2)

        color = (0, 255, 0)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        text_origin = (x1, max(20, y1 - 8))
        cv2.putText(
            img,
            label,
            text_origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )

    def format_label(self, track):
        identity = self.latest_identity_by_id.get(track.track_id)
        name = identity.name if identity is not None and identity.name else "unknown"
        label = f"id:{track.track_id} {name} {track.state}"
        if identity is not None and identity.status in ("recognized", "cached"):
            label += f" {identity.confidence:.2f}"
        depth = self.latest_depth_by_id.get(track.track_id)
        if depth is not None and depth.depth_m == depth.depth_m:
            label += f" {depth.depth_m:.2f}m"
            if depth.tof_used:
                label += " tof"
        return label

    def image_cb(self, msg):
        img = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")

        if self.latest_tracks is not None:
            for track in self.latest_tracks.tracks:
                self.draw_roi(img, track.roi, self.format_label(track))

        out = self.bridge.cv2_to_imgmsg(img, encoding="bgr8")
        out.header = msg.header
        self.pub.publish(out)


def main():
    rclpy.init()
    node = TrackingOverlayNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
