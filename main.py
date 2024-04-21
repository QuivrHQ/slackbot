import os
import re
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from fastapi import FastAPI, Request
from loguru import logger
import requests
import sqlite3
from pydantic import BaseModel
from fastapi import Depends
from slack_bolt.context.ack import Ack
from slack_bolt.request import BoltRequest
from slack_bolt.response import BoltResponse
import urllib.parse
import json

# Load environment variables
load_dotenv()

# Quivr API configuration
QUIVR_API_BASE_URL = "https://api.quivr.app"
QUIVR_API_KEY = os.environ.get("QUIVR_API_KEY")

# Database configuration
DB_NAME = "slack_chat.db"


class Config(BaseModel):
    slack_bot_token: str = os.environ.get("SLACK_BOT_TOKEN")
    slack_signing_secret: str = os.environ.get("SLACK_SIGNING_SECRET")
    quivr_api_base_url: str = QUIVR_API_BASE_URL
    quivr_api_key: str = QUIVR_API_KEY
    db_name: str = DB_NAME


class SlackChatApp:
    def __init__(self, config: Config):
        self.config = config
        self.app = App(
            token=config.slack_bot_token, signing_secret=config.slack_signing_secret
        )
        self.init_db()
        self.register_event_handlers()

    def init_db(self):
        conn = sqlite3.connect(self.config.db_name)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_chat_mapping (
                thread_ts TEXT PRIMARY KEY,
                chat_id TEXT
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_brain_mapping (
                thread_ts TEXT PRIMARY KEY,
                brain_id TEXT
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_question_mapping (
                thread_ts TEXT PRIMARY KEY,
                question TEXT
            )
        """
        )
        conn.commit()
        conn.close()

    def get_question(self, thread_ts):
        conn = sqlite3.connect(self.config.db_name)
        c = conn.cursor()
        c.execute(
            "SELECT question FROM thread_question_mapping WHERE thread_ts = ?",
            (thread_ts,),
        )
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def set_question(self, thread_ts, question):
        conn = sqlite3.connect(self.config.db_name)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO thread_question_mapping VALUES (?, ?)",
            (thread_ts, question),
        )
        conn.commit()
        conn.close()

    def register_event_handlers(self):
        self.app.event("app_home_opened")(self.update_home_tab)
        self.app.event("app_mention")(self.handle_app_mentions)

    def get_chat_id(self, thread_ts):
        conn = sqlite3.connect(self.config.db_name)
        c = conn.cursor()
        c.execute(
            "SELECT chat_id FROM thread_chat_mapping WHERE thread_ts = ?", (thread_ts,)
        )
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def set_chat_id(self, thread_ts, chat_id):
        conn = sqlite3.connect(self.config.db_name)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO thread_chat_mapping VALUES (?, ?)",
            (thread_ts, chat_id),
        )
        conn.commit()
        conn.close()

    def get_brain_id(self, thread_ts):
        conn = sqlite3.connect(self.config.db_name)
        c = conn.cursor()
        c.execute(
            "SELECT brain_id FROM thread_brain_mapping WHERE thread_ts = ?",
            (thread_ts,),
        )
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def set_brain_id(self, thread_ts, brain_id):
        conn = sqlite3.connect(self.config.db_name)
        logger.info(f"Setting brain ID: {brain_id} for thread: {thread_ts}")
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO thread_brain_mapping VALUES (?, ?)",
            (thread_ts, brain_id),
        )
        conn.commit()
        conn.close()

    def make_quivr_api_request(self, method, endpoint, data=None, params=None):
        logger.info(f"Making Quivr API request: {method} {endpoint}")
        logger.info(f"Data: {data}")
        logger.info(f"Params: {params}")
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.config.quivr_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.quivr_api_base_url}{endpoint}"
        response = requests.request(
            method, url, headers=headers, json=data, params=params
        )
        return response.json()

    def update_home_tab(self, client, event):
        try:
            client.views_publish(
                user_id=event["user"],
                view={
                    "type": "home",
                    "callback_id": "home_view",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*Welcome to your _App's Home tab_* :tada:",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "This button won't do much for now but you can set up a listener for it using the `actions()` method and passing its unique `action_id`. See an example in the `examples` folder within your Bolt app.",
                            },
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Click me!"},
                                }
                            ],
                        },
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error publishing home tab: {e}")

    def handle_app_mentions(self, body, say, client):
        print("Coming here")
        self.app.client.reactions_add(
            channel=body["event"]["channel"],
            name="brain",
            timestamp=body["event"]["ts"],
        )
        logger.info(f"Hanlding app mention")
        logger.info(f"Question is {body['event']['text']}")
        logger.info(f"Thread is {body['event']['ts']}")
        self.set_question(body["event"]["ts"], body["event"]["text"])

        # Check if brain is already set for this thread
        # Check if thread_ts is in the event payload, if not, use the ts from the event
        thread_ts = body["event"].get("thread_ts", body["event"]["ts"])
        brain_id = self.get_brain_id(thread_ts)
        logger.info(f"Brain ID: {brain_id}")

        if not brain_id:

            brains_response = self.make_quivr_api_request("GET", "/brains/")
            brains = brains_response.get("brains", [])
            # limit to 24 brains
            brains = brains[:24]

            if not brains:
                say("No brains found. Please create a brain first.")
                return

            # Create a button for each brain and an 'Any brain' button
            brain_buttons = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": brain["name"]},
                    "action_id": f"brain_{brain['id']}",
                }
                for brain in brains
            ]
            ## Action ID should be a null UUID with only zeros
            any_brain = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Any brain"},
                    "action_id": "00000000-0000-0000-0000-000000000000",
                }
            ]

            # Send a message with the buttons
            client.chat_postMessage(
                channel=body["event"]["channel"],
                text="Please select a brain:",
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "Available brains:"},
                    },
                    {
                        "type": "actions",
                        "elements": brain_buttons,
                    },
                ],
                thread_ts=body["event"]["ts"],
            )

            client.chat_postMessage(
                channel=body["event"]["channel"],
                text="Or select any brain:",
                blocks=[
                    {
                        "type": "actions",
                        "elements": any_brain,
                    },
                ],
                thread_ts=body["event"]["ts"],
            )

        else:
            self.ask_question(
                body, brain_id, body["event"]["ts"], question=body["event"]["text"]
            )
        self.app.client.reactions_remove(
            channel=body["event"]["channel"],
            name="brain",
            timestamp=body["event"]["ts"],
        )
        self.app.client.reactions_add(
            channel=body["event"]["channel"],
            name="white_check_mark",
            timestamp=body["event"]["ts"],
        )

    def ask_question(self, body, brain_id, thread_ts, question=None):
        logger.info(body)

        # Extract the question from the body
        text = body["event"]["text"]
        bot_id = f"<@{self.app.client.auth_test()['user_id']}>"
        question = text.replace(bot_id, "").strip()

        chat_id = self.get_chat_id(thread_ts)
        if not chat_id:
            chat_data = {"name": "Slack Chat"}
            chat_response = self.make_quivr_api_request("POST", "/chat", data=chat_data)
            chat_id = chat_response["chat_id"]
            self.set_chat_id(thread_ts, chat_id)

        logger.debug(question)
        # If question is not provided, get it from the database
        params = {}
        if brain_id == "00000000-0000-0000-0000-000000000000":
            brain_id = None
        params = {"brain_id": brain_id}
        question_data = {
            "question": question,
        }
        question_response = self.make_quivr_api_request(
            "POST", f"/chat/{chat_id}/question", data=question_data, params=params
        )

        logger.debug(question_response)
        if "assistant" in question_response:
            self.app.client.chat_postMessage(
                channel=body["event"]["channel"],
                text=question_response["assistant"],
                thread_ts=thread_ts,
            )
        else:
            self.app.client.chat_postMessage(
                channel=body["event"]["channel"],
                text="Sorry, I couldn't find an answer.",
                thread_ts=thread_ts,
            )


# FastAPI app setup
api = FastAPI()
config = Config()
slack_chat_app = SlackChatApp(config)
app_handler = SlackRequestHandler(slack_chat_app.app)


@api.post("/slack/events")
async def endpoint(req: Request):
    logger.info("Received request")
    return await app_handler.handle(req)


@api.post("/slack/interactive")
async def interactive(req: Request, ack: Ack = Depends(Ack)):
    logger.info("Received interactive request")
    ## URL decoding
    body = await req.body()
    body_decoded = urllib.parse.unquote(body.decode("utf-8"))
    payload = json.loads(body_decoded.split("payload=")[1])

    ack()  # Acknowledge the request

    brain_id = None
    action_id = payload["actions"][0]["action_id"]
    if action_id.startswith("brain_"):
        brain_id = action_id.split("_")[1]

    thread_ts = payload["container"]["thread_ts"]
    logger.info(f"Thread TS: {thread_ts}")
    logger.info(f"Interactive Brain ID: {brain_id}")
    slack_chat_app.set_brain_id(thread_ts, brain_id)

    chat_id = slack_chat_app.get_chat_id(thread_ts)
    if not chat_id:
        logger.info("Creating chat")
        chat_data = {"name": "Slack Chat"}
        chat_response = slack_chat_app.make_quivr_api_request(
            "POST", "/chat", data=chat_data
        )
        chat_id = chat_response["chat_id"]
        slack_chat_app.set_chat_id(thread_ts, chat_id)

    question = slack_chat_app.get_question(thread_ts)
    params = {}
    if brain_id == "00000000-0000-0000-0000-000000000000":
        brain_id = None
    params = {"brain_id": brain_id}
    question_data = {
        "question": question,
    }
    question_response = slack_chat_app.make_quivr_api_request(
        "POST", f"/chat/{chat_id}/question", data=question_data, params=params
    )

    logger.debug(question_response["assistant"])
    logger.debug(f"Brain ID: {question_response.get('brain_id')}")
    if "assistant" in question_response:
        slack_chat_app.app.client.chat_postMessage(
            channel=payload["channel"]["id"],
            text=question_response["assistant"],
            thread_ts=thread_ts,
        )
    else:
        slack_chat_app.app.client.chat_postMessage(
            channel=payload["channel"]["id"],
            text="Sorry, I couldn't find an answer.",
            thread_ts=thread_ts,
        )

    return BoltResponse(status=200)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:api", host="0.0.0.0", port=1234, log_level="info", reload=True)
