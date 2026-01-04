# Windows 编码问题永久解决方案

## 问题背景

Windows系统默认使用GBK编码，导致Python脚本中的中文字符和emoji无法正常显示，出现类似错误：
```
UnicodeEncodeError: 'gbk' codec can't encode character '\u2705' in position 0
```

## 解决方案

我们采用了**三层防御策略**，确保编码问题永久解决：

### 🛡️ 第一层：代码级强制UTF-8

在所有Python文件头部添加：
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import io

# 强制UTF-8编码
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
```

**已修改的文件**:
- ✅ `local_scanner_v2.py` (Lines 2, 42-58)
- ✅ `semantic_cluster.py` (Lines 2, 31-34)

### 🛡️ 第二层：启动脚本设置环境

#### Windows (run_semantic_scan.bat)
```batch
@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
.venv\Scripts\python.exe local_scanner_v2.py --semantic --domain crypto
```

#### Linux/Mac (run_semantic_scan.sh)
```bash
#!/bin/bash
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export LC_ALL=en_US.UTF-8
.venv/bin/python local_scanner_v2.py --semantic --domain crypto
```

### 🛡️ 第三层：emoji替换为ASCII

所有用户可见的输出使用ASCII字符代替emoji：
- ✅ → `[OK]`
- ❌ → `[ERROR]`
- ⚠️ → `[WARNING]`
- 🚀 → `[START]`
- 📊 → `[Step X]`

## 使用方法

### 推荐：使用启动脚本（最简单）

**Windows:**
```cmd
run_semantic_scan.bat
```

**Linux/Mac:**
```bash
chmod +x run_semantic_scan.sh
./run_semantic_scan.sh
```

**自定义参数:**
```cmd
run_semantic_scan.bat --domain crypto --threshold 0.80
```

### 方法2：直接运行Python

如果使用启动脚本，不需要手动设置环境变量。但如果要直接运行Python：

**Windows PowerShell:**
```powershell
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONUTF8="1"
.venv\Scripts\python.exe local_scanner_v2.py --semantic
```

**Windows CMD:**
```cmd
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
.venv\Scripts\python.exe local_scanner_v2.py --semantic
```

**Linux/Mac:**
```bash
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
.venv/bin/python local_scanner_v2.py --semantic
```

## 验证编码已修复

运行以下测试脚本：
```python
# test_encoding.py
import sys
print(f"stdout encoding: {sys.stdout.encoding}")
print(f"stderr encoding: {sys.stderr.encoding}")
print("测试中文显示")
print("[OK] 编码测试通过 ✅")
```

预期输出：
```
stdout encoding: utf-8
stderr encoding: utf-8
测试中文显示
[OK] 编码测试通过 ✅
```

## 技术细节

### 为什么需要三层防御？

1. **代码级设置** - 确保脚本内部处理UTF-8
2. **环境变量** - 影响Python解释器的默认行为
3. **ASCII替换** - 即使前两层失败，也能正常显示

### 关键环境变量说明

| 变量 | 作用 | 值 |
|------|------|-----|
| `PYTHONIOENCODING` | 强制stdin/stdout/stderr编码 | `utf-8` |
| `PYTHONUTF8` | Python 3.7+ UTF-8模式 | `1` |
| `LC_ALL` | 系统locale设置 (Linux/Mac) | `en_US.UTF-8` |
| `LANG` | 系统语言设置 (Linux/Mac) | `en_US.UTF-8` |

### Windows代码页说明

- `chcp 65001` - 切换控制台到UTF-8 (代码页65001)
- `chcp 936` - 默认GBK编码 (代码页936)

## 问题排查

### 如果仍然出现编码错误

1. **检查Python版本**:
   ```bash
   python --version  # 需要 >= 3.7
   ```

2. **检查环境变量**:
   ```bash
   # Windows
   echo %PYTHONIOENCODING%

   # Linux/Mac
   echo $PYTHONIOENCODING
   ```

3. **使用启动脚本**:
   - 启动脚本会自动设置所有必要的环境变量

4. **查看日志文件**:
   ```bash
   python local_scanner_v2.py --semantic 2>&1 | tee scan.log
   ```

## 总结

✅ **已永久解决Windows编码问题**

- 所有输出文件使用UTF-8编码
- 控制台显示使用ASCII替代emoji
- 启动脚本自动配置环境
- 代码内强制UTF-8编码

**以后运行扫描时，直接使用 `run_semantic_scan.bat` 即可，无需担心编码问题！**
