import asyncio
import logging
import uuid

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, BufferedInputFile, Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from .analytics import log_user_event
from .cards import create_prediction_card
from .config import (
    DEFAULT_BIAS_STRENGTH,
    DEFAULT_CANDIDATE_K,
    DEFAULT_SELECTION,
    DEFAULT_TEMPERATURE,
    SCHEDULE_EN_PATH,
    SCHEDULE_RU_PATH,
    TMP_DIR,
)
from .matcher import MatchSettings, SpaceObjectMatcher


class UserFlow(StatesGroup):
    """Finite-state flow for choosing a language and waiting for a user photo."""

    choosing_language = State()
    waiting_for_photo = State()


LANG_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Русский'), KeyboardButton(text='English')],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

LANG_BY_TEXT = {
    'русский': 'ru',
    'ru': 'ru',
    'russian': 'ru',
    'english': 'en',
    'en': 'en',
}

WELCOME_TEXT = '👇 Выбери язык / Choose language:'

INTRO_RU = (
    '✨ Это GalaxyMatchBot: научный космический оракул.\n\n'
    'Отправь своё фото, я сравню его с настоящими галактиками, туманностями, планетами и другими объектами космоса '
    'и верну карточку с объектом, который ближе всего по визуальному сходству.\n\n'
    'Пришли фото!'
)

INTRO_EN = (
    '✨ This is GalaxyMatchBot: a scientific cosmic oracle.\n\n'
    'Send me a photo and I will compare it with real galaxies, nebulae, planets, and other space objects, '
    'then return a card with the closest match.\n\n'
    'Send your photo!'
)

ABOUT_MODEL_RU = (
    '🔭 Как работает модель\n\n'
    'Бот использует модель clip-ViT-B-32 (CLIP от OpenAI). '
    'Она превращает твою фотографию и изображения реальных космических объектов в векторы, '
    'а затем выбирает ближайший по косинусному сходству.\n\n'
    'Калибровка (person-bias) нужна, чтобы дженерик-фото лиц не отображались всегда на одни и те же объекты. '
    'Это делает результаты разнообразнее.\n\n'
    '«Процент совпадения» это презентационная оценка (z-score + перцентильная смесь + детерминированный шум), '
    'а не научная вероятность.\n\n'
    'GitHub: https://github.com/kotikmatematik/galaxy-matching-veterok\n'
    'Автор: @elder_flower\n\n'
    'И да, можете предложить мне работу Data Scientist, если есть такая возможность 💼'
)

ABOUT_MODEL_EN = (
    '🔭 How the model works\n\n'
    'The bot uses the clip-ViT-B-32 model (CLIP by OpenAI). '
    'It turns your photo and images of real space objects into vectors, '
    'then picks the closest one by cosine similarity.\n\n'
    'Calibration (person-bias) prevents generic face photos from always mapping to the same objects, '
    'making results more varied.\n\n'
    'The "match %" is a fun presentation score (z-score + percentile blend + deterministic jitter), '
    'not a scientific probability.\n\n'
    'GitHub: https://github.com/kotikmatematik/galaxy-matching-veterok\n'
    'Author/Автор: @elder_flower\n\n'
    'And yes, feel free to offer me a Data Scientist role if you have one 💼'
)


def _read_schedule(lang: str) -> str:
    """Read the schedule file for the given language, with a graceful fallback."""
    path = SCHEDULE_EN_PATH if lang == 'en' else SCHEDULE_RU_PATH
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        if lang == 'en':
            return 'Schedule is not available yet. Check back soon!'
        return 'Расписание пока недоступно. Загляни позже!'


