-- database_setup.sql
-- 在Supabase SQL编辑器中运行此脚本

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(32) PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    last_login TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    subscription_tier VARCHAR(20) DEFAULT 'free'
);

-- 重置密码验证码表
CREATE TABLE IF NOT EXISTS reset_codes (
    code_id VARCHAR(16) PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    reset_code VARCHAR(6) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_used BOOLEAN DEFAULT FALSE
);

-- 数据缓存表
CREATE TABLE IF NOT EXISTS data_cache (
    cache_id VARCHAR(50) PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    data_type VARCHAR(20) NOT NULL,
    data_json JSONB NOT NULL,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- 分析历史表
CREATE TABLE IF NOT EXISTS analysis_history (
    analysis_id VARCHAR(16) PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    analysis_type VARCHAR(50) NOT NULL,
    input_params JSONB NOT NULL,
    result_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW())
);

-- 用户设置表
CREATE TABLE IF NOT EXISTS user_settings (
    setting_id VARCHAR(16) PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    default_cost_price DECIMAL(12,2) DEFAULT 100000.00,
    default_inventory DECIMAL(10,2) DEFAULT 100.00,
    default_hedge_ratio DECIMAL(5,4) DEFAULT 0.80,
    theme_color VARCHAR(20) DEFAULT 'blue',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW())
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_reset_codes_username ON reset_codes(username);
CREATE INDEX IF NOT EXISTS idx_reset_codes_expires ON reset_codes(expires_at);
CREATE INDEX IF NOT EXISTS idx_data_cache_symbol ON data_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_data_cache_expires ON data_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_analysis_history_user_id ON analysis_history(user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_history_created ON analysis_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);

-- 创建存储过程：清理过期数据
CREATE OR REPLACE FUNCTION cleanup_expired_data()
RETURNS void AS $$
BEGIN
    DELETE FROM data_cache WHERE expires_at < NOW();
    DELETE FROM reset_codes WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

-- 创建触发器：更新用户设置时间
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc'::text, NOW());
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_user_settings_updated_at 
    BEFORE UPDATE ON user_settings 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- 创建视图：用户活跃统计
CREATE VIEW user_activity_stats AS
SELECT 
    u.user_id,
    u.username,
    u.email,
    u.created_at,
    u.last_login,
    COUNT(DISTINCT ah.analysis_id) as total_analyses,
    MAX(ah.created_at) as last_analysis_time
FROM users u
LEFT JOIN analysis_history ah ON u.user_id = ah.user_id
WHERE u.is_active = TRUE
GROUP BY u.user_id, u.username, u.email, u.created_at, u.last_login;