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
MAX_CLEAR_MESSAGES = 500

VYRAS_ROLE_NAME = "Vyras"
PANELE_ROLE_NAME = "Panelė"

# ======================
# VALORANT NUSTATYMAI
# ======================

VALORANT_REGION = "eu"
VALORANT_UPDATE_HOURS = 12
VALORANT_LINKS_FILE = "valorant_links.json"

VERIFY_COOLDOWN_HOURS = 24
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
# ANTI-SPAM NUSTATYMAI
# ======================

SPAM_WINDOW_SECONDS = 7
SPAM_MAX_MESSAGES = 5

DUPLICATE_WINDOW_SECONDS = 10
DUPLICATE_MAX_MESSAGES = 3

SPAM_DELETE_LIMIT = 20
SPAM_DELETE_LOOKBACK_SECONDS = 15

SPAM_OFFENSE_RESET_SECONDS = 24 * 60 * 60

SPAM_PUNISHMENTS = [
    60,      # 1 pažeidimas = 1 min
    300,     # 2 pažeidimas = 5 min
    3600     # 3+ pažeidimas = 1 val
]

# ======================
# KEIKSMAŽODŽIŲ FILTRAS
# ======================

PROFANITY_RESET_SECONDS = 24 * 60 * 60

PROFANITY_PUNISHMENTS = [
    0,       # 1 kartas = tik įspėjimas
    300,     # 2 kartas = 5 min
    3600     # 3+ kartas = 1 val
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

    # tavo papildomi žodžiai
    "niuh",
    "niuhas",
    "mantel",
    "mantelis",
    "gryb",
    "grybas"
]

SEVERE_WORD_STEMS = [
    # savęs žalojimo / labai rimtos frazės
    "nusizudyk",
    "nusižudyk",
    "zudykis",
    "žudykis",
    "uzsimusk",
    "užsimušk",
    "kill yourself",
    "kys",

    # grasinimai
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

    # rasistiniai / diskriminaciniai variantai
    "nyg",
    "nyga",
    "niga",
    "nigg",
    "+n+y+g+a",
    "n.y.g.a",
    "n-y-g-a",

    # labai toksiški / diskriminaciniai žodžiai
    "ciurka",
    "čiurka",
    "zydas",
    "žydas",

    # ekstremistiniai žodžiai
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
# DISCORD INTENTS
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
# ATMINTIS IR COOLDOWNS
# ======================

user_memory = defaultdict(lambda: deque(maxlen=10))

ai_cooldowns = {}
role_cooldowns = {}

spam_messages = defaultdict(lambda: deque(maxlen=30))
spam_offenses = defaultdict(lambda: {"count": 0, "last": 0})
spam_punish_cooldowns = {}

profanity_offenses = defaultdict(lambda: {"count": 0, "last": 0})
profanity_punish_cooldowns = {}

# ======================
# JSON DATABASE VALORANT
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
# PAGALBINĖS FUNKCIJOS
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

# ======================
# HENRIKDEV VALORANT API
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
# VALORANT VERIFY FUNKCIJA
# ======================

async def verify_valorant_account(message: discord.Message, riot_id: str):
    try:
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
        "Taip pat gali rašyti:\n"
        "`rank Vardas#TAG`\n\n"
        f"🔄 Rankas automatiškai atnaujinamas kas **{VALORANT_UPDATE_HOURS} val.**\n"
        f"⏳ Rank verify galima naudoti kas **{VERIFY_COOLDOWN_HOURS} val.**\n\n"
        "🎭 Lyties rolės: parašyk `vyras`, `panele` arba `panelė`.\n\n"
        "💬 Valorant klausimus gali rašyti AI kanale arba su `!ask klausimas`.",
        mention_author=False
    )


