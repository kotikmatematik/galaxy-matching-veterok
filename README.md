# galaxy-matching-veterok

`galaxy-matching-veterok` is the project behind @GalaxyMatchBot, a Telegram bot that turns a portrait photo into a shareable space-object card. It compares the input image with a curated set of real galaxies, nebulae, planets, and other objects using CLIP image embeddings, then renders a bilingual result card.

The project started as a notebook prototype and is now organized as a small deployable Python service.

## What It Does

- Asks the user to choose Russian or English for the output card.
- Accepts a Telegram photo and stores it temporarily.
- Loads `clip-ViT-B-32` once at startup with `sentence-transformers`.
- Matches the photo against precomputed space-object embeddings.
- Applies the existing calibration and presentation scoring logic.
- Generates a JPG card with the user photo, matched object image, text, and match score.
- Sends the card back to the user and deletes temporary files.
- Writes a local CSV event log for basic user/activity analytics.

## Demo Flow

1. User sends `/start`.
2. Bot shows a short intro and language buttons.
3. User selects `Русский` or `English`.
4. User sends a portrait photo.
5. Bot returns a generated JPG card, followed by an invite to print it on the camp mini-printer (with a Leave-No-Trace note) and pointers to `/schedule` and `/about_model`.

## Commands

- `/start` — Begin the flow and choose a language.
- `/schedule` — Show the camp programme in the user's chosen language (content lives in editable `.txt` files, updated without a restart).
- `/about_model` — Brief explanation of how the CLIP model works, GitHub link, and author credit (@elder_flower).

## Project Structure

```text
.
├── app.py                         # Service entrypoint
├── requirements.txt               # Python dependencies
├── src/
│   ├── bot.py                     # Telegram handlers and user flow
│   ├── cards.py                   # Card rendering
│   ├── config.py                  # Paths and runtime defaults
│   └── matcher.py                 # CLIP matching and scoring
├── scripts/
│   ├── check_fonts.py             # Shows which card fonts are used
│   ├── check_runtime.py           # Validates data files and .env
│   └── show_users.py              # Summarizes local bot event logs
├── data/curated_space_objects/
│   ├── space_objects_data.csv
│   ├── space_object_embeddings.npy
│   ├── space_object_person_bias.npy
│   └── images/
├── deploy/
│   ├── README.md
│   └── spacebot.service.example
├── docs/
│   ├── DATA.md
│   └── OPERATIONS.md
└── archive/                       # Original notebooks kept for reference
```

## Requirements

- Python 3.10 or newer.
- A Telegram bot token from BotFather.
- Internet access on first model download.
- Linux font packages such as `fonts-liberation2` or `fonts-dejavu-core` for clean server-side card typography.

## Configuration

Create `.env` from the example file:

```bash
cp .env.example .env
```

Required value:

```bash
TELEGRAM_BOT_TOKEN=your_token_from_botfather
```

Optional font overrides for Linux servers:

```bash
CARD_FONT_REGULAR=/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf
CARD_FONT_BOLD=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf
```

Do not commit `.env`; it contains secrets and is ignored by git.

## Local Setup

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Validate runtime files:

```bash
python scripts/check_runtime.py
python scripts/check_fonts.py
```

Run the bot:

```bash
python app.py
```

## Entrypoint

`app.py` is intentionally small. It loads `.env`, reads `TELEGRAM_BOT_TOKEN`, initializes `SpaceObjectMatcher` once so the CLIP model and `.npy` files stay in memory, and starts Telegram polling through `src/bot.py`.

## Deployment Summary

Copy the project to a server without local virtualenv/cache files:

```bash
rsync -av \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.DS_Store' \
  --exclude 'tmp' \
  ./ user@IP:/home/user/galaxy-matching-veterok/
```

Install server packages and dependencies:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip fonts-liberation2 fonts-dejavu-core
python3 -m venv .venv
source .venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch
pip install -r requirements.txt
```

The explicit CPU-only `torch` install prevents pip from downloading large CUDA packages on a regular CPU server.

For full server instructions, see `deploy/README.md`. For day-to-day commands, see `docs/OPERATIONS.md`.

## Operations

Check service logs:

```bash
journalctl -u spacebot -f
```

Restart after deploying code changes:

```bash
sudo systemctl restart spacebot
```

Check which fonts are used on the server:

```bash
python scripts/check_fonts.py
```

## User Analytics

The bot writes basic event logs to:

```text
data/curated_space_objects/bot_events.csv
```

The file includes Telegram user IDs, usernames, names, selected language, event type, timestamp, and match metadata. It is ignored by git because it contains user data.

Show a compact user summary:

```bash
python scripts/show_users.py
```

Inspect recent raw events on the server:

```bash
tail -n 20 data/curated_space_objects/bot_events.csv
```

## Development Checks

Run these before deploying changes:

```bash
python3 -m compileall app.py src scripts
python scripts/check_runtime.py
python scripts/check_fonts.py
```

## Notes

- The generated match percentage is a presentation score, not a calibrated scientific probability.
- The bot uses polling, so no domain, TLS certificate, or webhook setup is required.
- Generated cards are written to `data/curated_space_objects/cards/` and ignored by git.
- Temporary Telegram photos are written to `tmp/` and ignored by git.
- User analytics are written to `data/curated_space_objects/bot_events.csv` and ignored by git.

## More Documentation

- `docs/DATA.md` - required runtime data files and CSV columns.
- `docs/OPERATIONS.md` - server maintenance, deploy, and health-check commands.
- `archive/README.md` - notes about the original notebooks.
