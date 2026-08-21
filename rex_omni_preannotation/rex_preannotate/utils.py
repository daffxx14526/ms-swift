"""通用工具：类别映射、bbox 转换、复核分档、Label Studio 导出。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def xyxy_to_xywh(box: List[float]) -> List[int]:
    """[x0, y0, x1, y1] -> 规范约定的 [x, y, w, h]（左上角 + 宽高，绝对像素）。"""
    x0, y0, x1, y1 = box
    return [int(round(x0)), int(round(y0)), int(round(x1 - x0)), int(round(y1 - y0))]


def clip_xyxy(box: List[float], width: int, height: int) -> List[float]:
    x0, y0, x1, y1 = box
    return [
        max(0.0, min(float(x0), width)),
        max(0.0, min(float(y0), height)),
        max(0.0, min(float(x1), width)),
        max(0.0, min(float(y1), height)),
    ]


@dataclass
class CategoryEntry:
    prompt: str
    label_cn: str
    group: str  # 'target' | 'evidence'
    phenomenon: Optional[str] = None


class CategoryMap:
    """加载 configs/categories.json，提供提示词列表与英文→中文映射。"""

    def __init__(self, config_path: str):
        raw = json.loads(Path(config_path).read_text(encoding='utf-8'))
        self.entries: Dict[str, CategoryEntry] = {}
        for item in raw.get('targets', []):
            self.entries[item['prompt']] = CategoryEntry(
                prompt=item['prompt'], label_cn=item['label_cn'], group='target')
        for item in raw.get('evidence', []):
            self.entries[item['prompt']] = CategoryEntry(
                prompt=item['prompt'], label_cn=item['label_cn'], group='evidence',
                phenomenon=item.get('phenomenon'))
        self.vehicle_labels_cn = set(raw.get('vehicle_labels_cn', ['机动车']))
        self.thresholds = raw.get('thresholds', {})
        self.phenomena = sorted({e.phenomenon for e in self.entries.values() if e.phenomenon})

    @property
    def prompts(self) -> List[str]:
        return list(self.entries.keys())

    def lookup(self, prompt: str) -> Optional[CategoryEntry]:
        """兼容模型输出的类别名与提示词大小写/首尾空白差异。"""
        key = prompt.strip()
        if key in self.entries:
            return self.entries[key]
        lowered = key.lower()
        for k, v in self.entries.items():
            if k.lower() == lowered:
                return v
        return None


def assess_review_priority(
    detections: List[dict],
    cat_map: CategoryMap,
    extra_high_reasons: Optional[List[str]] = None,
) -> Tuple[str, str, Dict[str, bool], int]:
    """按证据命中与车辆密度分档。

    返回 (priority, reason, evidence_hits, vehicle_count)。
    priority: '高' 全量精细复核 / '中' 全量快速复核 / '低' 抽检。
    """
    evidence_hits = {p: False for p in cat_map.phenomena}
    vehicle_count = 0
    for det in detections:
        if det['group'] == 'evidence' and det.get('phenomenon'):
            evidence_hits[det['phenomenon']] = True
        if det['label_cn'] in cat_map.vehicle_labels_cn:
            vehicle_count += 1

    reasons: List[str] = []
    hit_names = [p for p, hit in evidence_hits.items() if hit]
    if hit_names:
        reasons.append('检出事故证据: ' + '、'.join(hit_names))
    congestion_th = int(cat_map.thresholds.get('congestion_vehicle_count', 8))
    congested = vehicle_count >= congestion_th
    if congested:
        reasons.append(f'车辆密集({vehicle_count})疑似拥堵')
    if extra_high_reasons:
        reasons.extend(extra_high_reasons)

    if hit_names or extra_high_reasons:
        priority = '高'
    elif congested:
        priority = '中'
    else:
        priority = '低'
    return priority, '; '.join(reasons) if reasons else '无异常信号', evidence_hits, vehicle_count


def detections_to_labelstudio_task(
    image_rel_path: str,
    detections: List[dict],
    width: int,
    height: int,
) -> dict:
    """转 Label Studio 预标注导入格式（RectangleLabels，百分比坐标）。"""
    results = []
    for i, det in enumerate(detections):
        x, y, w, h = det['bbox_xywh']
        results.append({
            'id': f'det_{i}',
            'type': 'rectanglelabels',
            'from_name': 'label',
            'to_name': 'image',
            'original_width': width,
            'original_height': height,
            'value': {
                'x': x / width * 100.0,
                'y': y / height * 100.0,
                'width': w / width * 100.0,
                'height': h / height * 100.0,
                'rectanglelabels': [det['label_cn']],
            },
        })
    return {
        'data': {'image': image_rel_path},
        'predictions': [{'model_version': 'rex-omni-zeroshot', 'result': results}],
    }


def merge_time_windows(hit_secs: List[float], max_gap_sec: float) -> List[Tuple[float, float]]:
    """把离散命中时刻合并成连续时间窗（相邻命中间隔 <= max_gap_sec 视为同一窗）。"""
    if not hit_secs:
        return []
    secs = sorted(hit_secs)
    windows = [[secs[0], secs[0]]]
    for s in secs[1:]:
        if s - windows[-1][1] <= max_gap_sec:
            windows[-1][1] = s
        else:
            windows.append([s, s])
    return [(round(a, 2), round(b, 2)) for a, b in windows]
