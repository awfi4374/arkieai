#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心跳守护（Heartbeat Guardian）
================================
来源：2026-09-30 邮箱告警排查

【问题】
沙箱没有 systemd，心跳只能跑在会话进程里。
会话/环境重启 → 心跳进程死 → hc-ping 超时 → 用户邮箱收告警。
（历史数据：369 次心跳，断档 1 次，断了 269 分钟）

【本脚本的解法】
不解决"沙箱重启"，而是解决"重启后没人拉起"：
① 每 60 秒检查心跳是否新鲜（hb.log 最后一条 < 5 分钟）
② 不新鲜 → 自己重新拉起 hb_loop.py
③ 同时把状态写到 hb_guardian.log（可审计）

【为什么这样能治】
只要有任何"会话"活着，守护就在跑；
守护一跑起来，就能把死掉的心跳拉回来。
比"纯靠人工发现"强一个数量级。

用法：
  python3 hb_guardian.py           # 单次检查
  python3 hb_guardian.py loop      # 常驻守护
"""
import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path

STATE = Path('/app/agent/state')
HB_LOG = STATE / 'hb.log'
HB_LOOP = STATE / 'hb_loop.py'
GUARD_LOG = STATE / 'hb_guardian.log'
STALE_SECONDS = 300  # 5 分钟没心跳 = 判定死亡
CHECK_INTERVAL = 60  # 每 60 秒检查一次


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(GUARD_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def heartbeat_age():
    """返回心跳年龄（秒）；无记录返回 None"""
    if not HB_LOG.exists():
        return None
    # 找最后一条 "心跳: " 记录的时间戳
    try:
        lines = HB_LOG.read_text(errors='ignore').strip().split('\n')
        for line in reversed(lines):
            if '心跳: ' in line:
                ts = line.split(']')[0].strip('[')
                t = datetime.fromisoformat(ts)
                return (datetime.now() - t).total_seconds()
    except Exception:
        pass
    return None


def is_hb_loop_running():
    """检查 hb_loop.py 进程是否存在"""
    try:
        r = subprocess.run(
            ['pgrep', '-f', 'hb_loop.py'],
            capture_output=True, text=True, timeout=10
        )
        pids = [p for p in r.stdout.strip().split('\n') if p]
        # 排除自己（守护不叫 hb_loop）
        return len(pids) > 0
    except Exception:
        return False


def restart_hb_loop():
    """重新拉起心跳循环"""
    try:
        # 用 setsid 脱离当前会话，避免被父进程拖死
        subprocess.Popen(
            ['setsid', 'python3', str(HB_LOOP)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            cwd=str(STATE),
            start_new_session=True,
        )
        log('🔧 已重新拉起 hb_loop.py')
        return True
    except Exception as e:
        log(f'❌ 拉起失败: {type(e).__name__}: {e}')
        return False


def check_once():
    age = heartbeat_age()
    running = is_hb_loop_running()

    if age is None:
        log('⚠️ 无心跳记录 → 拉起')
        restart_hb_loop()
        return 1

    if age > STALE_SECONDS or not running:
        log(f'⚠️ 心跳异常（{age:.0f}秒前，进程{"在" if running else "不在"}）→ 拉起')
        restart_hb_loop()
        return 1

    log(f'✅ 心跳正常（{age:.0f}秒前，进程在）')
    return 0


def loop():
    log(f'守护启动（每 {CHECK_INTERVAL} 秒检查，阈值 {STALE_SECONDS} 秒）')
    while True:
        try:
            check_once()
        except Exception as e:
            log(f'检查异常: {type(e).__name__}: {e}')
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'loop':
        loop()
    else:
        sys.exit(check_once())
