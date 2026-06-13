import os
import time
import json
import asyncio
import requests
import discord
import re
import unicodedata

from datetime import timedelta
from urllib.parse import quote
from discord.ext import commands, tasks
from openai import AsyncOpenAI
from collections import defaultdict, deque

# ======================
# KONFIGŪRACIJA
# ======================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VALORANT_API_KEY = os.getenv("VALORANT_API_KEY")

print("VALORANT KEY loaded:", bool(VALORANT_API_KEY))

if not DISCORD_TOKEN:
    raise ValueError("❌ Nerastas DISCORD_TOKEN Railway Variables")

if not OPENAI_API_KEY:
    raise ValueError("❌ Nerastas OPENAI_API_KEY Railway Variables")

if not VALORANT_API_KEY:
    raise ValueError("❌ Nerastas VALORANT_API_KEY Railway Variables")

AI_MODEL = "gpt-4o-mini"

AI_COOLDOWN = 30
ROLE_COOLDOWN = 60
GAME_ROLE_COOLDOWN = 30
MAX_CLEAR_MESSAGES = 500

# ======================
# SERVERIO ROLĖS
# ======================

VYRAS_ROLE_NAME = "Vyras"
PANELE_ROLE_NAME = "Panelė"

UNVERIFIED_ROLE_NAME = "Nepatvirtintas"
VERIFIED_ROLE_NAME = "Narys"

GAME_ROLE_NAMES = {
    "valorant": "Valorant",
    "cs2": "CS2",
    "roblox": "Roblox",
    "minecraft": "Minecraft",
    "minicraft": "Minecraft"
}

# ======================
# WELCOME / TAISYKLĖS
# ======================

WELCOME_CHANNEL_NAMES = [
    "welcome",
    "👋・welcome",
    "👋︱welcome",
    "sveiki",
    "👋・sveiki",
    "👋︱sveiki",
    "ᴡᴇʟᴄᴏᴍᴇ",
    "👋・ᴡᴇʟᴄᴏᴍᴇ"
]

RULES_CHANNEL_NAMES = [
    "taisykles",
    "📜・taisykles",
    "📜︱taisykles",
    "📜・ᴛᴀɪsʏᴋʟᴇs",
    "rules",
    "📜・rules"
]

RULES_ACCEPT_CHANNEL_NAMES = [
    "patvirtinimas",
    "✅・patvirtinimas",
    "✅︱patvirtinimas",
    "✅・ᴘᴀᴛᴠɪʀᴛɪɴɪᴍᴀs",
    "accept",
    "✅・accept"
]

RULES_ACCEPT_WORDS = [
    "sutinku",
    "sutinku su taisyklemis",
    "sutinku su taisyklėmis",
    "patvirtinu",
    "accept",
    "agree"
]

RULES_READ_WAIT_SECONDS = 60
ACCEPT_DELETE_AFTER_SECONDS = 60

WELCOME_BANNER_URL = "https://images.unsplash.com/photo-1511512578047-dfb367046420?q=80&w=1600&auto=format&fit=crop"

# Jei turi savo NG Community logo URL, įdėk čia.
# Pvz: NG_COMMUNITY_LOGO_URL = "https://tavo-logo.png"
NG_COMMUNITY_LOGO_URL = ""

# ======================
# VALORANT
# ======================

VALORANT_REGION = "eu"
VALORANT_UPDATE_HOURS = 12
VALORANT_LINKS_FILE = "valorant_links.json"

VERIFY_COOLDOWN_HOURS = 4
VERIFY_COOLDOWN_SECONDS = VERIFY_COOLDOWN_HOURS * 60 * 60

VALORANT_RANK_ROLES = {
    "Iron": "Iron",
    "Bronze": "Bronze",
    "Silver": "Silver",
    "Gold": "Gold",
    "Platinum": "Platinum",
    "Diamond": "Diamond",
    "Ascendant": "Ascendant",
    "Immortal": "Immortal",
    "Radiant": "Radiant"
}

# ======================
# ANTI-SPAM
# ======================

SPAM_WINDOW_SECONDS = 7
SPAM_MAX_MESSAGES = 5

DUPLICATE_WINDOW_SECONDS = 10
DUPLICATE_MAX_MESSAGES = 3

SPAM_DELETE_LIMIT = 20
SPAM_DELETE_LOOKBACK_SECONDS = 15

SPAM_OFFENSE_RESET_SECONDS = 24 * 60 * 60

SPAM_PUNISHMENTS = [
    60,
    300,
    3600
]

# ======================
# KEIKSMAŽODŽIŲ FILTRAS
# ======================

PROFANITY_RESET_SECONDS = 24 * 60 * 60

PROFANITY_PUNISHMENTS = [
    0,
    300,
    3600
]

SEVERE_PROFANITY_TIMEOUT = 3600

BAD_WORD_STEMS = [
    "kurv",
    "byb",
    "pisk",
    "pizd",
    "nahui",
    "naxui",
    "nx",
    "debil",
    "duch",
    "gaid",
    "lop",
    "asil",
    "durn",
    "idiot",
    "suka",
    "padla",
    "ciulp",
    "čiulp",
    "kekš",
    "keks",
    "urod",
    "dalbaj",
    "daun",
    "pyder",
    "pydar",
    "pidar",

    "niuh",
    "niuhas",
    "mantel",
    "mantelis",
    "gryb",
    "grybas"
]

SEVERE_WORD_STEMS = [
    "nusizudyk",
    "nusižudyk",
    "zudykis",
    "žudykis",
    "uzsimusk",
    "užsimušk",
    "kill yourself",
    "kys",

    "papjausiu",
    "pjausiu",
    "nuzudysiu",
    "nužudysiu",
    "uzmusiu",
    "užmušiu",
    "uzdauzysiu",
    "uždaužysiu",
    "sudauzysiu",
    "sudaužysiu",
    "supjausiu",
    "papjaus",
    "nuzud",
    "nužud",
    "uzmus",
    "užmus",

    "nyg",
    "nyga",
    "niga",
    "nigg",
    "+n+y+g+a",
    "n.y.g.a",
    "n-y-g-a",

    "ciurka",
    "čiurka",
    "zydas",
    "žydas",

    "hitler",
    "nacis",
    "nazi",
    "nacistas",
    "teroristas",
    "terrorist"
]

# ======================
# OPENAI
# ======================

client_ai = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ======================
# DISCORD
# ======================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# ======================
# ATMINTIS
# ======================

user_memory = defaultdict(lambda: deque(maxlen=10))

ai_cooldowns = {}
role_cooldowns = {}
game_role_cooldowns = {}

spam_messages = defaultdict(lambda: deque(maxlen=30))
spam_offenses = defaultdict(lambda: {"count": 0, "last": 0})
spam_punish_cooldowns = {}

profanity_offenses = defaultdict(lambda: {"count": 0, "last": 0})
profanity_punish_cooldowns = {}

# ======================
# JSON DB
# ======================

