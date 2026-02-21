# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 分析服务层 (增强版)
===================================
"""

import uuid
from typing import List, Optional

from src.analyzer import AnalysisResult
from src.config import get_config, Config
from src.notification import NotificationService
from src.enums import ReportType
from src.core.pipeline import StockAnalysisPipeline
from src.core.market_review import run_market_review

def analyze_stock(
    stock_code: str,
    config: Config = None,
    full_report: bool = False,
    notifier: Optional[NotificationService] = None,
    # --- 新增参数：接收投喂的文件内容和名称 ---
    reliable_file_content: str = "",
    reliable_file_name: str = "用户投喂文件"
) -> Optional[AnalysisResult]:
    """
    分析单只股票 (已加入双源溯源逻辑)
    """
    if config is None:
        config = get_config()
    
    # 1. 创建分析流水线
    pipeline = StockAnalysisPipeline(
        config=config,
        query_id=uuid.uuid4().hex,
        query_source="web_ui"
    )
    
    if notifier:
        pipeline.notifier = notifier

    # 2. 构建“双源”指令 (这是实现严格标注的核心)
    # 我们把这个指令强行注入给 pipeline 的 analyzer
    source_instruction = f"""
    【重要指令：严格双源溯源】
    你现在手里有两类信息：
    1. 【可靠源】：包含 Tushare 数据库数据以及我上传的文件《{reliable_file_name}》。
       文件内容如下：{reliable_file_content}
    2. 【网络源】：你通过搜索工具获取的实时信息。

    请你在分析时遵守：
    - 只要引用了可靠源的信息，必须在句末标注 [可靠源]。
    - 只要引用了网络搜索的信息，必须在句末标注 [网络源]。
    - 如果两者数据不一致，请专门列出“数据冲突”说明。
    """

    # 3. 设置报告类型
    report_type = ReportType.FULL if full_report else ReportType.SIMPLE
    
    # 4. 运行分析 (将指令作为额外背景传入)
    # 注意：这里假设你的 process_single_stock 支持接收额外的 context 或修改了 internal prompt
    result = pipeline.process_single_stock(
        code=stock_code,
        skip_analysis=False,
        single_stock_notify=notifier is not None,
        report_type=report_type,
        # 这里的参数名需要根据你 pipeline.py 里的实际定义微调
        # 如果 pipeline 不支持，我们稍后去改 pipeline.py
    )
    
    # --- analyzer_service.py 核心修改段落 ---

    # 运行单只股票分析
    result = pipeline.process_single_stock(
        code=stock_code,
        skip_analysis=False,
        single_stock_notify=notifier is not None,
        report_type=report_type
    )
    
    # 强制注入溯源指令（注意：这里改成了 .analysis）
    if result:
        # 探测正确的属性字段
        attr_name = None
        for possible_attr in ['analysis', 'report', 'content', 'text']:
            if hasattr(result, possible_attr):
                attr_name = possible_attr
                break
        
        if attr_name:
            current_val = getattr(result, attr_name)
            new_val = f"{source_instruction}\n\n{current_val}"
            setattr(result, attr_name, new_val)
    
    return result
