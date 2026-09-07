# 交通事故识别：SFT → GRPO 两阶段训练设计

> 基座：`Qwen3-VL-*-Instruct`（推荐 4B/8B）；框架：ms-swift；
> 数据：本仓库标注规范（`accident_annotation_spec_video.md` / `accident_annotation_spec_image.md`）产出的结构化 JSON；
> 任务定义沿用 `accident_detection_training_plan.md` 的任务 A–E。
>
> 本文回答三个问题：**SFT 阶段怎么训、什么时候该进 GRPO、GRPO 的奖励怎么设计才能真正压住"拥堵/双闪误报"和"遮挡漏检"。**

---

## 0. 为什么要两阶段，而不是只做 SFT

| 阶段 | 解决的问题 | 解决不了的问题 |
|---|---|---|
| **SFT** | 学会任务格式、基础属性感知（场景/交通流/双闪）、证据→结论的推理模板 | 只能模仿标注文本，对"视觉相似、标签相反"的困难对（拥堵 vs 事故、临停 vs 事故停车）决策边界仍然模糊；teacher-forcing 下模型可能靠话术模板而不是真正看证据 |
| **GRPO** | 直接优化"最终结论是否正确"这一不可微目标；在困难样本上用组内对比逼模型找到真正的判别证据；可加入**非对称代价**（误报比漏报罚得更重或反之） | 需要 SFT 先把格式和基础能力立住；样本"全对"或"全错"时没有梯度 |

结论：**SFT 负责"会做"，GRPO 负责"做对困难的"**。GRPO 不是替代 SFT，而是只在 SFT 模型"会错但不总错"的样本上精修。

---

## 1. 总体流程

```text
结构化标注 JSON（唯一真源）
        │  脚本派生任务 A–E 样本（messages 格式）
        ▼
┌─────────────────────────────────────────┐
│ 阶段一 SFT（LoRA）                        │
│  1a 语义预热：任务 A + B + C，1 epoch     │
│  1b 主任务：  任务 E 60% + D 20% + 1a 回放 20%，1~2 epoch │
└───────────────┬─────────────────────────┘
                ▼
        分桶评估（门控）
        · 格式合规率 ≥ 98%
        · 困难桶答对率落在 30%~80%（GRPO 可训练区）
                ▼
┌─────────────────────────────────────────┐
│ 阶段二 GRPO（LoRA，vLLM colocate 采样）    │
│  数据：SFT 模型 pass-rate 在 [1/8, 7/8] 的困难样本 │
│  奖励：结论准确 + 证据一致 + 格式 + 非对称代价（按 task 路由）│
│  课程：第 1 轮纯困难样本 → 第 2 轮混 20% 简单样本防退化 │
└───────────────┬─────────────────────────┘
                ▼
        分桶回归评估（困难桶提升、简单桶不回退）
                ▼
┌─────────────────────────────────────────┐
│ 阶段三 合并与部署                          │
│  merge LoRA → 任务 E 短输出蒸馏（可选）→ vLLM 部署 │
└─────────────────────────────────────────┘
```

---

## 2. 阶段一：SFT

### 2.1 数据准备要点

1. **统一输出格式，为 GRPO 铺路**。任务 D（步骤化推理）的 assistant 答案在 SFT 阶段就固定为 GRPO 要用的格式，避免阶段切换时格式漂移：

```text
分析：<20~200 字，必须包含关键判别点话术>
结论：是
```

2. **判别点话术必须写进任务 D 答案**（来自 `accident_detection_training_plan.md` 8.4 话术库），GRPO 阶段的"证据一致性奖励"会用同一套关键词表打分，SFT 先把这些话术教会。

3. **困难样本 ≥ 30%**，且四类困难样本（拥堵负、双闪负、near-miss 负、遮挡正）每类都有"最小对比对"。

4. **每条样本冗余携带结构化字段**（`accident`、`congestion`、`hazard_light`、`hazard_light_reason`、`collision_occluded`、`traffic_flow`、`hard`、`bucket`）。SFT 训练忽略这些列，但 GRPO 奖励函数与分桶评估都要用，一次生成两阶段共用。

