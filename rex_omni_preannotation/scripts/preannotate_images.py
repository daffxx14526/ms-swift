#!/usr/bin/env python3
"""图片批量零样本预标注：Rex-Omni 检测 -> 规范 JSON 草稿 + 复核分档。

用法：
    python scripts/preannotate_images.py \
        --model-path ./models/Rex-Omni \
        --image-dir /data/traffic_images \
        --output-dir ./output/images \
        --backend transformers --batch-size 8 --vis --labelstudio
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rex_preannotate import (  # noqa: E402
    CategoryMap,
    RexPreannotator,
    assess_review_priority,
    detections_to_labelstudio_task,
)

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def collect_images(image_dir: Path):
    return sorted(p for p in image_dir.rglob('*') if p.suffix.lower() in IMAGE_EXTS)


def visualize(image: Image.Image, detections, out_path: Path):
    """按类别分组转 RexOmniVisualize 需要的 predictions 结构后画框。"""
    from rex_omni import RexOmniVisualize
    predictions = {}
    for det in detections:
        label = det['label_cn']
        predictions.setdefault(label, []).append(
            {'type': 'box', 'coords': det['bbox_xyxy']})
    vis = RexOmniVisualize(
        image=image, predictions=predictions,
        font_size=18, draw_width=4, show_labels=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vis.save(str(out_path))


def main():
    parser = argparse.ArgumentParser(description='Rex-Omni 图片批量预标注')
    parser.add_argument('--model-path', required=True, help='本地模型目录')
    parser.add_argument('--image-dir', required=True, help='待标注图片目录（递归扫描）')
    parser.add_argument('--output-dir', required=True, help='输出目录')
    parser.add_argument('--categories', default=str(
        Path(__file__).resolve().parent.parent / 'configs' / 'categories.json'))
    parser.add_argument('--backend', choices=['transformers', 'vllm'], default='transformers')
    parser.add_argument('--quantization', default=None, help="AWQ 量化版填 'awq'（需 vllm 后端）")
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--vis', action='store_true', help='输出画框可视化图')
    parser.add_argument('--labelstudio', action='store_true',
                        help='输出 Label Studio 预标注导入文件')
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    output_dir = Path(args.output_dir)
    json_dir = output_dir / 'json'
    json_dir.mkdir(parents=True, exist_ok=True)

    images = collect_images(image_dir)
    if not images:
        print(f'未在 {image_dir} 找到图片', file=sys.stderr)
        sys.exit(1)
    print(f'共 {len(images)} 张图片待预标注')

    cat_map = CategoryMap(args.categories)
    engine = RexPreannotator(
        model_path=args.model_path,
        cat_map=cat_map,
        backend=args.backend,
        quantization=args.quantization,
    )

    ls_tasks = []
    summary = {'高': 0, '中': 0, '低': 0}

    for start in tqdm(range(0, len(images), args.batch_size), desc='预标注'):
        batch_paths = images[start:start + args.batch_size]
        batch_images = [Image.open(p).convert('RGB') for p in batch_paths]
        batch_detections = engine.detect_batch(batch_images)

        for path, image, detections in zip(batch_paths, batch_images, batch_detections):
            priority, reason, evidence_hits, vehicle_count = assess_review_priority(
                detections, cat_map)
            summary[priority] += 1

            record = {
                'image': str(path.relative_to(image_dir)),
                'width': image.width,
                'height': image.height,
                'detections': detections,
                'evidence_hits': evidence_hits,
                'vehicle_count': vehicle_count,
                'review_priority': priority,
                'review_reason': reason,
            }
            out_json = json_dir / (path.stem + '.json')
            out_json.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')

            if args.labelstudio:
                ls_tasks.append(detections_to_labelstudio_task(
                    record['image'], detections, image.width, image.height))
            if args.vis:
                visualize(image, detections, output_dir / 'vis' / (path.stem + '_vis.jpg'))

    if args.labelstudio:
        ls_path = output_dir / 'labelstudio_tasks.json'
        ls_path.write_text(
            json.dumps(ls_tasks, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Label Studio 导入文件: {ls_path}')

    print(f'完成。复核分档统计: 高={summary["高"]} 中={summary["中"]} 低={summary["低"]}')
    print(f'JSON 草稿目录: {json_dir}')


if __name__ == '__main__':
    main()
