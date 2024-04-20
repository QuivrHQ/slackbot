import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from fastapi import FastAPI, Request
from loguru import logger
import requests
import sqlite3
from pydantic import BaseModel

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

    def make_quivr_api_request(self, method, endpoint, data=None):
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.config.quivr_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.quivr_api_base_url}{endpoint}"
        response = requests.request(method, url, headers=headers, json=data)
        return response.json()

    def update_home_tab(self, client, event, logger):
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

    def handle_app_mentions(self, body, say, logger, client):
        logger.info(body)

        client.reactions_add(
            channel=body["event"]["channel"],
            name="brain",
            timestamp=body["event"]["ts"],
        )

        brains_response = self.make_quivr_api_request("GET", "/brains/")
        brains = brains_response.get("brains", [])

        if not brains:
            say("No brains found. Please create a brain first.")
            return

        thread_ts = body["event"].get("thread_ts")
        chat_id = self.get_chat_id(thread_ts)
        if not chat_id:
            chat_data = {"name": "Slack Chat"}
            chat_response = self.make_quivr_api_request("POST", "/chat", data=chat_data)
            chat_id = chat_response["chat_id"]
            self.set_chat_id(body["event"]["ts"], chat_id)

        logger.info(body["event"]["text"])
        mention = f'<@{body["event"]["user"]}>'
        question = body["event"]["text"].replace(mention, "").strip()
        question_data = {"question": question}
        question_response = self.make_quivr_api_request(
            "POST", f"/chat/{chat_id}/question", data=question_data
        )

        client.reactions_add(
            channel=body["event"]["channel"],
            name="white_check_mark",
            timestamp=body["event"]["ts"],
        )

        logger.debug(question_response)
        if "assistant" in question_response:
            say(question_response["assistant"], thread_ts=body["event"]["ts"])
        else:
            say("Sorry, I couldn't find an answer.", thread_ts=body["event"]["ts"])


# FastAPI app setup
api = FastAPI()
config = Config()
slack_chat_app = SlackChatApp(config)
app_handler = SlackRequestHandler(slack_chat_app.app)


@api.post("/slack/events")
async def endpoint(req: Request):
    logger.info("Received request")
    return await app_handler.handle(req)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:api", host="0.0.0.0", port=1234, log_level="debug", reload=True)
