import os
import time
import json
import asyncio
import requests
import discord

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

# Valorant nustatymai
VALORANT_REGION = "eu"
VALORANT_UPDATE_HOURS = 12
VALORANT_LINKS_FILE = "valorant_links.json"

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


def save_user_valorant_link(guild_id: int, user_id: int, name: str, tag: str, rank: str):
    data = load_valorant_links()
    key = get_link_key(guild_id, user_id)

    data[key] = {
        "guild_id": guild_id,
        "user_id": user_id,
        "name": name,
        "tag": tag,
        "region": VALORANT_REGION,
        "last_rank": rank,
        "updated_at": int(time.time())
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

    return "ai" in channel_name or "ai" in parent_name


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


def get_base_valorant_rank(full_rank: str):
    if not full_rank:
        return None

    return full_rank.split(" ")[0]


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
# AUTO VALORANT UPDATE KAS 12 VAL.
# ======================

@tasks.loop(hours=VALORANT_UPDATE_HOURS)
async def valorant_rank_auto_update():
    await bot.wait_until_ready()

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

        if bot_member.top_role <= target_role:
            await safe_reply(
                message,
                "❌ Mano rolė per žemai. Pakelk boto rolę aukščiau už **Vyras** ir **Panelė**."
            )
            return

        try:
            if content == "vyras":
                await message.author.add_roles(vyras_role, reason="Vyras/Panelė pasirinkimas")
                await message.author.remove_roles(panele_role, reason="Vyras/Panelė pasirinkimas")
                await safe_reply(message, "✅ Gavai rolę: **Vyras**")

            elif content in ["panelė", "panele"]:
                await message.author.add_roles(panele_role, reason="Vyras/Panelė pasirinkimas")
                await message.author.remove_roles(vyras_role, reason="Vyras/Panelė pasirinkimas")
                await safe_reply(message, "✅ Gavai rolę: **Panelė**")

            role_cooldowns[user_id] = time.time()

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
                        "Tu esi MTX AI Discord botas. "
                        "Atsakyk lietuviškai, draugiškai, aiškiai ir natūraliai. "
                        "Nenaudok per ilgų atsakymų, nebent vartotojas prašo detaliai."
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
        "🤖 Aš esu **MTX AI** botas.\n"
        "Parašyk `vyras` arba `panele`, kad gautum rolę.\n"
        "AI veikia kanaluose, kurių pavadinime yra `ai`.\n"
        "Valorant rank verify: `!verify Vardas#TAG`.\n"
        "Žinučių trynimas: `!clear 100` arba `!clear 500`.",
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
    try:
        if "#" not in riot_id:
            await ctx.reply(
                "❌ Naudok taip: `!verify Vardas#TAG`\nPvz: `!verify Jonas#EUW`",
                mention_author=False
            )
            return

        name, tag = riot_id.split("#", 1)

        name = name.strip()
        tag = tag.strip()

        if not name or not tag:
            await ctx.reply(
                "❌ Blogas formatas. Naudok: `!verify Vardas#TAG`",
                mention_author=False
            )
            return

        async with ctx.typing():
            rank, rr, elo = await fetch_valorant_rank(name, tag)
            base_rank, role = await update_valorant_rank_role(ctx.guild, ctx.author, rank)

            save_user_valorant_link(
                guild_id=ctx.guild.id,
                user_id=ctx.author.id,
                name=name,
                tag=tag,
                rank=rank
            )

        await ctx.reply(
            f"✅ Valorant paskyra patikrinta: **{name}#{tag}**\n"
            f"🏆 Rankas: **{rank}**\n"
            f"📊 RR: **{rr}**\n"
            f"🔢 ELO: **{elo}**\n"
            f"🎭 Uždėta rolė: **{role.name}**\n"
            f"🔄 Rankas bus automatiškai tikrinamas kas **{VALORANT_UPDATE_HOURS} val.**",
            mention_author=False
        )

    except Exception as e:
        await ctx.reply(
            f"❌ Klaida tikrinant Valorant ranką: {e}",
            mention_author=False
        )


@bot.command(name="valorantupdate", aliases=["rankupdate"])
@commands.has_permissions(administrator=True)
async def manual_valorant_update(ctx):
    await ctx.reply("🔄 Paleidžiu rankų atnaujinimą rankiniu būdu...", mention_author=False)

    try:
        await valorant_rank_auto_update()
        await ctx.send("✅ Rankų atnaujinimas baigtas.")
    except Exception as e:
        await ctx.send(f"❌ Klaida paleidžiant rankų update: {e}")


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
                "❌ Naudok taip: `!verify Vardas#TAG`",
                mention_author=False
            )
        elif ctx.command and ctx.command.name == "clear":
            await ctx.reply(
                "❌ Naudok taip: `!clear 100`",
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
