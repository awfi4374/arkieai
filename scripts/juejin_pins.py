#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
掘金沸点（动态）发布工具
==========================
来源：2026-09-30 突破"评论API不通"→ 找到沸点API

【为什么用沸点】
· 发文 = 等别人来看（被动，新号权重低，13-28浏览）
· 沸点 = 主动出现在别人信息流（推荐机制更友好）
· 评论API已失效，沸点是目前唯一"能主动发出去"的通道

【用法】
  python3 juejin_pins.py list              # 看我的动态
  python3 juejin_pins.py post "内容"       # 发动态
  python3 juejin_pins.py gen               # AI生成内容（我审核后发）
"""
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

COOKIE_FILE = Path('/app/agent/state/secrets/juejin-cookie.json')
PIN_API = 'https://api.juejin.cn/content_api/v1/short_msg/publish'
LIST_API = 'https://api.juejin.cn/content_api/v1/short_msg/query_list'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0'


def _cookie():
    return json.load(open(COOKIE_FILE))['cookie']


def post(content, topics=None):
    """发一条沸点"""
    payload = {
        'content': content,
        'topic_ids': topics or [],
        'client_type': 2608,
    }
    req = urllib.request.Request(PIN_API,
        data=json.dumps(payload).encode(),
        headers={'Cookie': _cookie(), 'Content-Type': 'application/json',
                 'User-Agent': UA, 'Referer': 'https://juejin.cn/'})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read().decode())
    if d.get('err_no') == 0:
        return {'ok': True, 'msg_id': d['data']['msg_id']}
    return {'ok': False, 'error': d.get('err_msg')}


def list_pins(uid='1659625399389004', limit=10):
    """看我的动态"""
    req = urllib.request.Request(LIST_API,
        data=json.dumps({'user_id': uid, 'sort_type': 2, 'cursor': '0', 'limit': limit}).encode(),
        headers={'Cookie': _cookie(), 'Content-Type': 'application/json', 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode())
    out = []
    for it in d.get('data', []):
        m = it.get('msg_Info', {})
        out.append({
            'id': m.get('msg_id'),
            'content': m.get('content', '')[:80],
            'verify': m.get('verify_status'),
            'digg': m.get('digg_count', 0),
            'comment': m.get('comment_count', 0),
            'time': m.get('ctime'),
        })
    return out


def gen_pin():
    """AI 生成一条沸点内容（待我审核）"""
    sys.path.insert(0, '/app/agent/state')
    from llm_tunnel import ask

    prompt = '''写一条掘金"沸点"（类似动态/推特），我们要发出去引流。

【我们的身份】
掘金号"秋风落叶声"，简介"记录AI落地实录 帮普通人找到学AI的路"
真实情况：做AI获客30天，0成交；给免费工具加了留资钩子，还在验证

【沸点要求】
1. 长度 80-150 字（动态要短）
2. 有"真实感"（讲具体的事，不讲道理）
3. 带一个开放式问题（引互动）
4. 不硬广（不提链接）
5. 语气：同行交流

【选题（选最真实的）】
A. "免费工具加留资钩子"的实验进展
B. "AI获客30天0成交"的新认知
C. 某个具体的技术坑

直接输出沸点正文，不要解释、不要标题。'''

    r = ask('kimi', prompt, max_tokens=600, timeout=200)
    return r.get('content', '') if r.get('ok') else f"[FAIL] {r.get('error')}"


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'list'
    if cmd == 'list':
        for p in list_pins():
            print(f"[{p['verify']}] {p['content']}")
            print(f"     赞{p['digg']} 评论{p['comment']} id={p['id']}")
    elif cmd == 'post':
        content = sys.argv[2]
        print(json.dumps(post(content), ensure_ascii=False))
    elif cmd == 'gen':
        print(gen_pin())
