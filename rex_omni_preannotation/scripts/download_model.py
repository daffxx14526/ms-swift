#!/usr/bin/env python3
"""下载 Rex-Omni 模型权重到本地目录（HuggingFace 或 ModelScope）。

用法：
    python scripts/download_model.py --source hf --local-dir ./models/Rex-Omni
    python scripts/download_model.py --source hf --hf-mirror --local-dir ./models/Rex-Omni
    python scripts/download_model.py --source modelscope --local-dir ./models/Rex-Omni
    python scripts/download_model.py --source hf --repo IDEA-Research/Rex-Omni-AWQ \
        --local-dir ./models/Rex-Omni-AWQ
"""

import argparse
import os
from pathlib import Path


def download_from_hf(repo: str, local_dir: str, use_mirror: bool) -> str:
    if use_mirror:
        os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
    from huggingface_hub import snapshot_download
    path = snapshot_download(repo_id=repo, local_dir=local_dir)
    return path


def download_from_modelscope(repo: str, local_dir: str) -> str:
    from modelscope import snapshot_download
    path = snapshot_download(repo, local_dir=local_dir)
    return path


def main():
    parser = argparse.ArgumentParser(description='下载 Rex-Omni 模型到本地')
    parser.add_argument('--source', choices=['hf', 'modelscope'], default='hf',
                        help='下载源：hf (HuggingFace) 或 modelscope')
    parser.add_argument('--repo', default='IDEA-Research/Rex-Omni',
                        help='模型仓库 ID（AWQ 量化版: IDEA-Research/Rex-Omni-AWQ）')
    parser.add_argument('--local-dir', default='./models/Rex-Omni',
                        help='本地保存目录')
    parser.add_argument('--hf-mirror', action='store_true',
                        help='HuggingFace 走 hf-mirror.com 镜像（国内网络推荐）')
    args = parser.parse_args()

    local_dir = Path(args.local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    print(f'开始下载 {args.repo} -> {local_dir} (source={args.source})')
    if args.source == 'hf':
        path = download_from_hf(args.repo, str(local_dir), args.hf_mirror)
    else:
        path = download_from_modelscope(args.repo, str(local_dir))
    print(f'下载完成: {path}')
    print(f'后续脚本使用: --model-path {path}')


if __name__ == '__main__':
    main()
