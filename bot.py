import os
import time
import discord
from discord.ext import commands
from openai import OpenAI
from collections import defaultdict, deque

# ======================
# 🔐 TOKENS
# ======================
TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    raise ValueError("❌ Nerastas DISCORD_TOKEN Railway Variables")

if not OPENAI_API_KEY:
    raise ValueError("❌ Nerastas OPENAI_API_KEY Railway Variables")

client_ai = OpenAI(api_key=OPENAI_API_KEY)

# ======================
# 🧠 INTENTS
# ======================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ======================
# 🧠 AI MEMORY
# ======================
user_memory = defaultdict(lambda: deque(maxlen=10))

# ======================
# 🚫 COOLDOWNS
# ======================
ai_cooldowns = {}
role_cooldowns = {}

AI_COOLDOWN = 30
ROLE_COOLDOWN = 60

# ======================
# 🚀 READY
# ======================
@bot.event
async def on_ready():
    print(f"✅ {bot.user} online")

    for guild in bot.guilds:
        vyras_role = discord.utils.get(guild.roles, name="Vyras")
        panele_role = discord.utils.get(guild.roles, name="Panelė")

        if not vyras_role:
            await guild.create_role(
                name="Vyras",
                colour=discord.Colour.blue(),
                reason="Auto role sistema"
            )
            print(f"✅ Sukurta rolė Vyras serveryje: {guild.name}")

        if not panele_role:
            await guild.create_role(
                name="Panelė",
                colour=discord.Colour.pink(),
                reason="Auto role sistema"
            )
            print(f"✅ Sukurta rolė Panelė serveryje: {guild.name}")

# ======================
# 💬 MAIN LOGIC
# ======================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Ignoruojam DM
    if message.guild is None:
        return

    content = message.content.lower().strip()
    now = time.time()

    # ======================
    # 🚻 AUTO-ROLE SYSTEM
    # ======================
    if content in ["vyras", "panelė", "panele"]:
        user_id = message.author.id

        if user_id in role_cooldowns:
            if now - role_cooldowns[user_id] < ROLE_COOLDOWN:
                remaining = int(ROLE_COOLDOWN - (now - role_cooldowns[user_id]))
                await message.reply(f"⏳ Palauk {remaining}s prieš keičiant rolę.")
                return

        vyras_role = discord.utils.get(message.guild.roles, name="Vyras")
        panele_role = discord.utils.get(message.guild.roles, name="Panelė")

        if not vyras_role or not panele_role:
            await message.reply("❌ Rolės nerastos. Perkrauk botą arba sukurk roles rankiniu būdu.")
            return

        try:
            if content == "vyras":
                await message.author.add_roles(vyras_role)
                await message.author.remove_roles(panele_role)
                await message.reply("✅ Gavai rolę: Vyras")

            elif content in ["panelė", "panele"]:
                await message.author.add_roles(panele_role)
                await message.author.remove_roles(vyras_role)
                await message.reply("✅ Gavai rolę: Panelė")

            role_cooldowns[user_id] = now

        except discord.Forbidden:
            await message.reply("❌ Neturiu teisių duoti rolių. Pakelk mano rolę aukščiau.")
        except Exception as e:
            await message.reply(f"❌ Klaida duodant rolę: {e}")

        return

    # ======================
    # 🤖 AI SYSTEM
    # ======================
    if "ai" in message.channel.name.lower():
        user_id = message.author.id

        if user_id in ai_cooldowns:
            if now - ai_cooldowns[user_id] < AI_COOLDOWN:
                remaining = int(AI_COOLDOWN - (now - ai_cooldowns[user_id]))
                await message.reply(f"⏳ Palauk {remaining}s prieš kitą AI klausimą.")
                return

        try:
            user_memory[user_id].append({
                "role": "user",
                "content": message.content
            })

            history = [
                {
                    "role": "system",
                    "content": "Tu esi MTX AI Discord botas. Atsakyk lietuviškai, draugiškai ir natūraliai."
                }
            ]

            history.extend(list(user_memory[user_id]))

            response = client_ai.chat.completions.create(
                model="gpt-4o-mini",
                messages=history
            )

            reply = response.choices[0].message.content

            user_memory[user_id].append({
                "role": "assistant",
                "content": reply
            })

            await message.reply(reply[:1900])
            ai_cooldowns[user_id] = now

        except Exception as e:
            await message.reply(f"❌ AI klaida: {e}")

    await bot.process_commands(message)

# ======================
# ▶️ RUN BOT
# ======================
bot.run(TOKEN)
