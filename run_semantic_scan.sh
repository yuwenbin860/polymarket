#!/bin/bash
# ============================================================
# Polymarket 向量化语义扫描启动脚本 (Linux/Mac)
# ============================================================

echo "[启动] Polymarket 向量化语义扫描系统"
echo ""

# 设置UTF-8编码
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

# 默认参数
DOMAIN="crypto"
THRESHOLD="0.85"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain)
            DOMAIN="$2"
            shift 2
            ;;
        --threshold)
            THRESHOLD="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

echo "[配置] 领域: $DOMAIN, 阈值: $THRESHOLD"
echo ""

# 运行扫描
.venv/bin/python local_scanner_v2.py --semantic --domain "$DOMAIN" --threshold "$THRESHOLD"

echo ""
echo "[完成] 扫描已结束"
