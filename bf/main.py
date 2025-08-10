import os
import shutil
import tarfile
import json
import asyncio
import datetime
import re
import tempfile
import secrets

from pagermaid.listener import listener
from pagermaid.enums import Message

# 统一时区：北京（UTC+8）
BJ_TZ = datetime.timezone(datetime.timedelta(hours=8), name="UTC+8")


def now_bj():
    return datetime.datetime.now(BJ_TZ)


# 全局变量：用于定时任务
_cron_task = None
_last_client = None  # 捕获最近一次命令的 client 以便定时任务使用
_last_cron_minute_done = None  # 避免同一分钟重复触发


# 持久化确认机制
def get_hf_confirm_file():
    """获取hf确认文件路径"""
    return os.path.join(get_program_dir(), "data", "hf_confirm.json")


def save_hf_confirm_request(backup_info):
    """保存hf确认请求信息"""
    confirm_file = get_hf_confirm_file()
    os.makedirs(os.path.dirname(confirm_file), exist_ok=True)

    confirm_data = {
        "timestamp": now_bj().isoformat(),
        "backup_info": backup_info,
        "expires_at": (now_bj() + datetime.timedelta(minutes=5)).isoformat(),
    }

    with open(confirm_file, "w", encoding="utf-8") as f:
        json.dump(confirm_data, f, ensure_ascii=False, indent=2)


