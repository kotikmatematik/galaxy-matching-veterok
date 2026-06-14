# AGENTS.md

## Repo Shape
- This is the backend of the Telegram bot **@GalaxyMatchBot**: it turns a portrait photo into a shareable space-object card using CLIP image embeddings.
- The product is now a small deployable Python service, not a notebook. Entry point is `app.py`; all runtime logic lives in `src/`.
- Original prototype notebooks (`curated_space_objects_dataset.ipynb`, `efficientnet_galaxy_zoo.ipynb`) are kept under `archive/` for reference only — do not treat them as the live pipeline.
- `requirements.txt`, `README.md`, and docs exist; for end-user and deploy instructions read `README.md`, `docs/DATA.md`, `docs/OPERATIONS.md`, and `deploy/README.md`.

## Code Layout
- `app.py` — loads `.env`, requires `TELEGRAM_BOT_TOKEN`, constructs `SpaceObjectMatcher` once (CLIP model + `.npy` stay in memory), then starts aiogram polling via `run_bot`.
- `src/config.py` — single source of paths and runtime defaults (`MODEL_NAME`, `DEFAULT_CANDIDATE_K`, `DEFAULT_SELECTION`, `DEFAULT_TEMPERATURE`, `DEFAULT_BIAS_STRENGTH`). Change tuning knobs here.
- `src/matcher.py` — `SpaceObjectMatcher`, `MatchSettings`, scoring/selection helpers. Core CLIP matching.
- `src/bot.py` — aiogram handlers and the `UserFlow` FSM (choose language → wait for photo → return card).
- `src/cards.py` — Pillow card rendering (`create_prediction_card`).
- `src/analytics.py` — appends one event row per interaction to a local CSV.
- `scripts/` — `check_runtime.py` (validates data files + `.env`), `check_fonts.py` (shows card fonts), `show_users.py` (summarizes event log).

## Data Sources
- Metadata source of truth: `data/curated_space_objects/space_objects_data.csv`.
- Required CSV columns (validated in `matcher._load_objects`): `name_en`, `name_ru`, `description_en`, `description_ru`, `object_type_en`, `object_type_ru`, `mood_en`, `mood_ru`, `image_path`.
- `matcher` derives base columns (`name`, `object_type`, `description`, `mood`) from the `_en` columns when absent; localized reads go through `localized_value` with English fallback. Do not reintroduce `description_en_updated` / `description_ru_updated`.
- `image_path` is resolved relative to the repo root and must exist locally under `data/curated_space_objects/images/`. Rows with a missing image get `has_image=False` and are dropped from `objects_with_images`, which shrinks matching coverage.
- Precomputed assets: `space_object_embeddings.npy` and `space_object_person_bias.npy`. **Row counts must line up** — embeddings length must equal `len(objects_with_images)`, and bias length must equal embeddings length, or load raises. Regenerate embeddings whenever the image set or its ordering changes.
- Editable camp schedule files (committed to the repo, re-read on every `/schedule` call — no restart needed): `schedule_ru.txt` and `schedule_en.txt` in `data/curated_space_objects/`.
- Generated/ignored at runtime: `cards/`, `tmp/`, and `bot_events.csv` (contains user data; git-ignored).

## Matching / Scoring Logic (`src/matcher.py`)
- Active model: `SentenceTransformer('clip-ViT-B-32')`. Query image is encoded with `normalize_embeddings=True`; similarity is cosine vs. `space_embeddings`.
- Pipeline in `predict_space_object_raw`: raw cosine scores → subtract centered person-bias penalty (`adjusted_scores_with_person_bias`, capped at `penalty_cap=0.1`) → subtract `OBJECT_SCORE_PENALTIES` → take top `candidate_k` → `add_fun_match_scores` → pick one via `selected_candidate_position`.
- `candidate_k` controls the candidate pool (there is no `top_k`). `candidate_count_for_selection` defaults to 30 for the `diverse_sample` modes and 5 otherwise.
- Selection modes: `best` (pure adjusted-score top-1, closest to raw CLIP ranking), `sample`/`deterministic_sample` (temperature softmax over scores), `diverse_sample`/`deterministic_diverse_sample` (rank-based, more variety, farther from score order). `deterministic_*` modes seed the RNG from image pixels (`deterministic_seed_from_image`) so the same photo always yields the same card.
- Product defaults (in `config.py`): `selection='deterministic_sample'`, `candidate_k=5`, `temperature=0.03`, `bias_strength=1.0`.
- `bias_strength` controls how strongly calibration suppresses objects that match generic face photos; keep it tunable when adjusting distribution.
- `OBJECT_SCORE_PENALTIES` (e.g. `Tycho's Supernova` / `Сверхновая Тихо` at 0.01) are small soft nudges, not bans — keep them small.
- `cosmic_match_percent` is a presentation score (z-score + percentile blend, clamped to 72–96, plus deterministic jitter), **not** a calibrated probability. Don't present it as scientific.

## Bot Flow (`src/bot.py`)
- aiogram v3, polling (no webhook/TLS/domain needed). FSM states: `choosing_language` → `waiting_for_photo`.
- `/start`, the texts `start`/`старт`, and any unmatched first message all enter the language prompt. Language buttons map via `LANG_BY_TEXT` to `ru`/`en`.
- `/schedule` and `/about_model` are registered before the state-bound handlers so they work in any FSM state. Each reads the user's chosen language from the FSM data (defaulting to `ru`) and does not alter state.
- On a photo: download to `tmp/<uuid>.jpg`, run `predict_space_object_raw` and `create_prediction_card` in `asyncio.to_thread` (they are CPU-bound/blocking), reply with the JPG, send a follow-up message inviting the user to print the card on the camp mini-printer (with a Leave-No-Trace note and a pointer to `/schedule` and `/about_model`), then always delete the temp input/output in `finally`.
- Every step logs an event (`start`, `language_selected`, `photo_matched`, `schedule`, `about_model`, `non_photo_message`, `language_invalid`) via `analytics.log_user_event`.

## Card Rendering (`src/cards.py`)
- `create_prediction_card` builds a 960px-wide gradient card: side-by-side rounded INPUT/MATCH previews, localized title/type/vibe/description, and the match percent; height is content-driven up to `CARD_MAX_HEIGHT`.
- Fonts resolve through `get_font`, honoring `CARD_FONT_REGULAR` / `CARD_FONT_BOLD` env overrides, then macOS, then Linux Liberation/DejaVu/Noto paths, then Pillow default. On Linux servers install `fonts-liberation2` / `fonts-dejavu-core` for clean typography; verify with `python scripts/check_fonts.py`.

## Configuration
- Copy `.env.example` to `.env`. Required: `TELEGRAM_BOT_TOKEN`. Optional: `CARD_FONT_REGULAR`, `CARD_FONT_BOLD`. Never commit `.env` (git-ignored).

## Verification
- No test runner or CI. Before changes are considered done, run:
```bash
python3 -m compileall app.py src scripts
python scripts/check_runtime.py
python scripts/check_fonts.py
```
- `check_runtime.py` validates the presence and consistency of the data files and `.env`; run it after any change to the CSV, images, or `.npy` assets.
- For end-to-end behavior, set a token and run `python app.py`, then exercise the bot in Telegram.
