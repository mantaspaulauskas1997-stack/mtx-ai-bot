import os
import discord
from discord.ext import commands
from openai import OpenAI

TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client_ai = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"{bot.user} online")

@bot.event
async def on_message(message):
    print("GAUTA:", message.content)

    if message.author.bot:
        return

    # Ignoruojam privačias žinutes (DM)
    if not hasattr(message.channel, "name"):
        return

    # Atsako tik AI kanaluose
    if "ai" in message.channel.name.lower():
        try:
            response = client_ai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "{"role": "system", "content": "Tu esi MTX AI Discord botas."}
                    },
                    {
                        "role": "user",
                        "content": message.content
                    }
                ]
            )

            await message.reply(
                response.choices[0].message.content[:1900]
            )

        except Exception as e:
            await message.reply(f"Klaida: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
