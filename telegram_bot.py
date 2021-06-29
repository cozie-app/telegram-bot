import os
import sys
import json
import time
import logging
import requests
import pandas as pd
import seaborn as sns
import credentials as cd

from user_progress import *
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import collections.abc
from logging.handlers import RotatingFileHandler


def init_logger(log_file_location, name="main", limit_log_file_size=True):
    """Creates a logger to keep track of code errors and notifications"""
    # logger
    log_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s"
    )
    if limit_log_file_size:
        my_handler = RotatingFileHandler(
            log_file_location,
            mode="a",
            maxBytes=5 * 1024 * 1024,
            backupCount=1,
            encoding=None,
            delay=0,
        )
    else:
        my_handler = logging.FileHandler(log_file_location)

    my_handler.setFormatter(log_formatter)
    my_handler.setLevel(logging.INFO)
    app_log = logging.getLogger(name)
    app_log.setLevel(logging.INFO)
    app_log.addHandler(my_handler)

    # create console handler and set level to debug
    if debugging:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(log_formatter)
        app_log.addHandler(ch)

    return app_log


def init_msg_logs(log_file_location):
    """open file containing message logs, if it doesn't exist create one"""
    try:
        log_msg = json.load(open(log_file_location))
    except FileNotFoundError:
        log_msg = dict()
        json.dump(log_msg, open(log_file_location, "w"))

    return log_file_location


def update(d, u, save_location):
    """Update a dictionary without overriding existing keys and/or fields"""
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update(d.get(k, {}), v, save_location)
        else:
            d[k] = v
    json.dump(d, open(save_location, "w"))

    return d


def read_user_msg(
    chat_id, participant_id, vote_timestamp, log_msg_location, logger, logger_msg_sent
):
    # dictionary of commands and their responses
    telegram_available_requests = {"help": {}}
    telegram_available_requests["last vote"] = {
        "description": "Returns the date and time of the last fitbit response",
        "return": vote_timestamp.strftime("%b-%d %H:%M")
        if vote_timestamp is not None
        else "Error",
    }
    help_msg = (
        f"Welcome to the {cd.experiment_name} experiment. This telegram bot "
        + "will be used to automatically send you messages about your progress "
        + "during the experiment. In addition you can chat with the bot and "
        + "ask a predefined set of questions.\n\n"
        + 'Type and send "help" if you want to know the list of available '
        + "commands you can ask bo the Bot\n\n"
        + "Please remember that the Bot won't be able to answer any other "
        + "request. Hence, please contact the research team via the designated "
        + "telegram group. There might be a delay of a few minutes between "
        + "the time you type and send a request and the time you receive and answer. "
        + f"Thank you once again for participating in the {cd.experiment_name} experiment."
    )
    telegram_available_requests["/start"] = {
        "description": "Message when the user initiate a conversation with the Bot",
        "return": help_msg,
    }
    telegram_available_requests["help"] = {
        "description": "Returns list of available requests",
        "return": f'List of available requests: {str(", ".join(list(telegram_available_requests.keys())))}',
    }
    # open logs of previous messages
    log_msg = json.load(open(log_msg_location))
    # get telegram response
    response = requests.get(f"https://api.telegram.org/bot{cd.token}/getUpdates")

    if response.status_code == 200:
        all_incoming_msgs = response.json()["result"]
        logger.info(f"all messages: {all_incoming_msgs}")

        msgs_user = []
        for msg_user in all_incoming_msgs:
            if "message" in msg_user.keys():
                if msg_user["message"]["from"]["id"] == chat_id:
                    msgs_user.append(msg_user)

        # after changes in the API about chat members
        # msgs_user = [msg_user for msg_user in all_incoming_msgs if msg_user['message']['from']['id'] == chat_id]

        # get the last incoming message id from telegram that has already been processed
        try:
            last_handled_msg_id = log_msg[str(chat_id)]["incoming_msg"]["telegram_chat"]
        except KeyError:
            try:
                oldest_id = msgs_user[0]["message"]["message_id"] - 1
                logger.info("MESSAGE ID DECREASED BY 1")
            except IndexError:
                oldest_id = 0

            log_msg = update(
                log_msg,
                {str(chat_id): {"incoming_msg": {"telegram_chat": oldest_id}}},
                log_msg_location,
            )
            last_handled_msg_id = log_msg[str(chat_id)]["incoming_msg"]["telegram_chat"]

        logger.info(f"old message id: {last_handled_msg_id}")
        # go through all the received messages but only respond the last one
        for msg_to_process in [
            msg
            for msg in msgs_user
            if msg["message"]["message_id"] > last_handled_msg_id
        ]:
            logger.info(f'new message id: {msg_to_process["message"]["message_id"]}')
            try:
                text_message = msg_to_process["message"]["text"].lower()
            except KeyError:
                logger.error("Error while reading user's message")
                continue
            logger.info(f"Telegram bot received a new message: {text_message}")

            # if the user asked something that the bot does not know, send him list of available quesitons
            if text_message not in telegram_available_requests.keys():
                send_text(
                    "The bot cannot answer this request. List of available requests:",
                    chat_id,
                    logger,
                    logger_msg_sent,
                )
                for key in telegram_available_requests.keys():
                    message = (
                        key + ": " + telegram_available_requests[key]["description"]
                    )
                    send_text(message, participant_id, logger, logger_msg_sent)

            for key in telegram_available_requests.keys():
                if text_message == key:
                    send_text(
                        f"You have asked the bot for {key}:",
                        chat_id,
                        logger,
                        logger_msg_sent,
                    )
                    send_text(
                        telegram_available_requests[key]["return"],
                        chat_id,
                        logger,
                        logger_msg_sent,
                    )

            log_msg = update(
                log_msg,
                {
                    str(chat_id): {
                        "incoming_msg": {
                            "telegram_chat": msg_to_process["message"]["message_id"]
                        }
                    }
                },
                log_msg_location,
            )