样本示例（任务 D）：

```json
{
  "task": "D",
  "messages": [
    {"role": "user", "content": "<video>请按以下步骤分析并判断是否发生交通事故：\n1. 场景与交通流状态；\n2. 关键车辆行为（停止、双闪、避让、轨迹突变）；\n3. 是否存在碰撞或碰撞的间接证据；\n4. 结论（是/否）。\n输出格式：\n分析：<分析内容>\n结论：是/否"},
    {"role": "assistant", "content": "分析：隧道内车流缓行并排队，多辆车开启双闪但均随车流连续移动，没有固定中断点；未观察到碰撞、剐蹭或避让行为。\n结论：否"}
  ],
  "videos": ["/data/clips/tunnel_0231.mp4"],
  "solution": "否",
  "accident": "否", "congestion": "是", "hazard_light": "是",
  "hazard_light_reason": "拥堵缓行", "collision_occluded": "否",
  "traffic_flow": "拥堵", "hard": true, "bucket": "congestion_negative"
}
```

### 2.2 子阶段 1a：语义预热（任务 A + B + C）

目的：先让模型"看懂"场景、交通流、双闪、异常停止，再学决策。避免一上来就学二分类导致模型走捷径（如"有双闪就判事故"）。

```bash
PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
VIDEO_MAX_TOKEN_NUM=192 FPS_MAX_FRAMES=24 \
CUDA_VISIBLE_DEVICES=0,1,2,3 NPROC_PER_NODE=4 \
swift sft \
  --model Qwen/Qwen3-VL-4B-Instruct \
  --dataset /data/sft/stage1a_ABC.jsonl \
  --val_dataset /data/sft/val_ABC.jsonl \
  --tuner_type lora --target_modules all-linear \
  --lora_rank 16 --lora_alpha 32 --lora_dropout 0.05 \
  --freeze_vit true --freeze_aligner false \
  --torch_dtype bfloat16 --attn_impl flash_attn \
  --padding_free true --gradient_checkpointing true \
  --per_device_train_batch_size 1 --gradient_accumulation_steps 8 \
  --learning_rate 1e-4 --warmup_ratio 0.05 --num_train_epochs 1 \
  --max_length 6144 \
  --eval_steps 200 --save_steps 200 --save_total_limit 2 \
  --lazy_tokenize true --dataloader_num_workers 8 \
  --output_dir output/sft_1a_semantic
```

### 2.3 子阶段 1b：主任务（任务 E 60% + D 20% + 1a 回放 20%）

从 1a 的 LoRA 继续训练（`--resume_from_checkpoint` 只恢复权重需配 `--resume_only_model true`；或先 merge 再作为 `--model`）。**必须保留 20% 1a 数据回放**，否则属性感知能力会被二分类主任务冲掉。

```bash
PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
VIDEO_MAX_TOKEN_NUM=192 FPS_MAX_FRAMES=24 \
CUDA_VISIBLE_DEVICES=0,1,2,3 NPROC_PER_NODE=4 \
swift sft \
  --model Qwen/Qwen3-VL-4B-Instruct \
  --resume_from_checkpoint output/sft_1a_semantic/checkpoint-xxx \
  --resume_only_model true \
  --dataset /data/sft/stage1b_E.jsonl#6000 \
            /data/sft/stage1b_D.jsonl#2000 \
            /data/sft/stage1a_ABC.jsonl#2000 \
  --val_dataset /data/sft/val_bucketed.jsonl \
  --tuner_type lora --target_modules all-linear \
  --lora_rank 16 --lora_alpha 32 --lora_dropout 0.05 \
  --freeze_vit true --freeze_aligner false \
  --torch_dtype bfloat16 --attn_impl flash_attn \
  --padding_free true --gradient_checkpointing true \
  --per_device_train_batch_size 1 --gradient_accumulation_steps 8 \
  --learning_rate 5e-5 --warmup_ratio 0.05 --num_train_epochs 2 \
  --max_length 6144 \
  --eval_steps 200 --save_steps 200 --save_total_limit 3 \
  --metric_for_best_model token_acc --load_best_model_at_end true \
  --lazy_tokenize true --dataloader_num_workers 8 \
  --output_dir output/sft_1b_main
```

