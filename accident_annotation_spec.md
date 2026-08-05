# 交通事故视频素材结构化标注规范（分场景版 v2）

> 目的：对路侧监控事故视频进行**结构化、分场景**的要素标注，
> 覆盖所有与"事故是否发生"判断相关的要素，
> 为多任务训练（属性感知 / 证据判断 / 对比判别 / 步骤化推理 / 二分类）提供统一数据基础。
>
> v2 变更：
> ① JSON 结构固定化——所有场景输出**完全相同的字段集合**，场景差异通过字段取值"不适用"体现；
> ② 新增/拆分字段：机动车侧翻、非机动车侧翻、机动车着火、事故区域；
> ③ 全部字段标注优先级（P0/P1/P2），支持按优先级分层标注以节省人力。

---

## 目录

1. [设计原则](#1-设计原则)
2. [标注优先级说明](#2-标注优先级说明)
3. [固定 JSON 结构总览](#3-固定-json-结构总览)
4. [元信息与环境字段](#4-元信息与环境字段)
5. [交通流字段](#5-交通流字段)
6. [场景要素字段（固定结构，按场景启用）](#6-场景要素字段固定结构按场景启用)
7. [证据链字段](#7-证据链字段)
8. [事件级字段（时间/区域/参与者）](#8-事件级字段时间区域参与者)
9. [最终标签字段](#9-最终标签字段)
10. [取值约定与一致性规则](#10-取值约定与一致性规则)
11. [标注流程与质检](#11-标注流程与质检)
12. [完整标注示例](#12-完整标注示例)
13. [字段与训练任务的映射关系](#13-字段与训练任务的映射关系)
14. [附录：枚举值字典](#14-附录枚举值字典)

---

## 1. 设计原则

1. **面向判别**：只标注与"事故是否发生"判断相关的要素，不做通用视频描述；
2. **JSON 结构固定**：任何场景、任何样本输出的 JSON 字段集合**完全一致**，
   便于程序解析、批量校验和训练样本生成。场景差异性通过两个机制保留：
   - 每个场景要素字段定义了"适用场景"，不适用场景下取值固定为 `不适用`；
   - `scene` 字段本身参与训练与分桶，模型可学习场景条件下的要素含义；
3. **证据与结论分离**：先标"看到了什么"（证据字段），再标"结论是什么"（事故标签）；
4. **优先级分层**：字段按 P0/P1/P2 分级，人力紧张时可只标 P0 保证核心可用；
5. **不确定性显式化**：看不清、判不了的要素统一标"不确定"，禁止猜测；
6. **困难样本显式打标**：拥堵、双闪、near-miss、遮挡等易混淆样本自动派生 `hard` 标记。

---

## 2. 标注优先级说明

所有字段划分为三级，**优先级依据"与事故判定的相关度"排定**：

| 级别 | 定义 | 标注要求 |
|---|---|---|
| **P0** | 事故判定核心：直接决定 `accident` 结论、困难样本识别、误报判别的字段 | **所有进入细标的样本必标** |
| **P1** | 重要辅助：证据链补全、推理训练文本生成、场景要素主力字段 | 标准标注必标（正样本 + hard 负样本） |
| **P2** | 完整信息：环境细节、场景次要要素、统计分析用字段 | 人力允许时标注；仅正样本建议标全 |

与分层标注流程的对应关系：

```text
第一层（快速分诊）  ：仅 P0 中的 scene / accident 初判
第二层（标准标注）  ：全部 P0 + P1
第三层（完整标注）  ：全部 P0 + P1 + P2 + 事件级字段
```

**P0 字段清单（速览）**：

```text
meta:     scene
traffic:  traffic_flow, flow_interruption_point
evidence: collision_visible, collision_occluded, abnormal_stop,
          person_down, motor_vehicle_rollover, non_motor_rollover,
          vehicle_fire, bypass_behavior,
          hazard_light, hazard_light_reason,
          congestion_only, smooth_pullover, near_miss
event:    accident_area, event_start_sec, event_end_sec（仅正样本必标）
label:    accident, accident_type, confidence
```

---

## 3. 固定 JSON 结构总览

**每条视频输出一条 JSON，字段集合固定不变**（场景不适用的字段填 `不适用`）：

```json
{
  "meta":            { "...": "元信息，见第4节" },
  "env":             { "...": "环境条件，见第4节" },
  "traffic":         { "...": "交通流，见第5节" },
  "scene_elements":  { "...": "场景要素（固定字段集），见第6节" },
  "evidence":        { "...": "证据链，见第7节" },
  "event":           { "...": "事件级（时间/区域/参与者），见第8节" },
  "label":           { "...": "最终标签，见第9节" }
}
```

与 v1 的关键区别：v1 的 `scene_specific` 按场景嵌套分支（highway/intersection/...），
不同场景 JSON 结构不同；v2 改为**扁平的 `scene_elements` 固定字段块**，
所有场景要素字段始终存在，用取值 `不适用` 表达场景差异。

---

## 4. 元信息与环境字段

### 4.1 元信息 `meta`

| 字段 | 优先级 | 类型 | 取值 | 说明 |
|---|---|---|---|---|
| `video_path` | P0(自动) | string | - | 视频路径（工具自动填） |
| `duration_sec` | P2(自动) | float | - | 视频时长（工具自动填） |
| `scene` | **P0** | enum | 高速高架 / 城市路口 / 城市普通路段 / 隧道 / 匝道收费站 / 其他 | **决定场景要素字段的适用性** |
| `camera_view` | P2 | enum | 路侧固定 / 高点俯视 / 卡口近景 / 隧道固定 / 其他 | 可按摄像头配置表自动填 |
| `annotator_id` | P2(自动) | string | - | 标注员编号 |

### 4.2 环境条件 `env`

| 字段 | 优先级 | 取值 | 与事故判断的关系 |
|---|---|---|---|
| `lighting` | P1 | 白天 / 夜间 / 黄昏黎明 / 隧道暗光 | 影响细节可辨识度，分桶评估用 |
| `visibility` | P1 | 高 / 中 / 低 | 低能见度样本单独分桶 |
| `weather` | P2 | 晴 / 雨 / 雪 / 雾 / 不确定 | 雨雪天误报高发 |
| `road_surface` | P2 | 干燥 / 湿滑 / 积水积雪 / 不确定 | 湿滑路面事故形态不同 |
| `glare_or_reflection` | P2 | 是 / 否 | 夜间反光易误判双闪 |

---

## 5. 交通流字段

### 交通流 `traffic`

| 字段 | 优先级 | 取值 | 说明 |
|---|---|---|---|
| `traffic_flow` | **P0** | 畅通 / 缓行 / 拥堵 / 停止排队 / 某点中断 | **"某点中断"是事故最强间接信号，必须与"整体拥堵"严格区分** |
| `flow_interruption_point` | **P0** | 是 / 否 / 不确定 | 是否存在固定中断点（下游畅通、上游积压）；整体拥堵中也可能叠加中断点 |
| `queue_present` | P1 | 是 / 否 | 是否排队 |
| `pedestrian_gathering` | P1 | 是 / 否 | 是否有人员在车行道聚集（事故后常见） |

> `congestion` 不再需要人工标注：由 `traffic_flow` 自动派生
> （拥堵/停止排队 → 是；畅通/缓行 → 否；某点中断 → 按上游状态判定）。

---

## 6. 场景要素字段（固定结构，按场景启用）

`scene_elements` 是一个**扁平的固定字段块**：以下所有字段在每条 JSON 中都存在。
每个字段有明确的"适用场景"；`scene` 不在适用范围内时，该字段**必须填 `不适用`**（工具自动填充并锁定）。

### 6.1 停车与占道类

| 字段 | 优先级 | 适用场景 | 取值 | 与事故判断的关系 |
|---|---|---|---|---|
| `stop_position` | P1 | 全部场景 | 行车道 / 应急车道 / 路边 / 无停车 / 不适用 | 停车位置是"事故停车 vs 临停"的核心判别点 |
| `emergency_lane_occupied` | P1 | 高速高架、隧道 | 是 / 否 / 无应急车道 / 不适用 | 应急车道停车多为故障临停（负）；行车道停车为强事故信号（正） |
| `stop_in_lane` | P1 | 隧道、高速高架 | 是 / 否 / 不适用 | 隧道/高速行车道内停车事故概率高 |
| `roadside_parking_present` | P2 | 城市普通路段 | 是 / 否 / 不适用 | 路边常态化停车（静止 ≠ 事故的高频场景） |
| `double_parked` | P2 | 城市普通路段 | 是 / 否 / 不适用 | 并排违停易被误判为事故聚集 |
| `bus_stop_area` | P2 | 城市普通路段 | 是 / 否 / 不适用 | 公交站频繁停靠是误报源 |
| `toll_queue` | P2 | 匝道收费站 | 是 / 否 / 不适用 | 收费站排队（常态化停止，误报源） |

### 6.2 车流行为类

| 字段 | 优先级 | 适用场景 | 取值 | 与事故判断的关系 |
|---|---|---|---|---|
| `queue_at_signal` | P1 | 城市路口 | 是 / 否 / 不适用 | 路口最常见误报源：**等灯静止 ≠ 事故** |
| `hazard_light_chain` | P1 | 隧道、高速高架 | 是 / 否 / 不适用 | 拥堵时多车依次开双闪提醒后车（**不是事故**） |
| `sudden_brake_wave` | P1 | 高速高架、隧道 | 是 / 否 / 不适用 | 上游连锁急刹（事故前兆信号） |
| `rear_end_chain` | P1 | 高速高架 | 是 / 否 / 不适用 | 多车追尾链 |
| `merge_conflict` | P2 | 高速高架、匝道收费站 | 是 / 否 / 不适用 | 汇入/交织冲突 |
| `weaving_conflict` | P2 | 匝道收费站 | 是 / 否 / 不适用 | 交织区变道冲突 |
| `reverse_or_retrograde` | P2 | 高速高架、隧道 | 是 / 否 / 不适用 | 倒车/逆行（危险行为） |
| `intersection_blocked` | P2 | 城市路口 | 是 / 否 / 不适用 | 路口中央被异常滞留堵塞 |

### 6.3 交通参与者与冲突类

| 字段 | 优先级 | 适用场景 | 取值 | 与事故判断的关系 |
|---|---|---|---|---|
| `vru_involved` | P1 | 城市路口、城市普通路段 | 行人 / 非机动车 / 两者 / 无 / 不适用 | 弱势交通参与者是否卷入 |
| `turn_conflict` | P2 | 城市路口 | 是 / 否 / 不适用 | 转弯车与直行车/行人轨迹冲突 |
| `red_light_running` | P2 | 城市路口 | 是 / 否 / 不确定 / 不适用 | 闯红灯 |
| `signal_state_at_event` | P2 | 城市路口 | 红 / 绿 / 黄 / 闪烁 / 不可见 / 不适用 | 事件时刻信号状态 |
| `crosswalk_area` | P2 | 城市路口、城市普通路段 | 是 / 否 / 不适用 | 事件是否发生在斑马线区域 |
| `pedestrian_crossing_midblock` | P2 | 城市普通路段 | 是 / 否 / 不适用 | 行人非路口横穿 |
| `delivery_rider_involved` | P2 | 城市路口、城市普通路段 | 是 / 否 / 不适用 | 外卖/快递电动车（高频事故参与者） |
| `door_open_event` | P2 | 城市普通路段 | 是 / 否 / 不确定 / 不适用 | 开门碰撞（城市特有事故形态） |
| `truck_involved` | P2 | 全部场景 | 是 / 否 | 货车遮挡大、事故形态不同 |

### 6.4 设施与环境类

| 字段 | 优先级 | 适用场景 | 取值 | 与事故判断的关系 |
|---|---|---|---|---|
| `guardrail_impact` | P1 | 高速高架、匝道收费站 | 是 / 否 / 不确定 / 不适用 | 撞护栏（单车事故常见形态） |
| `debris_on_road` | P1 | 高速高架、隧道 | 是 / 否 / 不确定 / 不适用 | 路面抛洒物/碎片 |
| `smoke_in_view` | P1 | 隧道 | 是 / 否 / 不确定 / 不适用 | 隧道内烟雾（重大事故信号；着火统一用 evidence.vehicle_fire） |
| `construction_zone` | P2 | 全部场景 | 是 / 否 | 施工区缓行是常见误报源 |
| `tunnel_zone` | P2 | 隧道 | 入口段 / 中段 / 出口段 / 不适用 | 出入口光照突变区误判高发 |
| `lighting_transition_artifact` | P2 | 隧道 | 是 / 否 / 不适用 | 出入口过渡造成的过曝/欠曝 |
| `narrow_shoulder` | P2 | 隧道 | 有硬路肩 / 无硬路肩 / 不适用 | 决定"贴边停车"的解释 |
| `sharp_curve_area` | P2 | 匝道收费站 | 是 / 否 / 不适用 | 急弯区单车事故高发 |
| `ramp_type` | P2 | 匝道收费站 | 上匝道 / 下匝道 / 收费站广场 / 不确定 / 不适用 | - |

### 6.5 场景适用性矩阵（工具自动锁定的依据）

| 字段 → 场景 | 高速高架 | 城市路口 | 城市普通路段 | 隧道 | 匝道收费站 |
|---|---|---|---|---|---|
| stop_position / truck_involved / construction_zone | ✓ | ✓ | ✓ | ✓ | ✓ |
| emergency_lane_occupied / sudden_brake_wave / reverse_or_retrograde | ✓ | - | - | ✓ | - |
| stop_in_lane / hazard_light_chain / debris_on_road | ✓ | - | - | ✓ | - |
| rear_end_chain / guardrail_impact | ✓ | - | - | - | ✓(guardrail) |
| merge_conflict | ✓ | - | - | - | ✓ |
| queue_at_signal / turn_conflict / red_light_running / signal_state_at_event / intersection_blocked | - | ✓ | - | - | - |
| vru_involved / crosswalk_area / delivery_rider_involved | - | ✓ | ✓ | - | - |
| roadside_parking_present / double_parked / bus_stop_area / door_open_event / pedestrian_crossing_midblock | - | - | ✓ | - | - |
| smoke_in_view / tunnel_zone / lighting_transition_artifact / narrow_shoulder | - | - | - | ✓ | - |
| toll_queue / weaving_conflict / sharp_curve_area / ramp_type | - | - | - | - | ✓ |

（"-" 处工具自动填 `不适用` 并锁定，标注员不可修改，保证 JSON 结构与取值合法性一致。）

---

## 7. 证据链字段

> 证据链是生成"步骤化推理"训练数据的直接来源。全部字段在每条 JSON 中都存在。

### 7.1 直接证据（可见碰撞与事故后强证据）

| 字段 | 优先级 | 取值 | 说明 |
|---|---|---|---|
| `collision_visible` | **P0** | 是 / 否 / 不确定 | 碰撞/剐蹭/撞击过程可直接看到 |
| `person_down` | **P0** | 是 / 否 / 不确定 | 行人/骑车人倒地（**即"行人倒地"要素**） |
| `motor_vehicle_rollover` | **P0** | 是 / 否 / 不确定 | **机动车侧翻**/翻滚（v2 由原 rollover 拆分） |
| `non_motor_rollover` | **P0** | 是 / 否 / 不确定 | **非机动车侧翻**（电动车/自行车/摩托车倒地侧翻，v2 新增） |
| `vehicle_fire` | **P0** | 是 / 否 / 不确定 | **机动车着火**：明火/浓烟从车辆冒出（v2 新增，全场景通用） |
| `vehicle_deformation` | P1 | 是 / 否 / 不确定 | 车体变形/损伤可见（远景一律"不确定"，不标"否"） |
| `debris_scatter` | P1 | 是 / 否 / 不确定 | 事件前后路面新出现碎片/散落物 |

### 7.2 间接证据（遮挡/不明显事故的推断依据）

| 字段 | 优先级 | 取值 | 说明 |
|---|---|---|---|
| `collision_occluded` | **P0** | 是 / 否 | 碰撞点被遮挡（与 collision_visible 互斥为"是"） |
| `abnormal_stop` | **P0** | 是 / 否 / 不确定 | 车辆异常停止（行车道中间/斜停/横跨车道） |
| `bypass_behavior` | **P0** | 是 / 否 / 不确定 | 周围车辆绕行固定区域 |
| `occlusion_type` | P1 | 无遮挡 / 事故车自身遮挡 / 其他车辆遮挡 / 设施遮挡 / 画面边缘盲区 | 遮挡类型 |
| `abrupt_trajectory_change` | P1 | 是 / 否 / 不确定 | 轨迹突变（急偏转/旋转/弹开） |
| `posture_anomaly` | P1 | 是 / 否 / 不确定 | 停止后姿态歪斜/位置异常 |
| `people_exit_vehicle` | P1 | 是 / 否 | 人员下车查看/聚集 |

### 7.3 误报相关要素（负样本判别依据）

| 字段 | 优先级 | 取值 | 说明 |
|---|---|---|---|
| `hazard_light` | **P0** | 是 / 否 / 不确定 | 是否有双闪（须逐帧确认闪烁） |
| `hazard_light_reason` | **P0** | 事故后 / 拥堵缓行 / 临时停车 / 故障施工 / 无双闪 / 不明确 | 双闪原因 |
| `congestion_only` | **P0** | 是 / 否 | 仅拥堵、无任何碰撞证据 |
| `smooth_pullover` | **P0** | 是 / 否 / 不确定 | 平稳减速靠边（临停特征） |
| `near_miss` | **P0** | 是 / 否 | 险情但未碰撞（急刹/擦肩） |
| `close_distance_pass` | P1 | 是 / 否 | 近距离通过但无接触 |

---

## 8. 事件级字段（时间/区域/参与者）

> `event` 块在每条 JSON 中都存在。负样本中：时间字段填 0/时长，`accident_area` 填 `不适用`，`participants` 为空数组——结构不变。

### 8.1 时间定位 `event.timeline`

| 字段 | 优先级 | 类型 | 说明 |
|---|---|---|---|
| `event_start_sec` | **P0**(正样本) | float | 事件开始时刻（碰撞或首个异常行为；负样本填 0） |
| `event_end_sec` | **P0**(正样本) | float | 事件结束时刻（状态稳定；负样本填视频时长） |
| `collision_moment_visible` | P1 | 是 / 否 / 无碰撞 | 碰撞瞬间是否可见 |
| `pre_event_visible` | P1 | 是 / 否 | 事件前正常状态可见 |
| `post_event_visible` | P1 | 是 / 否 | 事件后状态可见 |
| `event_stage_coverage` | P1(自动可派生) | 全过程 / 仅前+后 / 仅后 / 仅前 / 不适用 | 由上面三个字段自动派生 |

### 8.2 事故区域 `event.accident_area`（v2 新增）

| 字段 | 优先级 | 类型 | 说明 |
|---|---|---|---|
| `area_box` | **P0**(正样本) | [x, y, w, h] 或 null | **事故区域**在画面中的外接框（覆盖全部涉事目标与碎片范围）；负样本为 null |
| `area_location` | **P0**(正样本) | 行车道内 / 路口中央 / 应急车道 / 路边 / 匝道 / 隧道行车道 / 画面边缘 / 不适用 | 事故区域的道路位置类别 |
| `area_occluded_ratio` | P2 | 无遮挡 / 部分遮挡 / 大部遮挡 / 不适用 | 事故区域被遮挡的程度 |

> 与 `participants[].roi_box` 的区别：`roi_box` 是**单个参与者**的活动区域框（供 ROI
> 裁剪管线逐目标使用）；`accident_area` 是**事件级**的整体事故区域（供事故定位训练、
> ROI 视频裁剪和 grounding 任务使用）。

### 8.3 参与者列表 `event.participants`

数组（负样本为空数组），每个参与者一条：

| 字段 | 优先级 | 取值 | 说明 |
|---|---|---|---|
| `type` | P1 | 轿车 / SUV / 货车 / 客车 / 摩托车 / 电动车 / 自行车 / 行人 / 固定物 | 参与者类型 |
| `role` | P1 | 主动方 / 被动方 / 受波及 / 不确定 | 在事件中的角色 |
| `behavior_before` | P1 | 正常行驶 / 变道 / 转弯 / 急刹 / 超速感 / 逆行倒车 / 静止 / 不确定 | 事件前行为 |
| `state_after` | P1 | 停止行车道 / 停止路边 / 驶离 / 倒地 / 侧翻 / 姿态歪斜 / 不确定 | 事件后状态 |
| `hazard_light_after` | P2 | 是 / 否 / 不可见 | 事件后是否开双闪 |
| `roi_box` | P2 | [x, y, w, h] | 该参与者主要活动区域框（可由检测器预填） |

---

## 9. 最终标签字段

### 最终标签 `label`

| 字段 | 优先级 | 取值 | 说明 |
|---|---|---|---|
| `accident` | **P0** | 是 / 否 / 不确定 | 最终事故标签（准入规则见 10.2；"不确定"不入训练集） |
| `accident_type` | **P0** | 无事故 / 追尾 / 侧碰 / 剐蹭 / 正面碰撞 / 撞行人非机动车 / 侧翻 / 撞固定物 / 多车连环 / 起火燃烧 / 不确定 | 事故类型（v2 增加"起火燃烧"） |
| `confidence` | **P0** | 高 / 中 / 低 | 标注员对结论的信心 |
| `hard` | P0(自动) | true / false | 困难样本标记（规则自动派生，见 10.3） |

---

## 10. 取值约定与一致性规则

### 10.1 取值约定

1. 所有布尔类字段只允许：**是 / 否 / 不确定**（部分字段额外允许"不适用/无/不可见"，见各表）；
2. **`不适用` 只能出现在场景要素字段和事件级字段中**，且必须与 `scene` 的适用性矩阵一致（工具自动锁定）；
3. 禁止自由文本代替枚举；确实无法归类时选"其他/不确定"并在 `note` 字段补充；
4. "不确定"的使用标准：正常速度播放 + 逐帧回看后仍无法判断。

### 10.2 事故正样本准入规则

`accident=是` 必须满足以下之一，否则不得标为正样本：

```text
① collision_visible = 是（碰撞过程可见）
② collision_occluded = 是，且以下间接证据 ≥ 2 项为"是"：
   abnormal_stop / abrupt_trajectory_change / posture_anomaly /
   bypass_behavior / flow_interruption_point / people_exit_vehicle
③ 事故后强证据可见，以下任一为"是"：
   person_down / motor_vehicle_rollover / non_motor_rollover /
   vehicle_fire / vehicle_deformation
```

不满足准入规则、但业务系统标记为事故的视频 → 标 `accident=不确定`，**不进入训练集**，单独归档。

### 10.3 困难样本自动派生规则

满足任一条件自动置 `hard=true`：

```text
正样本困难：
  collision_visible=否 且 accident=是            （不明显/遮挡事故）
  event_stage_coverage ∈ {仅后, 仅前+后}          （过程缺失）
  area_occluded_ratio ∈ {部分遮挡, 大部遮挡}      （事故区域被遮挡）

负样本困难：
  congestion_only=是                              （拥堵负样本）
  hazard_light=是 且 accident=否                  （双闪负样本）
  near_miss=是 或 close_distance_pass=是          （险情负样本）
  abnormal_stop=是 且 accident=否                 （异常停车但非事故，如故障）
  hazard_light_chain=是                           （隧道/高速双闪链）
  queue_at_signal=是                              （路口等灯静止）
```

### 10.4 结构与完整性校验（脚本自动执行）

```text
① 字段集合校验：每条 JSON 必须包含全部固定字段，不得缺失、不得多出；
② 适用性校验：scene 不适用的场景要素字段取值必须为"不适用"；
   scene 适用的场景要素字段取值不得为"不适用"（P2 字段未标时允许"未标注"占位值）；
③ 互斥校验：collision_visible=是 与 collision_occluded=是 不得同时成立；
④ 正样本校验：accident=是 时，准入规则（10.2）必须满足，
   且 event_start_sec / event_end_sec / accident_area.area_box / area_location 必须有效；
⑤ 优先级校验：进入第二层标注的样本 P0+P1 字段不得为"未标注"。
```

---

## 11. 标注流程与质检

### 11.1 标注流程（与优先级分层对应）

```text
第 1 步（分诊，~15秒）：标 scene + accident 初判 + 是否值得细标
第 2 步（P0 标注）：交通流 2 字段 → 证据链 P0 字段 → accident/accident_type/confidence
第 3 步（P1 标注）：env 主字段 → 场景要素 P1 字段（工具已按 scene 锁定不适用项）
                    → 证据链 P1 字段 → 正样本补 timeline / accident_area / participants
第 4 步（P2 标注，人力允许时）：其余字段
第 5 步：脚本自动派生（congestion / hard / event_stage_coverage）+ 完整性校验
```

### 11.2 质检要求

| 项目 | 要求 |
|---|---|
| 双人标注 | 全部正样本 + 全部 hard 负样本的 **P0 字段**双人独立标注 |
| 仲裁 | 双人 `accident` 或 `accident_type` 不一致 → 第三人仲裁 |
| 一致性指标 | `accident` 字段双人一致率 ≥ 95%，低于则回炉培训 |
| 抽检 | 普通负样本按 10% 抽检；P1/P2 字段按 5% 抽检 |
| 迭代 | 每轮训练错误归因中发现的标注错误，回写修正并记录 |

---

## 12. 完整标注示例

### 示例 1：高速追尾事故（正样本，碰撞可见）

```json
{
  "meta": {
    "video_path": "/data/videos/hw_00123.mp4",
    "duration_sec": 20.0,
    "scene": "高速高架",
    "camera_view": "路侧固定",
    "annotator_id": "A03"
  },
  "env": {
    "lighting": "白天",
    "visibility": "中",
    "weather": "雨",
    "road_surface": "湿滑",
    "glare_or_reflection": "否"
  },
  "traffic": {
    "traffic_flow": "某点中断",
    "flow_interruption_point": "是",
    "queue_present": "是",
    "pedestrian_gathering": "否"
  },
  "scene_elements": {
    "stop_position": "行车道",
    "emergency_lane_occupied": "否",
    "stop_in_lane": "是",
    "roadside_parking_present": "不适用",
    "double_parked": "不适用",
    "bus_stop_area": "不适用",
    "toll_queue": "不适用",
    "queue_at_signal": "不适用",
    "hazard_light_chain": "否",
    "sudden_brake_wave": "是",
    "rear_end_chain": "是",
    "merge_conflict": "否",
    "weaving_conflict": "不适用",
    "reverse_or_retrograde": "否",
    "intersection_blocked": "不适用",
    "vru_involved": "不适用",
    "turn_conflict": "不适用",
    "red_light_running": "不适用",
    "signal_state_at_event": "不适用",
    "crosswalk_area": "不适用",
    "pedestrian_crossing_midblock": "不适用",
    "delivery_rider_involved": "不适用",
    "door_open_event": "不适用",
    "truck_involved": "是",
    "guardrail_impact": "否",
    "debris_on_road": "是",
    "smoke_in_view": "不适用",
    "construction_zone": "否",
    "tunnel_zone": "不适用",
    "lighting_transition_artifact": "不适用",
    "narrow_shoulder": "不适用",
    "sharp_curve_area": "不适用",
    "ramp_type": "不适用"
  },
  "evidence": {
    "collision_visible": "是",
    "person_down": "否",
    "motor_vehicle_rollover": "否",
    "non_motor_rollover": "否",
    "vehicle_fire": "否",
    "vehicle_deformation": "是",
    "debris_scatter": "是",
    "collision_occluded": "否",
    "abnormal_stop": "是",
    "bypass_behavior": "是",
    "occlusion_type": "无遮挡",
    "abrupt_trajectory_change": "是",
    "posture_anomaly": "是",
    "people_exit_vehicle": "否",
    "hazard_light": "是",
    "hazard_light_reason": "事故后",
    "congestion_only": "否",
    "smooth_pullover": "否",
    "near_miss": "否",
    "close_distance_pass": "否"
  },
  "event": {
    "timeline": {
      "event_start_sec": 6.5,
      "event_end_sec": 14.0,
      "collision_moment_visible": "是",
      "pre_event_visible": "是",
      "post_event_visible": "是",
      "event_stage_coverage": "全过程"
    },
    "accident_area": {
      "area_box": [760, 320, 520, 340],
      "area_location": "行车道内",
      "area_occluded_ratio": "无遮挡"
    },
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
  "label": {
    "accident": "是",
    "accident_type": "追尾",
    "confidence": "高",
    "hard": false
  }
}
```

### 示例 2：隧道双闪链拥堵（困难负样本）

```json
{
  "meta": {
    "video_path": "/data/videos/tn_00456.mp4",
    "duration_sec": 20.0,
    "scene": "隧道",
    "camera_view": "隧道固定",
    "annotator_id": "A07"
  },
  "env": {
    "lighting": "隧道暗光",
    "visibility": "中",
    "weather": "不确定",
    "road_surface": "干燥",
    "glare_or_reflection": "是"
  },
  "traffic": {
    "traffic_flow": "拥堵",
    "flow_interruption_point": "否",
    "queue_present": "是",
    "pedestrian_gathering": "否"
  },
  "scene_elements": {
    "stop_position": "无停车",
    "emergency_lane_occupied": "无应急车道",
    "stop_in_lane": "否",
    "roadside_parking_present": "不适用",
    "double_parked": "不适用",
    "bus_stop_area": "不适用",
    "toll_queue": "不适用",
    "queue_at_signal": "不适用",
    "hazard_light_chain": "是",
    "sudden_brake_wave": "否",
    "rear_end_chain": "不适用",
    "merge_conflict": "不适用",
    "weaving_conflict": "不适用",
    "reverse_or_retrograde": "否",
    "intersection_blocked": "不适用",
    "vru_involved": "不适用",
    "turn_conflict": "不适用",
    "red_light_running": "不适用",
    "signal_state_at_event": "不适用",
    "crosswalk_area": "不适用",
    "pedestrian_crossing_midblock": "不适用",
    "delivery_rider_involved": "不适用",
    "door_open_event": "不适用",
    "truck_involved": "否",
    "guardrail_impact": "不适用",
    "debris_on_road": "否",
    "smoke_in_view": "否",
    "construction_zone": "否",
    "tunnel_zone": "中段",
    "lighting_transition_artifact": "否",
    "narrow_shoulder": "无硬路肩",
    "sharp_curve_area": "不适用",
    "ramp_type": "不适用"
  },
  "evidence": {
    "collision_visible": "否",
    "person_down": "否",
    "motor_vehicle_rollover": "否",
    "non_motor_rollover": "否",
    "vehicle_fire": "否",
    "vehicle_deformation": "否",
    "debris_scatter": "否",
    "collision_occluded": "否",
    "abnormal_stop": "否",
    "bypass_behavior": "否",
    "occlusion_type": "无遮挡",
    "abrupt_trajectory_change": "否",
    "posture_anomaly": "否",
    "people_exit_vehicle": "否",
    "hazard_light": "是",
    "hazard_light_reason": "拥堵缓行",
    "congestion_only": "是",
    "smooth_pullover": "否",
    "near_miss": "否",
    "close_distance_pass": "否"
  },
  "event": {
    "timeline": {
      "event_start_sec": 0.0,
      "event_end_sec": 20.0,
      "collision_moment_visible": "无碰撞",
      "pre_event_visible": "是",
      "post_event_visible": "是",
      "event_stage_coverage": "全过程"
    },
    "accident_area": {
      "area_box": null,
      "area_location": "不适用",
      "area_occluded_ratio": "不适用"
    },
    "participants": []
  },
  "label": {
    "accident": "否",
    "accident_type": "无事故",
    "confidence": "高",
    "hard": true
  }
}
```

---

## 13. 字段与训练任务的映射关系

| 训练任务 | 使用的标注字段 |
|---|---|
| 任务A 属性感知 | `scene`、`traffic_flow`、`hazard_light`、`abnormal_stop`、`lighting`、场景要素 P1 字段（如 `queue_at_signal`、`emergency_lane_occupied`、`hazard_light_chain`） |
| 任务B 证据判断 | `evidence` 全部字段（含 v2 新增的 `motor_vehicle_rollover` / `non_motor_rollover` / `vehicle_fire`） |
| 任务C 对比判别 | `accident` + `congestion_only` / `hazard_light_reason` / `near_miss` / `smooth_pullover` 组合映射四选一答案 |
| 任务D 步骤化推理 | 第 1 步 ← `scene`+`traffic`；第 2 步 ← `participants`+误报要素；第 3 步 ← 直接/间接证据；第 4 步 ← `accident` |
| 任务E 部署二分类 | `accident` |
| 事故定位/grounding 任务 | `accident_area.area_box`、`area_location`（v2 新增能力） |
| ROI 裁剪管线 | `accident_area.area_box`（事件级）、`participants[].roi_box`（目标级）、`event.timeline`（时间窗） |
| 分桶评估 | `hard` 派生条件、`scene`、`lighting`、`event_stage_coverage`、`area_occluded_ratio` |
| GRPO 数据筛选 | `confidence`、`hard`、准入规则（剔除"不确定"样本） |

场景要素字段的额外价值：可生成**场景特有的判别训练样本**，例如：

```text
高速：  "视频中车辆停在应急车道还是行车道？" → 教模型区分故障临停与事故
路口：  "视频中静止车辆是在等待信号灯吗？"   → 教模型区分等灯与事故
隧道：  "多辆车开双闪是拥堵提醒还是事故？"   → 教模型理解双闪链
```

---

## 14. 附录：枚举值字典

```yaml
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
area_location: [行车道内, 路口中央, 应急车道, 路边, 匝道, 隧道行车道, 画面边缘, 不适用]
area_occluded_ratio: [无遮挡, 部分遮挡, 大部遮挡, 不适用]
participant_type: [轿车, SUV, 货车, 客车, 摩托车, 电动车, 自行车, 行人, 固定物]
participant_role: [主动方, 被动方, 受波及, 不确定]
behavior_before: [正常行驶, 变道, 转弯, 急刹, 超速感, 逆行倒车, 静止, 不确定]
state_after: [停止行车道, 停止路边, 驶离, 倒地, 侧翻, 姿态歪斜, 不确定]
event_stage_coverage: [全过程, 仅前+后, 仅后, 仅前, 不适用]
tri_state: [是, 否, 不确定]
tri_state_na: [是, 否, 不确定, 不适用]
confidence: [高, 中, 低]
priority: [P0, P1, P2]
```
