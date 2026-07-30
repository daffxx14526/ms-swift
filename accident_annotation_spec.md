# 交通事故视频素材结构化标注规范（分场景版）

> 目的：对路侧监控事故视频进行**结构化、分场景**的要素标注，
> 覆盖所有与"事故是否发生"判断相关的要素，
> 为多任务训练（属性感知 / 证据判断 / 对比判别 / 步骤化推理 / 二分类）提供统一数据基础。

---

## 目录

1. [设计原则](#1-设计原则)
2. [标注体系总览：三层结构](#2-标注体系总览三层结构)
3. [第一层：通用基础字段（所有场景必标）](#3-第一层通用基础字段所有场景必标)
4. [第二层：场景特有字段（按场景分支标注）](#4-第二层场景特有字段按场景分支标注)
5. [第三层：事件级标注（时间段 + 参与者 + 证据链）](#5-第三层事件级标注时间段--参与者--证据链)
6. [标签取值约定与一致性规则](#6-标签取值约定与一致性规则)
7. [标注流程与质检](#7-标注流程与质检)
8. [完整标注示例](#8-完整标注示例)
9. [字段与训练任务的映射关系](#9-字段与训练任务的映射关系)
10. [附录：枚举值字典](#10-附录枚举值字典)

---

## 1. 设计原则

1. **面向判别**：只标注与"事故是否发生"判断相关的要素，不做通用视频描述；
2. **分场景**：不同场景的事故要素不同（高速看应急车道/追尾链，路口看信号灯/行人冲突），
   场景特有字段按场景分支启用，避免"一套字段硬套所有场景"；
3. **证据与结论分离**：先标"看到了什么"（证据字段），再标"结论是什么"（事故标签），
   保证推理类训练数据可以由证据字段模板化生成；
4. **可机读**：所有字段枚举化，一条视频一条 JSON，可直接由脚本转换为训练样本；
5. **不确定性显式化**：看不清、判不了的要素统一标"不确定"，禁止猜测；
6. **困难样本显式打标**：拥堵、双闪、near-miss、遮挡等易混淆样本自动派生 `hard` 标记。

---

## 2. 标注体系总览：三层结构

```text
一条视频的完整标注 = 第一层（通用） + 第二层（场景分支） + 第三层（事件级）

┌─────────────────────────────────────────────────────┐
│ 第一层：通用基础字段（所有场景必标）                    │
│   元信息 / 环境条件 / 画质 / 交通流 / 最终事故标签      │
├─────────────────────────────────────────────────────┤
│ 第二层：场景特有字段（按 scene 分支，只标对应场景的）    │
│   高速高架 / 城市路口 / 城市普通路段 / 隧道 / 匝道收费站 │
├─────────────────────────────────────────────────────┤
│ 第三层：事件级标注（仅事故正样本 + 困难负样本需要）      │
│   时间定位 / 参与者列表 / 证据链清单                    │
└─────────────────────────────────────────────────────┘
```

标注 JSON 顶层结构：

```json
{
  "meta": { },
  "env": { },
  "traffic": { },
  "scene_specific": { },
  "evidence": { },
  "event": { },
  "label": { }
}
```

---

## 3. 第一层：通用基础字段（所有场景必标）

### 3.1 元信息 `meta`

| 字段 | 类型 | 取值 | 说明 |
|---|---|---|---|
| `video_path` | string | - | 视频路径 |
| `duration_sec` | float | - | 视频时长（秒） |
| `camera_view` | enum | 路侧固定 / 高点俯视 / 卡口近景 / 隧道固定 / 其他 | 摄像头视角 |
| `scene` | enum | 高速高架 / 城市路口 / 城市普通路段 / 隧道 / 匝道收费站 / 其他 | **决定第二层启用哪组字段** |
| `annotator_id` | string | - | 标注员编号 |

### 3.2 环境条件 `env`

| 字段 | 取值 | 与事故判断的关系 |
|---|---|---|
| `lighting` | 白天 / 夜间 / 黄昏黎明 / 隧道暗光 | 夜间双闪更醒目、细节更难看清 |
| `weather` | 晴 / 雨 / 雪 / 雾 / 不确定 | 雨雪天临停/缓行增多，误报高发 |
| `road_surface` | 干燥 / 湿滑 / 积水积雪 / 不确定 | 湿滑路面事故形态不同（打滑侧滑） |
| `visibility` | 高 / 中 / 低 | 低能见度样本单独分桶评估 |
| `glare_or_reflection` | 是 / 否 | 夜间灯光反射易误判双闪/碰撞 |

### 3.3 交通流 `traffic`

| 字段 | 取值 | 说明 |
|---|---|---|
| `traffic_flow` | 畅通 / 缓行 / 拥堵 / 停止排队 / 某点中断 | **"某点中断"是事故最强间接信号，必须与"整体拥堵"严格区分** |
| `flow_interruption_point` | 是 / 否 / 不确定 | 交通流是否存在固定中断点（下游畅通、上游积压） |
| `queue_present` | 是 / 否 | 是否排队 |
| `bypass_behavior` | 是 / 否 / 不确定 | 是否有车辆绕行某一固定区域 |
| `pedestrian_gathering` | 是 / 否 | 是否有人员在车行道聚集（事故后常见） |

### 3.4 最终标签 `label`

| 字段 | 取值 | 说明 |
|---|---|---|
| `accident` | 是 / 否 | 最终事故标签（准入规则见第 6 节） |
| `accident_type` | 无事故 / 追尾 / 侧碰 / 剐蹭 / 正面碰撞 / 撞行人非机动车 / 侧翻 / 撞固定物 / 多车连环 / 不确定 | 事故类型 |
| `confidence` | 高 / 中 / 低 | 标注员对结论的信心 |
| `hard` | true / false | 困难样本标记（可由规则自动派生，见 6.3） |

---

## 4. 第二层：场景特有字段（按场景分支标注）

> 只标注 `scene` 对应场景的字段块，其余场景块留空。

### 4.1 高速 / 高架 `scene_specific.highway`

高速场景事故要素特点：车速高、追尾为主、应急车道行为关键、抛洒物与二次事故风险。

| 字段 | 取值 | 与事故判断的关系 |
|---|---|---|
| `emergency_lane_occupied` | 是 / 否 / 无应急车道 | 停在应急车道多为故障临停（负）；停在行车道为强事故信号（正） |
| `stop_position` | 行车道 / 应急车道 / 路肩 / 无停车 | 停车位置是"事故停车 vs 临停"的核心判别点 |
| `rear_end_chain` | 是 / 否 | 是否多车追尾链（前车急停后连锁） |
| `guardrail_impact` | 是 / 否 / 不确定 | 是否撞护栏/隔离带（单车事故常见形态） |
| `debris_on_road` | 是 / 否 / 不确定 | 路面抛洒物/碎片（事故后强证据，也可能是货物掉落） |
| `sudden_brake_wave` | 是 / 否 | 上游车流是否出现连锁急刹（刹车灯波动） |
| `reverse_or_retrograde` | 是 / 否 | 是否有倒车/逆行（错过出口的危险行为，易引发事故） |
| `construction_zone` | 是 / 否 | 施工区（锥桶/围挡导致的缓行是常见误报源） |
| `truck_involved` | 是 / 否 | 是否涉及货车（遮挡大、事故形态不同） |
| `merge_conflict` | 是 / 否 | 匝道汇入区是否存在汇入冲突 |

### 4.2 城市路口 `scene_specific.intersection`

路口场景事故要素特点：转弯冲突、行人/非机动车卷入、信号灯相位相关、低速剐蹭多。

| 字段 | 取值 | 与事故判断的关系 |
|---|---|---|
| `signal_visible` | 是 / 否 | 画面中信号灯是否可见 |
| `signal_state_at_event` | 红 / 绿 / 黄 / 闪烁 / 不可见 | 事件时刻信号状态（闯灯事故归因） |
| `red_light_running` | 是 / 否 / 不确定 | 是否有车辆/行人闯红灯 |
| `turn_conflict` | 是 / 否 | 转弯车与直行车/行人是否存在轨迹冲突 |
| `vru_involved` | 行人 / 非机动车 / 两者 / 无 | 弱势交通参与者是否卷入（VRU 事故形态：倒地、人车分离） |
| `person_down` | 是 / 否 / 不确定 | 是否有人员倒地（VRU 事故最强证据） |
| `crosswalk_area` | 是 / 否 | 事件是否发生在斑马线区域 |
| `queue_at_signal` | 是 / 否 | 是否为等灯排队（路口最常见误报源：**等灯静止 ≠ 事故**） |
| `intersection_blocked` | 是 / 否 | 路口中央是否被车辆异常滞留堵塞 |
| `delivery_rider_involved` | 是 / 否 | 是否涉及外卖/快递电动车（高频事故参与者） |

### 4.3 城市普通路段 `scene_specific.urban_road`

普通路段特点：路边停车干扰大、开门事故、公交站/学校区域、行人横穿。

| 字段 | 取值 | 与事故判断的关系 |
|---|---|---|
| `roadside_parking_present` | 是 / 否 | 路边是否有常态化停车（静止车辆 ≠ 事故的高频场景） |
| `stop_position` | 行车道中间 / 路边贴边 / 公交站 / 无停车 | 停车位置与姿态判别 |
| `door_open_event` | 是 / 否 / 不确定 | 是否开门碰撞（城市特有事故形态） |
| `pedestrian_crossing_midblock` | 是 / 否 | 是否有行人非路口横穿 |
| `vru_involved` | 行人 / 非机动车 / 两者 / 无 | 同路口定义 |
| `person_down` | 是 / 否 / 不确定 | 同路口定义 |
| `bus_stop_area` | 是 / 否 | 公交站区域（频繁停靠是误报源） |
| `double_parked` | 是 / 否 | 是否并排违停（易被误判为事故聚集） |

### 4.4 隧道 `scene_specific.tunnel`

隧道特点：光照突变、无应急车道或极窄、双闪链传播、火灾烟雾风险、误报高发。

| 字段 | 取值 | 与事故判断的关系 |
|---|---|---|
| `tunnel_zone` | 入口段 / 中段 / 出口段 | 入口/出口光照突变区事故与误判高发 |
| `hazard_light_chain` | 是 / 否 | 拥堵时隧道内常出现"双闪链"（多车依次开双闪提醒后车，**不是事故**） |
| `stop_in_lane` | 是 / 否 | 行车道内停车（隧道内无处可停，行车道停车事故概率高于地面道路） |
| `smoke_or_fire` | 是 / 否 / 不确定 | 烟雾/火光（重大事故信号） |
| `lighting_transition_artifact` | 是 / 否 | 是否存在入口/出口强光过渡造成的画面过曝/欠曝 |
| `narrow_shoulder` | 有硬路肩 / 无硬路肩 | 决定"贴边停车"的解释（无路肩时贴边停车也可疑） |

### 4.5 匝道 / 收费站 `scene_specific.ramp_toll`

| 字段 | 取值 | 与事故判断的关系 |
|---|---|---|
| `ramp_type` | 上匝道 / 下匝道 / 收费站广场 / 不确定 | - |
| `weaving_conflict` | 是 / 否 | 交织区变道冲突 |
| `toll_queue` | 是 / 否 | 收费站排队（常态化停止，误报源） |
| `sharp_curve_area` | 是 / 否 | 急弯区域（单车侧翻/撞护栏高发） |

---

## 5. 第三层：事件级标注（时间段 + 参与者 + 证据链）

> 适用范围：所有 `accident=是` 的正样本，以及 `hard=true` 的困难负样本。
> 普通负样本可跳过本层。

### 5.1 时间定位 `event.timeline`

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_start_sec` | float | 事件开始时刻（事故：碰撞或首个异常行为出现；负样本：可疑行为开始） |
| `event_end_sec` | float | 事件结束时刻（状态稳定：车辆静止/恢复通行） |
| `pre_event_visible` | 是 / 否 | 事件前正常状态是否在视频中可见 |
| `collision_moment_visible` | 是 / 否 / 无碰撞 | 碰撞瞬间是否可见 |
| `post_event_visible` | 是 / 否 | 事件后状态是否可见 |
| `event_stage_coverage` | 全过程 / 仅前+后 / 仅后 / 仅前 | 视频覆盖了事件的哪些阶段 |

### 5.2 参与者列表 `event.participants`

数组，每个参与者一条：

| 字段 | 取值 | 说明 |
|---|---|---|
| `type` | 轿车 / SUV / 货车 / 客车 / 摩托车 / 电动车 / 自行车 / 行人 / 固定物 | 参与者类型 |
| `role` | 主动方 / 被动方 / 受波及 / 不确定 | 在事件中的角色 |
| `behavior_before` | 正常行驶 / 变道 / 转弯 / 急刹 / 超速感 / 逆行倒车 / 静止 / 不确定 | 事件前行为 |
| `state_after` | 停止行车道 / 停止路边 / 驶离 / 倒地 / 侧翻 / 姿态歪斜 / 不确定 | 事件后状态 |
| `hazard_light_after` | 是 / 否 / 不可见 | 事件后是否开双闪 |
| `roi_box` | [x, y, w, h] | 参与者主要活动区域框（供 ROI 裁剪管线使用，可选） |

### 5.3 证据链清单 `evidence`

> 这是生成"步骤化推理"训练数据的直接来源，每项均为 是/否/不确定。

**直接证据（可见碰撞类）**

| 字段 | 说明 |
|---|---|
| `collision_visible` | 碰撞/剐蹭/撞击过程可直接看到 |
| `vehicle_deformation` | 车体变形/损伤可见 |
| `person_down` | 人员倒地 |
| `rollover` | 车辆侧翻/翻滚 |
| `debris_scatter` | 碎片飞散/抛洒物出现 |

**间接证据（遮挡/不明显事故的推断依据）**

| 字段 | 说明 |
|---|---|
| `collision_occluded` | 碰撞点被遮挡（配合 `occlusion_type` 使用） |
| `occlusion_type` | 无遮挡 / 事故车自身遮挡 / 其他车辆遮挡 / 设施遮挡 / 画面边缘盲区 |
| `abnormal_stop` | 车辆异常停止（行车道中间/斜停/横跨车道） |
| `abrupt_trajectory_change` | 轨迹突变（急偏转/旋转/弹开） |
| `posture_anomaly` | 停止后姿态歪斜/位置异常 |
| `bypass_behavior` | 周围车辆绕行固定区域 |
| `flow_interruption_point` | 交通流固定点中断 |
| `people_exit_vehicle` | 人员下车查看/聚集 |

**误报相关要素（负样本判别依据）**

| 字段 | 说明 |
|---|---|
| `hazard_light` | 是否有双闪 |
| `hazard_light_reason` | 事故后 / 拥堵缓行 / 临时停车 / 故障施工 / 无双闪 / 不明确 |
| `smooth_pullover` | 是否为平稳减速靠边（临停特征） |
| `near_miss` | 险情但未碰撞（急刹/擦肩） |
| `close_distance_pass` | 近距离通过但无接触 |
| `congestion_only` | 仅拥堵，无任何碰撞证据 |

---

## 6. 标签取值约定与一致性规则

### 6.1 取值约定

1. 所有布尔字段只允许：**是 / 否 / 不确定**（部分字段额外允许"不可见/无"，见各表）；
2. 禁止自由文本代替枚举；确实无法归类时选"其他/不确定"并在 `note` 字段补充；
3. "不确定"的使用标准：正常速度播放 + 逐帧回看后仍无法判断。

### 6.2 事故正样本准入规则

`accident=是` 必须满足以下之一，否则不得标为正样本：

```text
① collision_visible = 是（碰撞过程可见）
② collision_occluded = 是，且以下间接证据 ≥ 2 项为"是"：
   abnormal_stop / abrupt_trajectory_change / posture_anomaly /
   bypass_behavior / flow_interruption_point / people_exit_vehicle
③ 事故后强证据可见（person_down / rollover / vehicle_deformation 任一为"是"）
```

不满足准入规则、但业务系统标记为事故的视频 → 标 `accident=不确定`，**不进入训练集**，单独归档。

### 6.3 困难样本自动派生规则

满足任一条件自动置 `hard=true`：

```text
正样本困难：
  collision_visible=否 且 accident=是            （不明显/遮挡事故）
  event_stage_coverage ∈ {仅后, 仅前+后}          （过程缺失）

负样本困难：
  congestion_only=是                              （拥堵负样本）
  hazard_light=是 且 accident=否                  （双闪负样本）
  near_miss=是 或 close_distance_pass=是          （险情负样本）
  abnormal_stop=是 且 accident=否                 （异常停车但非事故，如故障）
  scene=隧道 且 hazard_light_chain=是             （隧道双闪链）
  queue_at_signal=是（路口等灯静止）
```

### 6.4 场景分支完整性检查

脚本校验规则：

```text
scene=高速高架     → scene_specific.highway 必须非空
scene=城市路口     → scene_specific.intersection 必须非空
scene=城市普通路段 → scene_specific.urban_road 必须非空
scene=隧道         → scene_specific.tunnel 必须非空
scene=匝道收费站   → scene_specific.ramp_toll 必须非空
accident=是        → event 三个子块（timeline/participants/evidence）必须完整
```

---

## 7. 标注流程与质检

### 7.1 标注流程

```text
第 1 步：观看完整视频（正常速度）→ 标注 meta / env / traffic
第 2 步：确定 scene → 展开对应场景分支字段并标注
第 3 步：初判 accident 与 accident_type
第 4 步：若 accident=是 或疑似困难样本 → 逐帧回看，完成第三层事件级标注
第 5 步：按 6.2 准入规则复核 accident 标签
第 6 步：脚本自动派生 hard 标记 + 完整性校验
```

### 7.2 质检要求

| 项目 | 要求 |
|---|---|
| 双人标注 | 全部正样本 + 全部 hard 负样本双人独立标注 |
| 仲裁 | 双人 `accident` 或 `accident_type` 不一致 → 第三人仲裁 |
| 一致性指标 | `accident` 字段双人一致率 ≥ 95%，低于则回炉培训 |
| 抽检 | 普通负样本按 10% 抽检 |
| 迭代 | 每轮训练后的错误归因中发现的标注错误，回写修正并记录 |

---

## 8. 完整标注示例

### 示例 1：高速追尾事故（正样本，碰撞可见）

```json
{
  "meta": {
    "video_path": "/data/videos/hw_00123.mp4",
    "duration_sec": 20.0,
    "camera_view": "路侧固定",
    "scene": "高速高架",
    "annotator_id": "A03"
  },
  "env": {
    "lighting": "白天",
    "weather": "雨",
    "road_surface": "湿滑",
    "visibility": "中",
    "glare_or_reflection": "否"
  },
  "traffic": {
    "traffic_flow": "某点中断",
    "flow_interruption_point": "是",
    "queue_present": "是",
    "bypass_behavior": "是",
    "pedestrian_gathering": "否"
  },
  "scene_specific": {
    "highway": {
      "emergency_lane_occupied": "否",
      "stop_position": "行车道",
      "rear_end_chain": "是",
      "guardrail_impact": "否",
      "debris_on_road": "是",
      "sudden_brake_wave": "是",
      "reverse_or_retrograde": "否",
      "construction_zone": "否",
      "truck_involved": "是",
      "merge_conflict": "否"
    }
  },
  "event": {
    "timeline": {
      "event_start_sec": 6.5,
      "event_end_sec": 14.0,
      "pre_event_visible": "是",
      "collision_moment_visible": "是",
      "post_event_visible": "是",
      "event_stage_coverage": "全过程"
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
  "evidence": {
    "collision_visible": "是",
    "vehicle_deformation": "是",
    "person_down": "否",
    "rollover": "否",
    "debris_scatter": "是",
    "collision_occluded": "否",
    "occlusion_type": "无遮挡",
    "abnormal_stop": "是",
    "abrupt_trajectory_change": "是",
    "posture_anomaly": "是",
    "bypass_behavior": "是",
    "flow_interruption_point": "是",
    "people_exit_vehicle": "否",
    "hazard_light": "是",
    "hazard_light_reason": "事故后",
    "smooth_pullover": "否",
    "near_miss": "否",
    "close_distance_pass": "否",
    "congestion_only": "否"
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
    "camera_view": "隧道固定",
    "scene": "隧道",
    "annotator_id": "A07"
  },
  "env": {
    "lighting": "隧道暗光",
    "weather": "不确定",
    "road_surface": "干燥",
    "visibility": "中",
    "glare_or_reflection": "是"
  },
  "traffic": {
    "traffic_flow": "拥堵",
    "flow_interruption_point": "否",
    "queue_present": "是",
    "bypass_behavior": "否",
    "pedestrian_gathering": "否"
  },
  "scene_specific": {
    "tunnel": {
      "tunnel_zone": "中段",
      "hazard_light_chain": "是",
      "stop_in_lane": "否",
      "smoke_or_fire": "否",
      "lighting_transition_artifact": "否",
      "narrow_shoulder": "无硬路肩"
    }
  },
  "event": {
    "timeline": {
      "event_start_sec": 0.0,
      "event_end_sec": 20.0,
      "pre_event_visible": "是",
      "collision_moment_visible": "无碰撞",
      "post_event_visible": "是",
      "event_stage_coverage": "全过程"
    },
    "participants": []
  },
  "evidence": {
    "collision_visible": "否",
    "vehicle_deformation": "否",
    "person_down": "否",
    "rollover": "否",
    "debris_scatter": "否",
    "collision_occluded": "否",
    "occlusion_type": "无遮挡",
    "abnormal_stop": "否",
    "abrupt_trajectory_change": "否",
    "posture_anomaly": "否",
    "bypass_behavior": "否",
    "flow_interruption_point": "否",
    "people_exit_vehicle": "否",
    "hazard_light": "是",
    "hazard_light_reason": "拥堵缓行",
    "smooth_pullover": "否",
    "near_miss": "否",
    "close_distance_pass": "否",
    "congestion_only": "是"
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

## 9. 字段与训练任务的映射关系

| 训练任务 | 使用的标注字段 |
|---|---|
| 任务A 属性感知 | `scene`、`traffic_flow`、`hazard_light`、`abnormal_stop`、`lighting`、场景分支字段（如 `signal_state_at_event`、`emergency_lane_occupied`） |
| 任务B 证据判断 | `evidence` 全部字段、`hazard_light_reason`、`bypass_behavior` |
| 任务C 对比判别 | `accident` + `congestion_only` / `hazard_light_reason` / `near_miss` / `smooth_pullover` 组合映射四选一答案 |
| 任务D 步骤化推理 | 第 1 步 ← `scene`+`traffic`；第 2 步 ← `participants`+误报要素；第 3 步 ← 直接/间接证据；第 4 步 ← `accident` |
| 任务E 部署二分类 | `accident` |
| ROI 裁剪管线 | `participants[].roi_box`、`event.timeline`（时间窗裁剪） |
| 分桶评估 | `hard` 派生条件、`scene`、`lighting`、`event_stage_coverage` |
| GRPO 数据筛选 | `confidence`、`hard`、准入规则（剔除"不确定"样本） |

场景分支字段的额外价值：可生成**场景特有的判别训练样本**，例如：

```text
高速：  "视频中车辆停在应急车道还是行车道？" → 教模型区分故障临停与事故
路口：  "视频中静止车辆是在等待信号灯吗？"   → 教模型区分等灯与事故
隧道：  "多辆车开双闪是拥堵提醒还是事故？"   → 教模型理解双闪链
```

---

## 10. 附录：枚举值字典

```yaml
scene: [高速高架, 城市路口, 城市普通路段, 隧道, 匝道收费站, 其他]
camera_view: [路侧固定, 高点俯视, 卡口近景, 隧道固定, 其他]
lighting: [白天, 夜间, 黄昏黎明, 隧道暗光]
weather: [晴, 雨, 雪, 雾, 不确定]
road_surface: [干燥, 湿滑, 积水积雪, 不确定]
visibility: [高, 中, 低]
traffic_flow: [畅通, 缓行, 拥堵, 停止排队, 某点中断]
accident_type: [无事故, 追尾, 侧碰, 剐蹭, 正面碰撞, 撞行人非机动车, 侧翻, 撞固定物, 多车连环, 不确定]
occlusion_type: [无遮挡, 事故车自身遮挡, 其他车辆遮挡, 设施遮挡, 画面边缘盲区]
hazard_light_reason: [事故后, 拥堵缓行, 临时停车, 故障施工, 无双闪, 不明确]
participant_type: [轿车, SUV, 货车, 客车, 摩托车, 电动车, 自行车, 行人, 固定物]
participant_role: [主动方, 被动方, 受波及, 不确定]
behavior_before: [正常行驶, 变道, 转弯, 急刹, 超速感, 逆行倒车, 静止, 不确定]
state_after: [停止行车道, 停止路边, 驶离, 倒地, 侧翻, 姿态歪斜, 不确定]
event_stage_coverage: [全过程, 仅前+后, 仅后, 仅前]
tri_state: [是, 否, 不确定]
confidence: [高, 中, 低]
```
