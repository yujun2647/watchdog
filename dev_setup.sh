#!/bin/bash

function init_dev_python_env() {
  if [ ! -d "./venv" ]; then
    python3 -m venv ./venv
  fi
  ./venv/bin/python -m pip install -U pip --index-url=https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
  ./venv/bin/python -m pip install -r ./requirements.txt \
      --index-url=https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

}

sudo apt install ffmpeg -y
init_dev_python_env