def send_text(msg, telegram_id, logger, logger_msg_sent):
    """Format string message to send via telegram"""
    token = cd.token
    send_text = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={telegram_id}&parse_mode=Markdown&text={msg}"
    response = requests.get(send_text)
    logger.info(f"Telegram message to telegram_id: {telegram_id}, message: {msg}")
    logger_msg_sent.info(f"##telegram_id: {telegram_id}, message: {msg}")

    return response.json()


def send_data_slack_channel(
    msg, reference_app="Telegram-bot", msg_level="Error", image=False
):
    """
    This function sends data to Slack webhooks in Python with the requests module.
    Detailed documentation of Slack Incoming Webhooks:
    - https://api.slack.com/incoming-webhooks
    - https://api.slack.com/messaging/webhooks#posting_with_webhooks
    """

    # sending an image is slightly different, treat it separately
    if image:
        # msg here is the filename
        f = {"file": (msg, open(msg, "rb"), "image/png", {"Expires": "0"})}
        response = requests.post(
            url="https://slack.com/api/files.upload",
            data={"token": cd.slack_token, "channels": cd.slack_channel, "media": f},
            headers={"Accept": "application/json"},
            files=f,
        )
        return response.text

    # set the webhook_url to the one provided by Slack when you create the webhook at https://my.slack.com/services/new/incoming-webhook/
    if msg_level == "Error":
        color = "red"

    webhook_url = cd.slack_webhook_url
    slack_data = {
        "type": "mrkdwn",
        "text": f"*{reference_app}* - `{msg_level}` - {msg}",
    }

    response = requests.post(
        webhook_url,
        data=json.dumps(slack_data),
        headers={"Content-Type": "application/json"},
    )
    if response.status_code != 200:
        raise ValueError(
            "Request to slack returned an error %s, the response is:\n%s"
            % (response.status_code, response.text)
        )

    return response.text


#####
debugging = False  # DEBUGGING

#####
# start loggers
logger = init_logger(os.path.join(os.getcwd(), "logs.log"))
logger.info("===============")
logger_msg_sent = init_logger(
    os.path.join(os.getcwd(), "logs_msg_sent.log"),
    name="telegram_logger",
    limit_log_file_size=False,
)

# start messages logs
logs_msg_location = init_msg_logs(os.path.join(os.getcwd(), "logs_msg.json"))

##### analyze each participant
# get current list of participants
df_users = pd.read_csv(cd.user_id_file)

if debugging:
    list_participants = ["enth28", "esk04"]
else:
    list_participants = df_users["user"].unique()

# dictionary to store the users and their respective votes
users_votes = {}
users_last_vote_time = {}
users_last_vote_unit = {}

# only send automatic messages to the participant and to slack at 6pm (UTC + 8) +/- 1min
threshold = pd.Timestamp.now().replace(hour=10, minute=0, second=0)  # 10am in UTC
cur_time = pd.Timestamp.now()
is_time = cur_time >= threshold - timedelta(
    minutes=1
) and cur_time <= threshold + timedelta(minutes=1)
send_plots = False
no_data = False

