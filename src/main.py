#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code Fusion 主程序

功能：
1. 读取调用链深度为 4 的数据
2. 分析代码的控制流图和必经点
3. 使用 LLM 将目标代码拆分并融合到调用链函数中
"""

import os
import sys
import json
import argparse
from typing import List, Dict, Optional
from dataclasses import dataclass

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cfg_analyzer import analyze_code_cfg, visualize_cfg
from dominator_analyzer import analyze_dominators, get_fusion_points
from llm_splitter import LLMCodeSplitter, split_code_for_call_chain
from code_fusion import CodeFusionEngine, CallChain, FunctionInfo, analyze_call_chain_group


@dataclass
class ProcessingResult:
    """处理结果"""
    group_index: int
    call_chain: List[str]
    call_depth: int
    functions_count: int
    total_fusion_points: int
    fused_code: Dict[str, str]
    success: bool
    error_message: str = ""
    global_declarations: str = ""  # 全局变量声明
    passing_method: str = "global"  # 变量传递方法
    parameter_struct: str = ""  # 参数结构体定义


class CodeFusionProcessor:
    """代码融合处理器"""
    
    def __init__(self, api_key: str = None):
        """
        初始化处理器
        
        Args:
            api_key: API 密钥
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.splitter = None
        self.engine = None
        
        if self.api_key:
            try:
                self.splitter = LLMCodeSplitter(api_key=self.api_key)
                self.engine = CodeFusionEngine(splitter=self.splitter)
            except Exception as e:
                print(f"Warning: Failed to initialize LLM splitter: {e}")
    
    def load_data(self, input_path: str) -> Dict:
        """
        加载数据文件
        
        Args:
            input_path: 输入文件路径
            
        Returns:
            数据字典
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def analyze_group(self, group: Dict) -> Dict:
        """
        分析单个调用链组
        
        Args:
            group: 调用链组数据
            
        Returns:
            分析结果
        """
        return analyze_call_chain_group(group)
    
    def process_group(
        self,
        group: Dict,
        target_code: str,
        group_index: int = 0,
        passing_method: str = "global"
    ) -> ProcessingResult:
        """
        处理单个调用链组，执行代码融合
        
        Args:
            group: 调用链组数据
            target_code: 要融合的目标代码
            group_index: 组索引
            
        Returns:
            ProcessingResult 对象
        """
        functions = group.get('functions', [])
        call_depth = group.get('call_depth', 0)
        call_chain = group.get('longest_call_chain', [])
        
        if not self.engine:
            return ProcessingResult(
                group_index=group_index,
                call_chain=call_chain,
                call_depth=call_depth,
                functions_count=len(functions),
                total_fusion_points=0,
                fused_code={},
                success=False,
                error_message="LLM engine not initialized",
                global_declarations="",
                passing_method=passing_method,
                parameter_struct=""
            )
        
        try:
            # 构建调用链
            chain = self.engine.build_call_chain(functions, call_chain)
            
            # 创建融合计划（传递 passing_method）
            plan = self.engine.create_fusion_plan(target_code, chain, passing_method)
            
            # 执行融合
            fused_code = self.engine.execute_fusion(plan)
            
            # 获取变量传递相关信息
            slice_result = plan.slice_result
            global_decl = slice_result.global_declarations if slice_result else ""
            param_struct = slice_result.parameter_struct if slice_result else ""
            
            return ProcessingResult(
                group_index=group_index,
                call_chain=call_chain,
                call_depth=call_depth,
                functions_count=len(functions),
                total_fusion_points=chain.get_total_fusion_points(),
                fused_code=fused_code,
                success=True,
                global_declarations=global_decl,
                passing_method=passing_method,
                parameter_struct=param_struct
            )
            
        except Exception as e:
            return ProcessingResult(
                group_index=group_index,
                call_chain=call_chain,
                call_depth=call_depth,
                functions_count=len(functions),
                total_fusion_points=0,
                fused_code={},
                success=False,
                error_message=str(e),
                global_declarations="",
                passing_method=passing_method,
                parameter_struct=""
            )
    
    def process_file(
        self,
        input_path: str,
        output_path: str,
        target_code: str,
        max_groups: int = 10,
        passing_method: str = "global"
    ) -> List[ProcessingResult]:
        """
        处理整个数据文件
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            target_code: 要融合的目标代码
            max_groups: 最大处理组数
            passing_method: 变量传递方法 "global" 或 "parameter"
            
        Returns:
            处理结果列表
        """
        print(f"Loading data from: {input_path}")
        data = self.load_data(input_path)
        groups = data.get('groups', [])
        
        print(f"Total groups: {len(groups)}")
        
        results = []
        processed = 0
        
        for i, group in enumerate(groups):
            if processed >= max_groups:
                break
            
            print(f"\nProcessing group {i + 1}/{len(groups)}...")
            
            # 首先分析组
            analysis = self.analyze_group(group)
            print(f"  Call chain: {' -> '.join(analysis['call_chain'])}")
            print(f"  Functions: {analysis['functions_count']}")
            print(f"  Fusion points: {analysis['total_fusion_points']}")
            
            # 处理组
            result = self.process_group(group, target_code, i, passing_method)
            results.append(result)
            
            if result.success:
                print(f"  Status: SUCCESS")
                processed += 1
            else:
                print(f"  Status: FAILED - {result.error_message}")
        
        # 保存结果
        self._save_results(results, output_path, target_code)
        
        return results
    
    def _save_results(
        self,
        results: List[ProcessingResult],
        output_path: str,
        target_code: str
    ):
        """
        保存处理结果
        """
        output_data = {
            "metadata": {
                "target_code": target_code,
                "total_processed": len(results),
                "successful": sum(1 for r in results if r.success),
                "failed": sum(1 for r in results if not r.success)
            },
            "results": []
        }
        
        for result in results:
            output_data["results"].append({
                "group_index": result.group_index,
                "call_chain": result.call_chain,
                "call_depth": result.call_depth,
                "functions_count": result.functions_count,
                "total_fusion_points": result.total_fusion_points,
                "success": result.success,
                "error_message": result.error_message,
                "fused_code": result.fused_code
            })
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\nResults saved to: {output_path}")
        
        # 保存合并后的代码文件
        self._save_fused_code_files(results, output_path, target_code)
        
        # 如果有参数传递方法的结果，也输出对应的文件
        param_results = [r for r in results if r.passing_method == "parameter" and r.success]
        if param_results:
            print(f"  Parameter passing method results: {len(param_results)}")
    
    def _save_fused_code_files(
        self,
        results: List[ProcessingResult],
        output_path: str,
        target_code: str
    ):
        """
        将融合后的代码保存为单独的代码文件
        """
        # 创建代码输出目录
        output_dir = os.path.dirname(output_path)
        code_dir = os.path.join(output_dir, "fused_code")
        os.makedirs(code_dir, exist_ok=True)
        
        for result in results:
            if not result.success or not result.fused_code:
                continue
            
            # 生成文件名
            chain_name = "_".join(result.call_chain[:2]) if len(result.call_chain) >= 2 else "unknown"
            filename = f"fused_group_{result.group_index}_{chain_name}.c"
            filepath = os.path.join(code_dir, filename)
            
            # 生成合并后的代码文件内容
            code_content = self._generate_fused_code_file(result, target_code, result.global_declarations)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(code_content)
            
            print(f"  Fused code saved to: {filepath}")
        
        # 生成汇总文件
        summary_path = os.path.join(code_dir, "all_fused_code.c")
        all_code = self._generate_all_fused_code(results, target_code)
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(all_code)
        print(f"  All fused code saved to: {summary_path}")
    
    def _generate_fused_code_file(
        self,
        result: ProcessingResult,
        target_code: str,
        global_declarations: str = ""
    ) -> str:
        """
        生成单个融合代码文件的内容
        """
        lines = []
        
        # 文件头
        lines.append("/*")
        lines.append(" * Fused Code File")
        lines.append(f" * Group Index: {result.group_index}")
        lines.append(f" * Call Chain: {' -> '.join(result.call_chain)}")
        lines.append(f" * Call Depth: {result.call_depth}")
        lines.append(" *")
        lines.append(" * Original Target Code:")
        for line in target_code.strip().split('\n'):
            lines.append(f" *   {line}")
        lines.append(" *")
        lines.append(" * Generated by Code Fusion Tool")
        lines.append(" */")
        lines.append("")
        
        # 包含常用头文件
        lines.append("#include <stdio.h>")
        lines.append("#include <stdlib.h>")
        lines.append("#include <string.h>")
        lines.append("")
        
        # 根据传递方法选择不同的变量声明方式
        passing_method = getattr(result, 'passing_method', 'global')
        parameter_struct = getattr(result, 'parameter_struct', '')
        
        if passing_method == "parameter":
            # 参数传递方法：使用结构体
            lines.append("/* === Shared State (Parameter Passing Method) === */")
            if parameter_struct:
                lines.append(parameter_struct)
            else:
                lines.append("typedef struct {")
                lines.append("    int secret;")
                lines.append("    int key;")
                lines.append("} FusionState;")
            lines.append("")
            lines.append("/* Usage: Pass FusionState* fusion_state to each function */")
            lines.append("/* Initialize: FusionState state; memset(&state, 0, sizeof(state)); */")
        else:
            # 全局变量方法
            lines.append("/* === Shared State Variables (Global) === */")
            if global_declarations:
                lines.append(global_declarations)
            else:
                lines.append("static int g_secret;")
                lines.append("static int g_key;")
        lines.append("")
        
        # 函数声明
        lines.append("/* === Function Declarations === */")
        for func_name in result.call_chain:
            if func_name in result.fused_code:
                # 提取函数签名
                code = result.fused_code[func_name]
                sig = self._extract_function_signature(code)
                if sig:
                    lines.append(f"{sig};")
        lines.append("")
        
        # 函数定义（按调用链顺序，从最内层到最外层）
        lines.append("/* === Function Definitions === */")
        lines.append("/* Functions are ordered from innermost to outermost in the call chain */")
        lines.append("")
        
        # 反转顺序，先定义被调用的函数
        for func_name in reversed(result.call_chain):
            if func_name in result.fused_code:
                lines.append(f"/* --- {func_name} --- */")
                lines.append(result.fused_code[func_name])
                lines.append("")
        
        return '\n'.join(lines)
    
    def _generate_all_fused_code(
        self,
        results: List[ProcessingResult],
        target_code: str
    ) -> str:
        """
        生成所有融合代码的汇总文件
        """
        lines = []
        
        # 文件头
        lines.append("/*")
        lines.append(" * All Fused Code - Summary File")
        lines.append(f" * Total Groups: {len([r for r in results if r.success])}")
        lines.append(" *")
        lines.append(" * Original Target Code:")
        for line in target_code.strip().split('\n'):
            lines.append(f" *   {line}")
        lines.append(" *")
        lines.append(" * Generated by Code Fusion Tool")
        lines.append(" */")
        lines.append("")
        
        lines.append("#include <stdio.h>")
        lines.append("#include <stdlib.h>")
        lines.append("#include <string.h>")
        lines.append("")
        
        # 每个成功的组
        for result in results:
            if not result.success or not result.fused_code:
                continue
            
            lines.append("")
            lines.append("/" + "=" * 78 + "/")
            lines.append(f"/* GROUP {result.group_index}: {' -> '.join(result.call_chain)} */")
            lines.append("/" + "=" * 78 + "/")
            lines.append("")
            
            # 根据传递方法选择不同的变量声明
            if result.passing_method == "parameter":
                lines.append("/* === Shared State (Parameter Passing Method) === */")
                if result.parameter_struct:
                    lines.append(result.parameter_struct)
                else:
                    lines.append("typedef struct { int secret; int key; } FusionState;")
                lines.append("/* Pass FusionState* fusion_state to each function */")
            else:
                lines.append("/* === Shared State Variables (Global) === */")
                if result.global_declarations:
                    lines.append(result.global_declarations)
                else:
                    lines.append("static int g_secret;")
                    lines.append("static int g_key;")
            lines.append("")
            
            # 函数定义
            for func_name in reversed(result.call_chain):
                if func_name in result.fused_code:
                    lines.append(f"/* {func_name} */")
                    lines.append(result.fused_code[func_name])
                    lines.append("")
        
        return '\n'.join(lines)
    
    def _extract_function_signature(self, func_code: str) -> Optional[str]:
        """
        从函数代码中提取函数签名
        """
        # 找到第一个 { 之前的内容
        brace_pos = func_code.find('{')
        if brace_pos == -1:
            return None
        
        sig = func_code[:brace_pos].strip()
        # 移除多余的空白和换行
        sig = ' '.join(sig.split())
        return sig


def demo_analysis(input_path: str):
    """
    演示分析功能（不调用 LLM）
    """
    print("=" * 60)
    print("Code Fusion Analysis Demo")
    print("=" * 60)
    
    # 加载数据
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    groups = data.get('groups', [])
    print(f"\nTotal groups: {len(groups)}")
    
    # 分析前几个组
    for i, group in enumerate(groups[:5]):
        print(f"\n--- Group {i + 1} ---")
        
        call_depth = group.get('call_depth', 0)
        call_chain = group.get('longest_call_chain', [])
        functions = group.get('functions', [])
        
        print(f"Call depth: {call_depth}")
        print(f"Call chain: {' -> '.join(call_chain)}")
        print(f"Functions count: {len(functions)}")
        
        # 分析每个函数
        for func_data in functions[:3]:
            code = func_data.get('func', '')[:200]
            cfg = analyze_code_cfg(code)
            fusion_points = get_fusion_points(cfg)
            
            print(f"\n  Function: {cfg.function_name}")
            print(f"  Blocks: {len(cfg.blocks)}")
            print(f"  Fusion points: {len(fusion_points)}")
            print(f"  Code preview: {code[:100]}...")


def main():
    parser = argparse.ArgumentParser(
        description='Code Fusion - 代码调用链分析与融合工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析调用链深度为 4 的数据
  python main.py --input output/primevul_valid_grouped_depth_4.json --analyze-only
  
  # 执行代码融合
  python main.py --input output/primevul_valid_grouped_depth_4.json \\
                 --output output/fusion_results.json \\
                 --target-code "int secret = 42; printf(\\"secret: %d\\n\\", secret);"
                 
  # 使用代码文件作为目标
  python main.py --input output/primevul_valid_grouped_depth_4.json \\
                 --output output/fusion_results.json \\
                 --target-file target_code.c
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
        help='输出文件路径'
    )
    
    parser.add_argument(
        '--target-code', '-t',
        type=str,
        default=None,
        help='要融合的目标代码字符串'
    )
    
    parser.add_argument(
        '--target-file', '-f',
        type=str,
        default=None,
        help='要融合的目标代码文件路径'
    )
    
    parser.add_argument(
        '--max-groups', '-m',
        type=int,
        default=5,
        help='最大处理组数（默认 5）'
    )
    
    parser.add_argument(
        '--analyze-only', '-a',
        action='store_true',
        help='只进行分析，不执行融合'
    )
    
    parser.add_argument(
        '--method',
        type=str,
        choices=['global', 'parameter'],
        default='global',
        help='变量传递方法: global（全局变量）或 parameter（参数传递）（默认 global）'
    )
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    # 只分析模式
    if args.analyze_only:
        demo_analysis(args.input)
        return
    
    # 获取目标代码
    target_code = args.target_code
    if args.target_file:
        if os.path.exists(args.target_file):
            with open(args.target_file, 'r', encoding='utf-8') as f:
                target_code = f.read()
        else:
            print(f"Error: Target file not found: {args.target_file}")
            sys.exit(1)
    
    if not target_code:
        # 使用默认的示例代码
        target_code = """
        // Example target code to be fused
        int secret_value = 0x12345678;
        int key = secret_value ^ 0xDEADBEEF;
        printf("Computed key: 0x%x\\n", key);
        """
        print("Using default example target code.")
    
    # 设置默认输出路径
    if args.output is None:
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        output_dir = os.path.dirname(args.input) or '.'
        args.output = os.path.join(output_dir, f'{base_name}_fused.json')
    
    # 创建处理器并执行
    processor = CodeFusionProcessor()
    
    print(f"Using variable passing method: {args.method}")
    
    results = processor.process_file(
        args.input,
        args.output,
        target_code,
        args.max_groups,
        args.method
    )
    
    # 打印摘要
    successful = sum(1 for r in results if r.success)
    print(f"\n{'=' * 60}")
    print(f"Processing Summary")
    print(f"{'=' * 60}")
    print(f"Total processed: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(results) - successful}")


if __name__ == '__main__':
    main()