def load_valorant_links():
    if not os.path.exists(VALORANT_LINKS_FILE):
        return {}

    try:
        with open(VALORANT_LINKS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def save_valorant_links(data):
    with open(VALORANT_LINKS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def get_link_key(guild_id: int, user_id: int):
    return f"{guild_id}:{user_id}"


def get_user_valorant_link(guild_id: int, user_id: int):
    data = load_valorant_links()
    key = get_link_key(guild_id, user_id)
    return data.get(key)


def save_user_valorant_link(guild_id: int, user_id: int, name: str, tag: str, rank: str):
    data = load_valorant_links()
    key = get_link_key(guild_id, user_id)
    now = int(time.time())
    old_data = data.get(key, {})

    data[key] = {
        "guild_id": guild_id,
        "user_id": user_id,
        "name": name,
        "tag": tag,
        "region": VALORANT_REGION,
        "last_rank": rank,
        "updated_at": now,
        "manual_verified_at": now,
        "created_at": old_data.get("created_at", now)
    }

    save_valorant_links(data)


def update_user_last_rank(guild_id: int, user_id: int, rank: str):
    data = load_valorant_links()
    key = get_link_key(guild_id, user_id)

    if key not in data:
        return

    data[key]["last_rank"] = rank
    data[key]["updated_at"] = int(time.time())

    save_valorant_links(data)

# ======================
# HELPERIAI
# ======================

def is_ai_channel(message: discord.Message) -> bool:
    channel_name = getattr(message.channel, "name", "").lower()

    parent = getattr(message.channel, "parent", None)
    parent_name = getattr(parent, "name", "").lower() if parent else ""

    ai_keywords = [
        "ai",
        "ᴀɪ",
        "ai-chat",
        "ᴀɪ-ᴄʜᴀᴛ"
    ]

    return (
        any(keyword in channel_name for keyword in ai_keywords)
        or any(keyword in parent_name for keyword in ai_keywords)
    )


def cooldown_left(cooldowns: dict, user_id: int, cooldown: int) -> int:
    now = time.time()

    if user_id not in cooldowns:
        return 0

    remaining = cooldown - (now - cooldowns[user_id])
    return max(0, int(remaining))


async def safe_reply(message: discord.Message, text: str):
    await message.reply(
        text[:1900],
        mention_author=False,
        allowed_mentions=discord.AllowedMentions.none()
    )


def discord_relative_time(timestamp: int):
    return f"<t:{timestamp}:R>"


def format_duration(seconds: int):
    if seconds >= 3600:
        return f"{seconds // 3600} val."
    if seconds >= 60:
        return f"{seconds // 60} min."
    return f"{seconds} sek."


def get_base_valorant_rank(full_rank: str):
    if not full_rank:
        return None

    return full_rank.split(" ")[0]


def find_channel_by_names(guild: discord.Guild, names: list, keywords: list):
    for name in names:
        channel = discord.utils.get(guild.text_channels, name=name)
        if channel:
            return channel

    for channel in guild.text_channels:
        channel_name = channel.name.lower()
        if any(keyword in channel_name for keyword in keywords):
            return channel

    return None


def find_welcome_channel(guild: discord.Guild):
    return find_channel_by_names(
        guild,
        WELCOME_CHANNEL_NAMES,
        ["welcome", "sveiki", "prisijung", "atvyk", "ᴡᴇʟᴄᴏᴍᴇ"]
    )


def find_rules_channel(guild: discord.Guild):
    return find_channel_by_names(
        guild,
        RULES_CHANNEL_NAMES,
        ["taisykles", "rules", "ᴛᴀɪsʏᴋʟᴇs"]
    )


def find_rules_accept_channel(guild: discord.Guild):
    return find_channel_by_names(
        guild,
        RULES_ACCEPT_CHANNEL_NAMES,
        ["patvirtinimas", "accept", "ᴘᴀᴛᴠɪʀᴛɪɴɪᴍᴀs"]
    )


def has_role(member: discord.Member, role_name: str):
    role = discord.utils.get(member.guild.roles, name=role_name)
    return role in member.roles if role else False


def has_verified_role(member: discord.Member):
    if member.guild_permissions.administrator or member.guild_permissions.manage_messages:
        return True

    return has_role(member, VERIFIED_ROLE_NAME)


async def give_role(member: discord.Member, role_name: str, reason: str = None):
    role = discord.utils.get(member.guild.roles, name=role_name)

    if not role:
        print(f"❌ Nerasta rolė: {role_name}")
        return False

    bot_member = member.guild.get_member(bot.user.id)

    if not bot_member:
        return False

    if bot_member.top_role <= role:
        print(f"❌ Boto rolė per žemai rolei: {role.name}")
        return False

    if role not in member.roles:
        await member.add_roles(role, reason=reason or "Role add")

    return True


async def remove_role(member: discord.Member, role_name: str, reason: str = None):
    role = discord.utils.get(member.guild.roles, name=role_name)

    if not role:
        return False

    bot_member = member.guild.get_member(bot.user.id)

    if not bot_member:
        return False

    if bot_member.top_role <= role:
        print(f"❌ Boto rolė per žemai rolei: {role.name}")
        return False

    if role in member.roles:
        await member.remove_roles(role, reason=reason or "Role remove")

    return True


async def require_verified(message: discord.Message):
    if has_verified_role(message.author):
        return True

    accept_channel = find_rules_accept_channel(message.guild)
    rules_channel = find_rules_channel(message.guild)

    if accept_channel:
        await safe_reply(
            message,
            f"📜 Pirma perskaityk taisykles ir kanale {accept_channel.mention} parašyk `sutinku`."
        )
    elif rules_channel:
        await safe_reply(
            message,
            f"📜 Pirma perskaityk taisykles kanale {rules_channel.mention} ir parašyk `sutinku`."
        )
    else:
        await safe_reply(
            message,
            "📜 Pirma turi perskaityti taisykles ir parašyti `sutinku`."
        )

    return False


def get_rules_wait_remaining(member: discord.Member):
    if not member.joined_at:
        return 0

    joined_timestamp = int(member.joined_at.timestamp())
    now = int(time.time())

    remaining = RULES_READ_WAIT_SECONDS - (now - joined_timestamp)
    return max(0, remaining)

# ======================
# WELCOME SISTEMA
# ======================

async def send_welcome_message(member: discord.Member):
    channel = find_welcome_channel(member.guild)

    if not channel:
        print("ℹ️ Welcome kanalas nerastas.")
        return

    member_count = member.guild.member_count or "?"

    logo_url = NG_COMMUNITY_LOGO_URL

    if not logo_url and member.guild.icon:
        logo_url = member.guild.icon.url

    embed = discord.Embed(
        title="🌐 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ɴɢ ᴄᴏᴍᴍᴜɴɪᴛʏ",
        description=(
            f"**Labas, {member.mention}!** 👋\n\n"
            f"Malonu tave matyti **{member.guild.name}** serveryje. "
            "Čia gali bendrauti, susirasti žmonių žaidimams, gauti pagalbos ir tiesiog gerai praleisti laiką.\n\n"
            "Mes norime, kad ši bendruomenė būtų jauki, draugiška ir saugi kiekvienam nariui. 💙"
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )

    embed.set_author(
        name=f"{member.display_name} prisijungė prie serverio",
        icon_url=member.display_avatar.url
    )

    if logo_url:
        embed.set_thumbnail(url=logo_url)
    else:
        embed.set_thumbnail(url=member.display_avatar.url)

    if WELCOME_BANNER_URL:
        embed.set_image(url=WELCOME_BANNER_URL)

    embed.add_field(
        name="🤖 Susipažink su manimi — MTX-AI",
        value=(
            "Aš esu **MTX-AI** — NG Community pagalbininkas ir automatinė moderacijos sistema.\n\n"
            "Mane rasi kanale **ᴀɪ-ᴄʜᴀᴛ**. Ten gali manęs klausti apie:\n"
            "• Valorant rankus, MMR, RR ir agentus;\n"
            "• FPS, crosshair, sensitivity ir žaidimo nustatymus;\n"
            "• serverio roles, taisykles ir komandas;\n"
            "• bendrą pagalbą ar klausimus apie serverį.\n\n"
            "Ši sistema sukurta tam, kad administracijai nereikėtų visko daryti rankomis, "
            "o nariai pagalbą gautų greičiau. ✨\n\n"
            "⚠️ Aš nepadedu su seksualiniu turiniu, smurtu, žiauriais dalykais, cheat, hack, phishing ar kita pavojinga veikla."
        ),
        inline=False
    )

    embed.add_field(
        name="📜 Pirmas žingsnis — taisyklės",
        value=(
            "Kad galėtum naudotis visu serveriu:\n\n"
            "1️⃣ Pirmiausia nueik į kanalą **📜・taisykles**.\n"
            "2️⃣ Ramiai perskaityk taisykles.\n"
            "3️⃣ Palauk bent **1 minutę**.\n"
            "4️⃣ Tada kanale **✅・patvirtinimas** parašyk:\n"
            "`sutinku`\n\n"
            "Tada gausi **Narys** rolę ir galėsi naudotis serveriu."
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Žaidimų rolės",
        value=(
            "Kai patvirtinsi taisykles, galėsi pasirinkti žaidimų roles parašydamas:\n\n"
            "`valorant` — Valorant rolė\n"
            "`cs2` — CS2 rolė\n"
            "`roblox` — Roblox rolė\n"
            "`minecraft` — Minecraft rolė\n\n"
            "Jeigu norėsi nusiimti rolę:\n"
            "`remove valorant`, `remove cs2`, `remove roblox`, `remove minecraft`"
        ),
        inline=False
    )

    embed.add_field(
        name="🏆 Valorant rank rolė",
        value=(
            "Jeigu nori gauti savo Valorant rank rolę, parašyk:\n\n"
            "`verify Vardas#TAG`\n\n"
            "Pavyzdys:\n"
            "`verify Jonas#EUW`\n\n"
            "Botas patikrins tavo ranką ir uždės rolę, pvz. **Gold**, **Platinum**, **Diamond** ir t.t.\n"
            "Rank verify galima naudoti kas **4 val.**"
        ),
        inline=False
    )

    embed.add_field(
        name="🎭 Lyties rolės",
        value=(
            "Pasirinkti lyties rolę gali paprastai parašydamas:\n\n"
            "`vyras` — gauti **Vyras** rolę\n"
            "`panele` arba `panelė` — gauti **Panelė** rolę"
        ),
        inline=False
    )

    embed.add_field(
        name="🎁 Specialios naudos",
        value=(
            "Papildomos naudos, specialios rolės ar išskirtiniai privalumai gali būti suteikiami nariams, kurie:\n\n"
            "🚀 boostina serverį;\n"
            "💙 paremia bendruomenę;\n"
            "🏆 dalyvauja arba laimi turnyruose;\n"
            "🌟 prisideda prie NG Community augimo.\n\n"
            "Tai padeda palaikyti aktyvią, sąžiningą ir motyvuotą bendruomenę."
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ ɴɢ ᴄᴏᴍᴍᴜɴɪᴛʏ ᴛᴠᴀʀᴋᴀ",
        value=(
            "⚠️ **Taisyklės šiame serveryje yra griežtos**, nes norime saugios, draugiškos ir tvarkingos bendruomenės.\n\n"
            "🤝 **Gerbk kitus narius** — bendrauk draugiškai ir kultūringai.\n"
            "🚫 **Nespamink** — flood, caps spam ir pasikartojančios žinutės bus trinamos.\n"
            "💬 **Neįžeidinėk** — jokio toxic elgesio, provokacijų ar patyčių.\n"
            "📢 **Nereklamuok be leidimo** — invite linkai ir reklamos draudžiamos.\n"
            "🛡️ **Jokių cheat / hack** — kenksminga veikla, phishing ar bypass metodai draudžiami.\n\n"
            "🤖 **MTX-AI apsauga aktyvi**\n"
            "Serveris automatiškai saugomas nuo spamo, įžeidimų ir taisyklių pažeidimų.\n\n"
            "💙 Laikykis taisyklių, gerbk kitus ir mėgaukis NG Community!"
        ),
        inline=False
    )

    embed.set_footer(
        text=f"Tu esi #{member_count} narys • NG Community linki gero laiko 💙",
        icon_url=logo_url if logo_url else None
    )

    try:
        await channel.send(
            content=f"🌟 Sveikas atvykęs, {member.mention}! Smagu tave matyti čia 💙",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True)
        )
    except Exception as e:
        print(f"❌ Nepavyko išsiųsti welcome žinutės: {e}")


async def handle_rules_accept(message: discord.Message):
    content = message.content.lower().strip()

    accept_channel = find_rules_accept_channel(message.guild)
    rules_channel = find_rules_channel(message.guild)

    if accept_channel and message.channel.id == accept_channel.id:
        if content not in RULES_ACCEPT_WORDS:
            try:
                await message.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
            except Exception:
                pass

            warn_msg = await message.channel.send(
                f"📜 {message.author.mention}, šiame kanale reikia parašyti tik `sutinku`.",
                allowed_mentions=discord.AllowedMentions(users=True)
            )

            try:
                await warn_msg.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
            except Exception:
                pass

            return True

    if content not in RULES_ACCEPT_WORDS:
        return False

    if accept_channel and message.channel.id != accept_channel.id:
        reply = await message.reply(
            f"📜 Taisykles reikia patvirtinti kanale {accept_channel.mention} parašant `sutinku`.",
            mention_author=False
        )

        try:
            await reply.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
        except Exception:
            pass

        return True

    remaining_wait = get_rules_wait_remaining(message.author)

    if remaining_wait > 0:
        reply = await message.reply(
            f"⏳ Pirma ramiai perskaityk taisykles.\n"
            f"Patvirtinti galėsi po **{remaining_wait} sek.**\n\n"
            f"📜 Taisyklės: {rules_channel.mention if rules_channel else '`taisykles` kanale'}",
            mention_author=False
        )

        try:
            await message.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
            await reply.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
        except Exception:
            pass

        return True

    if has_verified_role(message.author):
        reply = await message.reply(
            "✅ Tu jau esi patvirtintas.",
            mention_author=False
        )

        try:
            await message.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
            await reply.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
        except Exception:
            pass

        return True

    try:
        gave_verified = await give_role(
            message.author,
            VERIFIED_ROLE_NAME,
            reason="Taisyklių patvirtinimas"
        )

        await remove_role(
            message.author,
            UNVERIFIED_ROLE_NAME,
            reason="Taisyklių patvirtinimas"
        )

        if not gave_verified:
            reply = await message.reply(
                f"❌ Nepavyko duoti rolės **{VERIFIED_ROLE_NAME}**. Patikrink roles ir boto poziciją.",
                mention_author=False
            )

            try:
                await message.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
                await reply.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
            except Exception:
                pass

            return True

        reply = await message.reply(
            "✅ **Taisyklės patvirtintos!**\n\n"
            "Dabar gali naudotis serveriu.\n\n"
            "🎮 Žaidimų rolės: `valorant`, `cs2`, `roblox`, `minecraft`\n"
            "🎭 Lyties rolės: `vyras`, `panele`\n"
            "🏆 Valorant rank rolė: `verify Vardas#TAG`\n"
            "📊 MMR info: `mmr`",
            mention_author=False
        )

        try:
            await message.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
            await reply.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
        except Exception:
            pass

    except discord.Forbidden:
        reply = await message.reply(
            "❌ Negaliu duoti rolės. Reikia **Manage Roles** ir boto rolė turi būti aukščiau.",
            mention_author=False
        )

        try:
            await message.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
            await reply.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
        except Exception:
            pass

    except Exception as e:
        reply = await message.reply(
            f"❌ Klaida patvirtinant taisykles: {e}",
            mention_author=False
        )

        try:
            await message.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
            await reply.delete(delay=ACCEPT_DELETE_AFTER_SECONDS)
        except Exception:
            pass

    return True

# ======================
# GAME ROLES
# ======================

async def handle_game_role(message: discord.Message, content: str, user_id: int):
    if content in GAME_ROLE_NAMES:
        if not await require_verified(message):
            return True

        remaining = cooldown_left(game_role_cooldowns, user_id, GAME_ROLE_COOLDOWN)

        if remaining > 0:
            await safe_reply(message, f"⏳ Palauk {remaining}s prieš keičiant žaidimų rolę.")
            return True

        role_name = GAME_ROLE_NAMES[content]
        role = discord.utils.get(message.guild.roles, name=role_name)

        if not role:
            await safe_reply(
                message,
                f"❌ Nerasta rolė **{role_name}**. Sukurk ją Discord serveryje."
            )
            return True

        bot_member = message.guild.get_member(bot.user.id)

        if not bot_member:
            await safe_reply(message, "❌ Nepavyko rasti boto serveryje.")
            return True

        if bot_member.top_role <= role:
            await safe_reply(
                message,
                f"❌ Mano rolė per žemai. Pakelk boto rolę aukščiau už **{role.name}**."
            )
            return True

        if role in message.author.roles:
            await safe_reply(
                message,
                f"ℹ️ Tu jau turi rolę: **{role.name}**"
            )
            return True

        try:
            await message.author.add_roles(role, reason="Žaidimo rolės pasirinkimas")
            game_role_cooldowns[user_id] = time.time()

            await safe_reply(
                message,
                f"✅ Gavai žaidimo rolę: **{role.name}**"
            )

        except discord.Forbidden:
            await safe_reply(
                message,
                "❌ Neturiu teisių duoti šios rolės. Reikia **Manage Roles**."
            )

        except Exception as e:
            await safe_reply(
                message,
                f"❌ Klaida duodant žaidimo rolę: {e}"
            )

        return True

    remove_prefixes = ["remove ", "nuimti ", "nusiimti "]

    for prefix in remove_prefixes:
        if content.startswith(prefix):
            game_key = content[len(prefix):].strip()

            if game_key not in GAME_ROLE_NAMES:
                return False

            if not await require_verified(message):
                return True

            remaining = cooldown_left(game_role_cooldowns, user_id, GAME_ROLE_COOLDOWN)

            if remaining > 0:
                await safe_reply(message, f"⏳ Palauk {remaining}s prieš keičiant žaidimų rolę.")
                return True

            role_name = GAME_ROLE_NAMES[game_key]
            role = discord.utils.get(message.guild.roles, name=role_name)

            if not role:
                await safe_reply(message, f"❌ Nerasta rolė **{role_name}**.")
                return True

            if role not in message.author.roles:
                await safe_reply(message, f"ℹ️ Tu neturi rolės: **{role.name}**")
                return True

            bot_member = message.guild.get_member(bot.user.id)

            if not bot_member:
                await safe_reply(message, "❌ Nepavyko rasti boto serveryje.")
                return True

            if bot_member.top_role <= role:
                await safe_reply(
                    message,
                    f"❌ Mano rolė per žemai. Pakelk boto rolę aukščiau už **{role.name}**."
                )
                return True

            try:
                await message.author.remove_roles(role, reason="Žaidimo rolės nuėmimas")
                game_role_cooldowns[user_id] = time.time()

                await safe_reply(
                    message,
                    f"✅ Nusiėmei žaidimo rolę: **{role.name}**"
                )

            except discord.Forbidden:
                await safe_reply(message, "❌ Neturiu teisių nuimti šios rolės.")

            except Exception as e:
                await safe_reply(message, f"❌ Klaida nuimant žaidimo rolę: {e}")

            return True

    return False

# ======================
# HENRIKDEV API
# ======================

def fetch_valorant_rank_sync(name: str, tag: str):
    encoded_name = quote(name, safe="")
    encoded_tag = quote(tag, safe="")

    url = (
        f"https://api.henrikdev.xyz/valorant/v2/mmr/"
        f"{VALORANT_REGION}/{encoded_name}/{encoded_tag}"
    )

    headers = {
        "Authorization": VALORANT_API_KEY,
        "X-API-Key": VALORANT_API_KEY
    }

    response = requests.get(url, headers=headers, timeout=15)

    try:
        data = response.json()
    except Exception:
        raise ValueError(f"HenrikDev grąžino ne JSON atsakymą. HTTP: {response.status_code}")

    if response.status_code != 200:
        error_text = data.get("message") or data.get("error") or data.get("errors") or data
        raise ValueError(f"API klaida {response.status_code}: {error_text}")

    if data.get("status") != 200:
        raise ValueError(f"API status klaida: {data}")

    rank = data.get("data", {}).get("current_data", {}).get("currenttierpatched")
    rr = data.get("data", {}).get("current_data", {}).get("ranking_in_tier")
    elo = data.get("data", {}).get("current_data", {}).get("elo")

    if not rank:
        raise ValueError("Rankas nerastas. Gal žaidėjas nežaidė competitive arba blogas Riot ID.")

    return rank, rr, elo


async def fetch_valorant_rank(name: str, tag: str):
    return await asyncio.to_thread(fetch_valorant_rank_sync, name, tag)


async def update_valorant_rank_role(guild: discord.Guild, member: discord.Member, full_rank: str):
    base_rank = get_base_valorant_rank(full_rank)

    if not base_rank:
        raise ValueError("Nepavyko nustatyti ranko.")

    role_name = VALORANT_RANK_ROLES.get(base_rank)

    if not role_name:
        raise ValueError(f"Šitam rankui nėra nustatyta Discord rolė: {full_rank}")

    target_role = discord.utils.get(guild.roles, name=role_name)

    if not target_role:
        raise ValueError(f"Nerasta Discord rolė: {role_name}")

    bot_member = guild.get_member(bot.user.id)

    if not bot_member:
        raise ValueError("Nepavyko rasti boto serveryje.")

    if bot_member.top_role <= target_role:
        raise ValueError(
            f"Mano rolė per žemai. Pakelk boto rolę aukščiau už **{target_role.name}**."
        )

    valorant_role_names = list(VALORANT_RANK_ROLES.values())

    roles_to_remove = [
        role for role in member.roles
        if role.name in valorant_role_names and role != target_role
    ]

    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="Valorant rank update")

    if target_role not in member.roles:
        await member.add_roles(target_role, reason="Valorant rank verify/update")

    return base_rank, target_role

# ======================
# VALORANT VERIFY
# ======================

async def verify_valorant_account(message: discord.Message, riot_id: str):
    try:
        if not await require_verified(message):
            return

        if "#" not in riot_id:
            await message.reply(
                "❌ Naudok taip: `verify Vardas#TAG`\n"
                "Pvz: `verify Jonas#EUW`",
                mention_author=False
            )
            return

        name, tag = riot_id.split("#", 1)
        name = name.strip()
        tag = tag.strip()

        if not name or not tag:
            await message.reply(
                "❌ Blogas formatas. Naudok: `verify Vardas#TAG`",
                mention_author=False
            )
            return

        existing_link = get_user_valorant_link(message.guild.id, message.author.id)

        if existing_link:
            last_manual_verify = existing_link.get("manual_verified_at", 0)
            now = int(time.time())
            remaining = VERIFY_COOLDOWN_SECONDS - (now - last_manual_verify)

            if remaining > 0:
                next_verify_at = last_manual_verify + VERIFY_COOLDOWN_SECONDS

                await message.reply(
                    f"⏳ Rank verify gali naudoti tik kas **{VERIFY_COOLDOWN_HOURS} val.**\n"
                    f"Bandyk vėl: **{discord_relative_time(next_verify_at)}**\n"
                    f"🕒 Tikslus laikas: <t:{next_verify_at}:F>",
                    mention_author=False
                )
                return

        async with message.channel.typing():
            rank, rr, elo = await fetch_valorant_rank(name, tag)
            base_rank, role = await update_valorant_rank_role(message.guild, message.author, rank)

            save_user_valorant_link(
                guild_id=message.guild.id,
                user_id=message.author.id,
                name=name,
                tag=tag,
                rank=rank
            )

        next_verify_at = int(time.time()) + VERIFY_COOLDOWN_SECONDS

        await message.reply(
            f"✅ Valorant paskyra patikrinta: **{name}#{tag}**\n"
            f"🏆 Rankas: **{rank}**\n"
            f"📊 RR: **{rr}**\n"
            f"🔢 ELO: **{elo}**\n"
            f"🎭 Uždėta rolė: **{role.name}**\n"
            f"🔄 Rankas bus automatiškai tikrinamas kas **{VALORANT_UPDATE_HOURS} val.**\n"
            f"⏳ Rank verify vėl galėsi naudoti: **{discord_relative_time(next_verify_at)}**",
            mention_author=False
        )

    except Exception as e:
        await message.reply(
            f"❌ Klaida tikrinant Valorant ranką: {e}",
            mention_author=False
        )


async def send_valorant_help(message: discord.Message):
    await message.reply(
        "🎮 **Valorant pagalba**\n\n"
        "🏆 Rank rolė: parašyk `verify Vardas#TAG`\n"
        "Pvz: `verify Jonas#EUW`\n\n"
        "🎮 Žaidimo rolė: parašyk `valorant`\n\n"
        f"🔄 Rankas automatiškai atnaujinamas kas **{VALORANT_UPDATE_HOURS} val.**\n"
        f"⏳ Rank verify galima naudoti kas **{VERIFY_COOLDOWN_HOURS} val.**\n\n"
        "🎮 MMR info: parašyk `mmr` arba `valorant mmr`\n\n"
        "💬 Valorant klausimus gali rašyti AI kanale arba su `!ask klausimas`.",
        mention_author=False
    )


async def send_mmr_info(message: discord.Message):
    await message.reply(
        "🎮 **Valorant MMR**\n\n"
        "**MMR (Matchmaking Rating)** yra paslėpta sistema, kuri nustato tavo sugebėjimus "
        "ir padeda sukurti subalansuotus rungtynių poravimus.\n\n"
        "Kuo geriau žaidi, tuo didesnis tavo MMR. Jei tavo MMR yra aukštesnis už dabartinį ranką, "
        "gali gauti daugiau RR už pergalę ir prarasti mažiau RR už pralaimėjimą.\n\n"
        "📈 **Kaip pagerinti MMR:**\n"
        "• laimėk daugiau matchų;\n"
        "• žaisk stabiliai;\n"
        "• nedaryk tilt queue;\n"
        "• komunikuok su komanda;\n"
        "• turėk gerą impact žaidime;\n"
        "• žaisk agentus, su kuriais esi stipriausias.\n\n"
        "Jei turi klausimų dėl savo MMR arba kaip jį pagerinti, klausk AI kanale.",
        mention_author=False
    )


async def handle_no_prefix_valorant(message: discord.Message):
    original = message.content.strip()
    content = original.lower()

    if content in ["mmr", "valorant mmr", "kas yra mmr", "kas yra valorant mmr"]:
        await send_mmr_info(message)
        return True

    if content in [
        "rankai",
        "valorant rank",
        "valorant help",
        "pagalba valorant",
        "kaip gauti rank",
        "kaip gauti ranka",
        "kaip gauti rank rolę",
        "kaip gauti rank role"
    ]:
        await send_valorant_help(message)
        return True

    if content in ["verify", "patikrinti", "rankas"]:
        await message.reply(
            "❌ Naudok taip: `verify Vardas#TAG`\n"
            "Pvz: `verify Jonas#EUW`",
            mention_author=False
        )
        return True

    prefixes = [
        "verify ",
        "rank ",
        "rankas ",
        "patikrinti ",
        "patikrink "
    ]

    for prefix in prefixes:
        if content.startswith(prefix):
            riot_id = original[len(prefix):].strip()
            await verify_valorant_account(message, riot_id)
            return True

    return False

# ======================
# ANTI-SPAM
# ======================

def check_spam(message: discord.Message):
    user_id = message.author.id
    now = time.time()

    content = message.content.lower().strip()

    if not content:
        content = "[empty_or_attachment]"

    spam_messages[user_id].append({
        "time": now,
        "content": content
    })

    recent_messages = [
        item for item in spam_messages[user_id]
        if now - item["time"] <= SPAM_WINDOW_SECONDS
    ]

    if len(recent_messages) >= SPAM_MAX_MESSAGES:
        return "per daug žinučių per trumpą laiką"

    duplicate_messages = [
        item for item in spam_messages[user_id]
        if now - item["time"] <= DUPLICATE_WINDOW_SECONDS and item["content"] == content
    ]

    if len(duplicate_messages) >= DUPLICATE_MAX_MESSAGES:
        return "kartojamos tos pačios žinutės"

    if len(message.mentions) >= 5:
        return "mention spam"

    return None


def get_spam_punishment(user_id: int):
    now = int(time.time())
    record = spam_offenses[user_id]

    if record["last"] and now - record["last"] >= SPAM_OFFENSE_RESET_SECONDS:
        record["count"] = 0

    record["count"] += 1
    record["last"] = now

    offense_count = record["count"]
    punishment_index = min(offense_count - 1, len(SPAM_PUNISHMENTS) - 1)
    duration = SPAM_PUNISHMENTS[punishment_index]

    return offense_count, duration


async def delete_recent_spam_messages(message: discord.Message):
    now = discord.utils.utcnow()

    def check(msg: discord.Message):
        if msg.author.id != message.author.id:
            return False
        if msg.pinned:
            return False

        age = (now - msg.created_at).total_seconds()
        return age <= SPAM_DELETE_LOOKBACK_SECONDS

    try:
        await message.channel.purge(
            limit=SPAM_DELETE_LIMIT,
            check=check,
            bulk=True
        )
    except Exception:
        try:
            await message.delete()
        except Exception:
            pass


async def handle_spam(message: discord.Message):
    if not message.guild:
        return False

    if message.author.bot:
        return False

    if message.author.guild_permissions.administrator:
        return False

    if message.author.guild_permissions.manage_messages:
        return False

    user_id = message.author.id
    now = time.time()

    if user_id in spam_punish_cooldowns:
        if now - spam_punish_cooldowns[user_id] < 10:
            return True

    spam_reason = check_spam(message)

    if not spam_reason:
        return False

    spam_punish_cooldowns[user_id] = now
    offense_count, duration = get_spam_punishment(user_id)

    await delete_recent_spam_messages(message)

    warning_text = (
        f"⚠️ {message.author.mention}, **laikykitės tvarkos**.\n"
        f"Priežastis: **{spam_reason}**\n"
        f"Pažeidimas: **{offense_count}**\n"
        f"Skirtas timeout: **{format_duration(duration)}**"
    )

    try:
        until = discord.utils.utcnow() + timedelta(seconds=duration)

        await message.author.timeout(
            until,
            reason=f"Anti-spam: {spam_reason}"
        )

        await message.channel.send(
            warning_text,
            allowed_mentions=discord.AllowedMentions(users=True)
        )

    except discord.Forbidden:
        await message.channel.send(
            f"⚠️ {message.author.mention}, **laikykitės tvarkos**.\n"
            f"Spam žinutės ištrintos, bet negaliu uždėti timeout.\n"
            f"Reikia **Moderate Members** teisės ir boto rolė turi būti aukščiau.",
            allowed_mentions=discord.AllowedMentions(users=True)
        )

    except Exception as e:
        await message.channel.send(
            f"⚠️ {message.author.mention}, **laikykitės tvarkos**.\n"
            f"Nepavyko pritaikyti bausmės: `{e}`",
            allowed_mentions=discord.AllowedMentions(users=True)
        )

    return True

# ======================
# KEIKSMAŽODŽIŲ FILTRAS
# ======================

def normalize_bad_text(text: str):
    text = text.lower()

    normalized = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in normalized if not unicodedata.combining(char))

    replacements = {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "@": "a",
        "$": "s",
        "€": "e"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def contains_filtered_word(text: str):
    normalized = normalize_bad_text(text)

    spaced = normalized
    compact = re.sub(r"[^a-zA-Z0-9]", "", normalized)
    tokens = re.findall(r"\b\w+\b", normalized)

    for word in SEVERE_WORD_STEMS:
        clean_word = normalize_bad_text(word)
        clean_compact = re.sub(r"[^a-zA-Z0-9]", "", clean_word)

        if clean_word in spaced or clean_compact in compact:
            return "severe", word

    for word in BAD_WORD_STEMS:
        clean_word = normalize_bad_text(word)
        clean_compact = re.sub(r"[^a-zA-Z0-9]", "", clean_word)

        if len(clean_word) <= 3:
            if clean_word in tokens:
                return "normal", word
        else:
            if clean_word in spaced or clean_compact in compact:
                return "normal", word

    return None, None


def get_profanity_punishment(user_id: int):
    now = int(time.time())
    record = profanity_offenses[user_id]

    if record["last"] and now - record["last"] >= PROFANITY_RESET_SECONDS:
        record["count"] = 0

    record["count"] += 1
    record["last"] = now

    offense_count = record["count"]
    punishment_index = min(offense_count - 1, len(PROFANITY_PUNISHMENTS) - 1)
    duration = PROFANITY_PUNISHMENTS[punishment_index]

    return offense_count, duration


async def handle_profanity(message: discord.Message):
    if not message.guild:
        return False

    if message.author.bot:
        return False

    if message.author.guild_permissions.administrator:
        return False

    if message.author.guild_permissions.manage_messages:
        return False

    user_id = message.author.id
    now = time.time()

    if user_id in profanity_punish_cooldowns:
        if now - profanity_punish_cooldowns[user_id] < 5:
            return True

    severity, matched_word = contains_filtered_word(message.content)

    if not severity:
        return False

    profanity_punish_cooldowns[user_id] = now

    try:
        await message.delete()
    except Exception:
        pass

    if severity == "severe":
        offense_count, _ = get_profanity_punishment(user_id)
        duration = SEVERE_PROFANITY_TIMEOUT

        try:
            until = discord.utils.utcnow() + timedelta(seconds=duration)

            await message.author.timeout(
                until,
                reason="Rimtas draudžiamas žodis / grasinimas"
            )

            await message.channel.send(
                f"🚫 {message.author.mention}, **laikykitės tvarkos**.\n"
                f"Priežastis: **rimtas draudžiamas žodis / grasinimas**\n"
                f"Pažeidimas: **{offense_count}**\n"
                f"Skirtas timeout: **{format_duration(duration)}**",
                allowed_mentions=discord.AllowedMentions(users=True)
            )

        except discord.Forbidden:
            await message.channel.send(
                f"🚫 {message.author.mention}, **laikykitės tvarkos**.\n"
                f"Žinutė ištrinta, bet negaliu uždėti timeout.\n"
                f"Reikia **Moderate Members** teisės ir boto rolė turi būti aukščiau.",
                allowed_mentions=discord.AllowedMentions(users=True)
            )

        except Exception as e:
            await message.channel.send(
                f"🚫 {message.author.mention}, **laikykitės tvarkos**.\n"
                f"Nepavyko pritaikyti bausmės: `{e}`",
                allowed_mentions=discord.AllowedMentions(users=True)
            )

        return True

    offense_count, duration = get_profanity_punishment(user_id)

    if duration <= 0:
        await message.channel.send(
            f"⚠️ {message.author.mention}, **laikykitės tvarkos**.\n"
            f"Keiksmažodžiai ir įžeidimai serveryje draudžiami.\n"
            f"Pažeidimas: **{offense_count}**\n"
            f"Kitas kartas gali baigtis timeout.",
            allowed_mentions=discord.AllowedMentions(users=True)
        )
        return True

    try:
        until = discord.utils.utcnow() + timedelta(seconds=duration)

        await message.author.timeout(
            until,
            reason="Keiksmažodžiai / įžeidimai"
        )

        await message.channel.send(
            f"⚠️ {message.author.mention}, **laikykitės tvarkos**.\n"
            f"Keiksmažodžiai ir įžeidimai serveryje draudžiami.\n"
            f"Pažeidimas: **{offense_count}**\n"
            f"Skirtas timeout: **{format_duration(duration)}**",
            allowed_mentions=discord.AllowedMentions(users=True)
        )

    except discord.Forbidden:
        await message.channel.send(
            f"⚠️ {message.author.mention}, **laikykitės tvarkos**.\n"
            f"Žinutė ištrinta, bet negaliu uždėti timeout.\n"
            f"Reikia **Moderate Members** teisės ir boto rolė turi būti aukščiau.",
            allowed_mentions=discord.AllowedMentions(users=True)
        )

    except Exception as e:
        await message.channel.send(
            f"⚠️ {message.author.mention}, **laikykitės tvarkos**.\n"
            f"Nepavyko pritaikyti bausmės: `{e}`",
            allowed_mentions=discord.AllowedMentions(users=True)
        )

    return True

# ======================
# AUTO VALORANT UPDATE
# ======================

async def update_all_valorant_ranks():
    data = load_valorant_links()

    if not data:
        print("ℹ️ Nėra pririštų Valorant paskyrų.")
        return

    print(f"🔄 Pradedamas Valorant rankų auto update. Vartotojų: {len(data)}")

    updated = 0
    failed = 0

    for key, record in data.items():
        try:
            guild_id = int(record["guild_id"])
            user_id = int(record["user_id"])
            name = record["name"]
            tag = record["tag"]
            old_rank = record.get("last_rank")

            guild = bot.get_guild(guild_id)

            if not guild:
                print(f"❌ Guild nerastas: {guild_id}")
                failed += 1
                continue

            try:
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            except Exception:
                print(f"❌ Member nerastas: {user_id}")
                failed += 1
                continue

            new_rank, rr, elo = await fetch_valorant_rank(name, tag)

            await update_valorant_rank_role(guild, member, new_rank)
            update_user_last_rank(guild_id, user_id, new_rank)

            if old_rank != new_rank:
                print(f"✅ {name}#{tag}: {old_rank} -> {new_rank}")
            else:
                print(f"✅ {name}#{tag}: {new_rank}")

            updated += 1
            await asyncio.sleep(2)

        except Exception as e:
            print(f"❌ Auto update klaida {key}: {e}")
            failed += 1
            await asyncio.sleep(2)

    print(f"✅ Valorant auto update baigtas. Updated: {updated}, Failed: {failed}")


@tasks.loop(hours=VALORANT_UPDATE_HOURS)
async def valorant_rank_auto_update():
    await bot.wait_until_ready()
    await update_all_valorant_ranks()

# ======================
# BOT READY / JOIN
# ======================

@bot.event
async def on_ready():
    print("==============================")
    print(f"✅ Botas prisijungė: {bot.user}")
    print(f"✅ Serverių kiekis: {len(bot.guilds)}")
    print("==============================")

    for guild in bot.guilds:
        print(f"📌 Serveris: {guild.name} | ID: {guild.id}")

    if not valorant_rank_auto_update.is_running():
        valorant_rank_auto_update.start()
        print(f"✅ Valorant rank auto update paleistas kas {VALORANT_UPDATE_HOURS} val.")


@bot.event
async def on_member_join(member: discord.Member):
    await give_role(
        member,
        UNVERIFIED_ROLE_NAME,
        reason="Naujas narys - turi patvirtinti taisykles"
    )

    await send_welcome_message(member)

# ======================
# ŽINUČIŲ LOGIKA
# ======================

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild is None:
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    content = message.content.lower().strip()
    user_id = message.author.id

    if await handle_spam(message):
        return

    if await handle_profanity(message):
        return

    if await handle_rules_accept(message):
        return

    if await handle_game_role(message, content, user_id):
        return

    if await handle_no_prefix_valorant(message):
        return

    # ======================
    # VYRAS / PANELĖ
    # ======================

    if content in ["vyras", "panelė", "panele"]:
        if not await require_verified(message):
            return

        remaining = cooldown_left(role_cooldowns, user_id, ROLE_COOLDOWN)

        if remaining > 0:
            await safe_reply(message, f"⏳ Palauk {remaining}s prieš keičiant rolę.")
            return

        vyras_role = discord.utils.get(message.guild.roles, name=VYRAS_ROLE_NAME)
        panele_role = discord.utils.get(message.guild.roles, name=PANELE_ROLE_NAME)

        if not vyras_role:
            await safe_reply(message, "❌ Nerasta rolė **Vyras**. Sukurk ją Discord serveryje.")
            return

        if not panele_role:
            await safe_reply(message, "❌ Nerasta rolė **Panelė**. Sukurk ją Discord serveryje.")
            return

        bot_member = message.guild.get_member(bot.user.id)

        if not bot_member:
            await safe_reply(message, "❌ Nepavyko rasti boto serveryje.")
            return

        target_role = vyras_role if content == "vyras" else panele_role
        remove_role = panele_role if content == "vyras" else vyras_role

        if bot_member.top_role <= target_role or bot_member.top_role <= remove_role:
            await safe_reply(
                message,
                "❌ Mano rolė per žemai. Pakelk boto rolę aukščiau už **Vyras** ir **Panelė**."
            )
            return

        try:
            await message.author.add_roles(target_role, reason="Vyras/Panelė pasirinkimas")

            if remove_role in message.author.roles:
                await message.author.remove_roles(remove_role, reason="Vyras/Panelė pasirinkimas")

            role_cooldowns[user_id] = time.time()

            await safe_reply(message, f"✅ Gavai rolę: **{target_role.name}**")

        except discord.Forbidden:
            await safe_reply(message, "❌ Neturiu teisių duoti arba nuimti šios rolės.")
        except Exception as e:
            await safe_reply(message, f"❌ Klaida duodant rolę: {e}")

        return

    # ======================
    # AI KANALAI
    # ======================

    if is_ai_channel(message):
        remaining = cooldown_left(ai_cooldowns, user_id, AI_COOLDOWN)

        if remaining > 0:
            await safe_reply(message, f"⏳ Palauk {remaining}s prieš kitą AI klausimą.")
            return

        try:
            user_memory[user_id].append({
                "role": "user",
                "content": message.content
            })

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Tu esi MTX AI Discord serverio pagalbininkas. "
                        "Atsakyk lietuviškai, draugiškai, aiškiai ir trumpai. "
                        "Padėk žmonėms su Valorant: rankai, RR, MMR, agentai, mapai, crosshair, sensitivity, FPS, ping, klaidos, "
                        "beginner patarimai, aim training ir Discord rank sistema. "
                        "Jeigu klausia kaip gauti Valorant rank rolę, pasakyk: `verify Vardas#TAG`, pvz. `verify Jonas#EUW`. "
                        "Rankas atnaujinamas kas 12 val., verify galima naudoti kas 4 val. "
                        "Jeigu klausia apie MMR, paaiškink, kad tai paslėptas Matchmaking Rating. "
                        "Jeigu klausia apie Vyras/Panelė roles, pasakyk parašyti `vyras`, `panele` arba `panelė`. "
                        "Jeigu klausia apie žaidimų roles, pasakyk: `valorant`, `cs2`, `roblox`, `minecraft`. "
                        "Jeigu klausia apie taisykles, primink, kad reikia perskaityti taisykles ir patvirtinimo kanale parašyti `sutinku`. "
                        "Primink laikytis tvarkos, nespaminti ir gerbti kitus. "
                        "Nepadėk su seksualiniu turiniu, smurtu, žiauriais dalykais, cheat, hack, spoof, Vanguard bypass, ban evasion, phishing ar kenkėjiška veikla."
                    )
                }
            ]

            messages.extend(list(user_memory[user_id]))

            response = await client_ai.chat.completions.create(
                model=AI_MODEL,
                messages=messages
            )

            reply = response.choices[0].message.content or "Atsiprašau, nepavyko sugeneruoti atsakymo."

            user_memory[user_id].append({
                "role": "assistant",
                "content": reply
            })

            await safe_reply(message, reply)
            ai_cooldowns[user_id] = time.time()

        except Exception as e:
            await safe_reply(message, f"❌ AI klaida: {e}")

