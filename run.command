#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "请先按 README.md 安装依赖。"
  read -r -p "按回车关闭窗口…"
  exit 1
fi
exec .venv/bin/python -m deskpaw
