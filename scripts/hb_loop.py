#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
沙箱心跳循环（Heartbeat Loop）v4
==================================
2026-10-01 环境重置后重建（简化版，可靠优先）

【做什么】
① 每2分钟：发 hc-ping（证明沙箱活着）
② 同时写 hb.log（供守护检查）
③ 定期：写心跳时间戳

用法：python3 hb_loop.py
"""
import sys
import time
from datetime import datetime
from pathlib import Path

HC_SANDBOX = 'https://hc-ping.com/41d9c98c-b956-4e76-bb87-15e81b21e17b'
HB_LOG = Path('/app/agent/state/hb.log')
INTERVAL = 120  # 2分钟


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(HB_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def send():
    try:
        import urllib.request
        req = urllib.request.Request(HC_SANDBOX,
                                     headers={'User-Agent': 'MasterD-Sandbox/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    log('心跳循环启动（v4，每2分钟）')
    while True:
        try:
            ok = send()
            log(f'心跳: {"OK" if ok else "FAIL"}')
        except Exception as e:
            log(f'异常: {type(e).__name__}')
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
