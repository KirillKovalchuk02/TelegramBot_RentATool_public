import logging
import traceback
import bisect
import pandas as pd
import numpy as np
from tabulate import tabulate

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler, JobQueue, ConversationHandler

from google_sheet_connection import get_table_gsh, SCOPES, SERVICE_ACCOUNT_FILE, SAMPLE_RANGE, SAMPLE_SPREADSHEET_ID

from config import AGENT_PHONE_NUMBER, TOKEN, BOT_NAME, PAYMENT_PROVIDER_TOKEN, AVITO_LINK, PICK_UP_ADDRESS



logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO) # a logging code to make the logs appear when I run the code

logging.getLogger('httpx').setLevel(logging.WARNING) #only show logs that are WARNINGS and more important for httpx logger
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.WARNING)


INFO, TOOLS_SELECTION, CHOICE_PRICE_OR_DETAILS, SHOW_PRICES_OR_DETAILS, PRICES, ORDERING, CONCLUDE_ORDER, DELIVERY_QUESTION, DELIVERY_CHOICE, DELIVERY_DETAILS, CONFIRM_ORDER, PICK_UP_CONFIRM, PAYMENT = range(13)

"""
FUNCTION DEFINITIONS
"""


async def start_payment(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Sends an invoice without requiring shipping details."""
    chat_id = update.message.chat_id
    title = "Payment Example"
    description = "Example of a payment process using the python-telegram-bot library."

    # Unique payload to identify this payment request as being from your bot
    payload = "Custom-Payload"
    currency = "RUB"
    price = 1
    prices = [LabeledPrice("Test", price * 100)]

    await context.bot.send_invoice(
        chat_id,
        title,
        description,
        payload,
        currency,
        prices,
        provider_token=PAYMENT_PROVIDER_TOKEN,
    )



"""
SUPPORT FUNCTIONS
"""
async def refresh_gsh(context: ContextTypes.DEFAULT_TYPE):
    df = get_table_gsh(SCOPES, SERVICE_ACCOUNT_FILE, SAMPLE_RANGE, SAMPLE_SPREADSHEET_ID)
    clean_df = preclean_full_df(df)
    context.bot_data["full_tools_df"] = clean_df


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'{update.message} caused {context.error}')
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)


def get_tool_info(df, tool):
    df_for_tool = df.query(f'Инструмент == "{tool}"')
    unique_models = df_for_tool[['Бренд', 'Модель']].drop_duplicates()
    full_models_list = []
    for row in unique_models.iterrows():
        brand = row[1]['Бренд']
        model = row[1]['Модель']
        try:
            full_model = brand + ' ' + model
            if model == '-' or model == '':
                print(f'SEEMS LIKE {tool, brand} IS NOT PROPERLY DEFINED IN THE SHEET')
                pass
            else:
                full_models_list.append(full_model)
        except Exception as e:
            print(f'BRAND + MODEL CONCATENTATION GOES WRONG! Exception: {e}')
            pass
    
    return full_models_list


def get_list_of_tools_from_df(full_df):
    unique_tools = full_df['Инструмент'].unique()
    #dict mapping numbers to tools
    tool_dict = {i+1: tool for i, tool in enumerate(unique_tools)}

    text = '\n'.join(f"{i}. {tool}" for i, tool in tool_dict.items())

    return text, tool_dict


def preclean_full_df(df) -> pd.DataFrame: #function that removes the rows with no prices right away and adds the unique key Brand + Model

    price_cols = [col for col in df.columns if 'Стоимость ' in col]
    df = df.replace('', np.nan)
    clean_df = df.dropna(subset=price_cols)
    clean_df = clean_df.reset_index(drop=True)
    clean_df['model_index'] = clean_df['Бренд'] + ' ' + clean_df['Модель']

    return clean_df


async def prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chosen_model = context.user_data['chosen_model']
    full_df = context.bot_data['full_tools_df']

    specific_model_rows = full_df.query(f'model_index == "{chosen_model}"').drop_duplicates(subset=['Бренд', 'Модель'])   #THIS CAN POTENTIALLY CAUSE ISSUES IF THERE ARE MORE THAN 1 ROW WITH A SPECIFIC MODEL_INDEX IN OUR DF, WATCH OUT

    price_cols = [col for col in full_df.columns if 'Стоимость' in col]
    price_df = specific_model_rows[price_cols]
    price_df.columns = [col.replace('Стоимость ', '') for col in price_df.columns]
    price_t = price_df.T

    if price_t.empty:
        return 'NO_PRICES_FOUND'
    
    context.user_data['prices_for_chosen_tool'] = price_t

    headers = ["Срок", "Стоимость"]
    table_str = tabulate(price_t, headers, tablefmt="outline")

    message_header = f'Прайс-лист для инструмента {chosen_model}:\n\n'
    message_body = f"<pre>{table_str}</pre>\n\nПожалуйста, укажите желаемый срок аренды (в днях)"
    message_to_show = message_header + message_body

    return message_to_show




async def tool_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = context.bot_data['full_tools_df']
    chosen_model = context.user_data['chosen_model']
    specific_model_rows = df.query(f'model_index == "{chosen_model}"')

    picture_url =  specific_model_rows['picture_url'].unique()[0]
    text = specific_model_rows['detail_power'].unique()[0]

    return picture_url, text








"""
CONVERSATION HANDLER SUBHANDLERS
"""
async def conversation_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [
            InlineKeyboardButton(text="Посмотреть доступные виды инструмента", callback_data='tools_show')
        ],
        [
            InlineKeyboardButton(text="Оставить отзыв", callback_data='leave_review'),
            InlineKeyboardButton(text="Позвонить агенту", callback_data='agent_call')
        ]
    ]

    keyboard = InlineKeyboardMarkup(buttons)

    print('starting the conversation with conversation_start handler')
    await update.message.reply_text(text='Здравствуйте, я бот Rent A Tool, пожалуйста, выберите действие.', reply_markup=keyboard)

    return INFO



async def tool_types_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback_data = update.callback_query.data
    print(f'callback_data in TOOL_TYPE func is: {callback_data}')

    if callback_data == 'tools_show':
        full_df = context.bot_data['full_tools_df'] 
        text, tool_dict = get_list_of_tools_from_df(full_df)
        context.bot_data['tool_dict_current'] = tool_dict

        text_to_show = f'В настоящий момент доступны следующие виды инструмента: \n\n{text} \n\nПожалуйста укажите номер интересующего вас инструмента, чтобы увидеть доступные модели и прайс-лист'

        context.bot_data['list_of_tools_text'] = text_to_show
        context.user_data['tools_shown_flag'] = True
        
        await update.callback_query.edit_message_text(text_to_show)
        print('Returning TOOLS_SELECTION state')
        return TOOLS_SELECTION

    elif callback_data == 'agent_call':
        text_to_show = f'Вы можете позвонить нашему агенту по телефону:\n{AGENT_PHONE_NUMBER}'
        await update.callback_query.edit_message_text(text_to_show)
    
    elif callback_data == 'leave_review':
        text_to_show = f'Вот ссылка на <a href="{AVITO_LINK}">Avito</a>\nЗаранее спасибо за отзыв!'
        await update.callback_query.edit_message_text(text=text_to_show, parse_mode='HTML', disable_web_page_preview=True)

    else:
        await update.callback_query.edit_message_text(text='SOMETHING WENT WRONG')
    
    print('ending the conversation')
    return ConversationHandler.END #so here we return end for all options except the tools_show
    


async def tool_models_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if context.user_data.get('tools_shown_flag'):

        full_df = context.bot_data["full_tools_df"]
        tool_num = update.message.text

        tool = context.bot_data['tool_dict_current'][int(tool_num)]

        context.user_data['chosen_tool'] = tool

        models_list = get_tool_info(full_df, tool)

        if len(models_list) > 0:
            formated_models = '\n'.join(models_list)
            text_to_show = f'Доступные модели для инструмента {tool}:\n{formated_models}\n'
        
        else:
            await update.message.reply_text(f'Приносим свои извинения, список моделей для инструмента {tool} неполон. Для заказа этого инструмента, пожалуйста, проконсультируйтесь с нашим агентом:\n{AGENT_PHONE_NUMBER}\n' + 
                                            'Или укажите номер другого инструмента')
            return TOOLS_SELECTION

        buttons = []
        for model in models_list:
            model_button = [InlineKeyboardButton(text=model, callback_data=model + '__CALLBACK')]
            buttons.append(model_button)

        dynamic_keyboard = InlineKeyboardMarkup(buttons)


        await update.message.reply_text(text = text_to_show, reply_markup=dynamic_keyboard)

        print('Returning PRICES state')
        return CHOICE_PRICE_OR_DETAILS
    
    else:
        text_to_show = f'Ваше сообщение невозможно распознать, сори! Попробуйте начать с команды /start'
        await update.message.reply_text(text = text_to_show)
        return ConversationHandler.END



async def choice_prices_or_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback_data = update.callback_query.data
    print(f'callback_data in CHOICE_PRICES_OR_DETAILS func is: {callback_data}')

    chosen_model = callback_data.replace('__CALLBACK', '')

    context.user_data['chosen_model'] = chosen_model

    text = f'Пожалуйста, выберите действие для инструмента {chosen_model}'

    buttons = [
        [
            InlineKeyboardButton(text="Показать прайс лист (к оформлению заказа)", callback_data='show_chosen_tool_price_list'),
        ],
        [
            InlineKeyboardButton(text="Подробнее про инструмент", callback_data='show_tool_details')
        ]
    ]

    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    return SHOW_PRICES_OR_DETAILS



async def show_prices_or_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback_data = update.callback_query.data
    print(f'callback_data in SHOW_PRICES_OR_DETAILS func is: {callback_data}')

    if callback_data == 'show_chosen_tool_price_list':
        tool_prices_msg = await prices(update, context)
        if tool_prices_msg == 'NO_PRICES_FOUND':
            message = 'Просим прощения, но по данному инструменту в настоящее время не найдено доступных экземпляров'
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text=message)
            return TOOLS_SELECTION
        else:
            message = tool_prices_msg
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text=message, parse_mode='HTML')
            return DELIVERY_QUESTION
        
    elif callback_data == 'show_tool_details':
        tool_picture_url, tool_details_text = await tool_details(update, context)
        print(tool_picture_url)
        
        buttons = [
        [
            InlineKeyboardButton(text="Показать прайс лист (к оформлению заказа)", callback_data='show_chosen_tool_price_list'),
        ]
        ]

        keyboard = InlineKeyboardMarkup(buttons)

        if (tool_picture_url) is None or (tool_picture_url == '-'):
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Просим прощения, по инструменту {context.user_data['chosen_tool']} нет спецификаций. Мы работаем над устранением неполадки! Попробуйте указать номер другого инструмента')
            text = context.bot_data['list_of_tools_text']
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
            return TOOLS_SELECTION
        
        else:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=tool_picture_url, caption=tool_details_text, reply_markup=keyboard)
            return SHOW_PRICES_OR_DETAILS
    



async def delivery_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number_of_days = int(update.message.text)
    context.user_data['days_to_rent_tool'] = number_of_days

    buttons = [
        [
            InlineKeyboardButton(text="Доставка по Санкт-Петербургу", callback_data='delivery'),
            InlineKeyboardButton(text="Самовывоз", callback_data='pick_up_tool')
        ]
    ]

    keyboard = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(text='Выберите способ получения:', reply_markup=keyboard)

    print('Returning DELIVERY_CHOICE state')
    return DELIVERY_CHOICE



async def delivery_pickup_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback_data = update.callback_query.data

    if callback_data == 'delivery':
        await update.callback_query.edit_message_text(text=f'Пожалуйста, укажите адрес доставки в формате:\n\nУлица\nНомер дома\nНомер квартиры\n\nКаждый новый элемент с новой строки')
        print('Returning DELIVERY_DETAILS state')
        return DELIVERY_DETAILS
    


    elif callback_data == 'pick_up_tool':
        buttons = [
        [
            InlineKeyboardButton(text="Мне удобно забрать инструмент по этому адресу", callback_data='confirm_pick_up'),
        ],
        [
            InlineKeyboardButton(text="Мне все таки удобнее доставка", callback_data='delivery_change_mind')
        ]
        ]

        keyboard = InlineKeyboardMarkup(buttons)
        text = f'Адрес для самовывоза:\n{PICK_UP_ADDRESS}\nЧасы работы: \nТелефон пункта: {AGENT_PHONE_NUMBER}'

        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
        return PICK_UP_CONFIRM
    



async def pickup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback_data = update.callback_query.data
    if callback_data == 'confirm_pick_up':
        context.user_data['delivery_address'] = 'pick_up'
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text = 'Самовывоз заказа подтвержден')
        await confirm_order(update, context)
        return CONCLUDE_ORDER
    
    elif callback_data == 'delivery_change_mind':
        text=f'Пожалуйста, укажите адрес доставки в формате:\n\nУлица\nНомер дома\nНомер квартиры\n\nКаждый новый элемент с новой строки'
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text = text)
        return DELIVERY_DETAILS




async def delivery_details_ingestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address_raw = update.message.text
    address_list = address_raw.split('\n')

    #TODO: INSERT STRING CLEANING AND VALIDATION

    print(address_list)

    try:
        full_address_dict = {'street': address_list[0],
                              'house_nr': address_list[1],
                              'apt_nr': address_list[2]
                              }
    except IndexError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text = 'Ваш адрес указан в неверном формате, попробуйте еще раз')    
        return DELIVERY_DETAILS

    # await context.bot.send_message(chat_id=update.effective_chat.id,
    #                                text='Адрес распо')

    context.user_data['delivery_address'] = full_address_dict

    await confirm_order(update, context)

    return CONCLUDE_ORDER
    


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number_days = context.user_data['days_to_rent_tool']
    tool_pricing = context.user_data['prices_for_chosen_tool']
    address_dict = context.user_data['delivery_address']

    chosen_tool_full = context.user_data['chosen_tool'] + ' ' + context.user_data['chosen_model']

    limits = [1, 3, 7]
    idx = bisect.bisect_left(limits, number_days)
    price_per_day = tool_pricing.iloc[idx, 0]

    total_price_tool = int(price_per_day) * int(number_days)

    delivery_fee = 500                              #FOR NOW -> PURELY ARBITRARY NUMBER, TODO: ADD THE ACTUAL CALCULATION LATER

    total_price = total_price_tool + delivery_fee

    buttons = [
        [
            InlineKeyboardButton(text='Подтвердить заказ', callback_data='confirm_order')
        ],
        [
            InlineKeyboardButton(text="Начать заново", callback_data='restart_order'),
            InlineKeyboardButton(text="Отменить заказ", callback_data='cancel_order')
        ]
    ]

    keyboard = InlineKeyboardMarkup(buttons)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Полная стоимость вашего заказа составляет {total_price} рублей\nПожалуйста, проверьте ваш заказ и адрес доставки:\n\n')

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Выбранный инструмент:\n{chosen_tool_full}\n\n')

    if address_dict == 'pick_up':
        address_to_display = 'Самовывоз по адресу'
    else:
        address_to_display = 'Улица ' + address_dict['street'] + '\nДом ' + address_dict['house_nr'] + '\nКвартира ' + address_dict['apt_nr']
        
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Выбранный адрес доставки:\n{address_to_display}\n\n', reply_markup=keyboard)

    return CONCLUDE_ORDER
    



async def conclude_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback_data = update.callback_query.data
    print(f'Callback Data in CONCLUDE_ORDER func is - {callback_data}')
    if callback_data == 'confirm_order':
        text = 'Ваш заказ подтвержден, спасибо!'
        await context.bot.send_message(chat_id = update.effective_chat.id,
                                       text=text)
        return PAYMENT

    elif callback_data == 'restart_order':
        list_of_tools_text = context.bot_data['list_of_tools_text']
        await context.bot.send_message(chat_id = update.effective_chat.id,
                                       text=list_of_tools_text)
        return TOOLS_SELECTION
    
    elif callback_data == 'cancel_order':
        text = f'Ваш заказ отменен:(\nПожалуйста, оставьте отзыв по работе бота:{AVITO_LINK}'
        return ConversationHandler.END
    



async def end_convo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation."""
    await update.message.reply_text(
        "До свидания!")

    print('ending the conversation')
    return ConversationHandler.END



"""
MAIN FUNCTION
"""

def main():
    #base setup
    builder = Application.builder()
    builder.token(TOKEN)
    application = builder.build()

    #get the GSH data into a dataframe and then add it to the Context object, so that all the handlers have access to it
    application.job_queue.run_repeating(refresh_gsh, interval=600, first=1)


    #conversation handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", conversation_start)],

        states = {INFO: [CallbackQueryHandler(tool_types_show)],
                  TOOLS_SELECTION: [MessageHandler(filters.TEXT & filters.Regex(r"^\d+$"), tool_models_show)],
                  CHOICE_PRICE_OR_DETAILS: [CallbackQueryHandler(choice_prices_or_details)],
                  SHOW_PRICES_OR_DETAILS: [CallbackQueryHandler(show_prices_or_details)],               
                  DELIVERY_QUESTION: [MessageHandler(filters.TEXT & filters.Regex(r"^\d+$"), delivery_question)],
                  DELIVERY_CHOICE: [CallbackQueryHandler(delivery_pickup_choice)],
                  DELIVERY_DETAILS: [MessageHandler(filters.TEXT, callback=delivery_details_ingestion)],
                  PICK_UP_CONFIRM: [CallbackQueryHandler(pickup_confirm)],
                  CONFIRM_ORDER: [MessageHandler(filters.TEXT, callback=confirm_order)],
                  CONCLUDE_ORDER: [CallbackQueryHandler(conclude_order)],
                  },

        fallbacks=[CommandHandler('end', end_convo),
                   CommandHandler("start", conversation_start),
                  ]
    )

    #command handlers
    application.add_handler(CommandHandler("payment", start_payment))

    #adding handlers
    application.add_error_handler(error)
    application.add_handler(conv_handler)

    application.run_polling() #this line just keeps the bot running until CTRL+C is hit
   


if __name__ == '__main__':
    main()