async def handle_no_prefix_valorant(message: discord.Message):
    original = message.content.strip()
    content = original.lower()

    if content in [
        "valorant",
        "rankai",
        "rank",
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
# ANTI-SPAM SISTEMA
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
# BOT READY
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

    # ======================
    # ANTI-SPAM
    # ======================

    if await handle_spam(message):
        return

    # ======================
    # KEIKSMAŽODŽIŲ FILTRAS
    # ======================

    if await handle_profanity(message):
        return

    # ======================
    # VALORANT BE ŠAUKTUKO
    # ======================

    if await handle_no_prefix_valorant(message):
        return

    # ======================
    # VYRAS / PANELĖ ROLĖS
    # ======================

    if content in ["vyras", "panelė", "panele"]:
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
    # AI SISTEMA
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
                        "Rankas atnaujinamas kas 12 val., verify galima naudoti kas 24 val. "
                        "Jeigu klausia apie Vyras/Panelė roles, pasakyk parašyti `vyras`, `panele` arba `panelė`. "
                        "Primink laikytis tvarkos, nespaminti ir gerbti kitus. "
                        "Nepadėk su cheat, hack, spoof, Vanguard bypass, ban evasion, phishing ar kenkėjiška veikla."
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
        "🎮 **Valorant:** parašyk `valorant` arba `verify Vardas#TAG`\n"
        "🎭 **Rolės:** parašyk `vyras`, `panele` arba `panelė`\n"
        "💬 **AI pagalba:** veikia kanaluose, kurių pavadinime yra `ai`, arba naudok `!ask klausimas`\n"
        "🧹 **Žinučių trynimas:** `!clear 100`\n\n"
        "⚠️ Laikykitės tvarkos — spam, keiksmažodžiai ir įžeidimai gali būti ištrinti ir uždėtas timeout.",
        mention_author=False
    )


@bot.command(name="valorant", aliases=["vhelp", "rankhelp"])
async def valorant_help(ctx):
    await ctx.reply(
        "🎮 **Valorant pagalba**\n\n"
        "🏆 Rank rolė: parašyk `verify Vardas#TAG`\n"
        "Pvz: `verify Jonas#EUW`\n\n"
        f"🔄 Rankas automatiškai atnaujinamas kas **{VALORANT_UPDATE_HOURS} val.**\n"
        f"⏳ Verify galima naudoti kas **{VERIFY_COOLDOWN_HOURS} val.**\n\n"
        "🎭 Lyties rolės: parašyk `vyras`, `panele` arba `panelė`.",
        mention_author=False
    )


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
                        "Padėk su Valorant: rankai, agentai, crosshair, sensitivity, FPS, klaidos, "
                        "rank roles Discorde, `verify Vardas#TAG`, ir bendrais serverio klausimais. "
                        "Nepadėk su cheat, hack, spoof, Vanguard bypass ar nelegalia veikla."
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

# ======================
# KOMANDŲ KLAIDOS
# ======================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply(
            "❌ Tu neturi reikalingų teisių šiai komandai.",
            mention_author=False
        )

    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.reply(
            "❌ Botui trūksta teisių.",
            mention_author=False
        )

    elif isinstance(error, commands.MissingRequiredArgument):
        if ctx.command and ctx.command.name == "verify":
            await ctx.reply(
                "❌ Naudok taip: `!verify Vardas#TAG` arba `verify Vardas#TAG`",
                mention_author=False
            )
        elif ctx.command and ctx.command.name == "clear":
            await ctx.reply(
                "❌ Naudok taip: `!clear 100`",
                mention_author=False
            )
        elif ctx.command and ctx.command.name == "ask":
            await ctx.reply(
                "❌ Naudok taip: `!ask tavo klausimas`",
                mention_author=False
            )
        else:
            await ctx.reply(
                "❌ Trūksta argumento komandai.",
                mention_author=False
            )

    elif isinstance(error, commands.BadArgument):
        await ctx.reply(
            "❌ Blogas formatas.",
            mention_author=False
        )

    elif isinstance(error, commands.CommandNotFound):
        return

    else:
        await ctx.reply(
            f"❌ Komandos klaida: {error}",
            mention_author=False
        )

# ======================
# PALEIDIMAS
# ======================

bot.run(DISCORD_TOKEN)
