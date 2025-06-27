import gspread
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    ConversationHandler, CallbackContext
)
from oauth2client.service_account import ServiceAccountCredentials
import re

# Настройки Google Sheets
SHEET_NAME = "Название вашей таблицы"  # Замените на своё
SERVICE_ACCOUNT_FILE = "service_account.json"  # Путь к JSON-ключу

# Состояния диалога
GET_NICKNAME, GET_POINTS, GET_SQUAD_POWER, MODERATOR_SET_SHEET = range(4)

# Глобальные переменные
current_sheet_name = "Лист1"  # Лист по умолчанию
MODERATOR_CHAT_ID = 123456789  # Замените на ваш Telegram ID


# Авторизация в Google Sheets
def get_google_client():
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    return gspread.authorize(creds)


def get_google_sheet(sheet_name=None):
    client = get_google_client()
    spreadsheet = client.open(SHEET_NAME)

    if sheet_name:
        try:
            return spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Если лист не найден, копируем последний лист
            worksheets = spreadsheet.worksheets()
            if worksheets:
                last_sheet = worksheets[-1]
                new_sheet = last_sheet.duplicate(new_sheet_name=sheet_name)
                return new_sheet
            else:
                # Если нет ни одного листа, создаем новый
                return spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
    return spreadsheet.sheet1


# Поиск ника в столбце A (без учёта регистра)
def find_nickname_row(sheet, nickname):
    nicknames = sheet.col_values(1)  # Все ники из столбца A
    for idx, nick in enumerate(nicknames, start=1):
        if nick.lower() == nickname.lower():
            return idx  # Возвращает номер строки
    return None


# Команда /start
def start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "Введи свой ник (регистр не важен):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return GET_NICKNAME


# Обработка ника
def get_nickname(update: Update, context: CallbackContext) -> int:
    nickname = update.message.text.strip()
    sheet = get_google_sheet(current_sheet_name)

    if not nickname:
        update.message.reply_text("Ник не может быть пустым. Попробуй ещё раз:")
        return GET_NICKNAME

    row = find_nickname_row(sheet, nickname)
    if row:
        context.user_data["row"] = row
        update.message.reply_text("Ник найден! Теперь введи количество очков:")
    else:
        # Добавляем ник в первую свободную строку
        next_row = len(sheet.col_values(1)) + 1
        sheet.update_cell(next_row, 1, nickname)  # Столбец A
        context.user_data["row"] = next_row
        update.message.reply_text("Ник добавлен! Теперь введи количество очков:")

    return GET_POINTS


# Обработка очков
def get_points(update: Update, context: CallbackContext) -> int:
    points_text = update.message.text.strip()
    if not re.match(r"^\d+$", points_text):
        update.message.reply_text("Нужно ввести число! Попробуй ещё раз:")
        return GET_POINTS

    points = int(points_text)
    row = context.user_data["row"]
    sheet = get_google_sheet(current_sheet_name)

    sheet.update_cell(row, 2, points)  # Столбец B
    update.message.reply_text("Теперь введи мощь отряда:")
    return GET_SQUAD_POWER


# Обработка мощи отряда
def get_squad_power(update: Update, context: CallbackContext) -> int:
    power_text = update.message.text.strip()
    if not re.match(r"^\d+$", power_text):
        update.message.reply_text("Нужно ввести число! Попробуй ещё раз:")
        return GET_SQUAD_POWER

    power = int(power_text)
    row = context.user_data["row"]
    sheet = get_google_sheet(current_sheet_name)

    sheet.update_cell(row, 5, power)  # Столбец E
    update.message.reply_text("✅ Данные сохранены!")
    return ConversationHandler.END


# Команда для модератора (/set_sheet)
def set_sheet(update: Update, context: CallbackContext) -> int:
    if update.message.from_user.id != MODERATOR_CHAT_ID:
        update.message.reply_text("❌ Эта команда только для модераторов!")
        return ConversationHandler.END

    update.message.reply_text("Введи название листа (например, 'Лист2'):")
    return MODERATOR_SET_SHEET


# Обработка выбора листа модератором
def moderator_set_sheet(update: Update, context: CallbackContext) -> int:
    global current_sheet_name
    sheet_name = update.message.text.strip()

    try:
        # Попытка получить лист (если его нет - он создастся автоматически)
        sheet = get_google_sheet(sheet_name)
        current_sheet_name = sheet_name
        update.message.reply_text(f"✅ Теперь данные будут сохраняться в лист '{sheet_name}'!")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}. Попробуй ещё раз:")
        return MODERATOR_SET_SHEET

    return ConversationHandler.END


# Отмена
def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def main():
    # Замените 'YOUR_BOT_TOKEN' на токен вашего бота
    updater = Updater("YOUR_BOT_TOKEN", use_context=True)
    dp = updater.dispatcher

    # Обработчик для обычных пользователей
    user_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_NICKNAME: [MessageHandler(Filters.text & ~Filters.command, get_nickname)],
            GET_POINTS: [MessageHandler(Filters.text & ~Filters.command, get_points)],
            GET_SQUAD_POWER: [MessageHandler(Filters.text & ~Filters.command, get_squad_power)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик для модератора
    moderator_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("set_sheet", set_sheet)],
        states={
            MODERATOR_SET_SHEET: [MessageHandler(Filters.text & ~Filters.command, moderator_set_sheet)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(user_conv_handler)
    dp.add_handler(moderator_conv_handler)
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()