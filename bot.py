import os
import time
import discord
from discord.ext import commands
from openai import AsyncOpenAI
from collections import defaultdict, deque

# ======================
# KONFIGŪRACIJA
# ======================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not DISCORD_TOKEN:
    raise ValueError("❌ Nerastas DISCORD_TOKEN Railway Variables")

if not OPENAI_API_KEY:
    raise ValueError("❌ Nerastas OPENAI_API_KEY Railway Variables")

AI_MODEL = "gpt-4o-mini"

AI_COOLDOWN = 30
ROLE_COOLDOWN = 60
MAX_CLEAR_MESSAGES = 500

VYRAS_ROLE_NAME = "Vyras"
PANELE_ROLE_NAME = "Panelė"

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


# ======================
# ŽINUČIŲ LOGIKA
# ======================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild is None:
        return

    # Jeigu komanda prasideda su !
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
        status_msg = await ctx.send(f"🧹 Trinu **{amount}** žinučių...")

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
            "❌ Botui trūksta teisių. Reikia **Manage Messages**.",
            mention_author=False
        )

    elif isinstance(error, commands.BadArgument):
        await ctx.reply(
            "❌ Blogas formatas. Naudok taip: `!clear 100`",
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
