#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手全时段·全维度测查（Kuaishou Time-Slot Analysis）
==========================================================
来源：2026-10-01 董事长要求
"每天4个时段（6/12/18/24点），做过全面彻底的、全维度的测查"

【测什么】
① 时段：每个时段快手热榜"什么内容火"
② 内容类型：干货/情感/搞笑/痛点/剧情
③ 标签分布：什么标签高频
④ 时长偏好：短视频 vs 长视频
⑤ 互动率：哪些内容评论/点赞高

【怎么测】
· 每个时段抓热榜（brilliantData）
· 分析：标签/题材/互动
· 存进"时段数据库"
· 累积一周 → 出"时段规律报告"

【用法】
  python3 ks_timeslot.py once       # 抓一次
  python3 ks_timeslot.py loop       # 常驻（按4个时段自动抓）
  python3 ks_timeslot.py report     # 出报告
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/app/agent/state')
import urllib.request

STATE = Path('/app/agent/state')
DATA = STATE / 'ks-timeslot'
DATA.mkdir(exist_ok=True)
DB = DATA / 'timeslot-data.jsonl'

# 抓取用的（已验证可用）
API_URL = 'https://www.kuaishou.com/graphql'
import random
_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
]
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': _USER_AGENTS[0],
    'Origin': 'https://www.kuaishou.com',
    'Referer': 'https://www.kuaishou.com/brilliant',
}
QUERY = '''query brilliantData($page: String) {
  brilliantData(page: $page) {
    feeds {
      photo {
        ... on PhotoEntity {
          caption
          likeCount
          viewCount
          duration
        }
      }
    }
  }
}'''

# 时段定义
SLOTS = {6: '早6点(晨间)', 12: '午12点(午休)', 18: '晚18点(下班)', 24: '夜24点(深夜)'}

# 内容分类关键词
CATEGORIES = {
    '干货教程': ['怎么', '教你', '方法', '技巧', '步骤', '学会', '攻略', '教程'],
    '情感共鸣': ['妈妈', '爸爸', '父母', '孩子', '家', '爱', '眼泪', '心疼'],
    '搞笑娱乐': ['搞笑', '笑死', '沙雕', '整活', '反转', '离谱'],
    '生活记录': ['记录', '日常', '生活', 'vlog', '一天', '日常'],
    '美食': ['吃', '美食', '做饭', '菜', '味道', '好吃'],
    '游戏': ['游戏', '王者', '吃鸡', '光遇', '原神', '开黑'],
    '明星娱乐': ['明星', '偶像', '追星', '演唱会', '剧'],
    '赚钱副业': ['赚钱', '副业', '收入', '月入', '生意', '老板', '创业'],
}


def fetch_hot(limit=50):
    """抓热榜"""
    items = []
    for page in ['brilliant']:
        payload = {"operationName": "brilliantData",
                   "variables": {"page": page},
                   "query": QUERY}
        for attempt in range(3):
            try:
                h = dict(HEADERS)
                h['User-Agent'] = random.choice(_USER_AGENTS)
                req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(),
                                             headers=h, method='POST')
                with urllib.request.urlopen(req, timeout=25) as r:
                    d = json.loads(r.read().decode())
                feeds = d.get('data', {}).get('brilliantData', {}).get('feeds', [])
                for f in feeds:
                    p = f.get('photo', {})
                    if p.get('caption'):
                        items.append({
                            'caption': p.get('caption', ''),
                            'like': p.get('likeCount', 0),
                            'view': p.get('viewCount', 0),
                            'duration': p.get('duration', 0),
                            
                        })
                break
            except Exception as e:
                print(f'  第{attempt+1}次失败: {type(e).__name__}')
                time.sleep(20)
        time.sleep(3)
        if len(items) >= limit:
            break
    return items[:limit]


def classify(caption):
    """内容分类"""
    for cat, kws in CATEGORIES.items():
        if any(k in caption for k in kws):
            return cat
    return '其他'


def extract_tags(caption):
    """提取标签"""
    return re.findall(r'#([^\s#]+)', caption)


def analyze(items):
    """分析"""
    from collections import Counter
    cats = Counter()
    tags = Counter()
    durations = []
    likes = []
    for it in items:
        cats[classify(it['caption'])] += 1
        for t in extract_tags(it['caption']):
            tags[t] += 1
        try:
            d = int(it.get('duration') or 0)
            if d:
                durations.append(d)
        except Exception:
            pass
        try:
            lk = int(it.get('like') or 0)
            if lk:
                likes.append(lk)
        except Exception:
            pass
    return {
        'count': len(items),
        'categories': dict(cats.most_common()),
        'top_tags': dict(tags.most_common(10)),
        'avg_duration': sum(durations) / len(durations) if durations else 0,
        'avg_like': sum(likes) / len(likes) if likes else 0,
        'max_like': max(likes) if likes else 0,
    }


def capture(slot=None):
    """抓一次并归档"""
    now = datetime.now()
    hour = now.hour
    if slot is None:
        # 判断属于哪个时段
        slot = min(SLOTS.keys(), key=lambda s: abs(s - hour))
    name = SLOTS.get(slot, f'{slot}点')

    print(f'[{now.strftime("%H:%M")}] 抓取热榜（时段: {name}）...')
    items = fetch_hot(50)
    if not items:
        print('  ❌ 没抓到数据')
        return None

    ana = analyze(items)
    rec = {
        'ts': now.isoformat(),
        'slot': slot,
        'slot_name': name,
        'hour': hour,
        'data': ana,
        'samples': [it['caption'][:60] for it in items[:20]],
    }
    with open(DB, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    print(f'  ✅ 抓到 {ana["count"]} 条')
    print(f'  内容分布: {ana["categories"]}')
    print(f'  热门标签: {list(ana["top_tags"].keys())[:5]}')
    print(f'  平均时长: {ana["avg_duration"]:.0f}ms')
    return rec


def loop():
    """常驻：4个时段自动抓"""
    while True:
        now = datetime.now()
        h, m = now.hour, now.minute
        # 命中时段（±2分钟内）
        for slot in SLOTS:
            target_h = 0 if slot == 24 else slot
            if h == target_h and m < 5:
                capture(slot)
                time.sleep(3600)   # 抓完等1小时
                break
        time.sleep(120)   # 每2分钟检查


def report():
    """出报告"""
    if not DB.exists():
        print('（无数据）')
        return
    recs = [json.loads(l) for l in DB.read_text().split('\n') if l.strip()]
    print('=' * 60)
    print(f'  快手时段测查报告（{len(recs)} 次抓取）')
    print('=' * 60)
    from collections import Counter, defaultdict
    by_slot = defaultdict(list)
    for r in recs:
        by_slot[r['slot_name']].append(r)
    for slot_name, rs in by_slot.items():
        print(f'\n── {slot_name}（{len(rs)}次）──')
        cats = Counter()
        for r in rs:
            for c, n in r['data']['categories'].items():
                cats[c] += n
        print(f'  内容分布: {dict(cats.most_common(5))}')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'once'
    if cmd == 'once':
        capture()
    elif cmd == 'loop':
        loop()
    elif cmd == 'report':
        report()
