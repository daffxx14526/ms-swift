# 交通事故视频标注规范（核心字段版）

> 本文档是《accident_annotation_spec_video.md》的**精简版**：
> 只保留事故判定所需的**最高优先级**字段，JSON **不再**使用优先级分组键。
>
> 完整字段、场景要素、环境细节见完整版规范；判定细则见《accident_annotation_criteria.md》。

---

## 目录

1. [适用范围](#1-适用范围)
2. [时间戳约定](#2-时间戳约定)
3. [JSON 结构总览](#3-json-结构总览)
4. [元信息](#4-元信息)
5. [交通流](#5-交通流)
6. [证据链](#6-证据链)
7. [事件时间与事故区域](#7-事件时间与事故区域)
8. [最终标签](#8-最终标签)
9. [派生字段](#9-派生字段)
10. [准入与校验](#10-准入与校验)
11. [完整示例](#11-完整示例)

---

## 1. 适用范围

- 仅覆盖进入细标流程后、**必须标注**的核心字段；
- 不含环境、场景要素、参与者列表等辅助字段；
- 时序属性仍使用 `{value, timestamp_sec}`（见第 2 节）。

---

## 2. 时间戳约定

时序属性统一为对象：

```json
{"value": "是", "timestamp_sec": 6.5}
```

| 情况 | `value` | `timestamp_sec` |
|---|---|---|
| 确认观察到 | `是` | 首次可确认时刻（必填） |
| 确认未发生 | `否` | `null` |
| 看不清 | `不确定` | 有候选可填，否则 `null` |

- 原点：视频起点 `0.0`；单位：秒；精度：`0.1s`
- 范围：`0 ≤ timestamp_sec ≤ meta.duration_sec`

本规范中的时序属性：`collision_visible`、`person_down`、`motor_vehicle_rollover`、
`non_motor_rollover`、`vehicle_fire`、`abnormal_stop`、`bypass_behavior`、
`hazard_light`、`smooth_pullover`、`near_miss`。

事件级纯时间字段（直接 float）：`event_start_sec`、`event_end_sec`。

---

## 3. JSON 结构总览

```json
{
  "meta": { },
  "traffic": { },
  "evidence": { },
  "event": { },
  "label": { },
  "derived": { }
}
```

字段一律扁平写在各块内，**不出现**优先级分组键。

---

## 4. 元信息

| 字段 | 类型 | 取值 | 说明 |
|---|---|---|---|
| `media_type` | enum | video | 固定 |
| `video_path` | string | - | 视频路径 |
| `duration_sec` | float | - | 时长（秒） |
| `scene` | enum | 高速高架 / 城市路口 / 城市普通路段 / 隧道 / 匝道收费站 / 其他 | 场景类别，必填 |
| `camera_view` | enum | 路侧固定 / 高点俯视 / 卡口近景 / 隧道固定 / 其他 | 视角 |
| `annotator_id` | string | - | 标注员编号 |

---

## 5. 交通流

| 字段 | 取值 | 说明 |
|---|---|---|
| `traffic_flow` | 畅通 / 缓行 / 拥堵 / 停止排队 / 某点中断 | **"某点中断"是事故最强间接信号** |
| `flow_interruption_point` | 是 / 否 / 不确定 | 固定中断点（下游畅通、上游积压） |

---

## 6. 证据链

规则与准入判断时，对时序字段读 `.value`。

### 直接证据（时序对象）

| 字段 | value | timestamp 含义 |
|---|---|---|
| `collision_visible` | 是 / 否 / 不确定 | 碰撞过程首次可确认时刻 |
| `person_down` | 是 / 否 / 不确定 | 行人/骑车人倒地时刻 |
| `motor_vehicle_rollover` | 是 / 否 / 不确定 | 机动车侧翻时刻 |
| `non_motor_rollover` | 是 / 否 / 不确定 | 非机动车侧翻时刻 |
| `vehicle_fire` | 是 / 否 / 不确定 | 车辆着火/冒浓烟时刻 |

### 间接证据

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `collision_occluded` | 是 / 否 | 碰撞点被遮挡（与 `collision_visible.value=是` 互斥）；无时间戳 |
| `abnormal_stop` | 时序对象 | 异常停止；timestamp=首次静止于异常位置 |
| `bypass_behavior` | 时序对象 | 绕行；timestamp=首辆开始绕行 |

### 误报判别

| 字段 | 取值形式 | 说明 |
|---|---|---|
| `hazard_light` | 时序对象 | 双闪；timestamp=首次确认闪烁 |
| `hazard_light_reason` | 事故后 / 拥堵缓行 / 临时停车 / 故障施工 / 无双闪 / 不明确 | 双闪原因（无时间戳） |
| `congestion_only` | 是 / 否 | 仅拥堵、无碰撞证据 |
| `smooth_pullover` | 时序对象 | 平稳靠边；timestamp=开始靠边减速 |
| `near_miss` | 时序对象 | 险情未碰；timestamp=最险瞬间 |

---

## 7. 事件时间与事故区域

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_start_sec` | float | 事件开始（碰撞或首个异常行为；负样本填 0） |
| `event_end_sec` | float | 事件结束（状态稳定；负样本填视频时长） |
| `accident_area_box` | [x,y,w,h] 或 null | 事故区域外接框；负样本 null |
| `accident_area_location` | 行车道内 / 路口中央 / 应急车道 / 路边 / 匝道 / 隧道行车道 / 画面边缘 / 不适用 | 事故区域位置 |

---

## 8. 最终标签

| 字段 | 取值 | 说明 |
|---|---|---|
| `accident` | 是 / 否 / 不确定 | 最终事故标签（"不确定"不入训练集） |
| `accident_type` | 无事故 / 追尾 / 侧碰 / 剐蹭 / 正面碰撞 / 撞行人非机动车 / 侧翻 / 撞固定物 / 多车连环 / 起火燃烧 / 不确定 | 事故类型 |
| `confidence` | 高 / 中 / 低 | 标注信心 |

---

## 9. 派生字段

脚本自动计算，人工不填：

| 字段 | 规则 |
|---|---|
| `congestion` | `traffic_flow` ∈ {拥堵, 停止排队} → 是；{畅通, 缓行} → 否；某点中断 → 按上游状态 |
| `hard` | 见第 10 节 |

---

## 10. 准入与校验

### 正样本准入（`accident=是` 须满足之一）

```text
① collision_visible.value = 是
② collision_occluded = 是，且以下 ≥ 2 项为"是"：
   abnormal_stop / bypass_behavior / flow_interruption_point
   （完整版中的 abrupt_trajectory_change / posture_anomaly / people_exit_vehicle
    属于辅助字段，本精简版不强制；若已按完整版标注可一并计入）
③ 强证据任一 value="是"：
   person_down / motor_vehicle_rollover / non_motor_rollover / vehicle_fire
```

### 困难样本（`derived.hard = true`）

```text
正样本：collision_visible.value=否 且 accident=是
负样本：congestion_only=是
       或 hazard_light.value=是 且 accident=否
       或 near_miss.value=是
       或 abnormal_stop.value=是 且 accident=否
```

### 校验要点

```text
① 本规范字段集合必须齐全；
② 时序属性 value=是 时 timestamp_sec 必填且落在 [0, duration_sec]；
③ collision_visible.value=是 与 collision_occluded=是 互斥；
④ accident=是 时准入成立，且 event 四字段有效；
⑤ event_start_sec ≤ event_end_sec。
```

---

## 11. 完整示例

### 示例 1：高速追尾（正样本）

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
  "traffic": {
    "traffic_flow": "某点中断",
    "flow_interruption_point": "是"
  },
  "evidence": {
    "collision_visible": {"value": "是", "timestamp_sec": 6.5},
    "person_down": {"value": "否", "timestamp_sec": null},
    "motor_vehicle_rollover": {"value": "否", "timestamp_sec": null},
    "non_motor_rollover": {"value": "否", "timestamp_sec": null},
    "vehicle_fire": {"value": "否", "timestamp_sec": null},
    "collision_occluded": "否",
    "abnormal_stop": {"value": "是", "timestamp_sec": 7.2},
    "bypass_behavior": {"value": "是", "timestamp_sec": 8.0},
    "hazard_light": {"value": "是", "timestamp_sec": 7.5},
    "hazard_light_reason": "事故后",
    "congestion_only": "否",
    "smooth_pullover": {"value": "否", "timestamp_sec": null},
    "near_miss": {"value": "否", "timestamp_sec": null}
  },
  "event": {
    "event_start_sec": 6.5,
    "event_end_sec": 14.0,
    "accident_area_box": [760, 320, 520, 340],
    "accident_area_location": "行车道内"
  },
  "label": {
    "accident": "是",
    "accident_type": "追尾",
    "confidence": "高"
  },
  "derived": {
    "congestion": "是",
    "hard": false
  }
}
```

### 示例 2：隧道双闪拥堵（困难负样本）

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
  "traffic": {
    "traffic_flow": "拥堵",
    "flow_interruption_point": "否"
  },
  "evidence": {
    "collision_visible": {"value": "否", "timestamp_sec": null},
    "person_down": {"value": "否", "timestamp_sec": null},
    "motor_vehicle_rollover": {"value": "否", "timestamp_sec": null},
    "non_motor_rollover": {"value": "否", "timestamp_sec": null},
    "vehicle_fire": {"value": "否", "timestamp_sec": null},
    "collision_occluded": "否",
    "abnormal_stop": {"value": "否", "timestamp_sec": null},
    "bypass_behavior": {"value": "否", "timestamp_sec": null},
    "hazard_light": {"value": "是", "timestamp_sec": 3.0},
    "hazard_light_reason": "拥堵缓行",
    "congestion_only": "是",
    "smooth_pullover": {"value": "否", "timestamp_sec": null},
    "near_miss": {"value": "否", "timestamp_sec": null}
  },
  "event": {
    "event_start_sec": 0.0,
    "event_end_sec": 20.0,
    "accident_area_box": null,
    "accident_area_location": "不适用"
  },
  "label": {
    "accident": "否",
    "accident_type": "无事故",
    "confidence": "高"
  },
  "derived": {
    "congestion": "是",
    "hard": true
  }
}
```
