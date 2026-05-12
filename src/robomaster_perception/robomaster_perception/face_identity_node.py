import numpy as np
import rclpy
from cv_bridge import CvBridge
from insightface.app import FaceAnalysis
from pathlib import Path
from rclpy.node import Node
from sensor_msgs.msg import Image

from robomaster_perception_msgs.msg import (
    PeopleIdentities,
    PersonIdentity,
    TrackedPeople,
)


class FaceIdentityNode(Node):
    def __init__(self):
        super().__init__("face_identity_node")

        self.declare_parameter("image_topic", "/camera/image_color")
        self.declare_parameter("tracks_topic", "/people/tracks")
        self.declare_parameter("output_topic", "/people/identities")
        self.declare_parameter(
            "face_db_path",
            "face_db/embeddings/face_db.npz",
        )
        self.declare_parameter("rate_hz", 1.0)
        self.declare_parameter("threshold", 0.35)
        self.declare_parameter("model_name", "buffalo_l")
        self.declare_parameter("det_size", 640)
        self.declare_parameter("crop_padding", 0.15)
        self.declare_parameter("identity_hold_sec", 10.0)
        self.declare_parameter("use_gpu", False)

        self.bridge = CvBridge()
        self.latest_image = None
        self.latest_tracks = None
        self.identity_cache = {}

        self.names, self.embeddings = self.load_db(
            self.get_parameter("face_db_path").value
        )
        self.face_app = self.create_face_app()

        self.create_subscription(
            Image,
            self.get_parameter("image_topic").value,
            self.image_cb,
            10,
        )
        self.create_subscription(
            TrackedPeople,
            self.get_parameter("tracks_topic").value,
            self.tracks_cb,
            10,
        )
        self.pub = self.create_publisher(
            PeopleIdentities,
            self.get_parameter("output_topic").value,
            10,
        )

        period = 1.0 / max(0.1, float(self.get_parameter("rate_hz").value))
        self.create_timer(period, self.timer_cb)
        self.get_logger().info(
            f"Face identity node started with {len(self.names)} identity/identities"
        )

    def load_db(self, path):
        db_path = Path(path).expanduser()
        if not db_path.exists():
            raise FileNotFoundError(
                f"Face DB not found: {db_path}. Run `ros2 run robomaster_perception enroll_faces` first."
            )
        data = np.load(db_path, allow_pickle=False)
        names = [str(name) for name in data["names"]]
        embeddings = np.asarray(data["embeddings"], dtype=np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np.maximum(norms, 1e-6)
        return names, embeddings

    def create_face_app(self):
        model_name = str(self.get_parameter("model_name").value)
        det_size = int(self.get_parameter("det_size").value)
        use_gpu = bool(self.get_parameter("use_gpu").value)
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if use_gpu else ["CPUExecutionProvider"]
        app = FaceAnalysis(name=model_name, providers=providers)
        app.prepare(ctx_id=0 if use_gpu else -1, det_size=(det_size, det_size))
        return app

    def image_cb(self, msg):
        self.latest_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")

    def tracks_cb(self, msg):
        self.latest_tracks = msg

    def roi_to_crop(self, image, roi):
        h, w = image.shape[:2]
        cx = roi.x_offset * w
        cy = roi.y_offset * h
        bw = roi.width * w
        bh = roi.height * h
        pad = float(self.get_parameter("crop_padding").value)
        bw *= 1.0 + pad
        bh *= 1.0 + pad

        x1 = max(0, int(cx - bw / 2.0))
        y1 = max(0, int(cy - bh / 2.0))
        x2 = min(w, int(cx + bw / 2.0))
        y2 = min(h, int(cy + bh / 2.0))
        if x2 - x1 < 20 or y2 - y1 < 20:
            return None
        return image[y1:y2, x1:x2]

    def largest_face(self, crop):
        faces = self.face_app.get(crop)
        if not faces:
            return None
        return max(
            faces,
            key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]),
        )

    def recognize(self, crop):
        face = self.largest_face(crop)
        if face is None:
            return "unknown", 0.0, "no_face"

        embedding = np.asarray(face.normed_embedding, dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm <= 1e-6:
            return "unknown", 0.0, "bad_embedding"
        embedding = embedding / norm

        scores = self.embeddings @ embedding
        best_idx = int(np.argmax(scores))
        confidence = float(scores[best_idx])
        threshold = float(self.get_parameter("threshold").value)
        if confidence < threshold:
            return "unknown", confidence, "below_threshold"
        return self.names[best_idx], confidence, "recognized"

    def timer_cb(self):
        if self.latest_image is None or self.latest_tracks is None:
            return

        now = self.get_clock().now()
        hold_sec = float(self.get_parameter("identity_hold_sec").value)
        out = PeopleIdentities()
        out.header = self.latest_tracks.header

        for track in self.latest_tracks.tracks:
            crop = self.roi_to_crop(self.latest_image, track.roi)
            if crop is not None:
                name, confidence, status = self.recognize(crop)
                if status == "recognized":
                    self.identity_cache[track.track_id] = (name, confidence, now)
                elif track.track_id in self.identity_cache:
                    cached_name, cached_confidence, cached_time = self.identity_cache[track.track_id]
                    age = (now - cached_time).nanoseconds / 1e9
                    if age <= hold_sec:
                        name = cached_name
                        confidence = cached_confidence
                        status = "cached"
            else:
                name, confidence, status = "unknown", 0.0, "bad_crop"

            item = PersonIdentity()
            item.track_id = int(track.track_id)
            item.name = str(name)
            item.confidence = float(confidence)
            item.status = str(status)
            out.identities.append(item)

        self.pub.publish(out)


def main():
    rclpy.init()
    node = FaceIdentityNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
