#!/usr/bin/env bash
# WSL / Linux 本地开发自检启动脚本。
# 首次运行会自动创建 .venv 并安装依赖。
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "首次运行：创建虚拟环境并安装依赖…"
  python3 -m venv .venv
  .venv/bin/pip install -U pip -q
  .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python -m dingpan.main
