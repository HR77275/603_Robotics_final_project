class Track:
    def __init__(self, track_id, roi):
        self.track_id = track_id
        self.roi = roi
        self.age = 1
        self.hits = 1
        self.missed_frames = 0

    @property
    def state(self):
        return "confirmed" if self.hits >= 2 else "tentative"


def roi_to_xyxy(roi):
    x1 = roi.x_offset - roi.width / 2.0
    y1 = roi.y_offset - roi.height / 2.0
    x2 = roi.x_offset + roi.width / 2.0
    y2 = roi.y_offset + roi.height / 2.0
    return x1, y1, x2, y2


def iou(a, b):
    ax1, ay1, ax2, ay2 = roi_to_xyxy(a)
    bx1, by1, bx2, by2 = roi_to_xyxy(b)

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter

    return inter / union if union > 0.0 else 0.0


class IoUTracker:
    def __init__(self, iou_threshold=0.25, max_missed=10):
        self.iou_threshold = iou_threshold
        self.max_missed = max_missed
        self.next_id = 1
        self.tracks = []

    def update(self, detections):
        unmatched_dets = set(range(len(detections)))
        unmatched_tracks = set(range(len(self.tracks)))
        matches = []

        pairs = []
        for ti, track in enumerate(self.tracks):
            for di, det in enumerate(detections):
                pairs.append((iou(track.roi, det), ti, di))

        pairs.sort(reverse=True)

        for score, ti, di in pairs:
            if score < self.iou_threshold:
                break
            if ti in unmatched_tracks and di in unmatched_dets:
                matches.append((ti, di))
                unmatched_tracks.remove(ti)
                unmatched_dets.remove(di)

        for ti, di in matches:
            track = self.tracks[ti]
            track.roi = detections[di]
            track.age += 1
            track.hits += 1
            track.missed_frames = 0

        for ti in unmatched_tracks:
            self.tracks[ti].age += 1
            self.tracks[ti].missed_frames += 1

        for di in unmatched_dets:
            self.tracks.append(Track(self.next_id, detections[di]))
            self.next_id += 1

        self.tracks = [t for t in self.tracks if t.missed_frames <= self.max_missed]
        return self.tracks
