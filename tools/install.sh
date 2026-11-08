#!/usr/bin/env bash
# install.sh —— mcm-pilot-suite 一键安装（macOS / Linux / WSL / Git Bash）
#   bash tools/install.sh            # 灰度安装（disabled: true）
#   bash tools/install.sh --enable   # 装完直接启用
#   bash tools/install.sh --no-deps  # 跳过 pip 依赖
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
PKG_ROOT="$DSH_HOME/profiles/node_modules"
ENABLE=0
NO_DEPS=0
for a in "$@"; do
  case "$a" in
    --enable) ENABLE=1 ;;
    --no-deps) NO_DEPS=1 ;;
    *) echo "未知参数: $a"; exit 2 ;;
  esac
done

echo "== mcm-pilot-suite 安装 =="
echo "repo     : $REPO"
echo "DSH_HOME : $DSH_HOME"

echo
echo "[1/4] 探测 Python …"
PY="$(node "$REPO/tools/find-python.mjs" || true)"
if [ -z "${PY:-}" ]; then
  echo "找不到可用 Python。请安装 Python 3.8+，或设 MCM_PYTHON 指向解释器后重跑。" >&2
  exit 1
fi
echo "  python: $PY"

if [ "$NO_DEPS" -eq 0 ]; then
  echo
  echo "[2/4] 安装绘图依赖 …"
  "$PY" -m pip install --quiet --upgrade -r "$REPO/packages/plot-tools/requirements.txt" || \
    echo "  依赖安装失败：可手动安装（绘图工具将不可用）"
else
  echo
  echo "[2/4] 跳过依赖（--no-deps）"
fi

echo
echo "[3/4] 复制插件到 profile node_modules …"
mkdir -p "$PKG_ROOT"
for pair in "packages/mcm-pilot:mcm-pilot" "packages/plot-tools:dsh-plot-tools"; do
  src="$REPO/${pair%%:*}"; dst="$PKG_ROOT/${pair##*:}"
  rm -rf "$dst"; cp -R "$src" "$dst"
  find "$dst" -type d \( -name __pycache__ -o -name .mplcache \) -exec rm -rf {} + 2>/dev/null || true
  echo "  ${pair##*:} -> $dst"
done

echo
echo "[4/4] 写配置与接线 …"
CFG="$DSH_HOME/mcm-pilot.config.json"
WS="${MCM_WORKSPACE:-$PWD}"
cat > "$CFG" <<JSON
{
  "python": "$PY",
  "plotPython": "$PY",
  "workspace": "$WS"
}
JSON
echo "  $CFG"
echo "  workspace: $WS（改工作区改这个文件，或设 MCM_WORKSPACE）"

PATCH="$DSH_HOME/cordis.patch.yml"
[ -f "$PATCH" ] && cp "$PATCH" "$PATCH.bak-$(date +%Y%m%d%H%M%S)"
touch "$PATCH"
DISABLED=""
[ "$ENABLE" -eq 0 ] && DISABLED=$'\n      disabled: true'
for pair in "plot-tools:dsh-plot-tools" "mcm-pilot:mcm-pilot"; do
  id="${pair%%:*}"; pkg="${pair##*:}"
  if grep -qE "^[[:space:]]*-?[[:space:]]*id:[[:space:]]*${id}[[:space:]]*$" "$PATCH"; then
    echo "  已存在 id=$id，跳过"
    continue
  fi
  printf '\n- insert:\n    - id: %s\n      name: %s%s\n' "$id" "'$pkg'" "$DISABLED" >> "$PATCH"
  echo "  追加 insert: $id"
done

echo
echo "== 完成 =="
echo "自检：node tools/doctor.mjs --full"
[ "$ENABLE" -eq 0 ] && echo "当前为灰度（disabled: true）：删掉 $PATCH 里对应行的 disabled 即启用，或重跑 --enable。"
echo "重启 DSH（或等 HMR 重载）后，在会话里执行 mcm_start；绘图直接调 plot_data_chart。"
