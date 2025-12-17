<h1 align="center">SliceFusion-LLM</h1>

<p align="center">
  <strong>基于函数调用链的智能代码分片融合技术</strong>
</p>

## 概述

**SliceFusion-LLM** 是一个智能代码融合工具，能够将目标代码片段智能地拆分并嵌入到已有程序的多个函数调用链中。该技术融合了程序分析、编译原理和大语言模型（LLM）三大领域的方法论。

### 核心思路

```
目标代码 → [LLM智能拆分] → 代码片段序列 → [融合到调用链] → 混淆后代码
     │                                              │
     └──────── 语义等价性验证 ◄─────────────────────┘
```

## 特性

- **智能代码拆分** - 利用 LLM 进行语义感知的代码分片，自动处理变量依赖
- **控制流分析** - 构建 CFG，计算支配关系，精确定位融合点
- **多种传递方式** - 支持全局变量和参数传递两种跨函数状态共享机制
- **多层验证机制** - 语法结构验证 + LLM 语义审查，确保融合正确性
- **批量测试支持** - 支持多组调用链批量融合测试

## 快速开始

### 环境配置

```bash
# 克隆仓库
git clone https://github.com/yourusername/SliceFusion-LLM.git
cd SliceFusion-LLM

# 创建虚拟环境
conda create -n slicefusion python=3.10
conda activate slicefusion

# 安装依赖
pip install -r src/requirements.txt

# 配置 API Key
export DASHSCOPE_API_KEY="your-api-key-here"
```

### 基本使用

```bash
# 1. 数据预处理 - 提取调用关系
python utils/data_process/extract_call_relations.py \
    --input data/primevul_valid.jsonl \
    --output output/primevul_valid_grouped.json

# 2. 按调用深度筛选（深度≥4的调用链）
python utils/data_process/filter_by_call_depth.py \
    --input output/primevul_valid_grouped.json \
    --depth 4

# 3. 执行代码融合（全局变量法）
python src/main.py \
    --input output/primevul_valid_grouped_depth_4.json \
    --output output/fusion_results.json \
    --target-code "int secret = 42; int key = secret ^ 0xABCD; printf(\"key=%d\", key);" \
    --method global \
    --max-groups 5

# 4. 执行代码融合（参数传递法）
python scripts/run_param_fusion.py --groups 5
```

## 融合方法

### 方法一：全局变量法

通过全局变量在调用链的各函数间共享状态。

```bash
python src/main.py \
    --input output/primevul_valid_grouped_depth_4.json \
    --method global \
    --max-groups 5
```

**融合效果**：

```c
static int g_secret;
static int g_key;

void func1() {
    g_secret = 42;              // 片段1：初始化
    func2();
}

void func2() {
    g_key = g_secret ^ 0xABCD;  // 片段2：计算
    func3();
}

void func3() {
    printf("key=%d", g_key);    // 片段3：输出
}
```

### 方法二：参数传递法（推荐）

通过修改函数签名和参数传递状态，无需全局变量，更加隐蔽。

```bash
# 单组测试
python scripts/run_param_fusion.py

# 多组测试
python scripts/run_param_fusion.py --groups 5

# 自定义目标代码
python scripts/run_param_fusion.py \
    --target "int a=10; int b=20; printf(\"%d\", a+b);" \
    --groups 3
```

**融合效果**：

```c
void func1() {
    int secret = 42;
    func2(&secret);             // 传递指针
}

void func2(int* p_secret) {
    int key = (*p_secret) ^ 0xABCD;
    func3(&key);                // 继续传递
}

void func3(int* p_key) {
    printf("key=%d", *p_key);   // 使用参数
}
```

**数据流示意**：

```
┌─────────────────────────────────────────────────────────────────┐
│ crypto_get_certificate_data                                     │
│   int secret = 42;                                              │
│   crypto_cert_fingerprint(xcert, &secret);     ← 传递 &secret   │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ crypto_cert_fingerprint(xcert, int* p_secret)                   │
│   int key = (*p_secret) ^ 0xABCD;              ← 计算 key       │
│   crypto_cert_fingerprint_by_hash(..., &key);  ← 传递 &key      │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ crypto_cert_fingerprint_by_hash(..., int* p_key)                │
│   crypto_cert_hash(..., p_key);                ← 继续传递       │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ crypto_cert_hash(..., int* p_key)                               │
│   printf("key=%d", *p_key);                    ← 最终输出       │
└─────────────────────────────────────────────────────────────────┘
```

