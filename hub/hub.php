<?php
/**
 * Fayl-bot HUB — bitta Telegram bot orqali bir nechta kompyuterni boshqarish.
 *
 * Telegram xabarlarni shu faylga yuboradi (webhook). Hub ularni foydalanuvchi
 * tanlagan kompyuterning navbatiga qo'yadi. Har bir kompyuterdagi agent (bot.py)
 * ?a=poll orqali o'z navbatini olib turadi va javobni to'g'ridan-to'g'ri Telegram'ga yuboradi.
 *
 * Manzillar:
 *   hub.php?a=webhook            — Telegram uchun (qo'lda ochilmaydi)
 *   hub.php?a=poll&agent=ofis    — agentlar uchun (X-Agent-Key sarlavhasi bilan)
 *   hub.php?a=setup&key=SECRET   — bir marta ochiladi: webhook va buyruqlarni o'rnatadi
 *   hub.php?a=status&key=SECRET  — qaysi kompyuter onlayn ekanini ko'rish
 *
 * Talablar: PHP 7.3+, pdo_sqlite, curl. Oddiy cPanel hostingda ishlaydi.
 */

declare(strict_types=1);

const ONLINE_SEC = 60;   // shuncha sekund ichida aloqa bo'lgan kompyuter "onlayn"
const POLL_WAIT  = 20;   // eski agentlar uchun: javobni shuncha sekund kutib turamiz
// Yangi agentlar (v=2) kutmaydi: hub darhol javob beradi, agent o'zi 1-3 soniyada qayta so'raydi.
// Shunda hostingdagi PHP jarayoni har bir so'rovda millisekundlargina band bo'ladi.
const QUEUE_TTL  = 120;  // 2 daqiqada olinmagan xabar eskirgan hisoblanadi

$cfgFile = __DIR__ . '/config.php';
if (!is_file($cfgFile)) {
    http_response_code(500);
    exit('config.php topilmadi. config.example.php dan nusxa oling.');
}
$CFG = require $cfgFile;
date_default_timezone_set($CFG['timezone'] ?? 'Asia/Tashkent');
$API = rtrim($CFG['api_base'] ?? 'https://api.telegram.org', '/') . '/bot' . $CFG['bot_token'] . '/';

// ─────────────────────────── Yordamchi funksiyalar ───────────────────────────

function db(): PDO
{
    static $pdo = null;
    global $CFG;
    if ($pdo) {
        return $pdo;
    }
    $dir = $CFG['data_dir'] ?? (__DIR__ . '/data');
    if (!is_dir($dir)) {
        mkdir($dir, 0700, true);
    }
    if (!is_file("$dir/.htaccess")) {
        file_put_contents("$dir/.htaccess", "Require all denied\nDeny from all\n");
    }
    $pdo = new PDO("sqlite:$dir/hub.sqlite", null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $pdo->exec('PRAGMA busy_timeout = 5000');
    $pdo->exec('PRAGMA journal_mode = WAL');
    $pdo->exec('CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL, payload TEXT NOT NULL, created INTEGER NOT NULL)');
    $pdo->exec('CREATE INDEX IF NOT EXISTS queue_agent ON queue(agent, id)');
    $pdo->exec('CREATE TABLE IF NOT EXISTS seen (agent TEXT PRIMARY KEY, ts INTEGER NOT NULL)');
    $pdo->exec('CREATE TABLE IF NOT EXISTS choice (user_id INTEGER PRIMARY KEY, agent TEXT NOT NULL)');
    // O'rnatuvchi orqali o'zi ro'yxatdan o'tgan kompyuterlar (admin Telegram'da tasdiqlaydi)
    $pdo->exec('CREATE TABLE IF NOT EXISTS reg_agents (id TEXT PRIMARY KEY, name TEXT NOT NULL,
                key TEXT NOT NULL, host TEXT, status TEXT NOT NULL, created INTEGER NOT NULL)');
    return $pdo;
}

function tg(string $method, array $params): ?array
{
    global $API;
    $ch = curl_init($API . $method);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode($params, JSON_UNESCAPED_UNICODE),
        CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 15,
    ]);
    $res = curl_exec($ch);
    curl_close($ch);
    return $res ? json_decode($res, true) : null;
}