# ======================
# KOMANDOS
# ======================

@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply("🏓 Pong!", mention_author=False)


@bot.command(name="info")
async def info(ctx):
    await ctx.reply(
        "🤖 Aš esu **MTX AI** botas.\n\n"
        "📜 **Taisyklės:** perskaityk taisykles ir patvirtinimo kanale parašyk `sutinku`\n"
        "🎮 **Žaidimų rolės:** `valorant`, `cs2`, `roblox`, `minecraft`\n"
        "🏆 **Valorant rank:** `verify Vardas#TAG`\n"
        "🎮 **MMR:** `mmr` arba `valorant mmr`\n"
        "🎭 **Lyties rolės:** `vyras`, `panele`, `panelė`\n"
        "💬 **AI pagalba:** kanalai `ai`, `ᴀɪ`, `ai-chat`, `ᴀɪ-ᴄʜᴀᴛ`, arba `!ask klausimas`\n"
        "🧹 **Žinučių trynimas:** `!clear 100`\n\n"
        "⚠️ Laikykitės tvarkos — spam, keiksmažodžiai ir įžeidimai gali būti ištrinti ir uždėtas timeout.",
        mention_author=False
    )


@bot.command(name="valorant", aliases=["vhelp", "rankhelp"])
async def valorant_help(ctx):
    await send_valorant_help(ctx.message)