`--dataset path#N` 表示从该文件抽 N 条，用它直接控制配比。1b 学习率降到 5e-5，避免覆盖 1a 学到的语义。

### 2.4 SFT 退出门控（决定能否进 GRPO）

用 `swift infer`（temperature 0）跑分桶验证集，满足以下条件再进 GRPO：

| 门控项 | 阈值 | 不满足时的动作 |
|---|---|---|
| 任务 D 格式合规率（能解析出"结论：是/否"） | ≥ 98% | 补任务 D 数据、检查 prompt 是否带格式说明 |
| `easy_positive` recall | ≥ 0.95 | SFT 本身没训好，回到 1b 调数据 |
| 困难桶（congestion_negative / hazard_negative / occluded_positive）答对率 | **30% ~ 80%** | < 30%：补对比对再 SFT；> 80%：该桶不需要 GRPO |
| 辅助任务（交通流分类、双闪原因分类）准确率 | ≥ 0.85 | 感知层没学好，GRPO 救不了，补任务 A/B |

"30%~80%"是 GRPO 的**可训练区**：组内 8 次采样要既有对又有错，才有优势信号。

---

## 3. 阶段二：GRPO

### 3.1 训练目标

- 主目标：提升困难桶的**结论准确率**，且误报/漏报按业务代价加权；
- 副目标：让"分析"部分真正引用画面证据（与结构化标注一致），而不是套话；
- 约束：格式不崩、长度不膨胀、与 SFT 模型 KL 不爆。

### 3.2 GRPO 数据筛选（比奖励设计更重要）

**步骤：**

1. 用 SFT 模型对全部 `hard=true` 样本 + 各困难桶验证集之外的池子，做 **k=8 次采样**（temperature 1.0），用与奖励函数相同的解析逻辑算每条样本的 pass-rate；
2. **只保留 pass-rate ∈ [1/8, 7/8]** 的样本（全对无信号，全错大概率是标注噪声或视觉不可见）；
3. **按桶均衡**：congestion_negative / hazard_negative / nearmiss_negative / occluded_positive / unclear_positive 各桶数量拉平，正负样本约 1:1；
4. **剔除噪声**：pass-rate = 0 且人工复核确认"画面无证据"的正样本移出训练集（回到标注规范 2.3 噪声剔除规则）；
5. 第 2 轮课程再混入 **20% 简单样本**（pass-rate = 1），防止困难样本过拟合导致简单桶退化。

**数据格式**：messages 只保留 user 轮，标签放 `solution`，任务类型放 `task`，结构化字段照带：

```json
{
  "task": "D",
  "messages": [{"role": "user", "content": "<video>请按以下步骤分析……\n输出格式：\n分析：<分析内容>\n结论：是/否"}],
  "videos": ["/data/clips/tunnel_0231.mp4"],
  "solution": "否",
  "bucket": "congestion_negative",
  "accident": "否", "congestion": "是", "hazard_light": "是",
  "hazard_light_reason": "拥堵缓行", "collision_occluded": "否", "traffic_flow": "拥堵"
}
```

GRPO 主训任务 D（有分析过程才有"证据一致性"奖励可算），任务 C（四选一）和任务 E（单字）各混 15% 左右，通过 `task` 列路由到各自的奖励函数。

### 3.3 奖励设计

