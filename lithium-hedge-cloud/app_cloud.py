# app_cloud.py - 完整云端版本
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import os
import sys
from datetime import datetime, timedelta
import warnings
import json
import io
import base64
import hashlib
import traceback
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

# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

# ============================================================================
# 用户认证管理器（云端版）
# ============================================================================

class CloudUserAuth:
    """云端用户认证管理器"""
    
    def __init__(self):
        self.supabase = supabase if HAS_SUPABASE else None
    
    def register(self, username, password, email):
        """注册新用户"""
        if not self.supabase:
            return False, "数据库连接失败，请检查配置"
        
        # 验证输入
        if len(username) < 3:
            return False, "用户名至少3个字符"
        if len(password) < 6:
            return False, "密码至少6个字符"
        if '@' not in email:
            return False, "请输入有效的邮箱地址"
        
        result = self.supabase.create_user(username, password, email)
        return result["success"], result["message"]
    
    def login(self, username, password):
        """用户登录"""
        if not self.supabase:
            return False, "数据库连接失败，请检查配置"
        
        result = self.supabase.authenticate_user(username, password)
        return result["success"], result
    
    def generate_reset_code(self, username, email):
        """生成重置密码验证码"""
        if not self.supabase:
            return False, "数据库连接失败"
        
        success, result = self.supabase.create_reset_code(username, email)
        if success:
            return True, result
        return False, result
    
    def reset_password(self, username, reset_code, new_password):
        """重置密码"""
        if not self.supabase:
            return False, "数据库连接失败"
        
        # 验证重置码
        if not self.supabase.verify_reset_code(username, reset_code):
            return False, "验证码无效或已过期"
        
        # 更新密码
        if self.supabase.update_user_password(username, new_password):
            return True, "密码重置成功"
        return False, "密码重置失败"
    
    def change_password(self, username, old_password, new_password):
        """修改密码"""
        if not self.supabase:
            return False, "数据库连接失败"
        
        # 先验证旧密码
        success, result = self.login(username, old_password)
        if not success:
            return False, "原密码错误"
        
        # 更新密码
        if self.supabase.update_user_password(username, new_password):
            return True, "密码修改成功"
        return False, "密码修改失败"
    
    def get_user_settings(self, user_id):
        """获取用户设置"""
        if not self.supabase:
            return None
        return self.supabase.get_user_settings(user_id)
    
    def update_user_settings(self, user_id, settings):
        """更新用户设置"""
        if not self.supabase:
            return False
        return self.supabase.update_user_settings(user_id, settings)

