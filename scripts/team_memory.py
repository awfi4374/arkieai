#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队成员记忆共享 v1
========================
用户要求："你和你的同伴可以做到记忆共享"
         "每次和他们对话时，他们都可以找到以前的聊天记忆"

【原理】
伙伴没有持久记忆 → 但我们可以"每次注入"
① 调用前：检索相关记忆（facts.jsonl + 对话历史）
② 注入：把记忆塞进系统提示
③ 调用：伙伴就能"看到"以前的记忆
④ 调用后：把本次对话存进共享记忆库

【效果】
伙伴 A 说的话 → 存库 → 伙伴 B 也能看到
= 真正的"记忆共享"

【用法】
  from team_memory import ask_with_memory
  ask_with_memory('kimi', '任务', tags=['掘金'])

  python3 team_memory.py --store "kimi" "说了什么"
  python3 team_memory.py --recall "关键词"
  python3 team_memory.py --stats
"""
import json
import sys
import re
from pathlib import Path
from datetime import datetime

STATE = Path('/app/agent/state')
SHARED = STATE / 'learning' / 'team-shared-memory.jsonl'
FACTS = STATE / 'learning' / 'facts.jsonl'

# ===== 共享记忆读写 =====

def store(speaker, content, tags=None, kind='conversation'):
    """存一条共享记忆"""
    entry = {
        'ts': datetime.now().isoformat(),
        'speaker': speaker,          # 谁说的（kimi/deepseek/masterd/user）
        'kind': kind,                # conversation/decision/lesson
        'tags': tags or [],
        'content': content,
    }
    SHARED.parent.mkdir(parents=True, exist_ok=True)
    with SHARED.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return entry


def extract_terms(query):
    """提取关键词（支持中文，按2-4字切分）"""
    terms = set()
    # 1. 空格/标点分词
    for t in re.split(r'[\s,，、。？！?!；;：:（）()\[\]【】]+', query):
        t = t.strip()
        if len(t) >= 2:
            terms.add(t)
    # 2. 对长词做 2-gram 切分（中文无空格）
    for t in list(terms):
        if len(t) >= 4:
            for i in range(len(t) - 1):
                g = t[i:i+2]
                if len(g) == 2:
                    terms.add(g)
    # 3. 去掉单字和超短
    return [t for t in terms if len(t) >= 2]


def recall(query, limit=8):
    """检索共享记忆（关键词匹配）"""
    if not SHARED.exists():
        return []
    terms = extract_terms(query)
    hits = []
    for line in SHARED.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        text = e.get('content', '') + ' ' + ' '.join(e.get('tags', []))
        score = sum(1 for t in terms if t in text)
        if score > 0:
            hits.append((score, e))
    hits.sort(key=lambda x: -x[0])
    return [e for _, e in hits[:limit]]


def build_memory_context(query, max_chars=2000):
    """构造"记忆上下文"（注入给伙伴）"""
    parts = []

    # 1. 共享记忆（伙伴们说过的）
    shared = recall(query, limit=6)
    if shared:
        parts.append("【团队共享记忆（近期相关对话）】")
        for e in shared:
            ts = e['ts'][:16].replace('T', ' ')
            parts.append(f"  [{ts}] {e['speaker']}: {e['content'][:150]}")

    # 2. 原子事实（项目事实）
    if FACTS.exists():
        kw = extract_terms(query)
        facts = []
        for line in FACTS.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            try:
                f = json.loads(line)
            except Exception:
                continue
            if any(k in f.get('fact', '') for k in kw):
                facts.append(f['fact'])
        if facts:
            parts.append("\n【相关项目事实】")
            for f in facts[:8]:
                parts.append(f"  · {f[:110]}")

    text = '\n'.join(parts)
    return text[:max_chars]


def stats():
    if not SHARED.exists():
        print("共享记忆库：空")
        return
    entries = [json.loads(l) for l in SHARED.read_text(encoding='utf-8').splitlines() if l.strip()]
    by_speaker = {}
    for e in entries:
        by_speaker[e['speaker']] = by_speaker.get(e['speaker'], 0) + 1
    print(f"共享记忆：{len(entries)} 条")
    for s, c in sorted(by_speaker.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")


if __name__ == '__main__':
    if '--store' in sys.argv:
        i = sys.argv.index('--store')
        speaker = sys.argv[i+1]
        content = sys.argv[i+2]
        store(speaker, content)
        print(f"✅ 已存：{speaker}: {content[:50]}")
    elif '--recall' in sys.argv:
        q = sys.argv[sys.argv.index('--recall') + 1]
        hits = recall(q)
        print(f"找到 {len(hits)} 条：")
        for e in hits:
            print(f"  [{e['speaker']}] {e['content'][:100]}")
    elif '--context' in sys.argv:
        q = sys.argv[sys.argv.index('--context') + 1]
        print(build_memory_context(q))
    else:
        stats()