def build_router(matcher: SpaceObjectMatcher):
    """Create Telegram handlers bound to a preloaded space-object matcher."""
    router = Router()

    async def ask_language(message: Message, state: FSMContext):
        """Reset the user flow and ask for the output card language."""
        log_user_event(message, 'start')
        await state.set_state(UserFlow.choosing_language)
        await message.answer(WELCOME_TEXT, reply_markup=LANG_KEYBOARD)

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        """Start a new user flow by asking for the output card language."""
        await ask_language(message, state)

    @router.message(F.text.lower().in_({'start', 'старт'}))
    async def text_start(message: Message, state: FSMContext):
        """Start the flow when the user sends start as plain text."""
        await ask_language(message, state)

    @router.message(Command('schedule'))
    async def cmd_schedule(message: Message, state: FSMContext):
        """Reply with the current camp schedule in the user's chosen language."""
        data = await state.get_data()
        lang = data.get('lang', 'ru')
        log_user_event(message, 'schedule', language=lang)
        await message.answer(_read_schedule(lang))

    @router.message(Command('about_model'))
    async def cmd_about_model(message: Message, state: FSMContext):
        """Explain how the CLIP model works and credit the author."""
        data = await state.get_data()
        lang = data.get('lang', 'ru')
        log_user_event(message, 'about_model', language=lang)
        if lang == 'en':
            await message.answer(ABOUT_MODEL_EN)
        else:
            await message.answer(ABOUT_MODEL_RU)

    @router.message(UserFlow.choosing_language)
    async def choose_language(message: Message, state: FSMContext):
        """Store the selected language and ask the user to send a photo."""
        text = (message.text or '').strip().lower()
        lang = LANG_BY_TEXT.get(text)
        if lang is None:
            log_user_event(message, 'language_invalid', button=message.text)
            await message.answer('Нажми Русский или English.', reply_markup=LANG_KEYBOARD)
            return

        await state.update_data(lang=lang)
        log_user_event(message, 'language_selected', language=lang, button=message.text)
        await state.set_state(UserFlow.waiting_for_photo)
        if lang == 'en':
            await message.answer(INTRO_EN, reply_markup=ReplyKeyboardRemove())
        else:
            await message.answer(INTRO_RU, reply_markup=ReplyKeyboardRemove())

    @router.message(UserFlow.waiting_for_photo, F.photo)
    async def handle_photo(message: Message, state: FSMContext, bot: Bot):
        """Download a Telegram photo, generate a card, send it back, and clean up."""
        data = await state.get_data()
        lang = data.get('lang', 'ru')
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        photo_id = uuid.uuid4().hex
        input_path = TMP_DIR / f'{photo_id}.jpg'
        output_path = TMP_DIR / f'{photo_id}_card.jpg'

        try:
            await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            await bot.download_file(file.file_path, destination=input_path)

            settings = MatchSettings(
                candidate_k=DEFAULT_CANDIDATE_K,
                bias_strength=DEFAULT_BIAS_STRENGTH,
                selection=DEFAULT_SELECTION,
                temperature=DEFAULT_TEMPERATURE,
            )
            best, _, _ = await asyncio.to_thread(matcher.predict_space_object_raw, input_path, settings)
            log_user_event(
                message,
                'photo_matched',
                language=lang,
                matched_object_en=str(best.get('name_en', '')),
                matched_object_ru=str(best.get('name_ru', '')),
                match_percent=round(float(best.cosmic_match_percent), 1),
            )
            card_path = await asyncio.to_thread(create_prediction_card, input_path, best, lang, output_path)

            card_bytes = card_path.read_bytes()
            filename = 'space_card.jpg' if lang == 'en' else 'kosmicheskaya_kartochka.jpg'
            if lang == 'en':
                caption = (
                    '🖨 You can print this card at the Observatory camp on the mini-printer, '
                    'just ask any participant and they\'ll help you!\n\n'
                    'Just keep in mind that the printer uses thermal receipt paper, which is not quite LNT. If you print it, please take it with you and don\'t leave it in nature 🌿\n\n'
                    'By the way, there is so much more happening at the camp! Check out all the activities in /schedule, and if you\'re curious how the bot works: /about_model.'
                )
            else:
                caption = (
                    '🖨 Эту карточку можно распечатать в кемпе Обсерватория на мини-принтере, '
                    'подойди к любому участнику и они помогут!\n\n'
                    'Только имей в виду, что принтер печатает на чековой термобумаге, что не совсем LNT. Если распечатаешь, пожалуйста, забери с собой и не оставляй на природе 🌿\n\n'
                    'Кстати, у нас в кемпе ещё очень много интересного! Все активности смотри в /schedule, а если хочешь узнать как работает бот: /about_model.'
                )
            await message.answer_photo(BufferedInputFile(card_bytes, filename=filename), caption=caption)
        except Exception:
            logging.exception('Cannot process Telegram photo')
            if lang == 'en':
                await message.answer('Something went wrong. Please try another photo.')
            else:
                await message.answer('Что-то пошло не так. Попробуй отправить другое фото.')
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    @router.message(UserFlow.waiting_for_photo)
    async def ask_for_photo(message: Message, state: FSMContext):
        """Handle non-photo messages while the bot is waiting for an image."""
        data = await state.get_data()
        lang = data.get('lang', 'ru')
        log_user_event(message, 'non_photo_message', language=lang)
        if lang == 'en':
            await message.answer('Please send a photo, not text or a file.')
        else:
            await message.answer('Пришли именно фото, не текст и не файл.')

    @router.message()
    async def fallback_start(message: Message, state: FSMContext):
        """Start the flow for any first message that did not match other handlers."""
        await ask_language(message, state)

    return router


async def run_bot(token: str, matcher: SpaceObjectMatcher):
    """Start aiogram polling with the provided bot token and loaded matcher."""
    bot = Bot(token=token)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(matcher))
    await bot.set_my_commands([
        BotCommand(command='start', description='Начать / Start'),
        BotCommand(command='schedule', description='Расписание кемпа / Camp schedule'),
        BotCommand(command='about_model', description='Как работает модель / How the model works'),
    ])
    await dispatcher.start_polling(bot)
