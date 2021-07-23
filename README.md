# telegram-bot

![Python Version](https://upload.wikimedia.org/wikipedia/commons/3/34/Blue_Python_3.6_Shield_Badge.svg)

Telegram bot written on Python that sends telegram messages regarding `Cozie` data points to current participants.


## Files
`credentials.py`: file with credentials for the database, telegram API, slack app, etc.

`telegram-bot.py`: main script that sends daily summary to current participants.

`user_progress.py`: class that queries and process participants' data.

`spaces_name.py`: mapping from `spaces_id` to `spaces_names`. The bot only looks for valid data points: Data points with an indoor location associated to them.

`chat_ids.csv` : mapping from `user_id` to `chat_id` (telegram chat id). The bot will only send messages to the participants listed here.

Whenever you are going to use this bot for field experiments, the files to modify are:
- `spaces_name.py` with any new location or modification of existing locations
- `chat_ids.csv` with the telegram `chat_ids` for the new participants

The bot also sends the same messages to a Slack channel for better monitoring.

We recommend setting up the main script as a `cronjob`. For example, a cronjob for everyday at 6pm:

```
0 18 * * * cd ~/telegram-bot/ && python telegram_bot.py
```

## Commands
The participant is allowed to type the following commands to the bot (not case sensitive):
- `/start`: Starts the conversation with the Bot.
- `help`: Returns a list of all available commands the bot recognises.
- `last vote`: Returns the date and time of the last Cozie response.

More commands can be added or the messages for the existing ones modified in the `read_user_msg` function on the `telegram_bot.py` file.

## FAQ
- How to create the telegram bot? [Answer](https://core.telegram.org/bots#6-botfather)
- How to add get the `chat_id` from a participant? [Answer](https://www.wikihow.com/Know-Chat-ID-on-Telegram-on-Android)
- How do I make the bot send messages to my Slack channel? [Answer](https://api.slack.com/start/overview)
