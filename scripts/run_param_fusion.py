#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行参数传递法融合，并生成不带注释标记的代码文件
"""

import os
import sys
import json
import re

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from main import CodeFusionProcessor


def remove_fusion_markers(code: str) -> str:
    """移除融合标记注释"""
    # 移除 /* === Fused Code Start === */ 和 /* === Fused Code End === */ 及其包裹的内容保持
    patterns = [
        r'/\*\s*===\s*Fused Code Start\s*===\s*\*/\s*\n?',
        r'/\*\s*===\s*Fused Code End\s*===\s*\*/\s*\n?',
        r'/\*\s*中间层函数.*?\*/\s*\n?',
    ]
    
    result = code
    for pattern in patterns:
        result = re.sub(pattern, '', result)
    
    # 清理多余的空行
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result


def generate_clean_code_file(result, target_code: str) -> str:
    """生成干净的代码文件（不带标记注释）"""
    lines = []
    
    # 文件头
    lines.append("/*")
    lines.append(" * 参数传递法融合代码")
    lines.append(f" * 调用链: {' -> '.join(result['call_chain'])}")
    lines.append(f" * 调用深度: {result['call_depth']}")
    lines.append(" *")
    lines.append(" * 原始目标代码:")
    for line in target_code.strip().split('\n'):
        lines.append(f" *   {line.strip()}")
    lines.append(" */")
    lines.append("")
    
    # 头文件
    lines.append("#include <stdio.h>")
    lines.append("#include <stdlib.h>")
    lines.append("#include <string.h>")
    lines.append("")
    
    # 结构体定义（全局状态）
    lines.append("/* 共享状态结构体 */")
    lines.append("typedef struct {")
    lines.append("    int secret;")
    lines.append("    int key;")
    lines.append("} FusionState;")
    lines.append("")
    lines.append("/* 全局状态指针 */")
    lines.append("static FusionState* fusion_state = NULL;")
    lines.append("")
    
    # 函数定义（从最内层到最外层）
    lines.append("/* ========== 函数定义 ========== */")
    lines.append("")
    
    fused_code = result.get('fused_code', {})
    call_chain = result.get('call_chain', [])
    
    for func_name in reversed(call_chain):
        if func_name in fused_code:
            lines.append(f"/* {func_name} */")
            clean_code = remove_fusion_markers(fused_code[func_name])
            lines.append(clean_code)
            lines.append("")
    
    return '\n'.join(lines)


def main():
    # 配置
    input_path = "output/primevul_valid_grouped_depth_4.json"
    output_json = "output/fusion_param_clean.json"
    output_code = "output/fused_code/param_fusion_clean.c"
    
    target_code = "int secret = 42; int key = secret ^ 0xABCD; printf(\"key=%d\", key);"
    
    # 检查输入文件
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_full_path = os.path.join(project_root, input_path)
    
    if not os.path.exists(input_full_path):
        print(f"Error: Input file not found: {input_full_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("参数传递法融合（无标记注释）")
    print("=" * 60)
    print(f"\n目标代码: {target_code}")
    print(f"输入文件: {input_path}")
    print(f"输出JSON: {output_json}")
    print(f"输出代码: {output_code}")
    print("")
    
    # 创建处理器
    processor = CodeFusionProcessor(
        enable_verification=False,  # 禁用验证以加快速度
        enable_syntax_check=False,
        enable_semantic_check=False
    )
    
    # 加载数据
    data = processor.load_data(input_full_path)
    groups = data.get('groups', [])
    
    print(f"共有 {len(groups)} 个调用链组")
    print(f"选择第一个组进行融合...")
    print("")
    
    # 处理第一个组
    group = groups[0]
    result = processor.process_group(
        group,
        target_code,
        group_index=0,
        passing_method="parameter"
    )
    
    if not result.success:
        print(f"融合失败: {result.error_message}")
        sys.exit(1)
    
    print(f"融合成功!")
    print(f"调用链: {' -> '.join(result.call_chain)}")
    print(f"融合点数: {result.total_fusion_points}")
    print("")
    
    # 保存 JSON 结果
    output_data = {
        "metadata": {
            "target_code": target_code,
            "passing_method": "parameter",
            "total_processed": 1,
            "successful": 1
        },
        "results": [{
            "group_index": result.group_index,
            "call_chain": result.call_chain,
            "call_depth": result.call_depth,
            "functions_count": result.functions_count,
            "total_fusion_points": result.total_fusion_points,
            "success": result.success,
            "fused_code": result.fused_code
        }]
    }
    
    output_json_path = os.path.join(project_root, output_json)
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"JSON 结果已保存到: {output_json}")
    
    # 生成干净的代码文件
    clean_code = generate_clean_code_file(output_data['results'][0], target_code)
    
    output_code_path = os.path.join(project_root, output_code)
    os.makedirs(os.path.dirname(output_code_path), exist_ok=True)
    
    with open(output_code_path, 'w', encoding='utf-8') as f:
        f.write(clean_code)
    
    print(f"代码文件已保存到: {output_code}")
    print("")
    print("=" * 60)
    print("融合后的代码预览:")
    print("=" * 60)
    print(clean_code)


if __name__ == '__main__':
    main()
