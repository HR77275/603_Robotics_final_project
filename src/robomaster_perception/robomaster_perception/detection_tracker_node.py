import rclpy
from rclpy.node import Node

from robomaster_msgs.msg import Detection
from robomaster_perception_msgs.msg import TrackedPeople, TrackedPerson

from .iou_tracker import IoUTracker


class DetectionTrackerNode(Node):
    def __init__(self):
        super().__init__("detection_tracker_node")

        self.declare_parameter("iou_threshold", 0.25)
        self.declare_parameter("max_missed", 10)

        self.tracker = IoUTracker(
            iou_threshold=self.get_parameter("iou_threshold").value,
            max_missed=self.get_parameter("max_missed").value,
        )

        self.sub = self.create_subscription(Detection, "/vision", self.vision_cb, 10)
        self.pub = self.create_publisher(TrackedPeople, "/people/tracks", 10)

        self.get_logger().info("Detection tracker node started")

    def vision_cb(self, msg):
        detections = [person.roi for person in msg.people]
        tracks = self.tracker.update(detections)

        out = TrackedPeople()
        out.header = msg.header

        for track in tracks:
            item = TrackedPerson()
            item.track_id = track.track_id
            item.roi = track.roi
            item.confidence = 1.0
            item.state = track.state
            item.age = track.age
            item.missed_frames = track.missed_frames
            out.tracks.append(item)

        self.pub.publish(out)


def main():
    rclpy.init()
    node = DetectionTrackerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
