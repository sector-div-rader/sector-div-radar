import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

print("=== Gmail SMTP終極測試 ===")
user = os.environ.get('EMAIL_USER')
pwd = os.environ.get('EMAIL_PASS')
to = os.environ.get('EMAIL_TO', user)

print(f"USER: {user}")
print(f"PASS長度: {len(pwd) if pwd else 0}，應該係16")
print(f"TO: {to}")
print(f"PASS前4位: {pwd[:4] if pwd else 'None'}，檢查係唔係登入密碼")

if not user or not pwd:
    print("❌ Secrets未設定好")
    exit()

try:
    print("\n1. 連接 smtp.gmail.com:587...")
    server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
    server.starttls()
    print("✅ TLS連線成功")
    
    print("2. 登入Gmail...")
    server.login(user, pwd)
    print("✅ 登入成功，密碼正確")
    
    print("3. 發送測試郵件...")
    msg = MIMEMultipart()
    msg['From'] = user
    msg['To'] = to
    msg['Subject'] = "Radar Email測試成功"
    msg.attach(MIMEText("收到呢封代表EMAIL_PASS設定正確", 'plain', 'utf-8'))
    server.send_message(msg)
    server.quit()
    print(f"✅ Email已發送到 {to}，去Spam搵下")
    
except smtplib.SMTPAuthenticationError as e:
    print(f"❌ 密碼錯誤 535: {e}")
    print("原因：EMAIL_PASS唔係16位應用程式密碼，係你平時登入密碼")
    print("解決：Google帳戶 → 兩步驟驗證 → 應用程式密碼 → 重新產生")
    
except Exception as e:
    print(f"❌ 其他錯誤: {e}")