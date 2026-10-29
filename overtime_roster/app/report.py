"""The HTML change report written next to every save or export (self-contained, opens in any browser)."""
import html

CSS = """body{margin:0;background:#141217;color:#ece7e3;font:14px/1.45 'Segoe UI',system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 20px 60px}
h1{font:800 34px/1 'Segoe UI',Arial,sans-serif;text-transform:uppercase;
letter-spacing:.5px;margin:0 0 6px}h1:after{content:'';display:block;width:84px;height:4px;background:#f05d4a;margin-top:12px}
h2{font:700 20px 'Segoe UI',Arial,sans-serif;text-transform:uppercase;
margin:30px 0 10px;color:#ff8a3d}table{border-collapse:collapse;width:100%;background:#1f1d22}
td,th{padding:6px 10px;border-bottom:1px solid #322d33;text-align:left;vertical-align:top}
th{color:#b9aea8;font-weight:600;text-transform:uppercase;font-size:12px;letter-spacing:.6px}
.k{color:#b9aea8;width:180px}.err{color:#ff7a6b}.warn{color:#e8b25a}.ok{color:#6fdc8c}
.exp{display:inline-block;background:#f26b1d;color:#141217;font-weight:700;padding:1px 8px;margin-left:8px;
font-size:12px;text-transform:uppercase}"""


def write(path, title, source, target, folder, crc, changes, issues, when):
    e = html.escape
    errors = [i for i in issues if i.level == 'error']
    rows = ''.join(f'<tr><td>{e(str(w))}</td><td>{e(str(o))}</td><td>{e(str(n))}</td></tr>' for w, o, n in changes)
    iss = ''.join(f'<tr><td class="{"err" if i.level == "error" else "warn"}">{e(i.level)}</td><td>{e(i.rule)}</td>'
                  f'<td>{e(i.message)}</td></tr>' for i in issues[:500])
    kind = {'save': 'New roster save', 'folder': 'Folder to copy to another PC'}.get(
        target, 'Roster file for the Overtime server')
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(title)} - Overtime Roster report</title>
<style>{CSS}</style></head><body><main>
<h1>{e(title)}</h1>
<table><tr><td class="k">Made</td><td>{e(when.strftime('%Y-%m-%d %H:%M'))}</td></tr>
<tr><td class="k">From</td><td>{e(source)}</td></tr><tr><td class="k">Saved as</td><td>{kind}</td></tr>
<tr><td class="k">Where</td><td>{e(folder)}</td></tr><tr><td class="k">Roster CRC</td><td><code>{e(crc)}</code></td></tr>
<tr><td class="k">Verify</td><td class="{'err' if errors else 'ok'}">{len(errors)} error(s), {len(issues) - len(errors)} warning(s)</td></tr>
</table>
<h2>Changes ({len(changes)})</h2>
<table><tr><th>What</th><th>Before</th><th>After</th></tr>{rows or '<tr><td colspan="3">No edits: the roster as it was loaded.</td></tr>'}</table>
<h2>Verify</h2>
<table><tr><th>Level</th><th>Rule</th><th>Message</th></tr>{iss or '<tr><td colspan="3" class="ok">Every rule passed.</td></tr>'}</table>
</main></body></html>"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc)
    return path
