import rclpy
from cv_bridge import CvBridge
from deep_sort_realtime.deepsort_tracker import DeepSort
from rclpy.node import Node
from sensor_msgs.msg import Image

from robomaster_msgs.msg import Detection, RegionOfInterest
from robomaster_perception_msgs.msg import TrackedPeople, TrackedPerson


class DeepSortTrackerNode(Node):
    def __init__(self):
        super().__init__("deepsort_tracker_node")

        self.declare_parameter("image_topic", "/camera/image_color")
        self.declare_parameter("vision_topic", "/vision")
        self.declare_parameter("output_topic", "/people/tracks")
        self.declare_parameter("max_age", 15)
        self.declare_parameter("n_init", 2)
        self.declare_parameter("max_iou_distance", 0.7)
        self.declare_parameter("max_cosine_distance", 0.4)
        self.declare_parameter("embedder", "mobilenet")
        self.declare_parameter("embedder_gpu", True)

        image_topic = self.get_parameter("image_topic").value
        vision_topic = self.get_parameter("vision_topic").value
        output_topic = self.get_parameter("output_topic").value

        self.bridge = CvBridge()
        self.latest_frame = None
        self.latest_image_header = None
        self.warned_no_image = False

        self.tracker = DeepSort(
            max_age=int(self.get_parameter("max_age").value),
            n_init=int(self.get_parameter("n_init").value),
            max_iou_distance=float(self.get_parameter("max_iou_distance").value),
            max_cosine_distance=float(self.get_parameter("max_cosine_distance").value),
            embedder=str(self.get_parameter("embedder").value),
            embedder_gpu=bool(self.get_parameter("embedder_gpu").value),
            bgr=True,
        )

        self.create_subscription(Image, image_topic, self.image_cb, 10)
        self.create_subscription(Detection, vision_topic, self.vision_cb, 10)
        self.pub = self.create_publisher(TrackedPeople, output_topic, 10)

        self.get_logger().info(
            f"DeepSORT tracker started: image={image_topic}, vision={vision_topic}, output={output_topic}"
        )

    def image_cb(self, msg):
        self.latest_frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        self.latest_image_header = msg.header

    def roi_to_ltrb_pixels(self, roi, image_width, image_height):
        cx = roi.x_offset * image_width
        cy = roi.y_offset * image_height
        bw = roi.width * image_width
        bh = roi.height * image_height

        left = max(0.0, cx - bw / 2.0)
        top = max(0.0, cy - bh / 2.0)
        right = min(float(image_width - 1), cx + bw / 2.0)
        bottom = min(float(image_height - 1), cy + bh / 2.0)
        return left, top, right, bottom

    def ltrb_pixels_to_roi(self, ltrb, image_width, image_height):
        left, top, right, bottom = ltrb
        left = max(0.0, min(float(image_width - 1), float(left)))
        top = max(0.0, min(float(image_height - 1), float(top)))
        right = max(0.0, min(float(image_width - 1), float(right)))
        bottom = max(0.0, min(float(image_height - 1), float(bottom)))

        width = max(0.0, right - left)
        height = max(0.0, bottom - top)
        cx = left + width / 2.0
        cy = top + height / 2.0

        roi = RegionOfInterest()
        roi.x_offset = float(cx / image_width) if image_width else 0.0
        roi.y_offset = float(cy / image_height) if image_height else 0.0
        roi.width = float(width / image_width) if image_width else 0.0
        roi.height = float(height / image_height) if image_height else 0.0
        return roi

    def track_id_as_int(self, track_id):
        try:
            return int(track_id)
        except (TypeError, ValueError):
            return abs(hash(str(track_id))) % 2147483647

    def vision_cb(self, msg):
        if self.latest_frame is None:
            if not self.warned_no_image:
                self.get_logger().warn("Waiting for camera image before running DeepSORT")
                self.warned_no_image = True
            return

        frame = self.latest_frame
        image_height, image_width = frame.shape[:2]

        detections = []
        for person in msg.people:
            left, top, right, bottom = self.roi_to_ltrb_pixels(
                person.roi, image_width, image_height
            )
            width = right - left
            height = bottom - top
            if width <= 1.0 or height <= 1.0:
                continue
            detections.append(([left, top, width, height], 1.0, "person"))

        tracks = self.tracker.update_tracks(detections, frame=frame)

        out = TrackedPeople()
        out.header = msg.header

        for track in tracks:
            if getattr(track, "time_since_update", 0) > 1:
                continue

            item = TrackedPerson()
            item.track_id = self.track_id_as_int(track.track_id)
            ltrb = track.to_ltrb(orig=True, orig_strict=False)
            item.roi = self.ltrb_pixels_to_roi(ltrb, image_width, image_height)
            item.confidence = 1.0
            item.state = "confirmed" if track.is_confirmed() else "tentative"
            item.age = int(getattr(track, "age", 0))
            item.missed_frames = int(getattr(track, "time_since_update", 0))
            out.tracks.append(item)

        self.pub.publish(out)


def main():
    rclpy.init()
    node = DeepSortTrackerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
