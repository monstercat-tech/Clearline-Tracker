"""
Email open tracker.
Logs pixel hits to opens.json and serves a stats dashboard.

GET /pixel?id=LEAD_ID&name=COMPANY_NAME&email=EMAIL  -> 1x1 GIF + log
GET /stats                                            -> HTML dashboard
GET /stats.json                                       -> raw JSON
"""

import os, io, json, datetime, threading
from flask import Flask, request, send_file, jsonify, Response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'opens.json')
_lock = threading.Lock()

PIXEL_GIF = bytes([
    0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,
    0x80,0x00,0x00,0xff,0xff,0xff,0x00,0x00,0x00,0x21,
    0xf9,0x04,0x00,0x00,0x00,0x00,0x00,0x2c,0x00,0x00,
    0x00,0x00,0x01,0x00,0x01,0x00,0x00,0x02,0x02,0x44,
    0x01,0x00,0x3b,
])


def load_opens():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    return []


def save_opens(opens):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(opens, f, indent=2, ensure_ascii=False)


def log_open(lead_id, company_name, email, ip, user_agent):
    entry = {
        'lead_id':      lead_id,
        'company_name': company_name,
        'email':        email,
        'opened_at':    datetime.datetime.utcnow().isoformat() + 'Z',
        'ip':           ip,
        'user_agent':   user_agent,
    }
    with _lock:
        opens = load_opens()
        opens.append(entry)
        save_opens(opens)


@app.route('/pixel')
def pixel():
    lead_id      = request.args.get('id',    'unknown')
    company_name = request.args.get('name',  '')
    email        = request.args.get('email', '')
    ip           = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua           = request.user_agent.string

    log_open(lead_id, company_name, email, ip, ua)

    return send_file(io.BytesIO(PIXEL_GIF), mimetype='image/gif', max_age=0)


@app.route('/stats.json')
def stats_json():
    opens = load_opens()
    summary = {}
    for row in opens:
        lid = row['lead_id']
        if lid not in summary:
            summary[lid] = {
                'lead_id':      lid,
                'company_name': row.get('company_name', ''),
                'email':        row.get('email', ''),
                'opens':        0,
                'first_open':   row['opened_at'],
                'last_open':    row['opened_at'],
            }
        summary[lid]['opens'] += 1
        if row['opened_at'] > summary[lid]['last_open']:
            summary[lid]['last_open'] = row['opened_at']

    results = sorted(summary.values(), key=lambda x: x['first_open'], reverse=True)
    return jsonify({'total_opens': len(opens), 'unique_leads': len(results), 'leads': results})


@app.route('/stats')
def stats_html():
    opens = load_opens()
    summary = {}
    for row in opens:
        lid = row['lead_id']
        if lid not in summary:
            summary[lid] = {
                'company': row.get('company_name', lid),
                'email':   row.get('email', ''),
                'opens':   0,
                'first':   row['opened_at'][:16].replace('T', ' '),
            }
        summary[lid]['opens'] += 1

    leads = sorted(summary.values(), key=lambda x: x['first'], reverse=True)
    total_opens  = len(opens)
    unique_leads = len(leads)

    rows_html = ''.join(
        f"<tr><td>{l['company']}</td><td>{l['email']}</td>"
        f"<td style='text-align:center'>{l['opens']}</td>"
        f"<td>{l['first']} UTC</td></tr>"
        for l in leads
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
  <title>Clearline Email Opens</title>
  <style>
    body {{ font-family: sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #333; }}
    h1 {{ font-size: 22px; margin-bottom: 4px; }}
    .meta {{ color: #888; font-size: 14px; margin-bottom: 28px; }}
    .stats {{ display: flex; gap: 32px; margin-bottom: 32px; }}
    .stat {{ background: #f5f5f5; border-radius: 8px; padding: 18px 28px; }}
    .stat .n {{ font-size: 36px; font-weight: 700; color: #1a1a1a; }}
    .stat .label {{ font-size: 13px; color: #666; margin-top: 2px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th {{ text-align: left; padding: 10px 12px; background: #f0f0f0; border-bottom: 2px solid #ddd; }}
    td {{ padding: 9px 12px; border-bottom: 1px solid #eee; }}
    tr:hover td {{ background: #fafafa; }}
  </style>
</head>
<body>
  <h1>Clearline Web Co. — Email Opens</h1>
  <div class="meta">Refreshes every 60s &nbsp;·&nbsp; <a href="/stats.json">JSON</a></div>
  <div class="stats">
    <div class="stat"><div class="n">{total_opens}</div><div class="label">Total opens</div></div>
    <div class="stat"><div class="n">{unique_leads}</div><div class="label">Unique leads opened</div></div>
  </div>
  <table>
    <thead><tr><th>Company</th><th>Email</th><th>Opens</th><th>First opened</th></tr></thead>
    <tbody>{rows_html if rows_html else '<tr><td colspan="4" style="color:#aaa;padding:20px">No opens yet.</td></tr>'}</tbody>
  </table>
  <script>setTimeout(()=>location.reload(), 60000)</script>
</body>
</html>"""
    return Response(html, mimetype='text/html')


@app.route('/')
def index():
    return '<a href="/stats">Stats dashboard</a>'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
