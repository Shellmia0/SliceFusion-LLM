#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码融合模块

实现将代码片段融合到调用链函数中的逻辑。
"""

import json
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field

from cfg_analyzer import ControlFlowGraph, analyze_code_cfg, BasicBlock
from dominator_analyzer import DominatorAnalyzer, get_fusion_points
from llm_splitter import LLMCodeSplitter, SliceResult, CodeSlice


@dataclass
class FunctionInfo:
    """函数信息"""
    name: str
    code: str
    cfg: Optional[ControlFlowGraph] = None
    fusion_points: List[int] = field(default_factory=list)
    idx: Optional[int] = None  # 原始数据中的索引
    
    def analyze(self):
        """分析函数的 CFG 和融合点"""
        if self.cfg is None:
            self.cfg = analyze_code_cfg(self.code, self.name)
            self.fusion_points = get_fusion_points(self.cfg)


@dataclass
class CallChain:
    """调用链"""
    functions: List[FunctionInfo]
    depth: int
    call_path: List[str]  # 函数名调用路径
    
    @property
    def function_names(self) -> List[str]:
        return [f.name for f in self.functions]
    
    def get_total_fusion_points(self) -> int:
        """获取总融合点数量"""
        return sum(len(f.fusion_points) for f in self.functions)


@dataclass
class FusionPlan:
    """融合计划"""
    target_code: str
    call_chain: CallChain
    slice_result: SliceResult
    insertion_points: List[Tuple[str, int, str]]  # [(函数名, 块ID, 代码片段)]


class CodeFusionEngine:
    """代码融合引擎"""
    
    def __init__(self, splitter: LLMCodeSplitter = None):
        """
        初始化融合引擎
        
        Args:
            splitter: LLM 代码拆分器
        """
        self.splitter = splitter or LLMCodeSplitter()
    
    def extract_function_name(self, func_code: str) -> str:
        """提取函数名"""
        # 移除注释
        code = re.sub(r'//.*?\n', '\n', func_code)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        
        # 匹配函数定义
        patterns = [
            r'(?:[\w\s\*&<>,]+?)\s+(\w+::~?\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*(?:final)?\s*\{',
            r'^[\s]*(\w+::~?\w+)\s*\([^)]*\)\s*\{',
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
        
        return "unknown"
    
    def build_call_chain(self, functions: List[Dict], call_path: List[str]) -> CallChain:
        """
        构建调用链
        
        Args:
            functions: 函数列表（每个包含 func 字段）
            call_path: 调用路径（函数名列表）
            
        Returns:
            CallChain 对象
        """
        # 创建函数信息映射
        func_map = {}
        for func_data in functions:
            code = func_data.get('func', '')
            name = self.extract_function_name(code)
            func_info = FunctionInfo(
                name=name,
                code=code,
                idx=func_data.get('idx')
            )
            func_map[name] = func_info
        
        # 按调用路径排序
        ordered_functions = []
        for name in call_path:
            if name in func_map:
                func_info = func_map[name]
                func_info.analyze()
                ordered_functions.append(func_info)
        
        return CallChain(
            functions=ordered_functions,
            depth=len(call_path),
            call_path=call_path
        )
    
    def create_fusion_plan(
        self,
        target_code: str,
        call_chain: CallChain,
        passing_method: str = "global"
    ) -> FusionPlan:
        """
        创建融合计划
        
        Args:
            target_code: 要融合的目标代码
            call_chain: 调用链
            passing_method: 变量传递方法 "global" 或 "parameter"
            
        Returns:
            FusionPlan 对象
        """
        # 使用 LLM 拆分代码
        n_parts = len(call_chain.functions)
        slice_result = self.splitter.split_code(
            target_code,
            n_parts,
            call_chain.function_names,
            passing_method
        )
        
        # 确定插入点
        insertion_points = []
        for i, (func, code_slice) in enumerate(zip(call_chain.functions, slice_result.slices)):
            if func.fusion_points:
                # 选择第一个融合点
                block_id = func.fusion_points[0]
            else:
                # 如果没有融合点，使用入口块
                block_id = func.cfg.entry_block_id if func.cfg else 0
            
            insertion_points.append((func.name, block_id, code_slice.code))
        
        return FusionPlan(
            target_code=target_code,
            call_chain=call_chain,
            slice_result=slice_result,
            insertion_points=insertion_points
        )
    
    def execute_fusion(self, plan: FusionPlan) -> Dict[str, str]:
        """
        执行融合
        
        Args:
            plan: 融合计划
            
        Returns:
            融合后的函数代码字典 {函数名: 代码}
        """
        fused_code = {}
        
        for func, (func_name, block_id, insert_code) in zip(
            plan.call_chain.functions, 
            plan.insertion_points
        ):
            if not insert_code.strip() or insert_code.strip() == "// empty slice":
                fused_code[func_name] = func.code
                continue
            
            # 在函数中插入代码
            fused = self._insert_code_into_function(func, block_id, insert_code)
            fused_code[func_name] = fused
        
        return fused_code
    
    def _insert_code_into_function(
        self, 
        func: FunctionInfo, 
        block_id: int, 
        insert_code: str
    ) -> str:
        """
        在函数的指定位置插入代码
        
        Args:
            func: 函数信息
            block_id: 目标基本块ID
            insert_code: 要插入的代码
            
        Returns:
            插入代码后的函数代码
        """
        code = func.code
        
        # 找到函数体开始
        brace_pos = code.find('{')
        if brace_pos == -1:
            return code
        
        # 如果是入口块或第一个融合点，在函数体开头插入
        if block_id == func.cfg.entry_block_id or (func.fusion_points and block_id == func.fusion_points[0]):
            # 格式化插入代码
            insert_lines = insert_code.strip().split('\n')
            formatted_insert = '\n    '.join(insert_lines)
            
            return (
                code[:brace_pos + 1] + 
                f"\n    /* === Fused Code Start === */\n    {formatted_insert}\n    /* === Fused Code End === */\n" +
                code[brace_pos + 1:]
            )
        
        # 否则尝试找到对应的基本块位置
        # 这里简化处理，在函数中间插入
        return self._insert_at_middle(code, insert_code)
    
    def _insert_at_middle(self, func_code: str, insert_code: str) -> str:
        """
        在函数中间位置插入代码
        """
        # 找到函数体
        brace_start = func_code.find('{')
        brace_end = func_code.rfind('}')
        
        if brace_start == -1 or brace_end == -1:
            return func_code
        
        body = func_code[brace_start + 1:brace_end]
        lines = body.split('\n')
        
        # 在中间位置插入
        mid = len(lines) // 2
        
        insert_lines = insert_code.strip().split('\n')
        formatted_insert = '\n    '.join(insert_lines)
        
        lines.insert(mid, f"    /* === Fused Code Start === */")
        lines.insert(mid + 1, f"    {formatted_insert}")
        lines.insert(mid + 2, f"    /* === Fused Code End === */")
        
        return func_code[:brace_start + 1] + '\n'.join(lines) + func_code[brace_end:]


def analyze_call_chain_group(group: Dict) -> Dict:
    """
    分析一个调用链组
    
    Args:
        group: 包含 functions, call_depth, longest_call_chain 的字典
        
    Returns:
        分析结果字典
    """
    functions = group.get('functions', [])
    call_depth = group.get('call_depth', 0)
    call_chain = group.get('longest_call_chain', [])
    
    # 分析每个函数
    analyzed_functions = []
    for func_data in functions:
        code = func_data.get('func', '')
        cfg = analyze_code_cfg(code)
        fusion_points = get_fusion_points(cfg)
        
        analyzed_functions.append({
            'idx': func_data.get('idx'),
            'name': cfg.function_name,
            'blocks_count': len(cfg.blocks),
            'fusion_points_count': len(fusion_points),
            'fusion_points': fusion_points,
        })
    
    return {
        'call_depth': call_depth,
        'call_chain': call_chain,
        'functions_count': len(functions),
        'analyzed_functions': analyzed_functions,
        'total_fusion_points': sum(f['fusion_points_count'] for f in analyzed_functions)
    }


if __name__ == "__main__":
    # 测试代码
    test_func1 = """
    void outer_func() {
        printf("Start\\n");
        middle_func();
        printf("End\\n");
    }
    """
    
    test_func2 = """
    void middle_func() {
        int x = 10;
        inner_func();
        x += 5;
    }
    """
    
    test_func3 = """
    void inner_func() {
        printf("Inner\\n");
    }
    """
    
    functions = [
        {'func': test_func1, 'idx': 1},
        {'func': test_func2, 'idx': 2},
        {'func': test_func3, 'idx': 3},
    ]
    
    engine = CodeFusionEngine()
    call_chain = engine.build_call_chain(
        functions,
        ['outer_func', 'middle_func', 'inner_func']
    )
    
    print(f"Call chain depth: {call_chain.depth}")
    print(f"Functions: {call_chain.function_names}")
    print(f"Total fusion points: {call_chain.get_total_fusion_points()}")

