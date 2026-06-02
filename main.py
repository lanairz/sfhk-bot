import discord
from discord.ext import commands, tasks
import json
import os
from dotenv import load_dotenv
import asyncio

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.guild_scheduled_events = True

bot = commands.Bot(command_prefix='!', intents=intents)

# to track active voice sessions: {(guild_id, user_id): asyncio.Task}
voice_tasks = {}

load_dotenv()
token = os.getenv('TOKEN')

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    await bot.tree.sync()
    print(f'Synced {len(bot.tree.get_commands())} commands.')
    print('Bot is ready!')
    refresh_leaderboards.start()

# ==================== Methods ====================

# awards XP to a user every minute they are in a voice channel, until they leave the voice channel
async def award_voice_xp_loop(member, xp_to_award):
    guild_id = str(member.guild.id)
    user_id = str(member.id)
    while True:
        await asyncio.sleep(60)

        if os.path.exists('server_config.json'):
            with open('server_config.json', 'r') as f:
                config = json.load(f)
        else:
            config = {}

        if os.path.exists('xp.json'):
            with open('xp.json', 'r') as f:
                xp_data = json.load(f)
        else:
            xp_data = {}

        if guild_id not in xp_data:
            xp_data[guild_id] = {}
        if user_id not in xp_data[guild_id]:
            xp_data[guild_id][user_id] = 0

        old_xp = xp_data[guild_id][user_id]
        xp_data[guild_id][user_id] += xp_to_award
        new_xp = xp_data[guild_id][user_id]

        old_level = xp_to_level(old_xp)
        new_level = xp_to_level(new_xp)
        if new_level > old_level:
            levelup_channel_id = config.get(guild_id, {}).get('levelup_channel_id')
            if levelup_channel_id:
                levelup_channel = bot.get_channel(levelup_channel_id)
                if levelup_channel:
                    await levelup_channel.send(f'Herzlichen Glückwunsch {member.mention}, du bist jetzt ⭐Level {new_level}⭐!')

        with open('xp.json', 'w') as f:
            json.dump(xp_data, f, indent=4)

# converts XP to level via a fixed system where each level requires 100 XP more than the previous one
def xp_to_level(xp):
    level = 0
    while xp >= 0:
        level += 1
        xp -= level * 100
    return level

def build_leaderboard_text(guild):
    """Build the full leaderboard message text for a guild."""
    guild_id = str(guild.id)

    if os.path.exists('xp.json'):
        with open('xp.json', 'r') as f:
            xp_data = json.load(f)
    else:
        xp_data = {}

    entries = xp_data.get(guild_id, {})
    sorted_xp = sorted(entries.items(), key=lambda x: x[1], reverse=True)

    rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}
    tier_thresholds = [
        (15, "💎"),  # Diamond
        (10, "🏆"),  # Gold
        (5,  "⚡"),  # Silver-ish
        (1,  "🌱"),  # Starter
    ]

    def get_tier(level):
        for threshold, icon in tier_thresholds:
            if level >= threshold:
                return icon
        return "🌱"

    lines = []
    lines.append("```")
    lines.append("╔═════════════════════════════════╗")
    lines.append("║    🏅  XP  LEADERBOARD  🏅     ║")
    lines.append("╚═════════════════════════════════╝")
    lines.append("```")

    if not sorted_xp:
        lines.append("*Noch keine XP-Daten vorhanden.*")
        lines.append("")
        lines.append(f"-# 🔄 Zuletzt aktualisiert: <t:{int(__import__('time').time())}:R>")
        return "\n".join(lines)

    top20 = sorted_xp[:20]

    for idx, (user_id, xp) in enumerate(top20, start=1):
        member = guild.get_member(int(user_id))
        name = member.display_name if member else f"Unbekannt ({user_id})"
        level = xp_to_level(xp)
        tier = get_tier(level)
        rank_icon = rank_emojis.get(idx, f"`{idx:>2}.`")

        # Build a compact bar (10 chars wide) based on XP relative to top user
        top_xp = sorted_xp[0][1] if sorted_xp else 1
        filled = round((xp / top_xp) * 8) if top_xp > 0 else 0
        bar = "█" * filled + "░" * (8 - filled)

        if idx <= 3:
            lines.append(f"{rank_icon} **{name}**")
            lines.append(f"  {tier} Level **{level}**  ┃  `{bar}`  ┃  {xp:,} XP")
        else:
            lines.append(f"`{idx:>2}.` {tier} **{name}** — Lvl {level} ┃ {xp:,} XP")

        if idx == 3 and len(top20) > 3:
            lines.append("─────────────────────────────────────────")

    lines.append("")
    lines.append(f"-# 🔄 Zuletzt aktualisiert: <t:{int(__import__('time').time())}:R>  •  Alle 60 Min. aktualisiert")

    return "\n".join(lines)