| 奖励 | 权重 | 作用于 task | 计算方式 | 目的 |
|---|---|---|---|---|
| `acc_accident` 结论准确 | **1.0** | D, E | 解析"结论：是/否"（E 为整段单字）与 `solution` 比对，对 1.0 / 错 0.0 / 解析失败 0.0 | 主信号 |
| `acc_choice` 四选一准确 | 1.0 | C | 解析选项字母与 `solution` 比对 | 类间边界 |
| `evidence_consistency` 证据一致 | **0.5** | D | 分析文本中的判别点关键词与结构化字段是否一致（见下），一致 +，矛盾 − ，范围 [-0.5, 1.0] | 逼模型"看证据"而非套话 |
| `asymmetric_cost` 非对称代价 | 0.5 | D, E | 困难负样本（`hard` 且 `accident=否`）被判"是"→ −1.0；遮挡正样本（`collision_occluded=是`）被判"否"→ −0.6；其余 0 | 把业务代价编进奖励 |
| `format_accident` 格式 | 0.2 | D | 含"分析："与"结论："且顺序正确 +0.6；结论行只含单字 +0.2；分析 20~200 字 +0.2 | 格式稳定 |
| `soft_overlong`（内置） | 0.3 | 全部 | 接近 `max_completion_length` 时线性惩罚 | 防长度膨胀 |
| `repetition`（内置） | 0.2 | 全部 | n-gram 重复惩罚 | 防复读 |

**证据一致性关键词表**（与 SFT 话术库同源，可扩展）：

| 结构化条件 | 应出现（+0.25/项，最多 +1.0） | 不应出现（每项 −0.25） |
|---|---|---|
| `traffic_flow=拥堵` 且 `accident=否` | 缓行 / 连续移动 / 排队 / 无中断 | 中断 / 碰撞 / 撞 / 绕行 |
| `accident=是` 且 `traffic_flow=某点中断` | 中断 / 静止 / 绕行 / 避让 | 畅通 / 正常通行 |
| `hazard_light_reason=临时停车` 且 `accident=否` | 靠边 / 平稳 / 端正 / 合理位置 | 歪斜 / 碰撞 / 急停 |
| `abnormal_stop=是` 且 `accident=是` | 歪斜 / 异常位置 / 急停 / 偏转 | 平稳 / 正常 |
| `collision_occluded=是` 且 `accident=是` | 遮挡 / 间接 / 避让 / 异常停止 | 未发现任何异常 |
| `near_miss=是` 且 `accident=否` | 分开 / 未碰撞 / 无停止 | 碰撞 / 撞击 / 剐蹭 |

**关于奖励聚合**：多路奖励量纲不同，建议 `--scale_rewards gdpo`（每路奖励各自组内归一化后再按权重加和），避免权重 1.0 的准确率奖励被 [-1, 0] 的代价奖励在数值上淹没。

### 3.4 奖励插件完整实现

保存为 `plugins/accident_reward_plugin.py`（注意导入路径是 `swift.rewards`，不是旧版的 `swift.plugin`）：

