#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MasterD 记忆自检与报警系统
============================
职责：
  ① 定时自检 —— 检查记忆完整性
  ② 异常报警 —— 发现问题立即通知
  ③ 自动检修 —— 能修的自动修

核心：解决"我失忆了但没人知道"的问题

报警方式（按可用性）：
  · 写报警文件（沙箱恢复后能看到）
  · 服务器日志
  · 邮件/Webhook（如果配置了）

用法：
  python3 watchdog.py check     # 单次检查
  python3 watchdog.py loop      # 循环检查
"""
import os
import sys
import shutil
import json
import time
import hashlib
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/home/agent/.local/lib/python3.12/site-packages')
sys.path.insert(0, '/app/agent/state/pylibs')
try:
    import paramiko
except ImportError:
    paramiko = None

HOST = '43.161.226.155'
KEYFILE = '/tmp/mdkey'
# 自动重建 key（2026-10-01）
_src = '/app/agent/state/sshkeys/masterd'
if not os.path.exists(KEYFILE) and os.path.exists(_src):
    shutil.copy(_src, KEYFILE)
    os.chmod(KEYFILE, 0o600)
STATE = Path('/app/agent/state')
ALERT_FILE = STATE / 'ALERT.md'
LOG = STATE / 'logs' / 'watchdog.log'
HEARTBEAT = Path('/opt/masterd/memory/heartbeat.json')

# 必须存在的核心文件
CORE_FILES = {
    'identity.md': 3000,
    'mechanisms.md': 8000,
    'decisions.md': 5000,
    'infra.md': 3000,
    'team-roles.md': 3000,
    'user-profile.md': 800,
    'time-policy.md': 1000,
}

ALERT_LEVELS = {'OK': 0, 'WARN': 1, 'CRITICAL': 2}


def log(level, msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] [{level}] {msg}'
    print(line, flush=True)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    # 写入哈希链（防篡改）—— 2026-09-25 从情报中学到
    try:
        import sys as _sys
        if str(STATE) not in _sys.path:
            _sys.path.insert(0, str(STATE))
        from log_chain import append as chain_append
        chain_append('watchdog', f'{level}:{msg[:100]}')
    except Exception:
        pass


def raise_alert(level, title, detail):
    """写报警文件（沙箱恢复后第一眼能看到）"""
    ALERT_FILE.write_text(f"""# ⚠️ 系统报警

> 级别：**{level}**
> 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## {title}

{detail}

---

## 处理建议