for participant_id in list_participants:
    try:
        user_data = df_users[df_users["user"] == participant_id].to_dict("records")[
            0
        ]  # only one row
        logger.info(f"=== Analysing user: {participant_id}")
        user_progress = UserProgress(
            min_votes=80, min_time_between_votes=14, loc_threshold_time_tol=14
        )

        # check last Cozie vote and notify the user if the vote was > 2 days ago
        last_vote_time, time_units, vote_timestamp = user_progress.last_vote(
            participant_id
        )
        if last_vote_time is None:
            last_vote_msg = (
                f"Hey {participant_id}, looks like there are no previous votes from you"
            )
            logger.info(f"=== No data for {participant_id}")
            no_data = True
        else:
            last_vote_msg = f"Last Cozie vote was {last_vote_time:.0f} {time_units} ago"
            logger.info(f"=== {last_vote_msg}")

        if debugging:
            send_text(last_vote_msg, user_data["chat_id"], logger, logger_msg_sent)
            logger.info(f"=== forced message sent to {participant_id}")
            if not no_data:
                msg, num_votes = user_progress.daily_report(participant_id)
                send_text(msg, user_data["chat_id"], logger, logger_msg_sent)
                logger.info(f"=== forced report sent to {participant_id}")

        if time_units == "days" and not debugging and is_time:
            send_plots = True
            send_text(last_vote_msg, user_data["chat_id"], logger, logger_msg_sent)
            send_data_slack_channel(
                f"Last vote for participant {participant_id} was {last_vote_time:.0f} {time_units} ago",
                msg_level="Error",
            )

        # check if the user typed asking for the type of the last vote
        read_user_msg(
            user_data["chat_id"],
            participant_id,
            vote_timestamp,
            logs_msg_location,
            logger,
            logger_msg_sent,
        )

        # send progress summaries (only at 6pm with a tolerance of 2min)
        if is_time and participant_id != "test":
            if no_data:
                msg = last_vote_msg
                num_votes = 0
            else:
                msg, num_votes = user_progress.daily_report(participant_id)

            send_plots = True
            send_text(msg, user_data["chat_id"], logger, logger_msg_sent)

            if not debugging:  # otherwise it will spam the slack channel in every run
                send_data_slack_channel(msg, msg_level="Info")
                # check if participant finished the experiment
                if num_votes >= user_progress.min_votes:
                    send_data_slack_channel(
                        f"Participant {participant_id} just finished all required datapoints!",
                        msg_level="Info",
                    )

            # update user-votes dictionary for slack plots
            users_votes[participant_id] = num_votes
            users_last_vote_unit[participant_id] = time_units
            if time_units == "days":  # daily votes plot only shows days
                users_last_vote_time[participant_id] = last_vote_time
            else:
                users_last_vote_time[participant_id] = 0

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logger.error("Code stopped with error below:")
        logger.error(exc_type, f_name, exc_tb.tb_lineno)
        if (
            not debugging
        ):  # otherwise it will spam the slack channel with any small error
            send_data_slack_channel(
                f"Coded stopped with error - {participant_id} : {exc_type, f_name, exc_obj, exc_tb.tb_lineno}",
                msg_level="Error",
            )

#####
# generate summary plot
if send_plots:
    df_summary = pd.DataFrame.from_dict(
        users_votes, orient="index", columns=["Total votes"]
    )
    plot_time = pd.Timestamp.now(cd.time_zone).strftime("%b-%d %H:%M")

    fig, ax = plt.subplots(
        1, 1, constrained_layout=True, sharey=True, figsize=[8.06, 4.51]
    )
    sns.barplot(y=df_summary.index, x=df_summary["Total votes"], ax=ax)
    ax.axvline(x=80)
    plt.savefig(f"img/summary_responses_{plot_time}.png", dpi=150)
    plt.close(fig)
    if not debugging:  # otherwise it will spam the slack channel
        send_data_slack_channel(f"img/summary_responses_{plot_time}.png", image=True)

    # generate last vote plot
    df_last_vote = pd.DataFrame.from_dict(
        users_last_vote_time, orient="index", columns=["Days since last vote"]
    )
    fig, ax = plt.subplots(
        1, 1, constrained_layout=True, sharey=True, figsize=[8.06, 4.51]
    )
    sns.barplot(y=df_last_vote.index, x=df_last_vote["Days since last vote"], ax=ax)
    plt.savefig(f"img/last_vote_{plot_time}.png", dpi=150)
    plt.close(fig)
    if not debugging:  # otherwise it will spam the slack channel
        send_data_slack_channel(f"img/last_vote_{plot_time}.png", image=True)


# if the images are not needed for later, delete them
# os.remove('summary_responses.png')
