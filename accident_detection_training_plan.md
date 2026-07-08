# 基于 Qwen3-VL 的路侧监控交通事故检测多任务训练方案

> 目标：训练一个不仅能做事故二分类，还具备交通场景理解能力的多模态模型，
> 重点解决"拥堵误报为事故""双闪临停误报为事故""遮挡型事故漏检"等边界问题。

---

## 目录

1. [整体流程](#1-整体流程)
2. [结构化属性标注规范](#2-结构化属性标注规范)
3. [多任务训练样本自动生成](#3-多任务训练样本自动生成)
4. [数据配比与困难样本要求](#4-数据配比与困难样本要求)
5. [模型训练](#5-模型训练)
6. [分桶评估体系](#6-分桶评估体系)
7. [错误分析与迭代](#7-错误分析与迭代)
8. [附录：Prompt 模板汇总](#8-附录prompt-模板汇总)

---

## 1. 整体流程

```text
原始视频
   ↓
结构化属性标注（12 个核心字段）
   ↓
自动生成多任务训练样本
   ├─ 任务A 属性感知（场景/交通流/双闪/异常停车）
   ├─ 任务B 证据判断（碰撞/避让/双闪原因）
   ├─ 任务C 对比判别（事故/拥堵/临停/近距离 四选一）
   ├─ 任务D 步骤化推理（证据 → 结论）
   └─ 任务E 部署格式（只回答 是/否）
   ↓
按配比混合 + 困难样本 ≥ 30%
   ↓
LoRA 多任务 SFT（可选两阶段 / GRPO）
   ↓
分桶评估（困难子集 recall/precision + 辅助任务准确率）
   ↓
错误分析 → 补充对应对比对 → 迭代
```

---

## 2. 结构化属性标注规范

### 2.1 十二个核心字段

每个视频标注一条 JSON 记录：

```json
{
  "video_path": "/data/videos/xxx.mp4",

  "scene": "隧道",
  "traffic_flow": "拥堵",
  "congestion": "是",

  "hazard_light": "是",
  "hazard_light_reason": "拥堵/临停",
  "close_distance": "是",
  "near_miss": "否",

  "collision_visible": "否",
  "collision_occluded": "否",
  "occlusion_type": "无遮挡",
  "abnormal_stop": "否",

  "accident": "否"
}
```

### 2.2 字段取值定义

| 字段 | 取值枚举 | 说明 |
|---|---|---|
| `scene` | 城市路口 / 普通城市道路 / 高架高速 / 隧道 / 匝道 / 其他 | 道路场景 |
| `traffic_flow` | 畅通 / 缓行 / 拥堵 / 停止排队 / 某点中断 | 比 congestion 更细；"某点中断"是事故的重要信号 |
| `congestion` | 是 / 否 | 是否存在明显拥堵 |
| `hazard_light` | 是 / 否 | 是否有车辆开启双闪 |
| `hazard_light_reason` | 事故后 / 拥堵缓行 / 临时停车 / 故障或施工 / 无双闪 / 不明确 | 双闪原因，区分误报的关键 |
| `close_distance` | 是 / 否 | 是否存在两车近距离 |
| `near_miss` | 是 / 否 | 是否险情但未碰撞（急刹/擦肩而过） |
| `collision_visible` | 是 / 否 | 画面中是否可直接看到碰撞过程 |
| `collision_occluded` | 是 / 否 | 碰撞点是否被遮挡（事故存在但看不到碰撞点） |
| `occlusion_type` | 无遮挡 / 事故车自身遮挡 / 其他车辆遮挡 / 设施遮挡 / 画面边缘盲区 | 遮挡类型 |
| `abnormal_stop` | 是 / 否 | 是否有车辆异常停止（停在行车道中间/斜停/横跨车道） |
| `accident` | 是 / 否 | 最终事故标签 |

### 2.3 标注一致性规则

1. **标签统一**：所有是/否字段只允许"是"或"否"，禁止"有/没有/正常/发生"等变体；
2. **正样本准入**：`accident=是` 的样本必须满足以下之一：
   - `collision_visible=是`（碰撞过程可见）；
   - `collision_occluded=是` 且存在间接证据（异常停止/避让/交通流中断）；
3. **噪声剔除**：事故完全发生在视野盲区、画面中无任何证据的样本，**不进入训练集**（模型无法学习无证据的判断）；
4. **困难样本打标**：满足以下任一条件的样本额外标记 `hard=true`：
   - `congestion=是 且 accident=否`（拥堵负样本）
   - `hazard_light=是 且 accident=否`（双闪负样本）
   - `near_miss=是`（险情负样本）
   - `collision_occluded=是 且 accident=是`（遮挡事故正样本）
   - `collision_visible=否 且 accident=是`（不明显事故正样本）

---

## 3. 多任务训练样本自动生成

同一个视频依据结构化属性自动生成多条训练样本。
所有样本统一为 ms-swift 标准 messages 格式。

### 3.1 任务A：属性感知（低层语义）

**作用**：让模型先"看懂"基础交通要素。

#### A1 场景分类

```json
{
  "messages": [
    {"role": "user", "content": "<video>请判断该视频的道路场景类型。候选：城市路口、普通城市道路、高架高速、隧道、匝道、其他。只输出一个类别。"},
    {"role": "assistant", "content": "隧道"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案来源：`scene` 字段。

#### A2 交通流状态

```json
{
  "messages": [
    {"role": "user", "content": "<video>请判断视频中的交通流状态。候选：畅通、缓行、拥堵、停止排队、某点中断。只输出一个类别。"},
    {"role": "assistant", "content": "拥堵"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案来源：`traffic_flow` 字段。

#### A3 双闪检测

```json
{
  "messages": [
    {"role": "user", "content": "<video>视频中是否有车辆开启双闪灯？只回答\"是\"或\"否\"。"},
    {"role": "assistant", "content": "是"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案来源：`hazard_light` 字段。

#### A4 异常停止检测

```json
{
  "messages": [
    {"role": "user", "content": "<video>视频中是否有车辆异常停止（停在行车道中间、斜停、横跨车道）？只回答\"是\"或\"否\"。"},
    {"role": "assistant", "content": "否"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案来源：`abnormal_stop` 字段。

### 3.2 任务B：证据判断（中层语义）

**作用**：让模型学会识别事故的直接与间接证据。

#### B1 可见碰撞判断

```json
{
  "messages": [
    {"role": "user", "content": "<video>视频中是否出现可直接看到的车辆碰撞、剐蹭或撞击过程？只回答\"是\"或\"否\"。"},
    {"role": "assistant", "content": "否"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案来源：`collision_visible`。

#### B2 避让行为判断

```json
{
  "messages": [
    {"role": "user", "content": "<video>视频中是否存在周围车辆明显避让、绕行某一固定区域的行为？只回答\"是\"或\"否\"。"},
    {"role": "assistant", "content": "否"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案来源：由标注员标注或从 `abnormal_stop`/事故后行为推导。

#### B3 双闪原因判断

```json
{
  "messages": [
    {"role": "user", "content": "<video>视频中车辆开启双闪灯的最可能原因是什么？候选：事故后、拥堵缓行、临时停车、故障或施工、无法判断。只输出一项。"},
    {"role": "assistant", "content": "拥堵缓行"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案来源：`hazard_light_reason`。仅当 `hazard_light=是` 时生成此样本。

### 3.3 任务C：对比判别（类间边界，最关键）

**作用**：直接教模型区分四种最易混淆的情况。

```json
{
  "messages": [
    {"role": "user", "content": "<video>该视频最符合以下哪种情况？\nA. 发生了交通事故\nB. 交通拥堵但没有事故\nC. 车辆正常临停并开启双闪\nD. 车辆近距离通过但没有碰撞\n只输出选项字母。"},
    {"role": "assistant", "content": "B"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案映射规则：

| 属性条件 | 答案 |
|---|---|
| `accident=是` | A |
| `accident=否 且 congestion=是` | B |
| `accident=否 且 hazard_light=是 且 hazard_light_reason=临时停车` | C |
| `accident=否 且 (close_distance=是 或 near_miss=是)` | D |

> 注意：一个视频若同时满足多个负样本条件（如既拥堵又有双闪），
> 选择最主要特征作为答案，或生成时跳过有歧义的样本。

### 3.4 任务D：步骤化推理（高层语义）

**作用**：训练"证据 → 结论"的推理链条，提升理解上限。

```json
{
  "messages": [
    {"role": "user", "content": "<video>请按以下步骤分析并判断是否发生交通事故：\n1. 场景与交通流状态；\n2. 关键车辆行为（停止、双闪、避让、轨迹突变）；\n3. 是否存在碰撞或碰撞的间接证据；\n4. 结论（是/否）。"},
    {"role": "assistant", "content": "1. 隧道内，车流缓行并排队；\n2. 多辆车开启双闪，但均随车流缓慢移动，无车辆异常停在车道中间；\n3. 未观察到碰撞、剐蹭，也没有避让行为或交通流在某点突然中断；\n4. 结论：否"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

**推理文本生成规则**（由结构化属性模板化生成 + 人工抽检）：

```text
第1步 = scene + traffic_flow 描述
第2步 = hazard_light / abnormal_stop / close_distance / 避让 的组合描述
第3步 = collision_visible / collision_occluded / 间接证据 描述
第4步 = accident 标签
```

**关键判别点必须写入答案**，例如：

- 拥堵负样本："车流整体缓行、连续移动，没有固定中断点"
- 事故正样本："交通流在某点中断，事故车辆静止，后方车辆绕行"
- 临停负样本："车辆平稳减速靠边，车身端正，停在合理位置"
- 事故停车正样本："车辆急停/偏转后停止，姿态歪斜，位置异常"
- 遮挡事故正样本："碰撞点被遮挡，但两车接近后异常停止，周围车辆避让"

### 3.5 任务E：部署格式（输出稳定性）

**作用**：保证线上单轮推理输出稳定。

```json
{
  "messages": [
    {"role": "user", "content": "<video>请判断该路侧监控视频中是否发生交通事故。\n交通事故包括：明确可见的碰撞、剐蹭、追尾、侧翻，以及碰撞点被遮挡但可由车辆异常停止、轨迹突变、周围车辆避让等前后状态推断出的事故。\n注意：单纯拥堵、排队、车辆靠近、开启双闪但没有碰撞或异常状态变化，不算事故。\n只回答\"是\"或\"否\"。"},
    {"role": "assistant", "content": "否"}
  ],
  "videos": ["/data/videos/xxx.mp4"]
}
```

答案来源：`accident` 字段。

### 3.6 样本生成注意事项

1. **同一 prompt 只对应一种回答格式**：
   问"只回答是/否"的样本，答案绝不能带分析；问"按步骤分析"的样本，答案必须完整分析；
2. **每个视频不必生成全部任务**：
   可每个视频随机抽 2~3 个任务生成，控制总训练量；
3. **训练样本拆分为独立单轮样本**（推荐为主），
   多轮渐进式问答样本仅作为 10~20% 辅助，且建议将前置轮次
   assistant 的 loss 关闭（`"loss": false`）；
4. **视频片段裁剪**：
   长视频裁剪为"事故前 3~5 秒 + 事故过程 + 事故后 3~5 秒"，
   负样本裁剪为等长片段。

---

## 4. 数据配比与困难样本要求

### 4.1 任务配比

| 任务类型 | 占比 | 作用 |
|---|---|---|
| 任务E 部署格式二分类 | 40~50% | 主任务，保证输出稳定 |
| 任务C 对比判别四选一 | 15~20% | 类间边界 |
| 任务A+B 属性/证据判断 | 15~20% | 中间语义监督 |
| 任务D 步骤化推理 | 20~30% | 理解上限 |

### 4.2 困难样本要求

`hard=true` 的样本（见 2.3 节）在总训练集中占比 **≥ 30%**，其中：

| 困难类型 | 最低建议数量 |
|---|---|
| 拥堵但无事故（路口/隧道各覆盖） | 每场景 ≥ 200 条 |
| 双闪临停但无事故 | ≥ 200 条 |
| 近距离/急刹但无碰撞（near-miss） | ≥ 150 条 |
| 遮挡型事故（正样本） | ≥ 150 条 |
| 事故不明显（正样本） | ≥ 150 条 |

### 4.3 最小对比对

针对两大痛点，构造"视觉相似、标签相反"的成对样本：

**对比对①：拥堵 vs 事故**

| 样本 | 判别点写入推理答案 | 标签 |
|---|---|---|
| 隧道拥堵缓行 | 车流连续移动、无固定中断点 | 否 |
| 隧道事故排队 | 交通流在某点中断、事故车静止、后车绕行 | 是 |

**对比对②：单车事故停车 vs 正常双闪临停**

| 样本 | 判别点写入推理答案 | 标签 |
|---|---|---|
| 撞护栏后停车开双闪 | 停止过程异常：急停/偏转/姿态歪斜/位置异常 | 是 |
| 靠边临停开双闪 | 平稳减速、停在合理位置、车身端正 | 否 |

每组对比对两个样本都生成任务C、任务D、任务E 三种样本。

---

## 5. 模型训练

### 5.1 基础方案：单阶段 LoRA 多任务 SFT（推荐先做）

```bash
PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
IMAGE_MAX_TOKEN_NUM=1024 \
VIDEO_MAX_TOKEN_NUM=192 \
FPS_MAX_FRAMES=24 \
CUDA_VISIBLE_DEVICES=0 \
python swift/cli/sft.py \
  --model /path/to/Qwen3-VL-4B-Instruct \
  --dataset /path/to/multitask_train.jsonl \
  --val_dataset /path/to/multitask_val.jsonl \
  --tuner_type lora \
  --target_modules all-linear \
  --freeze_llm false \
  --freeze_vit true \
  --freeze_aligner false \
  --lora_rank 8 \
  --lora_alpha 32 \
  --lora_dropout 0.05 \
  --torch_dtype bfloat16 \
  --attn_impl flash_attn \
  --padding_free true \
  --gradient_checkpointing true \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 16 \
  --learning_rate 1e-4 \
  --warmup_ratio 0.05 \
  --num_train_epochs 2 \
  --max_length 6144 \
  --dataset_shuffle true \
  --train_dataloader_shuffle true \
  --data_seed 42 \
  --eval_strategy steps \
  --save_strategy steps \
  --eval_steps 200 \
  --save_steps 200 \
  --save_total_limit 3 \
  --metric_for_best_model token_acc \
  --load_best_model_at_end true \
  --lazy_tokenize true \
  --dataloader_num_workers 16 \
  --output_dir output/accident_multitask
```

关键参数说明：

| 参数 | 相比纯二分类的调整 | 原因 |
|---|---|---|
| `FPS_MAX_FRAMES` | 16 → 24（显存允许可到 32） | 覆盖"停止前过程"，区分临停与事故停车 |
| `VIDEO_MAX_TOKEN_NUM` | 128 → 192 | 提高视频信息量 |
| `--max_length` | 4096 → 6144 | 步骤化推理答案较长 |
| `--freeze_vit` | 先 true | 若对姿态歪斜/碎片不敏感，再试 false + 低学习率 |

### 5.2 可选：两阶段训练

```text
阶段一（语义预热）：
  数据 = 任务A + 任务B + 任务C
  epoch = 1

阶段二（主任务）：
  数据 = 任务E 为主(60%) + 任务D(20%) + 阶段一数据 replay(20%)
  epoch = 1~2
  从阶段一 checkpoint 继续训练（--resume_from_checkpoint 或
  --model 指向 merge 后的阶段一模型）
```

要点：阶段二必须保留 20% 阶段一数据，防止灾难性遗忘。

### 5.3 可选进阶：GRPO 强化

前提：SFT 后模型已能按"分析 → 结论"格式输出，且困难样本答对率在 30~80% 区间。

**奖励设计**：

```text
准确性奖励（权重 1.0）：提取"结论：是/否"与标签比对，对=1.0，错/无法提取=0.0
格式奖励（权重 0.3）：含"分析：""结论："且顺序正确 +0.2；
                      结论只含单字 +0.1；分析长度 20~200 字 +0.1
```

**训练命令**：

```bash
CUDA_VISIBLE_DEVICES=0,1 \
FPS_MAX_FRAMES=16 \
swift rlhf \
  --rlhf_type grpo \
  --model /path/to/sft_merged_model \
  --dataset /path/to/grpo_hard_samples.jsonl \
  --external_plugins /path/to/accident_reward_plugin.py \
  --reward_funcs accident_acc accident_format \
  --reward_weights 1.0 0.3 \
  --tuner_type lora \
  --num_generations 8 \
  --temperature 1.0 \
  --max_completion_length 256 \
  --beta 0.04 \
  --learning_rate 1e-6 \
  --use_vllm true \
  --output_dir output/grpo_accident
```

GRPO 数据要求：

- 只放 SFT 模型"会错但不总错"（答对率 30~80%）的样本；
- 剔除证据不可见的噪声正样本；
- 数据格式：messages 只含 user 问题 + `solution` 字段存标签。

**自定义奖励函数示例**（`accident_reward_plugin.py`）：

```python
import re
from typing import List
from swift.plugin import ORM, orms


class AccidentAccuracyReward(ORM):
    """准确性奖励：提取"结论：是/否"与标签比对"""

    def __call__(self, completions: List[str], solution: List[str], **kwargs) -> List[float]:
        rewards = []
        for completion, label in zip(completions, solution):
            match = re.search(r'结论[:：]\s*([是否])', completion)
            if match and match.group(1) == label.strip():
                rewards.append(1.0)
            else:
                rewards.append(0.0)
        return rewards


class AccidentFormatReward(ORM):
    """格式奖励：先分析后结论，结论只含是/否"""

    def __call__(self, completions: List[str], **kwargs) -> List[float]:
        rewards = []
        for completion in completions:
            score = 0.0
            has_analysis = re.search(r'分析[:：]', completion)
            conclusion = re.search(r'结论[:：]\s*([是否])\s*$', completion.strip())
            if has_analysis and conclusion:
                if completion.find('分析') < completion.find('结论'):
                    score += 0.2
                score += 0.1
                analysis_text = re.split(r'结论[:：]', completion)[0]
                if 20 <= len(analysis_text) <= 200:
                    score += 0.1
            rewards.append(score)
        return rewards


orms['accident_acc'] = AccidentAccuracyReward
orms['accident_format'] = AccidentFormatReward
```

---

## 6. 分桶评估体系

### 6.1 验证集构建

按结构化属性切分验证子集（各子集互不重叠或允许标记多桶）：

| 子集名 | 筛选条件 | 核心指标 | 目标 |
|---|---|---|---|
| easy_positive | collision_visible=是 | recall | ≥ 0.95 |
| occluded_positive | collision_occluded=是 且 accident=是 | recall | 重点提升 |
| unclear_positive | collision_visible=否 且 accident=是 | recall | 重点提升 |
| congestion_negative | congestion=是 且 accident=否 | precision / 误报率 | 重点提升 |
| hazard_negative | hazard_light=是 且 accident=否 | precision / 误报率 | 重点提升 |
| nearmiss_negative | near_miss=是 | precision | 重点提升 |
| night_tunnel | 夜间/隧道/雨天 | F1 | 监控 |
| overall | 全部 | accuracy / F1 / 混淆矩阵 | 监控 |

### 6.2 辅助任务评估

单独评估模型的中间语义能力：

| 任务 | 指标 | 意义 |
|---|---|---|
| 场景分类 | accuracy | 基础场景理解 |
| 交通流状态分类 | accuracy | 拥堵误报的根因指标 |
| 双闪原因分类 | accuracy | 双闪误报的根因指标 |
| 异常停止判断 | accuracy | 遮挡事故召回的根因指标 |

> 判断逻辑：若"交通流状态分类"准确率低，说明拥堵误报的根因
> 是感知层没学好，应补任务A/B数据；若辅助任务都好但事故判断差，
> 说明是决策边界问题，应补任务C对比判别数据。

### 6.3 评估执行方式

```bash
# 用 swift infer 跑验证集，再自行计算分桶指标
CUDA_VISIBLE_DEVICES=0 \
FPS_MAX_FRAMES=24 \
python swift/cli/infer.py \
  --model /path/to/base_model \
  --adapters /path/to/checkpoint \
  --val_dataset /path/to/bucketed_val.jsonl \
  --infer_backend transformers \
  --max_new_tokens 16 \
  --temperature 0 \
  --result_path result.jsonl
```

分桶指标计算要点：

1. 结果文件中每条记录带上原始结构化属性（`--remove_unused_columns false` 或在数据中冗余存储）；
2. 对"是/否"输出做归一化解析（去掉句号、空格、多余文字）；
3. 每个子桶分别计算 recall / precision，并输出混淆矩阵。

### 6.4 对照实验

每次训练至少对比三组：

```text
① base model（未微调）
② 纯二分类 SFT（baseline）
③ 多任务 SFT（本方案）
```

所有组使用相同验证集、相同推理参数（temperature=0）。

---

## 7. 错误分析与迭代

### 7.1 迭代循环

```text
分桶评估
   ↓
导出错误样本（按桶分类）
   ↓
错误归因（视觉不可见 / 语义混淆 / 格式解析失败 / 标注错误）
   ↓
针对性补数据：
   - 语义混淆 → 补对应"最小对比对"（任务C+D+E 三件套）
   - 感知不足 → 补任务A/B样本或提高帧数
   - 标注错误 → 修正标签
   - 视觉不可见 → 移出训练集
   ↓
重训 / 增量训练
   ↓
回归评估（确认目标桶提升且其他桶不回退）
```

### 7.2 错误归因表模板

| 错误样本 | 所属桶 | 模型输出 | 归因 | 处理动作 |
|---|---|---|---|---|
| video_0123 | congestion_negative | 是 | 把排队车流误判为事故中断 | 补"拥堵vs事故"对比对 ×5 |
| video_0456 | occluded_positive | 否 | 未识别避让行为 | 补避让证据样本(任务B2) |
| video_0789 | easy_positive | 否 | 夜间画质差 | 提高 FPS_MAX_FRAMES / 补夜间样本 |

### 7.3 停止条件

满足以下条件可停止迭代进入部署：

```text
1. congestion_negative 误报率 ≤ 业务阈值
2. hazard_negative 误报率 ≤ 业务阈值
3. occluded_positive recall 达到业务要求
4. 总体 F1 相比 baseline 提升且连续两轮迭代增益 < 1%
```

---

## 8. 附录：Prompt 模板汇总

### 8.1 部署用主 Prompt（任务E）

```text
<video>请判断该路侧监控视频中是否发生交通事故。
交通事故包括：明确可见的碰撞、剐蹭、追尾、侧翻，以及碰撞点被遮挡
但可由车辆异常停止、轨迹突变、周围车辆避让等前后状态推断出的事故。
注意：单纯拥堵、排队、车辆靠近、开启双闪但没有碰撞或异常状态变化，
不算事故。
只回答"是"或"否"。
```

### 8.2 推理解释 Prompt（任务D / GRPO）

```text
<video>请按以下步骤分析并判断是否发生交通事故：
1. 场景与交通流状态；
2. 关键车辆行为（停止、双闪、避让、轨迹突变）；
3. 是否存在碰撞或碰撞的间接证据；
4. 结论（是/否）。
```

### 8.3 GRPO 输出格式约定

```text
分析：<20~200字的证据分析>
结论：是/否
```

### 8.4 判别点话术库（写入任务D答案）

| 场景 | 话术 |
|---|---|
| 拥堵负样本 | 车流整体缓行、连续移动，没有固定中断点 |
| 事故正样本 | 交通流在某点中断，事故车辆静止不动，后方车辆绕行 |
| 临停负样本 | 车辆平稳减速靠边，车身端正，停在合理位置 |
| 事故停车正样本 | 车辆急停/偏转后停止，姿态歪斜，停在异常位置 |
| 遮挡事故正样本 | 碰撞点被遮挡，但两车接近后异常停止，周围车辆出现避让 |
| near-miss负样本 | 两车快速接近后正常分开，无停止、无姿态变化、无避让聚集 |