async def post_or_edit_leaderboard(guild):
    """Post a new leaderboard message or edit the existing one for a guild."""
    guild_id = str(guild.id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        return

    guild_config = config.get(guild_id, {})
    channel_id = guild_config.get('leaderboard_channel_id')
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        return

    text = build_leaderboard_text(guild)
    stored_msg_id = guild_config.get('leaderboard_message_id')

    # Try to edit existing message
    if stored_msg_id:
        try:
            msg = await channel.fetch_message(stored_msg_id)
            await msg.edit(content=text)
            return
        except (discord.NotFound, discord.Forbidden):
            pass  # Message gone or no perms — fall through to send a new one

    # Send a fresh message and save its ID
    new_msg = await channel.send(text)
    config[guild_id]['leaderboard_message_id'] = new_msg.id
    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)

# ==================== Background Task ====================

@tasks.loop(minutes=60)
async def refresh_leaderboards():
    """Refresh the leaderboard message in every configured guild every hour."""
    for guild in bot.guilds:
        try:
            await post_or_edit_leaderboard(guild)
        except Exception as e:
            print(f"Error refreshing leaderboard for guild {guild.id}: {e}")

@refresh_leaderboards.before_loop
async def before_refresh():
    await bot.wait_until_ready()

# ==================== Commands ====================

# slash command for ping
@bot.tree.command(name="ping", description="Check the bot's latency.")
async def ping(interaction: discord.Interaction):
    latency = bot.latency * 1000
    await interaction.response.send_message(f'Pong! Latency: {latency:.2f} ms', ephemeral=True)

# slash command for help
@bot.tree.command(name="help", description="Show the help message.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Help - SFHK Bot", description="Here are the available commands:", color=0x00ff00)
    embed.add_field(name="/ping", value="Check the bot's latency.", inline=False)
    if interaction.user.guild_permissions.administrator:
        embed.add_field(name="/setwelcome [channel]", value="Set the welcome channel for new members. (Admin only)", inline=False)
        embed.add_field(name="/setleaving [channel]", value="Set the leaving channel for members who leave. (Admin only)", inline=False)
        embed.add_field(name="/setwelcomemsg [message]", value="Set the welcome message for new members. Use {user} to mention the new member. (Admin only)", inline=False)
        embed.add_field(name="/setleavingmsg [message]", value="Set the leaving message for members who leave. Use {user} to mention the leaving member. (Admin only)", inline=False)
        embed.add_field(name="/setxppermessage [xp]", value="Set the amount of XP awarded per message. (Admin only)", inline=False)
        embed.add_field(name="/seteventchannel [channel]", value="Set the event channel for server events. (Admin only)", inline=False)
        embed.add_field(name="/setlevelupchannel [channel]", value="Set the channel for level-up messages. (Admin only)", inline=False)
        embed.add_field(name="/setleaderboardchannel [channel]", value="Set the live leaderboard channel (auto-updates every hour). (Admin only)", inline=False)
    embed.add_field(name="/leaderboard", value="Show the XP leaderboard for the server.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# slash command to set the welcome channel, only for administrators
@bot.tree.command(name="setwelcome", description="Set the welcome channel for new members.")
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    welcome_channel_id = channel.id

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]['welcome_channel_id'] = welcome_channel_id

    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)
    
    await interaction.response.send_message(f'Welcome channel set to {channel.mention}!', ephemeral=True)

