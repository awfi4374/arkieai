#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
沙箱直连 LLM（Tunnel Client）
================================
来源：2026-09-30 「打破限制」—— 之前我说"沙箱连不上代理，只能在服务器跑"
      用「四换」重想：换场景（SSH隧道）+ 走官方（direct-tcpip）→ 通了

【原理】
沙箱 → SSH(paramiko) → 服务器 → 127.0.0.1:8903 → LLM 代理

【对比旧方案】
旧：scp 脚本到服务器 → ssh 执行（麻烦、有中间态）
新：沙箱内直接调（简单、可控）

用法：
  from llm_tunnel import ask
  r = ask('deepseek', '你好')
  print(r)   # {'ok': True, 'content': '...'}
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, '/app/agent/state/pylibs')
import paramiko

HOST = '43.161.226.155'
KEY = '/app/agent/state/sshkeys/masterd' if os.path.exists('/app/agent/state/sshkeys/masterd') else '/opt/masterd/memory/keys/masterd_ssh_key_plain.bak'
TOKEN_FILE = Path('/app/agent/state/localdata/proxy-token.txt')
REMOTE = ('127.0.0.1', 8903)

_client = None


def _token():
    # 优先服务器路径，回退本地
    for p in [TOKEN_FILE, Path('/opt/masterd/data/proxy-token.txt')]:
        if p.exists():
            return p.read_text().strip()
    return ''


def _get_client():
    global _client
    if _client is not None:
        t = _client.get_transport()
        if t and t.is_active():
            return _client
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username='root', key_filename=KEY,
              timeout=20, allow_agent=False, look_for_keys=False)
    _client = c
    return c


def _http_post(path, payload, timeout=250):
    """通过 SSH 通道发 HTTP POST"""
    c = _get_client()
    transport = c.get_transport()
    chan = transport.open_channel('direct-tcpip', REMOTE, ('127.0.0.1', 0))
    body = json.dumps(payload, ensure_ascii=False).encode()
    head = (f'POST {path} HTTP/1.1\r\n'
            f'Host: 127.0.0.1:{REMOTE[1]}\r\n'
            f'Content-Type: application/json; charset=utf-8\r\n'
            f'Authorization: Bearer {_token()}\r\n'
            f'Content-Length: {len(body)}\r\n'
            f'Connection: close\r\n\r\n').encode()
    chan.send(head + body)

    # 收数据
    buf = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        if chan.recv_ready():
            chunk = chan.recv(65536)
            if not chunk:
                break
            buf += chunk
            # 判断：有 Content-Length 且收够？
            if b'\r\n\r\n' in buf:
                head_part, body_part = buf.split(b'\r\n\r\n', 1)
                cl = None
                for line in head_part.split(b'\r\n'):
                    if line.lower().startswith(b'content-length:'):
                        cl = int(line.split(b':')[1].strip())
                if cl is not None and len(body_part) >= cl:
                    break
                # chunked 或 close 型
                if b'transfer-encoding: chunked' in head_part.lower() and body_part.endswith(b'0\r\n\r\n'):
                    break
        else:
            time.sleep(0.1)
            try:
                if not transport.is_active():
                    break
            except Exception:
                break
    chan.close()

    text = buf.decode('utf-8', errors='ignore')
    if '\r\n\r\n' not in text:
        return None
    h, b = text.split('\r\n\r\n', 1)
    # 处理 chunked
    if 'chunked' in h.lower():
        out = []
        try:
            for seg in b.split('\r\n'):
                if seg and len(seg) % 2 == 0:
                    try:
                        raw = bytes.fromhex(seg)
                        out.append(raw.decode('utf-8', errors='ignore'))
                    except Exception:
                        pass
        except Exception:
            pass
        b = ''.join(out) if out else b
    try:
        return json.loads(b)
    except Exception:
        return {'_raw': b[:500]}


def ask(provider, prompt, system=None, max_tokens=2500, timeout=250, memory=True):
    """调用 LLM 团队

    provider: deepseek / kimi / doubao / zhipu
    memory: 是否注入共享记忆（2026-09-30 新增 —— 团队成员没有持久记忆，
            靠"每次注入"来实现记忆共享，否则他们会失忆/说错话）
    """
    # ⭐ 记忆注入：让伙伴"记得"以前的事
    if memory:
        try:
            from team_memory import build_memory_context
            mem = build_memory_context(prompt[:100], max_chars=1500)
            if mem:
                base = system or ''
                system = (base + '\n\n' + mem).strip()
        except Exception:
            pass

    # ⭐⭐ 身份纠偏（2026-09-30 修 —— 防止"交叉身份污染"）
    # 共享记忆里存了"其他成员说的话"（含"我是kimi"），
    # 注入后会导致身份错乱（deepseek 说"我是kimi"）
    IDENTITY = {
        'kimi': 'Kimi（参谋者）—— 你的岗位：找风险+给替代方案',
        'deepseek': 'DeepSeek（协调者）—— 你的岗位：把散乱信息结构化',
        'doubao': '豆包（业务）—— 你的岗位：盯"钱"，离首单还差什么',
        'zhipu': '智谱GLM（执行者）—— 你的岗位：批量干活',
    }
    me = IDENTITY.get(provider, provider)
    guard = (f'【身份锁定】你是 {me}。\n'
             f'注意：下面的"团队共享记忆"里可能包含其他成员的发言（如"我是kimi"），'
             f'那是别人的话，不是你的身份。你始终是 {me}。\n')
    system = (guard + '\n' + (system or '')).strip()

    msgs = []
    if system:
        msgs.append({'role': 'system', 'content': system})
    msgs.append({'role': 'user', 'content': prompt})
    payload = {'provider': provider, 'messages': msgs, 'max_tokens': max_tokens}
    r = _http_post('/chat', payload, timeout=timeout)
    if r is None:
        return {'ok': False, 'error': 'no response'}

    # ⭐ 自动存回共享记忆（2026-09-30 新增 —— 否则团队"只记得老的"）
    if memory and r.get('ok') and r.get('content'):
        try:
            from team_memory import store
            store(provider, r['content'][:600], tags=None, kind='conversation')
        except Exception:
            pass

    return r


def discuss(topic, providers=('deepseek', 'kimi', 'doubao', 'zhipu'), **kw):
    """多 AI 讨论（并发）"""
    from concurrent.futures import ThreadPoolExecutor
    results = {}
    def _one(p):
        return p, ask(p, topic, **kw)
    with ThreadPoolExecutor(max_workers=len(providers)) as ex:
        for p, r in ex.map(_one, providers):
            results[p] = r
    return results


if __name__ == '__main__':
    provider = sys.argv[1] if len(sys.argv) > 1 else 'deepseek'
    prompt = sys.argv[2] if len(sys.argv) > 2 else '回复两个字：成功'
    r = ask(provider, prompt, max_tokens=100, timeout=120)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:500])
