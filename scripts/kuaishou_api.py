#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手数据接口（Kuaishou API）
==================================
来源：2026-10-01 打通（不用登录，直接拿热榜数据）

【突破】
快手 GraphQL 接口是开放的！
· 不用 Cookie
· 不用登录
· 直接 POST https://www.kuaishou.com/graphql

【关键】
· operationName: brilliantData
· page: brilliant（热榜）
· 字段要用 inline fragment（... on PhotoEntity）

【用法】
  python3 kuaishou_api.py hot           # 拿热榜
  python3 kuaishou_api.py hot --limit 50
  python3 kuaishou_api.py search "关键词"  # 搜索（待验证）
"""
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

URL = 'https://www.kuaishou.com/graphql'
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Origin': 'https://www.kuaishou.com',
    'Referer': 'https://www.kuaishou.com/brilliant',
}

# 完整字段（含 inline fragment）
HOT_QUERY = '''query brilliantData($page: String) {
  brilliantData(page: $page) {
    feeds {
      photo {
        ... on PhotoEntity {
          caption
        }
      }
    }
  }
}'''


def _post(query, variables, op_name, retries=3):
    """POST 到快手（带重试 + 延时，应对风控）"""
    import time as _t
    import random
    for attempt in range(retries):
        try:
            payload = {"operationName": op_name, "variables": variables, "query": query}
            req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                         headers=HEADERS, method='POST')
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt < retries - 1:
                wait = 3 + random.random() * 5  # 3-8秒随机
                _t.sleep(wait)
            else:
                raise
    return {}


def hot(limit=20):
    """拿快手热榜"""
    out = []
    pcursor = ""
    while len(out) < limit:
        try:
            d = _post(HOT_QUERY, {"page": "brilliant", "pcursor": pcursor}, "brilliantData")
        except Exception as e:
            print(f'[错误] {type(e).__name__}: {str(e)[:100]}')
            break
        data = d.get('data', {}).get('brilliantData', {})
        feeds = data.get('feeds', [])
        if not feeds:
            break
        for f in feeds:
            p = f.get('photo', {})
            if p.get('caption'):
                out.append({
                    'caption': p.get('caption', ''),
                    'like': p.get('likeCount', 0),
                    'view': p.get('viewCount', 0),
                    'user': (p.get('user') or {}).get('name', ''),
                    'id': p.get('id', ''),
                })
        pcursor = data.get('pcursor', '')
        if not pcursor:
            break
    return out[:limit]


def analysis(items):
    """简单分析：什么类型的内容流量高"""
    import re
    print('=' * 60)
    print(f'  快手热榜分析（{len(items)} 条）')
    print('=' * 60)
    print()
    # 提取标签
    tags = {}
    for it in items:
        for t in re.findall(r'#([^\s#]+)', it['caption']):
            tags[t] = tags.get(t, 0) + 1
    print('【高频标签】')
    for t, c in sorted(tags.items(), key=lambda x: -x[1])[:15]:
        print(f'  {c}次  #{t}')
    print()
    print('【内容示例】')
    for it in items[:10]:
        print(f"  · {it['caption'][:50]}")
        print(f"    作者[{it['user']}] 赞{it['like']} 播{it['view']}")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'hot'
    if cmd == 'hot':
        limit = 20
        if '--limit' in sys.argv:
            limit = int(sys.argv[sys.argv.index('--limit') + 1])
        items = hot(limit)
        print(f'✅ 拿到 {len(items)} 条热榜视频\n')
        analysis(items)
        # 存档
        f = Path('/app/agent/state/kuaishou-data') / f'hot-{datetime.now().strftime("%Y%m%d-%H%M")}.json'
        f.parent.mkdir(exist_ok=True)
        f.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n✅ 已存档: {f}')
