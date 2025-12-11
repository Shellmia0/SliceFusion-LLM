#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
必经点 (Dominator) 分析器

分析控制流图中的必经点，即从入口到出口的所有路径都必须经过的节点。
"""

from typing import Dict, List, Set, Optional
from dataclasses import dataclass
import networkx as nx

from cfg_analyzer import ControlFlowGraph, BasicBlock


@dataclass 
class DominatorInfo:
    """必经点信息"""
    dominators: Dict[int, Set[int]]  # 每个节点的支配者集合
    immediate_dominators: Dict[int, Optional[int]]  # 直接支配者
    dominator_tree: Dict[int, List[int]]  # 支配树
    critical_points: Set[int]  # 关键必经点（从入口到出口必经）


class DominatorAnalyzer:
    """必经点分析器"""
    
    def __init__(self, cfg: ControlFlowGraph):
        self.cfg = cfg
        self.graph = cfg.to_networkx()
    
    def compute_dominators(self) -> Dict[int, Set[int]]:
        """
        计算每个节点的支配者集合
        
        使用数据流分析算法：
        Dom(entry) = {entry}
        Dom(n) = {n} ∪ (∩ Dom(p) for p in predecessors(n))
        """
        if not self.cfg.blocks:
            return {}
        
        all_nodes = set(self.cfg.blocks.keys())
        entry = self.cfg.entry_block_id
        
        if entry is None:
            return {}
        
        # 初始化
        dominators = {node: all_nodes.copy() for node in all_nodes}
        dominators[entry] = {entry}
        
        # 迭代计算
        changed = True
        while changed:
            changed = False
            for node in all_nodes:
                if node == entry:
                    continue
                
                preds = self.cfg.get_predecessors(node)
                if not preds:
                    new_dom = {node}
                else:
                    # 取所有前驱的支配者的交集
                    new_dom = all_nodes.copy()
                    for pred in preds:
                        new_dom &= dominators[pred]
                    new_dom.add(node)
                
                if new_dom != dominators[node]:
                    dominators[node] = new_dom
                    changed = True
        
        return dominators
    
    def compute_immediate_dominators(self, dominators: Dict[int, Set[int]]) -> Dict[int, Optional[int]]:
        """
        计算直接支配者
        
        节点 n 的直接支配者是最接近 n 的严格支配者
        """
        idoms = {}
        
        for node, doms in dominators.items():
            # 严格支配者（不包括自身）
            strict_doms = doms - {node}
            
            if not strict_doms:
                idoms[node] = None
                continue
            
            # 找到最接近的支配者
            # 即：不支配其他严格支配者的那个
            idom = None
            for candidate in strict_doms:
                is_idom = True
                for other in strict_doms:
                    if other != candidate and candidate in dominators.get(other, set()):
                        # candidate 支配 other，所以 candidate 不是直接支配者
                        is_idom = False
                        break
                if is_idom:
                    idom = candidate
                    break
            
            idoms[node] = idom
        
        return idoms
    
    def build_dominator_tree(self, idoms: Dict[int, Optional[int]]) -> Dict[int, List[int]]:
        """
        构建支配树
        """
        tree = {node: [] for node in self.cfg.blocks}
        
        for node, idom in idoms.items():
            if idom is not None:
                tree[idom].append(node)
        
        return tree
    
    def find_critical_points(self) -> Set[int]:
        """
        找出关键必经点
        
        关键点定义：从入口块到任意出口块的所有路径都必须经过该点
        """
        if not self.cfg.entry_block_id or not self.cfg.exit_block_ids:
            return set()
        
        entry = self.cfg.entry_block_id
        exits = set(self.cfg.exit_block_ids)
        
        # 使用路径分析找到必经点
        critical_points = set()
        all_nodes = set(self.cfg.blocks.keys())
        
        for node in all_nodes:
            # 检查移除此节点后是否还能从入口到达出口
            if node == entry:
                critical_points.add(node)
                continue
            
            if node in exits:
                critical_points.add(node)
                continue
            
            # 检查是否是必经点
            is_critical = self._check_critical_point(node, entry, exits)
            if is_critical:
                critical_points.add(node)
        
        return critical_points
    
    def _check_critical_point(self, node: int, entry: int, exits: Set[int]) -> bool:
        """
        检查节点是否是必经点
        
        如果移除该节点后，无法从入口到达任何出口，则该节点是必经点
        """
        # 创建不包含该节点的图
        remaining_nodes = set(self.cfg.blocks.keys()) - {node}
        
        if entry not in remaining_nodes:
            return True
        
        # BFS 检查可达性
        visited = set()
        queue = [entry]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            # 检查是否到达出口
            if current in exits:
                return False  # 可以绕过该节点到达出口
            
            for succ in self.cfg.get_successors(current):
                if succ not in visited and succ in remaining_nodes:
                    queue.append(succ)
        
        return True  # 无法绕过该节点到达出口
    
    def find_fusion_points(self) -> List[int]:
        """
        找出适合代码融合的点
        
        融合点需要满足：
        1. 是必经点
        2. 前驱数量 <= 1
        3. 后继数量 <= 1
        4. 不是条件分支
        """
        critical_points = self.find_critical_points()
        fusion_points = []
        
        for point in critical_points:
            preds = self.cfg.get_predecessors(point)
            succs = self.cfg.get_successors(point)
            
            # 检查前驱和后继数量
            if len(preds) <= 1 and len(succs) <= 1:
                fusion_points.append(point)
        
        return sorted(fusion_points)
    
    def analyze(self) -> DominatorInfo:
        """
        执行完整的必经点分析
        """
        dominators = self.compute_dominators()
        idoms = self.compute_immediate_dominators(dominators)
        dom_tree = self.build_dominator_tree(idoms)
        critical_points = self.find_critical_points()
        
        return DominatorInfo(
            dominators=dominators,
            immediate_dominators=idoms,
            dominator_tree=dom_tree,
            critical_points=critical_points
        )


def analyze_dominators(cfg: ControlFlowGraph) -> DominatorInfo:
    """
    分析控制流图的必经点
    
    Args:
        cfg: 控制流图
        
    Returns:
        DominatorInfo 对象
    """
    analyzer = DominatorAnalyzer(cfg)
    return analyzer.analyze()


def get_fusion_points(cfg: ControlFlowGraph) -> List[int]:
    """
    获取适合代码融合的点
    
    Args:
        cfg: 控制流图
        
    Returns:
        融合点ID列表
    """
    analyzer = DominatorAnalyzer(cfg)
    return analyzer.find_fusion_points()


if __name__ == "__main__":
    from cfg_analyzer import analyze_code_cfg
    
    # 测试代码
    test_code = """
    int test_function(int x) {
        int result = 0;
        if (x > 0) {
            result = x * 2;
        } else {
            result = x * -1;
        }
        result += 10;
        return result;
    }
    """
    
    cfg = analyze_code_cfg(test_code, "test_function")
    dom_info = analyze_dominators(cfg)
    
    print(f"Function: {cfg.function_name}")
    print(f"Blocks: {len(cfg.blocks)}")
    print(f"Critical Points: {dom_info.critical_points}")
    print(f"Fusion Points: {get_fusion_points(cfg)}")
    
    print("\nDominators:")
    for node, doms in dom_info.dominators.items():
        block_name = cfg.blocks[node].name
        print(f"  {block_name}: {doms}")

