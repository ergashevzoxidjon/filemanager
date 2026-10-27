# Fayl-bot

Bu dastur o'rnatilgan kompyuterlardagi fayllarni telefondan, Telegram orqali boshqarish imkonini beradi. Bitta bot bilan bir nechta kompyuterni (ofis, uy va h.k.) boshqarish ham mumkin.

## Nima qila oladi

| Tugma / buyruq | Vazifasi |
|---|---|
| 💻 Kompyuter, `/kompyuter` | Qaysi kompyuter bilan ishlashni tanlash (🟢 onlayn, 🔴 o'chiq) |
| 📂 Disklar, `/disk` | Disk va papkalarni ko'rish, faylni olish |
| 🔎 Qidirish, `/izla so'z` | Fayl nomi bo'yicha qidirish |
| 🖥 Ekran, `/ekran` | Ekranni rasmga olish |
| ↗️ Ulashish | Yuborilgan fayl ostidagi tugma. Faylni istalgan chat, guruh yoki kanalga yuborish uchun |

- 49 MB dan katta fayllar 45 MB lik qismlarga bo'linadi (`fayl.001`, `fayl.002` ...). Ularni 7-Zip bilan birlashtirasiz.
- Bot faqat ruxsat berilgan Telegram ID'larga javob beradi.
- Bot faqat ko'rsatilgan papkalarni ko'radi. Fayllarni o'chirmaydi va o'zgartirmaydi.
- Kim qaysi faylni olgani `logs\bot.log` ga yoziladi.

## Qanday ishlaydi

```
 Telefon (Telegram)
        │
   Telegram serveri
        │  webhook
   hub.php  ← hostingda (cPanel), 24/7 ishlaydi
     ▲      ▲
     │      │   har bir kompyuter hub'dan o'z buyruqlarini so'rab turadi
  [ofis]  [uy]  ← bot.py (agent)
     │      │
     └──────┴──→ fayllarni to'g'ridan-to'g'ri Telegram'ga yuboradi
```

Bitta Telegram botni bir vaqtda faqat bitta dastur «tinglay» oladi. Shuning uchun xabarlarni hostingdagi kichik **hub** qabul qiladi va siz tanlagan kompyuterga uzatadi. Fayllar hub orqali o'tmaydi: har bir kompyuter ularni to'g'ridan-to'g'ri Telegram'ga yuklaydi. Shu sababli hostingga og'irlik tushmaydi.

Kompyuterlarga tashqaridan kirish ochilmaydi: ular hub'ga o'zlari murojaat qiladi. Shuning uchun "oq IP" ham, router sozlash ham kerak emas.

> Kompyuteringiz bitta bo'lsa, hub shart emas. `config.env` da `HUB_URL` ni bo'sh qoldiring, shunda bot o'zi ishlaydi.

---

## 1-qism. Bot va hub (bir marta)

1. **Bot yarating.** @BotFather → `/newbot` → token oling.
2. **Ulashishni yoqing.** @BotFather → `/setinline` → botingizni tanlang → istalgan matn yozing (masalan `Fayl`). Bu qadamsiz «↗️ Ulashish» tugmasi ishlamaydi.
3. **ID'ingizni bilib oling.** @userinfobot → `/start`.
4. **Kalitlar yarating.** `yangi_kalit.bat` ni har safar bosganda yangi kalit chiqadi. Kerak bo'ladi:
   - 1 ta `webhook_secret` uchun;
   - har bir kompyuter uchun 1 tadan kalit.
5. **Hostingga yuklang.** cPanel → File Manager → `public_html` ichida `filebot` papkasini oching va `hub` papkasidagi 3 ta faylni (`hub.php`, `config.example.php`, `.htaccess`) shu yerga yuklang.
6. `config.example.php` dan nusxa olib, uni **`config.php`** deb nomlang. Ichini to'ldiring:
   - `bot_token`: bot tokeni
   - `webhook_secret`: 4-qadamdagi kalit
   - `allowed_users`: [sizning ID'ingiz]
   - `agents`: kompyuterlar ro'yxati, ularning nomlari va kalitlari
7. Brauzerda quyidagi manzilni oching:
   `https://saytingiz.uz/filebot/hub.php?a=setup&key=WEBHOOK_SECRET`
   Ikkala qatorda ham **OK** chiqishi kerak.

Kompyuterlarning holatini ko'rish uchun: `https://saytingiz.uz/filebot/hub.php?a=status&key=WEBHOOK_SECRET`

> Hub uchun PHP 7.3 yoki undan yangi versiya, `pdo_sqlite` va `curl` kerak. Ular deyarli har bir cPanel hostingda bor. Domen **https** bilan ochilishi shart (cPanel'dagi bepul SSL yetarli).

## 2-qism. Har bir kompyuterga o'rnatish

1. Python 3.12 ni o'rnating. O'rnatishda **"Add Python to PATH"** belgisini qo'ying.
2. Shu papkani kompyuterga ko'chiring (masalan `C:\FileBot`).
3. **`1_install.bat`** ni bosing. Ochilgan `config.env` ni to'ldiring:
   - `BOT_TOKEN`, `ALLOWED_USERS`: hub'dagi bilan bir xil
   - `ROOTS`: masalan `D:\`, `FAVORITES`: masalan `D:\Zakazlar;D:\Maketlar`
   - `HUB_URL`: `https://saytingiz.uz/filebot/hub.php`
   - `AGENT_ID`: `config.php` dagi nom (masalan `ofis`)
   - `AGENT_KEY`: shu kompyuterning kaliti
   - `AGENT_NAME`: telefonda ko'rinadigan nom
4. **`2_test.bat`** ni bosing va Telegram'da botga `/kompyuter` yozing. Kompyuter 🟢 bo'lib ko'rinishi kerak.
5. **`3_autostart_yoqish.bat`** ni bosing. Shundan keyin bot yashirin ishlaydi va kompyuter yonganda o'zi ishga tushadi.

Botni to'xtatish uchun **`4_toxtatish.bat`** ni bosing.

## Telefonda ishlatish

1. «💻 Kompyuter» → kerakli kompyuterni tanlang. Disklar darhol chiqadi.
2. Papkalarni ochib, faylni bosing → «📥 Menga yuborish».
3. Fayl kelgach, uning ostidagi «↗️ Ulashish» tugmasini bosing → chatni tanlang → chiqqan faylni bosing. Fayl o'sha chatga yuboriladi.

## Kompyuter sozlamalari (muhim)

- **Uyqu rejimini o'chiring:** Sozlamalar → Tizim → Quvvat → "Sleep" = **Never**.
- **Avtomatik kirish:** `Win+R` → `netplwiz` → "Users must enter a user name and password" belgisini olib tashlang. Aks holda kompyuter qayta yongach, kimdir Windows'ga kirmaguncha bot ishga tushmaydi.
- **Ekran qulflansa** (Win+L), skrinshot qora chiqadi. Fayllar esa baribir ishlaydi.

## Muammolar

| Belgi | Yechim |
|---|---|
| Kompyuter 🔴 ko'rinyapti | Kompyuter yoniqmi, internet bormi? `logs\bot.log` ni tekshiring |
| logda "Hub AGENT_ID yoki AGENT_KEY ni qabul qilmadi" | `config.env` dagi va `config.php` dagi nom/kalit bir xil emas |
| "SOZLAMA XATOSI" | `config.env` da xato bor. Logda qaysi qatorligi yozilgan |
| Bot umuman javob bermayapti | `hub.php?a=status&key=...` ni oching va "Oxirgi xato" qatorini o'qing |
| «Ulashish» bosilganda hech narsa chiqmayapti | @BotFather'da `/setinline` qilinmagan |
| "Tugma eskirgan" | Bot qayta yongan. `/disk` ni qayta bosing |
| Token oshkor bo'lib qoldi | @BotFather → `/revoke`. Keyin yangi tokenni hamma joyga yozing va `?a=setup` ni qayta oching |

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `bot.py` | Kompyuterdagi agent: buyruqlar va tugmalar |
| `hub_client.py` | Agentni hub'ga ulaydi |
| `config.py` | `config.env` ni o'qiydi va tekshiradi |
| `explorer.py`, `search.py`, `screen.py` | Papkalarni ko'rish, qidiruv, skrinshot |
| `sender.py`, `shares.py` | Fayl yuborish (katta faylni bo'lish), «Ulashish» |
| `hub/hub.php` | Hostingdagi hub |
