# Rex-Omni 交通场景零样本预标注工具库

基于 [IDEA-Research/Rex-Omni](https://github.com/IDEA-Research/Rex-Omni)（3B MLLM，零样本开放词汇检测）的
**交通监控预标注专用**代码库，实现 `zero_shot_preannotation_plan.md` 中的检测层流水线：

- **图片**：批量零样本检测 → 规范 JSON 草稿（`[x,y,w,h]` 绝对像素）+ 复核分档 + 可选 Label Studio 导入格式 / 可视化；
- **视频**：抽帧 → 逐帧检测 → IoU 轨迹关联 → 静止车辆轨迹 + 现象时间窗草稿（`start_sec/end_sec`）。

模型采用**下载到本地后离线加载**的方式，不依赖运行时联网。

---

## 1. 环境安装

```bash
# 1) 创建环境（Rex-Omni 官方要求 python 3.10）
conda create -n rexomni python=3.10 -y
conda activate rexomni

# 2) 安装 PyTorch（按你的 CUDA 版本选择，官方示例为 cu128）
pip install torch==2.7.0 torchvision --index-url https://download.pytorch.org/whl/cu128

# 3) 安装 Rex-Omni 官方包（源码安装）
git clone https://github.com/IDEA-Research/Rex-Omni.git
cd Rex-Omni
pip install -r requirements.txt
pip install -v -e .
cd ..

# 4) 安装本工具库依赖
cd rex_omni_preannotation
pip install -r requirements.txt

# 5)（可选，强烈推荐用于批量预标注提速）安装 vLLM
pip install vllm
```

## 2. 下载模型到本地

```bash
# 从 HuggingFace 下载（国内网络可加 --hf-mirror 走 hf-mirror.com）
python scripts/download_model.py --source hf --local-dir ./models/Rex-Omni

# 或从 ModelScope 下载
python scripts/download_model.py --source modelscope --local-dir ./models/Rex-Omni

# 显存紧张可下载 AWQ 量化版（省 50% 显存，需 vllm 后端 + quantization awq）
python scripts/download_model.py --source hf --repo IDEA-Research/Rex-Omni-AWQ --local-dir ./models/Rex-Omni-AWQ
```

下载完成后，后续所有脚本通过 `--model-path ./models/Rex-Omni` 离线加载本地权重。

## 3. 图片批量预标注

```bash
python scripts/preannotate_images.py \
    --model-path ./models/Rex-Omni \
    --image-dir /data/traffic_images \
    --output-dir ./output/images \
    --backend transformers \
    --batch-size 8 \
    --vis \
    --labelstudio
```

主要参数：

| 参数 | 说明 |
|---|---|
| `--model-path` | 本地模型目录（必填） |
| `--image-dir` | 待标注图片目录（jpg/png，递归扫描） |
| `--output-dir` | 输出目录 |
| `--backend` | `transformers`（默认）或 `vllm`（批量提速） |
| `--categories` | 类别映射表路径，默认 `configs/categories.json` |
| `--batch-size` | 每批送入模型的图片数 |
| `--vis` | 额外输出画框可视化图（`output/images/vis/`） |
| `--labelstudio` | 额外输出 Label Studio 预标注导入文件 `labelstudio_tasks.json` |
| `--quantization` | AWQ 量化版填 `awq`（须配合 `--backend vllm`） |

**输出**（每张图一个 JSON，`output/images/json/<图名>.json`）：

```json
{
  "image": "cam01_0001.jpg",
  "width": 1920, "height": 1080,
  "detections": [
    {"label_en": "car", "label_cn": "机动车", "group": "target",
     "bbox_xywh": [120, 340, 80, 60], "bbox_xyxy": [120, 340, 200, 400]}
  ],
  "evidence_hits": {"侧翻": false, "起火": false, "散落物": true, "人员倒地": false},
  "vehicle_count": 9,
  "review_priority": "高",
  "review_reason": "检出事故证据: 散落物; 车辆密集(9)疑似拥堵"
}
```

## 4. 视频预标注

```bash
python scripts/preannotate_video.py \
    --model-path ./models/Rex-Omni \
    --video /data/videos/cam01_20260821.mp4 \
    --output-dir ./output/videos \
    --sample-fps 1 \
    --backend vllm \
    --save-evidence-frames
```

主要参数：

| 参数 | 说明 |
|---|---|
| `--video` | 单个视频文件；或 `--video-dir` 批量处理目录 |
| `--sample-fps` | 抽帧频率（默认 1 fps；确认异常后可对片段用 2–5 fps 重跑） |
| `--save-evidence-frames` | 保存命中证据类别的帧（画框），便于人工快速定位 |

**输出**（每个视频一个 JSON）：

```json
{
  "video": "cam01_20260821.mp4",
  "duration_sec": 300.0, "sample_fps": 1.0,
  "tracks": [
    {"track_id": 3, "label_cn": "机动车", "start_sec": 8.0, "end_sec": 120.0,
     "is_static": true, "static_since_sec": 12.0,
     "boxes": [{"sec": 8.0, "bbox_xywh": [500, 400, 90, 70]}, ...]}
  ],
  "evidence_windows": [
    {"phenomenon": "散落物", "start_sec": 11.0, "end_sec": 45.0,
     "example_bbox_xywh": [430, 500, 60, 30]}
  ],
  "static_vehicle_summary": {"count": 2, "earliest_sec": 12.0},
  "review_priority": "高",
  "review_reason": "证据窗: 散落物[11.0,45.0]; 静止车辆轨迹 2 条"
}
```

`evidence_windows` 与 `tracks` 的时间字段直接对齐视频标注规范
（`accident_annotation_spec_video.md`）的 `start_sec/end_sec` 约定，
人工复核时以此为初值校正时间窗边界。

## 5. 复核分档规则（内置）

Rex-Omni 不输出置信度分数，分档基于**证据命中与目标密度**（可在 `rex_preannotate/utils.py` 调整阈值）：

| 档位 | 触发条件 | 建议人工处理 |
|---|---|---|
| 高 | 命中任一证据类（侧翻/起火/冒烟/散落物/人员倒地/锥桶三角牌）或视频出现静止车辆轨迹 | 全量精细复核 |
| 中 | 车辆数 ≥ 8（疑似拥堵，困难负样本） | 全量快速复核 |
| 低 | 其余 | 抽检 10% |

如需双模型交叉验证（Rex-Omni + MM-Grounding-DINO），参见 `zero_shot_preannotation_plan.md` 第 1 节，本库预留了 `detections` 通用格式便于合并。

## 6. 目录结构

```
rex_omni_preannotation/
├── README.md
├── requirements.txt
├── configs/
│   └── categories.json          # 英文提示词 → 中文类别映射（目标类 + 证据类）
├── rex_preannotate/
│   ├── __init__.py
│   ├── engine.py                # RexOmniWrapper 封装（本地加载、分批推理、结果标准化）
│   ├── tracker.py               # 轻量 IoU 贪心跟踪器（视频轨迹关联，零训练）
│   └── utils.py                 # bbox 转换、类别映射、复核分档、Label Studio 导出
└── scripts/
    ├── download_model.py        # HF / ModelScope 模型下载
    ├── preannotate_images.py    # 图片批量预标注
    └── preannotate_video.py     # 视频预标注（抽帧+跟踪+时间窗）
```

## 7. 常见问题

- **显存需求**：Rex-Omni 为 3B 模型，transformers 后端 bf16 约需 8–10 GB 显存；AWQ 量化版约减半。
- **速度**：transformers 后端单图约 1–3 s；批量预标注建议 `--backend vllm`（吞吐提升数倍）。
- **类别定制**：编辑 `configs/categories.json` 即可增删检测类别（英文短语召回更好），无需改代码。
- **与规范对接**：本库输出的是**检测层草稿**；认知层字段草稿（现象/事件分类）由 Qwen3-VL 按
  `zero_shot_preannotation_plan.md` 第 2 节另行生成后合并。