@bot.command(name="rules", aliases=["taisykles"])
async def rules_info(ctx):
    rules_channel = find_rules_channel(ctx.guild)
    accept_channel = find_rules_accept_channel(ctx.guild)

    if rules_channel and accept_channel:
        await ctx.reply(
            f"📜 Taisykles rasi čia: {rules_channel.mention}\n"
            f"✅ Patvirtinti reikia čia: {accept_channel.mention}\n"
            f"Perskaitęs palauk 1 min. ir parašyk: `sutinku`",
            mention_author=False
        )
    elif rules_channel:
        await ctx.reply(
            f"📜 Taisykles rasi čia: {rules_channel.mention}\n"
            f"Perskaitęs parašyk: `sutinku`",
            mention_author=False
        )
    else:
        await ctx.reply(
            "📜 Taisyklių kanalas nerastas. Sukurk kanalą `📜・taisykles`.",
            mention_author=False
        )


@bot.command(name="testwelcome")
@commands.has_permissions(administrator=True)
async def test_welcome(ctx):
    await send_welcome_message(ctx.author)
    await ctx.reply("✅ Welcome testas paleistas.", mention_author=False)


@bot.command(name="clear", aliases=["valyti", "trinti"])
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    if amount < 1:
        await ctx.reply("❌ Skaičius turi būti didesnis nei 0.", mention_author=False)
        return

    if amount > MAX_CLEAR_MESSAGES:
        await ctx.reply(
            f"❌ Maksimaliai galiu ištrinti **{MAX_CLEAR_MESSAGES}** žinučių vienu metu.",
            mention_author=False
        )
        return

    try:
        await ctx.send(f"🧹 Trinu **{amount}** žinučių...")

        deleted = await ctx.channel.purge(
            limit=amount + 2,
            bulk=False
        )

        result_msg = await ctx.send(
            f"✅ Ištrinta žinučių: **{max(len(deleted) - 1, 0)}**"
        )

        await result_msg.delete(delay=5)

    except discord.Forbidden:
        await ctx.reply(
            "❌ Botas neturi teisės trinti žinučių. Reikia **Manage Messages** teisės.",
            mention_author=False
        )

    except discord.HTTPException as e:
        await ctx.reply(
            f"❌ Discord klaida trinant žinutes: {e}",
            mention_author=False
        )

    except Exception as e:
        await ctx.reply(
            f"❌ Klaida trinant žinutes: {e}",
            mention_author=False
        )


