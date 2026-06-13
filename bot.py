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
    "rules",
    "📜・rules"
]

RULES_ACCEPT_WORDS = [
    "sutinku",
    "sutinku su taisyklemis",
    "sutinku su taisyklėmis",
    "patvirtinu",
    "accept",
    "agree"
]

WELCOME_BANNER_URL = "https://images.unsplash.com/photo-1511512578047-dfb367046420?q=80&w=1600&auto=format&fit=crop"

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
        ["taisykles", "rules"]
    )


def has_role(member: discord.Member, role_name: str):
    role = discord.utils.get(member.guild.roles, name=role_name)
    return role in member.roles if role else False


def has_verified_role(member: discord.Member):
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

    rules_channel = find_rules_channel(message.guild)

    if rules_channel:
        await safe_reply(
            message,
            f"📜 Pirma turi perskaityti taisykles ir parašyti `sutinku` kanale {rules_channel.mention}."
        )
    else:
        await safe_reply(
            message,
            "📜 Pirma turi perskaityti taisykles ir parašyti `sutinku` taisyklių kanale."
        )

    return False

# ======================
# WELCOME SISTEMA
# ======================

async def send_welcome_message(member: discord.Member):
    channel = find_welcome_channel(member.guild)

    if not channel:
        print("ℹ️ Welcome kanalas nerastas.")
        return

    member_count = member.guild.member_count or "?"

    embed = discord.Embed(
        title="🌐 Sveiki atvykę į NG COMMUNITY!",
        description=(
            f"Labas, {member.mention}! 👋\n\n"
            f"Džiaugiamės, kad prisijungei prie **{member.guild.name}** bendruomenės.\n"
            "Čia gali bendrauti, susirasti žmonių žaidimams, gauti pagalbos ir smagiai praleisti laiką.\n\n"
            "🤖 **Susipažink su manimi — MTX-AI**\n"
            "Mane rasi kanale **ᴀɪ-ᴄʜᴀᴛ**. Gali klausti apie Valorant, MMR, FPS, crosshair, agentus, roles ir serverio pagalbą."
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    if WELCOME_BANNER_URL:
        embed.set_image(url=WELCOME_BANNER_URL)

    embed.add_field(
        name="📜 Pirmas žingsnis",
        value=(
            "Perskaityk taisykles ir taisyklių kanale parašyk:\n"
            "`sutinku`\n\n"
            "Tik tada gausi pilną prieigą prie serverio."
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Žaidimų rolės",
        value=(
            "Po taisyklių patvirtinimo parašyk:\n"
            "`valorant` • `cs2` • `roblox` • `minecraft`\n\n"
            "Nusiimti rolę gali su:\n"
            "`remove valorant` • `remove cs2` • `remove roblox` • `remove minecraft`"
        ),
        inline=False
    )

    embed.add_field(
        name="🏆 Valorant rank rolė",
        value=(
            "Parašyk:\n"
            "`verify Vardas#TAG`\n\n"
            "Pvz:\n"
            "`verify Jonas#EUW`\n\n"
            "Rank verify galima naudoti kas **4 val.**"
        ),
        inline=False
    )

    embed.add_field(
        name="🎭 Lyties rolės",
        value=(
            "`vyras` — gauti **Vyras** rolę\n"
            "`panele` arba `panelė` — gauti **Panelė** rolę"
        ),
        inline=False
    )

    embed.add_field(
        name="⚠️ Tvarka",
        value=(
            "• Gerbk kitus\n"
            "• Nespamink\n"
            "• Nereklamuok be leidimo\n"
            "• Nenaudok keiksmažodžių / įžeidimų\n"
            "• Jokių cheat, hack ar kenkėjiškos veiklos"
        ),
        inline=False
    )

    embed.set_footer(
        text=f"Tu esi #{member_count} narys • Linkime gero laiko!",
        icon_url=member.guild.icon.url if member.guild.icon else None
    )

    try:
        await channel.send(
            content=f"👋 Sveikas atvykęs, {member.mention}!",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True)
        )
    except Exception as e:
        print(f"❌ Nepavyko išsiųsti welcome žinutės: {e}")


async def handle_rules_accept(message: discord.Message):
    content = message.content.lower().strip()

    if content not in RULES_ACCEPT_WORDS:
        return False

    rules_channel = find_rules_channel(message.guild)

    if rules_channel and message.channel.id != rules_channel.id:
        await safe_reply(
            message,
            f"📜 Taisykles reikia patvirtinti kanale {rules_channel.mention} parašant `sutinku`."
        )
        return True

    if has_verified_role(message.author):
        await safe_reply(message, "✅ Tu jau esi patvirtintas.")
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
            await safe_reply(
                message,
                f"❌ Nepavyko duoti rolės **{VERIFIED_ROLE_NAME}**. Patikrink roles ir boto poziciją."
            )
            return True

        await message.reply(
            "✅ **Taisyklės patvirtintos!**\n\n"
            "Dabar gali naudotis serveriu.\n\n"
            "🎮 Žaidimų rolės: `valorant`, `cs2`, `roblox`, `minecraft`\n"
            "🎭 Lyties rolės: `vyras`, `panele`\n"
            "🏆 Valorant rank rolė: `verify Vardas#TAG`\n"
            "📊 MMR info: `mmr`",
            mention_author=False
        )

    except discord.Forbidden:
        await safe_reply(
            message,
            "❌ Negaliu duoti rolės. Reikia **Manage Roles** ir boto rolė turi būti aukščiau."
        )

    except Exception as e:
        await safe_reply(message, f"❌ Klaida patvirtinant taisykles: {e}")

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
        "📜 **Taisyklės:** taisyklių kanale parašyk `sutinku`\n"
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

    if rules_channel:
        await ctx.reply(
            f"📜 Taisykles rasi čia: {rules_channel.mention}\n"
            f"Perskaitęs parašyk ten: `sutinku`",
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