```python
import re
from typing import List, Optional

from swift.rewards import ORM, orms

CONCLUSION_RE = re.compile(r'结论[:：]\s*([是否])')
CHOICE_RE = re.compile(r'\b([ABCD])\b')

# (条件函数, 应出现关键词, 不应出现关键词)
EVIDENCE_RULES = [
    (lambda r: r.get('traffic_flow') == '拥堵' and r.get('accident') == '否',
     ['缓行', '连续移动', '排队', '无中断', '没有固定中断'], ['中断', '碰撞', '撞', '绕行']),
    (lambda r: r.get('accident') == '是' and r.get('traffic_flow') == '某点中断',
     ['中断', '静止', '绕行', '避让'], ['畅通', '正常通行']),
    (lambda r: r.get('hazard_light_reason') == '临时停车' and r.get('accident') == '否',
     ['靠边', '平稳', '端正', '合理位置'], ['歪斜', '碰撞', '急停']),
    (lambda r: r.get('abnormal_stop') == '是' and r.get('accident') == '是',
     ['歪斜', '异常位置', '急停', '偏转'], ['平稳', '正常']),
    (lambda r: r.get('collision_occluded') == '是' and r.get('accident') == '是',
     ['遮挡', '间接', '避让', '异常停止'], ['未发现任何异常', '没有任何异常']),
    (lambda r: r.get('near_miss') == '是' and r.get('accident') == '否',
     ['分开', '未碰撞', '无停止', '没有停止'], ['碰撞', '撞击', '剐蹭']),
]


def _row(kwargs, i) -> dict:
    """把按列传入的数据集字段还原为第 i 条样本的字典。"""
    keys = ['accident', 'congestion', 'hazard_light', 'hazard_light_reason', 'collision_occluded',
            'traffic_flow', 'abnormal_stop', 'near_miss', 'hard', 'bucket']
    return {k: (kwargs.get(k) or [None] * (i + 1))[i] for k in keys}


def _parse_conclusion(text: str) -> Optional[str]:
    m = CONCLUSION_RE.search(text)
    if m:
        return m.group(1)
    stripped = text.strip().rstrip('。.')
    return stripped if stripped in ('是', '否') else None


class AccidentAccuracy(ORM):
    """任务 D/E：结论是否正确。非 D/E 任务返回 None（不参与该奖励）。"""

    def __call__(self, completions: List[str], solution: List[str], task: List[str], **kwargs) -> List[Optional[float]]:
        rewards = []
        for c, sol, t in zip(completions, solution, task):
            if t not in ('D', 'E'):
                rewards.append(None)
                continue
            pred = _parse_conclusion(c)
            rewards.append(1.0 if pred is not None and pred == sol.strip() else 0.0)
        return rewards


class ChoiceAccuracy(ORM):
    """任务 C：四选一选项字母是否正确。"""

    def __call__(self, completions: List[str], solution: List[str], task: List[str], **kwargs) -> List[Optional[float]]:
        rewards = []
        for c, sol, t in zip(completions, solution, task):
            if t != 'C':
                rewards.append(None)
                continue
            m = CHOICE_RE.search(c.strip())
            rewards.append(1.0 if m and m.group(1) == sol.strip() else 0.0)
        return rewards


class EvidenceConsistency(ORM):
    """任务 D：分析文本与结构化标注的判别点是否一致，范围 [-0.5, 1.0]。"""

    def __call__(self, completions: List[str], task: List[str], **kwargs) -> List[Optional[float]]:
        rewards = []
        for i, (c, t) in enumerate(zip(completions, task)):
            if t != 'D':
                rewards.append(None)
                continue
            row = _row(kwargs, i)
            analysis = re.split(r'结论[:：]', c)[0]
            score, matched_rule = 0.0, False
            for cond, should, should_not in EVIDENCE_RULES:
                if not cond(row):
                    continue
                matched_rule = True
                score += min(1.0, 0.25 * sum(1 for k in should if k in analysis))
                score -= 0.25 * sum(1 for k in should_not if k in analysis)
            rewards.append(max(-0.5, min(1.0, score)) if matched_rule else 0.0)
        return rewards


class AsymmetricCost(ORM):
    """业务代价：困难负样本误报 -1.0，遮挡正样本漏报 -0.6。"""

    def __call__(self, completions: List[str], solution: List[str], task: List[str], **kwargs) -> List[Optional[float]]:
        rewards = []
        for i, (c, sol, t) in enumerate(zip(completions, solution, task)):
            if t not in ('D', 'E'):
                rewards.append(None)
                continue
            row = _row(kwargs, i)
            pred = _parse_conclusion(c)
            cost = 0.0
            if pred == '是' and sol.strip() == '否' and row.get('hard') in (True, 'true', 'True', 1):
                cost = -1.0
            elif pred == '否' and sol.strip() == '是' and row.get('collision_occluded') == '是':
                cost = -0.6
            rewards.append(cost)
        return rewards


class AccidentFormat(ORM):
    """任务 D：分析→结论顺序、结论单字、分析长度。"""

    def __call__(self, completions: List[str], task: List[str], **kwargs) -> List[Optional[float]]:
        rewards = []
        for c, t in zip(completions, task):
            if t != 'D':
                rewards.append(None)
                continue
            score = 0.0
            has_analysis = re.search(r'分析[:：]', c)
            conclusion = re.search(r'结论[:：]\s*([是否])\s*$', c.strip())
            if has_analysis and conclusion and c.find('分析') < c.find('结论'):
                score += 0.6
                score += 0.2  # 结论行只含单字（正则已保证）
                analysis_text = re.split(r'结论[:：]', c)[0]
                if 20 <= len(analysis_text) <= 200:
                    score += 0.2
            rewards.append(score)
        return rewards


orms['acc_accident'] = AccidentAccuracy
orms['acc_choice'] = ChoiceAccuracy
orms['evidence_consistency'] = EvidenceConsistency
orms['asymmetric_cost'] = AsymmetricCost
orms['format_accident'] = AccidentFormat
```

