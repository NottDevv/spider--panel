# 🕷️ Spider Panel — راهنمای استقرار کامل روی JustRunMy.App

> **اجرای پنل حرفه‌ای VLESS Reality + WS + XHTTP فقط با یک فایل ZIP — بدون کارت اعتباری، بدون دردسر!**

<div align="center">

![Platform](https://img.shields.io/badge/Platform-JustRunMy.App-0ea5e9?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Async-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Protocols](https://img.shields.io/badge/Reality%20%7C%20VLESS%20WS%20%7C%20XHTTP%20%7C%20OpenVPN-Supported-22c55e?style=for-the-badge)

</div>

---

## 🗺️ نقشه‌ی راه

```
┌──────────────────┐   HTTPS / WSS   ┌───────────────────────────────┐
│  کلاینت شما      │ ──────────────▶ │  JustRunMy.App  (پورت 80)     │
│  V2Ray / NekoBox │                 │   └── Spider Panel (FastAPI)  │
│                  │ ◀────────────── │        └── 💾 /app/data       │
└──────────────────┘   کانفیگ / SUB  └───────────────────────────────┘

┌──────────────────┐   TCP Raw       ┌───────────────────────────────┐
│  کلاینت Reality  │ ──────────────▶ │  JustRunMy.App  (پورت TCP)    │
│  (TLS伪装)       │                 │   └── Xray (Reality Inbound)  │
└──────────────────┘                 └───────────────────────────────┘
```

این پنل **دو نوع اتصال** رو پشتیبانی می‌کنه:
- **VLESS WS/TLS و XHTTP:** از طریق پورت HTTPS (پورت 80 کانتینر) کار می‌کنن
- **VLESS Reality:** از طریق پورت TCP خام (نیاز به باز کردن پورت اضافی در پلتفرم)

---

## 🧰 پیش‌نیازها

| مورد | وضعیت |
|---|---|
| اکانت JustRunMy.App (لایه رایگان) | ✅ بدون کارت اعتباری |
| فایل ZIP پروژه | ✅ از [مخزن رسمی](https://github.com/amirappleidfd-stack/spider--panel) |
| زمان لازم | ⏱️ حدود ۵ دقیقه |

---

## 📦 گام ۱ — آماده‌سازی فایل ZIP

1. آخرین نسخه‌ی پروژه را از [اینجا](https://github.com/amirappleidfd-stack/spider--panel) دانلود کنید.
2. اگر کد را تغییر داده‌اید، دوباره ZIP کنید؛ **به‌طوری که فایل‌ها در ریشه‌ی ZIP باشند** (نه داخل یک پوشه تودرتو):

```
spider-panel.zip
├── main.py
├── pages.py
├── relay_vless.py
├── xhttp_siz10.py
├── shared.py
├── openvpn_pki.py
├── requirements.txt
├── static/
└── worker/
```

> [!TIP]
> پلتفرم به‌صورت خودکار `requirements.txt` را نصب می‌کند؛ نیازی به بیلد دستی نیست.

---

## ☁️ گام ۲ — ساخت اپلیکیشن

1. وارد داشبورد JustRunMy.app شوید → **Create application**
2. روش استقرار: **Zip Upload**
3. فایل ZIP را آپلود کنید.
4. بیلد شروع می‌شود و با پیام **«Runny needs a few details»** متوقف می‌شود — حالا نوبت گام ۳ است. 👇

---

## 🔐 گام ۳ — متغیرهای محیطی (قلب استقرار!)

> [!WARNING]
> مقادیر زیر **نمونه** هستند. هرگز مقادیر واقعی خود را داخل فایل عمومی GitHub کامیت نکنید!

| متغیر | مقدار نمونه | ضروری | توضیح |
|---|---|:---:|---|
| `PORT` | `80` | ✅ | پورت گوش‌دادن اپ — باید با پورت پلتفرم یکسان باشد |
| `ADMIN_PASSWORD` | `My$tr0ng@Pass!42` | ✅ | رمز ورود به پنل ادمین (بلافاصله عوض کنید) |
| `SECRET_KEY` | `Kx7vQ9mLz2Wp8Rtydkkf6Hd1Jc4Ga0E` | ✅ | امضای کوکی سشن؛ با مقدار ثابت، بعد از ری‌استارت همه لاگ‌اوت نمی‌شوند |
| `RAILWAY_PUBLIC_DOMAIN` | `xxx.jrnm.app` | ✅ | دامنه‌ی عمومی شما؛ برای ساخت کانفیگ‌های WS/XHTTP |
| `DATA_DIR` | `/app/data` | ✅ | مسیر ذخیره‌ی وضعیت — باید روی ولوم ماندگار باشد |
| `PYTHONUNBUFFERED` | `1` | ⭕ | نمایش زنده‌ی لاگ‌ها بدون بافر |

> [!TIP]
> برای ساخت `SECRET_KEY` تصادفی:
> ```bash
> python -c "import secrets; print(secrets.token_urlsafe(32))"
> ```

> [!IMPORTANT]
>متغیر **`RAILWAY_PUBLIC_DOMAIN` حیاتی‌ترین متغیر است!** این مقدار برای ساخت کانفیگ‌های VLESS WS/XHTTP استفاده می‌شود. اگر اشتباه باشد، کانفیگ‌ها وصل نمی‌شوند. مقدار دقیق را از بخش **Public access** پلتفرم بردارید.

---

## 🌐 گام ۴ — پورت و دستور اجرا

**بخش Ports:**

| پورت | پروتکل | Application Port | توضیح |
|:---:|:---:|:---:|---|
| `80` | HTTPS | `80` | برای WS/TLS و XHTTP |

> [!NOTE]
> برای Reality نیاز به پورت TCP اضافی دارید — در گام ۶ توضیح داده شده.

**بخش Run command:**

```bash
pip install -r requirements.txt && python main.py
```

---

## 💾 گام ۵ — ولوم ماندگار (خداحافظی با کانفیگ‌های گمشده!)

در بخش **Volume mapping** یک ولوم بسازید:

| Mount Path | هدف |
|---|---|
| `/app/data` | ذخیره‌ی دائمی `spider_state.json`، کلیدهای Reality و تاریخچه‌ها |

**چرا؟** اپلیکیشن به‌صورت پیش‌فرض در `/data` می‌نویسد که حافظه‌ی موقت کانتینر است و با هر ری‌استارت پاک می‌شود. با ترکیب `DATA_DIR=/app/data` + ولوم، همه‌چیز بین ری‌استارت‌ها و Redeployها **پایدار** می‌ماند.

---

## 🔓 گام ۶ — تنظیم VLESS Reality (اختیاری ولی قدرتمند)

پروتکل VLESS Reality یکی از **امن‌ترین و سخت‌ترین** پروتکل‌ها برای شناسایی است. ترافیک شما شبیه ترافیک عادی HTTPS به سایت‌های معتبر (مثل Apple CDN) به نظر می‌رسد.

### مرحله ۱: باز کردن پورت TCP

1. در تنظیمات اپ JustRunMy.app → بخش **Container ports** → **Add port**
2. پورت `8443` با پروتکل **TCP** (نه HTTPS) اضافه کنید
3. سپس **Restart** کنید
4. به بخش **Public access** بروید و **Network address** را یادداشت کنید:
   ```
   xxx.xxx.xxx.xxx:12345
   ```
   - آی پی: `xxx.xxx.xxx.xxx`
   - پورت عمومی: ``12345`
   - پورت کانتینر: `8443`

### مرحله ۲: ساخت Inbound در پنل

1. وارد پنل شوید (با `ADMIN_PASSWORD`)
2. در تب Inbounds باید ** Reality+XHTTP پیش‌فرض ** را ویرایش کنید.
3. تنظیمات زیر را وارد کنید:

| فیلد | مقدار | توضیح |
|---|---|---|
| **نام اینباند** | `Reality-XHTTP` | نام دلخواه |
| **پورت اینباند** | `8443` | پورت کانتینر که در گام ۶ باز کردید |
| **پروتکل** | `vless` | - |
| **امنیت** | `reality` | - |
| **دامنه (EXTERNAL DOMAIN)** | `167.235.244.201` یا خالی | IP عمومی سرور |
| **EXTERNAL PORT** | `12345` | پورت عمومی از Public access |
| **SNI** | `is1-ssl.mzstatic.com` | ⚠️ **تغییر ندهید!** پنل به‌طور خودکار از SNI‌های تست‌شده استفاده می‌کند |
| **SERVER NAMES (SNI)** | `is1-ssl.mzstatic.com` | همان SNI |
| **DESTINATION** | `is1-ssl.mzstatic.com:443` | SNI + پورت 443 |
| **PUBLIC KEY** | (خودکار تولید شده) | دست نزنید |
| **PRIVATE KEY** | (خودکار تولید شده) | دست نزنید |
| **SHORT IDs** | (خودکار تولید شده) | دست نزنید |
| **SPIDERX** | `/` | - |
| **شبکه (Network)** | `xhttp` | برای XHTTP |
| **PATH** | `/` | - |
| **MODE** | `stream-up` یا `packet-up` | حالت XHTTP |

> [!IMPORTANT]
>متغیر **SNI را تغییر ندهید!** پنل از سایت‌های معتبر مثل Apple CDN (`is1-ssl.mzstatic.com`) استفاده می‌کند که بهترین عملکرد را دارند. اگر SNI را تغییر دهید و سایت اشتباه انتخاب شود، کانفیگ وصل نمی‌شود.

### مرحله ۳: ساخت کاربر و تست

1. تب **Users** → **Create User**
2. یک کاربر بسازید و اینباند Reality را به آن اختصاص دهید
3. کانفیگ را کپی کنید — باید شبیه این باشد:
   ```
   vless://<uuid>@167.235.244.201:52365?encryption=none&security=reality&sni=is1-ssl.mzstatic.com&type=xhttp&mode=stream-up&fp=chrome&pbk=<public-key>&sid=<short-id>&spx=<spiderx>#Spider-Reality
   ```
4. در V2RayNG یا NekoBox تست کنید

---

## 🎯 گام ۷ — تنظیم VLESS WS/TLS (ساده‌تر و پایدارتر)

این پروتکل **خودکار آماده است** و نیازی به تنظیم دستی ندارد. فقط مطمئن شوید:

1. متغیر**`RAILWAY_PUBLIC_DOMAIN` درست تنظیم شده باشد** (گام ۳)
2. اینباند **VLESS WS** از قبل ساخته شده باشد (پنل به‌طور خودکار می‌سازد)
3. کانفیگ باید شبیه این باشد:
   ```
   vless://<uuid>@a55254-9735.d.jrnm.app:443?encryption=none&security=tls&type=ws&host=a55254-9735.d.jrnm.app&path=/ws/<uuid>&sni=a55254-9735.d.jrnm.app&fp=chrome&alpn=http/1.1#Spider-WS
   ```

> [!TIP]
> اگر کانفیگ WS وصل نشد، اول `RAILWAY_PUBLIC_DOMAIN` را چک کنید — ۹۰٪ مشکلات از همین متغیر است.

---

## 🧪 گام ۸ — اجرای نهایی و صحت‌سنجی

1. پس از اعمال تنظیمات، اپ را **Restart / Deploy** کنید.
2. باز کنید: `https://<your-domain>.jrnm.app`
3. با `ADMIN_PASSWORD` وارد شوید.
4. **بلافاصله رمز عبور را از تنظیمات پنل تغییر دهید**
5. یک کاربر بسازید و لینک SUB را بگیرید:
   ```
   https://<your-domain>.jrnm.app/sub/<username>
   ```
6. لینک را در کلاینت (V2RayNG / NekoBox / Shadowrocket) تست کنید. 🎉

---

## 🛡️ امنیت و حریم خصوصی

> [!WARNING]
> **پسورد پیش‌فرض `admin` است!** بلافاصله بعد از اولین لاگین، رمز را تغییر دهید.

### اقدامات امنیتی ضروری:

1. **تغییر رمز عبور** — بلافاصله بعد از اولین لاگین
2. **استفاده از `SECRET_KEY` قوی** — برای امنیت sessionها
3. **محدود کردن دسترسی به داشبورد** — URL داشبورد را با کسی به اشتراک نگذارید
4. **پشتیبان‌گیری از کلیدهای Reality** — در صورت پاک شدن `/app/data`، کلیدها از بین می‌روند و کانفیگ‌ها کار نمی‌کنند

### نکات حریم خصوصی:

- ✅ **هیچ phone-home یا تله‌متری وجود ندارد** (برخلاف پروژه‌های مشابه)
- ✅ ترافیک کاربران رمزنگاری شده و قابل شنود نیست
- ✅ پروتکل Reality از سایت‌های معتبر برای SNI استفاده می‌کند که شناسایی را سخت می‌کند

---

## 🧯 عیب‌یابی

| علامت | علت | درمان |
|---|---|---|
| خطای **Bad Gateway** بعد از بیلد | ناهماهنگی پورت اپ و پلتفرم | `PORT=8000` + پورت پلتفرم `8000` + بررسی لاگ‌ها |
| کانفیگ WS وصل نمی‌شود | `RAILWAY_PUBLIC_DOMAIN` اشتباه | دامنه دقیق از Public access را وارد کنید |
| کانفیگ Reality وصل نمی‌شود | پورت TCP باز نشده یا SNI اشتباه | پورت TCP را اضافه کنید و SNI را تغییر ندهید |
| لینک SUB با `localhost` ساخته می‌شود | متغیر دامنه ست نشده | `RAILWAY_PUBLIC_DOMAIN=<your-domain>` |
| کانفیگ‌ها بعد از ری‌استارت می‌پَرند | نوشتن در حافظه موقت | `DATA_DIR=/app/data` + ساخت ولوم روی همان مسیر |
| سشن‌ها بعد از هر ری‌استارت باطل می‌شوند | سکرت موقت | ست‌کردن `SECRET_KEY` ثابت |
| خطای `ModuleNotFoundError` | ZIP با پوشه تودرتو | فایل‌ها در ریشه‌ی ZIP باشند |
| لاگ خالی یا بدون تغییر | بافر لاگ | `PYTHONUNBUFFERED=1` |

---

## 📌 خلاصه‌ی پیکربندی نهایی (Quick Reference)

```env
# ── شبکه ────────────────────────────────────
PORT=80
RAILWAY_PUBLIC_DOMAIN=xxx.jrnm.app
PYTHONUNBUFFERED=1

# ── احراز هویت ─────────────────────────────
ADMIN_PASSWORD=<رمز_قوی_خودتان>
SECRET_KEY=<رشته_تصادفی_۳۲+_کاراکتری>

# ── ماندگاری ────────────────────────────────
DATA_DIR=/app/data
```

```text
Run Command : pip install -r requirements.txt && python main.py
Port (HTTPS): 8000
Port (TCP)  : 8443 (برای Reality)
Volume      : /app/data
```

---

## 📊 مقایسه پروتکل‌ها

| پروتکل | امنیت | پیچیدگی راه‌اندازی | پایداری | پیشنهاد |
|---|:---:|:---:|:---:|---|
| **VLESS Reality + XHTTP** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | بهترین برای استفاده بلندمدت |
| **VLESS WS + TLS** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ساده‌ترین و سریع‌ترین |
| **VLESS XHTTP** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | تعادل بین امنیت و سهولت |

---

## 🎯 نکات پیشرفته

### تغییر SNI (فقط در صورت لزوم)

اگر واقعاً نیاز به تغییر SNI دارید، **DESTINATION** را عوض کنید — SNI و SERVER NAMES به‌طور خودکار آپدیت می‌شوند:

```
DESTINATION = www.speedtest.net:443
```

سایت‌های پیشنهادی برای SNI:
- `is1-ssl.mzstatic.com` (Apple CDN — بهترین گزینه)
- `www.speedtest.net`
- `dl.google.com`
- `www.cloudflare.com`

### محدود کردن IP هم‌زمان

در تنظیمات کاربر، می‌توانید `concurrent_connections` را محدود کنید تا از اشتراک‌گذاری اکانت جلوگیری شود.

### انتخاب Cloudflare Worker (اختیاری)

برای پنهان کردن IP سرور اصلی، می‌توانید از Cloudflare Worker استفاده کنید:
1. یک Worker در Cloudflare بسازید
2. در تب **Worker** پنل، API Token و Account ID را وارد کنید
3. کاربران با `proxy_ip_enabled=true` از طریق Worker وصل می‌شوند

---

## 🔗 لینک‌های مفید

- [مستندات VLESS Reality](https://github.com/XTLS/REALITY)

---

<div align="center">

**ساخته‌شده با ❤️ برای جامعه‌ی Spider Panel — اگر این راهنما کمک کرد، یک ⭐ یادتون نره!**

</div>