@bot.command(name="verify")
async def verify(ctx, *, riot_id: str):
    if ctx.guild is None:
        await ctx.reply("❌ Ši komanda veikia tik serveryje.", mention_author=False)
        return

    await verify_valorant_account(ctx.message, riot_id)


@bot.command(name="valorantupdate", aliases=["rankupdate"])
@commands.has_permissions(administrator=True)
async def manual_valorant_update(ctx):
    await ctx.reply("🔄 Paleidžiu rankų atnaujinimą rankiniu būdu...", mention_author=False)

    try:
        await update_all_valorant_ranks()
        await ctx.send("✅ Rankų atnaujinimas baigtas.")
    except Exception as e:
        await ctx.send(f"❌ Klaida paleidžiant rankų update: {e}")


@bot.command(name="ask", aliases=["ai", "klausimas"])
async def ask_ai(ctx, *, question: str):
    user_id = ctx.author.id

    remaining = cooldown_left(ai_cooldowns, user_id, AI_COOLDOWN)

    if remaining > 0:
        await ctx.reply(
            f"⏳ Palauk {remaining}s prieš kitą AI klausimą.",
            mention_author=False
        )
        return

    try:
        async with ctx.typing():
            user_memory[user_id].append({
                "role": "user",
                "content": question
            })

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Tu esi MTX AI Discord serverio pagalbininkas. "
                        "Atsakyk lietuviškai, draugiškai, aiškiai ir trumpai. "
                        "Padėk su Valorant: rankai, MMR, RR, agentai, crosshair, sensitivity, FPS, klaidos, "
                        "rank roles Discorde, `verify Vardas#TAG`, žaidimų roles ir bendrais serverio klausimais. "
                        "Nepadėk su seksualiniu turiniu, smurtu, cheat, hack, spoof, Vanguard bypass ar nelegalia veikla."
                    )
                }
            ]

            messages.extend(list(user_memory[user_id]))

            response = await client_ai.chat.completions.create(
                model=AI_MODEL,
                messages=messages
            )

            reply = response.choices[0].message.content or "Atsiprašau, nepavyko sugeneruoti atsakymo."

            user_memory[user_id].append({
                "role": "assistant",
                "content": reply
            })

            await ctx.reply(
                reply[:1900],
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none()
            )

            ai_cooldowns[user_id] = time.time()

    except Exception as e:
        await ctx.reply(
            f"❌ AI klaida: {e}",
            mention_author=False
        )


