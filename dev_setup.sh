#!/bin/bash

function init_dev_python_env() {
  if [ ! -d "./venv11" ]; then
    python3.11 -m venv ./venv11
  fi
  ./venv11/bin/python -m pip install -U pip --index-url=https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
  #./venv/bin/python -m pip install torch==1.7.1+cpu torchvision==0.8.2+cpu torchaudio==0.7.2 -f https://download.pytorch.org/whl/torch_stable.html
  ./venv11/bin/python -m pip install -r ./requirements.txt \
      --index-url=https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

}


init_dev_python_env