# slash command to set the leaving channel, only for administrators
@bot.tree.command(name="setleaving", description="Set the leaving channel for members who leave.")
async def setleaving(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    leave_channel_id = channel.id

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]['leave_channel_id'] = leave_channel_id

    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)
    
    await interaction.response.send_message(f'Leaving channel set to {channel.mention}!', ephemeral=True)

# slash command to set the welcome message, only for administrators
@bot.tree.command(name="setwelcomemsg", description="Set the welcome message for new members.")
async def setwelcomemsg(interaction: discord.Interaction, *, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]['welcome_message'] = message

    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)
    
    await interaction.response.send_message('Welcome message updated!', ephemeral=True)

# slash command to set the leaving message, only for administrators
@bot.tree.command(name="setleavingmsg", description="Set the leaving message for members who leave.")
async def setleavingmsg(interaction: discord.Interaction, *, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]['leave_message'] = message

    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)
    
    await interaction.response.send_message('Leaving message updated!', ephemeral=True)

# slash command to set the amount of XP awarded per message, only for administrators
@bot.tree.command(name="setxppermessage", description="Set the amount of XP awarded per message.")
async def setxppermessage(interaction: discord.Interaction, xp: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]['xp_per_message'] = xp

    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)
    
    await interaction.response.send_message(f'XP per message set to {xp}!', ephemeral=True)

# slash command to set the event channel, only for administrators
@bot.tree.command(name="seteventchannel", description="Set the event channel for server events.")
async def seteventchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    event_channel_id = channel.id

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]['event_channel_id'] = event_channel_id

    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)
    
    await interaction.response.send_message(f'Event channel set to {channel.mention}!', ephemeral=True)

# slash command to show the XP leaderboard for the server
@bot.tree.command(name="leaderboard", description="Show the XP leaderboard for the server.")
async def leaderboard(interaction: discord.Interaction):
    embed = discord.Embed(title="XP Leaderboard", color=0xFFD700)
    guild_id = str(interaction.guild_id)
    if os.path.exists('xp.json'):
        with open('xp.json', 'r') as f:
            xp_data = json.load(f)
    else:
        xp_data = {}
    if guild_id in xp_data:
        sorted_xp = sorted(xp_data[guild_id].items(), key=lambda x: x[1], reverse=True)
        for idx, (user_id, xp) in enumerate(sorted_xp[:10], start=1):
            user = interaction.guild.get_member(int(user_id))
            if user:
                level = xp_to_level(xp)
                if idx == 1:
                    prefix = "🥇 "
                elif idx == 2:
                    prefix = "🥈 "
                elif idx == 3:
                    prefix = "🥉 "
                else:
                    prefix = f"{idx}. "
                embed.add_field(name=f"{prefix}{user.display_name}", value=f'{xp} XP - Level {level}', inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message('No XP data found for this server.', ephemeral=True)

# slash command to set the levelup message channel, only for administrators
@bot.tree.command(name="setlevelupchannel", description="Set the channel for level-up messages.")
async def setlevelupchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    levelup_channel_id = channel.id

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]['levelup_channel_id'] = levelup_channel_id

    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(f'Level-up channel set to {channel.mention}!', ephemeral=True)

