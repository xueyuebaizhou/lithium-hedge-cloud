# app_cloud.py - 完整云端版本
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from matplotlib import font_manager
import os
import sys
from datetime import datetime, timedelta
import warnings
import json
import io
import base64
import hashlib
import traceback
import math
from typing import Optional, Dict, Any, List
warnings.filterwarnings('ignore')

# 添加utils路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))

# 导入Supabase管理器
try:
    from supabase_client import get_supabase_manager
    supabase = get_supabase_manager()
    HAS_SUPABASE = supabase is not None
except ImportError as e:
    HAS_SUPABASE = False
    print(f"Supabase导入失败: {e}")


def ensure_chinese_font():
    """确保云端环境可用中文字体。"""
    font_dir = os.path.join(os.path.dirname(__file__), 'data', 'fonts')
    os.makedirs(font_dir, exist_ok=True)
    font_path = os.path.join(font_dir, 'NotoSansSC-Regular.otf')
    font_url = (
        "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/"
        "SimplifiedChinese/NotoSansSC-Regular.otf"
    )
    if not os.path.exists(font_path):
        try:
            import urllib.request
            urllib.request.urlretrieve(font_url, font_path)
        except Exception as exc:
            print(f"中文字体下载失败: {exc}")
            return None

    try:
        font_manager.fontManager.addfont(font_path)
        font_name = font_manager.FontProperties(fname=font_path).get_name()
        return font_name
    except Exception as exc:
        print(f"中文字体加载失败: {exc}")
        return None


chinese_font = ensure_chinese_font()
if chinese_font:
    matplotlib.rcParams['font.sans-serif'] = [chinese_font, 'DejaVu Sans', 'Arial']
else:
    matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
matplotlib.rcParams['axes.unicode_minus'] = False

# ============================================================================
# 用户认证管理器（云端版）
# ============================================================================

class CloudUserAuth:
    """云端用户认证管理器

    说明：
    - 认证与数据存储通过 utils/supabase_client.py 中的 Supabase 管理器完成（若存在）。
    - 由于不同版本/封装返回值形态不同，本类统一将所有返回规范化为 (ok, payload)。
    """

    def __init__(self):
        self.supabase = supabase if HAS_SUPABASE else None

    @staticmethod
    def _normalize_result(ret, default_ok: bool = False):
        """Normalize backend returns to (ok, payload)."""
        if isinstance(ret, tuple):
            if len(ret) >= 2:
                return bool(ret[0]), ret[1]
            if len(ret) == 1:
                return bool(ret[0]), None
            return default_ok, None
        # Some helpers may return dict/string directly
        return default_ok, ret

    def register(self, username: str, password: str, email: str):
        """注册用户。返回 (ok, payload/message)"""
        if not self.supabase:
            return False, "数据库连接失败，请检查配置"

        username = (username or "").strip()
        email = (email or "").strip()
        password = password or ""

        if len(username) < 3:
            return False, "用户名至少3个字符"
        if "@" not in email or "." not in email:
            return False, "请输入有效的邮箱地址"
        if len(password) < 6:
            return False, "密码长度至少6位"

        # Prefer project-specific helper if available
        for fn_name in ["create_user", "register", "sign_up", "signup"]:
            fn = getattr(self.supabase, fn_name, None)
            if callable(fn):
                try:
                    return self._normalize_result(fn(username, password, email), default_ok=True)
                except TypeError:
                    # Some SDK use (email, password) only
                    try:
                        return self._normalize_result(fn(email, password), default_ok=True)
                    except Exception as e:
                        return False, f"注册失败: {e}"
                except Exception as e:
                    return False, f"注册失败: {e}"

        # Supabase python client often uses supabase.auth.sign_up(...)
        auth = getattr(self.supabase, "auth", None)
        if auth and hasattr(auth, "sign_up"):
            try:
                return self._normalize_result(auth.sign_up({"email": email, "password": password}), default_ok=True)
            except Exception as e:
                return False, f"注册失败: {e}"

        return False, "后端未提供注册接口"

    def login(self, username_or_email: str, password: str):
        """登录。返回 (ok, payload)"""
        if not self.supabase:
            return False, "数据库连接失败，请检查配置"

        username_or_email = (username_or_email or "").strip()
        password = password or ""
        if not username_or_email:
            return False, "请输入用户名或邮箱"
        if not password:
            return False, "请输入密码"

        # Prefer project helper
        for fn_name in ["authenticate_user", "login", "sign_in", "sign_in_with_password"]:
            fn = getattr(self.supabase, fn_name, None)
            if callable(fn):
                try:
                    if fn_name == "sign_in_with_password":
                        return self._normalize_result(fn({"email": username_or_email, "password": password}), default_ok=True)
                    return self._normalize_result(fn(username_or_email, password), default_ok=True)
                except TypeError:
                    # Sometimes accepts (email, password) only
                    try:
                        return self._normalize_result(fn(username_or_email, password), default_ok=True)
                    except Exception as e:
                        return False, f"登录失败: {e}"
                except Exception as e:
                    return False, f"登录失败: {e}"

        # Supabase auth style
        auth = getattr(self.supabase, "auth", None)
        if auth and hasattr(auth, "sign_in_with_password"):
            try:
                return self._normalize_result(auth.sign_in_with_password({"email": username_or_email, "password": password}), default_ok=True)
            except Exception as e:
                return False, f"登录失败: {e}"

        return False, "后端未提供登录接口"

    def change_password(self, username_or_email: str, old_password: str, new_password: str):
        """修改密码：先验证旧密码再改新密码（若后端支持）。"""
        if not self.supabase:
            return False, "数据库连接失败"

        new_password = new_password or ""
        if len(new_password) < 6:
            return False, "新密码至少6位"

        # If helper exists
        for fn_name in ["change_password", "update_password", "update_user_password"]:
            fn = getattr(self.supabase, fn_name, None)
            if callable(fn):
                try:
                    return self._normalize_result(fn(username_or_email, old_password, new_password), default_ok=True)
                except TypeError:
                    try:
                        return self._normalize_result(fn(username_or_email, new_password), default_ok=True)
                    except Exception as e:
                        return False, f"修改密码失败: {e}"
                except Exception as e:
                    return False, f"修改密码失败: {e}"

        return False, "后端未提供改密接口"

    def generate_reset_code(self, username_or_email: str):
        """生成/发送重置码（如有邮件验证）。"""
        if not self.supabase:
            return False, "数据库连接失败"

        for fn_name in ["generate_reset_code", "send_reset_code", "send_password_reset_email", "reset_password_for_email"]:
            fn = getattr(self.supabase, fn_name, None)
            if callable(fn):
                try:
                    return self._normalize_result(fn(username_or_email), default_ok=True)
                except Exception as e:
                    return False, f"发送重置码失败: {e}"

        auth = getattr(self.supabase, "auth", None)
        if auth and hasattr(auth, "reset_password_for_email"):
            try:
                return self._normalize_result(auth.reset_password_for_email(username_or_email), default_ok=True)
            except Exception as e:
                return False, f"发送重置码失败: {e}"

        return False, "后端未提供重置码接口"

    def reset_password(self, username_or_email: str, new_password: str):
        """直接重置密码（需要后端允许）。"""
        if not self.supabase:
            return False, "数据库连接失败"

        new_password = new_password or ""
        if len(new_password) < 6:
            return False, "新密码至少6位"

        for fn_name in ["reset_password", "set_password", "update_user_password", "update_password"]:
            fn = getattr(self.supabase, fn_name, None)
            if callable(fn):
                try:
                    return self._normalize_result(fn(username_or_email, new_password), default_ok=True)
                except Exception as e:
                    return False, f"重置密码失败: {e}"

        return False, "后端未提供重置密码接口"

    def update_user_settings(self, user_id: str, settings: dict):
        """更新用户设置（可选）。"""
        if not self.supabase:
            return False, "数据库连接失败"
        for fn_name in ["update_user_settings", "update_settings"]:
            fn = getattr(self.supabase, fn_name, None)
            if callable(fn):
                try:
                    return self._normalize_result(fn(user_id, settings), default_ok=True)
                except Exception as e:
                    return False, f"更新设置失败: {e}"
        return False, "后端未提供设置更新接口"
