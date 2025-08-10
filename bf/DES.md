备份功能 
· `bf help` 查看帮助帮助
· `bf` 标准备份（data + plugins，排除敏感 session）
· `bf all` 完整备份（含全部文件）
· `bf all slim` 瘦身备份（跳过大文件）
· `bf p` 插件备份（仅 Python 插件）

恢复功能
· `hf` 恢复备份（需确认）
· `hf confirm` 确认恢复（5分钟内有效）

配置管理
· `bf set <ID...>` 设置目标聊天ID
· `bf del <ID|all>` 删除指定目标或全部
· `bf cron <表达式>` 定时备份（5段 Cron）
· `bf cron off` 关闭定时
· `bf cron show` 查看定时
