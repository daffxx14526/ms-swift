# Vendored: Rex-Omni 官方库（核心部分）

- 上游仓库: https://github.com/IDEA-Research/Rex-Omni
- 上游 commit: `6508981c1e0c3fbb2dbe7b962a4bb745005f3e2e`（2026-08 主分支）
- 许可证: IDEA License 1.0（见本目录 `LICENSE`；模型基于 Qwen，另受 Qwen Research License 约束）

## 保留内容

| 文件/目录 | 说明 |
|---|---|
| `rex_omni/` | 核心 Python 包（wrapper / tasks / parser / utils） |
| `setup.py` / `requirements.txt` | 安装配置与官方依赖 |
| `app.py` | 官方 Gradio 交互 demo |
| `LICENSE` / `README.md` | 许可证与官方文档 |

## 裁剪内容（与预标注部署无关的大文件）

- `.git/`（19M）、`tutorials/`（14M，教程测试图片）、`assets/`（6.7M，演示素材）
- `finetuning/`、`evaluation/`、`applications/`（微调/评测/应用示例，需要时到上游获取）

## 安装方式

不要单独在此目录 `pip install -r requirements.txt`（官方依赖固定了 flash-attn/vllm 等重依赖，
编译易失败）。请使用上级目录的一键部署脚本：

```bash
cd ..           # 回到 rex_omni_preannotation/
bash scripts/setup_env.sh
```