class CloudLithiumAnalyzer:
    """云端碳酸锂数据分析器"""
    
    def __init__(self):
        self.auth = CloudUserAuth()
        self.supabase = supabase if HAS_SUPABASE else None
        self.cache_data = {}
        self.cache_time = {}
    
    def fetch_real_time_data(self, symbol='LC0', years=1, force_refresh=False):
        """获取实时数据（带云端缓存）"""
        # 检查缓存
        cache_key = f"{symbol}_{years}"
        current_time = datetime.now()
        
        if (not force_refresh and cache_key in self.cache_data and 
            cache_key in self.cache_time and
            (current_time - self.cache_time[cache_key]).seconds < 1800):  # 30分钟缓存
            return self.cache_data[cache_key]
        
        # 检查云端缓存
        if self.supabase and not force_refresh:
            cached_data = self.supabase.get_price_data(symbol)
            if cached_data is not None:
                self.cache_data[cache_key] = cached_data
                self.cache_time[cache_key] = current_time
        ax.plot(price_changes * 100, hedge_profits, 'g-', linewidth=2.5, label='套保后盈亏')
        
        ax.set_xlabel('未来价格变化百分比 (%)', fontsize=13)
        ax.set_ylabel('盈亏金额 (元)', fontsize=13)
        ax.set_title(f'碳酸锂存货套保盈亏分析（{latest_date.strftime("%Y-%m-%d")}）', 
                    fontsize=16, fontweight='bold', pad=20)
        
        # 设置y轴范围
        y_min = min(min(no_hedge_profits), min(hedge_profits))
        y_max = max(max(no_hedge_profits), max(hedge_profits))
        y_abs_max = max(abs(y_min), abs(y_max))
        ax.set_ylim(-y_abs_max * 1.1, y_abs_max * 1.1)
        
        # 格式化y轴标签
        def format_y_axis(value):
            if abs(value) >= 1_0000_0000:  # 1亿
                return f'{value/1_0000_0000:.1f}亿'
            elif abs(value) >= 10000:  # 1万
                return f'{value/10000:.0f}万'
            else:
                return f'{value:.0f}'
        
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, pos: format_y_axis(x)))
        
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.axhline(y=0, color='k', linestyle='-', linewidth=0.8)
        ax.axvline(x=0, color='b', linestyle='--', linewidth=1.5, alpha=0.7, label='当前价格')
        
        if inventory != hedge_contracts_int:
            ax.axvline(x=no_hedge_breakeven_pct, color='r', linestyle=':', linewidth=1.5, alpha=0.5)
            ax.axvline(x=hedge_breakeven_pct, color='g', linestyle=':', linewidth=1.5, alpha=0.5)
        
        ax.legend(fontsize=12, loc='best', framealpha=0.9)
        
        # 添加当前点标注
        current_profit_no_hedge = (current_price - cost_price) * inventory
        ax.scatter(0, current_profit_no_hedge, color='r', s=100, zorder=5)
        ax.scatter(0, current_profit_no_hedge, color='g', s=100, zorder=5)
        ax.annotate(
            f"基准点 (0%, {current_profit_no_hedge:,.0f})",
            xy=(0, current_profit_no_hedge),
            xytext=(10, current_profit_no_hedge + y_abs_max * 0.05),
            textcoords='data',
            arrowprops=dict(arrowstyle='->', color='#1f77b4', lw=1.2),
            fontsize=11,
            color='#1f77b4',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8)
        )
        
        plt.tight_layout()
        
        # 生成建议文本
        suggestions = []
        suggestions.append("### 套保分析报告")
        suggestions.append(f"**数据来源**：akshare实时市场数据")
        suggestions.append(f"**分析时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        suggestions.append(f"**数据日期**：{latest_date.strftime('%Y-%m-%d')}")
        
        suggestions.append("\n### 输入参数")
        suggestions.append(f"- **存货成本价**：{cost_price:,.2f} 元/吨")
        suggestions.append(f"- **存货数量**：{inventory:,.2f} 吨")
        suggestions.append(f"- **套保比例**：{hedge_ratio*100:.1f}%")
        suggestions.append(f"- **保证金比例**：{margin_rate*100:.0f}%")
        
        suggestions.append("\n### 市场数据")
        suggestions.append(f"- **当前市场价格**：{current_price:,.2f} 元/吨")
        suggestions.append(f"- **每吨盈亏**：{profit_per_ton:,.2f} 元/吨 ({profit_percentage:.2f}%)")
        suggestions.append(f"- **总盈亏**：{current_profit:,.2f} 元")
        
        suggestions.append("\n### 套保方案")
        suggestions.append(f"- **理论套保手数**：{hedge_contracts:.2f} 手")
        suggestions.append(f"- **实际套保手数**：{hedge_contracts_int} 手 (四舍五入取整)")
        actual_ratio = hedge_contracts_int / inventory * 100 if inventory > 0 else 0
        margin_ratio = total_margin / total_value * 100 if total_value > 0 else 0
        suggestions.append(f"- **实际套保比例**：{actual_ratio:.2f}%")
        suggestions.append(f"- **每手保证金**：{margin_per_contract:,.2f} 元")
        suggestions.append(f"- **总保证金要求**：{total_margin:,.2f} 元")
        suggestions.append(f"- **保证金占存货价值**：{margin_ratio:.2f}%")
        
        suggestions.append("\n### 风险分析")
        suggestions.append(f"- **不套保盈亏平衡点**：{no_hedge_breakeven:,.2f} 元/吨 (较当前价{no_hedge_breakeven_pct:.1f}%)")
        suggestions.append(f"- **套保后盈亏平衡点**：{hedge_breakeven_str}")
        
        suggestions.append("\n### 操作建议")
        
        if hedge_ratio < 0.1:
            suggestions.append("**评估**：套保比例极低，风险敞口极大")
            suggestions.append("**建议**：立即将套保比例提高至50%以上")
        elif hedge_ratio < 0.3:
            suggestions.append("**评估**：套保比例较低，存在较大价格风险")
            suggestions.append("**建议**：考虑提高套保比例至60-80%")
        elif hedge_ratio < 0.7:
            suggestions.append("**评估**：套保比例适中，风险可控")
            suggestions.append("**建议**：维持当前比例或根据市场情况微调")
        elif hedge_ratio <= 1.0:
            suggestions.append("**评估**：套保比例充足，有效对冲风险")
            suggestions.append("**建议**：当前比例合适，关注市场变化")
        else:
            suggestions.append("**评估**：过度套保，可能产生额外风险")
            suggestions.append("**建议**：将套保比例调整至100%以内")
        
        if current_profit > 0:
            suggestions.append(f"\n**盈利状态**：当前盈利{profit_percentage:.2f}%，建议部分套保锁定利润")
            if profit_percentage > 20:
                suggestions.append("**策略建议**：可考虑锁定30-50%的利润")
        else:
            suggestions.append(f"\n**亏损状态**：当前亏损{abs(profit_percentage):.2f}%，建议加强套保防止进一步亏损")
            if abs(profit_percentage) > 10:
                suggestions.append("**策略建议**：考虑提高套保比例至80-100%")
        
        if hedge_contracts_int > 0:
            suggestions.append("\n### 实施方案")
            suggestions.append(f"1. **资金准备**：准备 {total_margin:,.0f} 元作为期货保证金")
            suggestions.append("2. **合约选择**：选择LC0主力合约或对应月份合约")
            suggestions.append("3. **交易方向**：卖出空头合约对冲价格下跌风险")
            suggestions.append("4. **入场时机**：根据市场走势选择合适入场点")
            suggestions.append("5. **风险监控**：每日关注价格变化和保证金情况")
            suggestions.append("6. **调整策略**：根据市场变化动态调整套保比例")
        else:
            suggestions.append("\n### 风险提示")
            suggestions.append(f"套保手数为0，无法有效对冲价格风险")
            suggestions.append(f"建议将套保比例从{hedge_ratio*100:.1f}%提高至至少50%")
        
        suggestions.append("\n### 注意事项")
        suggestions.append("1. **基差风险**：期货价格与现货价格可能存在差异")
        suggestions.append("2. **保证金风险**：价格剧烈波动可能导致保证金追加")
        suggestions.append("3. **流动性风险**：市场流动性不足可能影响平仓")
        suggestions.append("4. **操作风险**：期货交易需要专业知识和经验")
        suggestions.append("5. **免责声明**：本分析仅供参考，不构成投资建议")
        
        # 保存分析历史到云端
        if self.supabase and 'user_info' in st.session_state:
            input_params = {
                'cost_price': cost_price,
                'inventory': inventory,
                'hedge_ratio': hedge_ratio,
                'margin_rate': margin_rate
            }
            
            result_data = {
                'current_price': current_price,
                'hedge_contracts': hedge_contracts_int,
                'total_margin': total_margin,
                'profit_status': '盈利' if current_profit > 0 else '亏损',
                'profit_amount': current_profit,
                'profit_percentage': profit_percentage
            }
            
            analysis_id = self.supabase.save_analysis_result(
                st.session_state.user_info['user_id'],
                'hedge_calculation',
                input_params,
                result_data
            )
            
            if analysis_id:
         
                suggestions.append(f"\n**分析记录**：已保存到云端 (ID: {analysis_id})")
        
        return fig, "\n".join(suggestions), {
            'current_price': current_price,
            'hedge_contracts_int': hedge_contracts_int,
            'total_margin': total_margin,
            'current_profit': current_profit,
            'profit_percentage': profit_percentage,
            'latest_date': latest_date,
            'no_hedge_breakeven': no_hedge_breakeven,
            'hedge_breakeven': hedge_breakeven_str
        }
    
    def get_price_chart(self, period='1y'):
        """获取价格走势图（用于行情页）"""
        price_data = self.fetch_real_time_data()

        if price_data is None or price_data.empty:
            st.error("无法获取价格数据")
            return None, "数据获取失败"

        # 标准化日期列
        if "日期" in price_data.columns:
            price_data = price_data.sort_values("日期").copy()
        else:
            # 兼容没有日期列的情况
            price_data = price_data.reset_index().rename(columns={"index": "日期"}).sort_values("日期")

        # 根据周期筛选数据
        period = (period or "1y").lower()
        if period in ["1m", "30d"]:
            display_data = price_data.tail(30)
            title_suffix = "近30日"
        elif period in ["3m", "90d"]:
            display_data = price_data.tail(90)
            title_suffix = "近3个月"
        elif period in ["6m", "180d"]:
            display_data = price_data.tail(180)
            title_suffix = "近6个月"
        elif period in ["1y", "365d", "12m"]:
            display_data = price_data.tail(365)
            title_suffix = "近1年"
        else:
            display_data = price_data.copy()
            title_suffix = "全历史"

        # 选择价格列（优先收盘价）
        price_col = None
        for c in ["收盘价", "收盘", "close", "Close", "价格", "price"]:
            if c in display_data.columns:
                price_col = c
                break
        if price_col is None:
            st.error("价格数据列缺失（未找到收盘价/价格列）")
            return None, "价格数据列缺失"

        # 创建图表
        fig, ax = plt.subplots(figsize=(10, 4.8))
        ax.plot(display_data["日期"], display_data[price_col], linewidth=2.2, label="价格")

        # 标注最高/最低点
        try:
            max_idx = display_data[price_col].idxmax()
            min_idx = display_data[price_col].idxmin()
            max_row = display_data.loc[max_idx]
            min_row = display_data.loc[min_idx]

            ax.annotate(
                f"{max_row[price_col]:,.0f}",
                xy=(max_row["日期"], max_row[price_col]),
                xytext=(max_row["日期"], max_row[price_col] * 1.02),
                arrowprops=dict(arrowstyle="->", lw=1.4),
                fontsize=11,
                ha="center",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85),
            )
            ax.annotate(
                f"{min_row[price_col]:,.0f}",
                xy=(min_row["日期"], min_row[price_col]),
                xytext=(min_row["日期"], min_row[price_col] * 0.98),
                arrowprops=dict(arrowstyle="->", lw=1.4),
                fontsize=11,
                ha="center",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85),
            )
        except Exception:
            # 标注不是关键功能，忽略标注失败
            pass

        ax.set_title(f"碳酸锂期货 {title_suffix} 价格走势图", fontsize=16, fontweight="bold", pad=16)
        ax.set_xlabel("日期", fontsize=12)
        ax.set_ylabel("价格 (元/吨)", fontsize=12)
        ax.grid(True, alpha=0.25, linestyle="--")

        # y轴格式化
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, pos: f"{x:,.0f}"))

        plt.xticks(rotation=30)
        plt.tight_layout()

        # 生成统计信息
        stats_text = []
        try:
            start_date = pd.to_datetime(display_data["日期"].min()).strftime("%Y-%m-%d")
            end_date = pd.to_datetime(display_data["日期"].max()).strftime("%Y-%m-%d")
        except Exception:
            start_date = str(display_data["日期"].min())
            end_date = str(display_data["日期"].max())

        stats_text.append(f"### {title_suffix} 市场统计")
        stats_text.append(f"**数据期间**：{start_date} 至 {end_date}")
        stats_text.append(f"**最新价格**：{display_data[price_col].iloc[-1]:,.2f} 元/吨")
        stats_text.append(f"**期间最高**：{display_data[price_col].max():,.2f} 元/吨")
        stats_text.append(f"**期间最低**：{display_data[price_col].min():,.2f} 元/吨")
        stats_text.append(f"**平均价格**：{display_data[price_col].mean():,.2f} 元/吨")
        stats_text.append(f"**价格标准差**：{display_data[price_col].std():,.2f} 元/吨")

        # 日收益统计（如果可计算）
        if len(display_data) >= 2:
            returns = display_data[price_col].pct_change() * 100
            avg_return = returns.mean()
            up_days = int((returns > 0).sum())
            down_days = int((returns < 0).sum())
            flat_days = int((returns == 0).sum())
            max_up = returns.max()
            max_down = returns.min()
            stats_text.append(f"**平均日涨跌**：{avg_return:.2f}%")
            stats_text.append(f"**上涨天数**：{up_days} 天 ({up_days/len(display_data)*100:.1f}%)")
            stats_text.append(f"**下跌天数**：{down_days} 天 ({down_days/len(display_data)*100:.1f}%)")
            stats_text.append(f"**平盘天数**：{flat_days} 天 ({flat_days/len(display_data)*100:.1f}%)")
            stats_text.append(f"**最大单日涨幅**：{max_up:.2f}%")
            stats_text.append(f"**最大单日跌幅**：{max_down:.2f}%")

        if "成交量" in display_data.columns:
            avg_volume = display_data["成交量"].mean()
            total_volume = display_data["成交量"].sum()
            stats_text.append(f"**日均成交量**：{avg_volume:,.0f} 手")
            stats_text.append(f"**总成交量**：{total_volume:,.0f} 手")

        return fig, "\n".join(stats_text)

    def get_user_history(self, limit=20):
        """获取用户分析历史"""
        if not self.supabase or 'user_info' not in st.session_state:
            return []
        
        return self.supabase.get_user_analysis_history(
            st.session_state.user_info['user_id'],
            limit=limit
        )
    
    def delete_history_record(self, analysis_id):
        """删除历史记录"""
        if not self.supabase or 'user_info' not in st.session_state:
            return False
        
        return self.supabase.delete_analysis(
            analysis_id,
            st.session_state.user_info['user_id']
        )