1. 检查服务器上的记忆备份：`/opt/masterd/memory/`
2. 如果沙箱显示文件缺失，运行：`python3 /app/agent/state/RESTORE.py`
3. 如果无法恢复，用户可说「恢复」触发完整恢复流程
""", encoding='utf-8')
    log(level, f'报警已写入 {ALERT_FILE}')


def clear_alert():
    """清除报警（问题解决后）"""
    if ALERT_FILE.exists():
        ALERT_FILE.unlink()
        log('OK', '报警已清除')


def ssh_connect():
    if not paramiko:
        return None
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(HOST, username='root', key_filename=KEYFILE, timeout=20,
                  allow_agent=False, look_for_keys=False)
        return c
    except Exception as e:
        log('WARN', f'SSH 连接失败: {type(e).__name__}')
        return None


def check_local():
    """检查本地记忆"""
    issues = []

    # 1. 核心文件
    for fname, min_size in CORE_FILES.items():
        p = STATE / fname
        if not p.exists():
            issues.append(('CRITICAL', f'文件缺失: {fname}'))
        elif p.stat().st_size < min_size:
            issues.append(('WARN', f'{fname} 过小 ({p.stat().st_size} < {min_size})'))

    # 2. 密钥
    if not (STATE / 'sshkeys' / 'masterd').exists():
        issues.append(('CRITICAL', 'SSH 私钥缺失（无法连接服务器）'))

    # 3. 凭证
    if not (STATE / 'keys' / 'providers.env').exists():
        issues.append(('WARN', 'AI 凭证缺失'))

    return issues


def check_remote(c):
    """检查服务器备份 + 心跳"""
    issues = []
    if not c:
        return [('WARN', '无法连接服务器（无法检查备份）')]

    try:
        sftp = c.open_sftp()
        # 检查核心文件
        for fname in CORE_FILES:
            try:
                st = sftp.stat(f'/opt/masterd/memory/{fname}')
                if st.st_size < 500:
                    issues.append(('WARN', f'服务器 {fname} 过小 ({st.st_size})'))
            except FileNotFoundError:
                issues.append(('CRITICAL', f'服务器备份缺失: {fname}'))

        # 检查同步新鲜度
        try:
            stamp = sftp.open('/opt/masterd/memory/SYNC_STAMP.txt')
            content = stamp.read().decode('utf-8', errors='ignore')
            stamp.close()
            for line in content.split('\n'):
                if line.startswith('last_push='):
                    last = datetime.fromisoformat(line.split('=', 1)[1])
                    diff_min = (datetime.now() - last).total_seconds() / 60
                    if diff_min > 60:
                        issues.append(('WARN', f'同步过期 {diff_min:.0f} 分钟'))
        except Exception:
            pass
        sftp.close()
    except Exception as e:
        issues.append(('WARN', f'服务器检查失败: {type(e).__name__}'))

    return issues


def write_heartbeat(c):
    """写心跳到服务器（证明我还活着）"""
    if not c:
        return
    try:
        data = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'status': 'alive',
            'hostname': os.uname().nodename,
            'files': len(list(STATE.glob('*.md'))),
        }
        sftp = c.open_sftp()
        with sftp.file('/opt/masterd/memory/heartbeat.json', 'w') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
        sftp.close()
    except Exception:
        pass


def auto_repair(issues):
    """尝试自动修复"""
    repaired = []
    for level, msg in issues:
        # 能修的：文件缺失但服务器有备份
        if '文件缺失' in msg and '服务器' not in msg:
            fname = msg.split(': ')[-1]
            log('INFO', f'尝试自动修复 {fname}...')
            # 触发恢复
            try:
                import subprocess
                r = subprocess.run([sys.executable, str(STATE / 'RESTORE.py')],
                                   capture_output=True, text=True, timeout=200)
                if r.returncode == 0:
                    repaired.append(fname)
                    log('OK', f'自动修复成功: {fname}')
            except Exception as e:
                log('WARN', f'自动修复失败: {e}')
    return repaired


def check_once(auto_fix=True):
    """单次完整检查"""
    print('=' * 52)
    print('记忆自检 ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print('=' * 52)

    issues = []

    # 本地检查
    local_issues = check_local()
    issues.extend(local_issues)

    # 服务器检查
    c = ssh_connect()
    remote_issues = check_remote(c)
    issues.extend(remote_issues)

    # 心跳
    if c:
        write_heartbeat(c)
        c.close()

    # 汇总
    if not issues:
        log('OK', '✅ 全部正常')
        clear_alert()
        return 0

    # 分级
    critical = [i for i in issues if i[0] == 'CRITICAL']
    warn = [i for i in issues if i[0] == 'WARN']

    for level, msg in issues:
        log(level, msg)

    # 自动修复
    if auto_fix and critical:
        repaired = auto_repair(critical)
        if repaired:
            log('OK', f'自动修复了 {len(repaired)} 项')
            # 重新检查
            remaining = check_local()
            if not remaining:
                log('OK', '✅ 修复后全部正常')
                clear_alert()
                return 0

    # 报警
    if critical:
        raise_alert('CRITICAL',
                    f'{len(critical)} 项严重问题',
                    '\n'.join(f'- {m}' for _, m in issues))
        return 2
    elif warn:
        raise_alert('WARN',
                    f'{len(warn)} 项警告',
                    '\n'.join(f'- {m}' for _, m in issues))
        return 1

    return 0


def loop(interval=900):
    """循环检查（默认15分钟）"""
    log('INFO', f'启动自检循环（每 {interval//60} 分钟）')
    while True:
        try:
            check_once()
        except Exception as e:
            log('WARN', f'检查异常: {type(e).__name__}: {e}')
        time.sleep(interval)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'loop':
        loop()
    else:
        sys.exit(check_once())
