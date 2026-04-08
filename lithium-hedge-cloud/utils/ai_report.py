from typing import Any, Dict

from utils.ai_client import generate_text_with_deepseek


def _safe_num(v: Any) -> str:
    if v is None:
        return "未提供"
    try:
        if isinstance(v, (int, float)):
            return f"{v:,.2f}"
        return str(v)
    except Exception:
        return str(v)


def build_hedge_report_prompt(data: Dict[str, Any]) -> str:
    return f"""
请基于以下套保测算结果，生成一份更详细的企业风控分析报告。

注意要求：
1. 不得虚构不存在的市场数据
2. 不得把推测写成既定事实
3. 必须明确区分“已知输入”和“分析判断”
4. 输出语言要专业、克制，适合企业内部风控参考
5. 不要写成空泛鸡汤
6. 如果信息不足，要明确指出“需结合企业实际经营情况进一步确认”
7. 不要重新编造价格序列，不要生成任何模拟行情
8. 如果某些参数来自统计口径或参考价，请明确提示其适用边界

已知输入如下：

一、企业与场景
- 企业类型：新能源产业链相关企业
- 分析场景：碳酸锂套期保值测算

二、核心输入参数
- 套保方向：{_safe_num(data.get("hedge_side"))}
- 库存/敞口数量（吨）：{_safe_num(data.get("inventory_qty"))}
- 现货参考价（元/吨）：{_safe_num(data.get("spot_price"))}
- 真实采购成本（元/吨）：{_safe_num(data.get("real_cost"))}
- 期货价格（元/吨）：{_safe_num(data.get("futures_price"))}
- 基差（元/吨）：{_safe_num(data.get("basis"))}
- 基差口径：{_safe_num(data.get("basis_label"))}
- 建议套保比例：{_safe_num(data.get("hedge_ratio"))}
- 套保手数：{_safe_num(data.get("hedge_lots"))}
- 预计保证金（元）：{_safe_num(data.get("margin"))}
- 保证金比例：{_safe_num(data.get("margin_rate"))}
- 数据时间：{_safe_num(data.get("latest_date"))}

三、测算结果
- 未套保情景盈亏：{_safe_num(data.get("pnl_unhedged"))}
- 套保后情景盈亏：{_safe_num(data.get("pnl_hedged"))}
- 盈亏改善额：{_safe_num(data.get("pnl_improvement"))}
- 压力情景说明：{_safe_num(data.get("stress_note"))}

请按以下结构输出：

# AI套保分析报告

## 一、核心结论
用 3-5 条直接概括结果。

## 二、当前风险敞口分析
结合库存、价格波动、基差口径说明当前主要风险。

## 三、套保方案解读
解释为什么当前建议比例和手数有意义，并指出其适用前提。

## 四、主要风险提示
至少写 4 条，重点写：
- 基差风险
- 保证金占用风险
- 套保不足或过度套保风险
- 现货参考价与真实成交价偏离风险

## 五、后续建议关注指标
列出企业后续应持续跟踪的指标。

## 六、审慎提示
最后加一段简短提示，强调本报告仅作为内部辅助参考，不替代企业实际交易决策。
"""


def generate_hedge_analysis_report(data: Dict[str, Any]) -> str:
    system_prompt = """
你是一名新能源产业链企业风险管理顾问，擅长套期保值分析、基差分析、库存风险分析和风控报告撰写。
你的任务是根据用户给出的真实业务参数，生成专业、审慎、结构化的中文分析报告。
禁止捏造数据，禁止输出模拟行情，禁止把不确定信息写成确定事实。
"""

    user_prompt = build_hedge_report_prompt(data)
    return generate_text_with_deepseek(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model="deepseek-chat",
        temperature=0.2,
        max_tokens=1800,
    )