# ============================================================================
# 金融工具函数
# ============================================================================

def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def black_scholes_price(option_type: str, spot: float, strike: float, time_years: float,
                        risk_free: float, volatility: float) -> float:
    if spot <= 0 or strike <= 0 or time_years <= 0 or volatility <= 0:
        return 0.0

    d1 = (math.log(spot / strike) + (risk_free + 0.5 * volatility ** 2) * time_years) / (
        volatility * math.sqrt(time_years)
    )
    d2 = d1 - volatility * math.sqrt(time_years)

    if option_type == "call":
        return spot * _norm_cdf(d1) - strike * math.exp(-risk_free * time_years) * _norm_cdf(d2)
    return strike * math.exp(-risk_free * time_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)

# ============================================================================
# Streamlit应用主程序
# ============================================================================

def main():
    st.set_page_config(
        page_title="碳酸锂期货套保分析系统（云端版）",
        page_icon="LC",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 初始化分析器
    analyzer = CloudLithiumAnalyzer()
    
    # 初始化session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user_info' not in st.session_state:
        st.session_state.user_info = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "首页"
    if 'show_forgot_password' not in st.session_state:
        st.session_state.show_forgot_password = False
    if 'show_reset_form' not in st.session_state:
        st.session_state.show_reset_form = False
    if 'reset_username' not in st.session_state:
        st.session_state.reset_username = None
    if 'force_refresh' not in st.session_state:
        st.session_state.force_refresh = False
    
    # 自定义CSS
    st.markdown("""
    <style>
    html, body, [class*="css"]  {
        font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
        background-color: #f5f5f7;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 600;
        color: #1c1c1e;
        text-align: center;
        margin-bottom: 0.75rem;
    }
    .cloud-badge {
        background: rgba(10, 132, 255, 0.15);
        color: #0a84ff;
        padding: 4px 12px;
        border-radius: 18px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin-left: 8px;
        vertical-align: middle;
    }
    .data-source {
        font-size: 0.8rem;
        color: #6e6e73;
        text-align: right;
        margin-top: -10px;
        margin-bottom: 20px;
    }
    .card {
        background: white;
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
    }
    .stButton > button {
        border-radius: 12px;
        border: 1px solid #e5e5ea;
        background: white;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 14px rgba(0,0,0,0.08);
    }
    
    /* Ensure button text is always visible (especially primary buttons) */
    .stButton > button { color: #1c1c1e; }
    button[kind="primary"], button[data-testid="baseButton-primary"] {
        color: #ffffff !important;
        background-color: #ff3b30 !important;
        border: none !important;
        font-weight: 600 !important;
    }
    button[kind="primary"]:hover, button[data-testid="baseButton-primary"]:hover {
        color: #ffffff !important;
        filter: brightness(0.95);
    }

</style>
    """, unsafe_allow_html=True)
    
    # 检查Supabase连接状态
    with st.sidebar:
        if HAS_SUPABASE:
            st.success("Supabase连接正常")
        else:
            st.error("Supabase未配置")
            st.info("请设置环境变量：SUPABASE_URL和SUPABASE_KEY")
            st.info("当前使用本地模拟模式")
    
    # 登录/注册页面
    if not st.session_state.authenticated:
        if st.session_state.show_forgot_password:
            render_forgot_password(analyzer)
        elif st.session_state.show_reset_form and st.session_state.reset_username:
            render_reset_password(analyzer)
        else:
            render_auth_page(analyzer)
        return
    
    # 主应用界面
    render_main_app(analyzer)

# ============================================================================
# 页面渲染函数
# ============================================================================

def render_auth_page(analyzer):
    """渲染登录/注册页面"""
    st.markdown('<h1 class="main-header">碳酸锂期货套保分析系统</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#6e6e73;font-size:1.05rem;">云端存储 · 实时数据 · 专业分析</p>', unsafe_allow_html=True)

    # 忘记密码弹窗状态
    if "show_forgot_password" not in st.session_state:
        st.session_state.show_forgot_password = False

    tab_login, tab_register = st.tabs(["用户登录", "新用户注册"])

    with tab_login:
        col_left, col_center, col_right = st.columns([1, 2, 1])
        with col_center:
            st.markdown("### 用户登录")
            username = st.text_input("用户名", placeholder="请输入用户名", key="login_username")
            password = st.text_input("密码", type="password", placeholder="请输入密码", key="login_password")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("登录", type="primary", use_container_width=True):
                    with st.spinner("正在验证..."):
                        success, result = analyzer.auth.login(username, password)
                    if success:
                        st.session_state.authenticated = True
                        # result 可能是 dict 或字符串
                        if isinstance(result, dict):
                            st.session_state.user_info = {
                                "user_id": result.get("user_id") or result.get("id"),
                                "username": result.get("username") or username,
                                "email": result.get("email"),
                                "settings": result.get("settings", {}),
                            }
                        else:
                            st.session_state.user_info = {"username": username}
                        st.success("登录成功！")
                        st.rerun()
                    else:
                        msg = result.get("message") if isinstance(result, dict) else str(result)
                        st.error(msg or "登录失败")

            with col_btn2:
                if st.button("忘记密码", use_container_width=True):
                    st.session_state.show_forgot_password = True
                    st.rerun()

            with st.expander("快速体验"):
                st.markdown("""**演示账号**（如已在数据库中创建）：  
- 用户名：demo_user  
- 密码：demo123  

也可以直接注册新账号。""")

    with tab_register:
        col_left, col_center, col_right = st.columns([1, 2, 1])
        with col_center:
            st.markdown("### 新用户注册")
            new_username = st.text_input("用户名", key="reg_username", placeholder="至少3个字符")
            new_email = st.text_input("邮箱", key="reg_email", placeholder="用于找回密码")
            new_password = st.text_input("密码", type="password", key="reg_password1", placeholder="至少6个字符")
            confirm_password = st.text_input("确认密码", type="password", key="reg_password2")

            if st.button("注册并登录", type="primary", use_container_width=True):
                if not new_username or not new_email or not new_password:
                    st.error("请完整填写注册信息")
                elif new_password != confirm_password:
                    st.error("两次输入的密码不一致")
                elif len(new_password) < 6:
                    st.error("密码长度至少6位")
                else:
                    with st.spinner("正在注册..."):
                        ok, msg = analyzer.auth.register(new_username, new_password, new_email)
                    if isinstance(msg, dict):
                        msg = msg.get('message') or msg.get('msg') or str(msg)
                    if ok:
                        st.success(msg if isinstance(msg, str) else "注册成功")
                        # 自动登录
                        with st.spinner("正在登录..."):
                            success, result = analyzer.auth.login(new_username, new_password)
                        if success:
                            st.session_state.authenticated = True
                            if isinstance(result, dict):
                                st.session_state.user_info = {
                                    "user_id": result.get("user_id") or result.get("id"),
                                    "username": result.get("username") or new_username,
                                    "email": result.get("email") or new_email,
                                    "settings": result.get("settings", {}),
                                }
                            else:
                                st.session_state.user_info = {"username": new_username, "email": new_email}
                            st.rerun()
                        else:
                            st.info("注册成功，但自动登录失败，请回到“用户登录”手动登录。")
                    else:
                        st.error(msg if isinstance(msg, str) else "注册失败")

    if st.session_state.show_forgot_password:
        render_forgot_password(analyzer)

def render_forgot_password(analyzer):
    """渲染忘记密码页面"""
    st.markdown("### 找回密码")
    
    with st.container():
        col_left, col_center, col_right = st.columns([1, 2, 1])
        
        with col_center:
            username = st.text_input("用户名", key="forgot_username")
            email = st.text_input("注册邮箱", key="forgot_email")
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("获取验证码", use_container_width=True):
                    if username and email:
                        success, result = analyzer.auth.generate_reset_code(username, email)
                        if success:
                            st.session_state.reset_username = username
                            st.session_state.show_reset_form = True
                            st.success(f"验证码已发送到您的邮箱：**{result}**")
                            st.info("验证码有效期为1小时")
                            st.rerun()
                        else:
                            st.error(result)
                    else:
                        st.error("请输入用户名和邮箱")
            
            with col_btn2:
                if st.button("返回登录", use_container_width=True):
                    st.session_state.show_forgot_password = False
                    st.rerun()

def render_reset_password(analyzer):
    """渲染重置密码页面"""
    st.markdown(f"### 重置密码 - {st.session_state.reset_username}")
    
    with st.container():
        col_left, col_center, col_right = st.columns([1, 2, 1])
        
        with col_center:
            st.info(f"正在为用户 **{st.session_state.reset_username}** 重置密码")
            
            reset_code = st.text_input("验证码", placeholder="请输入6位验证码")
            new_password = st.text_input("新密码", type="password", placeholder="至少6个字符")
            confirm_password = st.text_input("确认新密码", type="password")
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("重置密码", type="primary", use_container_width=True):
                    if reset_code and new_password and confirm_password:
                        if new_password != confirm_password:
                            st.error("两次输入的密码不一致")
                        elif len(new_password) < 6:
                            st.error("密码长度至少6位")
                        else:
                            success, message = analyzer.auth.reset_password(
                                st.session_state.reset_username, reset_code, new_password
                            )
                            if success:
                                st.success(message)
                                st.session_state.show_reset_form = False
                                st.session_state.reset_username = None
                                st.session_state.show_forgot_password = False
                                st.info("请使用新密码登录")
                                st.rerun()
                            else:
                                st.error(message)
                    else:
                        st.error("请填写所有字段")
            
            with col_btn2:
                if st.button("取消", use_container_width=True):
                    st.session_state.show_reset_form = False
                    st.session_state.reset_username = None
                    st.rerun()


def render_main_app(analyzer):
    """渲染主应用界面"""
    pages = [
        "首页",
        "套保计算",
        "基差走势",
        "期权保险",
        "风险敞口",
        "多情景分析",
        "价格行情",
        "分析报告",
        "分析历史",
        "账号设置"
    ]

    with st.sidebar:
        st.markdown("### 导航")
        if st.session_state.current_page not in pages:
            st.session_state.current_page = pages[0]
        selected = st.radio("页面", pages, index=pages.index(st.session_state.current_page))
        st.session_state.current_page = selected

    st.markdown("<h2 class='main-header'>碳酸锂套保分析系统</h2>", unsafe_allow_html=True)
    st.markdown("<span class='cloud-badge'>云端版</span>", unsafe_allow_html=True)

    user_info = st.session_state.user_info
    st.markdown(
        f"<p style='text-align:right;color:#6e6e73;'>用户：{user_info['username']} | 云端存储 | "
        f"{datetime.now().strftime('%Y-%m-%d')}</p>",
        unsafe_allow_html=True
    )
    st.markdown('<p class="data-source">数据来源：akshare金融数据接口 | 数据更新：实时</p>',
                unsafe_allow_html=True)
    st.divider()

    if st.session_state.current_page == "首页":
        render_home_page(analyzer)
    elif st.session_state.current_page == "套保计算":
        render_hedge_page(analyzer)
    elif st.session_state.current_page == "基差走势":
        render_basis_page(analyzer)
    elif st.session_state.current_page == "期权保险":
        render_option_page(analyzer)
    elif st.session_state.current_page == "风险敞口":
        render_exposure_page(analyzer)
    elif st.session_state.current_page == "多情景分析":
        render_scenario_page(analyzer)
    elif st.session_state.current_page == "价格行情":
        render_price_page(analyzer)
    elif st.session_state.current_page == "分析报告":
        render_report_page(analyzer)
    elif st.session_state.current_page == "分析历史":
        render_history_page(analyzer)
    elif st.session_state.current_page == "账号设置":
        render_settings_page(analyzer)


def render_home_page(analyzer):
    """渲染首页"""
    st.markdown("<h1>系统首页</h1>", unsafe_allow_html=True)
    
    # 欢迎信息
    user_info = st.session_state.user_info
    st.markdown(f"### 欢迎回来，{user_info['username']}！")
    
    # 快速开始卡片

    st.markdown("### 快速开始")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        card1 = st.container()
        with card1:

            st.markdown("### 套保计算")
            st.markdown("基于当前市场价格，计算最优套保方案")
            if st.button("开始计算", key="home_calc", use_container_width=True):
                st.session_state.current_page = "套保计算"
                st.rerun()
    
    with col2:
        card2 = st.container()
        with card2:
            st.markdown("### 价格行情")
            st.markdown("查看碳酸锂期货实时价格走势")
            if st.button("查看行情", key="home_price", use_container_width=True):
                st.session_state.current_page = "价格行情"
                st.rerun()
    
    with col3:
        card3 = st.container()
        with card3:

            st.markdown("### 分析历史")
            st.markdown("查看您的历史分析记录")
            if st.button("查看历史", key="home_history", use_container_width=True):
                st.session_state.current_page = "分析历史"
                st.rerun()
    
    # 系统功能介绍

    st.markdown("### 系统功能")
    

    with st.expander("套保计算功能", expanded=True):
        st.markdown("""
        **核心计算功能**：
        1. **盈亏平衡分析**：自动计算套保前后的盈亏平衡点
        2. **情景模拟**：价格变动±50%到+100%的盈亏分析
        3. **保证金计算**：自动计算期货交易所需保证金
        4. **风险提示**：根据套保比例提供风险建议
        
        **计算参数**：
        - 存货成本价：0-500,000元/吨
        - 存货数量：0-10,000吨
        - 套保比例：0%-100%
        - 保证金比例：默认15%（可配置）
        """)
    
    with st.expander("价格行情功能"):
        st.markdown("""
        **实时数据**：
        - 来源：akshare金融数据接口
        - 合约：LC0主力合约及月合约
        - 频率：日度数据，自动更新
        
        **分析图表**：
        - 价格走势图
        - 移动平均线
        - 关键点标注
        - 统计信息
        
        **数据管理**：
        - 云端缓存30分钟
        - 手动刷新功能
        - 多周期查看
        """)
    

    with st.expander("云端功能"):
        st.markdown("""
        **数据存储**：
        - 用户数据安全存储在Supabase云端
        - 分析历史永久保存
        - 多设备同步访问
        
        **用户管理**：
        - 注册/登录/注销
        - 密码找回（邮箱验证）
        - 个性化设置
        - 数据隐私保护
        
        **安全特性**：
        - 密码bcrypt加密
        - HTTPS安全传输
        - 数据访问控制
        """)
    
    with st.expander("新增功能模块"):
        st.markdown("""
        - 基差走势与价格指数展示
        - 价格保险（期权）测算
        - 风险敞口量化与可视化
        - 多情景分析与对比表格
        - 分析报告汇总输出
        """)
    
    # 技术架构
    st.markdown("### 技术架构")
    
    architecture = """
    ```
    前端界面 (Streamlit)
         │
         ↓ HTTPS
    Python后端应用
         │
         ↓ API调用
    Supabase云端数据库 (PostgreSQL)
         │
         ↓ API调用
    第三方数据源 (akshare)
    ```
    
    **技术栈**：
    - 前端：Streamlit + Matplotlib
    - 后端：Python + Supabase SDK
    - 数据库：PostgreSQL (Supabase)
    - 数据源：akshare金融数据
    - 部署：Streamlit Community Cloud
    """
    
    st.code(architecture, language=None)
    
    # 侧边栏显示实时价格
    with st.sidebar:
        st.markdown("### 实时价格")
        try:
            price_data = analyzer.fetch_real_time_data(force_refresh=st.session_state.force_refresh)
            if st.session_state.force_refresh:
                st.session_state.force_refresh = False
            
            if not price_data.empty:
                latest_price = price_data['收盘价'].iloc[-1]
                latest_date = price_data['日期'].iloc[-1]
                
                if '涨跌幅' in price_data.columns:
                    price_change = price_data['涨跌幅'].iloc[-1]
                else:
                    price_change = 0
                
                delta_color = "normal" if price_change >= 0 else "inverse"
                st.metric(
                    label="碳酸锂期货",
                    value=f"{latest_price:,.0f}",
                    delta=f"{price_change:.2f}%" if price_change != 0 else None,
                    delta_color=delta_color
                )
                st.caption(f"更新时间：{latest_date.strftime('%Y-%m-%d')}")
        except:
            st.warning("无法获取实时价格")
def render_hedge_page(analyzer):
    """渲染套保计算页面"""
    st.markdown("<h1>套保计算器</h1>", unsafe_allow_html=True)
    
    # 获取用户设置（如果有）
    user_settings = {}
    if 'user_info' in st.session_state and st.session_state.user_info.get('settings'):
        user_settings = st.session_state.user_info['settings']
    
    # 创建两列布局
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.markdown("### 输入参数")
        st.markdown("---")
        
        # 成本价输入
        default_cost = user_settings.get('default_cost_price', 100000.0)
        cost_price = st.number_input(
            "存货成本价 (元/吨)",
            min_value=0.0,
            max_value=500000.0,
            value=float(default_cost),
            step=1000.0,
            help="您采购或生产碳酸锂的成本价格"
        )
        
        # 存货量输入
        default_inventory = user_settings.get('default_inventory', 100.0)
        inventory = st.number_input(
            "存货数量 (吨)",
            min_value=0.0,
            max_value=10000.0,
            value=float(default_inventory),
            step=1.0,
            help="您当前持有的碳酸锂库存数量"
        )
        
        # 套保比例滑块
        default_ratio = user_settings.get('default_hedge_ratio', 0.8)

        hedge_ratio_percent = st.slider(
            "套保比例 (%)",
            min_value=0,
            max_value=100,
            value=int(default_ratio * 100),
            step=5,
            help="计划对冲的价格风险比例，100%表示完全对冲"
        )
        
        hedge_ratio = hedge_ratio_percent / 100
        
        # 高级选项

        with st.expander("高级选项"):
            margin_rate = st.slider(
                "保证金比例 (%)",
                min_value=5,
                max_value=30,
                value=15,
                step=1,
                help="期货交易保证金比例"
            ) / 100
            
            # 保存为默认设置选项
            if 'user_info' in st.session_state:
                save_defaults = st.checkbox("保存为默认设置", value=False)
                if save_defaults:
                    new_settings = {
                        'default_cost_price': float(cost_price),
                        'default_inventory': float(inventory),
                        'default_hedge_ratio': float(hedge_ratio)
                    }

                    if analyzer.auth.update_user_settings(st.session_state.user_info['user_id'], new_settings):
                        st.success("默认设置已保存")
        
        # 操作按钮

        auto_update = st.toggle("实时更新", value=True, help="拖动参数后自动刷新图表")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            calc_button = st.button(
                "开始计算", 
                type="primary", 
                use_container_width=True,
                help="基于当前参数计算套保方案"
            )
        
        with col_btn2:
            if st.button("刷新数据", use_container_width=True):
                st.session_state.force_refresh = True
                st.rerun()
        
        # 如果点击了计算按钮
        should_calculate = auto_update or calc_button
        if should_calculate:
            with st.spinner("正在获取最新数据并计算套保方案..."):
                fig, suggestions, metrics = analyzer.hedge_calculation(
                    cost_price, inventory, hedge_ratio, margin_rate
                )

                if fig is not None:
                    st.session_state.hedge_results = {
                        'fig': fig,
                        'suggestions': suggestions,
                        'metrics': metrics,
                        'params': {
                            'cost_price': cost_price,
                            'inventory': inventory,
                            'hedge_ratio': hedge_ratio,
                            'margin_rate': margin_rate
                        }
                    }
                else:
                    st.error("计算失败，请检查网络连接或稍后重试")
    
    with col_right:
        st.markdown("### 分析结果")
        st.markdown("---")
        
        # 检查是否有计算结果
        if 'hedge_results' in st.session_state:
            results = st.session_state.hedge_results
            metrics = results['metrics']
            params = results['params']
            
            # 显示数据来源和时间
            st.info(f"数据时间：{metrics['latest_date'].strftime('%Y-%m-%d')}")
            
            # 关键指标卡片
            col_metric1, col_metric2, col_metric3 = st.columns(3)
            
            with col_metric1:
                # 计算价格变化
                price_diff = metrics['current_price'] - params['cost_price']
                price_diff_pct = (price_diff / params['cost_price']) * 100 if params['cost_price'] > 0 else 0
                
                delta_color = "normal" if price_diff >= 0 else "inverse"
                st.metric(
                    label="当前市场价格",
                    value=f"{metrics['current_price']:,.0f}",
                    delta=f"{price_diff_pct:+.1f}%",
                    delta_color=delta_color,
                    help=f"较成本价{price_diff:+,.0f}元/吨"
                )
            

            with col_metric2:
                actual_ratio = metrics['hedge_contracts_int'] / params['inventory'] * 100 if params['inventory'] > 0 else 0
                st.metric(

                    label="建议套保手数",
                    value=f"{metrics['hedge_contracts_int']}",
                    delta=f"{actual_ratio:.1f}%",
                    help=f"基于{params['inventory']:,.1f}吨存货"
                )
            
            with col_metric3:
                st.metric(

                    label="所需保证金",
                    value=f"¥{metrics['total_margin']:,.0f}",
                    help=f"按{params['margin_rate']*100:.0f}%保证金比例"
                )
            
            # 显示图表
           
            st.markdown("#### 盈亏情景分析")
            st.pyplot(results['fig'])
            
            # 详细建议
            with st.expander("详细分析报告", expanded=True):
                st.markdown(results['suggestions'])
            
            # 导出功能
            st.markdown("#### 导出结果")
            col_export1, col_export2, col_export3 = st.columns(3)
            
            with col_export1:
                if st.button("保存到云端历史", use_container_width=True, 
                           help="将分析结果保存到云端历史记录"):
                    if 'user_info' in st.session_state:
                        st.success("分析结果已保存到云端历史记录")
                    else:
                        st.warning("请先登录以保存历史记录")
            
            with col_export2:
                # 生成文本报告
                actual_ratio_report = metrics['hedge_contracts_int'] / params['inventory'] * 100 if params['inventory'] > 0 else 0
                report_text = f"""碳酸锂套保分析报告
生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
用户：{st.session_state.user_info['username'] if 'user_info' in st.session_state else '游客'}
数据来源：akshare实时数据

=== 输入参数 ===
存货成本价：{params['cost_price']:,.2f} 元/吨
存货数量：{params['inventory']:,.2f} 吨
套保比例：{params['hedge_ratio']*100:.2f}%
保证金比例：{params['margin_rate']*100:.0f}%

=== 市场数据 ===
当前价格：{metrics['current_price']:,.2f} 元/吨
数据时间：{metrics['latest_date'].strftime('%Y-%m-%d')}

=== 套保方案 ===
理论套保手数：{params['inventory'] * params['hedge_ratio']:.2f} 手
实际套保手数：{metrics['hedge_contracts_int']} 手
实际套保比例：{actual_ratio_report:.2f}%
每手保证金：{metrics['current_price'] * params['margin_rate']:,.2f} 元
总保证金要求：{metrics['total_margin']:,.2f} 元

=== 盈亏分析 ===
当前每吨盈亏：{metrics['current_price'] - params['cost_price']:,.2f} 元
当前总盈亏：{metrics['current_profit']:,.2f} 元
盈亏比例：{metrics['profit_percentage']:.2f}%

=== 风险提示 ===
请根据自身风险承受能力调整套保策略。
期货交易存在风险，建议咨询专业人士。
本分析仅供参考，不构成投资建议。
"""
                
               
                st.download_button(
                    label="下载文本报告",
                    data=report_text,
                    file_name=f"套保分析报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    help="下载完整的分析报告文本文件"
                )
            
            with col_export3:
             
                if st.button("保存图表", use_container_width=True,
                           help="保存分析图表为PNG文件"):
                    import io
                    buf = io.BytesIO()
                    results['fig'].savefig(buf, format='png', dpi=300, bbox_inches='tight')
                    buf.seek(0)
                    
                   
                    st.download_button(
                        label="下载PNG图表",
                        data=buf,
                        file_name=f"套保分析图表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                        mime="image/png",
                        use_container_width=True
                    )
        
        else:
            # 如果没有计算结果，显示说明
            st.info("请在左侧输入参数并点击“开始计算”")
            
            # 显示示例
            with st.expander("参数说明"):
                st.markdown("""
                **参数解释**：
                
                1. **存货成本价**：您采购或生产碳酸锂的成本价格
                   - 示例：100,000元/吨
                   - 范围：0-500,000元/吨
                
                2. **存货数量**：您当前持有的碳酸锂库存量
                   - 示例：100吨
                   - 范围：0-10,000吨
                
               
                3. **套保比例**：您希望对冲的价格风险比例
                   - 0%：完全不套保，承担全部价格风险
                   - 50%：对冲一半的价格风险
                   - 100%：完全对冲价格风险
                
                4. **保证金比例**：期货交易所需的保证金比例
                   - 行业标准：10-20%
                   - 交易所可能根据市场情况调整
                
                **计算原理**：
                - 根据当前市场价格计算盈亏
                - 模拟未来价格变动情景（-50%到+100%）
                - 计算套保后的盈亏变化
                - 提供风险管理建议
                """)
    
    # 侧边栏信息

    with st.sidebar:
        st.markdown("### 实时市场概况")
        
        # 获取最新价格数据
        price_data = analyzer.fetch_real_time_data(force_refresh=st.session_state.force_refresh)
        if st.session_state.force_refresh:
            st.session_state.force_refresh = False
        
        if not price_data.empty:
            latest_price = price_data['收盘价'].iloc[-1]
            latest_date = price_data['日期'].iloc[-1]
            
            if '涨跌幅' in price_data.columns:
                price_change = price_data['涨跌幅'].iloc[-1]
            else:
                price_change = 0
            
            delta_color = "normal" if price_change >= 0 else "inverse"
            st.metric(
                label="碳酸锂期货价格",
                value=f"{latest_price:,.0f}",
                delta=f"{price_change:.2f}%" if price_change != 0 else None,
                delta_color=delta_color
            )
            st.caption(f"更新时间：{latest_date.strftime('%Y-%m-%d')}")
            
            # 近期价格走势
            st.markdown("#### 近期价格走势")
            fig_small, ax_small = plt.subplots(figsize=(8, 3))
            
            recent_data = price_data.tail(30)
            ax_small.plot(recent_data['日期'], recent_data['收盘价'], 'b-', linewidth=1.5)
            ax_small.fill_between(recent_data['日期'], recent_data['收盘价'].min(), 
                                 recent_data['收盘价'], alpha=0.1, color='blue')
            ax_small.set_title('30日价格走势', fontsize=10)
            ax_small.grid(True, alpha=0.3)
            plt.xticks(rotation=45, fontsize=8)
            plt.tight_layout()
            st.pyplot(fig_small)
            
            # 市场统计
            st.markdown("#### 市场统计")
            col_stat1, col_stat2 = st.columns(2)
            with col_stat1:
                st.metric("30日最高", f"{recent_data['收盘价'].max():,.0f}")
            with col_stat2:
                st.metric("30日最低", f"{recent_data['收盘价'].min():,.0f}")
        

        st.markdown("### 使用提示")
        st.markdown("""
        1. **实时数据**：所有计算基于最新市场数据
        2. **自动更新**：数据每30分钟自动缓存
        3. **手动刷新**：可点击"刷新数据"按钮
        4. **云端保存**：登录后自动保存分析历史
        5. **风险提示**：计算结果仅供参考
        """)


def render_price_page(analyzer):
    """渲染价格行情页面"""
    st.markdown("<h1>碳酸锂实时价格行情</h1>", unsafe_allow_html=True)
    
    # 数据控制栏
    col_control1, col_control2, col_control3, col_control4 = st.columns([2, 2, 1, 1])
    
    with col_control1:
        period = st.selectbox(
            "查看周期",
            ["最近1个月", "最近3个月", "最近6个月", "最近1年", "全部数据"],
            index=3,
            help="选择要查看的价格周期"
        )
    
    with col_control2:
        symbol = st.selectbox(
            "选择合约",
            ["LC0", "LC2401", "LC2402", "LC2403", "LC2404", "LC2405", "LC2406"],
            index=0,
            help="选择碳酸锂期货合约"
        )
    
    with col_control3:

        if st.button("刷新", use_container_width=True, 
                    help="强制刷新最新数据"):
            analyzer.cache_data = {}
            st.session_state.force_refresh = True
            st.rerun()
    
    with col_control4:
        show_stats = st.checkbox("显示统计", value=True)
    
    # 获取数据
    with st.spinner("正在加载实时价格数据..."):
        price_data = analyzer.fetch_real_time_data(symbol=symbol)
    
    if price_data.empty:
        st.error("无法获取价格数据，请检查网络连接或稍后重试")
        return
    
    # 根据周期筛选数据
    period_map = {
        "最近1个月": 30,
        "最近3个月": 90,
        "最近6个月": 180,
        "最近1年": 365,
        "全部数据": len(price_data)
    }
    
    days = period_map[period]
    if len(display_data) > 20:
        ma20 = display_data['收盘价'].rolling(window=20).mean()
        ax_main.plot(display_data['日期'], ma20, 'r--', 
                    linewidth=1.5, alpha=0.7, label='20日移动平均')
    
    if len(display_data) > 60:
        ma60 = display_data['收盘价'].rolling(window=60).mean()
        ax_main.plot(display_data['日期'], ma60, 'g--', 
                    linewidth=1.5, alpha=0.7, label='60日移动平均')
    
    ax_main.set_title(f'{symbol} {period}价格走势', fontsize=16, fontweight='bold')
    ax_main.set_xlabel('日期', fontsize=12)
    ax_main.set_ylabel('价格 (元/吨)', fontsize=12)
    ax_main.grid(True, alpha=0.3)
    ax_main.legend(fontsize=10)
    
    # 格式化y轴
    ax_main.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, pos: f'{x:,.0f}'))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig_main)
    
    # 统计信息
    if show_stats:
        with st.expander("详细统计信息", expanded=True):
            col_stat1, col_stat2 = st.columns(2)
            
            with col_stat1:
                st.markdown("#### 价格统计")
                stats_price = {
                    "最新价格": f"{latest_price:,.2f} 元/吨",
                    "期间最高": f"{display_data['收盘价'].max():,.2f} 元/吨",
                    "期间最低": f"{display_data['收盘价'].min():,.2f} 元/吨",
                    "平均价格": f"{display_data['收盘价'].mean():,.2f} 元/吨",
                    "价格中位数": f"{display_data['收盘价'].median():,.2f} 元/吨",
                    "价格标准差": f"{display_data['收盘价'].std():,.2f} 元/吨",
                    "价格波动率": f"{(display_data['收盘价'].std() / display_data['收盘价'].mean() * 100):.2f}%"
                }
                
                for key, value in stats_price.items():
                    st.text(f"{key}: {value}")
            
            with col_stat2:
                if '涨跌幅' in display_data.columns:
                    st.markdown("#### 涨跌幅统计")
                    returns = display_data['涨跌幅'].dropna()
                    
                    stats_returns = {
                        "平均日涨跌": f"{returns.mean():.2f}%",
                        "上涨天数": f"{(returns > 0).sum()} 天",
                        "下跌天数": f"{(returns < 0).sum()} 天",
                        "平盘天数": f"{(returns == 0).sum()} 天",
                        "最大单日涨幅": f"{returns.max():.2f}%",
                        "最大单日跌幅": f"{returns.min():.2f}%",
                        "上涨概率": f"{(returns > 0).sum() / len(returns) * 100:.1f}%"
                    }
                    
                    for key, value in stats_returns.items():
                        st.text(f"{key}: {value}")
    
    # 详细数据表格
    with st.expander("详细数据表格", expanded=False):
        display_data_formatted = display_data.copy()
        display_data_formatted['日期'] = display_data_formatted['日期'].dt.strftime('%Y-%m-%d')
        
        # 选择显示的列
        available_cols = ['日期', '收盘价', '开盘价', '最高价', '最低价', '涨跌幅', '成交量']
        display_cols = [col for col in available_cols if col in display_data_formatted.columns]
        
        st.dataframe(
            display_data_formatted[display_cols].style.format({
                '收盘价': '{:,.0f}',
                '开盘价': '{:,.0f}',
                '最高价': '{:,.0f}',
                '最低价': '{:,.0f}',
                '涨跌幅': '{:.2f}%',
                '成交量': '{:,.0f}'
            } if '成交量' in display_data_formatted.columns else {
                '收盘价': '{:,.0f}',
                '开盘价': '{:,.0f}',
                '最高价': '{:,.0f}',
                '最低价': '{:,.0f}',
                '涨跌幅': '{:.2f}%'
            }),
            use_container_width=True,
            height=400
        )
    # 数据导出功能
    st.markdown("---")
    st.markdown("### 数据导出")

    col_export1, col_export2, col_export3 = st.columns(3)

    with col_export1:
        csv_data = display_data.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="下载CSV数据",
            data=csv_data,
            file_name=f"碳酸锂价格_{symbol}_{period}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            help="下载当前显示的价格数据为CSV文件",
        )

    with col_export2:
        buf = io.BytesIO()
        fig_main.savefig(buf, format="png", dpi=300, bbox_inches="tight")
        buf.seek(0)
        st.download_button(
            label="保存图表为PNG",
            data=buf,
            file_name=f"碳酸锂价格图表_{symbol}_{period}_{datetime.now().strftime('%Y%m%d')}.png",
            mime="image/png",
            use_container_width=True,
            help="下载当前图表为PNG图片",
        )

    with col_export3:
        # 生成价格分析报告（文本）
        latest_price = float(display_data["收盘价"].iloc[-1]) if "收盘价" in display_data.columns and not display_data.empty else float("nan")
        price_vol = float(display_data["收盘价"].std() / max(display_data["收盘价"].mean(), 1e-9) * 100) if "收盘价" in display_data.columns and len(display_data) > 1 else 0.0

        report_text = f"""=== 碳酸锂价格分析报告 ===
标的：{symbol}
周期：{period}
数据条数：{len(display_data)}
最新价格：{latest_price:,.2f} 元/吨
期间最高：{display_data['收盘价'].max():,.2f} 元/吨
期间最低：{display_data['收盘价'].min():,.2f} 元/吨
期间均价：{display_data['收盘价'].mean():,.2f} 元/吨
价格波动率：{price_vol:.2f}%

"""

        if "涨跌幅" in display_data.columns:
            returns = display_data["涨跌幅"].dropna()
            if not returns.empty:
                report_text += f"""=== 涨跌统计 ===
平均日涨跌：{returns.mean():.2f}%
最大单日涨幅：{returns.max():.2f}%
最大单日跌幅：{returns.min():.2f}%
上涨天数：{int((returns > 0).sum())}
下跌天数：{int((returns < 0).sum())}

"""

        report_text += f"""报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        st.download_button(
            label="生成分析报告",
            data=report_text,
            file_name=f"碳酸锂分析报告_{symbol}_{period}_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True,
            help="生成并下载详细的价格分析报告",
        )

def render_basis_page(analyzer):
    """渲染基差走势页面"""
    st.markdown("<h1>基差走势</h1>", unsafe_allow_html=True)

    col_left, col_right = st.columns([2, 1])
    with col_left:
        symbol = st.selectbox(
            "选择期货主力合约",
            ["LC0", "LC2401", "LC2402", "LC2403", "LC2404", "LC2405", "LC2406"],
            index=0
        )
        period = st.selectbox(
            "查看周期",
            ["最近1个月", "最近3个月", "最近6个月", "最近1年"],
            index=2
        )

    with col_right:
        st.markdown("### 市场基准价")
        spot_price = st.number_input(
            "现货均价（SMM）",
            min_value=0.0,
            value=float(st.session_state.get("basis_spot_price", 235000.0)),
            step=500.0
        )
        st.session_state.basis_spot_price = spot_price

    period_map = {
        "最近1个月": 30,
        "最近3个月": 90,
        "最近6个月": 180,
        "最近1年": 365
    }

    price_data = analyzer.fetch_real_time_data(symbol=symbol)
    if price_data.empty:
        st.error("无法获取期货数据")
        return

    display_data = price_data.tail(period_map[period]).copy()
    display_data["基差"] = display_data["收盘价"] - spot_price

    latest_futures = float(display_data["收盘价"].iloc[-1])
    latest_basis = latest_futures - spot_price
    update_time = display_data["日期"].iloc[-1]

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("市场基准价（数据来源：SMM）", f"{spot_price:,.0f} 元/吨")
    col_m2.metric("期货基准价（SHFE主力）", f"{latest_futures:,.0f} 元/吨")
    col_m3.metric("实时基差", f"{latest_basis:+,.0f} 元/吨")

    st.caption(f"更新时间：{update_time.strftime('%Y-%m-%d %H:%M')}")

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(display_data["日期"], display_data["基差"], color="#0a84ff", linewidth=2.2)
    ax.axhline(0, color="#8e8e93", linestyle="--", linewidth=1)
    ax.set_title("基差走势（期货主力 - 现货均价）", fontsize=15, fontweight="bold")
    ax.set_xlabel("日期")
    ax.set_ylabel("基差 (元/吨)")
    ax.grid(True, alpha=0.3, linestyle="--")
    plt.xticks(rotation=30)
    plt.tight_layout()
    st.pyplot(fig)

    st.session_state.basis_data = {
        "spot_price": spot_price,
        "futures_price": latest_futures,
        "basis": latest_basis,
        "update_time": update_time
    }

    st.markdown("#### 数据说明")
    st.markdown(
        "市场基准价以SMM官方口径为准，期货基准价采用SHFE主力合约。"
        "基差用于检验套保有效性，仅供参考。"
    )
    st.info("价格指数以官方发布为准，本系统仅展示，不自行计算。")


def render_option_page(analyzer):
    """渲染期权保险计算页面"""
    st.markdown("<h1>价格保险（期权）计算</h1>", unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 2])

    with col_left:
        option_mode = st.radio(
            "方案类型",
            ["锁定最高买入价", "锁定最低卖出价"],
            index=0
        )
        target_price = st.number_input(
            "锁定价格 (元/吨)",
            min_value=0.0,
            value=250000.0,
            step=500.0
        )
        quantity = st.number_input(
            "保障数量 (吨)",
            min_value=0.0,
            value=100.0,
            step=1.0
        )
        months = st.number_input(
            "保障月数",
            min_value=1,
            max_value=24,
            value=3,
            step=1
        )
        with st.expander("高级参数"):
            volatility = st.slider("波动率（年化）", 0.05, 0.8, 0.35, 0.01)
            risk_free = st.slider("无风险利率（年化）", 0.0, 0.1, 0.02, 0.005)

    with col_right:
        price_data = analyzer.fetch_real_time_data()
        current_price = float(price_data["收盘价"].iloc[-1]) if not price_data.empty else target_price
        time_years = months / 12
        option_type = "call" if option_mode == "锁定最高买入价" else "put"
        premium_per_ton = black_scholes_price(
            option_type, current_price, target_price, time_years, risk_free, volatility
        )
        total_premium = premium_per_ton * quantity

        st.markdown("### 输出结果")
        st.metric("您需支付的总保费约为", f"{total_premium:,.0f} 元")
        st.caption(f"当前期货价格：{current_price:,.0f} 元/吨")

        scenario_prices = np.linspace(current_price * 0.7, current_price * 1.3, 60)
        if option_type == "call":
            no_insurance = scenario_prices
            futures_locked = np.full_like(scenario_prices, target_price)
            option_cost = np.minimum(scenario_prices, target_price) + premium_per_ton
            ylabel = "采购成本 (元/吨)"
        else:
            no_insurance = scenario_prices
            futures_locked = np.full_like(scenario_prices, target_price)
            option_cost = np.maximum(scenario_prices, target_price) - premium_per_ton
            ylabel = "销售收入 (元/吨)"

        fig, ax = plt.subplots(figsize=(11, 6))
        ax.plot(scenario_prices, no_insurance, color="#ff3b30", linewidth=2, label="不买保险")
        ax.plot(scenario_prices, futures_locked, color="#34c759", linewidth=2, label="买期货")
        ax.plot(scenario_prices, option_cost, color="#0a84ff", linewidth=2, label="买期权")
        ax.set_title("三种情景对比", fontsize=14, fontweight="bold")
        ax.set_xlabel("未来价格 (元/吨)")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend()
        plt.tight_layout()
        st.pyplot(fig)

        st.session_state.option_result = {
            "mode": option_mode,
            "target_price": target_price,
            "quantity": quantity,
            "months": months,
            "premium_total": total_premium,
            "premium_per_ton": premium_per_ton
        }

        st.markdown("#### 操作提示")
        st.markdown(
            "后台可接入Black-Scholes或交易所期权定价模型进行实时计算，"
            "当前结果为基于最新期货价格的估算值。"
        )


def render_exposure_page(analyzer):
    """渲染风险敞口量化页面"""
    st.markdown("<h1>风险敞口量化</h1>", unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 2])
    with col_left:
        future_purchase = st.number_input(
            "未来计划采购量 (吨)",
            min_value=0.0,
            value=200.0,
            step=1.0
        )
        inventory = st.number_input(
            "现有库存量 (吨)",
            min_value=0.0,
            value=100.0,
            step=1.0
        )
        locked_sales = st.number_input(
            "已锁定的量 (吨)",
            min_value=0.0,
            value=80.0,
            step=1.0
        )
        st.caption(
            "已锁定的量指已签订固定价格合同或完成点价交易的数量，与价格无关。"
        )

    total_exposure = future_purchase + inventory - locked_sales
    total_volume = future_purchase + inventory + locked_sales
    exposure_ratio = abs(total_exposure) / total_volume if total_volume > 0 else 0

    if exposure_ratio < 0.2:
        risk_level = "低"
    elif exposure_ratio < 0.5:
        risk_level = "中"
    else:
        risk_level = "高"

    risk_direction = "原材料价格上涨" if total_exposure > 0 else "原材料价格下跌" if total_exposure < 0 else "风险中性"
    risk_impact = total_exposure * 10000

    with col_right:
        st.markdown("### 量化结果")
        st.metric("风险敞口", f"{total_exposure:,.0f} 吨")
        st.metric("风险程度", risk_level)
        st.markdown(f"**风险方向**：{risk_direction}")
        st.markdown(f"**风险影响**：原材料价格每上涨一万元/吨，成本将变化 {risk_impact:,.0f} 元")

        fig, ax = plt.subplots(figsize=(6, 6))
        components = [future_purchase, inventory, locked_sales]
        labels = ["未来采购", "现有库存", "已锁定"]
        ax.pie(components, labels=labels, autopct="%1.1f%%", startangle=90)
        ax.set_title("敞口构成", fontsize=13, fontweight="bold")
        st.pyplot(fig)

        st.markdown("#### 策略建议")
        st.markdown("考虑买入套保或配置期权，减少价格波动对成本的冲击。")

    st.session_state.exposure_result = {
        "future_purchase": future_purchase,
        "inventory": inventory,
        "locked_sales": locked_sales,
        "exposure": total_exposure,
        "risk_level": risk_level,
        "risk_direction": risk_direction,
        "risk_impact": risk_impact
    }


def render_scenario_page(analyzer):
    """渲染多情景分析页面"""
    st.markdown("<h1>多情景分析</h1>", unsafe_allow_html=True)

    default_params = st.session_state.get("hedge_results", {}).get("params", {})
    cost_price = st.number_input(
        "存货成本价 (元/吨)",
        min_value=0.0,
        value=float(default_params.get("cost_price", 100000.0)),
        step=500.0
    )
    inventory = st.number_input(
        "存货数量 (吨)",
        min_value=0.0,
        value=float(default_params.get("inventory", 100.0)),
        step=1.0
    )
    hedge_ratio = st.slider(
        "套保比例 (%)",
        min_value=0,
        max_value=100,
        value=int(default_params.get("hedge_ratio", 0.8) * 100),
        step=5
    ) / 100

    scenario_options = {
        "价格上涨10%": 0.1,
        "价格平稳": 0.0,
        "价格下降10%": -0.1,
        "用户自设定": None
    }

    cols = st.columns(4)
    selected = st.session_state.get("scenario_selected", "价格上涨10%")
    for idx, (label, _) in enumerate(scenario_options.items()):
        if cols[idx].button(label):
            selected = label
            st.session_state.scenario_selected = label

    if selected == "用户自设定":
        custom_pct = st.number_input("自设定变动 (%)", value=5.0, step=1.0)
        custom_change = custom_pct / 100
    else:
        custom_change = scenario_options[selected]

    price_data = analyzer.fetch_real_time_data()
    current_price = float(price_data["收盘价"].iloc[-1]) if not price_data.empty else cost_price
    hedge_contracts = int(np.round(inventory * hedge_ratio))

    scenarios = {
        "上涨10%": 0.1,
        "平稳": 0.0,
        "下降10%": -0.1,
        "自设定": custom_change
    }

    rows = []
    for name, change in scenarios.items():
        scenario_price = current_price * (1 + change)
        spot_profit = (scenario_price - cost_price) * inventory
        futures_profit = (current_price - scenario_price) * hedge_contracts
        hedge_profit = spot_profit + futures_profit
        rows.append({
            "情景": name,
            "价格变动": f"{change*100:+.1f}%",
            "不套保盈亏(元)": f"{spot_profit:,.0f}",
            "套保后盈亏(元)": f"{hedge_profit:,.0f}"
        })

    result_df = pd.DataFrame(rows)
    st.markdown("### 情景结果汇总")
    st.dataframe(result_df, use_container_width=True)

    st.session_state.scenario_results = rows


def render_report_page(analyzer):
    """渲染分析报告页面"""
    st.markdown("<h1>分析报告</h1>", unsafe_allow_html=True)

    basis_data = st.session_state.get("basis_data")
    if not basis_data:
        price_data = analyzer.fetch_real_time_data()
        latest_futures = float(price_data["收盘价"].iloc[-1]) if not price_data.empty else 0
        spot_price = st.number_input("现货参考价 (元/吨)", min_value=0.0, value=235000.0, step=500.0)
        basis_value = latest_futures - spot_price
        update_time = price_data["日期"].iloc[-1] if not price_data.empty else datetime.now()
        basis_data = {
            "spot_price": spot_price,
            "futures_price": latest_futures,
            "basis": basis_value,
            "update_time": update_time
        }

    exposure_result = st.session_state.get("exposure_result")
    scenario_results = st.session_state.get("scenario_results", [])

    st.markdown("### 1. 当前市场概况")
    st.markdown(
        f"- 日期：{basis_data['update_time'].strftime('%Y-%m-%d')}\n"
        f"- 现货价：{basis_data['spot_price']:,.0f} 元/吨\n"
        f"- 期货价：{basis_data['futures_price']:,.0f} 元/吨\n"
        f"- 基差：{basis_data['basis']:+,.0f} 元/吨\n"
        f"- 数据来源：SMM（现货）/ SHFE主力（期货）"
    )

    st.markdown("### 2. 风险敞口计算结果")
    if exposure_result:
        st.markdown(
            f"- 风险敞口：{exposure_result['exposure']:,.0f} 吨\n"
            f"- 风险方向：{exposure_result['risk_direction']}\n"
            f"- 风险程度：{exposure_result['risk_level']}\n"
            f"- 风险影响：每上涨1万元/吨，成本变化 {exposure_result['risk_impact']:,.0f} 元"
        )
    else:
        st.info("请先在“风险敞口”模块完成测算。")

    st.markdown("### 3. 情景指标对比")
    if scenario_results:
        scenario_df = pd.DataFrame(scenario_results)
        st.dataframe(scenario_df, use_container_width=True)
    else:
        st.info("请先在“多情景分析”模块生成对比结果。")

    st.markdown("### 4. 风险提示与建议")
    st.markdown(
        "- 基差扩大时需关注套保效率变化。\n"
        "- 结合敞口方向优先选择期货或期权锁定风险。\n"
        "- 如需精细报告，可导出当前页面内容并补充业务说明。"
    )

    report_text = f"""分析报告