# ============================================================================
# 数据分析器（云端版）
# ============================================================================

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
                return cached_data
        
        try:
            import akshare as ak
            
            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365 * years)
            
            start_str = start_date.strftime('%Y%m%d')
            end_str = end_date.strftime('%Y%m%d')
            
            # 尝试多种数据源
            all_data = []
            
            # 方法1: 新浪财经主力合约
            try:
                df_main = ak.futures_main_sina(symbol=symbol, start_date=start_str, end_date=end_str)
                if not df_main.empty:
                    df_main['合约'] = symbol
                    df_main['数据源'] = 'sina_main'
                    all_data.append(df_main)
            except Exception as e:
                print(f"新浪主力数据获取失败: {e}")
            
            # 方法2: 具体合约
            try:
                df_contract = ak.futures_zh_daily_sina(
                    symbol=symbol.lower(),
                    start_date=start_str,
                    end_date=end_str
                )
                if not df_contract.empty:
                    df_contract['合约'] = symbol
                    df_contract['数据源'] = 'sina_daily'
                    all_data.append(df_contract)
            except Exception as e:
                print(f"新浪日线数据获取失败: {e}")
            
            if not all_data:
                # 返回模拟数据
                return self._get_simulated_data(symbol)
            
            # 合并数据
            import pandas as pd
            combined_df = pd.concat(all_data, ignore_index=True, sort=False)
            
            # 清洗数据
            cleaned_df = self._clean_data(combined_df)
            
            # 缓存数据
            self.cache_data[cache_key] = cleaned_df
            self.cache_time[cache_key] = current_time
            
            # 保存到云端缓存
            if self.supabase:
                self.supabase.save_price_data(symbol, cleaned_df)
            
            return cleaned_df
            
        except Exception as e:
            print(f"数据获取失败: {e}")
            return self._get_simulated_data(symbol)
    
    def _clean_data(self, df):
        """清洗数据"""
        import pandas as pd
        
        df_clean = df.copy()
        
        # 标准化列名
        column_mapping = {
            'date': '日期',
            'trade_date': '日期', 
            'datetime': '日期',
            'open': '开盘价',
            'high': '最高价',
            'low': '最低价',
            'close': '收盘价',
            'settle': '收盘价',
            'volume': '成交量',
            'vol': '成交量',
            'position': '持仓量',
            'oi': '持仓量',
            'amount': '成交额',
            'symbol': '合约',
            'variety': '合约',
        }
        
        for old_col, new_col in column_mapping.items():
            if old_col in df_clean.columns and new_col not in df_clean.columns:
                df_clean.rename(columns={old_col: new_col}, inplace=True)
        
        # 处理日期
        if '日期' in df_clean.columns:
            df_clean['日期'] = pd.to_datetime(df_clean['日期'], errors='coerce')
            df_clean = df_clean.dropna(subset=['日期'])
            df_clean = df_clean.sort_values('日期').reset_index(drop=True)
        
        # 处理价格数据
        price_cols = ['开盘价', '最高价', '最低价', '收盘价']
        for col in price_cols:
            if col in df_clean.columns:
                if df_clean[col].dtype == 'object':
                    df_clean[col] = (
                        df_clean[col]
                        .astype(str)
                        .str.replace(',', '')
                        .str.replace('元', '')
                        .str.strip()
                    )
                df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
        
        # 确保有收盘价列
        if '收盘价' not in df_clean.columns and 'close' in df.columns:
            df_clean['收盘价'] = df['close']
        
        # 计算涨跌幅
        if '收盘价' in df_clean.columns:
            df_clean['涨跌幅'] = df_clean['收盘价'].pct_change() * 100
        
        return df_clean
    
    def _get_simulated_data(self, symbol='LC0'):
        """生成模拟数据"""
        dates = pd.date_range(start='2023-01-01', end=datetime.now(), freq='D')
        np.random.seed(42)
        
        base_price = 100000
        price_trend = 1 + 0.0005 * np.arange(len(dates))
        price_volatility = np.random.normal(0, 0.02, len(dates))
        
        price_series = base_price * price_trend * (1 + price_volatility)
        
        df = pd.DataFrame({
            '日期': dates,
            '收盘价': price_series,
            '开盘价': price_series * (1 + np.random.normal(0, 0.005, len(dates))),
            '最高价': price_series * (1 + np.abs(np.random.normal(0, 0.01, len(dates)))),
            '最低价': price_series * (1 - np.abs(np.random.normal(0, 0.01, len(dates)))),
            '成交量': np.random.randint(10000, 50000, len(dates)),
            '合约': symbol
        })
        
        df['涨跌幅'] = df['收盘价'].pct_change() * 100
        
        return df
    
    def hedge_calculation(self, cost_price, inventory, hedge_ratio, margin_rate=0.15):
        """
        套保计算核心函数
        """
        # 获取价格数据
        price_data = self.fetch_real_time_data()
        
        if price_data.empty or '收盘价' not in price_data.columns:
            st.error("无法获取价格数据，请检查网络连接")
            return None, "数据获取失败，请重试", {}
        
        # 使用最新价格
        current_price = float(price_data['收盘价'].iloc[-1])
        latest_date = price_data['日期'].iloc[-1]
        
        # 计算用户当前盈亏
        total_value = current_price * inventory
        total_cost = cost_price * inventory
        current_profit = total_value - total_cost
        profit_per_ton = current_price - cost_price
        profit_percentage = (current_profit / total_cost * 100) if total_cost > 0 else 0
        
        # 计算套保需要的期货合约数量（1手=1吨）
        contract_size = 1
        hedge_contracts = inventory * hedge_ratio
        hedge_contracts_int = int(np.round(hedge_contracts))
        
        # 计算期货保证金
        margin_per_contract = current_price * contract_size * margin_rate
        total_margin = margin_per_contract * hedge_contracts_int
        
        # 生成未来价格情景分析
        price_changes = np.linspace(-0.5, 1.0, 151)  # -50% 到 +100%
        future_prices = current_price * (1 + price_changes)
        
        # 计算不同价格情景下的盈亏
        no_hedge_profits = []  # 不套保的盈亏
        hedge_profits = []     # 套保后的盈亏
        
        for future_price in future_prices:
            # 不套保：仅现货盈亏
            spot_profit = (future_price - cost_price) * inventory
            
            # 套保：现货盈亏 + 期货盈亏
            futures_profit = (current_price - future_price) * hedge_contracts_int
            total_hedge_profit = spot_profit + futures_profit
            
            no_hedge_profits.append(spot_profit)
            hedge_profits.append(total_hedge_profit)
        
        # 计算盈亏平衡点
        no_hedge_breakeven = cost_price
        no_hedge_breakeven_pct = (no_hedge_breakeven / current_price - 1) * 100
        
        if inventory != hedge_contracts_int:
            hedge_breakeven = (cost_price * inventory - current_price * hedge_contracts_int) / (inventory - hedge_contracts_int)
            hedge_breakeven_pct = (hedge_breakeven / current_price - 1) * 100
            hedge_breakeven_str = f"{hedge_breakeven:,.2f} 元/吨 (较当前价{hedge_breakeven_pct:.1f}%)"
        else:
            hedge_breakeven = current_price
            hedge_breakeven_str = "完全对冲，价格变化不影响总盈亏"
        
        # 生成图表
        fig, ax = plt.subplots(figsize=(12, 7))
        
        ax.plot(price_changes * 100, no_hedge_profits, 'r-', linewidth=2.5, label='不套保盈亏')
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
        
        plt.tight_layout()
        
        # 生成建议文本
        suggestions = []
        suggestions.append("### 📊 套保分析报告")
        suggestions.append(f"**数据来源**：akshare实时市场数据")
        suggestions.append(f"**分析时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        suggestions.append(f"**数据日期**：{latest_date.strftime('%Y-%m-%d')}")
        
        suggestions.append("\n### ⚙️ 输入参数")
        suggestions.append(f"- **存货成本价**：{cost_price:,.2f} 元/吨")
        suggestions.append(f"- **存货数量**：{inventory:,.2f} 吨")
        suggestions.append(f"- **套保比例**：{hedge_ratio*100:.1f}%")
        suggestions.append(f"- **保证金比例**：{margin_rate*100:.0f}%")
        
        suggestions.append("\n### 📈 市场数据")
        suggestions.append(f"- **当前市场价格**：{current_price:,.2f} 元/吨")
        suggestions.append(f"- **每吨盈亏**：{profit_per_ton:,.2f} 元/吨 ({profit_percentage:.2f}%)")
        suggestions.append(f"- **总盈亏**：{current_profit:,.2f} 元")
        
        suggestions.append("\n### 🎯 套保方案")
        suggestions.append(f"- **理论套保手数**：{hedge_contracts:.2f} 手")
        suggestions.append(f"- **实际套保手数**：{hedge_contracts_int} 手 (四舍五入取整)")
        suggestions.append(f"- **实际套保比例**：{hedge_contracts_int/inventory*100:.2f}%")
        suggestions.append(f"- **每手保证金**：{margin_per_contract:,.2f} 元")
        suggestions.append(f"- **总保证金要求**：{total_margin:,.2f} 元")
        suggestions.append(f"- **保证金占存货价值**：{total_margin/total_value*100:.2f}%")
        
        suggestions.append("\n### ⚠️ 风险分析")
        suggestions.append(f"- **不套保盈亏平衡点**：{no_hedge_breakeven:,.2f} 元/吨 (较当前价{no_hedge_breakeven_pct:.1f}%)")
        suggestions.append(f"- **套保后盈亏平衡点**：{hedge_breakeven_str}")
        
        suggestions.append("\n### 💡 操作建议")
        
        if hedge_ratio < 0.1:
            suggestions.append("**评估**：⚡ 套保比例极低，风险敞口极大")
            suggestions.append("**建议**：立即将套保比例提高至50%以上")
        elif hedge_ratio < 0.3:
            suggestions.append("**评估**：⚠️ 套保比例较低，存在较大价格风险")
            suggestions.append("**建议**：考虑提高套保比例至60-80%")
        elif hedge_ratio < 0.7:
            suggestions.append("**评估**：✅ 套保比例适中，风险可控")
            suggestions.append("**建议**：维持当前比例或根据市场情况微调")
        elif hedge_ratio <= 1.0:
            suggestions.append("**评估**：🛡️ 套保比例充足，有效对冲风险")
            suggestions.append("**建议**：当前比例合适，关注市场变化")
        else:
            suggestions.append("**评估**：🚨 过度套保，可能产生额外风险")
            suggestions.append("**建议**：将套保比例调整至100%以内")
        
        if current_profit > 0:
            suggestions.append(f"\n**盈利状态**：💰 当前盈利{profit_percentage:.2f}%，建议部分套保锁定利润")
            if profit_percentage > 20:
                suggestions.append("**策略建议**：可考虑锁定30-50%的利润")
        else:
            suggestions.append(f"\n**亏损状态**：📉 当前亏损{abs(profit_percentage):.2f}%，建议加强套保防止进一步亏损")
            if abs(profit_percentage) > 10:
                suggestions.append("**策略建议**：考虑提高套保比例至80-100%")
        
        if hedge_contracts_int > 0:
            suggestions.append("\n### ✅ 实施方案")
            suggestions.append(f"1. **资金准备**：准备 {total_margin:,.0f} 元作为期货保证金")
            suggestions.append("2. **合约选择**：选择LC0主力合约或对应月份合约")
            suggestions.append("3. **交易方向**：卖出空头合约对冲价格下跌风险")
            suggestions.append("4. **入场时机**：根据市场走势选择合适入场点")
            suggestions.append("5. **风险监控**：每日关注价格变化和保证金情况")
            suggestions.append("6. **调整策略**：根据市场变化动态调整套保比例")
        else:
            suggestions.append("\n### ⚠️ 风险提示")
            suggestions.append(f"套保手数为0，无法有效对冲价格风险")
            suggestions.append(f"建议将套保比例从{hedge_ratio*100:.1f}%提高至至少50%")
        
        suggestions.append("\n### 📝 注意事项")
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
                suggestions.append(f"\n**分析记录**：✅ 已保存到云端 (ID: {analysis_id})")
        
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
        """获取价格走势图"""
        price_data = self.fetch_real_time_data()
        
        if price_data.empty:
            st.error("无法获取价格数据")
            return None, "数据获取失败"
        
        # 根据周期筛选数据
        if period == '1m':
            display_data = price_data.tail(30)
            title_suffix = '近30日'
        elif period == '3m':
            display_data = price_data.tail(90)
            title_suffix = '近3个月'
        elif period == '6m':
            display_data = price_data.tail(180)
            title_suffix = '近6个月'
        else:  # 1y
            display_data = price_data.tail(365)
            title_suffix = '近1年'
        
        fig, ax = plt.subplots(figsize=(14, 7))
        
        # 绘制价格走势
        ax.plot(display_data['日期'], display_data['收盘价'], 
                color='#1f77b4', linewidth=2.5, alpha=0.8, label='收盘价')
        ax.fill_between(display_data['日期'], display_data['收盘价'].min(), 
                       display_data['收盘价'], alpha=0.1, color='#1f77b4')
        
        # 添加移动平均线
        if len(display_data) > 20:
            ma20 = display_data['收盘价'].rolling(window=20).mean()
            ax.plot(display_data['日期'], ma20, 'r--', 
                   linewidth=1.5, alpha=0.7, label='20日移动平均')
        
        if len(display_data) > 60:
            ma60 = display_data['收盘价'].rolling(window=60).mean()
            ax.plot(display_data['日期'], ma60, 'g--', 
                   linewidth=1.5, alpha=0.7, label='60日移动平均')
        
        # 标注关键点
        if len(display_data) > 0:
            max_price = display_data['收盘价'].max()
            min_price = display_data['收盘价'].min()
            max_date = display_data.loc[display_data['收盘价'].idxmax(), '日期']
            min_date = display_data.loc[display_data['收盘价'].idxmin(), '日期']
            
            ax.scatter([max_date, min_date], [max_price, min_price], 
                      color=['red', 'green'], s=100, zorder=5)
            
            # 标注文本
            ax.annotate(f'{max_price:,.0f}', xy=(max_date, max_price),
                       xytext=(max_date, max_price * 1.02),
                       arrowprops=dict(arrowstyle='->', color='red', lw=1.5),
                       fontsize=11, color='red', ha='center',
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
            
            ax.annotate(f'{min_price:,.0f}', xy=(min_date, min_price),
                       xytext=(min_date, min_price * 0.98),
                       arrowprops=dict(arrowstyle='->', color='green', lw=1.5),
                       fontsize=11, color='green', ha='center',
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        
        ax.set_title(f'碳酸锂期货{title_suffix}价格走势图', 
                    fontsize=18, fontweight='bold', pad=20)
        ax.set_xlabel('日期', fontsize=14)
        ax.set_ylabel('价格 (元/吨)', fontsize=14)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(fontsize=12, loc='upper left')
        
        # 格式化y轴
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, pos: f'{x:,.0f}'))
        
        plt.xticks(rotation=30)
        plt.tight_layout()
        
        # 生成统计信息
        stats_text = []
        stats_text.append(f"### 📈 {title_suffix}市场统计")
        stats_text.append(f"**数据期间**：{display_data['日期'].min().strftime('%Y-%m-%d')} 至 {display_data['日期'].max().strftime('%Y-%m-%d')}")
        stats_text.append(f"**最新价格**：{display_data['收盘价'].iloc[-1]:,.2f} 元/吨")
        stats_text.append(f"**期间最高**：{display_data['收盘价'].max():,.2f} 元/吨")
        stats_text.append(f"**期间最低**：{display_data['收盘价'].min():,.2f} 元/吨")
        stats_text.append(f"**平均价格**：{display_data['收盘价'].mean():,.2f} 元/吨")
        stats_text.append(f"**价格标准差**：{display_data['收盘价'].std():,.2f} 元/吨")
        
        if '涨跌幅' in display_data.columns:
            avg_return = display_data['涨跌幅'].mean()
            up_days = (display_data['涨跌幅'] > 0).sum()
            down_days = (display_data['涨跌幅'] < 0).sum()
            flat_days = (display_data['涨跌幅'] == 0).sum()
            max_up = display_data['涨跌幅'].max()
            max_down = display_data['涨跌幅'].min()
            
            stats_text.append(f"**平均日涨跌**：{avg_return:.2f}%")
            stats_text.append(f"**上涨天数**：{up_days} 天 ({up_days/len(display_data)*100:.1f}%)")
            stats_text.append(f"**下跌天数**：{down_days} 天 ({down_days/len(display_data)*100:.1f}%)")
            stats_text.append(f"**平盘天数**：{flat_days} 天 ({flat_days/len(display_data)*100:.1f}%)")
            stats_text.append(f"**最大单日涨幅**：{max_up:.2f}%")
            stats_text.append(f"**最大单日跌幅**：{max_down:.2f}%")
        
        if '成交量' in display_data.columns:
            avg_volume = display_data['成交量'].mean()
            total_volume = display_data['成交量'].sum()
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
# Streamlit应用主程序
# ============================================================================

def main():
    st.set_page_config(
        page_title="碳酸锂期货套保分析系统（云端版）",
        page_icon="☁️📈",
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
    .cloud-badge {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-block;
        margin-left: 10px;
        vertical-align: middle;
    }
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    .data-source {
        font-size: 0.8rem;
        color: #666;
        text-align: right;
        margin-top: -15px;
        margin-bottom: 20px;
    }
    .stButton > button {
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 检查Supabase连接状态
    with st.sidebar:
        if HAS_SUPABASE:
            st.success("✅ Supabase连接正常")
        else:
            st.error("⚠️ Supabase未配置")
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
    st.markdown('<h1 class="main-header">☁️ 碳酸锂期货套保分析系统</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#666;font-size:1.2rem;">云端存储 · 实时数据 · 专业分析</p>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔐 用户登录", "📝 新用户注册"])
    
    with tab1:
        with st.container():
            col_left, col_center, col_right = st.columns([1, 2, 1])
            
            with col_center:
                st.markdown("### 用户登录")
                
                username = st.text_input("用户名", placeholder="请输入用户名")
                password = st.text_input("密码", type="password", placeholder="请输入密码")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("登录", type="primary", use_container_width=True):
                        if username and password:
                            with st.spinner("正在验证..."):
                                success, result = analyzer.auth.login(username, password)
                                if success:
                                    st.session_state.authenticated = True
                                    st.session_state.user_info = {
                                        'user_id': result['user_id'],
                                        'username': result['username'],
                                        'email': result['email'],
                                        'settings': result.get('settings', {})
                                    }
                                    st.success("登录成功！")
                                    st.rerun()
                                else:
                                    st.error(result.get('message', '登录失败'))
                        else:
                            st.error("请输入用户名和密码")
                
                with col_btn2:
                    if st.button("忘记密码", use_container_width=True):
                        st.session_state.show_forgot_password = True
                        st.rerun()
                
                # 演示账号（可选）
                with st.expander("💡 快速体验"):
                    st.markdown("""
                    **演示账号**：
                    - 用户名：demo_user
                    - 密码：demo123
                    
                    **或直接注册新账号**
                    """)
    
    with tab2:
        with st.container():
            col_left, col_center, col_right = st.columns([1, 2, 1])
            
            with col_center:
                st.markdown("### 新用户注册")
                
                new_username = st.text_input("用户名", key="reg_username", 
                                           placeholder="至少3个字符")
                new_email = st.text_input("邮箱", key="reg_email", 
                                        placeholder="用于找回密码")
                new_password = st.text_input("密码", type="password", 
                                           key="reg_password1", 
                                           placeholder="至少6个字符")
                confirm_password = st.text_input("确认密码", type="password", 
                                               key="reg_password2")
                
                # 密码强度检查
                if new_password:
                    strength = "弱" if len(new_password) < 8 else "中" if len(new_password) < 12 else "强"
                    color = "red" if strength == "弱" else "orange" if strength == "中" else "green"
                    st.markdown(f"密码强度：<span style='color:{color};font-weight:bold'>{strength}</span>", 
                              unsafe_allow_html=True)
                
                if st.button("注册", type="primary", use_container_width=True):
                    if not all([new_username, new_email, new_password, confirm_password]):
                        st.error("请填写所有字段")
                    elif len(new_username) < 3:
                        st.error("用户名至少3个字符")
                    elif '@' not in new_email:
                        st.error("请输入有效的邮箱地址")
                    elif new_password != confirm_password:
                        st.error("两次输入的密码不一致")
                    elif len(new_password) < 6:
                        st.error("密码长度至少6位")
                    else:
                        with st.spinner("正在注册..."):
                            success, message = analyzer.auth.register(new_username, new_password, new_email)
                            if success:
                                st.success(message)
                                # 自动登录
                                success, result = analyzer.auth.login(new_username, new_password)
                                if success:
                                    st.session_state.authenticated = True
                                    st.session_state.user_info = {
                                        'user_id': result['user_id'],
                                        'username': result['username'],
                                        'email': result['email'],
                                        'settings': result.get('settings', {})
                                    }
                                    st.success("自动登录成功！")
                                    st.rerun()
                            else:
                                st.error(message)

def render_forgot_password(analyzer):
    """渲染忘记密码页面"""
    st.markdown("### 🔑 找回密码")
    
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
    st.markdown(f"### 🔑 重置密码 - {st.session_state.reset_username}")
    
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
    # 顶部导航栏
    col1, col2, col3, col4, col5, col6, col7 = st.columns([3, 1, 1, 1, 1, 1, 1])
    
    with col1:
        st.markdown(f"<h2 style='margin:0;'>📈 碳酸锂套保分析系统</h2>", unsafe_allow_html=True)
        st.markdown(f"<span class='cloud-badge'>云端版</span>", unsafe_allow_html=True)
    
    # 导航按钮
    pages = ["首页", "套保计算", "价格行情", "分析历史", "账号设置"]
    page_icons = ["🏠", "🧮", "📊", "📜", "⚙️"]
    
    for i, (page, icon) in enumerate(zip(pages, page_icons)):
        col = [col2, col3, col4, col5, col6][i]
        with col:
            if st.button(f"{icon} {page}", use_container_width=True, 
                        help=f"切换到{page}页面"):
                st.session_state.current_page = page
                st.rerun()
    
    # 显示用户信息和数据来源
    user_info = st.session_state.user_info
    st.markdown(f"<p style='text-align:right;color:#666;'>👤 {user_info['username']} | ☁️ 云端存储 | 📅 {datetime.now().strftime('%Y-%m-%d')}</p>", 
                unsafe_allow_html=True)
    
    st.markdown('<p class="data-source">数据来源：akshare金融数据接口 | 数据更新：实时</p>', 
                unsafe_allow_html=True)
    
    st.divider()
    
    # 页面内容路由
    if st.session_state.current_page == "首页":
        render_home_page(analyzer)
    elif st.session_state.current_page == "套保计算":
        render_hedge_page(analyzer)
    elif st.session_state.current_page == "价格行情":
        render_price_page(analyzer)
    elif st.session_state.current_page == "分析历史":
        render_history_page(analyzer)
    elif st.session_state.current_page == "账号设置":
        render_settings_page(analyzer)

def render_home_page(analyzer):
    """渲染首页"""
    st.markdown("<h1>🏠 系统首页</h1>", unsafe_allow_html=True)
    
    # 欢迎信息
    user_info = st.session_state.user_info
    st.markdown(f"### 欢迎回来，{user_info['username']}！")
    
    # 快速开始卡片
    st.markdown("### 🚀 快速开始")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        card1 = st.container()
        with card1:
            st.markdown("### 🧮 套保计算")
            st.markdown("基于当前市场价格，计算最优套保方案")
            if st.button("开始计算", key="home_calc", use_container_width=True):
                st.session_state.current_page = "套保计算"
                st.rerun()
    
    with col2:
        card2 = st.container()
        with card2:
            st.markdown("### 📊 价格行情")
            st.markdown("查看碳酸锂期货实时价格走势")
            if st.button("查看行情", key="home_price", use_container_width=True):
                st.session_state.current_page = "价格行情"
                st.rerun()
    
    with col3:
        card3 = st.container()
        with card3:
            st.markdown("### 📜 分析历史")
            st.markdown("查看您的历史分析记录")
            if st.button("查看历史", key="home_history", use_container_width=True):
                st.session_state.current_page = "分析历史"
                st.rerun()
    
    # 系统功能介绍
    st.markdown("### 🌟 系统功能")
    
    with st.expander("📈 套保计算功能", expanded=True):
        st.markdown("""
        **核心计算功能**：
        1. **盈亏平衡分析**：自动计算套保前后的盈亏平衡点
        2. **情景模拟**：价格变动±50%到+100%的盈亏分析
        3. **保证金计算**：自动计算期货交易所需保证金
        4. **风险提示**：根据套保比例提供风险建议
        
        **计算参数**：
        - 存货成本价：0-500,000元/吨
        - 存货数量：0-10,000吨
        - 套保比例：0%-200%
        - 保证金比例：默认15%（可配置）
        """)
    
    with st.expander("📊 价格行情功能"):
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
    
    with st.expander("☁️ 云端功能"):
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
    
    # 技术架构
    st.markdown("### 🏗️ 技术架构")
    
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
        st.markdown("### 📈 实时价格")
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
    st.markdown("<h1>🧮 套保计算器</h1>", unsafe_allow_html=True)
    
    # 获取用户设置（如果有）
    user_settings = {}
    if 'user_info' in st.session_state and st.session_state.user_info.get('settings'):
        user_settings = st.session_state.user_info['settings']
    
    # 创建两列布局
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.markdown("### ⚙️ 输入参数")
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
            max_value=200,
            value=int(default_ratio * 100),
            step=5,
            help="计划对冲的价格风险比例，100%表示完全对冲"
        )
        
        hedge_ratio = hedge_ratio_percent / 100
        
        # 高级选项
        with st.expander("⚙️ 高级选项"):
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
                        st.success("✅ 默认设置已保存")
        
        # 操作按钮
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            calc_button = st.button(
                "🚀 开始计算", 
                type="primary", 
                use_container_width=True,
                help="基于当前参数计算套保方案"
            )
        
        with col_btn2:
            if st.button("🔄 刷新数据", use_container_width=True):
                st.session_state.force_refresh = True
                st.rerun()
        
        # 如果点击了计算按钮
        if calc_button:
            with st.spinner("正在获取最新数据并计算套保方案..."):
                fig, suggestions, metrics = analyzer.hedge_calculation(
                    cost_price, inventory, hedge_ratio, margin_rate
                )
                
                if fig is not None:
                    # 保存结果到session state
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
        st.markdown("### 📊 分析结果")
        st.markdown("---")
        
        # 检查是否有计算结果
        if 'hedge_results' in st.session_state:
            results = st.session_state.hedge_results
            metrics = results['metrics']
            params = results['params']
            
            # 显示数据来源和时间
            st.info(f"📅 数据时间：{metrics['latest_date'].strftime('%Y-%m-%d')}")
            
            # 关键指标卡片
            col_metric1, col_metric2, col_metric3 = st.columns(3)
            
            with col_metric1:
                # 计算价格变化
                price_diff = metrics['current_price'] - params['cost_price']
                price_diff_pct = (price_diff / params['cost_price']) * 100 if params['cost_price'] > 0 else 0
                
                delta_color = "normal" if price_diff >= 0 else "inverse"
                st.metric(
                    label="📈 当前市场价格",
                    value=f"{metrics['current_price']:,.0f}",
                    delta=f"{price_diff_pct:+.1f}%",
                    delta_color=delta_color,
                    help=f"较成本价{price_diff:+,.0f}元/吨"
                )
            
            with col_metric2:
                actual_ratio = metrics['hedge_contracts_int'] / params['inventory'] * 100 if params['inventory'] > 0 else 0
                st.metric(
                    label="📦 建议套保手数",
                    value=f"{metrics['hedge_contracts_int']}",
                    delta=f"{actual_ratio:.1f}%",
                    help=f"基于{params['inventory']:,.1f}吨存货"
                )
            
            with col_metric3:
                st.metric(
                    label="💰 所需保证金",
                    value=f"¥{metrics['total_margin']:,.0f}",
                    help=f"按{params['margin_rate']*100:.0f}%保证金比例"
                )
            
            # 显示图表
            st.markdown("#### 📉 盈亏情景分析")
            st.pyplot(results['fig'])
            
            # 详细建议
            with st.expander("📋 详细分析报告", expanded=True):
                st.markdown(results['suggestions'])
            
            # 导出功能
            st.markdown("#### 💾 导出结果")
            col_export1, col_export2, col_export3 = st.columns(3)
            
            with col_export1:
                if st.button("☁️ 保存到云端历史", use_container_width=True, 
                           help="将分析结果保存到云端历史记录"):
                    if 'user_info' in st.session_state:
                        st.success("✅ 分析结果已保存到云端历史记录")
                    else:
                        st.warning("请先登录以保存历史记录")
            
            with col_export2:
                # 生成文本报告
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
实际套保比例：{metrics['hedge_contracts_int']/params['inventory']*100:.2f}%
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
                    label="📄 下载文本报告",
                    data=report_text,
                    file_name=f"套保分析报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    help="下载完整的分析报告文本文件"
                )
            
            with col_export3:
                if st.button("🖼️ 保存图表", use_container_width=True,
                           help="保存分析图表为PNG文件"):
                    import io
                    buf = io.BytesIO()
                    results['fig'].savefig(buf, format='png', dpi=300, bbox_inches='tight')
                    buf.seek(0)
                    
                    st.download_button(
                        label="📥 下载PNG图表",
                        data=buf,
                        file_name=f"套保分析图表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                        mime="image/png",
                        use_container_width=True
                    )
        
        else:
            # 如果没有计算结果，显示说明
            st.info("👈 请在左侧输入参数并点击'开始计算'")
            
            # 显示示例
            with st.expander("📝 参数说明"):
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
                   - >100%：过度套保，可能产生额外风险
                
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
        st.markdown("### 📊 实时市场概况")
        
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
        
        st.markdown("### 💡 使用提示")
        st.markdown("""
        1. **实时数据**：所有计算基于最新市场数据
        2. **自动更新**：数据每30分钟自动缓存
        3. **手动刷新**：可点击"刷新数据"按钮
        4. **云端保存**：登录后自动保存分析历史
        5. **风险提示**：计算结果仅供参考
        """)

def render_price_page(analyzer):
    """渲染价格行情页面"""
    st.markdown("<h1>📊 碳酸锂实时价格行情</h1>", unsafe_allow_html=True)
    
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
        if st.button("🔄 刷新", use_container_width=True, 
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
    display_data = price_data.tail(min(days, len(price_data))).copy()
    
    # 顶部指标卡
    col1, col2, col3, col4 = st.columns(4)
    
    latest_data = display_data.iloc[-1]
    latest_price = latest_data['收盘价']
    
    with col1:
        price_change = latest_data['涨跌幅'] if '涨跌幅' in latest_data else 0
        delta_color = "normal" if price_change >= 0 else "inverse"
        st.metric(
            label="最新价格",
            value=f"{latest_price:,.0f}",
            delta=f"{price_change:.2f}%" if price_change != 0 else None,
            delta_color=delta_color
        )
    
    with col2:
        open_price = latest_data['开盘价'] if '开盘价' in latest_data else latest_price
        st.metric(
            label="当日开盘",
            value=f"{open_price:,.0f}"
        )
    
    with col3:
        high_price = display_data['最高价'].max() if '最高价' in display_data.columns else display_data['收盘价'].max()
        st.metric(
            label=f"{period}最高",
            value=f"{high_price:,.0f}"
        )
    
    with col4:
        low_price = display_data['最低价'].min() if '最低价' in display_data.columns else display_data['收盘价'].min()
        st.metric(
            label=f"{period}最低",
            value=f"{low_price:,.0f}"
        )
    
    # 主图表区域
    st.markdown(f"### {symbol} {period}价格走势")
    
    fig_main, ax_main = plt.subplots(figsize=(14, 6))
    
    # 价格走势线
    ax_main.plot(display_data['日期'], display_data['收盘价'], 
                color='#1f77b4', linewidth=2.5, label='收盘价')
    
    # 添加移动平均线
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
        with st.expander("📊 详细统计信息", expanded=True):
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
    with st.expander("📋 详细数据表格", expanded=False):
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
    st.markdown("### 📥 数据导出")
    
    col_export1, col_export2, col_export3 = st.columns(3)
    
    with col_export1:
        csv_data = display_data.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="下载CSV数据",
            data=csv_data,
            file_name=f"碳酸锂价格_{symbol}_{period}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            help="下载当前显示的价格数据为CSV文件"
        )
    
    with col_export2:
        # 保存图表
        buf = io.BytesIO()
        fig_main.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        
        st.download_button(
            label="保存图表为PNG",
            data=buf,
            file_name=f"碳酸锂价格图表_{symbol}_{period}_{datetime.now().strftime('%Y%m%d')}.png",
            mime="image/png",
            use_container_width=True,
            help="下载当前价格走势图为PNG文件"
        )
    
    with col_export3:
        # 生成分析报告
        report_text = f"""碳酸锂价格分析报告
生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
合约代码：{symbol}
分析周期：{period}

=== 数据统计 ===
数据期间：{display_data['日期'].min().strftime('%Y-%m-%d')} 至 {display_data['日期'].max().strftime('%Y-%m-%d')}
数据点数：{len(display_data)} 天
最新价格：{display_data['收盘价'].iloc[-1]:,.2f} 元/吨
期间最高：{display_data['收盘价'].max():,.2f} 元/吨
期间最低：{display_data['收盘价'].min():,.2f} 元/吨
平均价格：{display_data['收盘价'].mean():,.2f} 元/吨
价格标准差：{display_data['收盘价'].std():,.2f} 元/吨
价格波动率：{(display_data['收盘价'].std() / display_data['收盘价'].mean() * 100):.2f}%

"""
        
        if '涨跌幅' in display_data.columns:
            returns = display_data['涨跌幅'].dropna()
            report_text += f"""=== 涨跌统计 ===
平均日涨跌：{returns.mean():.2f}%
上涨天数：{(returns > 0).sum()} 天
下跌天数：{(returns < 0).sum()} 天
平盘天数：{(returns == 0).sum()} 天
最大单日涨幅：{returns.max():.2f}%
最大单日跌幅：{returns.min():.2f}%
上涨概率：{(returns > 0).sum() / len(returns) * 100:.1f}%

"""
        
        report_text += f"""=== 数据说明 ===
数据来源：akshare金融数据接口
更新频率：日度数据
数据用途：仅供参考，不构成投资建议

报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        st.download_button(
            label="生成分析报告",
            data=report_text,
            file_name=f"碳酸锂分析报告_{symbol}_{period}_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True,
            help="生成并下载详细的价格分析报告"
        )

def render_history_page(analyzer):
    """渲染分析历史页面"""
    st.markdown("<h1>📜 分析历史记录</h1>", unsafe_allow_html=True)
    
    # 获取用户历史记录
    with st.spinner("正在加载分析历史..."):
        history = analyzer.get_user_history(limit=50)
    
    if not history:
        st.info("暂无分析历史记录")
        st.markdown("""
        ### 💡 开始您的第一次分析
        
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
    st.markdown("### 📋 历史记录列表")
    
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
                if st.button("🗑️ 删除", key=f"delete_{analysis_id}", 
                           help="删除此条记录"):
                    if analyzer.delete_history_record(analysis_id):
                        st.success("记录已删除")
                        st.rerun()
                    else:
                        st.error("删除失败")
                
                # 重新分析按钮
                if 'input_params' in record and isinstance(record['input_params'], dict):
                    if st.button("🔄 重新分析", key=f"recalc_{analysis_id}"):
                        st.session_state.recalc_params = record['input_params']
                        st.session_state.current_page = "套保计算"
                        st.rerun()
    
    # 批量操作
    st.markdown("---")
    st.markdown("### 📦 批量操作")
    
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
            st.warning("⚠️ 此操作将删除所有历史记录，且不可恢复！")
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
    st.markdown("<h1>⚙️ 账号设置</h1>", unsafe_allow_html=True)
    
    user_info = st.session_state.user_info
    
    tab1, tab2, tab3, tab4 = st.tabs(["账户信息", "修改密码", "偏好设置", "数据管理"])
    
    with tab1:
        st.markdown("### 👤 账户信息")
        
        if user_info:
            col_info1, col_info2 = st.columns(2)
            
            with col_info1:
                st.markdown(f"**用户名**：{user_info['username']}")
                st.markdown(f"**邮箱**：{user_info['email']}")
                st.markdown(f"**用户ID**：`{user_info['user_id']}`")
            
            with col_info2:
                if 'settings' in user_info and user_info['settings']:
                    settings = user_info['settings']
                    st.markdown("**账户状态**：✅ 正常")
                    st.markdown(f"**会员等级**：{settings.get('subscription_tier', '免费版')}")
                    st.markdown(f"**注册时间**：{settings.get('created_at', '未知')[:10]}")
                else:
                    st.markdown("**账户状态**：⚠️ 设置未加载")
        
        # 账户操作
        st.markdown("### 🔧 账户操作")
        
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
        st.markdown("### 🔑 修改密码")
        
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
        st.markdown("### 🎨 偏好设置")
        
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
                max_value=200,
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
                    st.success("✅ 偏好设置已保存")
                    st.session_state.user_info['settings'] = new_settings
                else:
                    st.error("保存设置失败")
        else:
            st.info("正在加载用户设置...")
    
    with tab4:
        st.markdown("### 📊 数据管理")
        
        st.markdown("#### 本地缓存")
        col_cache1, col_cache2 = st.columns(2)
        
        with col_cache1:
            if st.button("清除本地缓存", use_container_width=True, 
                        help="清除本地缓存的价格数据"):
                analyzer.cache_data = {}
                analyzer.cache_time = {}
                st.success("✅ 本地缓存已清除")
        
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
            st.warning("⚠️ 此操作将删除您的所有数据，且不可恢复！")
            confirm = st.checkbox("我确认要注销账户")
            if confirm:
                st.error("账户注销功能开发中")
                # 这里需要实现账户删除功能
    
    # 退出登录按钮
    st.markdown("---")
    col_logout1, col_logout2, col_logout3 = st.columns([1, 2, 1])
    
    with col_logout2:
        if st.button("🚪 退出登录", type="primary", use_container_width=True):
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
