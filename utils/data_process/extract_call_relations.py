#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析代码函数的 caller 和 callee 关系，将有调用关系的函数合并为组。
"""

import json
import re
import os
import argparse
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional


# 常见的 C/C++ 库函数和系统调用，这些不应该作为连接不同函数组的依据
COMMON_LIB_FUNCTIONS = {
    # 内存管理
    'malloc', 'calloc', 'realloc', 'free', 'memcpy', 'memmove', 'memset',
    'memcmp', 'memchr', 'alloca', 'aligned_alloc',
    # 字符串处理
    'strlen', 'strcpy', 'strncpy', 'strcat', 'strncat', 'strcmp', 'strncmp',
    'strchr', 'strrchr', 'strstr', 'strtok', 'strdup', 'strndup', 'strspn',
    'strcspn', 'strpbrk', 'strerror', 'sprintf', 'snprintf', 'vsprintf',
    'vsnprintf', 'sscanf',
    # 输入输出
    'printf', 'fprintf', 'vprintf', 'vfprintf', 'puts', 'fputs', 'putc',
    'fputc', 'putchar', 'gets', 'fgets', 'getc', 'fgetc', 'getchar',
    'scanf', 'fscanf', 'fopen', 'fclose', 'fread', 'fwrite', 'fseek',
    'ftell', 'rewind', 'fflush', 'feof', 'ferror', 'clearerr', 'perror',
    # 类型转换
    'atoi', 'atol', 'atoll', 'atof', 'strtol', 'strtoll', 'strtoul',
    'strtoull', 'strtof', 'strtod', 'strtold',
    # 数学函数
    'abs', 'labs', 'llabs', 'fabs', 'floor', 'ceil', 'round', 'sqrt',
    'pow', 'exp', 'log', 'log10', 'sin', 'cos', 'tan', 'asin', 'acos',
    'atan', 'atan2', 'min', 'max',
    # 时间函数
    'time', 'clock', 'difftime', 'mktime', 'strftime', 'localtime',
    'gmtime', 'asctime', 'ctime', 'gettimeofday', 'sleep', 'usleep',
    'nanosleep',
    # 进程和信号
    'exit', 'abort', '_exit', 'atexit', 'system', 'getenv', 'setenv',
    'fork', 'exec', 'execl', 'execv', 'execle', 'execve', 'execlp',
    'execvp', 'wait', 'waitpid', 'kill', 'signal', 'raise',
    # 断言和错误处理
    'assert', 'errno', 'setjmp', 'longjmp',
    # POSIX 和系统调用
    'open', 'close', 'read', 'write', 'lseek', 'stat', 'fstat', 'lstat',
    'access', 'chmod', 'chown', 'link', 'unlink', 'rename', 'mkdir',
    'rmdir', 'opendir', 'closedir', 'readdir', 'getcwd', 'chdir',
    'pipe', 'dup', 'dup2', 'fcntl', 'ioctl', 'select', 'poll', 'mmap',
    'munmap', 'mprotect', 'socket', 'bind', 'listen', 'accept', 'connect',
    'send', 'recv', 'sendto', 'recvfrom', 'shutdown', 'setsockopt',
    'getsockopt', 'pthread_create', 'pthread_join', 'pthread_exit',
    'pthread_mutex_lock', 'pthread_mutex_unlock', 'pthread_cond_wait',
    'pthread_cond_signal',
    # C++ 常用
    'std', 'make_shared', 'make_unique', 'move', 'forward', 'swap',
    'begin', 'end', 'size', 'empty', 'push_back', 'pop_back', 'front',
    'back', 'insert', 'erase', 'clear', 'find', 'count', 'sort',
    'unique', 'reverse', 'copy', 'fill', 'transform', 'accumulate',
    # 类型检查
    'static_assert', 'ASSERT', 'DCHECK', 'CHECK', 'EXPECT', 'VERIFY',
    # 日志
    'LOG', 'DLOG', 'VLOG', 'ERR', 'WARN', 'INFO', 'DEBUG', 'TRACE',
    # 其他常见宏/函数
    'DISALLOW_COPY_AND_ASSIGN', 'NOTREACHED', 'UNIMPLEMENTED',
    'offsetof', 'container_of', 'likely', 'unlikely', 'BUG', 'BUG_ON',
    'WARN_ON', 'IS_ERR', 'PTR_ERR', 'ERR_PTR', 'ERR_CAST',
    # 测试相关
    'TEST', 'TEST_F', 'TEST_P', 'EXPECT_TRUE', 'EXPECT_FALSE',
    'EXPECT_EQ', 'EXPECT_NE', 'EXPECT_LT', 'EXPECT_LE', 'EXPECT_GT',
    'EXPECT_GE', 'ASSERT_TRUE', 'ASSERT_FALSE', 'ASSERT_EQ', 'ASSERT_NE',
    'MOCK_METHOD', 'INSTANTIATE_TEST_SUITE_P',
}


def extract_function_name(func_code: str) -> Optional[str]:
    """
    从函数代码中提取函数名。
    支持 C/C++ 风格的函数定义。
    """
    # 移除注释
    code = re.sub(r'//.*?\n', '\n', func_code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    # 匹配函数定义的模式
    # 格式: [返回类型] [类名::]函数名(参数列表)
    patterns = [
        # C++ 成员函数: ReturnType ClassName::FunctionName(...)
        r'(?:[\w\s\*&<>,]+?)\s+(\w+::~?\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*(?:final)?\s*(?:\{|:)',
        # 构造函数/析构函数: ClassName::ClassName(...) 或 ClassName::~ClassName(...)
        r'^[\s]*(\w+::~?\w+)\s*\([^)]*\)\s*(?:\{|:)',
        # 普通 C 函数: ReturnType FunctionName(...)
        r'(?:[\w\s\*&<>,]+?)\s+(\w+)\s*\([^)]*\)\s*\{',
        # 简单模式
        r'^\s*(?:static\s+)?(?:inline\s+)?(?:virtual\s+)?(?:[\w\*&<>,\s]+)\s+(\w+)\s*\(',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, code, re.MULTILINE)
        if match:
            func_name = match.group(1)
            # 如果是 ClassName::FunctionName 格式，只取函数名
            if '::' in func_name:
                func_name = func_name.split('::')[-1]
            return func_name
    
    return None


def extract_function_calls(
    func_code: str, 
    self_name: Optional[str] = None,
    exclude_common_libs: bool = True
) -> Set[str]:
    """
    从函数代码中提取所有被调用的函数名（callees）。
    
    Args:
        func_code: 函数代码
        self_name: 当前函数名（会被排除）
        exclude_common_libs: 是否排除常见库函数
    """
    # 移除注释和字符串
    code = re.sub(r'//.*?\n', '\n', func_code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)  # 移除字符串
    code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)  # 移除字符
    
    # 提取函数调用: 函数名(
    # 排除关键字和常见的非函数调用
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
    
    # 匹配函数调用
    pattern = r'\b([a-zA-Z_]\w*)\s*\('
    matches = re.findall(pattern, code)
    
    # 过滤关键字、自身和常见库函数
    callees = set()
    for name in matches:
        if name in keywords:
            continue
        if self_name is not None and name == self_name:
            continue
        if exclude_common_libs and name in COMMON_LIB_FUNCTIONS:
            continue
        callees.add(name)
    
    return callees


def load_jsonl(file_path: str) -> List[Dict]:
    """
    加载 JSONL 文件。
    """
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def build_call_graph(
    records: List[Dict],
    exclude_common_libs: bool = True
) -> Tuple[Dict[str, Set[str]], Dict[int, str], Dict[str, List[int]]]:
    """
    构建函数调用图。
    
    Args:
        records: 数据记录列表
        exclude_common_libs: 是否排除常见库函数
    
    返回:
        - call_graph: {函数名: {被调用的函数名集合}}
        - idx_to_func: {记录索引: 函数名}
        - func_to_idxs: {函数名: [记录索引列表]}（一个函数名可能对应多条记录）
    """
    call_graph = {}
    idx_to_func = {}
    func_to_idxs = defaultdict(list)
    
    for i, record in enumerate(records):
        func_code = record.get('func', '')
        func_name = extract_function_name(func_code)
        
        if func_name:
            callees = extract_function_calls(func_code, func_name, exclude_common_libs)
            call_graph[func_name] = callees
            idx_to_func[i] = func_name
            func_to_idxs[func_name].append(i)
    
    return call_graph, idx_to_func, func_to_idxs


def find_high_frequency_functions(
    call_graph: Dict[str, Set[str]],
    all_funcs: Set[str],
    threshold_percentile: float = 99.0
) -> Set[str]:
    """
    找出被高频调用的函数（可能是通用工具函数）。
    
    Args:
        call_graph: 函数调用图
        all_funcs: 数据集中的所有函数名
        threshold_percentile: 阈值百分位数（默认 99%）
    
    Returns:
        高频被调用的函数集合
    """
    # 统计每个函数被调用的次数
    callee_count = defaultdict(int)
    for callees in call_graph.values():
        for callee in callees:
            if callee in all_funcs:
                callee_count[callee] += 1
    
    if not callee_count:
        return set()
    
    # 计算阈值
    counts = sorted(callee_count.values())
    threshold_idx = int(len(counts) * threshold_percentile / 100)
    threshold = counts[min(threshold_idx, len(counts) - 1)]
    
    # 只有当阈值大于某个最小值时才过滤（避免过滤掉正常的调用关系）
    if threshold < 10:
        return set()
    
    high_freq_funcs = {fn for fn, count in callee_count.items() if count >= threshold}
    return high_freq_funcs


def find_related_groups(
    records: List[Dict],
    call_graph: Dict[str, Set[str]],
    func_to_idxs: Dict[str, List[int]],
    auto_filter_high_freq: bool = True,
    high_freq_threshold: float = 99.0
) -> List[List[Dict]]:
    """
    找出有调用关系的函数组。
    使用 Union-Find 算法将有调用关系的函数合并。
    
    Args:
        records: 数据记录列表
        call_graph: 函数调用图
        func_to_idxs: 函数名到记录索引的映射
        auto_filter_high_freq: 是否自动过滤高频调用的函数
        high_freq_threshold: 高频函数的阈值百分位数
    """
    # 获取所有函数名
    all_funcs = set(call_graph.keys())
    
    # 找出高频被调用的函数
    high_freq_funcs = set()
    if auto_filter_high_freq:
        high_freq_funcs = find_high_frequency_functions(
            call_graph, all_funcs, high_freq_threshold
        )
        if high_freq_funcs:
            print(f"  自动过滤 {len(high_freq_funcs)} 个高频被调用的函数")
    
    # 只保留在数据集中实际存在的调用关系
    # 构建双向关系图（caller -> callee, callee -> caller）
    related_graph = defaultdict(set)
    
    for caller, callees in call_graph.items():
        for callee in callees:
            # 只有当 callee 也在我们的数据集中时才建立关系
            # 排除高频被调用的函数
            if callee in all_funcs and callee not in high_freq_funcs:
                related_graph[caller].add(callee)
                related_graph[callee].add(caller)
    
    # 使用 BFS/DFS 找连通分量
    visited = set()
    groups = []
    
    for func_name in all_funcs:
        if func_name not in visited:
            # BFS 找到所有连通的函数
            group_funcs = set()
            queue = [func_name]
            
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                group_funcs.add(current)
                
                # 添加相关的函数
                for related in related_graph.get(current, []):
                    if related not in visited:
                        queue.append(related)
            
            # 将函数名转换为对应的记录
            group_records = []
            for fn in group_funcs:
                for idx in func_to_idxs.get(fn, []):
                    group_records.append(records[idx])
            
            if group_records:
                groups.append(group_records)
    
    return groups


def process_file(
    input_path: str, 
    output_path: str, 
    min_group_size: int = 1,
    max_group_size: int = 0,
    exclude_common_libs: bool = True
):
    """
    处理单个 JSONL 文件。
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        min_group_size: 最小组大小（默认为1，可设置为2只保留有调用关系的组）
        max_group_size: 最大组大小（0表示不限制，超过此大小的组会被拆分为单独的记录）
        exclude_common_libs: 是否排除常见库函数
    """
    print(f"加载数据: {input_path}")
    records = load_jsonl(input_path)
    print(f"共加载 {len(records)} 条记录")
    
    print("构建函数调用图...")
    call_graph, idx_to_func, func_to_idxs = build_call_graph(records, exclude_common_libs)
    print(f"识别出 {len(call_graph)} 个函数")
    
    print("分析调用关系，合并相关函数...")
    groups = find_related_groups(
        records, call_graph, func_to_idxs,
        auto_filter_high_freq=True,
        high_freq_threshold=99.0
    )
    
    # 处理超大组：如果设置了 max_group_size，将超大组拆分为单独的记录
    if max_group_size > 0:
        new_groups = []
        oversized_count = 0
        for g in groups:
            if len(g) > max_group_size:
                oversized_count += 1
                # 将超大组中的每个记录拆分为单独的组
                for record in g:
                    new_groups.append([record])
            else:
                new_groups.append(g)
        if oversized_count > 0:
            print(f"  (已将 {oversized_count} 个超大组拆分为单独记录)")
        groups = new_groups
    
    # 按组大小过滤
    if min_group_size > 1:
        groups = [g for g in groups if len(g) >= min_group_size]
    
    # 统计信息
    total_funcs = sum(len(g) for g in groups)
    groups_with_relations = [g for g in groups if len(g) > 1]
    single_func_groups = len([g for g in groups if len(g) == 1])
    
    # 按组大小分布统计
    size_distribution = defaultdict(int)
    for g in groups:
        size = len(g)
        if size == 1:
            size_distribution["1 (单独函数)"] += 1
        elif size <= 5:
            size_distribution["2-5"] += 1
        elif size <= 10:
            size_distribution["6-10"] += 1
        elif size <= 50:
            size_distribution["11-50"] += 1
        elif size <= 100:
            size_distribution["51-100"] += 1
        elif size <= 500:
            size_distribution["101-500"] += 1
        elif size <= 1000:
            size_distribution["501-1000"] += 1
        else:
            size_distribution["1000+"] += 1
    
    print(f"\n==================== 统计信息 ====================")
    print(f"  总记录数（原始）: {len(records)}")
    print(f"  总函数数（分组后）: {total_funcs}")
    print(f"  总组数: {len(groups)}")
    print(f"    - 单独函数组（无调用关系）: {single_func_groups}")
    print(f"    - 有调用关系的组（大小>1）: {len(groups_with_relations)}")
    
    if groups_with_relations:
        actual_max_size = max(len(g) for g in groups_with_relations)
        avg_group_size = sum(len(g) for g in groups_with_relations) / len(groups_with_relations)
        print(f"  最大组大小: {actual_max_size}")
        print(f"  有关系组的平均大小: {avg_group_size:.2f}")
    
    print(f"\n  组大小分布:")
    # 按特定顺序输出
    order = ["1 (单独函数)", "2-5", "6-10", "11-50", "51-100", "101-500", "501-1000", "1000+"]
    for key in order:
        if key in size_distribution:
            count = size_distribution[key]
            percentage = count / len(groups) * 100
            print(f"    - 大小 {key}: {count} 组 ({percentage:.1f}%)")
    print(f"====================================================")
    
    # 输出结果
    output_data = {
        "metadata": {
            "source_file": os.path.basename(input_path),
            "total_records": len(records),
            "total_functions_grouped": total_funcs,
            "total_groups": len(groups),
            "single_function_groups": single_func_groups,
            "groups_with_relations": len(groups_with_relations),
            "max_group_size": max(len(g) for g in groups) if groups else 0,
            "avg_related_group_size": round(sum(len(g) for g in groups_with_relations) / len(groups_with_relations), 2) if groups_with_relations else 0,
            "size_distribution": dict(size_distribution),
        },
        "groups": groups
    }
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='分析代码函数的调用关系')
    parser.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='输入的 JSONL 文件路径'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='输出的 JSON 文件路径（默认为 output/<输入文件名>_grouped.json）'
    )
    parser.add_argument(
        '--min-group-size', '-m',
        type=int,
        default=1,
        help='最小组大小，设为2可只保留有调用关系的组（默认为1）'
    )
    parser.add_argument(
        '--max-group-size', '-M',
        type=int,
        default=0,
        help='最大组大小，超过此大小的组会被拆分（0表示不限制，默认为0）'
    )
    parser.add_argument(
        '--include-common-libs',
        action='store_true',
        default=False,
        help='是否包含常见库函数作为调用关系（默认排除）'
    )
    
    args = parser.parse_args()
    
    # 设置默认输出路径
    if args.output is None:
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        # 获取脚本所在目录的上两级（项目根目录）
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))
        args.output = os.path.join(project_root, 'output', f'{base_name}_grouped.json')
    
    process_file(
        args.input, 
        args.output, 
        args.min_group_size,
        args.max_group_size,
        exclude_common_libs=not args.include_common_libs
    )


if __name__ == '__main__':
    main()