# slash command to set the live leaderboard channel, only for administrators
@bot.tree.command(name="setleaderboardchannel", description="Set the channel for the live leaderboard (auto-updates every hour).")
async def setleaderboardchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id not in config:
        config[guild_id] = {}

    # If the channel changed, clear the old message ID so a fresh message is posted
    old_channel_id = config[guild_id].get('leaderboard_channel_id')
    if old_channel_id != channel.id:
        config[guild_id].pop('leaderboard_message_id', None)

    config[guild_id]['leaderboard_channel_id'] = channel.id

    with open('server_config.json', 'w') as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(
        f'Live leaderboard channel set to {channel.mention}! Posting the first update now…',
        ephemeral=True
    )

    # Post the first update immediately
    await post_or_edit_leaderboard(interaction.guild)

# ==================== Events ====================

@bot.event
async def on_scheduled_event_create(event):
    guild_id = str(event.guild_id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id in config and 'event_channel_id' in config[guild_id]:
        channel_id = config[guild_id]['event_channel_id']
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(f'@everyone\n{event.url}')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = str(message.guild.id)
    user_id = str(message.author.id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    xp_per_message = config.get(guild_id, {}).get('xp_per_message', 0)

    if xp_per_message > 0:
        if os.path.exists('xp.json'):
            with open('xp.json', 'r') as f:
                xp_data = json.load(f)
        else:
            xp_data = {}

        if guild_id not in xp_data:
            xp_data[guild_id] = {}
        if user_id not in xp_data[guild_id]:
            xp_data[guild_id][user_id] = 0
        old_xp = xp_data[guild_id][user_id]
        xp_data[guild_id][user_id] += xp_per_message
        new_xp = xp_data[guild_id][user_id]
        old_level = xp_to_level(old_xp)
        new_level = xp_to_level(new_xp)
        if new_level > old_level:
            levelup_channel_id = config.get(guild_id, {}).get('levelup_channel_id')
            if levelup_channel_id:
                levelup_channel = bot.get_channel(levelup_channel_id)
                if levelup_channel:
                    await levelup_channel.send(f'Herzlichen Glückwunsch {message.author.mention}, du bist jetzt ⭐Level {new_level}⭐!')

        with open('xp.json', 'w') as f:
            json.dump(xp_data, f, indent=4)

@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id in config and 'welcome_channel_id' in config[guild_id] and 'welcome_message' in config[guild_id]:
        channel_id = config[guild_id]['welcome_channel_id']
        welcome_message = config[guild_id]['welcome_message'].replace('{user}', member.mention)
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(welcome_message)

@bot.event
async def on_member_remove(member):
    guild_id = str(member.guild.id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if guild_id in config and 'leave_channel_id' in config[guild_id] and 'leave_message' in config[guild_id]:
        channel_id = config[guild_id]['leave_channel_id']
        leave_message = config[guild_id]['leave_message'].replace('{user}', member.mention)
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(leave_message)

@bot.event
async def on_voice_state_update(member, before, after):
    guild_id = str(member.guild.id)
    user_id = str(member.id)
    key = (guild_id, user_id)

    if os.path.exists('server_config.json'):
        with open('server_config.json', 'r') as f:
            config = json.load(f)
    else:
        config = {}

    xp_per_message = config.get(guild_id, {}).get('xp_per_message', 0)

    # User joined a voice channel (was not in one before)
    if before.channel is None and after.channel is not None:
        if key in voice_tasks:
            voice_tasks[key].cancel()
            del voice_tasks[key]
        if xp_per_message > 0:
            xp_to_award = (xp_per_message + 2) // 3
            for event in member.guild.scheduled_events:
                if event.status == discord.EventStatus.active and event.channel_id == after.channel.id:
                    xp_to_award = int(xp_to_award * 1.5)
                    break
            task = asyncio.create_task(award_voice_xp_loop(member, xp_to_award))
            voice_tasks[key] = task

    # User left a voice channel (is not in one after)
    elif before.channel is not None and after.channel is None:
        if key in voice_tasks:
            voice_tasks[key].cancel()
            del voice_tasks[key]

bot.run(token)