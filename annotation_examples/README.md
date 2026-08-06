# 交通事故标注 JSON 演示样例

本目录提供带 `//` 行内注释的 JSONC 示例，便于阅读字段含义。

| 文件 | 对应规范 |
|---|---|
| `accident_annotation_example_video.jsonc` | `accident_annotation_spec_video.md`（完整版） |
| `accident_annotation_example_video_core.jsonc` | `accident_annotation_spec_video_core.md`（核心字段） |
| `accident_annotation_example_image.jsonc` | `accident_annotation_spec_image.md`（图片完整版） |

约定摘要：

- 视频时序属性：`{ "value", "start_sec", "end_sec", "bbox"? }`
- 位置相关属性：必含 `bbox: [x, y, w, h]`（画面左上角像素坐标）
- 图片无 `start_sec` / `end_sec`
- JSONC 仅用于演示；入库/训练前请去除注释并校验为标准 JSON
