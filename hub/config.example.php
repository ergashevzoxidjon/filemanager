<?php
// Hub sozlamalari. Bu faylni config.php nomi bilan nusxalang va to'ldiring.
return [
    // @BotFather bergan token (kompyuterlardagi config.env dagi BOT_TOKEN bilan bir xil)
    'bot_token' => 'BU_YERGA_TOKEN_YOZING',

    // Telegram -> hub so'rovlarini tekshirish uchun maxfiy satr.
    // Faqat lotin harf, raqam, _ va - (16-64 belgi). Shu satr setup/status sahifalari paroli ham.
    'webhook_secret' => 'BU_YERGA_UZUN_MAXFIY_SATR',

    // Botdan foydalana oladigan odamlarning Telegram ID'lari
    'allowed_users' => [123456789],

    // Kompyuterlar ro'yxati.
    //   kalit (ofis, uy ...) = kompyuterdagi config.env dagi AGENT_ID (1-10 lotin harf/raqam)
    //   key                  = shu kompyuterdagi config.env dagi AGENT_KEY (kamida 16 belgi)
    'agents' => [
        'ofis' => ['name' => 'Ofis kompyuteri', 'key' => 'BU_YERGA_OFIS_KALITI'],
        'uy'   => ['name' => 'Uy kompyuteri',   'key' => 'BU_YERGA_UY_KALITI'],
    ],

    // 49 MB dan katta fayllar uchun (my.telegram.org -> API development tools). Ixtiyoriy.
    'api_id' => 0,
    'api_hash' => '',

    // Vaqt mintaqasi ("oxirgi aloqa" vaqti uchun)
    'timezone' => 'Asia/Tashkent',

    // Agar hosting manzilni noto'g'ri aniqlasa, to'liq https manzilni yozing:
    // 'public_url' => 'https://saytingiz.uz/filebot/hub.php',
];
