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

AI_COOLDOWN = 30      # sekundės
ROLE_COOLDOWN = 60    # sekundės

# ======================
# 🚀 READY
# ======================
@bot.event
async def on_ready():
    print(f"{bot.user} online")

# ======================
# 💬 MAIN LOGIC
# ======================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not hasattr(message.channel, "name"):
        return

    content = message.content.lower()
    now = time.time()

    # ======================
    # 🚫 AUTO-ROLE SYSTEM
    # ======================
    if content in ["vyras", "panelė", "panele"]:
        user_id = message.author.id

        # cooldown check
        if user_id in role_cooldowns:
            if now - role_cooldowns[user_id] < ROLE_COOLDOWN:
                remaining = int(ROLE_COOLDOWN - (now - role_cooldowns[user_id]))
                await message.reply(f"⏳ Palauk {remaining}s prieš keičiant rolę.")
                return

        role_name = "Vyras" if content == "vyras" else "Panelė"
        role = discord.utils.get(message.guild.roles, name=role_name)

        if role:
            await message.author.add_roles(role)
            await message.reply(f"✅ Gavai rolę: {role_name}")
            role_cooldowns[user_id] = now
        else:
            await message.reply("❌ Role nerasta serveryje")

        return

    # ======================
    # 🤖 AI SYSTEM (AI CHANNEL ONLY)
    # ======================
    if "ai" in message.channel.name.lower():

        user_id = message.author.id

        # AI cooldown
        if user_id in ai_cooldowns:
            if now - ai_cooldowns[user_id] < AI_COOLDOWN:
                remaining = int(AI_COOLDOWN - (now - ai_cooldowns[user_id]))
                await message.reply(f"⏳ Palauk {remaining}s prieš kitą AI klausimą.")
                return

        try:
            # 💾 save user message
            user_memory[user_id].append({
                "role": "user",
                "content": message.content
            })

            # 🧠 build history
            history = [
                {
                    "role": "system",
                    "content": "Tu esi MTX AI Discord botas. Atsimeni pokalbį ir atsakai natūraliai."
                }
            ]

            history.extend(list(user_memory[user_id]))

            # 🤖 AI request
            response = client_ai.chat.completions.create(
                model="gpt-4o-mini",
                messages=history
            )

            reply = response.choices[0].message.content

            # 💾 save AI response
            user_memory[user_id].append({
                "role": "assistant",
                "content": reply
            })

            await message.reply(reply[:1900])

            ai_cooldowns[user_id] = now

        except Exception as e:
            await message.reply(f"Klaida: {e}")

    await bot.process_commands(message)

# ======================
# ▶️ RUN BOT
# ======================
bot.run(TOKEN)
