# Quivr Slack Bot

This Slack bot allows users to ask questions to a Quivr brain directly from Slack.

## Prerequisites

- Python 3.x
- Slack bot token and signing secret
- Quivr API key

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/quivrHQ/slackbot.git
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   - Create a `.env` file in the project root.
   - Add the following variables to the `.env` file:
     ```
     SLACK_BOT_TOKEN=your-slack-bot-token
     SLACK_SIGNING_SECRET=your-slack-signing-secret
     QUIVR_API_KEY=your-quivr-api-key
     ```

## Usage

1. Start the bot:
   ```
   uvicorn main:api --reload --port 1234
   ```

2. Invite the bot to a Slack channel.

3. Mention the bot in a message to ask a question:
   ```
   @quivr-bot What is the capital of France?
   ```

   The bot will retrieve the answer from the Quivr brain and respond in the Slack channel.

## Customization

- You can modify the `handle_app_mentions` function in `main.py` to customize the bot's behavior.
- Adjust the Quivr API endpoints and request parameters as needed.

## License

This project is licensed under the MIT License.