# 交通事故图片素材结构化标注规范（v1）

> 目的：对路侧监控**单帧图片**（卡口抓拍、监控截图、视频抽帧）进行结构化标注，
> 与视频标注规范配套，为图片类训练任务（静态证据感知 / 事故区域定位 / 图片二分类）提供数据基础。
>
> 配套文档：视频数据标注见《accident_annotation_spec_video.md》；
> 判定标准见《accident_annotation_criteria.md》（时序类标准不适用于本规范）。
>
> 与视频规范的核心差异：**图片没有时间维度**——所有依赖"过程/变化/闪烁"的字段
> 被移除或替换为单帧可判的静态代理字段；JSON 同样采用固定结构 + p0/p1/p2 优先级分组。

---

## 目录

1. [图片标注的特殊性](#1-图片标注的特殊性)
2. [标注优先级说明](#2-标注优先级说明)
3. [固定 JSON 结构总览](#3-固定-json-结构总览)
4. [元信息与环境字段](#4-元信息与环境字段)
5. [交通状态字段（静态代理）](#5-交通状态字段静态代理)
6. [场景要素字段](#6-场景要素字段)
7. [证据字段（静态证据）](#7-证据字段静态证据)
8. [事故区域与参与者字段](#8-事故区域与参与者字段)
9. [最终标签与派生字段](#9-最终标签与派生字段)
10. [取值约定与一致性规则](#10-取值约定与一致性规则)
11. [完整标注示例](#11-完整标注示例)
12. [字段与训练任务的映射关系](#12-字段与训练任务的映射关系)
13. [附录：与视频规范的字段对照表](#13-附录与视频规范的字段对照表)

---

## 1. 图片标注的特殊性

单帧图片相对视频丢失了全部时序信息，标注设计遵循三条原则：

1. **只标单帧可判的要素**：凡是需要"看过程"才能判断的字段
   （碰撞过程、双闪闪烁、急刹、绕行动作、平稳靠边过程）一律不设，
   或替换为静态代理字段（见第 13 节对照表）；
2. **状态代替过程**：图片能看到"接触状态、倒地状态、姿态、灯亮、队形、密度"，
   这些静态状态是图片标注的主体；
3. **更保守的结论标准**：图片的事故判定天然比视频更不确定，
   准入规则更严格（见 10.2），预期"不确定"比例高于视频标注。

图片来源标记（`meta.image_source`）区分两类：

```text
independent：独立图片（卡口抓拍等，无对应视频）
video_frame：视频抽帧（可继承视频标注的 label 与部分字段，人工只补图片级字段）
```

视频抽帧图片建议直接由视频标注 + 抽帧脚本自动生成大部分字段，人工仅校对。

---

## 2. 标注优先级说明

与视频规范一致的三级体系：

| 级别 | 定义 | 标注要求 |
|---|---|---|
| **P0** | 事故判定核心字段 | 所有细标图片必标 |
| **P1** | 证据补全与场景要素主力字段 | 正样本 + hard 负样本必标 |
| **P2** | 环境细节与统计字段 | 人力允许时标注 |

---

## 3. 固定 JSON 结构总览

**每张图片输出一条 JSON，结构与字段集合固定不变**，块内按优先级分组：

```json
{
  "meta":           { "...": "工具自动填，见第4节" },
  "env":            { "p1": { }, "p2": { } },
  "traffic":        { "p0": { }, "p1": { } },
  "scene_elements": { "p1": { }, "p2": { } },
  "evidence":       { "p0": { }, "p1": { } },
  "event":          { "p0": { }, "p1": { } },
  "label":          { "p0": { } },
  "derived":        { "...": "脚本自动派生" }
}
```

约定与视频规范相同：`p0/p1/p2` 子对象始终存在；未标注层级填 `未标注`；
场景不适用字段填 `不适用`（工具锁定）。

---

## 4. 元信息与环境字段

### 4.1 元信息 `meta`（工具自动填）

| 字段 | 类型 | 取值 | 说明 |
|---|---|---|---|
| `media_type` | enum | image | 固定为 image |
| `image_path` | string | - | 图片路径 |
| `image_source` | enum | independent / video_frame | 图片来源 |
| `source_video_path` | string 或 null | - | 来源视频路径（video_frame 时填） |
| `frame_time_sec` | float 或 null | - | 抽帧时刻（video_frame 时填） |
| `scene` | enum | 高速高架 / 城市路口 / 城市普通路段 / 隧道 / 匝道收费站 / 其他 | **P0 性质**，决定场景要素适用性 |
| `camera_view` | enum | 路侧固定 / 高点俯视 / 卡口近景 / 隧道固定 / 其他 | - |
| `annotator_id` | string | - | 标注员编号 |

### 4.2 环境条件 `env`（与视频规范一致）

| 子对象 | 字段 | 取值 |
|---|---|---|
| **p1** | `lighting` | 白天 / 夜间 / 黄昏黎明 / 隧道暗光 |
| **p1** | `visibility` | 高 / 中 / 低 |
| **p2** | `weather` | 晴 / 雨 / 雪 / 雾 / 不确定 |
| **p2** | `road_surface` | 干燥 / 湿滑 / 积水积雪 / 不确定 |
| **p2** | `glare_or_reflection` | 是 / 否 |

---

## 5. 交通状态字段（静态代理）

图片无法观察"流动"，用单帧可见的空间形态代理：

| 子对象 | 字段 | 取值 | 说明 |
|---|---|---|---|
| **p0** | `traffic_density` | 稀疏 / 中等 / 密集 / 排队队形 | 静态密度（代替视频的 traffic_flow） |
| **p0** | `flow_gap_pattern` | 是 / 否 / 不确定 | **断层形态**：某处上游车辆积压、下游明显空置（事故中断点的单帧投影） |
| **p1** | `queue_formation` | 是 / 否 | 车辆呈首尾相接队形 |
| **p1** | `pedestrian_gathering` | 是 / 否 | 人员在车行道聚集 |
| **p1** | `brake_lights_chain` | 是 / 否 / 不可见 | 连片刹车灯亮起（急刹波的单帧投影） |

---

## 6. 场景要素字段

适用性矩阵与视频规范 6.3 节相同；时序类字段已移除。

### 6.1 p1 子对象

| 字段 | 适用场景 | 取值 | 说明 |
|---|---|---|---|
| `stop_position` | 全部场景 | 行车道 / 应急车道 / 路边 / 无停车 / 不适用 | 图片中静止推断：占道且无行驶迹象 |
| `emergency_lane_occupied` | 高速高架、隧道 | 是 / 否 / 无应急车道 / 不适用 | - |
| `vehicle_in_lane_stationary_suspected` | 高速高架、隧道 | 是 / 否 / 不确定 / 不适用 | 疑似行车道内静止（单帧对"静止"只能是疑似） |
| `queue_at_signal` | 城市路口 | 是 / 否 / 不确定 / 不适用 | 停止线后整齐队形 +（可见时）红灯 |
| `rear_end_chain_visible` | 高速高架 | 是 / 否 / 不适用 | 多车首尾贴合链（追尾链的静态形态） |
| `vru_involved` | 城市路口、城市普通路段 | 行人 / 非机动车 / 两者 / 无 / 不适用 | - |
| `guardrail_impact` | 高速高架、匝道收费站 | 是 / 否 / 不确定 / 不适用 | 护栏变形/车辆抵触护栏可见 |
| `debris_on_road` | 高速高架、隧道 | 是 / 否 / 不确定 / 不适用 | - |
| `smoke_in_view` | 隧道 | 是 / 否 / 不确定 / 不适用 | - |

### 6.2 p2 子对象

| 字段 | 适用场景 | 取值 |
|---|---|---|
| `roadside_parking_present` | 城市普通路段 | 是 / 否 / 不适用 |
| `double_parked` | 城市普通路段 | 是 / 否 / 不适用 |
| `bus_stop_area` | 城市普通路段 | 是 / 否 / 不适用 |
| `toll_queue` | 匝道收费站 | 是 / 否 / 不适用 |
| `intersection_blocked` | 城市路口 | 是 / 否 / 不适用 |
| `signal_state` | 城市路口 | 红 / 绿 / 黄 / 不可见 / 不适用 |
| `crosswalk_area` | 城市路口、城市普通路段 | 是 / 否 / 不适用 |
| `delivery_rider_involved` | 城市路口、城市普通路段 | 是 / 否 / 不适用 |
| `truck_involved` | 全部场景 | 是 / 否 |
| `construction_zone` | 全部场景 | 是 / 否 |
| `tunnel_zone` | 隧道 | 入口段 / 中段 / 出口段 / 不适用 |
| `narrow_shoulder` | 隧道 | 有硬路肩 / 无硬路肩 / 不适用 |
| `sharp_curve_area` | 匝道收费站 | 是 / 否 / 不适用 |
| `ramp_type` | 匝道收费站 | 上匝道 / 下匝道 / 收费站广场 / 不确定 / 不适用 |

---

## 7. 证据字段（静态证据）

### 7.1 p0 子对象（事故判定核心）

**直接静态证据：**

| 字段 | 取值 | 说明 |
|---|---|---|
| `collision_contact_visible` | 是 / 否 / 不确定 | 两目标**接触/贴合状态**可见（图片版"碰撞可见"：看状态不看过程） |
| `person_down` | 是 / 否 / 不确定 | 行人/骑车人倒地 |
| `motor_vehicle_rollover` | 是 / 否 / 不确定 | 机动车侧翻/翻覆状态 |
| `non_motor_rollover` | 是 / 否 / 不确定 | 非机动车侧翻倒地 |
| `vehicle_fire` | 是 / 否 / 不确定 | 机动车着火（明火/浓烟） |
| `vehicle_deformation` | 是 / 否 / 不确定 | 车体变形/损伤可见 |

**间接静态证据：**

| 字段 | 取值 | 说明 |
|---|---|---|
| `abnormal_stop_posture` | 是 / 否 / 不确定 | 异常停放形态：车道中间/斜停 > 15°/横跨车道线（图片版"异常停止"，只看姿态与位置） |
| `collision_area_occluded` | 是 / 否 | 疑似事故区域被遮挡 |
| `lane_avoidance_pattern` | 是 / 否 / 不确定 | 绕行队形：某车道在固定点前空置、相邻车道排队（绕行行为的静态投影） |

**误报判别要素：**

| 字段 | 取值 | 说明 |
|---|---|---|
| `rear_lights_on_both_sides` | 是 / 否 / 不可见 | 左右尾灯同时亮起（**单帧无法确认闪烁，只能标"疑似双闪"的静态依据**） |
| `congestion_only_suspected` | 是 / 否 | 画面仅呈现密集/排队，无任何碰撞证据 |
| `normal_parking_posture` | 是 / 否 / 不确定 | 规范停放形态：贴边、车身端正、位置合理（临停特征的静态版） |

### 7.2 p1 子对象

| 字段 | 取值 | 说明 |
|---|---|---|
| `debris_scatter` | 是 / 否 / 不确定 | 路面碎片/散落物 |
| `occlusion_type` | 无遮挡 / 事故车自身遮挡 / 其他车辆遮挡 / 设施遮挡 / 画面边缘盲区 | - |
| `people_gathered_around` | 是 / 否 | 人员围聚在某目标周边 |
| `fluid_on_road` | 是 / 否 / 不确定 | 路面液体痕迹（油液/大面积水渍） |
| `close_distance_pair` | 是 / 否 | 两目标近距离（<1 车身）但未见接触 |

---

## 8. 事故区域与参与者字段

### 8.1 p0 子对象

| 字段 | 类型 | 说明 |
|---|---|---|
| `accident_area_box` | [x, y, w, h] 或 null | **事故区域**外接框（覆盖全部涉事目标与碎片；负样本 null） |
| `accident_area_location` | 行车道内 / 路口中央 / 应急车道 / 路边 / 匝道 / 隧道行车道 / 画面边缘 / 不适用 | 事故区域道路位置 |

### 8.2 p1 子对象

| 字段 | 类型 | 说明 |
|---|---|---|
| `participants` | array | 参与者列表（负样本为空数组），结构见 8.3 |
| `area_occluded_ratio` | 无遮挡 / 部分遮挡 / 大部遮挡 / 不适用 | 事故区域遮挡程度 |

### 8.3 参与者对象结构（无时序字段）

| 字段 | 取值 |
|---|---|
| `type` | 轿车 / SUV / 货车 / 客车 / 摩托车 / 电动车 / 自行车 / 行人 / 固定物 |
| `state_now` | 接触贴合 / 倒地 / 侧翻 / 姿态歪斜 / 正常停放 / 行驶中 / 不确定 |
| `rear_lights_on` | 是 / 否 / 不可见 |
| `roi_box` | [x, y, w, h] |

---

## 9. 最终标签与派生字段

### 9.1 最终标签 `label`（全部 p0）

| 字段 | 取值 | 说明 |
|---|---|---|
| `accident` | 是 / 否 / 不确定 | 图片事故标签（准入规则见 10.2，比视频更严格） |
| `accident_type` | 无事故 / 追尾 / 侧碰 / 剐蹭 / 正面碰撞 / 撞行人非机动车 / 侧翻 / 撞固定物 / 多车连环 / 起火燃烧 / 不确定 | - |
| `confidence` | 高 / 中 / 低 | - |

### 9.2 派生字段 `derived`

| 字段 | 派生规则 |
|---|---|
| `hard` | 见 10.3 |
| `congestion_suspected` | traffic_density ∈ {密集, 排队队形} → 是 |

---

## 10. 取值约定与一致性规则

### 10.1 取值约定

与视频规范一致：是/否/不确定 + 不适用（工具锁定）+ 未标注（分层占位）。
图片标注中"不确定"的使用标准放宽为：**放大查看后仍无法判断**（无逐帧回看可用）。

### 10.2 图片事故正样本准入规则（比视频严格）

`accident=是` 必须满足以下之一：

```text
① 直接静态证据任一为"是"：
   collision_contact_visible / person_down / motor_vehicle_rollover /
   non_motor_rollover / vehicle_fire
② vehicle_deformation=是 且 abnormal_stop_posture=是（车损 + 异常停放的组合）
③ abnormal_stop_posture=是 且 以下 ≥ 2 项为"是"：
   debris_scatter / people_gathered_around / lane_avoidance_pattern / fluid_on_road
```

> 视频规范中"间接证据 ≥ 2"的遮挡推断链在图片上不成立（看不到前后状态变化），
> 因此图片对"无直接证据"的疑似事故一律更保守：宁标"不确定"。

### 10.3 困难样本自动派生规则（`derived.hard = true`）

```text
正样本困难：
  collision_contact_visible=否 且 accident=是      （靠组合证据判定的正样本）
  area_occluded_ratio ∈ {部分遮挡, 大部遮挡}

负样本困难：
  congestion_only_suspected=是                     （密集/排队负样本）
  rear_lights_on_both_sides=是 且 accident=否      （疑似双闪负样本）
  abnormal_stop_posture=是 且 accident=否          （异常停放但非事故）
  close_distance_pair=是                           （近距离负样本）
  queue_at_signal=是                               （等灯队形）
```

### 10.4 校验规则

与视频规范 10.4 一致（结构 / 优先级 / 适用性 / 正样本校验），
其中互斥校验调整为：`collision_contact_visible=是` 与 `collision_area_occluded=是` 不得同时成立。

---

## 11. 完整标注示例

### 城市路口事故图片（正样本：电动车倒地）

```json
{
  "meta": {
    "media_type": "image",
    "image_path": "/data/images/ix_00789.jpg",
    "image_source": "video_frame",
    "source_video_path": "/data/videos/ix_00789.mp4",
    "frame_time_sec": 8.2,
    "scene": "城市路口",
    "camera_view": "高点俯视",
    "annotator_id": "A11"
  },
  "env": {
    "p1": { "lighting": "白天", "visibility": "高" },
    "p2": { "weather": "晴", "road_surface": "干燥", "glare_or_reflection": "否" }
  },
  "traffic": {
    "p0": { "traffic_density": "中等", "flow_gap_pattern": "否" },
    "p1": { "queue_formation": "否", "pedestrian_gathering": "是", "brake_lights_chain": "不可见" }
  },
  "scene_elements": {
    "p1": {
      "stop_position": "行车道",
      "emergency_lane_occupied": "不适用",
      "vehicle_in_lane_stationary_suspected": "不适用",
      "queue_at_signal": "否",
      "rear_end_chain_visible": "不适用",
      "vru_involved": "非机动车",
      "guardrail_impact": "不适用",
      "debris_on_road": "不适用",
      "smoke_in_view": "不适用"
    },
    "p2": {
      "roadside_parking_present": "不适用",
      "double_parked": "不适用",
      "bus_stop_area": "不适用",
      "toll_queue": "不适用",
      "intersection_blocked": "否",
      "signal_state": "绿",
      "crosswalk_area": "是",
      "delivery_rider_involved": "是",
      "truck_involved": "否",
      "construction_zone": "否",
      "tunnel_zone": "不适用",
      "narrow_shoulder": "不适用",
      "sharp_curve_area": "不适用",
      "ramp_type": "不适用"
    }
  },
  "evidence": {
    "p0": {
      "collision_contact_visible": "否",
      "person_down": "是",
      "motor_vehicle_rollover": "否",
      "non_motor_rollover": "是",
      "vehicle_fire": "否",
      "vehicle_deformation": "不确定",
      "abnormal_stop_posture": "是",
      "collision_area_occluded": "否",
      "lane_avoidance_pattern": "不确定",
      "rear_lights_on_both_sides": "不可见",
      "congestion_only_suspected": "否",
      "normal_parking_posture": "否"
    },
    "p1": {
      "debris_scatter": "否",
      "occlusion_type": "无遮挡",
      "people_gathered_around": "是",
      "fluid_on_road": "否",
      "close_distance_pair": "否"
    }
  },
  "event": {
    "p0": {
      "accident_area_box": [540, 410, 380, 260],
      "accident_area_location": "路口中央"
    },
    "p1": {
      "participants": [
        {
          "type": "电动车",
          "state_now": "侧翻",
          "rear_lights_on": "不可见",
          "roi_box": [560, 450, 180, 160]
        },
        {
          "type": "轿车",
          "state_now": "姿态歪斜",
          "rear_lights_on": "否",
          "roi_box": [640, 400, 260, 200]
        }
      ],
      "area_occluded_ratio": "无遮挡"
    }
  },
  "label": {
    "p0": { "accident": "是", "accident_type": "撞行人非机动车", "confidence": "高" }
  },
  "derived": {
    "hard": false,
    "congestion_suspected": "否"
  }
}
```

---

## 12. 字段与训练任务的映射关系

| 训练任务 | 使用字段 |
|---|---|
| 图片属性感知 QA | `meta.scene`、`traffic.p0`、`scene_elements.p1` |
| 静态证据判断 QA | `evidence.p0` + `evidence.p1` |
| 图片对比判别（事故/密集排队/规范停放/近距离 四选一） | `label.p0.accident` + `congestion_only_suspected` / `normal_parking_posture` / `close_distance_pair` 映射 |
| 图片二分类（部署格式） | `label.p0.accident` |
| 事故区域定位 / grounding | `event.p0.accident_area_box`、`accident_area_location` |
| 多粒度训练的 ROI 特写来源 | `participants[].roi_box`（配合视频全局输入组成"全局视频 + 局部图片"样本） |
| 分桶评估 | `derived.hard`、`meta.scene`、`env.p1` |

**与视频数据的协同**：`image_source=video_frame` 的图片可与来源视频组成
"全局视频 + 关键帧特写"的多粒度训练样本；其 `label` 应与视频标注保持一致，
不一致时以视频标注为准并回查。

---

## 13. 附录：与视频规范的字段对照表

| 视频字段（时序） | 图片对应字段（静态代理） | 说明 |
|---|---|---|
| `traffic_flow`（五级） | `traffic_density`（四级） | 流动性 → 密度形态 |
| `flow_interruption_point` | `flow_gap_pattern` | 中断点 → 断层形态（单帧可见） |
| `sudden_brake_wave` | `brake_lights_chain` | 急刹波 → 连片刹车灯 |
| `collision_visible`（过程） | `collision_contact_visible`（状态） | 碰撞过程 → 接触/贴合状态 |
| `hazard_light`（闪烁确认） | `rear_lights_on_both_sides` | 无法确认闪烁，只标静态依据 |
| `hazard_light_reason` | 无对应 | 需要过程信息，图片不标 |
| `abnormal_stop`（含过程） | `abnormal_stop_posture`（仅姿态位置） | - |
| `smooth_pullover`（过程） | `normal_parking_posture`（形态） | - |
| `bypass_behavior`（动作） | `lane_avoidance_pattern`（队形） | - |
| `near_miss` | 无对应（`close_distance_pair` 仅记录近距离） | 险情动作不可判 |
| `abrupt_trajectory_change` | 无对应 | 纯时序 |
| `rear_end_chain` | `rear_end_chain_visible` | 追尾链 → 贴合链形态 |
| `people_exit_vehicle`（动作） | `people_gathered_around`（状态） | - |
| `event_start/end_sec`、`event_stage_coverage` | 无对应（`frame_time_sec` 记录抽帧时刻） | 图片无时间轴 |
| `participants[].behavior_before` | 无对应 | 纯时序 |
| `participants[].state_after` | `participants[].state_now` | 事后状态 → 当前状态 |
| 其余静态字段 | 同名保留 | person_down / 两类侧翻 / vehicle_fire / accident_area 等 |
