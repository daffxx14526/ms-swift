#!/usr/bin/env bash
# Rex-Omni 预标注环境一键部署脚本
#
# 用法：
#   bash scripts/setup_env.sh              # GPU 环境（CUDA 12.8 wheel，可用 TORCH_INDEX_URL 覆盖）
#   TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu bash scripts/setup_env.sh   # CPU 验证环境
#   WITH_FLASH_ATTN=1 bash scripts/setup_env.sh   # 追加安装 flash-attn（需 CUDA 编译环境）
#   WITH_VLLM=1 bash scripts/setup_env.sh         # 追加安装 vLLM（批量推理提速）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
PY="${PYTHON:-$(command -v python || command -v python3)}"

echo "==> [1/4] 安装 PyTorch (${TORCH_INDEX_URL})"
"${PY}" -m pip install "torch==2.7.0" torchvision --index-url "${TORCH_INDEX_URL}"

echo "==> [2/4] 安装 Rex-Omni 核心依赖（跳过 flash-attn/vllm/gradio 等可选重依赖）"
"${PY}" -m pip install \
    "transformers==4.51.3" \
    "qwen_vl_utils==0.0.14" \
    "accelerate==1.10.1" \
    "numpy==1.26.4" \
    "Pillow==10.4.0" \
    "matplotlib==3.10.6" \
    "pydantic==2.10.6"

echo "==> [3/4] 安装 vendored Rex-Omni 官方包（--no-deps，依赖已在上一步装好）"
"${PY}" -m pip install -e "${ROOT_DIR}/Rex-Omni" --no-deps

echo "==> [4/4] 安装预标注工具库依赖"
"${PY}" -m pip install -r "${ROOT_DIR}/requirements.txt"

if [[ "${WITH_FLASH_ATTN:-0}" == "1" ]]; then
    echo "==> [可选] 安装 flash-attn（编译可能耗时较长）"
    "${PY}" -m pip install "flash-attn==2.7.4.post1" --no-build-isolation
fi

if [[ "${WITH_VLLM:-0}" == "1" ]]; then
    echo "==> [可选] 安装 vLLM"
    "${PY}" -m pip install "vllm==0.9.1"
fi

echo "==> 验证安装"
"${PY}" -c "
from rex_omni import RexOmniWrapper, RexOmniVisualize, TaskType  # noqa: F401
print('rex_omni 导入成功')
"
"${PY}" -c "
import sys; sys.path.insert(0, '${ROOT_DIR}')
from rex_preannotate import RexPreannotator, CategoryMap  # noqa: F401
print('rex_preannotate 导入成功')
"

echo ""
echo "部署完成。下一步："
echo "  1) 下载模型:   python scripts/download_model.py --source modelscope --local-dir ./models/Rex-Omni"
echo "  2) 图片预标注: python scripts/preannotate_images.py --model-path ./models/Rex-Omni --image-dir <图片目录> --output-dir ./output/images"
echo "提示: 未安装 flash-attn 时请给预标注脚本加 --attn-impl sdpa"
