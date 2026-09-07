# 交通事故视频素材结构化标注规范（v6）

> 目的：对路侧监控事故**视频**进行结构化、分场景的要素标注，
> 覆盖所有与"事故是否发生"判断相关的要素，
> 为多任务训练（属性感知 / 证据判断 / 对比判别 / 步骤化推理 / 二分类）提供统一数据基础。
>
> 配套文档：图片数据标注见《accident_annotation_spec_image.md》；
> 各要素判定标准见《accident_annotation_criteria.md》。
>
> v6 变更：时序属性由 `start_sec`/`end_sec` 改为 **`start_sec` / `end_sec` 时间窗**；
> 位置相关属性增加 **`bbox: [x,y,w,h]`** 坐标标注；`collision_moment_start_sec / collision_moment_end_sec` 拆为
> `collision_moment_start_sec` / `collision_moment_end_sec`。
> （v5 变更保留：`scene_elements` 按场景分对象。）
>
> 精简版见《accident_annotation_spec_video_core.md》；
> 带注释演示样例见 `annotation_examples/accident_annotation_example_video.jsonc`。

---

## 目录

1. [设计原则](#1-设计原则)
2. [标注优先级说明](#2-标注优先级说明)
3. [时间窗与坐标标注约定（视频专用）](#3-时间窗与坐标标注约定视频专用)
4. [固定 JSON 结构总览（按优先级分组）](#4-固定-json-结构总览按优先级分组)
5. [元信息与环境字段](#5-元信息与环境字段)
6. [交通流字段](#6-交通流字段)
7. [场景要素字段（按场景分对象）](#7-场景要素字段按场景分对象)
8. [证据链字段](#8-证据链字段)
9. [事件级字段（时间/区域/参与者）](#9-事件级字段时间区域参与者)
10. [最终标签与派生字段](#10-最终标签与派生字段)
11. [取值约定与一致性规则](#11-取值约定与一致性规则)
12. [标注流程与质检](#12-标注流程与质检)
13. [完整标注示例](#13-完整标注示例)
14. [字段与训练任务的映射关系](#14-字段与训练任务的映射关系)
15. [附录：枚举值字典](#15-附录枚举值字典)

---

## 1. 设计原则

1. **面向判别**：只标注与"事故是否发生"判断相关的要素，不做通用视频描述；
2. **JSON 顶层结构固定**：块集合一致；`scene_elements` 内按场景分对象，
   仅 `meta.scene` 对应场景填写字段，其余场景为空 `{}`；
3. **优先级内嵌于结构**：每个语义块内部按 `p0 / p1 / p2` 子对象分组，
   JSON 本身即优先级清单，训练数据生成与完整性校验直接按层遍历；
4. **证据与结论分离**：先标"看到了什么"（证据字段），再标"结论是什么"（事故标签）；
5. **时序属性必带时间窗（start_sec/end_sec）**：凡描述"某一时刻发生/首次可确认"的属性，必须标注 `start_sec`/`end_sec`（见第 3 节）；位置相关属性必须标注 `bbox`；
   状态/环境/结论类属性不加时间窗；
6. **不确定性显式化**：看不清、判不了的要素统一标"不确定"，禁止猜测；
7. **困难样本显式打标**：拥堵、双闪、near-miss、遮挡等易混淆样本自动派生 `hard` 标记。

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

## 3. 时间窗与坐标标注约定（视频专用）

> 图片标注不适用时间窗（无时序）；图片的坐标约定见图片规范。

### 3.1 时序属性取值对象

时序属性统一使用对象，**禁止**再写成纯字符串：

```json
{"value": "是", "start_sec": 6.5, "end_sec": 7.0}
```

若该属性同时具有画面位置（见 3.4），则带上 `bbox`：

```json
{"value": "是", "start_sec": 6.5, "end_sec": 7.0, "bbox": [780, 360, 280, 220]}
```

| 情况 | `value` | `start_sec` / `end_sec` | `bbox`（若适用） |
|---|---|---|---|
| 确认观察到 | `是`（或肯定枚举） | **必填**时间窗 | **必填**外接框 |
| 确认未发生 | `否` | 均为 `null` | `null` |
| 看不清 | `不确定` | 有候选可填，否则 `null` | 有候选可填，否则 `null` |
| 场景不适用 / 未标注 | `不适用` / `未标注` | `null` | `null` |

### 3.2 时间窗度量

| 约定 | 说明 |
|---|---|
| 原点 | 视频文件起点 = `0.0` |
| 单位 | 秒（`sec`） |
| 精度 | **0.1s**；`frame_idx / fps` |
| 范围 | `0 ≤ start_sec ≤ end_sec ≤ meta.duration_sec` |
| `start_sec` | 现象**首次可确认**出现的时刻 |
| `end_sec` | 现象结束、离开画面或状态稳定的时刻；瞬时事件可令 `end_sec = start_sec` |

### 3.3 时序属性清单（必须用 `{value, start_sec, end_sec}`）

| 所在块 | 字段 |
|---|---|
| `scene_elements.<场景>.p1` | `hazard_light_chain`、`sudden_brake_wave`、`rear_end_chain`、`guardrail_impact`、`debris_on_road`、`smoke_in_view` |
| `scene_elements.<场景>.p2` | `merge_conflict`、`weaving_conflict`、`reverse_or_retrograde`、`turn_conflict`、`red_light_running`、`door_open_event` |
| `evidence.p0` | `collision_visible`、`person_down`、`motor_vehicle_rollover`、`non_motor_rollover`、`vehicle_fire`、`abnormal_stop`、`bypass_behavior`、`hazard_light`、`smooth_pullover`、`near_miss` |
| `evidence.p1` | `debris_scatter`、`abrupt_trajectory_change`、`people_exit_vehicle`、`close_distance_pass` |

### 3.4 坐标标注约定 `bbox`

| 约定 | 说明 |
|---|---|
| 格式 | `[x, y, w, h]`：左上角像素坐标 + 宽高 |
| 坐标系 | 相对**整帧画面**，原点在左上 |
| 必标条件 | 位置相关属性且 `value` 为肯定（或"不确定"但区域可估）时必填 |
| 否定/不适用 | `bbox = null` |

**位置相关属性**（须带 `bbox`，可与时间窗并存）：

| 所在块 | 字段 |
|---|---|
| `traffic` | `flow_interruption_point`（中断点区域） |
| `scene_elements.<场景>` | `stop_position`、`stop_in_lane`、`emergency_lane_occupied`（为"是"/有停车时）、以及第 3.3 节全部时序场景字段 |
| `evidence` | `collision_visible`、`person_down`、两类侧翻、`vehicle_fire`、`abnormal_stop`、`bypass_behavior`、`hazard_light`、`smooth_pullover`、`near_miss`、`debris_scatter`、`abrupt_trajectory_change`、`people_exit_vehicle`、`close_distance_pass`、`vehicle_deformation`、`posture_anomaly` |
| `event` | `accident_area_box`（事件级区域，格式同 bbox）；`participants[].roi_box` |

### 3.5 事件级纯时间字段

| 字段 | 优先级 | 说明 |
|---|---|---|
| `event.p0.event_start_sec` | P0 | 事件开始（负样本填 0） |
| `event.p0.event_end_sec` | P0 | 事件结束（负样本填视频时长） |
| `event.p1.collision_moment_start_sec` | P1 | 碰撞接触开始；无碰撞/不可见填 `null` |
| `event.p1.collision_moment_end_sec` | P1 | 碰撞接触结束；瞬时碰撞可与 start 相同或 +0.2s |

### 3.6 不加时间窗的字段（状态 / 环境 / 结论）

`env.*`、`label.*`、`occlusion_type`、`collision_occluded`、`congestion_only`、
`hazard_light_reason`、`traffic_flow`、排队类、灯态类、以及纯类别枚举等。
其中部分位置类字段仍须按 3.4 带 `bbox`（如 `stop_position`）。

---

## 4. 固定 JSON 结构总览（按优先级分组）

**每条视频输出一条 JSON，结构与字段集合固定不变**。每个语义块内部按优先级分组：

```json
{
  "meta":    { "...": "工具自动填，不分优先级，见第5节" },
  "env":     { "p1": { }, "p2": { } },
  "traffic": { "p0": { }, "p1": { } },
  "scene_elements": {
    "高速高架":     { "p1": { }, "p2": { } },
    "城市路口":     { "p1": { }, "p2": { } },
    "城市普通路段": { "p1": { }, "p2": { } },
    "隧道":         { "p1": { }, "p2": { } },
    "匝道收费站":   { "p1": { }, "p2": { } },
    "其他":         { "p1": { }, "p2": { } }
  },
  "evidence": { "p0": { }, "p1": { } },
  "event":    { "p0": { }, "p1": { }, "p2": { } },
  "label":    { "p0": { } },
  "derived":  { "...": "脚本自动派生字段，见第10节" }
}
```

约定：

1. 每个块内的 `p0/p1/p2` 子对象**始终存在**（即使为空对象也保留键）；
2. `scene_elements` 六个场景键**始终存在**；非当前场景为 `{"p1":{},"p2":{}}`；
3. 未到达对应标注层级时，字段填占位值 `未标注`（区别于"不确定"）；
4. `meta` 与 `derived` 不参与人工优先级——前者工具自动填，后者脚本自动算。

---

## 5. 元信息与环境字段

### 5.1 元信息 `meta`（工具自动填，无优先级分组）

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

### 5.2 环境条件 `env`

| 子对象 | 字段 | 取值 | 与事故判断的关系 |
|---|---|---|---|
| **p1** | `lighting` | 白天 / 夜间 / 黄昏黎明 / 隧道暗光 | 影响细节可辨识度，分桶评估用 |
| **p1** | `visibility` | 高 / 中 / 低 | 低能见度样本单独分桶 |
| **p2** | `weather` | 晴 / 雨 / 雪 / 雾 / 不确定 | 雨雪天误报高发 |
| **p2** | `road_surface` | 干燥 / 湿滑 / 积水积雪 / 不确定 | 湿滑路面事故形态不同 |
| **p2** | `glare_or_reflection` | 是 / 否 | 夜间反光易误判双闪 |

---

## 6. 交通流字段

### 交通流 `traffic`

| 子对象 | 字段 | 取值 | 说明 |
|---|---|---|---|
| **p0** | `traffic_flow` | 畅通 / 缓行 / 拥堵 / 停止排队 / 某点中断 | **"某点中断"是事故最强间接信号** |
| **p0** | `flow_interruption_point` | `{value, bbox}` | 固定中断点；肯定时 bbox 标中断区域 |
| **p1** | `queue_present` | 是 / 否 | 是否排队 |
| **p1** | `pedestrian_gathering` | 是 / 否 | 人员在车行道聚集（事故后常见） |

> `congestion` 由 `traffic_flow` 自动派生，见第 10 节 `derived`。

---

## 7. 场景要素字段（按场景分对象）

`scene_elements` 按场景拆分为独立子对象；键名与 `meta.scene` 枚举一致：

```json
{
  "scene_elements": {
    "高速高架": { "p1": { }, "p2": { } },
    "城市路口": { "p1": { }, "p2": { } },
    "城市普通路段": { "p1": { }, "p2": { } },
    "隧道": { "p1": { }, "p2": { } },
    "匝道收费站": { "p1": { }, "p2": { } },
    "其他": { "p1": { }, "p2": { } }
  }
}
```

约定：

1. **六个场景键始终存在**；
2. 仅 `meta.scene` 对应的场景对象填写字段；其余场景对象固定为
   `{"p1": {}, "p2": {}}`；
3. 不再使用跨场景扁平字段 + `不适用` 锁定；场景差异通过「不同场景对象」表达；
4. 各场景对象内部仍按 `p1 / p2` 分组（场景要素无 p0 层）。

### `高速高架`

#### p1（主力字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `stop_position` | `{value, bbox}`：行车道 / 应急车道 / 路边 / 无停车 | 事故停车 vs 临停核心判别点 |
| `emergency_lane_occupied` | `{value, bbox}`：是 / 否 / 无应急车道 | 应急车道停车多为故障临停；行车道停车为强事故信号 |
| `stop_in_lane` | `{value, bbox}`：是 / 否 | 隧道/高速行车道停车事故概率高 |
| `hazard_light_chain` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 多车依次开双闪提醒后车（不是事故）；start/end=双闪链起止；含 bbox |
| `sudden_brake_wave` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 上游连锁急刹（事故前兆）；start/end=急刹波起止；含 bbox |
| `rear_end_chain` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 多车追尾链；start/end=追尾链起止；含 bbox |
| `guardrail_impact` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}`/不确定 | 撞护栏；start/end=撞击起止；含 bbox |
| `debris_on_road` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}`/不确定 | 路面抛洒物/碎片；start/end + bbox |

#### p2（次要字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `merge_conflict` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 汇入冲突；start/end + bbox |
| `reverse_or_retrograde` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 倒车/逆行；start/end + bbox |
| `truck_involved` | 纯枚举：是 / 否 | 货车卷入 |
| `construction_zone` | 纯枚举：是 / 否 | 施工区域 |

### `城市路口`

#### p1（主力字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `stop_position` | `{value, bbox}`：行车道 / 应急车道 / 路边 / 无停车 | 事故停车 vs 临停核心判别点 |
| `queue_at_signal` | 纯枚举：是 / 否 | 等灯静止 ≠ 事故（路口最常见误报源） |
| `vru_involved` | 纯枚举：行人 / 非机动车 / 两者 / 无 | 弱势交通参与者卷入 |

#### p2（次要字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `intersection_blocked` | 纯枚举：是 / 否 | 路口被堵死 |
| `turn_conflict` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 转弯冲突；start/end + bbox |
| `red_light_running` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}`/不确定 | 闯红灯；start/end + bbox |
| `signal_state_at_event` | 纯枚举：红 / 绿 / 黄 / 闪烁 / 不可见 | 取事件开始时刻的灯态 |
| `crosswalk_area` | 纯枚举：是 / 否 | 人行横道区域 |
| `delivery_rider_involved` | 纯枚举：是 / 否 | 外卖骑手卷入 |
| `truck_involved` | 纯枚举：是 / 否 | 货车卷入 |
| `construction_zone` | 纯枚举：是 / 否 | 施工区域 |

### `城市普通路段`

#### p1（主力字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `stop_position` | `{value, bbox}`：行车道 / 应急车道 / 路边 / 无停车 | 事故停车 vs 临停核心判别点 |
| `vru_involved` | 纯枚举：行人 / 非机动车 / 两者 / 无 | 弱势交通参与者卷入 |

#### p2（次要字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `roadside_parking_present` | 纯枚举：是 / 否 | 路边停车 |
| `double_parked` | 纯枚举：是 / 否 | 双排停车 |
| `bus_stop_area` | 纯枚举：是 / 否 | 公交站区域 |
| `crosswalk_area` | 纯枚举：是 / 否 | 人行横道区域 |
| `pedestrian_crossing_midblock` | 纯枚举：是 / 否 | 路段中穿行 |
| `delivery_rider_involved` | 纯枚举：是 / 否 | 外卖骑手卷入 |
| `door_open_event` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}`/不确定 | 开车门事件；start/end + bbox |
| `truck_involved` | 纯枚举：是 / 否 | 货车卷入 |
| `construction_zone` | 纯枚举：是 / 否 | 施工区域 |

### `隧道`

#### p1（主力字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `stop_position` | `{value, bbox}`：行车道 / 应急车道 / 路边 / 无停车 | 事故停车 vs 临停核心判别点 |
| `emergency_lane_occupied` | `{value, bbox}`：是 / 否 / 无应急车道 | 应急车道停车多为故障临停；行车道停车为强事故信号 |
| `stop_in_lane` | `{value, bbox}`：是 / 否 | 隧道/高速行车道停车事故概率高 |
| `hazard_light_chain` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 多车依次开双闪提醒后车（不是事故）；start/end=双闪链起止；含 bbox |
| `sudden_brake_wave` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 上游连锁急刹（事故前兆）；start/end=急刹波起止；含 bbox |
| `debris_on_road` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}`/不确定 | 路面抛洒物/碎片；start/end + bbox |
| `smoke_in_view` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}`/不确定 | 隧道烟雾（着火用 evidence.vehicle_fire）；start/end + bbox |

#### p2（次要字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `reverse_or_retrograde` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 倒车/逆行；start/end + bbox |
| `truck_involved` | 纯枚举：是 / 否 | 货车卷入 |
| `construction_zone` | 纯枚举：是 / 否 | 施工区域 |
| `tunnel_zone` | 纯枚举：入口段 / 中段 / 出口段 | 隧道区段 |
| `lighting_transition_artifact` | 纯枚举：是 / 否 | 出入口光强突变伪影 |
| `narrow_shoulder` | 纯枚举：有硬路肩 / 无硬路肩 | 硬路肩有无 |

### `匝道收费站`

#### p1（主力字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `stop_position` | `{value, bbox}`：行车道 / 应急车道 / 路边 / 无停车 | 事故停车 vs 临停核心判别点 |
| `guardrail_impact` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}`/不确定 | 撞护栏；start/end=撞击起止；含 bbox |

#### p2（次要字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `toll_queue` | 纯枚举：是 / 否 | 收费站排队 |
| `merge_conflict` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 汇入冲突；start/end + bbox |
| `weaving_conflict` | 时序+坐标对象：`{value,start_sec,end_sec,bbox}` | 交织冲突；start/end + bbox |
| `truck_involved` | 纯枚举：是 / 否 | 货车卷入 |
| `construction_zone` | 纯枚举：是 / 否 | 施工区域 |
| `sharp_curve_area` | 纯枚举：是 / 否 | 急弯区域 |
| `ramp_type` | 纯枚举：上匝道 / 下匝道 / 收费站广场 / 不确定 | 匝道/收费站类型 |

### `其他`

#### p1（主力字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `stop_position` | `{value, bbox}`：行车道 / 应急车道 / 路边 / 无停车 | 事故停车 vs 临停核心判别点 |

#### p2（次要字段）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `truck_involved` | 纯枚举：是 / 否 | 货车卷入 |
| `construction_zone` | 纯枚举：是 / 否 | 施工区域 |

---

## 8. 证据链字段

> 时序对象格式见第 3 节：`{"value","start_sec","end_sec"}`；位置相关另含 `bbox`。
> 规则与准入判断时，对时序字段一律读其 `.value`。

### 8.1 p0 子对象（事故判定核心证据）

**直接证据（均为时序对象）：**

| 字段 | value 取值 | start/end 含义 | bbox |
|---|---|---|
| `collision_visible` | 是 / 否 / 不确定 | 碰撞过程时间窗 | 碰撞区域 |
| `person_down` | 是 / 否 / 不确定 | 倒地时间窗 | 倒地目标 |
| `motor_vehicle_rollover` | 是 / 否 / 不确定 | 侧翻时间窗 | 侧翻车辆 |
| `non_motor_rollover` | 是 / 否 / 不确定 | 侧翻时间窗 | 侧翻目标 |
| `vehicle_fire` | 是 / 否 / 不确定 | 着火时间窗 | 着火车辆 |

**间接证据核心：**

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `collision_occluded` | 纯枚举：是 / 否 | 碰撞点被遮挡（与 collision_visible.value="是" 互斥）；状态字段，无时间窗 |
| `abnormal_stop` | **时序+坐标对象** | 异常停止；start=静止时刻，end=持续至稳定；bbox=车辆 |
| `bypass_behavior` | **时序+坐标对象** | 周围车辆绕行；start/end=绕行起止；bbox=绕行区域 |

**误报判别要素：**

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `hazard_light` | **时序+坐标对象** | 双闪（须逐帧确认闪烁）；start/end=双闪起止；bbox=车辆 |
| `hazard_light_reason` | 纯枚举：事故后 / 拥堵缓行 / 临时停车 / 故障施工 / 无双闪 / 不明确 | 双闪原因（结论类，无时间窗） |
| `congestion_only` | 纯枚举：是 / 否 | 仅拥堵、无任何碰撞证据（结论类） |
| `smooth_pullover` | **时序+坐标对象** | 平稳减速靠边；start/end=靠边起止；bbox=车辆 |
| `near_miss` | **时序+坐标对象** | 险情但未碰撞；start/end=最险时间窗；bbox=近接区域 |

### 8.2 p1 子对象（证据链补全）

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `vehicle_deformation` | 纯枚举：是 / 否 / 不确定 | 车损可见（远景一律"不确定"，不标"否"；状态类） |
| `debris_scatter` | **时序+坐标对象** | 事件前后路面新出现碎片；start/end + bbox |
| `occlusion_type` | 纯枚举：无遮挡 / 事故车自身遮挡 / 其他车辆遮挡 / 设施遮挡 / 画面边缘盲区 | 遮挡类型（状态类） |
| `abrupt_trajectory_change` | **时序+坐标对象** | 轨迹突变；start/end + bbox |
| `posture_anomaly` | 纯枚举：是 / 否 / 不确定 | 停止后姿态歪斜/位置异常（状态类） |
| `people_exit_vehicle` | **时序+坐标对象** | 人员下车查看/聚集；start/end + bbox |
| `close_distance_pass` | **时序+坐标对象** | 近距离通过但无接触；start/end + bbox |

---

## 9. 事件级字段（时间/区域/参与者)

> `event` 块结构固定。负样本中：p0 时间字段填 0/时长，`accident_area` 各字段填
> null/不适用，`participants` 为空数组，`collision_moment_start_sec / collision_moment_end_sec` 填 `null`。

### 9.1 p0 子对象（正样本必标）

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_start_sec` | float | 事件开始时刻（碰撞或首个异常行为；负样本填 0） |
| `event_end_sec` | float | 事件结束时刻（状态稳定；负样本填视频时长） |
| `accident_area_box` | [x, y, w, h] 或 null | **事故区域**画面外接框（覆盖全部涉事目标与碎片；负样本 null） |
| `accident_area_location` | 行车道内 / 路口中央 / 应急车道 / 路边 / 匝道 / 隧道行车道 / 画面边缘 / 不适用 | 事故区域道路位置类别 |

> `accident_area_box` 与参与者 `roi_box` 的区别：前者是**事件级**整体事故区域
> （事故定位/grounding/ROI 视频裁剪用）；后者是**单个参与者**的活动区域框。

### 9.2 p1 子对象

| 字段 | 类型/取值 | 说明 |
|---|---|---|
| `collision_moment_visible` | 是 / 否 / 无碰撞 | 碰撞瞬间是否可见 |
| `collision_moment_start_sec` | float 或 null | 碰撞接触开始；`collision_moment_visible=是` 时必填 |
| `collision_moment_end_sec` | float 或 null | 碰撞接触结束；瞬时可与 start 相同或 +0.2s |
| `pre_event_visible` | 是 / 否 | 事件前正常状态可见 |
| `post_event_visible` | 是 / 否 | 事件后状态可见 |
| `participants` | array | 参与者列表（结构见 9.4；负样本为空数组） |

> 一致性：`collision_visible.value=是` 时，通常 `collision_moment_start_sec / collision_moment_end_sec` 应等于或接近
> `collision_visible.start_sec`，且落在 `[event_start_sec, event_end_sec]` 内。

### 9.3 p2 子对象

| 字段 | 取值 | 说明 |
|---|---|---|
| `area_occluded_ratio` | 无遮挡 / 部分遮挡 / 大部遮挡 / 不适用 | 事故区域被遮挡程度 |

### 9.4 参与者对象结构（`event.p1.participants[]`）

| 字段 | 优先级性质 | 取值 |
|---|---|---|
| `type` | p1 | 轿车 / SUV / 货车 / 客车 / 摩托车 / 电动车 / 自行车 / 行人 / 固定物 |
| `role` | p1 | 主动方 / 被动方 / 受波及 / 不确定 |
| `behavior_before` | p1 | 正常行驶 / 变道 / 转弯 / 急刹 / 超速感 / 逆行倒车 / 静止 / 不确定 |
| `state_after` | p1 | 停止行车道 / 停止路边 / 驶离 / 倒地 / 侧翻 / 姿态歪斜 / 不确定 |
| `hazard_light_after` | p2 | 是 / 否 / 不可见 |
| `roi_box` | p2 | [x, y, w, h]（可由检测器预填） |

---

## 10. 最终标签与派生字段

### 10.1 最终标签 `label`（全部 p0）

| 字段 | 取值 | 说明 |
|---|---|---|
| `accident` | 是 / 否 / 不确定 | 最终事故标签（准入规则见 11.2；"不确定"不入训练集） |
| `accident_type` | 无事故 / 追尾 / 侧碰 / 剐蹭 / 正面碰撞 / 撞行人非机动车 / 侧翻 / 撞固定物 / 多车连环 / 起火燃烧 / 不确定 | 事故类型 |
| `confidence` | 高 / 中 / 低 | 标注员对结论的信心 |

### 10.2 派生字段 `derived`（脚本自动计算，人工不填）

| 字段 | 派生规则 |
|---|---|
| `congestion` | traffic_flow ∈ {拥堵, 停止排队} → 是；{畅通, 缓行} → 否；某点中断 → 按上游状态 |
| `hard` | 见 11.3 困难样本派生规则 |
| `event_stage_coverage` | 由 collision_moment_visible / pre_event_visible / post_event_visible 组合派生：全过程 / 仅前+后 / 仅后 / 仅前 / 不适用 |

---

## 11. 取值约定与一致性规则

### 11.1 取值约定

1. 所有布尔类字段只允许：**是 / 否 / 不确定**（部分字段额外允许"不适用/无/不可见"，见各表）；
2. **时序属性**必须为 `{value, start_sec, end_sec}` 对象（见第 3 节），禁止写成纯字符串；
3. 场景差异通过空场景对象表达，场景要素字段本身不再使用 `不适用`；
   事件级字段仍可用 `不适用`（如负样本 `accident_area_location`）；
4. **`未标注`** 是分层占位值：仅允许出现在尚未到达标注层级的 p1/p2 字段中，
   p0 字段在细标样本中不得为"未标注"；
5. "不确定"的使用标准：正常速度播放 + 逐帧回看后仍无法判断。

### 11.2 事故正样本准入规则

`accident=是` 必须满足以下之一（时序字段读 `.value`）：

```text
① collision_visible.value = 是（碰撞过程可见）
② collision_occluded = 是，且以下间接证据 ≥ 2 项 value="是"：
   abnormal_stop / abrupt_trajectory_change / posture_anomaly /
   bypass_behavior / flow_interruption_point / people_exit_vehicle
③ 事故后强证据任一 value="是"：
   person_down / motor_vehicle_rollover / non_motor_rollover /
   vehicle_fire ；或 vehicle_deformation = 是
```

不满足准入规则的疑似事故 → `accident=不确定`，不进训练集，单独归档。

### 11.3 困难样本自动派生规则（`derived.hard = true` 条件）

```text
正样本困难：
  collision_visible.value=否 且 accident=是
  event_stage_coverage ∈ {仅后, 仅前+后}
  area_occluded_ratio ∈ {部分遮挡, 大部遮挡}

负样本困难：
  congestion_only=是
  hazard_light.value=是 且 accident=否
  near_miss.value=是 或 close_distance_pass.value=是
  abnormal_stop.value=是 且 accident=否
  scene_elements[<scene>].p1.hazard_light_chain.value=是
  scene_elements[<scene>].p1.queue_at_signal=是
```

### 11.4 结构与完整性校验（脚本自动执行）

```text
① 结构校验：JSON 必须包含全部块及其 p0/p1/p2 子对象，字段集合与本规范完全一致；
② 优先级校验：细标样本所有 p0 字段 ≠ 未标注；标准标注样本 p0+p1 字段 ≠ 未标注；
③ 场景对象校验：`scene_elements` 必须含全部六个场景键；仅 `meta.scene` 对应对象
   可含非空字段，其余场景必须为 `{"p1":{},"p2":{}}`；
④ 互斥校验：collision_visible.value=是 与 collision_occluded=是 不得同时成立；
⑤ 正样本校验：accident=是 时准入规则必须满足，且 event.p0 四字段必须有效；
⑥ 时间窗校验（视频专用）：
   - 时序属性：value 肯定时 start_sec/end_sec 必为数字且
     0 ≤ start_sec ≤ end_sec ≤ duration_sec；否定/不适用/未标注时二者均为 null；
   - event_start_sec ≤ event_end_sec；正样本时间窗落在 [0, duration_sec]；
   - collision_moment_visible=是 时 collision_moment_start/end_sec 必填且落在
     [event_start_sec, event_end_sec]；=无碰撞/否 时二者均为 null；
   - 时序属性时间窗建议与事件窗重叠或相邻（预警类可早于 event_start）；
⑦ 坐标校验：位置相关属性 value 肯定时 bbox 必为 [x,y,w,h] 且落在画面内；
   否定/不适用时 bbox=null；accident_area_box 与 participants[].roi_box 同理。
```

---

## 12. 标注流程与质检

### 12.1 标注流程（与 JSON 优先级分组一一对应）

```text
第 1 步（分诊，~15秒）  ：meta.scene + label 初判 + 是否值得细标
第 2 步（p0 层标注）    ：traffic.p0 → evidence.p0（含时序时间窗与坐标）→ label.p0
                          （正样本补 event.p0：时间起止 + 事故区域）
第 3 步（p1 层标注）    ：env.p1 → scene_elements.p1 → evidence.p1 → event.p1
                          （含 collision_moment_start_sec / collision_moment_end_sec 与时序属性时间窗/坐标）
第 4 步（p2 层标注）    ：各块 p2（人力允许时）
第 5 步（自动处理）     ：derived 派生 + 结构/完整性校验
```

### 12.2 质检要求

| 项目 | 要求 |
|---|---|
| 双人标注 | 全部正样本 + 全部 hard 负样本的 **p0 子对象**双人独立标注 |
| 仲裁 | 双人 `accident` 或 `accident_type` 不一致 → 第三人仲裁 |
| 一致性指标 | `accident` 双人一致率 ≥ 95%，低于则回炉培训 |
| 抽检 | 普通负样本 10% 抽检；p1/p2 字段 5% 抽检 |
| 迭代 | 训练错误归因中发现的标注错误，回写修正并记录 |

---

## 13. 完整标注示例

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
    "p1": {
      "lighting": "白天",
      "visibility": "中"
    },
    "p2": {
      "weather": "雨",
      "road_surface": "湿滑",
      "glare_or_reflection": "否"
    }
  },
  "traffic": {
    "p0": {
      "traffic_flow": "某点中断",
      "flow_interruption_point": {
        "value": "是",
        "bbox": [
          750,
          300,
          500,
          360
        ]
      }
    },
    "p1": {
      "queue_present": "是",
      "pedestrian_gathering": "否"
    }
  },
  "scene_elements": {
    "高速高架": {
      "p1": {
        "stop_position": {
          "value": "行车道",
          "bbox": [
            800,
            340,
            420,
            300
          ]
        },
        "emergency_lane_occupied": {
          "value": "否",
          "bbox": null
        },
        "stop_in_lane": {
          "value": "是",
          "bbox": [
            800,
            340,
            420,
            300
          ]
        },
        "hazard_light_chain": {
          "value": "否",
          "start_sec": null,
          "end_sec": null,
          "bbox": null
        },
        "sudden_brake_wave": {
          "value": "是",
          "start_sec": 5.8,
          "end_sec": 7.3,
          "bbox": [
            600,
            200,
            700,
            350
          ]
        },
        "rear_end_chain": {
          "value": "是",
          "start_sec": 6.5,
          "end_sec": 7.5,
          "bbox": [
            760,
            320,
            520,
            340
          ]
        },
        "guardrail_impact": {
          "value": "否",
          "start_sec": null,
          "end_sec": null,
          "bbox": null
        },
        "debris_on_road": {
          "value": "是",
          "start_sec": 6.8,
          "end_sec": 7.3,
          "bbox": [
            760,
            480,
            160,
            80
          ]
        }
      },
      "p2": {
        "merge_conflict": {
          "value": "否",
          "start_sec": null,
          "end_sec": null,
          "bbox": null
        },
        "reverse_or_retrograde": {
          "value": "否",
          "start_sec": null,
          "end_sec": null,
          "bbox": null
        },
        "truck_involved": "是",
        "construction_zone": "否"
      }
    },
    "城市路口": {
      "p1": {},
      "p2": {}
    },
    "城市普通路段": {
      "p1": {},
      "p2": {}
    },
    "隧道": {
      "p1": {},
      "p2": {}
    },
    "匝道收费站": {
      "p1": {},
      "p2": {}
    },
    "其他": {
      "p1": {},
      "p2": {}
    }
  },
  "evidence": {
    "p0": {
      "collision_visible": {
        "value": "是",
        "start_sec": 6.5,
        "end_sec": 6.8,
        "bbox": [
          780,
          360,
          280,
          220
        ]
      },
      "person_down": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "motor_vehicle_rollover": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "non_motor_rollover": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "vehicle_fire": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "collision_occluded": "否",
      "abnormal_stop": {
        "value": "是",
        "start_sec": 7.2,
        "end_sec": 14.0,
        "bbox": [
          800,
          340,
          420,
          300
        ]
      },
      "bypass_behavior": {
        "value": "是",
        "start_sec": 8.0,
        "end_sec": 14.0,
        "bbox": [
          700,
          280,
          600,
          400
        ]
      },
      "hazard_light": {
        "value": "是",
        "start_sec": 7.5,
        "end_sec": 14.0,
        "bbox": [
          820,
          340,
          420,
          300
        ]
      },
      "hazard_light_reason": "事故后",
      "congestion_only": "否",
      "smooth_pullover": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "near_miss": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      }
    },
    "p1": {
      "vehicle_deformation": {
        "value": "是",
        "bbox": [
          780,
          380,
          300,
          240
        ]
      },
      "debris_scatter": {
        "value": "是",
        "start_sec": 6.8,
        "end_sec": 7.3,
        "bbox": [
          760,
          480,
          160,
          80
        ]
      },
      "occlusion_type": "无遮挡",
      "abrupt_trajectory_change": {
        "value": "是",
        "start_sec": 6.5,
        "end_sec": 7.0,
        "bbox": [
          780,
          380,
          300,
          240
        ]
      },
      "posture_anomaly": {
        "value": "是",
        "bbox": [
          780,
          380,
          300,
          240
        ]
      },
      "people_exit_vehicle": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "close_distance_pass": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      }
    }
  },
  "event": {
    "p0": {
      "event_start_sec": 6.5,
      "event_end_sec": 14.0,
      "accident_area_box": [
        760,
        320,
        520,
        340
      ],
      "accident_area_location": "行车道内"
    },
    "p1": {
      "collision_moment_visible": "是",
      "collision_moment_start_sec / collision_moment_end_sec": 6.5,
      "pre_event_visible": "是",
      "post_event_visible": "是",
      "participants": [
        {
          "type": "货车",
          "role": "被动方",
          "behavior_before": "急刹",
          "state_after": "停止行车道",
          "hazard_light_after": "是",
          "roi_box": [
            820,
            340,
            420,
            300
          ]
        },
        {
          "type": "轿车",
          "role": "主动方",
          "behavior_before": "正常行驶",
          "state_after": "姿态歪斜",
          "hazard_light_after": "不可见",
          "roi_box": [
            780,
            380,
            300,
            240
          ]
        }
      ]
    },
    "p2": {
      "area_occluded_ratio": "无遮挡"
    }
  },
  "label": {
    "p0": {
      "accident": "是",
      "accident_type": "追尾",
      "confidence": "高"
    }
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
    "p1": {
      "lighting": "隧道暗光",
      "visibility": "中"
    },
    "p2": {
      "weather": "未标注",
      "road_surface": "未标注",
      "glare_or_reflection": "未标注"
    }
  },
  "traffic": {
    "p0": {
      "traffic_flow": "拥堵",
      "flow_interruption_point": {
        "value": "否",
        "bbox": null
      }
    },
    "p1": {
      "queue_present": "是",
      "pedestrian_gathering": "否"
    }
  },
  "scene_elements": {
    "高速高架": {
      "p1": {},
      "p2": {}
    },
    "城市路口": {
      "p1": {},
      "p2": {}
    },
    "城市普通路段": {
      "p1": {},
      "p2": {}
    },
    "隧道": {
      "p1": {
        "stop_position": {
          "value": "无停车",
          "bbox": null
        },
        "emergency_lane_occupied": {
          "value": "无应急车道",
          "bbox": [
            50,
            400,
            200,
            180
          ]
        },
        "stop_in_lane": {
          "value": "否",
          "bbox": null
        },
        "hazard_light_chain": {
          "value": "是",
          "start_sec": 3.0,
          "end_sec": 20.0,
          "bbox": [
            300,
            250,
            900,
            400
          ]
        },
        "sudden_brake_wave": {
          "value": "否",
          "start_sec": null,
          "end_sec": null,
          "bbox": null
        },
        "debris_on_road": {
          "value": "否",
          "start_sec": null,
          "end_sec": null,
          "bbox": null
        },
        "smoke_in_view": {
          "value": "否",
          "start_sec": null,
          "end_sec": null,
          "bbox": null
        }
      },
      "p2": {
        "reverse_or_retrograde": {
          "value": "未标注",
          "start_sec": null,
          "end_sec": null,
          "bbox": null
        },
        "truck_involved": "未标注",
        "construction_zone": "未标注",
        "tunnel_zone": "未标注",
        "lighting_transition_artifact": "未标注",
        "narrow_shoulder": "未标注"
      }
    },
    "匝道收费站": {
      "p1": {},
      "p2": {}
    },
    "其他": {
      "p1": {},
      "p2": {}
    }
  },
  "evidence": {
    "p0": {
      "collision_visible": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "person_down": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "motor_vehicle_rollover": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "non_motor_rollover": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "vehicle_fire": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "collision_occluded": "否",
      "abnormal_stop": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "bypass_behavior": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "hazard_light": {
        "value": "是",
        "start_sec": 3.0,
        "end_sec": 20.0,
        "bbox": [
          820,
          340,
          420,
          300
        ]
      },
      "hazard_light_reason": "拥堵缓行",
      "congestion_only": "是",
      "smooth_pullover": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "near_miss": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      }
    },
    "p1": {
      "vehicle_deformation": {
        "value": "否",
        "bbox": null
      },
      "debris_scatter": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "occlusion_type": "无遮挡",
      "abrupt_trajectory_change": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "posture_anomaly": {
        "value": "否",
        "bbox": null
      },
      "people_exit_vehicle": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      },
      "close_distance_pass": {
        "value": "否",
        "start_sec": null,
        "end_sec": null,
        "bbox": null
      }
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
      "collision_moment_start_sec / collision_moment_end_sec": null,
      "pre_event_visible": "是",
      "post_event_visible": "是",
      "participants": []
    },
    "p2": {
      "area_occluded_ratio": "不适用"
    }
  },
  "label": {
    "p0": {
      "accident": "否",
      "accident_type": "无事故",
      "confidence": "高"
    }
  },
  "derived": {
    "congestion": "是",
    "hard": true,
    "event_stage_coverage": "全过程"
  }
}
```

---

## 14. 字段与训练任务的映射关系

| 训练任务 | 使用的标注字段（按优先级层直接取用） |
|---|---|
| 任务A 属性感知 | `meta.scene`、`traffic.p0`、`evidence.p0` 中的 hazard_light / abnormal_stop、`env.p1.lighting`、`scene_elements[<scene>].p1` |
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

## 15. 附录：枚举值字典

```yaml
# 时序属性：{value, start_sec, end_sec[, bbox]}
# 位置属性：{value, bbox[, start_sec, end_sec]}
# 见第 3 节清单；以下枚举为各字段的 value 取值空间
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
timed_value_object: "{value, start_sec, end_sec, bbox?}"
located_value_object: "{value, bbox, start_sec?, end_sec?}"
bbox: "[x, y, w, h] | null"
event_time_fields: [event_start_sec, event_end_sec, collision_moment_start_sec, collision_moment_end_sec]
placeholder: [未标注]
confidence: [高, 中, 低]
priority_level: [p0, p1, p2]
```
