#!/usr/bin/env bash
# fwd_download.sh —— 下载正向反应预测模型到 data/forward/模型（走 Clash 代理，支持断点续传）
# 注意：curl 是原生 Windows 程序，不能直接接收中文路径；故先 cd 进目录再用相对文件名。
set -u
PROXY="http://127.0.0.1:7890"
ROOT="C:/Users/zzl/Desktop/hx/data/forward/模型"

dl() {
  local repo="$1"; shift
  cd "$ROOT" || exit 1
  mkdir -p "$repo"
  cd "$repo" || exit 1
  for f in "$@"; do
    local url="https://huggingface.co/$repo/resolve/main/$f"
    echo "[DL] $repo/$f"
    curl -x "$PROXY" -L --fail --retry 5 --retry-delay 3 -C - -o "$f" "$url"
    if [ $? -ne 0 ]; then echo "  !! FAIL $repo/$f"; else echo "  OK $(stat -c %s "$f" 2>/dev/null) bytes"; fi
  done
}

COMMON="config.json generation_config.json special_tokens_map.json tokenizer.json tokenizer_config.json"

# 主力：USPTO 微调版
dl "ReactionT5v2-forward-USPTO_MIT" model.safetensors $COMMON
# 备选：ORD 版（泛化更好）
dl "ReactionT5v2-forward" model.safetensors $COMMON

echo "[DONE]"
