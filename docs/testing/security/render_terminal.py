"""Render terminal.txt thành HTML kiểu terminal để chụp ảnh bằng Chrome headless.
  python render_terminal.py terminal.txt out.html [from_line] [to_line]
"""
import html, sys
lines = open(sys.argv[1], encoding='utf-8').read().splitlines()
a = int(sys.argv[3]) if len(sys.argv) > 3 else 0
b = int(sys.argv[4]) if len(sys.argv) > 4 else len(lines)
out = []
for l in lines[a:b]:
    e = html.escape(l)
    cls = 'pass' if l.startswith('[PASS]') else 'fail' if l.startswith('[FAIL]') else 'info' if l.startswith('[INFO]') else 'hd' if l.startswith('---') or l.startswith('TỔNG') or l.startswith('ABC') else ''
    out.append(f'<div class="{cls}">{e or "&nbsp;"}</div>')
open(sys.argv[2], 'w', encoding='utf-8').write('''<!doctype html><meta charset="utf-8"><style>
body{background:#0c0c0c;color:#cccccc;font:13px/1.45 Consolas,"Courier New",monospace;margin:0;padding:16px;white-space:pre-wrap;word-break:break-all}
.pass{color:#16c60c}.fail{color:#f14c4c}.info{color:#f9f1a5}.hd{color:#3b9cff;font-weight:bold}</style><body>''' + '\n'.join(out))