def load_hf_confirm_request():
    """加载hf确认请求信息"""
    confirm_file = get_hf_confirm_file()
    if not os.path.exists(confirm_file):
        return None

    try:
        with open(confirm_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 检查是否过期
        expires_at = datetime.datetime.fromisoformat(data["expires_at"])
        if now_bj() > expires_at:
            os.remove(confirm_file)
            return None

        return data
    except Exception:
        try:
            os.remove(confirm_file)
        except Exception:
            pass
        return None


def clear_hf_confirm_request():
    """清除hf确认请求"""
    confirm_file = get_hf_confirm_file()
    try:
        if os.path.exists(confirm_file):
            os.remove(confirm_file)
    except Exception:
        pass


def get_program_dir():
    return os.getcwd()


def get_config_file():
    """获取配置文件路径"""
    return os.path.join(get_program_dir(), "data", "bf_config.json")


def load_config():
    """加载配置文件"""
    config_file = get_config_file()
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(config):
    """保存配置文件"""
    config_file = get_config_file()
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# 定时任务配置存取
def get_cron_expr():
    cfg = load_config()
    expr = cfg.get("cron_expr")
    if isinstance(expr, str) and expr.strip():
        return expr.strip()
    return None


def set_cron_expr(expr: str | None):
    cfg = load_config()
    if expr and expr.strip():
        cfg["cron_expr"] = expr.strip()
    else:
        cfg.pop("cron_expr", None)
    save_config(cfg)


def get_cron_last_run():
    """获取最近一次定时触发时间（字符串），无则返回 None"""
    cfg = load_config()
    val = cfg.get("cron_last_run")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def set_cron_last_run(ts: str):
    """保存最近一次定时触发时间（字符串）"""
    cfg = load_config()
    cfg["cron_last_run"] = ts
    save_config(cfg)


def _parse_cron_field(field: str, min_v: int, max_v: int):
    """解析单个 cron 字段，返回允许的整数集合。
    支持: "*", "*/n", 具体数字, 逗号列表, 区间a-b, 以及结合步进 a-b/n。
    简化实现，满足常见使用。
    """
    field = field.strip()
    values = set()

    def add_range(a, b, step=1):
        a = max(min_v, int(a))
        b = min(max_v, int(b))
        if step <= 0:
            step = 1
        for v in range(a, b + 1, step):
            values.add(v)

    if field == "*":
        return set(range(min_v, max_v + 1))

    # */n
    if field.startswith("*/"):
        step = int(field[2:])
        add_range(min_v, max_v, step)
        return values

    # 逗号分隔的多项
    parts = field.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            rng, step_s = part.split("/", 1)
            step = int(step_s)
            if rng == "*":
                add_range(min_v, max_v, step)
            elif "-" in rng:
                a, b = rng.split("-", 1)
                add_range(int(a), int(b), step)
            else:
                # 单值带步进等价于该值
                values.add(int(rng))
        elif "-" in part:
            a, b = part.split("-", 1)
            add_range(int(a), int(b))
        else:
            values.add(int(part))
    # 过滤越界
    return {v for v in values if min_v <= v <= max_v}


def _cron_matches(now: datetime.datetime, expr: str) -> bool:
    """判断当前时间是否匹配5段 cron: m h dom mon dow"""
    try:
        fields = expr.split()
        if len(fields) != 5:
            return False
        m_set = _parse_cron_field(fields[0], 0, 59)
        h_set = _parse_cron_field(fields[1], 0, 23)
        dom_set = _parse_cron_field(fields[2], 1, 31)
        mon_set = _parse_cron_field(fields[3], 1, 12)
        dow_set = _parse_cron_field(fields[4], 0, 6)  # 0=周日（cron 语义）

        # Python: Monday=0..Sunday=6
        # 我们约定 cron 的 DOW: 0=周日..6=周六，因此做一次映射：py_dow->cron_dow
        cron_dow = (now.weekday() + 1) % 7  # Monday(0)->1, ..., Sunday(6)->0

        return (
            (now.minute in m_set)
            and (now.hour in h_set)
            and (now.day in dom_set)
            and (now.month in mon_set)
            and (cron_dow in dow_set)
        )
    except Exception:
        return False


def get_next_cron_time(
    expr: str,
    from_dt: datetime.datetime | None = None,
    max_minutes: int = 365 * 24 * 60,
):
    """估算下次匹配时间（本地时区）。按分钟粒度向前搜索，最多一年。
    返回 datetime 或 None。"""
    try:
        base = from_dt or now_bj()
        # 从下一分钟开始找，避免当前分钟重复
        start = base.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        for i in range(max_minutes):
            t = start + datetime.timedelta(minutes=i)
            if _cron_matches(t, expr):
                return t
    except Exception:
        pass
    return None


async def _run_standard_backup_via_client(client):
    """
    无消息上下文的标准备份：打包 data+plugins（默认排除 session），
    如配置允许（upload_sessions=True）则同时生成 sessions 包。
    上传逻辑：若存在目标ID且>1，先上传到收藏夹再转发，以节省重复上传。
    """
    program_dir = get_program_dir()
    data_dir = os.path.join(program_dir, "data")
    plugins_dir = os.path.join(program_dir, "plugins")
    # 清理 data/ 下的历史配置快照，仅保留最新一份
    _prune_config_backups(data_dir)
    now_str = now_bj().strftime("%Y%m%d_%H%M%S")

    tmpdir = tempfile.gettempdir()
    backup_path = os.path.join(tmpdir, f"pagermaid_backup_{now_str}.tar.gz")
    sessions_path = os.path.join(tmpdir, f"pagermaid_sessions_{now_str}.tar.gz")

    # 是否上传 sessions 由配置决定（默认 False）
    cfg = load_config()
    upload_sessions = bool(cfg.get("upload_sessions", False))

    try:
        # 创建主备份（排除 session 文件）
        create_data_plugins_backup(
            backup_path, program_dir=program_dir, exclude_session=True, compresslevel=5
        )

        # 如需上传 session，则另外创建 sessions 包（但若配置禁止，则跳过）
        sessions_created = None
        if upload_sessions:
            sessions_created = create_sessions_archive(
                sessions_path, program_dir=program_dir
            )

        caption = (
            f"📦 **Pagermaid定时标准备份**\n\n"
            f"• 创建时间: {now_bj().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"• 包含: data (不含 session) + plugins\n"
            f"• 触发: cron 定时任务"
        )

        targets = get_target_chat_ids()
        if targets:
            # 多目标优化：单目标直接上传，多目标先上传到收藏夹再转发
            if len(targets) == 1:
                await client.send_file(int(targets[0]), backup_path, caption=caption)
                if sessions_created:
                    await client.send_file(
                        int(targets[0]),
                        sessions_created,
                        caption="🔐 会话（session）备份 — 请妖善保管（敏感）",
                    )
            else:
                # 上传到收藏夹
                sent_msg = await client.send_file("me", backup_path, caption=caption)
                for tgt in targets:
                    try:
                        await client.forward_messages(int(tgt), sent_msg, "me")
                    except Exception:
                        # 若转发失败则退回直接上传
                        await client.send_file(int(tgt), backup_path, caption=caption)
                # sessions 如果生成了也同样处理
                if sessions_created:
                    sent_s = await client.send_file(
                        "me",
                        sessions_created,
                        caption="🔐 会话（session）备份 — 请妖善保管（敏感）",
                    )
                    for tgt in targets:
                        try:
                            await client.forward_messages(int(tgt), sent_s, "me")
                        except Exception:
                            await client.send_file(
                                int(tgt),
                                sessions_created,
                                caption="🔐 会话（session）备份 — 请妖善保管（敏感）",
                            )
        else:
            # 无目标则发送到收藏夹
            await client.send_file("me", backup_path, caption=caption)
            if sessions_created:
                await client.send_file(
                    "me",
                    sessions_created,
                    caption="🔐 会话（session）备份 — 请妖善保管（敏感）",
                )
    finally:
        # 清理临时文件
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
        except Exception:
            pass
        try:
            if os.path.exists(sessions_path):
                os.remove(sessions_path)
        except Exception:
            pass


async def _cron_loop():
    global _last_cron_minute_done
    while True:
        try:
            expr = get_cron_expr()
            if not expr:
                # 未配置，稍后重查
                await asyncio.sleep(30)
                continue
            now = now_bj()
            key = now.strftime("%Y%m%d%H%M")
            if _cron_matches(now, expr) and _last_client is not None:
                # 避免同一分钟重复
                if _last_cron_minute_done != key:
                    _last_cron_minute_done = key
                    try:
                        await _run_standard_backup_via_client(_last_client)
                        # 记录最近一次触发时间
                        set_cron_last_run(now.strftime("%Y-%m-%d %H:%M:%S"))
                    except Exception:
                        pass
            # 10s 粒度检查
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            break
        except Exception:
            # 出错不退出
            await asyncio.sleep(10)


def _restart_cron_task():
    """根据当前配置重启后台定时任务循环"""
    global _cron_task
    try:
        if _cron_task and not _cron_task.done():
            _cron_task.cancel()
    except Exception:
        pass
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
        except Exception:
            loop = None
    if loop and loop.is_running():
        _cron_task = loop.create_task(_cron_loop())
    else:
        # 若当前尚未运行事件循环，稍后在首次命令调用时再启动
        _cron_task = None


# 目标聊天ID管理（支持多目标）
def get_target_chat_ids():
    cfg = load_config()
    ids = []
    # 向后兼容旧字段
    if "target_chat_ids" in cfg and isinstance(cfg["target_chat_ids"], list):
        ids = cfg["target_chat_ids"]
    elif "target_chat_id" in cfg and cfg["target_chat_id"]:
        ids = [cfg["target_chat_id"]]
        # 迁移为新字段
        cfg["target_chat_ids"] = ids
        cfg.pop("target_chat_id", None)
        save_config(cfg)
    # 过滤空白
    ids = [str(i).strip() for i in ids if str(i).strip()]
    # 去重保持顺序
    seen = set()
    uniq = []
    for i in ids:
        if i not in seen:
            uniq.append(i)
            seen.add(i)
    return uniq


def set_target_chat_ids(new_ids):
    cfg = load_config()
    cfg["target_chat_ids"] = new_ids
    save_config(cfg)


def add_target_chat_ids(ids_to_add):
    exist = get_target_chat_ids()
    for x in ids_to_add:
        s = str(x).strip()
        if s and s not in exist:
            exist.append(s)
    set_target_chat_ids(exist)
    return exist


def remove_target_chat_id(id_to_remove):
    exist = get_target_chat_ids()
    if id_to_remove == "all":
        set_target_chat_ids([])
        return []
    exist = [i for i in exist if i != str(id_to_remove).strip()]
    set_target_chat_ids(exist)
    return exist


def create_tar_gz(
    source_dirs,
    output_filename,
    exclude_dirs=None,
    exclude_exts=None,
    max_file_size_mb=None,
    compresslevel=5,
):
    """
    创建 tar.gz 压缩包，支持排除目录/后缀/大文件，并使用可调压缩级别。

    exclude_dirs: 目录名黑名单（命中则整目录跳过），如 ['.git', '__pycache__']
    exclude_exts: 文件后缀黑名单（含点），如 ['.log', '.zip']
    max_file_size_mb: 跳过大于此大小的单文件（单位MB），None表示不限制
    compresslevel: gzip压缩等级，1(快/大) - 9(慢/小)，默认5折中
    """
    exclude_dirs = set(exclude_dirs or [])
    exclude_exts = set(exclude_exts or [])
    size_limit = (max_file_size_mb * 1024 * 1024) if max_file_size_mb else None

    # Python 3.8+ 支持 compresslevel 参数
    with tarfile.open(output_filename, "w:gz", compresslevel=compresslevel) as tar:
        for source_dir in source_dirs:
            if not os.path.exists(source_dir):
                raise FileNotFoundError(f"{source_dir} 不存在")

            base_name = os.path.basename(source_dir.rstrip(os.sep))

            # 如果是单个文件，直接添加
            if os.path.isfile(source_dir):
                fname = os.path.basename(source_dir)
                _, ext = os.path.splitext(fname)
                if ext in exclude_exts:
                    continue
                if size_limit is not None:
                    try:
                        if os.path.getsize(source_dir) > size_limit:
                            continue
                    except Exception:
                        continue
                arcname = os.path.join("pagermaid_backup", base_name)
                tar.add(source_dir, arcname=arcname)
                continue

            # 目录则递归遍历
            for root, dirs, files in os.walk(source_dir):
                # 过滤目录
                dirs[:] = [d for d in dirs if d not in exclude_dirs]

                for fname in files:
                    fpath = os.path.join(root, fname)
                    # 过滤后缀
                    _, ext = os.path.splitext(fname)
                    if ext in exclude_exts:
                        continue
                    # 过滤大文件
                    if size_limit is not None:
                        try:
                            if os.path.getsize(fpath) > size_limit:
                                continue
                        except Exception:
                            continue

                    # 归档名：pagermaid_backup/<source_dir_name>/<relative_path>
                    rel = os.path.relpath(fpath, source_dir)
                    # 确保使用相对路径，防止路径穿越
                    rel = os.path.normpath(rel)
                    if os.path.isabs(rel) or rel.startswith(".."):
                        continue  # 跳过危险路径
                    arcname = os.path.join("pagermaid_backup", base_name, rel)
                    tar.add(fpath, arcname=arcname)


def _gather_session_files(data_dir: str):
    """返回 data 目录下所有 session 相关文件的绝对路径列表"""
    sessions = []
    if not os.path.isdir(data_dir):
        return sessions
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            if f.endswith(".session") or f.endswith(".session-journal"):
                sessions.append(os.path.join(root, f))
    return sessions


def create_data_plugins_backup(
    output_filename: str,
    program_dir: str | None = None,
    exclude_session: bool = True,
    compresslevel: int = 5,
    archive_root: str = "pagermaid_backup",
):
    """
    只打包 program_dir 下的 data 与 plugins（可选择排除 session 文件）。
    - output_filename: 完整路径
    - exclude_session: True 则跳过 *.session / *.session-journal
    - archive_root: 压缩包内的根目录名（默认 pagermaid_backup）
    """
    program_dir = program_dir or get_program_dir()
    data_dir = os.path.join(program_dir, "data")
    plugins_dir = os.path.join(program_dir, "plugins")

    os.makedirs(os.path.dirname(output_filename), exist_ok=True)

    # 使用 explicit walk 以便精确控制哪些文件会被加入
    with tarfile.open(output_filename, "w:gz", compresslevel=compresslevel) as tar:

        def _add_tree(src_dir):
            if not os.path.isdir(src_dir):
                return
            for root, dirs, files in os.walk(src_dir):
                # 排除 __pycache__ 等临时目录
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fname in files:
                    if exclude_session and (
                        fname.endswith(".session") or fname.endswith(".session-journal")
                    ):
                        continue
                    full = os.path.join(root, fname)
                    # 归档内路径：以 program_dir 为基准 => pagermaid_backup/<relative_path>
                    rel = os.path.relpath(full, program_dir)
                    # 防止路径穿越与绝对路径：rel 不应以 .. 开头
                    if rel.startswith(".."):
                        continue
                    arcname = os.path.join(archive_root, rel) if archive_root else rel
                    tar.add(full, arcname=arcname)

        # 先添加 plugins，再添加 data（顺序无关）
        _add_tree(plugins_dir)
        _add_tree(data_dir)


def create_sessions_archive(output_filename: str, program_dir: str | None = None):
    """
    将 data 下的 session 文件（*.session, *.session-journal）打包为单独的 archive。
    若不存在 session 文件，返回 None；否则返回 output_filename。
    """
    program_dir = program_dir or get_program_dir()
    data_dir = os.path.join(program_dir, "data")
    sessions = _gather_session_files(data_dir)
    if not sessions:
        return None

    os.makedirs(os.path.dirname(output_filename), exist_ok=True)
    with tarfile.open(output_filename, "w:gz") as tar:
        for fpath in sessions:
            # arcname 放到 sessions/<relative_path_from_data>
            rel = os.path.relpath(fpath, data_dir)
            if rel.startswith(".."):
                # 防护：不接受 data 目录外的文件
                continue
            arcname = os.path.join("sessions", rel)
            tar.add(fpath, arcname=arcname)
    return output_filename


def _prune_config_backups(data_dir: str, keep_count: int = 1):
    """清理 data/ 下的历史配置快照，仅保留最新一份"""
    try:
        # 这里可以添加具体的清理逻辑，比如删除旧的配置备份文件
        # 目前为空实现，可根据实际需要添加
        pass
    except Exception:
        pass


def delete_specific_files_from_backup(backup_file, temp_dir, files_to_delete):
    with tarfile.open(backup_file, "r:gz") as tar:
        tar.extractall(path=temp_dir)
    for root, dirs, files in os.walk(temp_dir):
        for file_name in files:
            if file_name in files_to_delete:
                file_path = os.path.join(root, file_name)
                os.remove(file_path)
    new_backup_file = backup_file.replace(".tar.gz", "_modified.tar.gz")
    with tarfile.open(new_backup_file, "w:gz") as tar:
        tar.add(temp_dir, arcname="pagermaid_backup")
    return new_backup_file


def safe_extract(tar, path="."):
    """严格的安全解压函数，防止路径穿越攻击"""
    abs_path = os.path.abspath(path)

    for member in tar.getmembers():
        # 规范化路径
        member_path = os.path.normpath(member.name)

        # 检查绝对路径
        if os.path.isabs(member_path):
            raise Exception(f"检测到绝对路径，拒绝解压: {member.name}")

        # 检查路径穿越
        full_path = os.path.abspath(os.path.join(path, member_path))
        if not full_path.startswith(abs_path + os.sep) and full_path != abs_path:
            raise Exception(f"路径穿越检测到，终止恢复: {member.name}")

        # 检查允许的目录（白名单）
        allowed_dirs = ["plugins", "data", "pagermaid_backup"]
        path_parts = member_path.split(os.sep)
        if path_parts and path_parts[0] not in allowed_dirs:
            raise Exception(f"不允许的目录路径: {member.name}")

    # 所有检查通过，执行解压
    tar.extractall(path)


def un_tar_gz(filename, dirs):
    """安全解压 .tar.gz 到指定目录，避免路径穿越"""
    try:
        with tarfile.open(filename, "r:gz") as tar:
            safe_extract(tar, dirs)
        return True
    except Exception as e:
        print(f"解压失败: {e}")
        return False


def sanitize_filename(filename):
    """清理文件名，确保安全"""
    # 移除或替换危险字符
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
    # 限制长度
    if len(safe_name) > 100:
        safe_name = safe_name[:100]
    return safe_name


def generate_smart_package_name(backup_type="backup"):
    """AI智能生成包名"""
    # 获取当前时间信息
    now = now_bj()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # 根据备份类型生成前缀
    if backup_type == "plugins":
        prefix = "bf_p"
    elif backup_type == "data":
        prefix = "bf_d"
    elif backup_type == "full":
        prefix = "bf_all"
    else:
        prefix = "bf"

    # 生成安全的随机ID
    random_id = secrets.token_hex(4)  # 8字符随机ID

    # 组合包名并清理
    package_name = f"{prefix}_{timestamp}_{random_id}.tar.gz"
    package_name = sanitize_filename(package_name)

    return package_name


def create_secure_temp_file(suffix=".tar.gz"):
    """创建安全的临时文件"""
    program_dir = get_program_dir()
    temp_dir = os.path.join(program_dir, "data", "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # 设置目录权限（仅所有者可访问）
    try:
        os.chmod(temp_dir, 0o700)
    except Exception:
        pass  # Windows可能不支持

    # 创建临时文件
    fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=temp_dir)
    os.close(fd)  # 关闭文件描述符，但保留文件
    return temp_path


def create_backup_info(backup_type, file_list=None):
    """创建备份元数据信息"""
    backup_info = {
        "version": "1.0",
        "created_at": now_bj().isoformat(),
        "backup_type": backup_type,
        "pagermaid_version": "unknown",  # 可以后续添加版本检测
        "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
        "file_count": len(file_list) if file_list else 0,
        "files": file_list or [],
        "security_checks": {
            "path_validation": True,
            "safe_extraction": True,
            "whitelist_dirs": ["plugins", "data", "pagermaid_backup"],
        },
    }
    return backup_info


def add_backup_info_to_archive(tar_path, backup_info):
    """向备份文件中添加元数据信息"""
    try:
        # 创建临时信息文件
        temp_info_file = create_secure_temp_file(".json")
        with open(temp_info_file, "w", encoding="utf-8") as f:
            json.dump(backup_info, f, ensure_ascii=False, indent=2)

        # 添加到存档
        with tarfile.open(tar_path, "a:gz") as tar:
            tar.add(temp_info_file, arcname="backup_info.json")

        # 清理临时文件
        os.remove(temp_info_file)
        return True
    except Exception as e:
        print(f"添加备份信息失败: {e}")
        return False


def read_backup_info(tar_path):
    """从备份文件中读取元数据信息"""
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            try:
                info_member = tar.getmember("backup_info.json")
                info_file = tar.extractfile(info_member)
                if info_file:
                    return json.loads(info_file.read().decode("utf-8"))
            except KeyError:
                # 旧版本备份没有元数据
                return None
    except Exception as e:
        print(f"读取备份信息失败: {e}")
    return None


# bf 备份命令
@listener(command="bf", description="备份主命令，支持多种备份模式", need_admin=True)
async def bf(bot, message: Message):
    param = message.parameter
    program_dir = get_program_dir()
    # 捕获 client 以供定时任务使用
    global _last_client
    _last_client = message.client

    if param and param[0] in ["help", "帮助"]:
        help_text = (
            "🔧 备份/恢复 快速指南\n\n"
            "常用：\n"
            "• 帮助：`bf help`\n"
            "• 标准：`bf`\n"
            "• 全量：`bf all [slim|fast]`\n"
            "• 插件：`bf p`\n"
            "• 目标：`bf set <ID...>` / `bf del <ID|all>`\n"
            "• 恢复：`hf`（可在备份上回复后执行）\n"
            "• 定时：`bf cron`\n\n"
            "提示：执行子命令会显示对应说明（如 `bf cron` 或 `<指令名> help`）。"
        )
        await message.edit(help_text)
        return

    if param and param[0] == "set":
        # bf set <id...>
        if len(param) < 2 or param[1] in ["help", "-h", "--help", "?"]:
            set_help = (
                "🎯 设置目标聊天\n\n"
                "用法：\n"
                "• `bf set <ID...>`\n"
                "  - 可空格或逗号分隔多个ID\n\n"
                "示例：\n"
                "• `bf set 123456789 987654321`\n"
                "• `bf set 123456789,987654321`\n\n"
                "提示：设置后，备份会发送到这些目标；未设置时发送到收藏夹。"
            )
            await message.edit(set_help)
            return

        try:
            raw = " ".join(param[1:])
            # 支持空格/逗号分隔
            parts = []
            for seg in raw.replace(",", " ").split():
                if seg.strip():
                    parts.append(seg.strip())
            # 校验：仅允许纯数字或以 '-' 开头的数字（聊天ID/频道ID），不接受 @username
            import re

            valid = []
            for seg in parts:
                if re.fullmatch(r"-?\d+", seg):
                    valid.append(seg)
                else:
                    await message.edit(
                        f"无效的聊天ID: {seg} \n仅支持数字ID，例如 123456 或 -1001234567890"
                    )
                    return
            if not valid:
                await message.edit("聊天ID不能为空")
                return
            new_list = add_target_chat_ids(valid)
            await message.edit(
                f"目标聊天ID已更新：{', '.join(new_list) if new_list else '（已清空）'}"
            )
            return
        except Exception as e:
            await message.edit(f"设置失败：{str(e)}")
            return

    if param and param[0] == "del":
        # bf del <id|all>
        if len(param) < 2 or param[1] in ["help", "-h", "--help", "?"]:
            del_help = (
                "🧹 删除目标聊天\n\n"
                "用法：\n"
                "• 删除单个：`bf del <ID>`\n"
                "• 清空全部：`bf del all`\n\n"
                "示例：\n"
                "• `bf del 123456789`\n"
                "• `bf del all`\n"
            )
            await message.edit(del_help)
            return
        target = param[1]
        try:
            new_list = remove_target_chat_id(target)
            if target == "all":
                await message.edit("已清空全部目标聊天ID")
            else:
                await message.edit(
                    f"已删除：{target}，当前目标列表：{', '.join(new_list) if new_list else '（空）'}"
                )
            return
        except Exception as e:
            await message.edit(f"删除失败：{str(e)}")
            return

    # bf cron - 管理定时任务（国际标准5段cron）
    if param and param[0] == "cron":
        # 用法：
        # bf cron show
        # bf cron off
        # bf cron * * * * *
        if len(param) == 1:
            cur = get_cron_expr()
            last = get_cron_last_run()
            nxt = None
            if cur:
                nxt_dt = get_next_cron_time(cur)
                nxt = nxt_dt.strftime("%Y-%m-%d %H:%M") if nxt_dt else "—"
            cron_help = (
                "⏱️ Cron 定时备份\n\n"
                "用法：\n"
                "• 查看当前：`bf cron show`\n"
                "• 关闭定时：`bf cron off`\n"
                "• 设置定时：`bf cron <m h dom mon dow>`（5 段国际标准）\n\n"
                f"当前设置：{cur if cur else '未设置'}\n"
                f"最近一次触发：{last if last else '—'}\n"
                f"下次预计触发：{nxt if cur else '—'}\n\n"
                "语法说明：\n"
                "• * 任意值  • a-b 范围  • a,b 列表  • */n 步进  • a-b/n 组合\n"
                "• 星期取值 0-6（0=周日）\n\n"
                "常用示例：\n"
                "• 每分钟：`bf cron * * * * *`\n"
                "• 每 5 分钟：`bf cron */5 * * * *`\n"
                "• 每天 03:30：`bf cron 30 3 * * *`\n"
                "• 工作日 02:00：`bf cron 0 2 * * 1-5`\n"
                "• 每月 1 日 00:10：`bf cron 10 0 1 * *`\n"
                "• 每周日 23:50：`bf cron 50 23 * * 0`\n\n"
                "提示：\n"
                "• 定时任务触发标准备份（等同 `bf`）\n"
                "• 同一分钟只会触发一次；时间以本地时区计算\n"
                "• 如已设置目标聊天（`bf set ...`），备份将发送到目标；否则发送到收藏夹\n"
            )
            await message.edit(cron_help)
            return
        sub = " ".join(param[1:]).strip()
        if sub.lower() == "show":
            cur = get_cron_expr()
            last = get_cron_last_run()
            nxt = None
            if cur:
                nxt_dt = get_next_cron_time(cur)
                nxt = nxt_dt.strftime("%Y-%m-%d %H:%M") if nxt_dt else "—"
            await message.edit(
                f"当前定时：{cur if cur else '未设置'}\n最近一次触发：{last if last else '—'}\n下次预计触发：{nxt if cur else '—'}"
            )
            return
        if sub.lower() == "off":
            set_cron_expr(None)
            _restart_cron_task()
            await message.edit("已关闭定时备份")
            return
        # 其余视为表达式
        fields = sub.split()
        if len(fields) != 5:
            await message.edit("无效的表达式：必须为5段，如：bf cron * * * * *")
            return
        # 基础合法性校验
        try:
            # 简单调用解析避免异常
            _ = _parse_cron_field(fields[0], 0, 59)
            _ = _parse_cron_field(fields[1], 0, 23)
            _ = _parse_cron_field(fields[2], 1, 31)
            _ = _parse_cron_field(fields[3], 1, 12)
            _ = _parse_cron_field(fields[4], 0, 6)
        except Exception as e:
            await message.edit(f"表达式解析失败：{str(e)}")
            return
        set_cron_expr(sub)
        _restart_cron_task()
        nxt_dt = get_next_cron_time(sub)
        nxt = nxt_dt.strftime("%Y-%m-%d %H:%M") if nxt_dt else "—"
        await message.edit(
            f"✅ 已设置定时备份：`{sub}`\n下次预计触发：{nxt}\n提示：定时任务将于匹配分钟触发，文件发送到已配置目标或收藏夹。"
        )
        return

    # bf all - 完整程序备份
    if param and param[0] == "all":
        try:
            await message.edit("🔄 正在创建完整程序备份...")

            # 生成智能包名
            package_name = generate_smart_package_name("full")
            backup_filename = f"{package_name}.tar.gz"
            slim_mode = len(param) > 1 and param[1].lower() in ["slim", "fast"]

            # 备份整个程序目录：扩展排除规则，并使用更快压缩等级
            exclude_dirnames = [
                ".git",
                "__pycache__",
                ".pytest_cache",
                "venv",
                "env",
                ".venv",
                "node_modules",
                "cache",
                "caches",
                "logs",
                "log",
                "downloads",
                "download",
                "media",
                ".mypy_cache",
                ".ruff_cache",
            ]
            exclude_exts = [
                ".log",  # 日志文件
                # 注意：不排除 .zip, .tar, .gz 等压缩文件，因为可能是重要的备份数据
                # 不排除媒体文件，因为可能是用户数据
            ]

            # 瘦身模式：更激进的目录排除与文件大小限制，压缩等级更快
            max_file_size_mb = None
            compress_level = 5
            if slim_mode:
                exclude_dirnames.extend(["dist", "build", ".cache", "tmp", "temp"])
                max_file_size_mb = 20  # 跳过超过20MB的大文件
                compress_level = 3  # 更快一些

            include_items = []
            for item in os.listdir(program_dir):
                # 保持与原有逻辑一致：只跳过隐藏文件（以点开头）的顶层文件
                if item.startswith("."):
                    continue
                include_items.append(os.path.join(program_dir, item))

            create_tar_gz(
                include_items,
                backup_filename,
                exclude_dirs=exclude_dirnames,
                exclude_exts=exclude_exts,
                max_file_size_mb=max_file_size_mb,
                compresslevel=compress_level,
            )

            await message.edit("📤 正在上传完整备份...")
            import datetime

            caption = (
                f"🎯 **完整程序备份{'（瘦身）' if slim_mode else ''}**\n\n"
                f"• 包名: `{package_name}`\n"
                f"• 创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"• 备份类型: 完整程序包{'（瘦身上传更快）' if slim_mode else ''}\n"
                f"• 包含: 所有程序文件和配置"
                f"{'（跳过>20MB文件与更多缓存目录）' if slim_mode else ''}"
            )

            # 根据是否存在目标ID决定发送目的地
            targets = get_target_chat_ids()
            show_progress = len(targets) <= 1

            # 进度条仅在单目标时展示，避免多次刷屏
            progress = {"last": 0}

            def _progress(sent, total):
                if not show_progress:
                    return
                try:
                    if total:
                        pct = int(sent * 100 / total)
                        if pct >= progress["last"] + 10:
                            progress["last"] = pct
                            try:
                                message.client.loop.create_task(
                                    message.edit(f"📤 正在上传完整备份... {pct}%")
                                )
                            except Exception:
                                pass
                except Exception:
                    pass

            try:
                if targets:
                    for idx, tgt in enumerate(targets, 1):
                        await message.client.send_file(
                            int(tgt),
                            backup_filename,
                            caption=caption,
                            force_document=True,
                            progress_callback=_progress if show_progress else None,
                        )
                else:
                    await message.client.send_file(
                        "me",
                        backup_filename,
                        caption=caption,
                        force_document=True,
                        progress_callback=_progress,
                    )
            except Exception as e:
                raise Exception(f"上传失败: {str(e)}")

            os.remove(backup_filename)
            if targets:
                await message.edit(
                    f"✅ 完整备份已完成\n\n📦 **包名:** `{package_name}`\n🎯 **已发送到:** {', '.join(targets)}"
                )
            else:
                await message.edit(
                    f"✅ 完整备份已完成\n\n📦 **包名:** `{package_name}`\n🎯 **已保存到:** 收藏夹"
                )
            return
        except Exception as e:
            if "backup_filename" in locals() and os.path.exists(backup_filename):
                os.remove(backup_filename)
            await message.edit(f"❌ 完整备份失败: {str(e)}")
            return

    # bf p - 仅备份Python插件
    if param and param[0] == "p":
        try:
            await message.edit("🐍 正在创建Python插件备份...")

            # 生成智能包名
            package_name = generate_smart_package_name("plugins")
            backup_filename = f"{package_name}.tar.gz"

            plugins_dir = os.path.join(program_dir, "plugins")
            if not os.path.exists(plugins_dir):
                await message.edit("❌ plugins目录不存在")
                return

            # 创建临时根目录，并在其中创建 plugins 目录，保证打包根为 plugins
            temp_root = os.path.join(program_dir, "_tmp_plugins_py_only")
            temp_plugins_dir = os.path.join(temp_root, "plugins")
            os.makedirs(temp_plugins_dir, exist_ok=True)

            # 递归复制所有 .py 文件，保留目录结构，排除 __pycache__
            py_count = 0
            for root, dirs, files in os.walk(plugins_dir):
                # 过滤无用目录
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fname in files:
                    if not fname.endswith(".py"):
                        continue
                    src_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(src_path, plugins_dir)
                    dst_path = os.path.join(temp_plugins_dir, rel_path)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    py_count += 1

            if py_count == 0:
                shutil.rmtree(temp_root)
                await message.edit("❌ 未找到任何Python插件文件")
                return

            # 只打包临时根下的 plugins 目录，保证归档根目录名为 plugins
            create_tar_gz([temp_plugins_dir], backup_filename)
            shutil.rmtree(temp_root)

            await message.edit("📤 正在分享插件备份...")
            import datetime

            caption = f"🐍 **Python插件备份**\n\n• 包名: `{package_name}`\n• 创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n• 备份类型: Python插件包\n• 插件数量: {py_count} 个\n• 适合: 插件分享和迁移"

            # 安全的多目标上传：先上传到所有目标，再删除文件
            targets = get_target_chat_ids()
            upload_tasks = []

            if targets:
                for tgt in targets:
                    upload_tasks.append(
                        message.client.send_file(
                            int(tgt), backup_filename, caption=caption
                        )
                    )
            else:
                upload_tasks.append(
                    message.client.send_file("me", backup_filename, caption=caption)
                )

            # 等待所有上传完成
            await asyncio.gather(*upload_tasks)

            # 所有上传完成后才删除文件
            os.remove(backup_filename)
            if targets:
                await message.edit(
                    f"✅ 插件备份已完成\n\n📦 **包名:** `{package_name}`\n🐍 **插件数量:** {py_count} 个\n🎯 **已发送到:** {', '.join(targets)}"
                )
            else:
                await message.edit(
                    f"✅ 插件备份已完成\n\n📦 **包名:** `{package_name}`\n🐍 **插件数量:** {py_count} 个\n🎯 **已保存到:** 收藏夹"
                )
            return
        except Exception as e:
            if "backup_filename" in locals() and os.path.exists(backup_filename):
                os.remove(backup_filename)
            # 清理插件临时目录（尽量移除根目录与其子目录）
            try:
                if "temp_root" in locals() and os.path.exists(temp_root):
                    shutil.rmtree(temp_root)
                elif "temp_plugins_dir" in locals() and os.path.exists(
                    temp_plugins_dir
                ):
                    shutil.rmtree(temp_plugins_dir)
            except Exception:
                pass
            await message.edit(f"❌ 插件备份失败: {str(e)}")
            return

    if param and param[0] == "to":
        # 兼容旧命令：提示已取消此命令，改用 bf set / bf del
        targets = get_target_chat_ids()
        await message.edit(
            "ℹ️ `bf to` 已取消：\n"
            "- 现在如已设置目标聊天ID，`bf`/`bf all`/`bf p` 会默认发送到所有目标\n"
            "- 使用 `bf set <ID...>` 增加目标；`bf del <ID|all>` 删除目标\n"
            f"- 当前目标：{', '.join(targets) if targets else '（无）'}"
        )
        return

    # 默认备份功能（标准备份）
    try:
        data_dir = os.path.join(program_dir, "data")
        plugins_dir = os.path.join(program_dir, "plugins")
        import datetime

        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # 使用临时目录放置备份，避免与程序目录混淆
        import tempfile

        tmpdir = tempfile.gettempdir()
        backup_path = os.path.join(tmpdir, f"pagermaid_backup_{now_str}.tar.gz")
        sessions_path = os.path.join(tmpdir, f"pagermaid_sessions_{now_str}.tar.gz")

        await message.edit("🔄 正在创建标准备份...")
        # 仅备份 data + plugins（默认排除 session）
        create_data_plugins_backup(
            backup_path, program_dir=program_dir, exclude_session=True, compresslevel=5
        )

        # sessions 是否需要打包/上传由配置控制（upload_sessions: True/False）
        cfg = load_config()
        upload_sessions = bool(cfg.get("upload_sessions", False))
        sessions_created = None
        if upload_sessions:
            sessions_created = create_sessions_archive(
                sessions_path, program_dir=program_dir
            )

        await message.edit("📤 正在上传备份...")
        caption = f"📦 **Pagermaid标准备份**\n\n• 创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n• 包含: data (不含 session) + plugins\n• 备份类型: 标准配置备份"
        targets = get_target_chat_ids()
        if targets:
            # 多目标优化：先上传到收藏夹再转发（避免重复上传）
            if len(targets) == 1:
                await message.client.send_file(
                    int(targets[0]), backup_path, caption=caption, force_document=True
                )
                if sessions_created:
                    await message.client.send_file(
                        int(targets[0]),
                        sessions_created,
                        caption="🔐 会话（session）备份 — 请妖善保管（敏感）",
                    )
            else:
                sent_msg = await message.client.send_file(
                    "me", backup_path, caption=caption, force_document=True
                )
                for tgt in targets:
                    try:
                        await message.client.forward_messages(int(tgt), sent_msg, "me")
                    except Exception:
                        await message.client.send_file(
                            int(tgt), backup_path, caption=caption, force_document=True
                        )
                if sessions_created:
                    sent_s = await message.client.send_file(
                        "me",
                        sessions_created,
                        caption="🔐 会话（session）备份 — 请妖善保管（敏感）",
                        force_document=True,
                    )
                    for tgt in targets:
                        try:
                            await message.client.forward_messages(
                                int(tgt), sent_s, "me"
                            )
                        except Exception:
                            await message.client.send_file(
                                int(tgt),
                                sessions_created,
                                caption="🔐 会话（session）备份 — 请妖善保管（敏感）",
                                force_document=True,
                            )
        else:
            await message.client.send_file(
                "me", backup_path, caption=caption, force_document=True
            )
            if sessions_created:
                await message.client.send_file(
                    "me",
                    sessions_created,
                    caption="🔐 会话（session）备份 — 请妖善保管（敏感）",
                    force_document=True,
                )

        # 清理临时文件
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
        except Exception:
            pass
        try:
            if os.path.exists(sessions_path):
                os.remove(sessions_path)
        except Exception:
            pass

        if targets:
            await message.edit(
                f"✅ 标准备份已完成\n\n🎯 **已发送到:** {', '.join(targets)}\n📦 **包含:** 配置文件 + 插件（session 已单独处理）"
            )
        else:
            await message.edit(
                "✅ 标准备份已完成\n\n🎯 **已保存到:** 收藏夹\n📦 **包含:** 配置文件 + 插件（session 已单独处理）"
            )
    except Exception as e:
        if "backup_path" in locals() and os.path.exists(backup_path):
            os.remove(backup_path)
        if "sessions_path" in locals() and os.path.exists(sessions_path):
            os.remove(sessions_path)
        await message.edit(f"❌ 备份失败: {str(e)}")


# hf 恢复命令
@listener(command="hf", description="恢复备份命令，支持确认模式")
async def hf(bot, message: Message):
    param = message.parameter

    # 检查是否有确认参数
    if not param or param[0] != "confirm":
        # 显示安全警告和确认信息
        warning_text = """⚠️ **危险操作警告** ⚠️

🔄 **恢复备份将会：**
• 覆盖当前所有 data 文件夹内容
• 覆盖当前所有 plugins 文件夹内容
• 可能丢失最近的配置和插件更改
• 需要重启 Pagermaid 才能生效

📋 **恢复前建议：**
• 确认当前没有重要未保存的配置
• 确认要恢复的备份是正确的版本
• 系统会在确认后自动创建一次“防丢失全备份”并上传到收藏夹（无需手动运行 `bf`）

🎯 **将要恢复的备份：**"""

        try:
            await message.edit("🔍 正在扫描备份文件...")
            # 优先使用用户回复的备份文件，其次使用收藏夹中最新的备份
            backup_msg = None
            replied_msg = None
            try:
                replied_msg = await message.get_reply_message()
            except Exception:
                replied_msg = None

            # 优先使用用户回复的任何 .tar.gz 备份
            if (
                replied_msg
                and getattr(replied_msg, "file", None)
                and replied_msg.file.name
                and replied_msg.file.name.endswith(".tar.gz")
            ):
                # 当对着备份文件恢复时：先自动下载文件用于后续确认恢复
                program_dir = get_program_dir()
                temp_dir = os.path.join(program_dir, "data")
                os.makedirs(temp_dir, exist_ok=True)
                selected_temp_path = os.path.join(
                    temp_dir, "_hf_selected_backup.tar.gz"
                )
                try:
                    if os.path.exists(selected_temp_path):
                        os.remove(selected_temp_path)
                except Exception:
                    pass
                await message.edit("📥 正在下载你回复的备份文件...")
                await message.client.download_media(
                    replied_msg, file=selected_temp_path
                )
                backup_msg = replied_msg
            else:
                # 在收藏夹中查找最近的 .tar.gz 备份（兼容 bf / bf all / bf p 等不同命名）
                async for msg in message.client.iter_messages("me", limit=50):
                    if (
                        getattr(msg, "file", None)
                        and msg.file.name
                        and msg.file.name.endswith(".tar.gz")
                    ):
                        backup_msg = msg
                        break

            if not backup_msg:
                await message.edit(
                    "❌ **未找到备份文件**\n\n• 请先创建一个备份（`bf`）或直接回复一个备份文件后再次执行 `hf`\n• 确保备份文件在收藏夹或当前对话中可见"
                )
                return

            # 解析备份文件信息
            file_name = backup_msg.file.name
            file_size = round(backup_msg.file.size / 1024 / 1024, 2)  # MB
            backup_date = backup_msg.date.strftime("%Y-%m-%d %H:%M:%S")

            warning_text += f"\n• **文件名:** `{file_name}`\n• **文件大小:** {file_size} MB\n• **创建时间:** {backup_date}\n\n"
            # 若来自回复，已在上方自动下载，无需再次下载
            if (
                replied_msg
                and backup_msg
                and (backup_msg.id == getattr(replied_msg, "id", None))
            ):
                warning_text += """已自动下载该备份文件。
✅ **确认恢复请输入:**
`hf confirm`

❌ **取消操作请忽略此消息**"""
            else:
                warning_text += """✅ **确认恢复请输入:**
`hf confirm`

❌ **取消操作请忽略此消息**"""

            await message.edit(warning_text)
            return

        except Exception as e:
            await message.edit(f"❌ **扫描失败:** {str(e)}")
            return

    # 用户已确认，开始恢复流程
    try:
        # 优先使用预下载的临时文件（当用户对备份消息回复执行 hf 时会生成）
        program_dir = get_program_dir()
        selected_temp_path = os.path.join(
            program_dir, "data", "_hf_selected_backup.tar.gz"
        )
        pgm_backup_zip_name = None
        temp_extract_dir = None

        if os.path.exists(selected_temp_path):
            await message.edit(
                "✅ **用户已确认，开始恢复流程**\n\n• 已选择回复的备份文件，准备解压..."
            )
            pgm_backup_zip_name = selected_temp_path
        else:
            await message.edit(
                "✅ **用户已确认，开始恢复流程**\n\n• 正在获取最新备份..."
            )
            # 优先使用回复的备份文件，其次获取收藏夹中的最新备份
            backup_msg = None
            replied_msg = None
            try:
                replied_msg = await message.get_reply_message()
            except Exception:
                replied_msg = None

            # 再次优先使用用户回复的任何 .tar.gz 备份
            if (
                replied_msg
                and getattr(replied_msg, "file", None)
                and replied_msg.file.name
                and replied_msg.file.name.endswith(".tar.gz")
            ):
                backup_msg = replied_msg
            else:
                async for msg in message.client.iter_messages("me", limit=50):
                    if (
                        getattr(msg, "file", None)
                        and msg.file.name
                        and msg.file.name.endswith(".tar.gz")
                    ):
                        backup_msg = msg
                        break

            if not backup_msg:
                await message.edit("❌ **恢复失败**\n\n• 未找到任何备份文件")
                return

            await message.edit("📥 **正在下载备份文件...**")
            pgm_backup_zip_name = await message.client.download_media(
                backup_msg, file="pagermaid_backup.tar.gz"
            )

        await message.edit("🗃️ **正在解压备份文件...**")
        program_dir = get_program_dir()

        # 使用临时目录解压，避免直接解压到根目录导致混乱
        temp_extract_dir = os.path.join(program_dir, "_tmp_restore")
        try:
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            os.makedirs(temp_extract_dir, exist_ok=True)
        except Exception:
            pass

        if not un_tar_gz(pgm_backup_zip_name, temp_extract_dir):
            os.remove(pgm_backup_zip_name)
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            await message.edit(
                "❌ **解压失败**\n\n• 备份文件可能损坏\n• 请重新下载备份"
            )
            return

        # 删除压缩包
        os.remove(pgm_backup_zip_name)

        # 尝试识别备份根目录
        final_backup_folder = os.path.join(temp_extract_dir, "pagermaid_backup")
        if not os.path.exists(final_backup_folder):
            # 兼容旧包结构：取临时目录下的唯一顶级目录，或直接使用临时目录
            top_items = [
                os.path.join(temp_extract_dir, x) for x in os.listdir(temp_extract_dir)
            ]
            dirs = [p for p in top_items if os.path.isdir(p)]
            files = [p for p in top_items if os.path.isfile(p)]
            if len(dirs) == 1 and not files:
                final_backup_folder = dirs[0]
            else:
                final_backup_folder = temp_extract_dir

        # 恢复前自动创建一次当前状态的标准全备份（data+plugins）到收藏夹
        try:
            data_dir = os.path.join(program_dir, "data")
            plugins_dir = os.path.join(program_dir, "plugins")
            import datetime

            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_backup_filename = f"pre_restore_backup_{now_str}.tar.gz"
            create_tar_gz([data_dir, plugins_dir], safe_backup_filename)
            caption = f"🛟 恢复前自动全备份\n\n• 创建时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n• 包含: data + plugins"
            await message.client.send_file("me", safe_backup_filename, caption=caption)
            os.remove(safe_backup_filename)
        except Exception:
            # 备份失败不阻塞恢复流程，仅忽略
            pass

        await message.edit("🔄 **正在恢复文件...**")

        # 将解压出的内容释放到程序根目录，跳过 session 文件（避免覆盖会话登陆状态）
        def _is_session_file(path: str) -> bool:
            name = os.path.basename(path)
            return name.endswith(".session") or name.endswith(".session-journal")

        for item in os.listdir(final_backup_folder):
            src_path = os.path.join(final_backup_folder, item)
            dest_path = os.path.join(program_dir, item)
            if os.path.isdir(src_path):
                # 目录复制：逐文件遍历以跳过 session 文件
                for root, dirs, files in os.walk(src_path):
                    rel_root = os.path.relpath(root, src_path)
                    target_root = (
                        os.path.join(dest_path, rel_root)
                        if rel_root != "."
                        else dest_path
                    )
                    os.makedirs(target_root, exist_ok=True)
                    for fname in files:
                        s = os.path.join(root, fname)
                        if _is_session_file(s):
                            continue
                        d = os.path.join(target_root, fname)
                        os.makedirs(os.path.dirname(d), exist_ok=True)
                        shutil.copy2(s, d)
            else:
                if _is_session_file(src_path):
                    continue
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)

        # 清理临时目录
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        # 如使用了预下载的临时文件，恢复完成后删除
        try:
            if pgm_backup_zip_name == selected_temp_path and os.path.exists(
                selected_temp_path
            ):
                os.remove(selected_temp_path)
        except Exception:
            pass

        await message.edit(
            "✅ **备份恢复完成**\n\n• 所有文件已恢复\n• 已在收藏夹保存恢复前的全备份\n• 请输入 `-restart` 重启生效"
        )

    except Exception as e:
        # 失败时尽量清理临时资源
        try:
            if (
                "temp_extract_dir" in locals()
                and temp_extract_dir
                and os.path.exists(temp_extract_dir)
            ):
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            if (
                "pgm_backup_zip_name" in locals()
                and pgm_backup_zip_name
                and os.path.exists(pgm_backup_zip_name)
            ):
                # 仅删除我们下载到当前目录的临时包或预下载选择的包
                if pgm_backup_zip_name.endswith(
                    "pagermaid_backup.tar.gz"
                ) or pgm_backup_zip_name.endswith("_hf_selected_backup.tar.gz"):
                    os.remove(pgm_backup_zip_name)
        except Exception:
            pass
        await message.edit(
            f"❌ **恢复失败**\n\n• 错误信息: {str(e)}\n• 请检查备份文件是否完整"
        )
