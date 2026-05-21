
# SFHK Bot

Small Discord bot with slash commands for welcome/leave messages, XP tracking, scheduled event announcements, and voice XP.

## Features

- Welcome and leave messages (configurable per server)
- XP per message with leaderboard and level display
- Voice XP while users are in a voice channel
- Scheduled event announcements to a configured channel

## Requirements

- Python 3.10+
- A Discord bot token

## Setup
Optional:
Set up python venv
```
python -m venv venv
```

Windows:
```
.\venv\Scripts\activate
```

Linux:
```
source .\venv\bin\activate
```

1) Install dependencies

```
pip install -r requirements.txt
```

2) Rename .env.example to .env and insert your bot token

```
TOKEN='your_bot_token_here'
```

3) Run the bot

```
python main.py
```

## Commands

- /ping
- /help
- /leaderboard
- /setwelcome
- /setleaving
- /setwelcomemsg
- /setleavingmsg
- /setxppermessage
- /seteventchannel

## Config files

The bot stores per-server configuration in server_config.json and XP data in xp.json.