function json_out(array $data, int $code = 200): void
{
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

function h(string $s): string
{
    return htmlspecialchars($s, ENT_QUOTES | ENT_HTML5, 'UTF-8');
}

/** Tasdiqlangan barcha kompyuterlar: config.php dagilar + o'rnatuvchi orqali qo'shilganlar */
function agents(): array
{
    global $CFG;
    static $cache = null;
    if ($cache !== null) {
        return $cache;
    }
    $list = $CFG['agents'] ?? [];
    foreach (db()->query("SELECT id, name, key FROM reg_agents WHERE status = 'ok' ORDER BY created") as $r) {
        if (!isset($list[$r['id']])) {
            $list[$r['id']] = ['name' => $r['name'], 'key' => $r['key']];
        }
    }
    return $cache = $list;
}

function reg_agent(string $id): ?array
{
    $st = db()->prepare('SELECT * FROM reg_agents WHERE id = ?');
    $st->execute([$id]);
    return $st->fetch(PDO::FETCH_ASSOC) ?: null;
}

/** O'rnatuvchiga joylanadigan ro'yxatdan o'tish kodi. webhook_secret dan hosil qilinadi. */
function enroll_code(): string
{
    global $CFG;
    return substr(hash_hmac('sha256', 'filebot-enroll', (string)$CFG['webhook_secret']), 0, 24);
}

function admins(): array
{
    global $CFG;
    return $CFG['allowed_users'] ?? [];
}

function agent_name(string $a): string
{
    return agents()[$a]['name'] ?? $a;
}

function is_admin(int $uid): bool
{
    global $CFG;
    return in_array($uid, $CFG['allowed_users'] ?? [], true);
}

function data_dir(): string
{
    global $CFG;
    $dir = $CFG['data_dir'] ?? (__DIR__ . '/data');
    if (!is_dir($dir)) {
        mkdir($dir, 0700, true);
    }
    return $dir;
}

/** "Oxirgi aloqa" fayl vaqti sifatida saqlanadi - ma'lumotlar bazasiga yozmaslik uchun */
function seen_file(string $a): string
{
    return data_dir() . '/seen_' . preg_replace('/[^a-z0-9]/', '', $a);
}

function last_seen(string $a): int
{
    $f = seen_file($a);
    clearstatcache(true, $f);
    if (is_file($f)) {
        return (int)filemtime($f);
    }
    $st = db()->prepare('SELECT ts FROM seen WHERE agent = ?');  // eski versiyadan qolgan qiymat
    $st->execute([$a]);
    return (int)($st->fetchColumn() ?: 0);
}

/** Navbatda xabar bormi - bazani ochmasdan, belgi faylidan bilamiz */
function flag_file(string $a): string
{
    return data_dir() . '/queue_' . preg_replace('/[^a-z0-9]/', '', $a);
}

function is_online(string $a): bool
{
    return time() - last_seen($a) < ONLINE_SEC;
}

function mark_seen(string $a): void
{
    $f = seen_file($a);
    clearstatcache(true, $f);
    if (!is_file($f) || time() - (int)filemtime($f) >= 10) {  // har 10 soniyada bir marta yozamiz
        @touch($f);
    }
}

function chosen(int $uid): ?string
{
    $st = db()->prepare('SELECT agent FROM choice WHERE user_id = ?');
    $st->execute([$uid]);
    $a = $st->fetchColumn();
    if ($a && isset(agents()[$a])) {
        return $a;
    }
    return count(agents()) === 1 ? array_key_first(agents()) : null;
}

function choose(int $uid, string $a): void
{
    db()->prepare('INSERT OR REPLACE INTO choice(user_id, agent) VALUES(?, ?)')->execute([$uid, $a]);
}

function enqueue(string $a, array $update): void
{
    db()->prepare('INSERT INTO queue(agent, payload, created) VALUES(?, ?, ?)')
        ->execute([$a, json_encode($update, JSON_UNESCAPED_UNICODE), time()]);
    @touch(flag_file($a));
}

function seen_text(string $a): string
{
    $ts = last_seen($a);
    return $ts ? date('d.m.Y H:i', $ts) : 'hech qachon';
}

function main_keyboard(): array
{
    return [
        'keyboard' => [
            [['text' => '💻 Kompyuter']],
            [['text' => '📂 Disklar'], ['text' => '🔎 Qidirish']],
            [['text' => '🖥 Ekran'], ['text' => 'ℹ️ Yordam']],
        ],
        'resize_keyboard' => true,
    ];
}

function pc_list_markup(int $uid): array
{
    $cur = chosen($uid);
    $rows = [];
    foreach (agents() as $id => $a) {
        $icon = is_online($id) ? '🟢' : '🔴';
        $mark = $id === $cur ? ' ✅' : '';
        $row = [['text' => "$icon {$a['name']}$mark", 'callback_data' => "hub|pc:$id"]];
        if (reg_agent($id)) {  // o'rnatuvchi orqali qo'shilganini o'chirish mumkin
            $row[] = ['text' => '🗑', 'callback_data' => "hub|rm:$id"];
        }
        $rows[] = $row;
    }
    return ['inline_keyboard' => $rows];
}

function send_pc_list(int $chat, int $uid, string $title = '💻 <b>Kompyuterni tanlang</b>'): void
{
    tg('sendMessage', [
        'chat_id' => $chat,
        'text' => "$title\n\n🟢 onlayn · 🔴 o'chiq yoki internetsiz",
        'parse_mode' => 'HTML',
        'reply_markup' => pc_list_markup($uid),
    ]);
}

// ─────────────────────────── Webhook: Telegram'dan kelgan xabar ───────────────────────────

function handle_webhook(): void
{
    global $CFG;
    $secret = $_SERVER['HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN'] ?? '';
    if (!hash_equals((string)$CFG['webhook_secret'], $secret)) {
        http_response_code(403);
        exit('forbidden');
    }
    $u = json_decode((string)file_get_contents('php://input'), true);
    if (!is_array($u)) {
        exit('bad');
    }
    if (isset($u['callback_query'])) {
        route_callback($u);
    } elseif (isset($u['inline_query'])) {
        route_inline($u);
    } elseif (isset($u['message'])) {
        route_message($u);
    }
    echo 'ok';
}

function route_message(array $u): void
{
    $m = $u['message'];
    $uid = (int)($m['from']['id'] ?? 0);
    $chat = (int)$m['chat']['id'];
    $private = ($m['chat']['type'] ?? '') === 'private';
    $text = trim((string)($m['text'] ?? ''));
    $cmd = strtolower((string)preg_replace('/@\w+$/', '', explode(' ', $text)[0]));

    if (!is_admin($uid)) {
        if ($private) {
            tg('sendMessage', ['chat_id' => $chat, 'parse_mode' => 'HTML',
                'text' => "⛔ Ruxsat yo'q.\nSizning ID: <code>$uid</code>"]);
        }
        return;
    }
    if ($cmd === '/kompyuter' || $text === '💻 Kompyuter') {
        send_pc_list($chat, $uid);
        return;
    }
    $a = chosen($uid);
    if ($a === null) {
        send_pc_list($chat, $uid, '💻 <b>Avval kompyuterni tanlang</b>');
        return;
    }
    if (!is_online($a)) {
        send_pc_list($chat, $uid, '💤 <b>' . h(agent_name($a)) . '</b> hozir javob bermayapti '
            . '(oxirgi aloqa: ' . seen_text($a) . ").\nBoshqa kompyuterni tanlang:");
        return;
    }
    enqueue($a, $u);
}

function route_callback(array $u): void
{
    $cq = $u['callback_query'];
    $uid = (int)$cq['from']['id'];
    $data = (string)($cq['data'] ?? '');

    if (!is_admin($uid)) {
        tg('answerCallbackQuery', ['callback_query_id' => $cq['id'], 'text' => "⛔ Ruxsat yo'q", 'show_alert' => true]);
        return;
    }
    $parts = explode('|', $data, 2);
    $prefix = $parts[0];
    $rest = $parts[1] ?? '';

    if ($prefix === 'hub' && preg_match('/^(ok|no|rm|rmy):([a-z0-9]{1,10})$/', $rest, $mm)) {
        handle_admin_action($cq, $mm[1], $mm[2]);
        return;
    }
    if ($prefix === 'hub' && strpos($rest, 'pc:') === 0) {
        $a = substr($rest, 3);
        if (!isset(agents()[$a])) {
            tg('answerCallbackQuery', ['callback_query_id' => $cq['id'], 'text' => 'Bunday kompyuter yo\'q']);
            return;
        }
        choose($uid, $a);
        $online = is_online($a);
        tg('answerCallbackQuery', ['callback_query_id' => $cq['id'], 'text' => '✅ ' . agent_name($a)]);
        if (isset($cq['message'])) {
            tg('editMessageReplyMarkup', [
                'chat_id' => $cq['message']['chat']['id'],
                'message_id' => $cq['message']['message_id'],
                'reply_markup' => pc_list_markup($uid),
            ]);
        }
        tg('sendMessage', [
            'chat_id' => $uid,
            'parse_mode' => 'HTML',
            'text' => '✅ Tanlandi: <b>' . h(agent_name($a)) . '</b>'
                . ($online ? '' : "\n\n💤 Bu kompyuter hozir javob bermayapti (oxirgi aloqa: " . seen_text($a) . ').'),
            'reply_markup' => main_keyboard(),
        ]);
        if ($online) {  // darhol disklar ro'yxatini ko'rsatamiz
            enqueue($a, ['update_id' => 0, 'message' => [
                'message_id' => $cq['message']['message_id'] ?? 0,
                'date' => time(),
                'chat' => ['id' => $uid, 'type' => 'private'],
                'from' => $cq['from'],
                'text' => '/disk',
                'entities' => [['type' => 'bot_command', 'offset' => 0, 'length' => 5]],
            ]]);
        }
        return;
    }

    if (!isset(agents()[$prefix])) {
        tg('answerCallbackQuery', ['callback_query_id' => $cq['id'], 'show_alert' => true,
            'text' => 'Bu tugma eskirgan. «💻 Kompyuter» ni bosing.']);
        return;
    }
    if (!is_online($prefix)) {
        tg('answerCallbackQuery', ['callback_query_id' => $cq['id'], 'show_alert' => true,
            'text' => '💤 ' . agent_name($prefix) . ' hozir javob bermayapti (oxirgi aloqa: ' . seen_text($prefix) . ')']);
        return;
    }
    $u['callback_query']['data'] = $rest;
    enqueue($prefix, $u);
}

function handle_admin_action(array $cq, string $act, string $id): void
{
    $r = reg_agent($id);
    $answer = function (string $t) use ($cq) {
        tg('answerCallbackQuery', ['callback_query_id' => $cq['id'], 'text' => $t, 'show_alert' => true]);
    };
    if (!$r) {
        $answer("Bu kompyuter topilmadi (config.php orqali qo'shilganlarni bu yerdan o'chirib bo'lmaydi).");
        return;
    }
    $edit = function (string $text, ?array $markup = null) use ($cq) {
        if (!isset($cq['message'])) {
            return;
        }
        $p = ['chat_id' => $cq['message']['chat']['id'], 'message_id' => $cq['message']['message_id'],
              'text' => $text, 'parse_mode' => 'HTML'];
        if ($markup) {
            $p['reply_markup'] = $markup;
        }
        tg('editMessageText', $p);
    };
    $name = h($r['name']);
    if ($act === 'ok') {
        db()->prepare("UPDATE reg_agents SET status = 'ok' WHERE id = ?")->execute([$id]);
        $answer('✅ Qabul qilindi');
        $edit("✅ <b>$name</b> qo'shildi. Bir daqiqada «💻 Kompyuter» ro'yxatida 🟢 bo'lib chiqadi.");
    } elseif ($act === 'no') {
        db()->prepare("UPDATE reg_agents SET status = 'no' WHERE id = ?")->execute([$id]);
        $answer('❌ Rad etildi');
        $edit("❌ <b>$name</b> rad etildi.");
    } elseif ($act === 'rm') {
        $edit("🗑 <b>$name</b> ro'yxatdan o'chirilsinmi? Kompyuterdagi bot ishlashdan to'xtaydi.",
            ['inline_keyboard' => [[
                ['text' => "🗑 Ha, o'chirish", 'callback_data' => "hub|rmy:$id"],
                ['text' => 'Bekor qilish', 'callback_data' => "hub|pc:$id"],
            ]]]);
        tg('answerCallbackQuery', ['callback_query_id' => $cq['id']]);
    } elseif ($act === 'rmy') {
        db()->prepare('DELETE FROM reg_agents WHERE id = ?')->execute([$id]);
        db()->prepare('DELETE FROM queue WHERE agent = ?')->execute([$id]);
        $answer("🗑 O'chirildi");
        $edit("🗑 <b>$name</b> ro'yxatdan o'chirildi.");
    }
}

function route_inline(array $u): void
{
    $iq = $u['inline_query'];
    $uid = (int)$iq['from']['id'];
    $parts = explode(' ', trim((string)$iq['query']), 2);
    $a = $parts[0];
    $token = trim($parts[1] ?? '');

    if (is_admin($uid) && isset(agents()[$a]) && $token !== '' && is_online($a)) {
        $u['inline_query']['query'] = $token;
        enqueue($a, $u);
        return;
    }
    $params = ['inline_query_id' => $iq['id'], 'results' => [], 'cache_time' => 0, 'is_personal' => true];
    if (is_admin($uid) && isset(agents()[$a]) && !is_online($a)) {
        $params['button'] = ['text' => '💤 ' . agent_name($a) . ' javob bermayapti', 'start_parameter' => 'pc'];
    }
    tg('answerInlineQuery', $params);
}

// ─────────────────────────── Poll: agent o'z navbatini oladi ───────────────────────────

function handle_poll(): void
{
    $a = (string)($_GET['agent'] ?? '');
    $key = (string)($_SERVER['HTTP_X_AGENT_KEY'] ?? ($_GET['key'] ?? ''));
    agent_auth($a, $key);
    mark_seen($a);
    // v=2 agentlar kutmaydi (wait=0). Eski agentlar avvalgidek 20 soniya kutadi.
    $wait = isset($_GET['v']) ? max(0, min(POLL_WAIT, (int)($_GET['wait'] ?? 0))) : POLL_WAIT;
    @set_time_limit($wait + 20);
    $flag = flag_file($a);
    $deadline = microtime(true) + $wait;
    while (true) {
        clearstatcache(true, $flag);
        if (is_file($flag)) {  // navbatda nimadir bor - endi bazani ochamiz
            $rows = take_queue($a);
            if ($rows) {
                json_out(['ok' => true, 'updates' => $rows]);
            }
        }
        if (microtime(true) >= $deadline || connection_aborted()) {
            break;
        }
        usleep(500000);
    }
    json_out(['ok' => true, 'updates' => []]);
}

function take_queue(string $a): array
{
    $pdo = db();
    if (mt_rand(1, 50) === 1) {  // eskirgan xabarlarni vaqti-vaqti bilan tozalaymiz
        $pdo->prepare('DELETE FROM queue WHERE created < ?')->execute([time() - QUEUE_TTL]);
    }
    // Belgini avval o'chiramiz: shu orada yangi xabar kelsa, enqueue() uni qayta qo'yadi
    @unlink(flag_file($a));
    $pdo->beginTransaction();
    $st = $pdo->prepare('SELECT id, payload, created FROM queue WHERE agent = ? ORDER BY id LIMIT 50');
    $st->execute([$a]);
    $rows = $st->fetchAll(PDO::FETCH_ASSOC);
    if ($rows) {
        $pdo->prepare('DELETE FROM queue WHERE agent = ? AND id <= ?')->execute([$a, end($rows)['id']]);
    }
    $left = (int)$pdo->query('SELECT COUNT(*) FROM queue WHERE agent = ' . $pdo->quote($a))->fetchColumn();
    $pdo->commit();
    if ($left > 0) {
        @touch(flag_file($a));
    }
    $out = [];
    foreach ($rows as $r) {
        if ((int)$r['created'] >= time() - QUEUE_TTL) {
            $out[] = json_decode($r['payload'], true);
        }
    }
    return $out;
}

/** Kompyuter kalitini tekshiradi. Tasdiqlanmagan bo'lsa sababini qaytaradi. */
function agent_auth(string $a, string $key): void
{
    $agents = agents();
    if (isset($agents[$a]) && hash_equals((string)$agents[$a]['key'], $key)) {
        return;
    }
    $r = preg_match('/^[a-z0-9]{1,10}$/', $a) ? reg_agent($a) : null;
    if ($r && hash_equals((string)$r['key'], $key)) {
        json_out(['ok' => false, 'error' => $r['status'] === 'wait' ? 'pending' : 'rejected'], 403);
    }
    json_out(['ok' => false, 'error' => 'auth'], 403);
}

// ─────────────────────────── O'rnatuvchi: ro'yxatdan o'tish ───────────────────────────

function handle_register(): void
{
    $in = json_decode((string)file_get_contents('php://input'), true) ?: [];
    if (!hash_equals(enroll_code(), (string)($in['code'] ?? ''))) {
        json_out(['ok' => false, 'error' => 'code'], 403);
    }
    $name = trim(preg_replace('/\s+/u', ' ', (string)($in['name'] ?? '')));
    $name = mb_substr($name !== '' ? $name : 'Kompyuter', 0, 40);
    $host = mb_substr((string)($in['host'] ?? ''), 0, 60);
    $pdo = db();
    $pdo->prepare("DELETE FROM reg_agents WHERE status = 'wait' AND created < ?")->execute([time() - 86400]);
    $waiting = (int)$pdo->query("SELECT COUNT(*) FROM reg_agents WHERE status = 'wait'")->fetchColumn();
    if ($waiting >= 10) {
        json_out(['ok' => false, 'error' => 'too_many'], 429);
    }
    do {
        $id = 'k' . substr(str_shuffle('abcdefghijkmnpqrstuvwxyz23456789'), 0, 5);
    } while (isset(agents()[$id]) || reg_agent($id));
    $key = rtrim(strtr(base64_encode(random_bytes(24)), '+/', '-_'), '=');
    $pdo->prepare("INSERT INTO reg_agents(id, name, key, host, status, created) VALUES(?, ?, ?, ?, 'wait', ?)")
        ->execute([$id, $name, $key, $host, time()]);
    foreach (admins() as $uid) {
        tg('sendMessage', [
            'chat_id' => $uid,
            'parse_mode' => 'HTML',
            'text' => "🆕 <b>Yangi kompyuter ulanmoqchi</b>\n\n💻 Nomi: <b>" . h($name) . '</b>'
                . ($host !== '' ? "\n🖥 Kompyuter: <code>" . h($host) . '</code>' : '')
                . "\n\nAgar bu kompyuterga o'rnatishni siz boshlagan bo'lsangiz, qabul qiling.",
            'reply_markup' => ['inline_keyboard' => [[
                ['text' => '✅ Qabul qilish', 'callback_data' => "hub|ok:$id"],
                ['text' => '❌ Rad etish', 'callback_data' => "hub|no:$id"],
            ]]],
        ]);
    }
    json_out(['ok' => true, 'agent' => $id, 'key' => $key, 'status' => 'pending']);
}

/** Tasdiqlangan kompyuterga bot tokeni va foydalanuvchilar ro'yxatini beradi. */
function handle_bootstrap(): void
{
    global $CFG;
    $a = (string)($_GET['agent'] ?? '');
    agent_auth($a, (string)($_SERVER['HTTP_X_AGENT_KEY'] ?? ''));
    mark_seen($a);
    json_out(['ok' => true, 'token' => $CFG['bot_token'], 'users' => admins(), 'name' => agent_name($a),
              'api_id' => (int)($CFG['api_id'] ?? 0), 'api_hash' => (string)($CFG['api_hash'] ?? '')]);
}

// ─────────────────────────── Setup va status ───────────────────────────

function require_secret(): void
{
    global $CFG;
    $key = (string)($_SERVER['HTTP_X_SETUP_KEY'] ?? ($_GET['key'] ?? ''));
    if (!hash_equals((string)$CFG['webhook_secret'], $key)) {
        http_response_code(403);
        exit('Kalit noto\'g\'ri');
    }
}

function self_url(): string
{
    global $CFG;
    if (!empty($CFG['public_url'])) {
        return $CFG['public_url'];
    }
    $https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
        || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
    $path = strtok($_SERVER['REQUEST_URI'] ?? '/hub.php', '?');
    return ($https ? 'https' : 'http') . '://' . $_SERVER['HTTP_HOST'] . $path;
}

function handle_setup(): void
{
    global $CFG;
    require_secret();
    header('Content-Type: text/plain; charset=utf-8');
    $url = self_url() . '?a=webhook';
    if (strpos($url, 'https://') !== 0) {
        echo "DIQQAT: Telegram faqat https manzilni qabul qiladi. Hozirgi manzil: $url\n"
            . "config.php ga 'public_url' => 'https://...' yozing.\n\n";
    }
    $r1 = tg('setWebhook', [
        'url' => $url,
        'secret_token' => $CFG['webhook_secret'],
        'allowed_updates' => ['message', 'callback_query', 'inline_query'],
        'drop_pending_updates' => true,
    ]);
    $r2 = tg('setMyCommands', ['commands' => [
        ['command' => 'kompyuter', 'description' => 'Kompyuterni tanlash'],
        ['command' => 'disk', 'description' => 'Disk va papkalar'],
        ['command' => 'izla', 'description' => 'Fayl qidirish'],
        ['command' => 'ekran', 'description' => 'Ekran skrinshoti'],
        ['command' => 'kattafayl', 'description' => '2 GB gacha fayl yuborishni yoqish'],
        ['command' => 'id', 'description' => 'Chat ID'],
        ['command' => 'yordam', 'description' => 'Yordam'],
    ]]);
    db();  // ma'lumotlar bazasini yaratib qo'yamiz
    echo "Webhook: $url\n";
    echo 'setWebhook: ' . (($r1['ok'] ?? false) ? 'OK' : 'XATO — ' . json_encode($r1, JSON_UNESCAPED_UNICODE)) . "\n";
    echo 'setMyCommands: ' . (($r2['ok'] ?? false) ? 'OK' : 'XATO — ' . json_encode($r2, JSON_UNESCAPED_UNICODE)) . "\n";
    echo "\nTayyor bo'lsa, Telegram'da botga /kompyuter yozing.\n";
}

function handle_status(): void
{
    require_secret();
    header('Content-Type: text/plain; charset=utf-8');
    foreach (agents() as $id => $a) {
        echo (is_online($id) ? '[ONLAYN] ' : '[o\'chiq] ') . "$id — {$a['name']} — oxirgi aloqa: " . seen_text($id) . "\n";
    }
    $info = tg('getWebhookInfo', []);
    echo "\nWebhook: " . ($info['result']['url'] ?? '-') . "\n";
    echo 'Kutilayotgan xabarlar: ' . ($info['result']['pending_update_count'] ?? '-') . "\n";
    if (!empty($info['result']['last_error_message'])) {
        echo 'Oxirgi xato: ' . $info['result']['last_error_message'] . "\n";
    }
}

// ─────────────────────────── Marshrutlash ───────────────────────────

switch ($_GET['a'] ?? '') {
    case 'webhook':
        handle_webhook();
        break;
    case 'poll':
        handle_poll();
        break;
    case 'setup':
        handle_setup();
        break;
    case 'register':
        handle_register();
        break;
    case 'bootstrap':
        handle_bootstrap();
        break;
    case 'status':
        handle_status();
        break;
    default:
        header('Content-Type: text/plain; charset=utf-8');
        echo 'OK';
}
