# 只改 send_email 同 main，其他 function 照用 V14.5
def send_email(sub, body, csv, merged):
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.application import MIMEApplication

    # 1. 置中純文字
    text_html = f'<div style="text-align:center;font-family:Consolas,monospace;white-space:pre-wrap;line-height:1.6;">{body}</div>'

    # 2. HTML大表（中文冇問題）
    rows = ''.join([f"<tr><td>{m['ticker']}</td><td>{m['name']}</td><td>{m['levels']}</td><td>{m['dir']}</td><td>{m['inds']}</td><td>{m['category']}</td></tr>" for m in merged])
    table_html = f"""
    <div style="text-align:center;margin-top:30px;">
    <table style="margin:auto;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;">
    <tr style="background:#2c3e50;color:white;"><th>Ticker</th><th>名稱</th><th>時段</th><th>方向</th><th>指標</th><th>類別</th></tr>
    {rows}
    </table></div>
    """

    msg = MIMEMultipart('mixed')
    msg['Subject'] = sub; msg['From'] = EMAIL_CONFIG['sender_email']; msg['To'] = EMAIL_CONFIG['receiver_email']
    msg.attach(MIMEText(text_html + table_html, 'html', 'utf-8'))

    with open(csv,'rb') as f:
        att = MIMEApplication(f.read(), _subtype='csv')
        att.add_header('Content-Disposition','attachment',filename=os.path.basename(csv))
        msg.attach(att)

    s = smtplib.SMTP(EMAIL_CONFIG['smtp_server'],EMAIL_CONFIG['smtp_port'])
    s.starttls(); s.login(EMAIL_CONFIG['sender_email'],EMAIL_CONFIG['sender_password']); s.send_message(msg); s.quit()

def main():
    sigs = []
    for t,i in ALL.items(): sigs += scan_asset(t,i)
    mg = merge_signals(sigs); cf = detect_conflicts(sigs)
    r,te,cy,ix,ra,op,tr = analyze(sigs)
    body = build_text(r,te,cy,ix,ra,op,tr,mg,cf)
    ns = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M')
    csv = save_csv(mg, ns)
    send_email(f"[Radar V14.6] Risk{r} {ra} - {ns[:8]}", body, csv, mg)