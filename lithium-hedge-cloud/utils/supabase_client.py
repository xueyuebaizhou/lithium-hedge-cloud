# utils/supabase_client.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import bcrypt
import secrets
from typing import Optional, Dict, Any, List, Tuple
import pandas as pd
import numpy as np
from dateutil import parser

# 加载环境变量
load_dotenv()

class SupabaseManager:
    """Supabase数据库管理器"""
    
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("请设置SUPABASE_URL和SUPABASE_KEY环境变量")
        
        self.client: Client = create_client(self.url, self.key)
        print(f"✅ Supabase连接成功: {self.url[:30]}...")
    
    # ==================== 用户管理 ====================
    
    def create_user(self, username: str, password: str, email: str) -> Dict[str, Any]:
        """创建新用户"""
        try:
            # 检查用户名是否已存在
            existing_user = self.get_user_by_username(username)
            if existing_user:
                return {"success": False, "message": "用户名已存在"}
            
            # 检查邮箱是否已存在
            existing_email = self.get_user_by_email(email)
            if existing_email:
                return {"success": False, "message": "邮箱已被注册"}
            
            # 哈希密码
            hashed_password = self._hash_password(password)
            
            # 生成用户ID
            user_id = f"user_{secrets.token_hex(12)}"
            
            # 插入用户数据
            user_data = {
                "user_id": user_id,
                "username": username,
                "password_hash": hashed_password,
                "email": email,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "last_login": None,
                "is_active": True,
                "subscription_tier": "free"
            }
            
            response = self.client.table("users").insert(user_data).execute()
            
            if response.data:
                # 创建默认用户设置
                self.create_user_settings(user_id)
                return {
                    "success": True, 
                    "message": "注册成功",
                    "user_id": user_id,
                    "data": response.data[0]
                }
            else:
                return {"success": False, "message": "注册失败"}
                
        except Exception as e:
            print(f"注册错误: {str(e)}")
            return {"success": False, "message": f"注册错误: {str(e)}"}
    
    def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """用户认证"""
        try:
            # 获取用户
            response = self.client.table("users")\
                .select("*")\
                .eq("username", username)\
                .eq("is_active", True)\
                .execute()
            
            if not response.data:
                return {"success": False, "message": "用户不存在"}
            
            user = response.data[0]
            
            # 验证密码
            if not self._verify_password(password, user["password_hash"]):
                return {"success": False, "message": "密码错误"}
            
            # 更新最后登录时间
            update_data = {
                "last_login": datetime.utcnow().isoformat() + "Z"
            }
            
            self.client.table("users")\
                .update(update_data)\
                .eq("user_id", user["user_id"])\
                .execute()
            
            # 获取用户设置
            settings = self.get_user_settings(user["user_id"])
            
            return {
                "success": True,
                "message": "登录成功",
                "user_id": user["user_id"],
                "username": user["username"],
                "email": user["email"],
                "created_at": user["created_at"],
                "last_login": user["last_login"],
                "settings": settings
            }
            
        except Exception as e:
            print(f"登录错误: {str(e)}")
            return {"success": False, "message": f"登录错误: {str(e)}"}
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """根据用户名获取用户"""
        try:
            response = self.client.table("users")\
                .select("*")\
                .eq("username", username)\
                .execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"获取用户错误: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """根据邮箱获取用户"""
        try:
            response = self.client.table("users")\
                .select("*")\
                .eq("email", email)\
                .execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"获取用户错误: {e}")
            return None
    
    def update_user_password(self, username: str, new_password: str) -> bool:
        """更新用户密码"""
        try:
            hashed_password = self._hash_password(new_password)
            
            self.client.table("users")\
                .update({"password_hash": hashed_password})\
                .eq("username", username)\
                .execute()
            
            return True
        except Exception as e:
            print(f"更新密码错误: {e}")
            return False
    
    # ==================== 用户设置 ====================
    
    def create_user_settings(self, user_id: str) -> bool:
        """创建用户默认设置"""
        try:
            setting_id = f"set_{secrets.token_hex(8)}"
            
            setting_data = {
                "setting_id": setting_id,
                "user_id": user_id,
                "default_cost_price": 100000.00,
                "default_inventory": 100.00,
                "default_hedge_ratio": 0.80,
                "theme_color": "blue",
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            
            self.client.table("user_settings").insert(setting_data).execute()
            return True
            
        except Exception as e:
            print(f"创建用户设置错误: {e}")
            return False
    
    def get_user_settings(self, user_id: str) -> Optional[Dict]:
        """获取用户设置"""
        try:
            response = self.client.table("user_settings")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
            
            if response.data:
                return response.data[0]
            
            # 如果没有设置，创建默认设置
            self.create_user_settings(user_id)
            response = self.client.table("user_settings")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
            
            return response.data[0] if response.data else None
            
        except Exception as e:
            print(f"获取用户设置错误: {e}")
            return None
    
    def update_user_settings(self, user_id: str, settings: Dict) -> bool:
        """更新用户设置"""
        try:
            self.client.table("user_settings")\
                .update(settings)\
                .eq("user_id", user_id)\
                .execute()
            
            return True
        except Exception as e:
            print(f"更新用户设置错误: {e}")
            return False
    
    # ==================== 验证码管理 ====================
    
    def create_reset_code(self, username: str, email: str) -> Tuple[bool, str]:
        """创建重置密码验证码"""
        try:
            user = self.get_user_by_username(username)
            if not user:
                return False, "用户不存在"
            
            if user["email"] != email:
                return False, "邮箱不匹配"
            
            # 生成6位验证码
            reset_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            
            # 存储验证码（1小时有效）
            code_data = {
                "code_id": f"code_{secrets.token_hex(8)}",
                "username": username,
                "reset_code": reset_code,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
                "is_used": False
            }
            
            self.client.table("reset_codes").insert(code_data).execute()
            
            return True, reset_code
            
        except Exception as e:
            print(f"创建验证码错误: {e}")
            return False, f"创建验证码错误: {str(e)}"
    
    def verify_reset_code(self, username: str, reset_code: str) -> bool:
        """验证重置码"""
        try:
            response = self.client.table("reset_codes")\
                .select("*")\
                .eq("username", username)\
                .eq("reset_code", reset_code)\
                .eq("is_used", False)\
                .execute()
            
            if not response.data:
                return False
            
            code_data = response.data[0]
            expires_at = parser.parse(code_data["expires_at"])
            
            # 检查是否过期
            if datetime.utcnow() > expires_at:
                return False
            
            # 标记为已使用
            self.client.table("reset_codes")\
                .update({"is_used": True})\
                .eq("code_id", code_data["code_id"])\
                .execute()
            
            return True
            
        except Exception as e:
            print(f"验证验证码错误: {e}")
            return False
    
    # ==================== 数据分析缓存 ====================
    
    def save_price_data(self, symbol: str, data: pd.DataFrame, cache_minutes: int = 30) -> bool:
        """保存价格数据到缓存"""
        try:
            # 转换DataFrame为JSON
            data_json = data.to_json(orient='records', date_format='iso')
            
            cache_data = {
                "cache_id": f"price_{symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                "symbol": symbol,
                "data_type": "price",
                "data_json": data_json,
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "expires_at": (datetime.utcnow() + timedelta(minutes=cache_minutes)).isoformat() + "Z"
            }
            
            # 删除旧的缓存（如果有）
            self.client.table("data_cache")\
                .delete()\
                .eq("symbol", symbol)\
                .eq("data_type", "price")\
                .execute()
            
            # 插入新缓存
            response = self.client.table("data_cache").insert(cache_data).execute()
            
            return bool(response.data)
            
        except Exception as e:
            print(f"保存数据缓存失败: {e}")
            return False
    
    def get_price_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """从缓存获取价格数据"""
        try:
            response = self.client.table("data_cache")\
                .select("*")\
                .eq("symbol", symbol)\
                .eq("data_type", "price")\
                .order("last_updated", desc=True)\
                .limit(1)\
                .execute()
            
            if not response.data:
                return None
            
            cache_data = response.data[0]
            expires_at = parser.parse(cache_data["expires_at"])
            
            # 检查是否过期
            if datetime.utcnow() > expires_at:
                return None
            
            # 解析JSON数据
            data = pd.read_json(cache_data["data_json"], orient='records')
            
            # 转换日期列
            if '日期' in data.columns:
                data['日期'] = pd.to_datetime(data['日期'])
            elif 'date' in data.columns:
                data['日期'] = pd.to_datetime(data['date'])
                data = data.rename(columns={'date': '日期'})
            
            return data
            
        except Exception as e:
            print(f"获取缓存数据失败: {e}")
            return None
    
    # ==================== 分析历史 ====================
    
    def save_analysis_result(self, user_id: str, analysis_type: str, 
                           input_params: Dict, result_data: Dict) -> str:
        """保存分析结果，返回分析ID"""
        try:
            analysis_id = f"ana_{secrets.token_hex(8)}"
            
            analysis_data = {
                "analysis_id": analysis_id,
                "user_id": user_id,
                "analysis_type": analysis_type,
                "input_params": json.dumps(input_params, ensure_ascii=False),
                "result_data": json.dumps(result_data, ensure_ascii=False),
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            
            response = self.client.table("analysis_history").insert(analysis_data).execute()
            
            if response.data:
                return analysis_id
            else:
                return ""
            
        except Exception as e:
            print(f"保存分析结果失败: {e}")
            return ""
    
    def get_user_analysis_history(self, user_id: str, limit: int = 20) -> List[Dict]:
        """获取用户分析历史"""
        try:
            response = self.client.table("analysis_history")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            
            if not response.data:
                return []
            
            # 解析JSON数据
            history = []
            for record in response.data:
                try:
                    record["input_params"] = json.loads(record["input_params"])
                    record["result_data"] = json.loads(record["result_data"])
                except:
                    record["input_params"] = {}
                    record["result_data"] = {}
                
                history.append(record)
            
            return history
            
        except Exception as e:
            print(f"获取分析历史失败: {e}")
            return []
    
    def delete_analysis(self, analysis_id: str, user_id: str) -> bool:
        """删除分析记录"""
        try:
            response = self.client.table("analysis_history")\
                .delete()\
                .eq("analysis_id", analysis_id)\
                .eq("user_id", user_id)\
                .execute()
            
            return bool(response.data)
            
        except Exception as e:
            print(f"删除分析记录失败: {e}")
            return False
    
    # ==================== 辅助函数 ====================
    
    @staticmethod
    def _hash_password(password: str) -> str:
        """哈希密码"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def _verify_password(password: str, hashed_password: str) -> bool:
        """验证密码"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except:
            return False
    
    def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            response = self.client.table("users").select("count", count="exact").limit(1).execute()
            return True
        except Exception as e:
            print(f"数据库连接测试失败: {e}")
            return False

# 全局Supabase实例
_supabase_manager = None

def get_supabase_manager():
    """获取Supabase管理器单例"""
    global _supabase_manager
    if _supabase_manager is None:
        try:
            _supabase_manager = SupabaseManager()
            if _supabase_manager.test_connection():
                print("✅ Supabase连接测试通过")
            else:
                print("⚠️ Supabase连接测试失败")
        except Exception as e:
            print(f"❌ 初始化Supabase失败: {e}")
            return None
    return _supabase_manager
