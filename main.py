import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from fastapi import FastAPI, Request
from loguru import logger
import requests


# Load environment variables
load_dotenv()

# Initialize your app with your bot token and signing secret
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# Quivr API configuration
QUIVR_API_BASE_URL = "https://api.quivr.app"
QUIVR_API_KEY = os.environ.get("QUIVR_API_KEY")


# Helper function to make API requests to Quivr
def make_quivr_api_request(method, endpoint, data=None):
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {QUIVR_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{QUIVR_API_BASE_URL}{endpoint}"
    response = requests.request(method, url, headers=headers, json=data)
    return response.json()


# Slack Bolt event handlers
@app.event("app_home_opened")
def update_home_tab(client, event, logger):
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


@app.event("app_mention")
def handle_app_mentions(body, say, logger):
    logger.info(body)

    # Retrieve list of brains
    brains_response = make_quivr_api_request("GET", "/brains/")
    brains = brains_response.get("brains", [])

    if not brains:
        say("No brains found. Please create a brain first.")
        return

    # Use the first brain for now (you can add logic to select a specific brain)
    selected_brain = brains[0]
    brain_id = selected_brain["id"]

    # Create a new chat
    chat_data = {"name": "Slack Chat"}
    chat_response = make_quivr_api_request("POST", "/chat", data=chat_data)
    chat_id = chat_response["chat_id"]

    # Ask a question
    logger.info(body["event"]["text"])
    mention = f'<@{body["event"]["user"]}>'
    question = body["event"]["text"].replace(mention, "").strip()
    question_data = {"question": question, "brain_id": brain_id}
    question_response = make_quivr_api_request(
        "POST", f"/chat/{chat_id}/question", data=question_data
    )

    logger.debug(question_response)
    if "assistant" in question_response:
        say(question_response["assistant"], thread_ts=body["event"]["ts"])
    else:
        say("Sorry, I couldn't find an answer.", thread_ts=body["event"]["ts"])


# FastAPI app setup
api = FastAPI()
app_handler = SlackRequestHandler(app)


@api.post("/slack/events")
async def endpoint(req: Request):
    logger.info("Received request")
    logger.info(await req.body())

    return await app_handler.handle(req)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:api", host="0.0.0.0", port=1234, log_level="debug", reload=True)
