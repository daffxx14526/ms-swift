# 交通事故视频素材结构化标注规范（v3）

> 目的：对路侧监控事故**视频**进行结构化、分场景的要素标注，
> 覆盖所有与"事故是否发生"判断相关的要素，
> 为多任务训练（属性感知 / 证据判断 / 对比判别 / 步骤化推理 / 二分类）提供统一数据基础。
>
> 配套文档：图片数据标注见《accident_annotation_spec_image.md》；
> 各要素判定标准见《accident_annotation_criteria.md》。
>
> v3 变更：JSON 按 **p0/p1/p2 优先级分组**组织——从 JSON 内容即可直观看出每个要素的
> 优先级，训练数据生成脚本可直接按优先级层遍历字段。
> （v2 变更保留：固定 JSON 结构；新增机动车侧翻/非机动车侧翻/机动车着火/事故区域字段。）

---

## 目录

1. [设计原则](#1-设计原则)
2. [标注优先级说明](#2-标注优先级说明)
3. [固定 JSON 结构总览（按优先级分组）](#3-固定-json-结构总览按优先级分组)
4. [元信息与环境字段](#4-元信息与环境字段)
5. [交通流字段](#5-交通流字段)
6. [场景要素字段（固定结构，按场景启用）](#6-场景要素字段固定结构按场景启用)
7. [证据链字段](#7-证据链字段)
8. [事件级字段（时间/区域/参与者）](#8-事件级字段时间区域参与者)
9. [最终标签与派生字段](#9-最终标签与派生字段)
10. [取值约定与一致性规则](#10-取值约定与一致性规则)
11. [标注流程与质检](#11-标注流程与质检)
12. [完整标注示例](#12-完整标注示例)
13. [字段与训练任务的映射关系](#13-字段与训练任务的映射关系)
14. [附录：枚举值字典](#14-附录枚举值字典)

---

## 1. 设计原则

1. **面向判别**：只标注与"事故是否发生"判断相关的要素，不做通用视频描述；
2. **JSON 结构固定**：任何场景、任何样本输出的 JSON 字段集合**完全一致**。
   场景差异通过字段取值 `不适用` 体现（工具按适用性矩阵自动锁定）；
3. **优先级内嵌于结构**：每个语义块内部按 `p0 / p1 / p2` 子对象分组，
   JSON 本身即优先级清单，训练数据生成与完整性校验直接按层遍历；
4. **证据与结论分离**：先标"看到了什么"（证据字段），再标"结论是什么"（事故标签）；
5. **不确定性显式化**：看不清、判不了的要素统一标"不确定"，禁止猜测；
6. **困难样本显式打标**：拥堵、双闪、near-miss、遮挡等易混淆样本自动派生 `hard` 标记。

---

## 2. 标注优先级说明

| 级别 | 定义 | 标注要求 |
|---|---|---|
| **P0** | 事故判定核心：直接决定 `accident` 结论、困难样本识别、误报判别的字段 | **所有进入细标的样本必标** |
| **P1** | 重要辅助：证据链补全、推理训练文本生成、场景要素主力字段 | 标准标注必标（正样本 + hard 负样本） |
| **P2** | 完整信息：环境细节、场景次要要素、统计分析用字段 | 人力允许时标注；仅正样本建议标全 |

与分层标注流程的对应关系：

```text
第一层（快速分诊）  ：仅 meta.scene + label 初判
第二层（标准标注）  ：所有块的 p0 + p1 子对象
第三层（完整标注）  ：p0 + p1 + p2 全量
```

训练数据生成脚本的使用方式：

```python
for block in ["traffic", "scene_elements", "evidence", "event"]:
    for level in ["p0", "p1", "p2"]:
        fields = anno[block].get(level, {})
        # p0 字段 → 核心训练任务；p1 → 推理文本/辅助任务；p2 → 元数据/分桶
```

---

## 3. 固定 JSON 结构总览（按优先级分组）

**每条视频输出一条 JSON，结构与字段集合固定不变**。每个语义块内部按优先级分组：

```json
{
  "meta":           { "...": "工具自动填，不分优先级，见第4节" },
  "env":            { "p1": { }, "p2": { } },
  "traffic":        { "p0": { }, "p1": { } },
  "scene_elements": { "p1": { }, "p2": { } },
  "evidence":       { "p0": { }, "p1": { } },
  "event":          { "p0": { }, "p1": { }, "p2": { } },
  "label":          { "p0": { } },
  "derived":        { "...": "脚本自动派生字段，见第9节" }
}
```

约定：

1. 每个块内的 `p0/p1/p2` 子对象**始终存在**（即使为空对象也保留键）；
2. 未到达对应标注层级时，字段填占位值 `未标注`（区别于"不确定"）；
3. `meta` 与 `derived` 不参与人工优先级——前者工具自动填，后者脚本自动算。

---

## 4. 元信息与环境字段

### 4.1 元信息 `meta`（工具自动填，无优先级分组）

| 字段 | 类型 | 取值 | 说明 |
|---|---|---|---|
| `media_type` | enum | video | 固定为 video（图片数据见图片规范） |
| `video_path` | string | - | 视频路径 |
| `duration_sec` | float | - | 视频时长（秒） |
| `scene` | enum | 高速高架 / 城市路口 / 城市普通路段 / 隧道 / 匝道收费站 / 其他 | **P0 性质**，分诊阶段人工确认，决定场景要素适用性 |
| `camera_view` | enum | 路侧固定 / 高点俯视 / 卡口近景 / 隧道固定 / 其他 | 可按摄像头配置表自动填 |
| `annotator_id` | string | - | 标注员编号 |

> `scene` 虽放在 meta（因其决定其余字段适用性、且在分诊层就已确定），
> 优先级视同 P0：任何样本必须有效。

### 4.2 环境条件 `env`

| 子对象 | 字段 | 取值 | 与事故判断的关系 |
|---|---|---|---|
| **p1** | `lighting` | 白天 / 夜间 / 黄昏黎明 / 隧道暗光 | 影响细节可辨识度，分桶评估用 |
| **p1** | `visibility` | 高 / 中 / 低 | 低能见度样本单独分桶 |
| **p2** | `weather` | 晴 / 雨 / 雪 / 雾 / 不确定 | 雨雪天误报高发 |
| **p2** | `road_surface` | 干燥 / 湿滑 / 积水积雪 / 不确定 | 湿滑路面事故形态不同 |
| **p2** | `glare_or_reflection` | 是 / 否 | 夜间反光易误判双闪 |

---

## 5. 交通流字段

### 交通流 `traffic`

| 子对象 | 字段 | 取值 | 说明 |
|---|---|---|---|
| **p0** | `traffic_flow` | 畅通 / 缓行 / 拥堵 / 停止排队 / 某点中断 | **"某点中断"是事故最强间接信号** |
| **p0** | `flow_interruption_point` | 是 / 否 / 不确定 | 固定中断点（下游畅通、上游积压）；整体拥堵中也可能叠加中断点 |
| **p1** | `queue_present` | 是 / 否 | 是否排队 |
| **p1** | `pedestrian_gathering` | 是 / 否 | 人员在车行道聚集（事故后常见） |

> `congestion` 由 `traffic_flow` 自动派生，见第 9 节 `derived`。

---

## 6. 场景要素字段（固定结构，按场景启用）

`scene_elements` 是扁平固定字段块：以下所有字段在每条 JSON 中都存在，
按 `p1 / p2` 分组；`scene` 不适用时该字段填 `不适用`（工具自动锁定）。

### 6.1 p1 子对象（场景要素主力字段）

| 字段 | 适用场景 | 取值 | 与事故判断的关系 |
|---|---|---|---|
| `stop_position` | 全部场景 | 行车道 / 应急车道 / 路边 / 无停车 / 不适用 | "事故停车 vs 临停"核心判别点 |
| `emergency_lane_occupied` | 高速高架、隧道 | 是 / 否 / 无应急车道 / 不适用 | 应急车道停车多为故障临停；行车道停车为强事故信号 |
| `stop_in_lane` | 隧道、高速高架 | 是 / 否 / 不适用 | 隧道/高速行车道停车事故概率高 |
| `queue_at_signal` | 城市路口 | 是 / 否 / 不适用 | **等灯静止 ≠ 事故**（路口最常见误报源） |
| `hazard_light_chain` | 隧道、高速高架 | 是 / 否 / 不适用 | 多车依次开双闪提醒后车（**不是事故**） |
| `sudden_brake_wave` | 高速高架、隧道 | 是 / 否 / 不适用 | 上游连锁急刹（事故前兆） |
| `rear_end_chain` | 高速高架 | 是 / 否 / 不适用 | 多车追尾链 |
| `vru_involved` | 城市路口、城市普通路段 | 行人 / 非机动车 / 两者 / 无 / 不适用 | 弱势交通参与者卷入 |
| `guardrail_impact` | 高速高架、匝道收费站 | 是 / 否 / 不确定 / 不适用 | 撞护栏（单车事故常见形态） |
| `debris_on_road` | 高速高架、隧道 | 是 / 否 / 不确定 / 不适用 | 路面抛洒物/碎片 |
| `smoke_in_view` | 隧道 | 是 / 否 / 不确定 / 不适用 | 隧道烟雾（着火统一用 evidence.vehicle_fire） |

### 6.2 p2 子对象（场景要素次要字段）

| 字段 | 适用场景 | 取值 |
|---|---|---|
| `roadside_parking_present` | 城市普通路段 | 是 / 否 / 不适用 |
| `double_parked` | 城市普通路段 | 是 / 否 / 不适用 |
| `bus_stop_area` | 城市普通路段 | 是 / 否 / 不适用 |
| `toll_queue` | 匝道收费站 | 是 / 否 / 不适用 |
| `merge_conflict` | 高速高架、匝道收费站 | 是 / 否 / 不适用 |
| `weaving_conflict` | 匝道收费站 | 是 / 否 / 不适用 |
| `reverse_or_retrograde` | 高速高架、隧道 | 是 / 否 / 不适用 |
| `intersection_blocked` | 城市路口 | 是 / 否 / 不适用 |
| `turn_conflict` | 城市路口 | 是 / 否 / 不适用 |
| `red_light_running` | 城市路口 | 是 / 否 / 不确定 / 不适用 |
| `signal_state_at_event` | 城市路口 | 红 / 绿 / 黄 / 闪烁 / 不可见 / 不适用 |
| `crosswalk_area` | 城市路口、城市普通路段 | 是 / 否 / 不适用 |
| `pedestrian_crossing_midblock` | 城市普通路段 | 是 / 否 / 不适用 |
| `delivery_rider_involved` | 城市路口、城市普通路段 | 是 / 否 / 不适用 |
| `door_open_event` | 城市普通路段 | 是 / 否 / 不确定 / 不适用 |
| `truck_involved` | 全部场景 | 是 / 否 |
| `construction_zone` | 全部场景 | 是 / 否 |
| `tunnel_zone` | 隧道 | 入口段 / 中段 / 出口段 / 不适用 |
| `lighting_transition_artifact` | 隧道 | 是 / 否 / 不适用 |
| `narrow_shoulder` | 隧道 | 有硬路肩 / 无硬路肩 / 不适用 |
| `sharp_curve_area` | 匝道收费站 | 是 / 否 / 不适用 |
| `ramp_type` | 匝道收费站 | 上匝道 / 下匝道 / 收费站广场 / 不确定 / 不适用 |

### 6.3 场景适用性矩阵（工具自动锁定的依据）

| 字段 → 场景 | 高速高架 | 城市路口 | 城市普通路段 | 隧道 | 匝道收费站 |
|---|---|---|---|---|---|
| stop_position / truck_involved / construction_zone | ✓ | ✓ | ✓ | ✓ | ✓ |
| emergency_lane_occupied / sudden_brake_wave / reverse_or_retrograde | ✓ | - | - | ✓ | - |
| stop_in_lane / hazard_light_chain / debris_on_road | ✓ | - | - | ✓ | - |
| rear_end_chain | ✓ | - | - | - | - |
| guardrail_impact | ✓ | - | - | - | ✓ |
| merge_conflict | ✓ | - | - | - | ✓ |
| queue_at_signal / turn_conflict / red_light_running / signal_state_at_event / intersection_blocked | - | ✓ | - | - | - |
| vru_involved / crosswalk_area / delivery_rider_involved | - | ✓ | ✓ | - | - |
| roadside_parking_present / double_parked / bus_stop_area / door_open_event / pedestrian_crossing_midblock | - | - | ✓ | - | - |
| smoke_in_view / tunnel_zone / lighting_transition_artifact / narrow_shoulder | - | - | - | ✓ | - |
| toll_queue / weaving_conflict / sharp_curve_area / ramp_type | - | - | - | - | ✓ |

（"-" 处工具自动填 `不适用` 并锁定。）

---

## 7. 证据链字段

### 7.1 p0 子对象（事故判定核心证据）

**直接证据：**

| 字段 | 取值 | 说明 |
|---|---|---|
| `collision_visible` | 是 / 否 / 不确定 | 碰撞/剐蹭/撞击过程可直接看到 |
| `person_down` | 是 / 否 / 不确定 | 行人/骑车人倒地（**即"行人倒地"要素**） |
| `motor_vehicle_rollover` | 是 / 否 / 不确定 | **机动车侧翻**/翻滚 |
| `non_motor_rollover` | 是 / 否 / 不确定 | **非机动车侧翻**（电动车/自行车/摩托车） |
| `vehicle_fire` | 是 / 否 / 不确定 | **机动车着火**：明火/浓烟从车辆冒出（全场景通用） |

**间接证据核心：**

| 字段 | 取值 | 说明 |
|---|---|---|
| `collision_occluded` | 是 / 否 | 碰撞点被遮挡（与 collision_visible 互斥为"是"） |
| `abnormal_stop` | 是 / 否 / 不确定 | 异常停止（行车道中间/斜停/横跨车道） |
| `bypass_behavior` | 是 / 否 / 不确定 | 周围车辆绕行固定区域 |

**误报判别要素：**

| 字段 | 取值 | 说明 |
|---|---|---|
| `hazard_light` | 是 / 否 / 不确定 | 双闪（须逐帧确认闪烁） |
| `hazard_light_reason` | 事故后 / 拥堵缓行 / 临时停车 / 故障施工 / 无双闪 / 不明确 | 双闪原因 |
| `congestion_only` | 是 / 否 | 仅拥堵、无任何碰撞证据 |
| `smooth_pullover` | 是 / 否 / 不确定 | 平稳减速靠边（临停特征） |
| `near_miss` | 是 / 否 | 险情但未碰撞（急刹/擦肩） |

### 7.2 p1 子对象（证据链补全）

| 字段 | 取值 | 说明 |
|---|---|---|
| `vehicle_deformation` | 是 / 否 / 不确定 | 车损可见（远景一律"不确定"，不标"否"） |
| `debris_scatter` | 是 / 否 / 不确定 | 事件前后路面新出现碎片/散落物 |
| `occlusion_type` | 无遮挡 / 事故车自身遮挡 / 其他车辆遮挡 / 设施遮挡 / 画面边缘盲区 | 遮挡类型 |
| `abrupt_trajectory_change` | 是 / 否 / 不确定 | 轨迹突变（急偏转/旋转/弹开） |
| `posture_anomaly` | 是 / 否 / 不确定 | 停止后姿态歪斜/位置异常 |
| `people_exit_vehicle` | 是 / 否 | 人员下车查看/聚集 |
| `close_distance_pass` | 是 / 否 | 近距离通过但无接触 |

---

## 8. 事件级字段（时间/区域/参与者)

> `event` 块结构固定。负样本中：p0 时间字段填 0/时长，`accident_area` 各字段填
> null/不适用，`participants` 为空数组。

### 8.1 p0 子对象（正样本必标）

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_start_sec` | float | 事件开始时刻（碰撞或首个异常行为；负样本填 0） |
| `event_end_sec` | float | 事件结束时刻（状态稳定；负样本填视频时长） |
| `accident_area_box` | [x, y, w, h] 或 null | **事故区域**画面外接框（覆盖全部涉事目标与碎片；负样本 null） |
| `accident_area_location` | 行车道内 / 路口中央 / 应急车道 / 路边 / 匝道 / 隧道行车道 / 画面边缘 / 不适用 | 事故区域道路位置类别 |

> `accident_area_box` 与参与者 `roi_box` 的区别：前者是**事件级**整体事故区域
> （事故定位/grounding/ROI 视频裁剪用）；后者是**单个参与者**的活动区域框。

### 8.2 p1 子对象

| 字段 | 类型/取值 | 说明 |
|---|---|---|
| `collision_moment_visible` | 是 / 否 / 无碰撞 | 碰撞瞬间是否可见 |
| `pre_event_visible` | 是 / 否 | 事件前正常状态可见 |
| `post_event_visible` | 是 / 否 | 事件后状态可见 |
| `participants` | array | 参与者列表（结构见 8.4；负样本为空数组） |

### 8.3 p2 子对象

| 字段 | 取值 | 说明 |
|---|---|---|
| `area_occluded_ratio` | 无遮挡 / 部分遮挡 / 大部遮挡 / 不适用 | 事故区域被遮挡程度 |

### 8.4 参与者对象结构（`event.p1.participants[]`）

| 字段 | 优先级性质 | 取值 |
|---|---|---|
| `type` | p1 | 轿车 / SUV / 货车 / 客车 / 摩托车 / 电动车 / 自行车 / 行人 / 固定物 |
| `role` | p1 | 主动方 / 被动方 / 受波及 / 不确定 |
| `behavior_before` | p1 | 正常行驶 / 变道 / 转弯 / 急刹 / 超速感 / 逆行倒车 / 静止 / 不确定 |
| `state_after` | p1 | 停止行车道 / 停止路边 / 驶离 / 倒地 / 侧翻 / 姿态歪斜 / 不确定 |
| `hazard_light_after` | p2 | 是 / 否 / 不可见 |
| `roi_box` | p2 | [x, y, w, h]（可由检测器预填） |

---

## 9. 最终标签与派生字段

### 9.1 最终标签 `label`（全部 p0）

| 字段 | 取值 | 说明 |
|---|---|---|
| `accident` | 是 / 否 / 不确定 | 最终事故标签（准入规则见 10.2；"不确定"不入训练集） |
| `accident_type` | 无事故 / 追尾 / 侧碰 / 剐蹭 / 正面碰撞 / 撞行人非机动车 / 侧翻 / 撞固定物 / 多车连环 / 起火燃烧 / 不确定 | 事故类型 |
| `confidence` | 高 / 中 / 低 | 标注员对结论的信心 |

### 9.2 派生字段 `derived`（脚本自动计算，人工不填）

| 字段 | 派生规则 |
|---|---|
| `congestion` | traffic_flow ∈ {拥堵, 停止排队} → 是；{畅通, 缓行} → 否；某点中断 → 按上游状态 |
| `hard` | 见 10.3 困难样本派生规则 |
| `event_stage_coverage` | 由 collision_moment_visible / pre_event_visible / post_event_visible 组合派生：全过程 / 仅前+后 / 仅后 / 仅前 / 不适用 |

---

## 10. 取值约定与一致性规则

### 10.1 取值约定

1. 所有布尔类字段只允许：**是 / 否 / 不确定**（部分字段额外允许"不适用/无/不可见"，见各表）；
2. **`不适用`** 只能出现在场景要素与事件级字段中，且必须与适用性矩阵一致（工具锁定）；
3. **`未标注`** 是分层占位值：仅允许出现在尚未到达标注层级的 p1/p2 字段中，
   p0 字段在细标样本中不得为"未标注"；
4. "不确定"的使用标准：正常速度播放 + 逐帧回看后仍无法判断。

### 10.2 事故正样本准入规则

`accident=是` 必须满足以下之一：

```text
① collision_visible = 是（碰撞过程可见）
② collision_occluded = 是，且以下间接证据 ≥ 2 项为"是"：
   abnormal_stop / abrupt_trajectory_change / posture_anomaly /
   bypass_behavior / flow_interruption_point / people_exit_vehicle
③ 事故后强证据任一为"是"：
   person_down / motor_vehicle_rollover / non_motor_rollover /
   vehicle_fire / vehicle_deformation
```

不满足准入规则的疑似事故 → `accident=不确定`，不进训练集，单独归档。

### 10.3 困难样本自动派生规则（`derived.hard = true` 条件）

```text
正样本困难：
  collision_visible=否 且 accident=是
  event_stage_coverage ∈ {仅后, 仅前+后}
  area_occluded_ratio ∈ {部分遮挡, 大部遮挡}

负样本困难：
  congestion_only=是
  hazard_light=是 且 accident=否
  near_miss=是 或 close_distance_pass=是
  abnormal_stop=是 且 accident=否
  hazard_light_chain=是
  queue_at_signal=是
```

### 10.4 结构与完整性校验（脚本自动执行）

```text
① 结构校验：JSON 必须包含全部块及其 p0/p1/p2 子对象，字段集合与本规范完全一致；
② 优先级校验：细标样本所有 p0 字段 ≠ 未标注；标准标注样本 p0+p1 字段 ≠ 未标注；
③ 适用性校验：scene 不适用的场景要素字段必须为"不适用"，适用的不得为"不适用"；
④ 互斥校验：collision_visible=是 与 collision_occluded=是 不得同时成立；
⑤ 正样本校验：accident=是 时准入规则必须满足，且 event.p0 四字段必须有效。
```

---

## 11. 标注流程与质检

### 11.1 标注流程（与 JSON 优先级分组一一对应）

```text
第 1 步（分诊，~15秒）  ：meta.scene + label 初判 + 是否值得细标
第 2 步（p0 层标注）    ：traffic.p0 → evidence.p0 → label.p0
                          （正样本补 event.p0：时间起止 + 事故区域）
第 3 步（p1 层标注）    ：env.p1 → scene_elements.p1 → evidence.p1 → event.p1
第 4 步（p2 层标注）    ：各块 p2（人力允许时）
第 5 步（自动处理）     ：derived 派生 + 结构/完整性校验
```

### 11.2 质检要求

| 项目 | 要求 |
|---|---|
| 双人标注 | 全部正样本 + 全部 hard 负样本的 **p0 子对象**双人独立标注 |
| 仲裁 | 双人 `accident` 或 `accident_type` 不一致 → 第三人仲裁 |
| 一致性指标 | `accident` 双人一致率 ≥ 95%，低于则回炉培训 |
| 抽检 | 普通负样本 10% 抽检；p1/p2 字段 5% 抽检 |
| 迭代 | 训练错误归因中发现的标注错误，回写修正并记录 |

---

## 12. 完整标注示例

### 示例 1：高速追尾事故（正样本，碰撞可见）

```json
{
  "meta": {
    "media_type": "video",
    "video_path": "/data/videos/hw_00123.mp4",
    "duration_sec": 20.0,
    "scene": "高速高架",
    "camera_view": "路侧固定",
    "annotator_id": "A03"
  },
  "env": {
    "p1": { "lighting": "白天", "visibility": "中" },
    "p2": { "weather": "雨", "road_surface": "湿滑", "glare_or_reflection": "否" }
  },
  "traffic": {
    "p0": { "traffic_flow": "某点中断", "flow_interruption_point": "是" },
    "p1": { "queue_present": "是", "pedestrian_gathering": "否" }
  },
  "scene_elements": {
    "p1": {
      "stop_position": "行车道",
      "emergency_lane_occupied": "否",
      "stop_in_lane": "是",
      "queue_at_signal": "不适用",
      "hazard_light_chain": "否",
      "sudden_brake_wave": "是",
      "rear_end_chain": "是",
      "vru_involved": "不适用",
      "guardrail_impact": "否",
      "debris_on_road": "是",
      "smoke_in_view": "不适用"
    },
    "p2": {
      "roadside_parking_present": "不适用",
      "double_parked": "不适用",
      "bus_stop_area": "不适用",
      "toll_queue": "不适用",
      "merge_conflict": "否",
      "weaving_conflict": "不适用",
      "reverse_or_retrograde": "否",
      "intersection_blocked": "不适用",
      "turn_conflict": "不适用",
      "red_light_running": "不适用",
      "signal_state_at_event": "不适用",
      "crosswalk_area": "不适用",
      "pedestrian_crossing_midblock": "不适用",
      "delivery_rider_involved": "不适用",
      "door_open_event": "不适用",
      "truck_involved": "是",
      "construction_zone": "否",
      "tunnel_zone": "不适用",
      "lighting_transition_artifact": "不适用",
      "narrow_shoulder": "不适用",
      "sharp_curve_area": "不适用",
      "ramp_type": "不适用"
    }
  },
  "evidence": {
    "p0": {
      "collision_visible": "是",
      "person_down": "否",
      "motor_vehicle_rollover": "否",
      "non_motor_rollover": "否",
      "vehicle_fire": "否",
      "collision_occluded": "否",
      "abnormal_stop": "是",
      "bypass_behavior": "是",
      "hazard_light": "是",
      "hazard_light_reason": "事故后",
      "congestion_only": "否",
      "smooth_pullover": "否",
      "near_miss": "否"
    },
    "p1": {
      "vehicle_deformation": "是",
      "debris_scatter": "是",
      "occlusion_type": "无遮挡",
      "abrupt_trajectory_change": "是",
      "posture_anomaly": "是",
      "people_exit_vehicle": "否",
      "close_distance_pass": "否"
    }
  },
  "event": {
    "p0": {
      "event_start_sec": 6.5,
      "event_end_sec": 14.0,
      "accident_area_box": [760, 320, 520, 340],
      "accident_area_location": "行车道内"
    },
    "p1": {
      "collision_moment_visible": "是",
      "pre_event_visible": "是",
      "post_event_visible": "是",
      "participants": [
        {
          "type": "货车",
          "role": "被动方",
          "behavior_before": "急刹",
          "state_after": "停止行车道",
          "hazard_light_after": "是",
          "roi_box": [820, 340, 420, 300]
        },
        {
          "type": "轿车",
          "role": "主动方",
          "behavior_before": "正常行驶",
          "state_after": "姿态歪斜",
          "hazard_light_after": "不可见",
          "roi_box": [780, 380, 300, 240]
        }
      ]
    },
    "p2": { "area_occluded_ratio": "无遮挡" }
  },
  "label": {
    "p0": { "accident": "是", "accident_type": "追尾", "confidence": "高" }
  },
  "derived": {
    "congestion": "是",
    "hard": false,
    "event_stage_coverage": "全过程"
  }
}
```

### 示例 2：隧道双闪链拥堵（困难负样本，仅标到 p1 层）

```json
{
  "meta": {
    "media_type": "video",
    "video_path": "/data/videos/tn_00456.mp4",
    "duration_sec": 20.0,
    "scene": "隧道",
    "camera_view": "隧道固定",
    "annotator_id": "A07"
  },
  "env": {
    "p1": { "lighting": "隧道暗光", "visibility": "中" },
    "p2": { "weather": "未标注", "road_surface": "未标注", "glare_or_reflection": "未标注" }
  },
  "traffic": {
    "p0": { "traffic_flow": "拥堵", "flow_interruption_point": "否" },
    "p1": { "queue_present": "是", "pedestrian_gathering": "否" }
  },
  "scene_elements": {
    "p1": {
      "stop_position": "无停车",
      "emergency_lane_occupied": "无应急车道",
      "stop_in_lane": "否",
      "queue_at_signal": "不适用",
      "hazard_light_chain": "是",
      "sudden_brake_wave": "否",
      "rear_end_chain": "不适用",
      "vru_involved": "不适用",
      "guardrail_impact": "不适用",
      "debris_on_road": "否",
      "smoke_in_view": "否"
    },
    "p2": {
      "roadside_parking_present": "不适用",
      "double_parked": "不适用",
      "bus_stop_area": "不适用",
      "toll_queue": "不适用",
      "merge_conflict": "不适用",
      "weaving_conflict": "不适用",
      "reverse_or_retrograde": "未标注",
      "intersection_blocked": "不适用",
      "turn_conflict": "不适用",
      "red_light_running": "不适用",
      "signal_state_at_event": "不适用",
      "crosswalk_area": "不适用",
      "pedestrian_crossing_midblock": "不适用",
      "delivery_rider_involved": "不适用",
      "door_open_event": "不适用",
      "truck_involved": "未标注",
      "construction_zone": "未标注",
      "tunnel_zone": "未标注",
      "lighting_transition_artifact": "未标注",
      "narrow_shoulder": "未标注",
      "sharp_curve_area": "不适用",
      "ramp_type": "不适用"
    }
  },
  "evidence": {
    "p0": {
      "collision_visible": "否",
      "person_down": "否",
      "motor_vehicle_rollover": "否",
      "non_motor_rollover": "否",
      "vehicle_fire": "否",
      "collision_occluded": "否",
      "abnormal_stop": "否",
      "bypass_behavior": "否",
      "hazard_light": "是",
      "hazard_light_reason": "拥堵缓行",
      "congestion_only": "是",
      "smooth_pullover": "否",
      "near_miss": "否"
    },
    "p1": {
      "vehicle_deformation": "否",
      "debris_scatter": "否",
      "occlusion_type": "无遮挡",
      "abrupt_trajectory_change": "否",
      "posture_anomaly": "否",
      "people_exit_vehicle": "否",
      "close_distance_pass": "否"
    }
  },
  "event": {
    "p0": {
      "event_start_sec": 0.0,
      "event_end_sec": 20.0,
      "accident_area_box": null,
      "accident_area_location": "不适用"
    },
    "p1": {
      "collision_moment_visible": "无碰撞",
      "pre_event_visible": "是",
      "post_event_visible": "是",
      "participants": []
    },
    "p2": { "area_occluded_ratio": "不适用" }
  },
  "label": {
    "p0": { "accident": "否", "accident_type": "无事故", "confidence": "高" }
  },
  "derived": {
    "congestion": "是",
    "hard": true,
    "event_stage_coverage": "全过程"
  }
}
```

---

## 13. 字段与训练任务的映射关系

| 训练任务 | 使用的标注字段（按优先级层直接取用） |
|---|---|
| 任务A 属性感知 | `meta.scene`、`traffic.p0`、`evidence.p0` 中的 hazard_light / abnormal_stop、`env.p1.lighting`、`scene_elements.p1` |
| 任务B 证据判断 | `evidence.p0` + `evidence.p1` 全部字段 |
| 任务C 对比判别 | `label.p0.accident` + `evidence.p0` 误报要素组合映射四选一答案 |
| 任务D 步骤化推理 | 第 1 步 ← `meta.scene`+`traffic`；第 2 步 ← `event.p1.participants`+误报要素；第 3 步 ← 直接/间接证据；第 4 步 ← `label.p0.accident` |
| 任务E 部署二分类 | `label.p0.accident` |
| 事故定位/grounding | `event.p0.accident_area_box`、`accident_area_location` |
| ROI 裁剪管线 | `event.p0.accident_area_box`（事件级）、`participants[].roi_box`（目标级）、`event.p0` 时间窗 |
| 分桶评估 | `derived.hard`、`meta.scene`、`env.p1`、`derived.event_stage_coverage`、`event.p2.area_occluded_ratio` |
| GRPO 数据筛选 | `label.p0.confidence`、`derived.hard`、准入规则 |

生成脚本按优先级取数的约定：

```text
p0 层字段 → 核心训练任务（任务 C/E 与关键属性 QA）
p1 层字段 → 推理文本生成（任务 D）与辅助任务（任务 A/B）
p2 层字段 → 只作元数据：分桶 / 筛选 / 统计，不生成训练监督信号
```

---

## 14. 附录：枚举值字典

```yaml
media_type: [video]
scene: [高速高架, 城市路口, 城市普通路段, 隧道, 匝道收费站, 其他]
camera_view: [路侧固定, 高点俯视, 卡口近景, 隧道固定, 其他]
lighting: [白天, 夜间, 黄昏黎明, 隧道暗光]
weather: [晴, 雨, 雪, 雾, 不确定]
road_surface: [干燥, 湿滑, 积水积雪, 不确定]
visibility: [高, 中, 低]
traffic_flow: [畅通, 缓行, 拥堵, 停止排队, 某点中断]
accident_type: [无事故, 追尾, 侧碰, 剐蹭, 正面碰撞, 撞行人非机动车, 侧翻, 撞固定物, 多车连环, 起火燃烧, 不确定]
occlusion_type: [无遮挡, 事故车自身遮挡, 其他车辆遮挡, 设施遮挡, 画面边缘盲区]
hazard_light_reason: [事故后, 拥堵缓行, 临时停车, 故障施工, 无双闪, 不明确]
accident_area_location: [行车道内, 路口中央, 应急车道, 路边, 匝道, 隧道行车道, 画面边缘, 不适用]
area_occluded_ratio: [无遮挡, 部分遮挡, 大部遮挡, 不适用]
participant_type: [轿车, SUV, 货车, 客车, 摩托车, 电动车, 自行车, 行人, 固定物]
participant_role: [主动方, 被动方, 受波及, 不确定]
behavior_before: [正常行驶, 变道, 转弯, 急刹, 超速感, 逆行倒车, 静止, 不确定]
state_after: [停止行车道, 停止路边, 驶离, 倒地, 侧翻, 姿态歪斜, 不确定]
event_stage_coverage: [全过程, 仅前+后, 仅后, 仅前, 不适用]
tri_state: [是, 否, 不确定]
tri_state_na: [是, 否, 不确定, 不适用]
placeholder: [未标注]
confidence: [高, 中, 低]
priority_level: [p0, p1, p2]
```
