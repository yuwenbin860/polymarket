#!/bin/bash
# Polymarket组合套利系统 - 快速入门脚本

echo "======================================"
echo "Polymarket 组合套利系统 - 快速设置"
echo "======================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到Python3，请先安装"
    exit 1
fi
echo "✅ Python3 已安装"

# 安装依赖
echo ""
echo "正在安装依赖..."
pip3 install requests anthropic --quiet
echo "✅ 依赖安装完成"

# 检查API Key
echo ""
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  未设置 ANTHROPIC_API_KEY 环境变量"
    echo "   系统将使用规则匹配替代LLM分析"
    echo ""
    echo "   如需使用LLM分析，请运行："
    echo "   export ANTHROPIC_API_KEY='your-api-key'"
    echo ""
else
    echo "✅ ANTHROPIC_API_KEY 已设置"
fi

# 提示运行
echo ""
echo "======================================"
echo "设置完成！你可以运行以下命令："
echo "======================================"
echo ""
echo "1. 使用模拟数据测试系统："
echo "   python3 polymarket_arb_mvp.py"
echo ""
echo "2. 扫描真实市场（需要能访问Polymarket）："
echo "   python3 local_scanner.py"
echo ""
echo "3. 查看帮助文档："
echo "   cat README.md"
echo ""