生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

1. 当前市场概况
日期：{basis_data['update_time'].strftime('%Y-%m-%d')}
现货价：{basis_data['spot_price']:,.0f} 元/吨
期货价：{basis_data['futures_price']:,.0f} 元/吨
基差：{basis_data['basis']:+,.0f} 元/吨
数据来源：SMM（现货）/ SHFE主力（期货）

2. 风险敞口计算结果
"""
    if exposure_result:
        report_text += (
            f"风险敞口：{exposure_result['exposure']:,.0f} 吨\n"
            f"风险方向：{exposure_result['risk_direction']}\n"
            f"风险程度：{exposure_result['risk_level']}\n"
            f"风险影响：每上涨1万元/吨，成本变化 {exposure_result['risk_impact']:,.0f} 元\n"
        )
    else:
        report_text += "风险敞口：未填写\n"

    report_text += "\n3. 情景指标对比\n"
    if scenario_results:
        for row in scenario_results:
            report_text += (
                f"{row['情景']} | {row['价格变动']} | 不套保盈亏 {row['不套保盈亏(元)']} | "
                f"套保后盈亏 {row['套保后盈亏(元)']}\n"
            )
    else:
        report_text += "未生成情景分析\n"

    report_text += "\n4. 风险提示与建议\n"
    report_text += (
        "基差扩大时需关注套保效率变化；结合敞口方向选择期货或期权；"
        "如需精细报告，可补充业务说明。\n"
    )

    st.download_button(
        label="下载分析报告",
        data=report_text,
        file_name=f"分析报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain",
        use_container_width=True
    )


def render_history_page(analyzer):
    """渲染分析历史页面"""
    st.markdown("<h1>分析历史记录</h1>", unsafe_allow_html=True)
    
    # 获取用户历史记录
    with st.spinner("正在加载分析历史..."):
        history = analyzer.get_user_history(limit=50)
    
    if not history:
        st.info("暂无分析历史记录")
        st.markdown("""
        ### 开始您的第一次分析
        
        1. 前往 **套保计算** 页面
        2. 输入您的存货参数
        3. 点击 **开始计算**
        4. 分析结果将自动保存到历史记录
        
        所有分析记录都会安全存储在云端，您可以随时查看和导出。
        """)
        return
    
    # 显示历史记录统计
    total_analyses = len(history)
    latest_analysis = history[0]['created_at'] if history else None
    
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("总分析次数", f"{total_analyses}")
    with col_stat2:
        if latest_analysis:
            from dateutil import parser
            latest_time = parser.parse(latest_analysis)
            time_diff = datetime.now() - latest_time.replace(tzinfo=None)
            if time_diff.days > 0:
                latest_str = f"{time_diff.days}天前"
            elif time_diff.seconds > 3600:
                latest_str = f"{time_diff.seconds // 3600}小时前"
            else:
                latest_str = f"{time_diff.seconds // 60}分钟前"
            st.metric("最近分析", latest_str)
    
    # 历史记录列表
    st.markdown("### 历史记录列表")
    
    for i, record in enumerate(history):
        with st.expander(f"分析 #{total_analyses - i} - {record['created_at'][:19]}", expanded=(i == 0)):
            col_record1, col_record2, col_record3 = st.columns([3, 2, 1])
            
            with col_record1:
                st.markdown(f"**分析类型**：{record['analysis_type']}")
                if 'input_params' in record and isinstance(record['input_params'], dict):
                    st.markdown("**输入参数**：")
                    for key, value in record['input_params'].items():
                        if key == 'cost_price':
                            st.text(f"  - 成本价：{value:,.2f} 元/吨")
                        elif key == 'inventory':
                            st.text(f"  - 存货量：{value:,.2f} 吨")
                        elif key == 'hedge_ratio':
                            st.text(f"  - 套保比例：{value*100:.1f}%")
                        elif key == 'margin_rate':
                            st.text(f"  - 保证金比例：{value*100:.0f}%")
            
            with col_record2:
                if 'result_data' in record and isinstance(record['result_data'], dict):
                    st.markdown("**分析结果**：")
                    result = record['result_data']
                    if 'current_price' in result:
                        st.text(f"  - 当时价格：{result['current_price']:,.0f}元")
                    if 'hedge_contracts' in result:
                        st.text(f"  - 建议手数：{result['hedge_contracts']}手")
                    if 'total_margin' in result:
                        st.text(f"  - 保证金：{result['total_margin']:,.0f}元")
                    if 'profit_status' in result:
                        profit_color = "green" if result['profit_status'] == '盈利' else "red"
                        st.markdown(f"  - 盈亏状态：<span style='color:{profit_color}'>{result['profit_status']}</span>", 
                                  unsafe_allow_html=True)
            
            with col_record3:
                analysis_id = record['analysis_id']
                if st.button("删除", key=f"delete_{analysis_id}", 
                           help="删除此条记录"):
                    if analyzer.delete_history_record(analysis_id):
                        st.success("记录已删除")
                        st.rerun()
                    else:
                        st.error("删除失败")
                
                # 重新分析按钮
                if 'input_params' in record and isinstance(record['input_params'], dict):
                    if st.button("重新分析", key=f"recalc_{analysis_id}"):
                        st.session_state.recalc_params = record['input_params']
                        st.session_state.current_page = "套保计算"
                        st.rerun()
    
    # 批量操作
    st.markdown("---")
    st.markdown("### 批量操作")
    
    col_batch1, col_batch2, col_batch3 = st.columns(3)
    
    with col_batch1:
        if st.button("导出所有记录", use_container_width=True):
            # 导出所有历史记录为JSON
            export_data = {
                "export_time": datetime.now().isoformat(),
                "user": st.session_state.user_info['username'] if 'user_info' in st.session_state else "未知用户",
                "total_records": len(history),
                "history": history
            }
            
            json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
            st.download_button(
                label="下载JSON文件",
                data=json_str,
                file_name=f"套保分析历史_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
    
    with col_batch2:
        if st.button("清空所有记录", use_container_width=True, type="secondary"):
            st.warning("此操作将删除所有历史记录，且不可恢复！")
            confirm = st.checkbox("我确认要删除所有记录")
            if confirm and st.button("确认删除", type="primary"):
                # 这里需要实现批量删除功能
                st.error("批量删除功能开发中")
                # for record in history:
                #     analyzer.delete_history_record(record['analysis_id'])
                # st.success("所有记录已删除")
                # st.rerun()
    
    with col_batch3:
        if st.button("刷新列表", use_container_width=True):
            st.rerun()


def render_settings_page(analyzer):
    """渲染账号设置页面"""
    st.markdown("<h1>账号设置</h1>", unsafe_allow_html=True)
    
    user_info = st.session_state.user_info
    
    tab1, tab2, tab3, tab4 = st.tabs(["账户信息", "修改密码", "偏好设置", "数据管理"])
    
    with tab1:
        st.markdown("### 账户信息")
        
        if user_info:
            col_info1, col_info2 = st.columns(2)
            
            with col_info1:
                st.markdown(f"**用户名**：{user_info['username']}")
                st.markdown(f"**邮箱**：{user_info['email']}")
                st.markdown(f"**用户ID**：`{user_info['user_id']}`")
            
            with col_info2:
                if 'settings' in user_info and user_info['settings']:
                    settings = user_info['settings']
                    st.markdown("**账户状态**：正常")
                    st.markdown(f"**会员等级**：{settings.get('subscription_tier', '免费版')}")
                    st.markdown(f"**注册时间**：{settings.get('created_at', '未知')[:10]}")
                else:
                    st.markdown("**账户状态**：设置未加载")
        
        # 账户操作
        st.markdown("### 账户操作")
        
        col_action1, col_action2 = st.columns(2)
        
        with col_action1:
            if st.button("刷新账户信息", use_container_width=True):
                # 重新加载用户信息
                if analyzer.supabase and 'user_info' in st.session_state:
                    settings = analyzer.supabase.get_user_settings(st.session_state.user_info['user_id'])
                    if settings:
                        st.session_state.user_info['settings'] = settings
                        st.success("账户信息已刷新")
                        st.rerun()
        
        with col_action2:
            if st.button("导出账户数据", use_container_width=True):
                export_data = {
                    "user_info": user_info,
                    "export_time": datetime.now().isoformat()
                }
                
                json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
                st.download_button(
                    label="下载账户数据",
                    data=json_str,
                    file_name=f"账户数据_{user_info['username']}_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json",
                    use_container_width=True
                )
    
    with tab2:
        st.markdown("### 修改密码")
        
        old_password = st.text_input("当前密码", type="password", 
                                   help="请输入当前使用的密码")
        new_password = st.text_input("新密码", type="password", 
                                   help="至少6个字符，建议包含字母和数字")
        confirm_password = st.text_input("确认新密码", type="password")
        
        # 密码强度检查
        if new_password:
            has_letter = any(c.isalpha() for c in new_password)
            has_digit = any(c.isdigit() for c in new_password)
            length_ok = len(new_password) >= 6
            
            if length_ok and (has_letter and has_digit):
                strength = "强"
                color = "green"
            elif length_ok and (has_letter or has_digit):
                strength = "中"
                color = "orange"
            else:
                strength = "弱"
                color = "red"
            
            st.markdown(f"密码强度：<span style='color:{color};font-weight:bold'>{strength}</span>", 
                      unsafe_allow_html=True)
        
        if st.button("确认修改密码", type="primary", use_container_width=True):
            if not all([old_password, new_password, confirm_password]):
                st.error("请填写所有字段")
            elif new_password != confirm_password:
                st.error("两次输入的新密码不一致")
            elif len(new_password) < 6:
                st.error("密码长度至少6位")
            elif old_password == new_password:
                st.error("新密码不能与旧密码相同")
            else:
                success, message = analyzer.auth.change_password(
                    user_info['username'], old_password, new_password
                )
                if success:
                    st.success(message)
                    st.info("请使用新密码重新登录")
                else:
                    st.error(message)
    
    with tab3:
        st.markdown("### 偏好设置")
        
        if 'settings' in user_info and user_info['settings']:
            settings = user_info['settings']
            
            # 默认参数设置
            st.markdown("#### 默认计算参数")
            
            default_cost = st.number_input(
                "默认成本价 (元/吨)",
                min_value=0.0,
                max_value=500000.0,
                value=float(settings.get('default_cost_price', 100000.0)),
                step=1000.0
            )
            
            default_inventory = st.number_input(
                "默认存货量 (吨)",
                min_value=0.0,
                max_value=10000.0,
                value=float(settings.get('default_inventory', 100.0)),
                step=1.0
            )
            

            default_ratio = st.slider(
                "默认套保比例 (%)",
                min_value=0,
                max_value=100,
                value=int(settings.get('default_hedge_ratio', 0.8) * 100),
                step=5
            )
            
            # 主题颜色
            theme_color = st.selectbox(
                "主题颜色",
                ["blue", "green", "purple", "orange", "red"],
                index=["blue", "green", "purple", "orange", "red"].index(
                    settings.get('theme_color', 'blue')
                )
            )
            
            if st.button("保存设置", type="primary", use_container_width=True):
                new_settings = {
                    'default_cost_price': float(default_cost),
                    'default_inventory': float(default_inventory),
                    'default_hedge_ratio': float(default_ratio) / 100,
                    'theme_color': theme_color
                }
                
                if analyzer.auth.update_user_settings(user_info['user_id'], new_settings):
                    st.success("偏好设置已保存")
                    st.session_state.user_info['settings'] = new_settings
                else:
                    st.error("保存设置失败")
        else:
            st.info("正在加载用户设置...")
    
    with tab4:
        st.markdown("### 数据管理")
        
        st.markdown("#### 本地缓存")
        col_cache1, col_cache2 = st.columns(2)
        
        with col_cache1:
            if st.button("清除本地缓存", use_container_width=True, 
                        help="清除本地缓存的价格数据"):
                analyzer.cache_data = {}
                analyzer.cache_time = {}
                st.success("本地缓存已清除")
        
        with col_cache2:
            if st.button("查看缓存状态", use_container_width=True):
                cache_count = len(analyzer.cache_data)
                st.info(f"当前缓存了 {cache_count} 个数据集的 {sum(len(df) for df in analyzer.cache_data.values())} 条记录")
        
        st.markdown("#### 数据导出")
        
        # 导出所有分析历史
        history = analyzer.get_user_history(limit=1000)
        if history:
            export_all = {
                "user": user_info['username'],
                "export_time": datetime.now().isoformat(),
                "total_records": len(history),
                "records": history
            }
            
            json_str = json.dumps(export_all, ensure_ascii=False, indent=2)
            st.download_button(
                label="导出所有历史记录",
                data=json_str,
                file_name=f"套保分析完整历史_{user_info['username']}_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
                use_container_width=True
            )
        else:
            st.info("暂无历史记录可导出")
        
        st.markdown("#### 账户操作")
        
        if st.button("注销账户", type="secondary", use_container_width=True):
            st.warning("此操作将删除您的所有数据，且不可恢复！")
            confirm = st.checkbox("我确认要注销账户")
            if confirm:
                st.error("账户注销功能开发中")
                # 这里需要实现账户删除功能
    
    # 退出登录按钮
    st.markdown("---")
    col_logout1, col_logout2, col_logout3 = st.columns([1, 2, 1])
    
    with col_logout2:
        if st.button("退出登录", type="primary", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_info = None
            st.success("已退出登录")
            st.rerun()

# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    # 创建必要的目录
    os.makedirs('data', exist_ok=True)
    os.makedirs('charts', exist_ok=True)
    
    # 运行应用
    try:
        main()
    except Exception as e:
        st.error(f"应用程序运行出错: {str(e)}")
        st.code(traceback.format_exc())
        st.info("请检查：\n1. 网络连接\n2. 环境变量配置\n3. 依赖包安装")

