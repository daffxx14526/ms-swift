"""RexOmniWrapper 封装：本地权重加载、分批推理、输出标准化为通用 detections 格式。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PIL import Image

from .utils import CategoryMap, clip_xyxy, xyxy_to_xywh


class RexPreannotator:

    def __init__(
        self,
        model_path: str,
        cat_map: CategoryMap,
        backend: str = 'transformers',
        quantization: Optional[str] = None,
        max_tokens: int = 2048,
        **backend_kwargs,
    ):
        model_dir = Path(model_path)
        if not model_dir.exists():
            raise FileNotFoundError(
                f'本地模型目录不存在: {model_path}\n'
                '请先运行 scripts/download_model.py 下载模型权重。')

        from rex_omni import RexOmniWrapper

        kwargs = dict(
            model_path=str(model_dir),
            backend=backend,
            max_tokens=max_tokens,
            temperature=0.0,
            top_p=0.05,
            top_k=1,
            repetition_penalty=1.05,
        )
        if quantization:
            kwargs['quantization'] = quantization
        kwargs.update(backend_kwargs)
        self.rex = RexOmniWrapper(**kwargs)
        self.cat_map = cat_map

    def detect_batch(self, images: List[Image.Image]) -> List[List[dict]]:
        """对一批 PIL 图片做零样本检测。

        返回与输入等长的列表，每项是该图的 detections：
        [{label_en, label_cn, group, phenomenon, bbox_xyxy, bbox_xywh}, ...]
        """
        results = self.rex.inference(
            images=images, task='detection', categories=self.cat_map.prompts)

        all_detections: List[List[dict]] = []
        for image, result in zip(images, results):
            detections: List[dict] = []
            if result.get('success', True):
                preds = result.get('extracted_predictions') or {}
                for category, items in preds.items():
                    entry = self.cat_map.lookup(category)
                    if entry is None:
                        continue
                    for item in items or []:
                        if item.get('type') != 'box':
                            continue
                        coords = item.get('coords')
                        if not coords or len(coords) != 4:
                            continue
                        xyxy = clip_xyxy(coords, image.width, image.height)
                        if xyxy[2] <= xyxy[0] or xyxy[3] <= xyxy[1]:
                            continue
                        detections.append({
                            'label_en': entry.prompt,
                            'label_cn': entry.label_cn,
                            'group': entry.group,
                            'phenomenon': entry.phenomenon,
                            'bbox_xyxy': [round(v, 1) for v in xyxy],
                            'bbox_xywh': xyxy_to_xywh(xyxy),
                        })
            all_detections.append(detections)
        return all_detections