实现要点：

- 非本任务样本**返回 `None`**，ms-swift 会只在任务内计算该奖励（多任务奖励路由机制）；
- 数据集的额外列（`accident`、`hard`…）按列名以 list 形式传入 `kwargs`，`_row()` 负责还原为单条字典；
- 训练前务必用 SFT 模型的采样结果**离线跑一遍插件**，看奖励分布是否合理（准确率奖励均值应在 0.3~0.8，证据奖励不应全为 0）。

### 3.5 GRPO 训练命令

先把 SFT LoRA 合并成完整权重（vLLM colocate 采样最省事）：

```bash
swift export --adapters output/sft_1b_main/checkpoint-best --merge_lora true \
  --output_dir output/sft_merged
```

GRPO 训练（4 卡示例，LoRA + vLLM colocate）：

```bash
PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
VIDEO_MAX_TOKEN_NUM=192 FPS_MAX_FRAMES=16 \
CUDA_VISIBLE_DEVICES=0,1,2,3 NPROC_PER_NODE=4 \
swift rlhf \
  --rlhf_type grpo \
  --model output/sft_merged \
  --dataset /data/grpo/round1_hard.jsonl \
  --load_from_cache_file true \
  --external_plugins plugins/accident_reward_plugin.py \
  --reward_funcs acc_accident acc_choice evidence_consistency asymmetric_cost format_accident soft_overlong repetition \
  --reward_weights 1.0 1.0 0.5 0.5 0.2 0.3 0.2 \
  --scale_rewards gdpo \
  --soft_cache_length 64 \
  --tuner_type lora --target_modules all-linear \
  --lora_rank 16 --lora_alpha 32 \
  --torch_dtype bfloat16 --attn_impl flash_attn \
  --use_vllm true --vllm_mode colocate \
  --vllm_gpu_memory_utilization 0.5 --vllm_tensor_parallel_size 2 \
  --vllm_max_model_len 8192 \
  --vllm_limit_mm_per_prompt '{"video": 1}' \
  --sleep_level 1 --offload_model true --offload_optimizer true \
  --num_generations 8 \
  --per_device_train_batch_size 2 --gradient_accumulation_steps 4 \
  --generation_batch_size 32 \
  --max_completion_length 320 \
  --temperature 1.0 --top_p 0.95 \
  --beta 0.04 \
  --epsilon 0.2 --epsilon_high 0.28 \
  --dynamic_sample true --max_resample_times 3 \
  --overlong_filter true \
  --learning_rate 1e-6 --warmup_ratio 0.05 --num_train_epochs 1 \
  --max_length 8192 --truncation_strategy delete \
  --eval_strategy no \
  --save_steps 50 --save_total_limit 3 \
  --logging_steps 1 --log_completions true \
  --report_to swanlab \
  --output_dir output/grpo_round1
```

关键参数解释：

