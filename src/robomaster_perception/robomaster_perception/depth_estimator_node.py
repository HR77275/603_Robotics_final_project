import time

import cv2
import numpy as np
import rclpy
import torch
import torch.nn.functional as F
from cv_bridge import CvBridge
from PIL import Image as PILImage
from rclpy.node import Node
from sensor_msgs.msg import Image, Range
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

from robomaster_perception_msgs.msg import PeopleDepth, PersonDepth, TrackedPeople


class DepthEstimatorNode(Node):
    def __init__(self):
        super().__init__("depth_estimator_node")

        self.declare_parameter(
            "model_name", "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
        )
        self.declare_parameter("image_topic", "/camera/image_color")
        self.declare_parameter("tracks_topic", "/people/tracks")
        self.declare_parameter("tof_topic", "/range_0")
        self.declare_parameter("depth_topic", "/depth/image")
        self.declare_parameter("depth_viz_topic", "/depth/image_viz")
        self.declare_parameter("people_depth_topic", "/people/depth")
        self.declare_parameter("device", "cuda")
        self.declare_parameter("rate_hz", 2.0)
        self.declare_parameter("roi_center_fraction", 0.6)
        self.declare_parameter("tof_center_fraction", 0.12)
        self.declare_parameter("tof_scale_alpha", 0.2)
        self.declare_parameter("tof_stale_timeout_sec", 0.5)
        self.declare_parameter("tof_requires_centered_track", True)
        self.declare_parameter("tof_min_track_overlap_fraction", 0.25)
        self.declare_parameter("tof_max_scale_jump_ratio", 1.8)
        self.declare_parameter("default_depth_scale", 1.0)
        self.declare_parameter("min_scale", 0.2)
        self.declare_parameter("max_scale", 2.0)
        self.declare_parameter("depth_filter_alpha", 0.4)
        self.declare_parameter("depth_max_step_m", 0.35)

        self.bridge = CvBridge()
        self.latest_tracks = None
        self.latest_tof = None
        self.last_tof_time = None
        self.filtered_scale = None
        self.scale_locked = False
        self.filtered_depth_by_id = {}
        self.last_inference_time = 0.0

        self.image_topic = self.get_parameter("image_topic").value
        self.tracks_topic = self.get_parameter("tracks_topic").value
        self.tof_topic = self.get_parameter("tof_topic").value
        self.rate_hz = float(self.get_parameter("rate_hz").value)
        self.roi_center_fraction = float(self.get_parameter("roi_center_fraction").value)
        self.tof_center_fraction = float(self.get_parameter("tof_center_fraction").value)
        self.tof_scale_alpha = float(self.get_parameter("tof_scale_alpha").value)
        self.tof_stale_timeout_sec = float(
            self.get_parameter("tof_stale_timeout_sec").value
        )
        self.tof_requires_centered_track = bool(
            self.get_parameter("tof_requires_centered_track").value
        )
        self.tof_min_track_overlap_fraction = float(
            self.get_parameter("tof_min_track_overlap_fraction").value
        )
        self.tof_max_scale_jump_ratio = float(
            self.get_parameter("tof_max_scale_jump_ratio").value
        )
        self.default_depth_scale = float(self.get_parameter("default_depth_scale").value)
        self.min_scale = float(self.get_parameter("min_scale").value)
        self.max_scale = float(self.get_parameter("max_scale").value)
        self.depth_filter_alpha = float(self.get_parameter("depth_filter_alpha").value)
        self.depth_max_step_m = float(self.get_parameter("depth_max_step_m").value)
        self.method = str(self.get_parameter("model_name").value)
        self.filtered_scale = self.default_depth_scale

        requested_device = str(self.get_parameter("device").value)
        if requested_device == "cuda" and not torch.cuda.is_available():
            self.get_logger().warn("CUDA requested but unavailable; using CPU")
            requested_device = "cpu"
        self.device = torch.device(requested_device)

        model_name = str(self.get_parameter("model_name").value)
        self.get_logger().info(f"Loading depth model: {model_name} on {self.device}")
        self.processor = AutoImageProcessor.from_pretrained(model_name)
        self.model = AutoModelForDepthEstimation.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self.get_logger().info("Depth model loaded")

        self.create_subscription(Image, self.image_topic, self.image_cb, 10)
        self.create_subscription(TrackedPeople, self.tracks_topic, self.tracks_cb, 10)
        self.create_subscription(Range, self.tof_topic, self.tof_cb, 10)

        self.depth_pub = self.create_publisher(
            Image, self.get_parameter("depth_topic").value, 10
        )
        self.depth_viz_pub = self.create_publisher(
            Image, self.get_parameter("depth_viz_topic").value, 10
        )
        self.people_depth_pub = self.create_publisher(
            PeopleDepth, self.get_parameter("people_depth_topic").value, 10
        )

    def tracks_cb(self, msg):
        self.latest_tracks = msg

    def tof_cb(self, msg):
        if msg.min_range <= msg.range <= msg.max_range and np.isfinite(msg.range):
            self.latest_tof = float(msg.range)
            self.last_tof_time = time.monotonic()

    def should_run(self):
        if self.rate_hz <= 0.0:
            return True
        now = time.monotonic()
        if now - self.last_inference_time < 1.0 / self.rate_hz:
            return False
        self.last_inference_time = now
        return True

    def infer_depth(self, bgr_image):
        rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        pil_image = PILImage.fromarray(rgb_image)
        inputs = self.processor(images=pil_image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            predicted_depth = outputs.predicted_depth
            prediction = F.interpolate(
                predicted_depth.unsqueeze(1),
                size=bgr_image.shape[:2],
                mode="bicubic",
                align_corners=False,
            )

        return prediction.squeeze().detach().cpu().numpy().astype(np.float32)

    def median_valid(self, crop):
        valid = crop[np.isfinite(crop)]
        valid = valid[valid > 0.0]
        if valid.size == 0:
            return float("nan"), 0.0
        return float(np.median(valid)), float(valid.size / crop.size)

    def tof_is_fresh(self):
        if self.latest_tof is None:
            return False
        if self.last_tof_time is None:
            return False
        return time.monotonic() - self.last_tof_time <= self.tof_stale_timeout_sec

    def fallback_scale(self):
        if self.filtered_scale is not None and np.isfinite(self.filtered_scale):
            return float(self.filtered_scale)
        return float(self.default_depth_scale)

    def track_tof_overlap_fraction(self, track):
        frac = max(0.02, min(0.5, self.tof_center_fraction))
        beam_left = 0.5 - frac / 2.0
        beam_top = 0.5 - frac / 2.0
        beam_right = 0.5 + frac / 2.0
        beam_bottom = 0.5 + frac / 2.0

        roi = track.roi
        track_left = roi.x_offset - roi.width / 2.0
        track_top = roi.y_offset - roi.height / 2.0
        track_right = roi.x_offset + roi.width / 2.0
        track_bottom = roi.y_offset + roi.height / 2.0

        overlap_width = max(
            0.0,
            min(beam_right, track_right) - max(beam_left, track_left),
        )
        overlap_height = max(
            0.0,
            min(beam_bottom, track_bottom) - max(beam_top, track_top),
        )
        beam_area = max(frac * frac, 1e-6)
        return (overlap_width * overlap_height) / beam_area

    def has_centered_tof_track(self):
        if not self.tof_requires_centered_track:
            return True
        if self.latest_tracks is None:
            return False

        min_overlap = max(0.0, min(1.0, self.tof_min_track_overlap_fraction))
        return any(
            self.track_tof_overlap_fraction(track) >= min_overlap
            for track in self.latest_tracks.tracks
        )

    def update_tof_scale(self, depth_map):
        if not self.tof_is_fresh():
            return self.fallback_scale(), float("nan"), False
        if not self.has_centered_tof_track():
            return self.fallback_scale(), self.latest_tof, False

        h, w = depth_map.shape[:2]
        frac = max(0.02, min(0.5, self.tof_center_fraction))
        bw = int(w * frac)
        bh = int(h * frac)
        cx = w // 2
        cy = h // 2
        x1 = max(0, cx - bw // 2)
        y1 = max(0, cy - bh // 2)
        x2 = min(w, cx + bw // 2)
        y2 = min(h, cy + bh // 2)

        mono_center, conf = self.median_valid(depth_map[y1:y2, x1:x2])
        if conf <= 0.0 or not np.isfinite(mono_center) or mono_center <= 0.0:
            return self.fallback_scale(), self.latest_tof, False

        scale = self.latest_tof / mono_center
        if scale < self.min_scale or scale > self.max_scale:
            return self.fallback_scale(), self.latest_tof, False

        max_jump = max(1.0, self.tof_max_scale_jump_ratio)
        if self.scale_locked and self.filtered_scale is not None:
            jump = scale / max(self.filtered_scale, 1e-6)
            if jump > max_jump or jump < 1.0 / max_jump:
                return self.fallback_scale(), self.latest_tof, False

        if self.filtered_scale is None:
            self.filtered_scale = scale
        else:
            alpha = max(0.0, min(1.0, self.tof_scale_alpha))
            self.filtered_scale = (1.0 - alpha) * self.filtered_scale + alpha * scale

        self.scale_locked = True
        return self.filtered_scale, self.latest_tof, True

    def filter_track_depth(self, track_id, depth_m):
        if not np.isfinite(depth_m) or depth_m <= 0.0:
            return depth_m

        previous = self.filtered_depth_by_id.get(int(track_id))
        if previous is None or not np.isfinite(previous):
            filtered = float(depth_m)
        else:
            alpha = max(0.0, min(1.0, self.depth_filter_alpha))
            candidate = previous + alpha * (float(depth_m) - previous)
            max_step = max(0.0, self.depth_max_step_m)
            if max_step > 0.0:
                delta = max(-max_step, min(max_step, candidate - previous))
                filtered = previous + delta
            else:
                filtered = candidate

        self.filtered_depth_by_id[int(track_id)] = filtered
        return filtered

    def roi_to_bounds(self, roi, width, height):
        cx = roi.x_offset * width
        cy = roi.y_offset * height
        bw = roi.width * width
        bh = roi.height * height

        frac = max(0.1, min(1.0, self.roi_center_fraction))
        bw *= frac
        bh *= frac

        x1 = int(max(0, cx - bw / 2.0))
        y1 = int(max(0, cy - bh / 2.0))
        x2 = int(min(width, cx + bw / 2.0))
        y2 = int(min(height, cy + bh / 2.0))
        return x1, y1, x2, y2

    def estimate_track_depth(self, depth_map, roi):
        height, width = depth_map.shape[:2]
        x1, y1, x2, y2 = self.roi_to_bounds(roi, width, height)
        if x2 <= x1 or y2 <= y1:
            return float("nan"), 0.0
        return self.median_valid(depth_map[y1:y2, x1:x2])

    def publish_depth_images(self, depth_map, header):
        raw_msg = self.bridge.cv2_to_imgmsg(depth_map, encoding="32FC1")
        raw_msg.header = header
        self.depth_pub.publish(raw_msg)

        valid = depth_map[np.isfinite(depth_map)]
        if valid.size > 0:
            lo = float(np.percentile(valid, 2))
            hi = float(np.percentile(valid, 98))
            denom = max(hi - lo, 1e-6)
            norm = np.clip((depth_map - lo) / denom, 0.0, 1.0)
            viz = (255.0 * (1.0 - norm)).astype(np.uint8)
        else:
            viz = np.zeros(depth_map.shape, dtype=np.uint8)

        viz_msg = self.bridge.cv2_to_imgmsg(viz, encoding="mono8")
        viz_msg.header = header
        self.depth_viz_pub.publish(viz_msg)

    def publish_people_depth(self, depth_map, header):
        scale, tof_range, tof_used = self.update_tof_scale(depth_map)

        out = PeopleDepth()
        out.header = header

        if self.latest_tracks is not None:
            active_track_ids = set()
            for track in self.latest_tracks.tracks:
                active_track_ids.add(int(track.track_id))
                raw_depth_m, confidence = self.estimate_track_depth(depth_map, track.roi)
                corrected_depth_m = raw_depth_m * scale if np.isfinite(raw_depth_m) else raw_depth_m
                filtered_depth_m = self.filter_track_depth(
                    track.track_id,
                    corrected_depth_m,
                )

                item = PersonDepth()
                item.track_id = track.track_id
                item.roi = track.roi
                item.depth_m = float(filtered_depth_m)
                item.raw_depth_m = float(raw_depth_m)
                item.tof_range_m = float(tof_range)
                item.tof_scale = float(scale)
                item.tof_used = bool(tof_used)
                item.confidence = float(confidence)
                method_suffix = "+tof_scale" if tof_used else "+scale_hold"
                item.method = self.method + method_suffix + "+filtered"
                out.people.append(item)

            for track_id in list(self.filtered_depth_by_id):
                if track_id not in active_track_ids:
                    self.filtered_depth_by_id.pop(track_id, None)

        self.people_depth_pub.publish(out)

    def image_cb(self, msg):
        if not self.should_run():
            return

        bgr_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        depth_map = self.infer_depth(bgr_image)
        self.publish_depth_images(depth_map, msg.header)
        self.publish_people_depth(depth_map, msg.header)


def main():
    rclpy.init()
    node = DepthEstimatorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
