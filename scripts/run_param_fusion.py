#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参数传递法融合 - 支持多参数传递和多组测试
"""

import os
import sys
import json
import re
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from openai import OpenAI


def get_llm_client():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("请设置 DASHSCOPE_API_KEY 环境变量")
    return OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")


def get_original_functions(functions: list, call_chain: list) -> dict:
    result = {}
    for func_name in call_chain:
        for func in functions:
            code = func.get('func', '')
            if func_name in code:
                result[func_name] = code
                break
    return result


def create_prompt(target_code: str, original_funcs: dict, call_chain: list) -> str:
    funcs_text = ""
    for name in call_chain:
        if name in original_funcs:
            funcs_text += f"=== {name} ===\n{original_funcs[name]}\n\n"
    
    n = len(call_chain)
    
    return f"""将目标代码通过参数传递方式融合到调用链函数中。

目标代码:
{target_code}

调用链 ({n} 层): {' -> '.join(call_chain)}

原始函数:
{funcs_text}

融合规则（参数传递法）:
1. 分析目标代码中的所有变量和操作
2. 将变量初始化、计算、使用分散到调用链的不同层级
3. 通过添加函数参数（指针）在层级间传递变量
4. 每个函数可以传递多个参数

具体要求:
- 第1层（{call_chain[0]}）：定义初始变量，通过指针传递给下一层
- 中间层：接收上层参数，执行计算，传递结果给下一层
- 最后层（{call_chain[-1]}）：接收参数，执行最终操作（如printf）

输出要求:
- 每个函数输出完整代码
- 不要添加任何注释
- 保持原函数逻辑完整

返回格式:
{{
{', '.join([f'"{name}": "完整函数代码"' for name in call_chain])}
}}"""


def remove_comments(code: str) -> str:
    code = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    code = re.sub(r'\n{3,}', '\n\n', code)
    return code.strip()


def parse_response(response: str) -> dict:
    def try_parse(text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        return None
    
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
    if match:
        result = try_parse(match.group(1))
        if result:
            return result
    
    result = try_parse(response)
    if result:
        return result
    
    match = re.search(r'\{[\s\S]*\}', response)
    if match:
        result = try_parse(match.group(0))
        if result:
            return result
    
    try:
        result = {}
        func_pattern = r'"(\w+)":\s*"((?:[^"\\]|\\.)*)(?:"|$)'
        for match in re.finditer(func_pattern, response, re.DOTALL):
            name = match.group(1)
            code = match.group(2)
            code = code.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
            result[name] = code
        if result:
            return result
    except:
        pass
    
    return None


def process_group(client, group: dict, target_code: str, group_idx: int) -> dict:
    """处理单个调用链组"""
    functions = group['functions']
    call_chain = group['longest_call_chain']
    
    original_funcs = get_original_functions(functions, call_chain)
    
    if len(original_funcs) < len(call_chain):
        return {"success": False, "error": "无法提取所有函数", "call_chain": call_chain}
    
    prompt = create_prompt(target_code, original_funcs, call_chain)
    
    try:
        completion = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是代码融合专家。只返回JSON，不要添加任何注释到代码中。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )
        
        response = completion.choices[0].message.content
        result = parse_response(response)
        
        if not result:
            return {"success": False, "error": "JSON解析失败", "call_chain": call_chain}
        
        for name in result:
            result[name] = remove_comments(result[name])
        
        return {
            "success": True,
            "group_idx": group_idx,
            "call_chain": call_chain,
            "fused_functions": result
        }
    except Exception as e:
        return {"success": False, "error": str(e), "call_chain": call_chain}


def generate_code_file(result: dict) -> str:
    """生成代码文件内容"""
    call_chain = result['call_chain']
    fused_functions = result['fused_functions']
    
    lines = ["#include <stdio.h>", "#include <stdlib.h>", "#include <string.h>", ""]
    for name in reversed(call_chain):
        if name in fused_functions:
            lines.append(fused_functions[name])
            lines.append("")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='参数传递法融合')
    parser.add_argument('--target', '-t', type=str, default=None, help='目标代码')
    parser.add_argument('--groups', '-g', type=int, default=1, help='测试组数（默认1）')
    parser.add_argument('--multi', '-m', action='store_true', help='使用多参数测试用例')
    args = parser.parse_args()
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_path = os.path.join(project_root, "output/primevul_valid_grouped_depth_4.json")
    output_dir = os.path.join(project_root, "output")
    code_dir = os.path.join(output_dir, "fused_code")
    
    if args.target:
        target_code = args.target
    elif args.multi:
        target_code = 'int a = 10; int b = 20; int c = a + b; printf("sum=%d, a=%d, b=%d", c, a, b);'
    else:
        target_code = 'int secret = 42; int key = secret ^ 0xABCD; printf("key=%d", key);'
    
    print("=" * 60)
    print(f"参数传递法融合 - 测试 {args.groups} 组")
    print("=" * 60)
    print(f"目标代码: {target_code}\n")
    
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    groups = data['groups']
    num_groups = min(args.groups, len(groups))
    
    print(f"可用调用链组: {len(groups)}")
    print(f"将测试: {num_groups} 组\n")
    
    client = get_llm_client()
    results = []
    success_count = 0
    
    for i in range(num_groups):
        group = groups[i]
        call_chain = group['longest_call_chain']
        
        print(f"[{i+1}/{num_groups}] 处理: {' -> '.join(call_chain[:2])}...")
        
        result = process_group(client, group, target_code, i)
        results.append(result)
        
        if result['success']:
            success_count += 1
            print(f"       ✓ 成功")
            
            # 保存单独的代码文件
            chain_name = "_".join(call_chain[:2])
            code_file = os.path.join(code_dir, f"param_group_{i}_{chain_name}.c")
            code_content = generate_code_file(result)
            
            os.makedirs(code_dir, exist_ok=True)
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code_content)
        else:
            print(f"       ✗ 失败: {result['error']}")
    
    # 保存汇总 JSON
    output_json = os.path.join(output_dir, "fusion_param_results.json")
    output_data = {
        "metadata": {
            "target_code": target_code,
            "passing_method": "parameter",
            "total_groups": num_groups,
            "success_count": success_count,
            "failed_count": num_groups - success_count
        },
        "results": results
    }
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"成功: {success_count}/{num_groups}")
    print(f"失败: {num_groups - success_count}/{num_groups}")
    print(f"JSON: {output_json}")
    print(f"代码目录: {code_dir}")
    
    # 显示成功的结果
    if success_count > 0:
        print("\n成功的调用链:")
        for r in results:
            if r['success']:
                print(f"  - Group {r['group_idx']}: {' -> '.join(r['call_chain'])}")


if __name__ == '__main__':
    main()
