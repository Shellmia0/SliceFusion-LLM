#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从分组后的 JSON 文件中，筛选出特定调用链深度的组。

调用链深度定义：
- caller -> callee 是深度 2
- caller -> caller -> func 是深度 3
- caller -> caller -> caller -> func 是深度 4
"""

import json
import re
import os
import argparse
from collections import defaultdict
from typing import Dict, List, Set, Optional, Tuple


def extract_function_name(func_code: str) -> Optional[str]:
    """
    从函数代码中提取函数名。
    """
    code = re.sub(r'//.*?\n', '\n', func_code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    patterns = [
        r'(?:[\w\s\*&<>,]+?)\s+(\w+::~?\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*(?:final)?\s*(?:\{|:)',
        r'^[\s]*(\w+::~?\w+)\s*\([^)]*\)\s*(?:\{|:)',
        r'(?:[\w\s\*&<>,]+?)\s+(\w+)\s*\([^)]*\)\s*\{',
        r'^\s*(?:static\s+)?(?:inline\s+)?(?:virtual\s+)?(?:[\w\*&<>,\s]+)\s+(\w+)\s*\(',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, code, re.MULTILINE)
        if match:
            func_name = match.group(1)
            if '::' in func_name:
                func_name = func_name.split('::')[-1]
            return func_name
    
    return None


def extract_function_calls(func_code: str, self_name: Optional[str] = None) -> Set[str]:
    """
    从函数代码中提取所有被调用的函数名。
    """
    code = re.sub(r'//.*?\n', '\n', func_code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
    code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
    
    keywords = {
        'if', 'else', 'while', 'for', 'switch', 'case', 'return', 'break',
        'continue', 'sizeof', 'typeof', 'alignof', 'decltype', 'static_cast',
        'dynamic_cast', 'reinterpret_cast', 'const_cast', 'new', 'delete',
        'throw', 'catch', 'try', 'namespace', 'class', 'struct', 'enum',
        'union', 'typedef', 'using', 'template', 'typename', 'public',
        'private', 'protected', 'virtual', 'override', 'final', 'explicit',
        'inline', 'static', 'extern', 'const', 'volatile', 'mutable',
        'register', 'auto', 'default', 'goto', 'asm', '__asm', '__asm__',
    }
    
    pattern = r'\b([a-zA-Z_]\w*)\s*\('
    matches = re.findall(pattern, code)
    
    callees = set()
    for name in matches:
        if name not in keywords:
            if self_name is None or name != self_name:
                callees.add(name)
    
    return callees


def compute_call_depth(group: List[Dict]) -> Tuple[int, List[str]]:
    """
    计算一个组内的最大调用链深度。
    
    Returns:
        (最大深度, 最长调用链路径)
    """
    if len(group) <= 1:
        return 1, []
    
    # 提取每个函数的名称和它调用的函数
    func_names = {}  # idx -> func_name
    func_codes = {}  # func_name -> code
    call_graph = {}  # func_name -> set of callees
    
    for i, record in enumerate(group):
        func_code = record.get('func', '')
        func_name = extract_function_name(func_code)
        if func_name:
            func_names[i] = func_name
            func_codes[func_name] = func_code
            callees = extract_function_calls(func_code, func_name)
            call_graph[func_name] = callees
    
    # 获取组内所有函数名
    group_funcs = set(func_names.values())
    
    # 只保留组内存在的调用关系
    filtered_graph = {}
    for caller, callees in call_graph.items():
        filtered_callees = callees & group_funcs
        filtered_graph[caller] = filtered_callees
    
    # 使用 DFS 计算最长调用链深度
    def dfs(func: str, visited: Set[str], path: List[str]) -> Tuple[int, List[str]]:
        """
        从 func 开始，找到最长的调用链。
        """
        if func in visited:
            return len(path), path.copy()
        
        visited.add(func)
        path.append(func)
        
        max_depth = len(path)
        max_path = path.copy()
        
        for callee in filtered_graph.get(func, []):
            if callee not in visited:
                depth, p = dfs(callee, visited, path)
                if depth > max_depth:
                    max_depth = depth
                    max_path = p
        
        path.pop()
        visited.remove(func)
        
        return max_depth, max_path
    
    # 从每个函数开始尝试，找到最长调用链
    overall_max_depth = 1
    overall_max_path = []
    
    for func_name in group_funcs:
        depth, path = dfs(func_name, set(), [])
        if depth > overall_max_depth:
            overall_max_depth = depth
            overall_max_path = path
    
    return overall_max_depth, overall_max_path


def load_grouped_json(file_path: str) -> Dict:
    """
    加载分组后的 JSON 文件。
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def filter_groups_by_depth(
    groups: List[List[Dict]], 
    min_depth: int = 1, 
    max_depth: int = float('inf')
) -> Tuple[List[Dict], Dict[int, int]]:
    """
    按调用链深度筛选组。
    
    Args:
        groups: 所有组
        min_depth: 最小深度（包含）
        max_depth: 最大深度（包含）
    
    Returns:
        (符合条件的组列表（包含深度信息）, 深度分布统计)
    """
    filtered_groups = []
    depth_distribution = defaultdict(int)
    
    print("分析调用链深度...")
    total = len(groups)
    
    for i, group in enumerate(groups):
        if (i + 1) % 500 == 0:
            print(f"  处理进度: {i + 1}/{total}")
        
        depth, path = compute_call_depth(group)
        depth_distribution[depth] += 1
        
        if min_depth <= depth <= max_depth:
            # 添加深度信息到组中
            group_with_info = {
                "call_depth": depth,
                "longest_call_chain": path,
                "group_size": len(group),
                "functions": group
            }
            filtered_groups.append(group_with_info)
    
    return filtered_groups, dict(depth_distribution)


