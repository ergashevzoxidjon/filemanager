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
const POLL_WAIT  = 20;   // agent so'roviga javobni shuncha sekund kutib turamiz
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

function agents(): array
{
    global $CFG;
    return $CFG['agents'] ?? [];
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

function last_seen(string $a): int
{
    $st = db()->prepare('SELECT ts FROM seen WHERE agent = ?');
    $st->execute([$a]);
    return (int)($st->fetchColumn() ?: 0);
}

function is_online(string $a): bool
{
    return time() - last_seen($a) < ONLINE_SEC;
}

function mark_seen(string $a): void
{
    db()->prepare('INSERT OR REPLACE INTO seen(agent, ts) VALUES(?, ?)')->execute([$a, time()]);
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
        $rows[] = [['text' => "$icon {$a['name']}$mark", 'callback_data' => "hub|pc:$id"]];
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
    $agents = agents();
    if (!isset($agents[$a]) || !hash_equals((string)$agents[$a]['key'], $key)) {
        json_out(['ok' => false, 'error' => 'auth'], 403);
    }
    @set_time_limit(POLL_WAIT + 20);
    $pdo = db();
    $pdo->prepare('DELETE FROM queue WHERE created < ?')->execute([time() - QUEUE_TTL]);
    mark_seen($a);

    $deadline = microtime(true) + POLL_WAIT;
    $select = $pdo->prepare('SELECT id, payload FROM queue WHERE agent = ? ORDER BY id LIMIT 50');
    $delete = $pdo->prepare('DELETE FROM queue WHERE agent = ? AND id <= ?');
    do {
        $pdo->beginTransaction();
        $select->execute([$a]);
        $rows = $select->fetchAll(PDO::FETCH_ASSOC);
        if ($rows) {
            $delete->execute([$a, end($rows)['id']]);
        }
        $pdo->commit();
        if ($rows) {
            mark_seen($a);
            json_out(['ok' => true, 'updates' => array_map(function ($r) {
                return json_decode($r['payload'], true);
            }, $rows)]);
        }
        if (connection_aborted()) {
            exit;
        }
        usleep(500000);
    } while (microtime(true) < $deadline);
    mark_seen($a);
    json_out(['ok' => true, 'updates' => []]);
}

// ─────────────────────────── Setup va status ───────────────────────────

function require_secret(): void
{
    global $CFG;
    if (!hash_equals((string)$CFG['webhook_secret'], (string)($_GET['key'] ?? ''))) {
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
    case 'status':
        handle_status();
        break;
    default:
        header('Content-Type: text/plain; charset=utf-8');
        echo 'OK';
}
