"""Đo WebSocket đồng thời: mở N kết nối vào /ws/table_<id>/ (khách) và đo thời gian bắt tay, tỉ lệ thành công,
độ trễ ping/pong, và độ trễ nhận sự kiện new_order broadcast.

  python ws_load.py --host 127.0.0.1:8030 --n 200 --hold 20 --tokens tokens.json

Kênh bàn cần token phiên bàn (?token=): tokens.json do make_tokens.py tạo (khoá TABLES).
"""
import argparse, asyncio, json, statistics, time, urllib.request
import websockets


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p / 100))] if v else float('nan')


async def client(i, host, res, hold, evt, tokens):
    table = (i % 30) + 1
    t0 = time.perf_counter()
    try:
        async with websockets.connect(f'ws://{host}/ws/table_{table}/?token={tokens[str(table)]}', open_timeout=20) as ws:
            res['connect_ms'].append((time.perf_counter() - t0) * 1000)
            res['ok'] += 1
            t1 = time.perf_counter()
            await ws.send(json.dumps({'type': 'ping'}))
            await asyncio.wait_for(ws.recv(), 20)
            res['ping_ms'].append((time.perf_counter() - t1) * 1000)
            evt.set_ready()
            end = time.perf_counter() + hold
            while time.perf_counter() < end:
                try:
                    m = json.loads(await asyncio.wait_for(ws.recv(), max(0.1, end - time.perf_counter())))
                    if m.get('type') == 'new_order' and table == res['target']:
                        res['event_ms'].append((time.perf_counter() - res['sent']) * 1000)
                except asyncio.TimeoutError:
                    break
    except Exception as e:
        res['fail'] += 1
        res['errors'].append(type(e).__name__ + ':' + str(e)[:60])


class Ready:
    def __init__(self): self.n = 0
    def set_ready(self): self.n += 1


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1:8030'); ap.add_argument('--n', type=int, default=200); ap.add_argument('--hold', type=int, default=20); ap.add_argument('--tokens', default='tokens.json')
    a = ap.parse_args()
    tokens = json.load(open(a.tokens))['TABLES']
    res = {'ok': 0, 'fail': 0, 'connect_ms': [], 'ping_ms': [], 'event_ms': [], 'errors': [], 'target': 1, 'sent': 0}
    evt = Ready()
    tasks = [asyncio.create_task(client(i, a.host, res, a.hold, evt, tokens)) for i in range(a.n)]
    while evt.n + res['fail'] < a.n:
        await asyncio.sleep(0.2)
    await asyncio.sleep(1)
    # kích một đơn mới ở bàn target -> các client của bàn đó phải nhận new_order
    loop = asyncio.get_running_loop()
    def post():
        req = urllib.request.Request(f'http://{a.host}/api/orders/', method='POST',
                                     data=json.dumps({'table_id': 1, 'items': [{'menu_item_id': 1, 'quantity': 1}]}).encode(),
                                     headers={'Content-Type': 'application/json', 'X-Table-Id': '1', 'X-Table-Token': tokens['1']})
        try: urllib.request.urlopen(req, timeout=20).read()
        except Exception as e: print('post order error', e)
    res['sent'] = time.perf_counter()
    await loop.run_in_executor(None, post)
    await asyncio.gather(*tasks)
    out = {'n': a.n, 'connected': res['ok'], 'failed': res['fail'],
           'connect_ms_p50': round(statistics.median(res['connect_ms']), 1) if res['connect_ms'] else None,
           'connect_ms_p95': round(pct(res['connect_ms'], 95), 1), 'connect_ms_max': round(max(res['connect_ms'] or [0]), 1),
           'ping_ms_p50': round(statistics.median(res['ping_ms']), 1) if res['ping_ms'] else None, 'ping_ms_p95': round(pct(res['ping_ms'], 95), 1),
           'broadcast_receivers': len(res['event_ms']), 'broadcast_ms_p95': round(pct(res['event_ms'], 95), 1), 'errors': sorted(set(res['errors']))[:5]}
    print(json.dumps(out, ensure_ascii=False, indent=2))

asyncio.run(main())