@bot.command(name="mtxnaudojimas", aliases=["mtxinfo", "mtxai"])
@commands.has_permissions(administrator=True)
async def mtx_usage_announcement(ctx):
    ends_at = int(time.time()) + 24 * 60 * 60

    embed1 = discord.Embed(
        title="📢 NG COMMUNITY • MTX-AI NAUDOJIMO INFORMACIJA",
        description=(
            "Sveiki visi! 💙\n\n"
            "Norime oficialiai pranešti apie **MTX-AI** naudojimą **NG Community** serveryje.\n\n"
            "**MTX-AI** yra oficialus NG Community botas, sukurtas serverio savininko **MTX**. "
            "Tai nauja pagalbos, role, Valorant rank ir moderacijos sistema, kuri padės serveriui "
            "veikti tvarkingiau, saugiau ir moderniau."
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )

    if ctx.guild and ctx.guild.icon:
        embed1.set_thumbnail(url=ctx.guild.icon.url)

    embed1.add_field(
        name="👑 Apie savininką",
        value=(
            "Aš esu **MTX** — **NG Community** serverio savininkas.\n\n"
            "Šį serverį kuriu tam, kad žmonės turėtų vietą, kur gali bendrauti, žaisti, "
            "susirasti komandą, dalyvauti veiklose ir būti saugioje bendruomenėje.\n\n"
            "**MTX-AI** yra mano oficialus botas ir viena iš pagrindinių serverio sistemų."
        ),
        inline=False
    )

    embed1.add_field(
        name="🤖 Kas yra MTX-AI?",
        value=(
            "**MTX-AI** yra oficialus **NG Community** pagalbininkas.\n\n"
            "Tai automatinė pagalbos, role ir moderacijos sistema, kuri padeda nariams greičiau "
            "gauti informaciją, roles ir pagalbą, o administracijai sumažina rankinį darbą."
        ),
        inline=False
    )

    embed1.add_field(
        name="🧠 Ką gali MTX-AI?",
        value=(
            "• Padėti su **Valorant rank rolėmis**\n"
            "• Paaiškinti **MMR / RR / rank sistemą**\n"
            "• Duoti **žaidimų roles**\n"
            "• Duoti **lyties roles**\n"
            "• Atsakyti į klausimus kanale **ᴀɪ-ᴄʜᴀᴛ**\n"
            "• Padėti su **FPS, crosshair, sensitivity, agentais**\n"
            "• Padėti su serverio klausimais\n"
            "• Prižiūrėti tvarką automatiškai\n"
            "• Trinti spamą ir įžeidimus\n"
            "• Taikyti timeout už pažeidimus"
        ),
        inline=False
    )

    embed1.add_field(
        name="🎁 MTX-AI naudojimo naudos",
        value=(
            "Tam tikros **MTX-AI funkcijos**, specialios rolės ar papildomos naudos bus skirtos "
            "nariams, kurie prisideda prie **NG Community** augimo.\n\n"
            "Naudas galės gauti tie, kurie:\n"
            "🚀 **boostina serverį**\n"
            "💙 **paremia serverį**\n"
            "🏆 **dalyvauja arba laimi turnyruose**\n"
            "🌟 **aktyviai prisideda prie bendruomenės**\n"
            "🛠️ **padeda su idėjomis ar serverio tobulinimu**\n\n"
            "Tai padeda kurti aktyvią, sąžiningą ir motyvuotą bendruomenę."
        ),
        inline=False
    )

    embed1.add_field(
        name="⏳ 24 val. aktyvumo laikotarpis",
        value=(
            f"Specialių naudų / prioritetinio MTX-AI naudojimo laikotarpis aktyvus: **<t:{ends_at}:R>**\n"
            f"🕒 Tikslus pabaigos laikas: **<t:{ends_at}:F>**\n\n"
            "Per šį laiką galite sužinoti daugiau, prisidėti prie serverio ir pasiruošti būsimoms naudoms."
        ),
        inline=False
    )

    embed2 = discord.Embed(
        title="📌 Kaip naudotis MTX-AI?",
        description=(
            "Žemiau pateikta visa pagrindinė informacija, kaip naudotis serverio sistemomis."
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )

    if ctx.guild and ctx.guild.icon:
        embed2.set_thumbnail(url=ctx.guild.icon.url)

    embed2.add_field(
        name="📜 Kaip patekti į serverį?",
        value=(
            "Nauji nariai turi atlikti šiuos žingsnius:\n\n"
            "1️⃣ Nueiti į kanalą **📜・taisykles**\n"
            "2️⃣ Perskaityti taisykles\n"
            "3️⃣ Palaukti bent **1 minutę**\n"
            "4️⃣ Nueiti į kanalą **✅・patvirtinimas**\n"
            "5️⃣ Parašyti:\n"
            "`sutinku`\n\n"
            "Tada narys gauna **Narys** rolę ir gali naudotis serveriu."
        ),
        inline=False
    )

    embed2.add_field(
        name="🎮 Žaidimų rolės",
        value=(
            "Po taisyklių patvirtinimo gali pasirinkti žaidimų roles parašydamas:\n\n"
            "`valorant` — Valorant rolė\n"
            "`cs2` — CS2 rolė\n"
            "`roblox` — Roblox rolė\n"
            "`minecraft` — Minecraft rolė\n\n"
            "Nusiimti rolę gali su:\n"
            "`remove valorant`, `remove cs2`, `remove roblox`, `remove minecraft`"
        ),
        inline=False
    )

    embed2.add_field(
        name="🏆 Valorant rank rolė",
        value=(
            "Jeigu nori gauti savo Valorant rank rolę, parašyk:\n\n"
            "`verify Vardas#TAG`\n\n"
            "Pavyzdys:\n"
            "`verify Jonas#EUW`\n\n"
            "MTX-AI patikrins tavo Valorant ranką ir uždės atitinkamą Discord rolę:\n"
            "**Iron, Bronze, Silver, Gold, Platinum, Diamond, Ascendant, Immortal arba Radiant**.\n\n"
            "Rank verify galima naudoti kas **4 val.**\n"
            "Rankai automatiškai atnaujinami kas **12 val.**"
        ),
        inline=False
    )

    embed2.add_field(
        name="📊 MMR informacija",
        value=(
            "Jeigu nori sužinoti, kas yra Valorant MMR, parašyk:\n\n"
            "`mmr`\n\n"
            "MTX-AI paaiškins, kas yra **Matchmaking Rating**, kaip jis veikia ir kaip jį galima pagerinti."
        ),
        inline=False
    )

    embed2.add_field(
        name="🎭 Lyties rolės",
        value=(
            "Jeigu nori pasirinkti lyties rolę, parašyk:\n\n"
            "`vyras` — gauti **Vyras** rolę\n"
            "`panele` arba `panelė` — gauti **Panelė** rolę"
        ),
        inline=False
    )

    embed2.add_field(
        name="💬 AI pagalba",
        value=(
            "MTX-AI gali atsakyti į klausimus specialiame kanale:\n\n"
            "**ᴀɪ-ᴄʜᴀᴛ**\n\n"
            "Ten gali klausti apie Valorant, MMR, FPS, crosshair, roles, taisykles ar serverio naudojimą.\n\n"
            "Taip pat gali naudoti:\n"
            "`!ask tavo klausimas`"
        ),
        inline=False
    )

    embed2.add_field(
        name="🛡️ Serverio apsauga",
        value=(
            "Serveryje veikia automatinė apsauga:\n\n"
            "• anti-spam sistema\n"
            "• keiksmažodžių filtras\n"
            "• įžeidimų filtras\n"
            "• automatinis žinučių trynimas\n"
            "• timeout sistema\n"
            "• taisyklių patvirtinimo sistema\n\n"
            "Jeigu narys spamina, įžeidinėja ar pažeidžia taisykles, MTX-AI gali automatiškai reaguoti."
        ),
        inline=False
    )

    embed2.add_field(
        name="🚫 Ko MTX-AI nedaro?",
        value=(
            "MTX-AI nepadeda su:\n\n"
            "• seksualiniu turiniu\n"
            "• smurtu ar žiauriais dalykais\n"
            "• grasinimais\n"
            "• cheat / hack\n"
            "• Vanguard bypass\n"
            "• phishing / scam\n"
            "• kenkėjiška ar nelegalia veikla\n\n"
            "Tokie prašymai gali būti ignoruojami arba perduoti administracijai."
        ),
        inline=False
    )

    embed2.add_field(
        name="📌 Naudingos komandos",
        value=(
            "`valorant` — gauti Valorant žaidimo rolę\n"
            "`cs2` — gauti CS2 rolę\n"
            "`roblox` — gauti Roblox rolę\n"
            "`minecraft` — gauti Minecraft rolę\n\n"
            "`verify Vardas#TAG` — gauti Valorant rank rolę\n"
            "`mmr` — sužinoti apie Valorant MMR\n\n"
            "`vyras` — gauti Vyras rolę\n"
            "`panele` — gauti Panelė rolę\n\n"
            "`!ask klausimas` — paklausti MTX-AI\n"
            "`!info` — boto informacija"
        ),
        inline=False
    )

    embed2.add_field(
        name="💙 Pabaigai",
        value=(
            "NG Community serveris yra aktyvus ir toliau bus tobulinamas.\n\n"
            "MTX-AI sukurtas tam, kad viskas būtų paprasčiau nariams, administracijai ir visai bendruomenei.\n\n"
            "Ačiū visiems, kurie palaiko **NG Community**, prisideda prie serverio augimo ir padeda kurti geresnę bendruomenę.\n\n"
            "**NG Community juda į priekį! 🚀**"
        ),
        inline=False
    )

    embed2.set_footer(
        text=f"Paskelbė {ctx.author.display_name} • NG Community",
        icon_url=ctx.author.display_avatar.url
    )

    await ctx.send(embeds=[embed1, embed2])

# ======================
# KOMANDŲ KLAIDOS
# ======================

# ======================
# PALEIDIMAS
# ======================

bot.run(DISCORD_TOKEN)