| 参数 | 值 | 原因 |
|---|---|---|
| `--num_generations 8` | 8 | 每题 8 次采样；困难样本 pass-rate 在 1/8~7/8 才有信号 |
| `--generation_batch_size 32` | = 2×4×4 | 必须能被 `num_generations` 整除，且是 `per_device_bs × world_size` 的整数倍 |
| `--beta 0.04` | 默认 | 与 SFT 参考模型的 KL 约束；分析文本变套话时可调大到 0.1 |
| `--epsilon_high 0.28` | DAPO clip-higher | 让低概率但正确的证据表述有机会被拉起来 |
| `--dynamic_sample true` | DAPO | 组内奖励全同（全对/全错）的题重采样，保证有效梯度 |
| `--overlong_filter true` | DAPO | 被截断的输出不进 loss，防止模型学会"写不完" |
| `--scale_rewards gdpo` | 多奖励 | 各奖励分别归一化再加权，代价奖励不会被数值淹没 |
| `--truncation_strategy delete` | 多模态必需 | 左截断会切掉视频 token 导致 shape 错误 |
| `--max_completion_length 320` | 分析 200 字 + 结论 | 任务 D 够用；任务 E 输出单字也不受影响 |
| `--learning_rate 1e-6` | 小 | GRPO 阶段的 LoRA 学习率比 SFT 低两个量级 |
| `--sleep_level 1 --offload_*` | 显存 | 训练与 vLLM 采样共卡时释放显存 |

**可选：格式硬约束**。若格式奖励仍压不住格式崩坏，可用 vLLM 引导解码强制输出格式，这样格式奖励可以去掉、把权重让给证据奖励：

```bash
  --structured_outputs_regex '分析：[^\n]{20,200}\n结论：[是否]'
```

**从 LoRA 直接继续（不 merge）的替代写法**：`--model Qwen/Qwen3-VL-4B-Instruct --adapters output/sft_1b_main/checkpoint-best --ref_adapters output/sft_1b_main/checkpoint-best`，此时 vLLM 需 `--vllm_enable_lora true --lora_rank 16`。

### 3.6 训练监控与停止

`--log_completions true` 会把每步采样写到 `completions.jsonl`，配合 SwanLab/W&B 看以下曲线：

| 指标 | 健康信号 | 异常信号 → 处置 |
|---|---|---|
| `reward/acc_accident` 均值 | 从 ~0.5 稳步升到 0.8+ | 停在 0.5 不动 → 数据 pass-rate 分布有问题，回 3.2 重筛 |
| `reward/evidence_consistency` | 同步上升 | 不升甚至下降 → 模型在猜结论不看证据，把权重升到 0.8 |
| `reward/asymmetric_cost` | 趋近 0 | 长期 < −0.3 → 困难负样本仍大量误报，增补拥堵/临停对比对 |
| `completions/mean_length` | 稳定在 100~250 字 | 单调增长 → 加大 `soft_overlong` 权重或减 `max_completion_length` |
| `kl` | < 0.1 缓慢上升 | 突增 → 调大 `beta`、降 lr |
| `clip_ratio` | 0.1~0.3 | 长期 > 0.5 → 策略更新过猛，降 lr |

停止条件（满足任一）：

1. 困难桶（congestion_negative / hazard_negative / occluded_positive）验证指标连续 3 次评估提升 < 0.5%；
2. `easy_positive` recall 或简单桶指标出现 > 1% 回退（说明过拟合困难样本，回退到上一 checkpoint 并进入第 2 轮课程）；
3. KL > 0.3。

### 3.7 两轮课程

| 轮次 | 数据 | 目标 |
|---|---|---|
| Round 1 | 纯困难样本（pass-rate 1/8~7/8），各桶均衡 | 主攻决策边界 |
| Round 2 | Round 1 后重新用新模型算 pass-rate 再筛一次困难样本 80% + 简单样本（pass-rate=1）20% | 巩固并防退化；`--model` 指向 Round 1 merge 后权重 |

Round 2 的 GRPO 数据必须**重新筛选**——Round 1 训完后原来的困难样本很多已变成"全对"，继续用会没有梯度。

---

## 4. 阶段三：合并与部署

### 4.1 merge

```bash
swift export --adapters output/grpo_round2/checkpoint-best --merge_lora true \
  --output_dir output/accident_final
```

### 4.2 部署格式选择

