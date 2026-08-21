#!/usr/bin/env python3
"""视频零样本预标注：抽帧 -> Rex-Omni 逐帧检测 -> IoU 轨迹关联 ->
静止车辆轨迹 + 现象时间窗草稿（对齐视频标注规范的 start_sec/end_sec）。

用法：
    python scripts/preannotate_video.py \
        --model-path ./models/Rex-Omni \
        --video /data/videos/cam01.mp4 \
        --output-dir ./output/videos \
        --sample-fps 1 --backend vllm --save-evidence-frames
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
from PIL import Image
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rex_preannotate import CategoryMap, IouTracker, RexPreannotator  # noqa: E402
from rex_preannotate.tracker import analyze_static_tracks  # noqa: E402
from rex_preannotate.utils import merge_time_windows  # noqa: E402

VIDEO_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.ts'}


def sample_frames(video_path: Path, sample_fps: float):
    """按 sample_fps 抽帧，yield (sec, PIL.Image)。"""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f'无法打开视频: {video_path}')
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / native_fps if native_fps > 0 else 0.0
    step = max(1, int(round(native_fps / sample_fps)))

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % step == 0:
            sec = round(frame_idx / native_fps, 2)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            yield sec, Image.fromarray(rgb)
        frame_idx += 1
    cap.release()
    return duration


def draw_and_save(image: Image.Image, detections, out_path: Path):
    import numpy as np
    frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    for det in detections:
        x0, y0, x1, y1 = [int(v) for v in det['bbox_xyxy']]
        color = (0, 0, 255) if det['group'] == 'evidence' else (0, 200, 0)
        cv2.rectangle(frame, (x0, y0), (x1, y1), color, 2)
        cv2.putText(frame, det['label_en'], (x0, max(0, y0 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)


def process_video(video_path: Path, engine: RexPreannotator, cat_map: CategoryMap,
                  output_dir: Path, sample_fps: float, batch_size: int,
                  save_evidence_frames: bool):
    cap = cv2.VideoCapture(str(video_path))
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = round(total_frames / native_fps, 2) if native_fps > 0 else 0.0
    cap.release()

    tracker = IouTracker()
    # phenomenon -> [(sec, bbox_xywh), ...]
    evidence_hits = {}

    frames = list(sample_frames(video_path, sample_fps))
    for start in tqdm(range(0, len(frames), batch_size), desc=video_path.name):
        batch = frames[start:start + batch_size]
        batch_detections = engine.detect_batch([img for _, img in batch])
        for (sec, image), detections in zip(batch, batch_detections):
            tracker.update(sec, detections)
            frame_has_evidence = False
            for det in detections:
                if det['group'] == 'evidence' and det.get('phenomenon'):
                    evidence_hits.setdefault(det['phenomenon'], []).append(
                        (sec, det['bbox_xywh']))
                    frame_has_evidence = True
            if save_evidence_frames and frame_has_evidence:
                draw_and_save(
                    image, detections,
                    output_dir / 'evidence_frames' / video_path.stem / f'{sec:08.2f}s.jpg')

    tracks = tracker.close()
    th = cat_map.thresholds
    static_tracks = analyze_static_tracks(
        tracks,
        min_duration_sec=float(th.get('static_track_min_duration_sec', 10.0)),
        center_shift_ratio=float(th.get('static_center_shift_ratio', 0.3)),
        vehicle_labels_cn=cat_map.vehicle_labels_cn,
    )
    static_ids = {t['track_id'] for t in static_tracks}

    # 相邻命中间隔容忍 2 个采样周期，避免单帧漏检打断时间窗
    max_gap = 2.0 / sample_fps
    evidence_windows = []
    for phenomenon, hits in sorted(evidence_hits.items()):
        for w_start, w_end in merge_time_windows([s for s, _ in hits], max_gap):
            example_bbox = next(b for s, b in hits if w_start <= s <= w_end)
            evidence_windows.append({
                'phenomenon': phenomenon,
                'start_sec': w_start,
                'end_sec': w_end,
                'example_bbox_xywh': example_bbox,
            })

    reasons = []
    if evidence_windows:
        reasons.append('证据窗: ' + '; '.join(
            f'{w["phenomenon"]}[{w["start_sec"]},{w["end_sec"]}]' for w in evidence_windows))
    if static_tracks:
        reasons.append(f'静止车辆轨迹 {len(static_tracks)} 条')
    priority = '高' if reasons else '低'

    track_records = []
    for t in tracks:
        boxes = t['boxes']
        static_info = next((s for s in static_tracks if s['track_id'] == t['track_id']), None)
        track_records.append({
            'track_id': t['track_id'],
            'label_cn': t['label_cn'],
            'start_sec': boxes[0]['sec'],
            'end_sec': boxes[-1]['sec'],
            'is_static': t['track_id'] in static_ids,
            'static_since_sec': static_info['static_since_sec'] if static_info else None,
            'boxes': [{'sec': b['sec'], 'bbox_xywh': b['bbox_xywh']} for b in boxes],
        })

    record = {
        'video': video_path.name,
        'duration_sec': duration,
        'sample_fps': sample_fps,
        'tracks': track_records,
        'evidence_windows': evidence_windows,
        'static_vehicle_summary': {
            'count': len(static_tracks),
            'earliest_sec': min((t['static_since_sec'] for t in static_tracks), default=None),
        },
        'review_priority': priority,
        'review_reason': '; '.join(reasons) if reasons else '无异常信号',
    }

    out_json = output_dir / 'json' / (video_path.stem + '.json')
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{video_path.name}: priority={priority}, tracks={len(track_records)}, '
          f'evidence_windows={len(evidence_windows)} -> {out_json}')


def main():
    parser = argparse.ArgumentParser(description='Rex-Omni 视频预标注')
    parser.add_argument('--model-path', required=True, help='本地模型目录')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--video', help='单个视频文件')
    group.add_argument('--video-dir', help='视频目录（批量）')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--categories', default=str(
        Path(__file__).resolve().parent.parent / 'configs' / 'categories.json'))
    parser.add_argument('--backend', choices=['transformers', 'vllm'], default='transformers')
    parser.add_argument('--quantization', default=None, help="AWQ 量化版填 'awq'（需 vllm 后端）")
    parser.add_argument('--attn-impl', default=None,
                        help="transformers 后端注意力实现；未安装 flash-attn 时填 'sdpa'")
    parser.add_argument('--sample-fps', type=float, default=1.0, help='抽帧频率（默认 1 fps）')
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--save-evidence-frames', action='store_true',
                        help='保存命中证据类别的帧（画框）')
    args = parser.parse_args()

    if args.video:
        videos = [Path(args.video)]
    else:
        videos = sorted(p for p in Path(args.video_dir).rglob('*')
                        if p.suffix.lower() in VIDEO_EXTS)
    if not videos:
        print('未找到视频文件', file=sys.stderr)
        sys.exit(1)
    print(f'共 {len(videos)} 个视频待预标注')

    cat_map = CategoryMap(args.categories)
    engine_kwargs = {}
    if args.attn_impl:
        engine_kwargs['attn_implementation'] = args.attn_impl
    engine = RexPreannotator(
        model_path=args.model_path,
        cat_map=cat_map,
        backend=args.backend,
        quantization=args.quantization,
        **engine_kwargs,
    )

    output_dir = Path(args.output_dir)
    for video_path in videos:
        process_video(video_path, engine, cat_map, output_dir,
                      args.sample_fps, args.batch_size, args.save_evidence_frames)


if __name__ == '__main__':
    main()
