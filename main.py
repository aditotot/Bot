import os  # Import OS module to read secrets
import discord
import random
from discord.ext import commands

# Get the bot token from Replit Secrets
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Intents setup
intents = discord.Intents.default()
intents.message_content = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

# Image list
image_links = [
    "https://media.discordapp.net/attachments/1346804495983575094/1349477533187313716/NA.jpg",
    "https://media.discordapp.net/attachments/1346804495983575094/1349477533606871080/Anti.jpg",
    "https://media.discordapp.net/attachments/1346804495983575094/1349477534173106289/Dead.png",
    "https://media.discordapp.net/attachments/1346804495983575094/1349477534646927512/Vish.png",
    "https://media.discordapp.net/attachments/1346804495983575094/1349477535012098179/Meow.jpg",
    "https://media.discordapp.net/attachments/1346804495983575094/1349477535318147092/Bhaijaan.jpg",
    "https://media.discordapp.net/attachments/1346804495983575094/1349477535678992505/Nik.jpg",
    "https://media.discordapp.net/attachments/1346804495983575094/1349477536010338364/Netzo.jpg",
    "https://media.discordapp.net/attachments/1346804495983575094/1349477536324915341/Pyaradox.jpg",
    "https://cdn.discordapp.com/attachments/1346804495983575094/1349477536752472104/Rebelartist.jpg"
]

# Storage for used, sold, and unsold images
used_images = []
sold_images = set()
unsold_images = []


# Function to reset memory
def reset_memory():
    global used_images, sold_images, unsold_images
    used_images = []
    sold_images = set()
    unsold_images = []


# Start command (resets memory)
@bot.command()
async def start(ctx):
    reset_memory()
    await ctx.send("✅ Bot memory has been reset. Ready to summon images!")


# Reset command (resets memory anytime)
@bot.command()
async def reset(ctx):
    reset_memory()
    await ctx.send("🔄 All memory has been reset.")


# Summon command (sends a random image)
@bot.command()
async def summon(ctx):
    global used_images, unsold_images

    # Get available images
    available_images = [
        img for img in image_links
        if img not in used_images and img not in sold_images
    ]

    # If all images are used, allow unsold images again
    if not available_images and unsold_images:
        available_images = unsold_images.copy()
        unsold_images = []
        message = "**This is an unsold player!**"
    else:
        message = ""

    # If no images left, notify user
    if not available_images:
        await ctx.send("⚠️ No more images left to summon.")
        return

    # Choose a random image
    chosen_image = random.choice(available_images)
    used_images.append(chosen_image)

    # Send the image
    embed = discord.Embed(description=message)
    embed.set_image(url=chosen_image)
    await ctx.send(embed=embed)


# Sold command (marks last image as sold)
@bot.command()
async def sold(ctx):
    if used_images:
        last_image = used_images[-1]
        sold_images.add(last_image)
        await ctx.send("✅ Marked as SOLD. This image will not be repeated.")
    else:
        await ctx.send("⚠️ No image has been summoned yet!")


# Unsold command (marks last image as unsold)
@bot.command()
async def unsold(ctx):
    if used_images:
        last_image = used_images[-1]
        if last_image in sold_images:
            sold_images.remove(last_image)
        unsold_images.append(last_image)
        await ctx.send("✅ Marked as UNSOLD. This image may be summoned again.")
    else:
        await ctx.send("⚠️ No image has been summoned yet!")


# Bot startup confirmation
@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} is now online!")


# Run the bot
if TOKEN:
    bot.run(TOKEN)
else:
    print(
        "❌ ERROR: Bot token is missing! Make sure you added it in Replit Secrets."
    )
