# 交通事故图片标注规范（核心字段版）

> 本文档是《accident_annotation_spec_image.md》的**精简版**：
> 只保留事故判定所需的**最高优先级**字段，JSON **不再**使用优先级分组键。
>
> 完整字段、场景要素、环境细节见完整版规范；判定细则见《accident_annotation_criteria.md》
> （时序类标准不适用于图片）。

---

## 目录

1. [适用范围](#1-适用范围)
2. [JSON 结构总览](#2-json-结构总览)
3. [元信息](#3-元信息)
4. [交通状态（静态代理）](#4-交通状态静态代理)
5. [静态证据](#5-静态证据)
6. [事故区域](#6-事故区域)
7. [最终标签](#7-最终标签)
8. [派生字段](#8-派生字段)
9. [准入与校验](#9-准入与校验)
10. [完整示例](#10-完整示例)

---

## 1. 适用范围

- 仅覆盖细标图片**必须标注**的核心字段；
- 不含环境、场景要素、参与者列表等辅助字段；
- 图片无时间轴：不使用 `{value, timestamp_sec}`，也不标注 `event_start/end_sec`。

---

## 2. JSON 结构总览

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

## 3. 元信息

| 字段 | 类型 | 取值 | 说明 |
|---|---|---|---|
| `media_type` | enum | image | 固定 |
| `image_path` | string | - | 图片路径 |
| `image_source` | enum | independent / video_frame | 来源 |
| `source_video_path` | string 或 null | - | 来源视频（抽帧时填） |
| `frame_time_sec` | float 或 null | - | 抽帧时刻（抽帧时填） |
| `scene` | enum | 高速高架 / 城市路口 / 城市普通路段 / 隧道 / 匝道收费站 / 其他 | 场景类别，必填 |
| `camera_view` | enum | 路侧固定 / 高点俯视 / 卡口近景 / 隧道固定 / 其他 | 视角 |
| `annotator_id` | string | - | 标注员编号 |

---

## 4. 交通状态（静态代理）

| 字段 | 取值 | 说明 |
|---|---|---|
| `traffic_density` | 稀疏 / 中等 / 密集 / 排队队形 | 静态密度 |
| `flow_gap_pattern` | 是 / 否 / 不确定 | 断层形态：上游积压、下游空置 |

---

## 5. 静态证据

### 直接静态证据

| 字段 | 取值 | 说明 |
|---|---|---|
| `collision_contact_visible` | 是 / 否 / 不确定 | 两目标接触/贴合状态可见 |
| `person_down` | 是 / 否 / 不确定 | 行人/骑车人倒地 |
| `motor_vehicle_rollover` | 是 / 否 / 不确定 | 机动车侧翻 |
| `non_motor_rollover` | 是 / 否 / 不确定 | 非机动车侧翻 |
| `vehicle_fire` | 是 / 否 / 不确定 | 机动车着火 |
| `vehicle_deformation` | 是 / 否 / 不确定 | 车损可见 |

### 间接静态证据

| 字段 | 取值 | 说明 |
|---|---|---|
| `abnormal_stop_posture` | 是 / 否 / 不确定 | 异常停放形态（车道中间/斜停/跨线） |
| `collision_area_occluded` | 是 / 否 | 疑似事故区域被遮挡 |
| `lane_avoidance_pattern` | 是 / 否 / 不确定 | 绕行队形 |

### 误报判别

| 字段 | 取值 | 说明 |
|---|---|---|
| `rear_lights_on_both_sides` | 是 / 否 / 不可见 | 左右尾灯同时亮（疑似双闪的静态依据） |
| `congestion_only_suspected` | 是 / 否 | 仅密集/排队，无碰撞证据 |
| `normal_parking_posture` | 是 / 否 / 不确定 | 规范停放形态（临停特征） |

---

## 6. 事故区域

| 字段 | 类型 | 说明 |
|---|---|---|
| `accident_area_box` | [x,y,w,h] 或 null | 事故区域外接框；负样本 null |
| `accident_area_location` | 行车道内 / 路口中央 / 应急车道 / 路边 / 匝道 / 隧道行车道 / 画面边缘 / 不适用 | 位置类别 |

---

## 7. 最终标签

| 字段 | 取值 | 说明 |
|---|---|---|
| `accident` | 是 / 否 / 不确定 | 图片事故标签（比视频更严格；"不确定"不入训） |
| `accident_type` | 无事故 / 追尾 / 侧碰 / 剐蹭 / 正面碰撞 / 撞行人非机动车 / 侧翻 / 撞固定物 / 多车连环 / 起火燃烧 / 不确定 | 类型 |
| `confidence` | 高 / 中 / 低 | 标注信心 |

---

## 8. 派生字段

| 字段 | 规则 |
|---|---|
| `hard` | 见第 9 节 |
| `congestion_suspected` | `traffic_density` ∈ {密集, 排队队形} → 是 |

---

## 9. 准入与校验

### 正样本准入（比视频严格）

```text
① 直接证据任一为"是"：
   collision_contact_visible / person_down / motor_vehicle_rollover /
   non_motor_rollover / vehicle_fire
② vehicle_deformation=是 且 abnormal_stop_posture=是
③ abnormal_stop_posture=是 且 lane_avoidance_pattern=是
   （完整版还可计入 debris_scatter / people_gathered_around / fluid_on_road）
```

无直接证据时宁标 `不确定`。

### 困难样本（`derived.hard = true`）

```text
正样本：collision_contact_visible=否 且 accident=是
负样本：congestion_only_suspected=是
       或 rear_lights_on_both_sides=是 且 accident=否
       或 abnormal_stop_posture=是 且 accident=否
```

### 校验要点

```text
① 本规范字段集合必须齐全；
② collision_contact_visible=是 与 collision_area_occluded=是 互斥；
③ accident=是 时准入成立，且 accident_area 字段有效。
```

---

## 10. 完整示例

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
  "traffic": {
    "traffic_density": "中等",
    "flow_gap_pattern": "否"
  },
  "evidence": {
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
  "event": {
    "accident_area_box": [540, 410, 380, 260],
    "accident_area_location": "路口中央"
  },
  "label": {
    "accident": "是",
    "accident_type": "撞行人非机动车",
    "confidence": "高"
  },
  "derived": {
    "hard": false,
    "congestion_suspected": "否"
  }
}
```
