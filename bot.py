import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv("DISCORD_TOKEN")

@bot.event
async def on_ready():
    print(f"✅ Bot is online!")
    print(f"Logged in as: {bot.user.name} ({bot.user.id})")
    print(f"Connected to {len(bot.guilds)} server(s)")

    if not hasattr(bot, "synced"):  # only sync once
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash command(s)")
            bot.synced = True
        except Exception as e:
            print(f"❌ Failed to sync commands: {e}")

    print("─" * 40)

# Load all cogs from the 'cogs' folder
async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            cog_name = filename[:-3]
            try:
                await bot.load_extension(f'cogs.{cog_name}')
                print(f"✅ Loaded cog: {cog_name}")
            except Exception as e:
                print(f"❌ Failed to load cog {cog_name}: {e}")

# Command to manually reload cogs (admin only)
@bot.command(name="reload")
@commands.is_owner()
async def reload_cog(ctx, cog_name: str):
    """Reload a specific cog"""
    try:
        await bot.reload_extension(f'cogs.{cog_name}')
        await ctx.send(f"✅ Reloaded cog: {cog_name}")
    except Exception as e:
        await ctx.send(f"❌ Failed to reload {cog_name}: {str(e)}")

@bot.command(name="load")
@commands.is_owner()
async def load_cog(ctx, cog_name: str):
    """Load a specific cog"""
    try:
        await bot.load_extension(f'cogs.{cog_name}')
        await ctx.send(f"✅ Loaded cog: {cog_name}")
    except Exception as e:
        await ctx.send(f"❌ Failed to load {cog_name}: {str(e)}")

@bot.command(name="unload")
@commands.is_owner()
async def unload_cog(ctx, cog_name: str):
    """Unload a specific cog"""
    try:
        await bot.unload_extension(f'cogs.{cog_name}')
        await ctx.send(f"✅ Unloaded cog: {cog_name}")
    except Exception as e:
        await ctx.send(f"❌ Failed to unload {cog_name}: {str(e)}")

# Basic ping command
@bot.command(name="ping")
async def ping(ctx):
    """Check bot latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")

@bot.command(name="sync")
@commands.is_owner()
async def sync(ctx):
    """Sync slash commands to current guild (instant)"""
    try:
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ Synced {len(synced)} command(s) to this server!")
    except Exception as e:
        await ctx.send(f"❌ Failed to sync: {e}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)



from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run_web():
    app.run(host='0.0.0.0', port=10000)

threading.Thread(target=run_web).start()



if __name__ == "__main__":
    print("🤖 Starting Discord Bot...")
    print("Make sure to:")
    print("1. Replace YOUR_BOT_TOKEN_HERE with your actual bot token")
    print("2. Enable message content intent in Discord Developer Portal")
    print("─" * 40)
    
    asyncio.run(main())