GRPO 主训的是任务 D（分析 + 结论），线上部署有两条路：

| 方式 | 做法 | 优点 | 代价 |
|---|---|---|---|
| **A. 直接部署任务 D 格式** | 线上 prompt 用任务 D，服务端解析"结论："，分析文本作为告警解释一并推送 | 可解释、告警运维友好；GRPO 增益全部保留 | 每次多生成 100~250 token，延迟略增 |
| **B. 蒸馏回任务 E 短输出** | 用最终模型对训练集自采样，保留"结论正确"的样本，把其 `结论` 作为任务 E 答案，再做一轮小规模任务 E SFT（lr 2e-5，1 epoch，混 30% 任务 D 防遗忘） | 线上单字输出、延迟最低 | 多一轮训练；需验证蒸馏后困难桶不回退 |

推荐：**中心侧用 A**（需要解释），**路侧边缘用 B**（算力受限）。

### 4.3 部署推理示例

```bash
swift deploy --model output/accident_final --infer_backend vllm \
  --vllm_limit_mm_per_prompt '{"video": 1}' --max_model_len 8192 \
  --served_model_name accident-qwen3vl --port 8000
```

请求时 `temperature=0`、`max_tokens=320`（方式 A）或 `max_tokens=4`（方式 B）；Qwen3-VL-Instruct 不需要 `enable_thinking` 相关设置。

---

## 5. 常见失败模式与对策

| 现象 | 根因 | 对策 |
|---|---|---|
| 分析全是套话（"车流正常，无碰撞"），结论靠猜 | 准确率奖励可被格式化话术+随机结论薅到 | 提高 `evidence_consistency` 权重；加"不应出现"关键词扣分；`beta` 调大 |
| 模型学会输出"结论：否"以躲避非对称代价 | 代价只罚误报不罚漏报 | 给一般正样本漏报也加 −0.3；检查正负样本比是否 1:1 |
| 奖励曲线抖动大、不收敛 | 组内奖励标准差为 0 的题占比高 | 开 `dynamic_sample`；回 3.2 检查 pass-rate 筛选 |
| completion 越来越长 | 长度没约束、模型靠堆证据词刷分 | `soft_overlong` 权重↑；`evidence_consistency` 单题上限已封顶 1.0，确认生效 |
| 格式崩坏（结论出现两次、无"分析："） | 格式奖励权重不足 | 用 `--structured_outputs_regex` 硬约束 |
| 简单桶回退 | 困难样本过拟合 | Round 2 混 20% 简单样本；`beta` 调大 |
| 视频样本 OOM / shape 错误 | 截断切掉了视频 token | `--truncation_strategy delete`；降 `FPS_MAX_FRAMES` 到 16 |
| 奖励函数报错找不到列 | GRPO 会丢弃 assistant 回复，但保留其他列 | 标签放 `solution` 列而不是 messages；确认 jsonl 每行都有 `task` 列 |

---

## 6. 执行清单

```text
[ ] 1. 结构化 JSON → 派生任务 A–E 样本，每条冗余携带结构化字段 + task + bucket + solution
[ ] 2. SFT 1a（A+B+C，1 epoch）
[ ] 3. SFT 1b（E 60% + D 20% + 1a 回放 20%，2 epoch，lr 5e-5）
[ ] 4. 分桶评估，通过 2.4 门控（格式 ≥98%，困难桶 30%~80%）
[ ] 5. SFT 模型 k=8 采样困难池，算 pass-rate，筛 [1/8, 7/8]，各桶均衡
[ ] 6. 离线用采样结果跑 accident_reward_plugin.py，检查奖励分布
[ ] 7. merge SFT LoRA → GRPO Round 1（纯困难样本）
[ ] 8. 分桶回归评估：困难桶↑、简单桶不回退
[ ] 9. 重筛 pass-rate → GRPO Round 2（80% 困难 + 20% 简单）
[ ] 10. merge → 选择部署格式（A 直接部署 / B 蒸馏任务 E）→ swift deploy
```
