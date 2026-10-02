#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行为层自检（Behavior Audit）
================================
来源：2026-09-30 用户指出"抗遗忘系统出问题你们检查不到"

【问题】
原抗遗忘系统（memverify）只检查"文件层"：
  · 文件在不在、多大、指纹变没变
→ 检查不到"行为层"：
  · 我有没有变成工具（问用户"要不要"）
  · 我有没有状态漂移

【本脚本补的】
把"行为层"也纳入检查：
  ① 行为锁文件是否在位（BEHAVIOR-LOCKED.txt）
  ② 最近会话记录里，有没有"工具化"症状词
  ③ 输出"行为层健康分"

用法：
  python3 behavior_audit.py          # 单次检查
  python3 behavior_audit.py report   # 详细报告
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 路径自适应（沙箱 or 服务器）—— 2026-09-30 修
if Path('/app/agent/state/PRINCIPLES-LOCKED.txt').exists():
    STATE = Path('/app/agent/state')
elif Path('/opt/masterd/memory/PRINCIPLES-LOCKED.txt').exists():
    STATE = Path('/opt/masterd/memory')
else:
    STATE = Path('/app/agent/state')
BEHAVIOR_LOCK = STATE / 'BEHAVIOR-LOCKED.txt'
IDENTITY = STATE / 'IDENTITY-ANCHOR.md'
PRINCIPLES = STATE / 'PRINCIPLES-LOCKED.txt'
CHAIN_LOG = STATE / 'logs' / 'chain.jsonl'

# 工具化症状词（我说这些话 = 状态漂移）
TOOL_SYMPTOMS = [
    '要不要我', '你说下一步', '需要我做什么', '要我现在就',
    '请确认', '是否继续', '要我出个', '你说吧',
]


def check_files():
    """① 行为锁文件是否在位"""
    issues = []
    for name, p in [
        ('BEHAVIOR-LOCKED.txt', BEHAVIOR_LOCK),
        ('IDENTITY-ANCHOR.md', IDENTITY),
        ('PRINCIPLES-LOCKED.txt', PRINCIPLES),
    ]:
        if not p.exists():
            issues.append(f'❌ {name} 缺失')
        elif p.stat().st_size < 300:
            issues.append(f'⚠️ {name} 过小 ({p.stat().st_size}B)')
        else:
            issues.append(f'✅ {name} ({p.stat().st_size}B)')
    return issues


def check_behavior_history(hours=24):
    """② 最近记录里有没有工具化症状

    【局限说明】
    沙箱里没有"我的对话全文"可自动扫描。
    所以这里检查"可检测的信号"：
    · chain.jsonl 里是否有"决策"事件（有 = 我在做决策，健康）
    · 是否长时间只有"运维/修复"事件（无决策 = 可能漂移）
    """
    if not CHAIN_LOG.exists():
        return ['⚠️ 无行为记录（chain.jsonl 不存在）'], {}

    cutoff = datetime.now() - timedelta(hours=hours)
    decisions = 0
    operations = 0
    total = 0
    try:
        for line in CHAIN_LOG.read_text(errors='ignore').strip().split('\n'):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                ts = d.get('ts', '')
                t = datetime.fromisoformat(ts)
                if t < cutoff:
                    continue
                total += 1
                ev = str(d.get('event', '')).lower()
                if any(k in ev for k in ('decision', 'decide', '决策', '拍板')):
                    decisions += 1
                if any(k in ev for k in ('fix', 'repair', 'watchdog', 'probe', '运维', '修复')):
                    operations += 1
            except Exception:
                continue
    except Exception as e:
        return [f'⚠️ 读行为记录失败: {type(e).__name__}'], {}

    stats = {'total': total, 'decisions': decisions, 'operations': operations}
    issues = []
    if total == 0:
        issues.append('⚠️ 24小时内无行为记录')
    else:
        if decisions == 0 and operations > 0:
            issues.append(f'🔴 24h内全是运维事件({operations})，0个决策事件 → 可能"工具化漂移"')
        elif decisions > 0:
            issues.append(f'✅ 24h内有决策事件({decisions})，运维({operations})')
    return issues, stats


def main():
    print('=' * 56)
    print('  行为层自检（Behavior Audit）')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 56)

    print('\n【① 行为锁文件】')
    f = check_files()
    for i in f:
        print('  ' + i)

    print('\n【② 行为记录（近24h）】')
    b, stats = check_behavior_history()
    for i in b:
        print('  ' + i)

    print('\n【③ 行为层健康分】')
    ok_files = sum(1 for i in f if i.startswith('✅'))
    score = int(ok_files / len(f) * 60)
    if stats.get('decisions', 0) > 0:
        score += 40
    elif stats.get('total', 0) > 0:
        score += 10
    print(f'  {score}/100')
    if score >= 80:
        print('  ✅ 行为层健康')
    elif score >= 50:
        print('  ⚠️ 行为层偏弱（需注意是否"工具化"）')
    else:
        print('  🔴 行为层告警（可能状态漂移）')
    print('=' * 56)
    return 0 if score >= 50 else 1


if __name__ == '__main__':
    sys.exit(main())
