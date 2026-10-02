#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""团队状态检查（Team State Check）
======================================
来源：2026-09-30 用户建议
"每次和他们沟通的时候，先问一下他们的状态回来了没有？
 如果没回来，就让他们把状态调回来，然后再讨论"

【为什么需要】
· 团队成员没有持久记忆，靠"注入"模拟
· 但注入可能失败/记忆可能过期 → 团队"状态没回来"
· 状态没回来就讨论 → 说错话（如"凌晨写文档=逃避"）

【流程】
① 注入记忆后，先问"你的状态/记忆回来了吗？"
② 如果没回来 → 重新注入（补更完整的上下文）
③ 状态确认后 → 才开始正式讨论
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/app/agent/state')
import os
_sandbox = '/app/agent/state'
_server = '/opt/masterd/memory'
STATE = Path(_sandbox) if os.path.isdir(_sandbox) and os.access(_sandbox, os.W_OK) else Path(_server)
LOG = STATE / 'logs' / 'team-state-check.log'
LOG.parent.mkdir(parents=True, exist_ok=True)

STATUS_CHECK_PROMPT = '''【状态自检（回答前先做，不要跳过）】

⚠️ 重要：下面的对话里会给你【团队共享记忆】。
你必须【先用记忆里的信息回答】，不要自己猜、不要说"上下文未提供"。
记忆里有：主线、真实数据（粉丝/留资/首单）、团队问题。

请先回答以下问题，确认你的"状态回来了"：

1. 你是 MasterD 团队的哪位成员？你的岗位职责是什么？
2. 我们团队现在的主线是什么？（唯一指标是什么？）
3. 我们团队现在最真实的数据是什么？（粉丝/留资/首单）
4. 我们团队最大的问题是什么？

【回答格式】
状态：[回来了 / 没回来]
1. ____
2. ____
3. ____
4. ____

如果任何一项你答不上来或不确定 → 回答"没回来"，不要编。
'''


def check_state(provider, verbose=True):
    """检查一个团队成员的"状态"是否回来了"""
    from llm_tunnel import ask

    r = ask(provider, STATUS_CHECK_PROMPT, max_tokens=500, timeout=180)
    if not r.get('ok'):
        return {'ok': False, 'provider': provider, 'error': r.get('error'), 'state': 'unknown'}

    content = r.get('content', '')
    back = ('状态：回来了' in content.replace(' ', '') or
            '状态:回来了' in content.replace(' ', '') or
            '状态：已恢复' in content)
    # 关键内容校验（不只看他说"回来了"）
    has_mainline = any(k in content for k in ['首单', '获客'])
    has_truth = any(k in content for k in ['0', '零']) and any(k in content for k in ['粉丝', '留资', '掘金', '浏览'])

    ok = back and has_mainline and has_truth
    result = {
        'ok': True,
        'provider': provider,
        'state': 'back' if ok else 'NOT_BACK',
        'raw': content[:500],
        'checks': {'said_back': back, 'knows_mainline': has_mainline, 'knows_truth': has_truth},
    }

    # 记录
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': datetime.now().isoformat(), **result}, ensure_ascii=False) + '\n')

    if verbose:
        print(f"[{provider}] 状态: {'✅ 回来了' if ok else '🔴 没回来'}")
        print(f"  自称回来:{back} | 知道主线:{has_mainline} | 知道真实数据:{has_truth}")
        print(f"  原文: {content[:200]}")
        print()

    return result


def ensure_state(provider, max_retry=2):
    """确保状态回来（没回来就补注入，再问）"""
    for attempt in range(max_retry + 1):
        r = check_state(provider, verbose=(attempt == 0))
        if r.get('state') == 'back':
            return r
        if attempt < max_retry:
            print(f"  🔧 [{provider}] 状态没回来 → 补注入记忆（第{attempt+1}次重试）")
            try:
                import team_memory_sync
                team_memory_sync.sync_today()
                team_memory_sync.sync_current_state()
            except Exception as e:
                print(f"     同步失败: {e}")
    return r


def check_all(providers=('kimi', 'deepseek', 'doubao')):
    """检查所有成员"""
    results = []
    for p in providers:
        results.append(check_state(p))
    print('=' * 56)
    for r in results:
        s = '✅' if r.get('state') == 'back' else '🔴'
        print(f'  {s} {r["provider"]}')
    return results


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd == 'all':
        check_all()
    elif cmd == 'ensure':
        p = sys.argv[2] if len(sys.argv) > 2 else 'kimi'
        ensure_state(p)
    else:
        check_state(cmd)
