"""轻量 IoU 贪心多目标跟踪器（零训练，用于视频预标注的轨迹关联）。

仅依赖检测框输入，按"同类别 + IoU 最大 + 超过阈值"逐帧贪心匹配。
预标注场景对轨迹质量要求低于在线跟踪（有人工复核兜底），
若需更强的跟踪（遮挡恢复、运动预测），可替换为 ByteTrack / BoT-SORT。
"""

from __future__ import annotations

from typing import Dict, List


def _iou(a: List[float], b: List[float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


class IouTracker:

    def __init__(self, iou_threshold: float = 0.3, max_missed_frames: int = 3):
        self.iou_threshold = iou_threshold
        self.max_missed_frames = max_missed_frames
        self._next_id = 1
        # active track: {track_id, label_cn, boxes: [{sec, bbox_xyxy, bbox_xywh}], missed}
        self._active: List[dict] = []
        self.finished: List[dict] = []

    def update(self, sec: float, detections: List[dict]) -> None:
        """喂入一帧的检测结果（只跟踪 group == 'target' 的目标）。"""
        dets = [d for d in detections if d['group'] == 'target']
        unmatched = list(range(len(dets)))

        for track in self._active:
            best_iou, best_j = 0.0, -1
            last_box = track['boxes'][-1]['bbox_xyxy']
            for j in unmatched:
                if dets[j]['label_cn'] != track['label_cn']:
                    continue
                iou = _iou(last_box, dets[j]['bbox_xyxy'])
                if iou > best_iou:
                    best_iou, best_j = iou, j
            if best_j >= 0 and best_iou >= self.iou_threshold:
                d = dets[best_j]
                track['boxes'].append(
                    {'sec': sec, 'bbox_xyxy': d['bbox_xyxy'], 'bbox_xywh': d['bbox_xywh']})
                track['missed'] = 0
                unmatched.remove(best_j)
            else:
                track['missed'] += 1

        still_active = []
        for track in self._active:
            if track['missed'] > self.max_missed_frames:
                self.finished.append(track)
            else:
                still_active.append(track)
        self._active = still_active

        for j in unmatched:
            d = dets[j]
            self._active.append({
                'track_id': self._next_id,
                'label_cn': d['label_cn'],
                'boxes': [{'sec': sec, 'bbox_xyxy': d['bbox_xyxy'], 'bbox_xywh': d['bbox_xywh']}],
                'missed': 0,
            })
            self._next_id += 1

    def close(self) -> List[dict]:
        """结束跟踪，返回全部轨迹（按出现时间排序）。"""
        self.finished.extend(self._active)
        self._active = []
        for t in self.finished:
            t.pop('missed', None)
        return sorted(self.finished, key=lambda t: t['boxes'][0]['sec'])


def analyze_static_tracks(
    tracks: List[dict],
    min_duration_sec: float,
    center_shift_ratio: float,
    vehicle_labels_cn: set,
) -> List[Dict]:
    """找出"长时间静止的车辆轨迹"（事故/故障停驶候选）。

    判定：轨迹持续 >= min_duration_sec，且中心点最大位移 < center_shift_ratio * 框对角线。
    """
    static_tracks = []
    for track in tracks:
        if track['label_cn'] not in vehicle_labels_cn:
            continue
        boxes = track['boxes']
        duration = boxes[-1]['sec'] - boxes[0]['sec']
        if duration < min_duration_sec or len(boxes) < 2:
            continue
        first = boxes[0]['bbox_xyxy']
        diag = ((first[2] - first[0]) ** 2 + (first[3] - first[1]) ** 2) ** 0.5
        cx0 = (first[0] + first[2]) / 2
        cy0 = (first[1] + first[3]) / 2
        max_shift = 0.0
        for b in boxes[1:]:
            bb = b['bbox_xyxy']
            cx = (bb[0] + bb[2]) / 2
            cy = (bb[1] + bb[3]) / 2
            shift = ((cx - cx0) ** 2 + (cy - cy0) ** 2) ** 0.5
            max_shift = max(max_shift, shift)
        if diag > 0 and max_shift < center_shift_ratio * diag:
            static_tracks.append({
                'track_id': track['track_id'],
                'label_cn': track['label_cn'],
                'static_since_sec': boxes[0]['sec'],
                'static_until_sec': boxes[-1]['sec'],
                'duration_sec': round(duration, 2),
            })
    return static_tracks