## 使用示例

### 示例 1：批量融合测试

```bash
# 测试 10 组不同的调用链
python scripts/run_param_fusion.py --groups 10
```

输出：
```
============================================================
参数传递法融合 - 测试 10 组
============================================================
目标代码: int secret = 42; int key = secret ^ 0xABCD; printf("key=%d", key);

[1/10] 处理: crypto_get_certificate_data -> crypto_cert_fingerprint...
       ✓ 成功
[2/10] 处理: zend_throw_exception_object -> zend_throw_exception_internal...
       ✓ 成功
...

============================================================
测试结果汇总
============================================================
成功: 10/10
失败: 0/10
```

### 示例 2：多参数传递

```bash
python scripts/run_param_fusion.py \
    --target "int a = 10; int b = 20; int c = a + b; printf(\"sum=%d\", c);" \
    --groups 3
```

### 示例 3：带验证的融合

```bash
# 完整验证（语法 + LLM语义审查）
python src/main.py \
    --input output/primevul_valid_grouped_depth_4.json \
    --target-code "int x = 10; x = x * 2; printf(\"%d\", x);" \
    --max-groups 2

# 禁用验证（快速模式）
python src/main.py \
    --input output/primevul_valid_grouped_depth_4.json \
    --target-code "int x = 10; printf(\"%d\", x);" \
    --no-verify \
    --max-groups 5
```

### 示例 4：仅分析模式

```bash
# 仅分析调用链，不执行融合
python src/main.py \
    --input output/primevul_valid_grouped_depth_4.json \
    --analyze-only
```

## 输出文件

### 参数传递法输出

```
output/
├── fusion_param_results.json           # 汇总结果
└── fused_code/
    ├── param_group_0_xxx.c             # 组0融合代码
    ├── param_group_1_xxx.c             # 组1融合代码
    └── ...
```

### 全局变量法输出

```
output/
├── fusion_results.json                 # 汇总结果
└── fused_code/
    ├── all_fused_code.c                # 所有融合代码
    ├── fused_group_0_xxx.c             # 组0融合代码
    └── ...
```

## 技术架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SliceFusion-LLM System                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  输入层          数据处理层           分析层            拆分层               │
│  ┌─────┐      ┌─────────────┐     ┌──────────┐      ┌─────────────┐        │
│  │JSONL│  →   │ 调用关系提取 │  →  │ CFG构建  │  →   │ LLM代码拆分 │        │
│  │源码 │      │ 调用链筛选   │     │ 支配分析 │      │ Fallback    │        │
│  └─────┘      └─────────────┘     └──────────┘      └─────────────┘        │
│                                                            │                │
│                                                            ▼                │
│  输出层          验证层                              融合层                  │
│  ┌─────┐      ┌─────────────┐                    ┌─────────────┐           │
│  │.c   │  ←   │ 语法验证    │  ←                 │ 状态生成    │           │
│  │文件 │      │ LLM语义审查 │                    │ 代码插入    │           │
│  └─────┘      └─────────────┘                    └─────────────┘           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 项目结构

```
SliceFusion-LLM/
├── src/                              # 核心源代码
│   ├── main.py                       # 主程序入口（全局变量法）
│   ├── cfg_analyzer.py               # CFG 分析器
│   ├── dominator_analyzer.py         # 支配节点分析器
│   ├── llm_splitter.py               # LLM 代码拆分器
│   ├── code_fusion.py                # 代码融合引擎
│   ├── syntax_validator.py           # 语法验证器
│   ├── semantic_reviewer.py          # 语义审查器
│   └── verification_agent.py         # 验证代理
│
├── scripts/                          # 脚本工具
│   └── run_param_fusion.py           # 参数传递法融合脚本
│
├── utils/data_process/               # 数据处理工具
│   ├── extract_call_relations.py     # 调用关系提取
│   └── filter_by_call_depth.py       # 调用深度筛选
│
├── data/                             # 数据集
├── output/                           # 输出目录
│   ├── fused_code/                   # 融合后的代码
│   ├── fusion_param_results.json     # 参数传递法结果
│   └── fusion_results.json           # 全局变量法结果
│
├── SliceFusion/                      # LLVM Pass 实现 (C++)
└── docs/                             # 详细文档
```