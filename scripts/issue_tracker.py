#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""问题追踪器（Issue Tracker）—— 支撑"三次原则"
==================================================
来源：2026-09-30 用户确立"三次原则"

【规则】
· 同类问题 1次 → 记录
· 同类问题 2次 → 警觉
· 同类问题 3次 → 必须深挖（改机制，不是打补丁）

【用法】
  python3 issue_tracker.py log "问题描述" --tag 状态漂移
  python3 issue_tracker.py check          # 看哪些问题达到3次
  python3 issue_tracker.py deepdive <tag> # 触发深挖（要写根因）
  python3 issue_tracker.py list           # 全部记录
"""
import json
import sys
from datetime import datetime
from pathlib import Path

STATE = Path('/app/agent/state')
ISSUES = STATE / 'issue-tracker.jsonl'


def log_issue(desc, tag, note=''):
    """记录一个问题"""
    rec = {
        'ts': datetime.now().isoformat(),
        'tag': tag,
        'desc': desc,
        'note': note,
        'status': 'open',
    }
    with open(ISSUES, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    # 统计同类
    count = sum(1 for r in _all() if r['tag'] == tag)
    print(f'✅ 已记录（tag={tag}，同类累计 {count} 次）')
    if count >= 3:
        print()
        print('🚨🚨🚨 触发「三次原则」！同类问题已达 3 次 → 必须深挖')
        print(f'    执行：python3 issue_tracker.py deepdive {tag}')
    elif count == 2:
        print('⚠️ 同类问题第2次 → 警觉（找模式）')
    return count


def _all():
    if not ISSUES.exists():
        return []
    out = []
    for line in ISSUES.read_text().split('\n'):
        if line.strip():
            out.append(json.loads(line))
    return out


def check():
    """检查哪些问题达到3次"""
    from collections import Counter
    cnt = Counter(r['tag'] for r in _all())
    print('=' * 56)
    print('  问题追踪 · 三类检查')
    print('=' * 56)
    hot = []
    for tag, n in cnt.most_common():
        flag = '🚨 必须深挖' if n >= 3 else ('⚠️ 警觉' if n == 2 else '✓')
        print(f'  [{n}次] {tag}  {flag}')
        if n >= 3:
            hot.append(tag)
    if not hot:
        print()
        print('  ✅ 暂无达到3次的问题')
    return hot


def deepdive(tag):
    """触发深挖（要写根因+机制修复）"""
    recs = [r for r in _all() if r['tag'] == tag]
    print('=' * 56)
    print(f'  深挖：{tag}（{len(recs)} 次）')
    print('=' * 56)
    for r in recs:
        print(f"  · [{r['ts'][:16]}] {r['desc']}")
    print()
    print('【必须回答（写进 issue-tracker-deepdive.md）】')
    print('  ① 根因（为什么会重复发生，不是"这次为什么"）')
    print('  ② 机制缺陷（不是个人失误）')
    print('  ③ 改什么机制（不是"下次注意"）')
    print('  ④ 防复发（怎么确保第4次不出现）')
    print('  ⑤ 固化在哪（否决清单/行为锁/定时检查）')


def list_all():
    for r in _all():
        print(f"[{r['ts'][:16]}] ({r['tag']}) {r['desc'][:70]}")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'log':
        desc = sys.argv[2]
        tag = 'general'
        if '--tag' in sys.argv:
            tag = sys.argv[sys.argv.index('--tag') + 1]
        log_issue(desc, tag)
    elif cmd == 'check':
        check()
    elif cmd == 'deepdive':
        deepdive(sys.argv[2])
    elif cmd == 'list':
        list_all()