def main():
    parser = argparse.ArgumentParser(
        description='按调用链深度筛选函数组',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 筛选深度为 3 的组
  python filter_by_call_depth.py -i output/grouped.json -d 3

  # 筛选深度在 2-5 之间的组
  python filter_by_call_depth.py -i output/grouped.json --min-depth 2 --max-depth 5

  # 筛选深度 >= 4 的组
  python filter_by_call_depth.py -i output/grouped.json --min-depth 4
        """
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='输入的分组 JSON 文件路径'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='输出的 JSON 文件路径（默认自动生成）'
    )
    parser.add_argument(
        '--depth', '-d',
        type=int,
        default=None,
        help='精确匹配的调用链深度（与 --min-depth/--max-depth 互斥）'
    )
    parser.add_argument(
        '--min-depth',
        type=int,
        default=1,
        help='最小调用链深度（包含，默认为1）'
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        default=None,
        help='最大调用链深度（包含，默认不限制）'
    )
    
    args = parser.parse_args()
    
    # 处理深度参数
    if args.depth is not None:
        min_depth = args.depth
        max_depth = args.depth
    else:
        min_depth = args.min_depth
        max_depth = args.max_depth if args.max_depth is not None else float('inf')
    
    # 设置默认输出路径
    if args.output is None:
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        output_dir = os.path.dirname(args.input)
        if max_depth == float('inf'):
            depth_str = f"depth_{min_depth}+"
        elif min_depth == max_depth:
            depth_str = f"depth_{min_depth}"
        else:
            depth_str = f"depth_{min_depth}-{max_depth}"
        args.output = os.path.join(output_dir, f'{base_name}_{depth_str}.json')
    
    # 加载数据
    print(f"加载数据: {args.input}")
    data = load_grouped_json(args.input)
    groups = data.get('groups', [])
    print(f"共加载 {len(groups)} 个组")
    
    # 筛选
    if max_depth == float('inf'):
        print(f"\n筛选调用链深度 >= {min_depth} 的组...")
    elif min_depth == max_depth:
        print(f"\n筛选调用链深度 = {min_depth} 的组...")
    else:
        print(f"\n筛选调用链深度在 {min_depth}-{max_depth} 之间的组...")
    
    filtered_groups, depth_distribution = filter_groups_by_depth(groups, min_depth, max_depth)
    
    # 统计信息
    print(f"\n==================== 统计信息 ====================")
    print(f"原始组数: {len(groups)}")
    print(f"筛选后组数: {len(filtered_groups)}")
    print(f"筛选后总函数数: {sum(g['group_size'] for g in filtered_groups)}")
    
    print(f"\n调用链深度分布（全部数据）:")
    for depth in sorted(depth_distribution.keys()):
        count = depth_distribution[depth]
        pct = count / len(groups) * 100
        marker = " <--" if min_depth <= depth <= (max_depth if max_depth != float('inf') else depth) else ""
        print(f"  深度 {depth}: {count} 组 ({pct:.1f}%){marker}")
    
    if filtered_groups:
        depths = [g['call_depth'] for g in filtered_groups]
        print(f"\n筛选结果统计:")
        print(f"  最小深度: {min(depths)}")
        print(f"  最大深度: {max(depths)}")
        print(f"  平均深度: {sum(depths)/len(depths):.2f}")
    print(f"====================================================")
    
    # 输出结果
    output_data = {
        "metadata": {
            "source_file": os.path.basename(args.input),
            "filter_min_depth": min_depth,
            "filter_max_depth": max_depth if max_depth != float('inf') else "unlimited",
            "original_groups": len(groups),
            "filtered_groups": len(filtered_groups),
            "total_functions": sum(g['group_size'] for g in filtered_groups),
            "depth_distribution": depth_distribution,
        },
        "groups": filtered_groups
    }
    
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {args.output}")


if __name__ == '__main__':
    main()

