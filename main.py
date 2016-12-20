#!/usr/bin/env python3
import logging
import os
import re
from base64 import b64encode
from datetime import datetime
from email.utils import parseaddr
import telebot
from flask import (Flask, redirect, render_template, request,
                   send_from_directory)
import config
import vizidb

logger = telebot.logger
telebot.logger.setLevel(logging.DEBUG)

server = Flask(__name__)
bot = telebot.TeleBot(config.token)

# Логика бота


def get_image_uri(file_id):
    """Преобразует файл в то, что можно вставить в <img src=\"\">"""
    file_info = bot.get_file(file_id)
    file_format = file_info.file_path.split('.')[-1]
    photo = bot.download_file(file_info.file_path)
    data_uri = b64encode(photo).decode('ascii')
    return 'data:image/{0};base64,{1}'.format(file_format, data_uri)


def get_profile_image_id(message):
    try:
        return bot.get_user_profile_photos(
            user_id=int(message.chat.id)).photos[0][-1].file_id
    except Exception:
        return None


def get_name(message):
    if message.chat.last_name:
        return ' '.join([message.chat.first_name, message.chat.last_name])
    else:
        return message.chat.first_name


def get_username(message):
    if message.chat.username:
        return message.chat.username
    else:
        return str(message.chat.id)


def check_existing(message):
    query = vizidb.User.select().where(
        vizidb.User.username == get_username(message))
    return query.exists()


def parse_link(query):
    query = query.split()
    url = query[0]
    description = " ".join(query[1:])
    if description == '':
        raise ValueError
    if not (url.lower().startswith('http') or url.startswith('//')):
        url = '//' + url
    return [url, description]

# Бот: /start


@bot.message_handler(commands=['start'], func=lambda message:
                     not check_existing(message))
@bot.message_handler(commands=['restart'])
def start_bot(message, restarted=False):
    vizidb.create_user(get_username(message))
    reply = ''
    if not restarted:
        reply = 'Привет! Я Визий, я помогу сделать тебе веб-визитку.\n'
    reply += 'Тебя зовут {}, не так ли?'.format(get_name(message))
    markup = telebot.types.ReplyKeyboardMarkup(
        row_width=1, one_time_keyboard=True)
    markup.add(telebot.types.KeyboardButton('Да, всё верно'),
               telebot.types.KeyboardButton('Нет, давай поменяем'))
    new_message = bot.reply_to(message, reply, reply_markup=markup)
    bot.register_next_step_handler(new_message, name_step)


def name_step(message):
    if 'да' in message.text.lower():
        vizidb.set_name(get_username(message), get_name(message))
        bio_preparation(message, said_yes=True)
    elif 'нет' in message.text.lower():
        new_message = bot.reply_to(
            message, 'Хм, а как тогда тебя называть?',
            reply_markup=telebot.types.ReplyKeyboardHide())
        bot.register_next_step_handler(new_message, change_name_step)
    else:
        new_message = bot.reply_to(
            message, 'Прости, я довольно тупенький, давай попробуем заново')
        start_bot(new_message, restarted=True)


def change_name_step(message):
    vizidb.set_name(get_username(message), message.text)
    bio_preparation(message)


def bio_preparation(message, said_yes=False):
    if said_yes:
        new_message = bot.reply_to(
            message, 'Супер! Расскажешь немного о себе?',
            reply_markup=telebot.types.ReplyKeyboardHide())
    else:
        new_message = bot.reply_to(
            message, 'Запомнил! А теперь расскажешь немного о себе?')
    bot.register_next_step_handler(new_message, bio_step)


def bio_step(message):
    vizidb.set_bio(get_username(message), message.text)
    date_preparation(message)


def date_preparation(message):
    new_message = bot.reply_to(message,
                               ' '.join(['Здорово! А сколько тебе лет?',
                                         'Напиши мне дату своего рождения в',
                                         'формате ДД.ММ.ГГГГ, пожалуйста']))
    bot.register_next_step_handler(new_message, date_step)


def date_step(message):
    try:
        date = datetime.strptime(message.text, '%d.%m.%Y')
    except ValueError:
        new_message = bot.reply_to(message, ' '.join(
            ['Слушай, какая-то странная дата.', 'Давай ещё разок попробуем.',
             'Напомню формат: ДД.ММ.ГГГГ :)']))
        bot.register_next_step_handler(new_message, date_step)
    else:
        vizidb.set_birthday(get_username(message), date)
        image_preparation(message)


def image_preparation(message):
    if get_profile_image_id(message):
        markup = telebot.types.ReplyKeyboardMarkup(
            row_width=1, one_time_keyboard=True)
        markup.add(telebot.types.KeyboardButton('Да'),
                   telebot.types.KeyboardButton('Нет'))
        new_message = bot.send_photo(
            message.chat.id, get_profile_image_id(message),
            caption='Спасибо. Я могу использовать вот это фото?',
            reply_markup=markup)
        bot.register_next_step_handler(new_message, image_step)
    else:
        new_message = bot.reply_to(
            message, 'Как ты выглядишь? Отправь, пожалуйста, свою фотографию')
        bot.register_next_step_handler(new_message, upload_image_step)


def image_step(message):
    if 'Да' in message.text:
        vizidb.set_image(get_username(message), get_image_uri(
                         get_profile_image_id(message)))
        email_preparation(message)
    elif 'Нет' in message.text:
        new_message = bot.reply_to(
            message, 'Тогда пришли другую свою фотографию, пожалуйста',
            reply_markup=telebot.types.ReplyKeyboardHide())
        bot.register_next_step_handler(new_message, upload_image_step)


def upload_image_step(message):
    if message.content_type == 'photo':
        vizidb.set_image(get_username(message),
                         get_image_uri(message.photo[-1].file_id))
        email_preparation(message)
    else:
        new_message = bot.reply_to(
            message, 'По-моему, это не фотография. Ещё разок?')
        bot.register_next_step_handler(new_message, upload_image_step)


def email_preparation(message):
    new_message = bot.reply_to(
        message, 'Прекрасно! А какой у тебя email-адрес?',
        reply_markup=telebot.types.ReplyKeyboardHide())
    bot.register_next_step_handler(new_message, email_step)


def email_step(message):
    if '@' not in parseaddr(message.text)[1]:
        new_message = bot.reply_to(
            message, 'Что-то не похоже на адрес, проверь, пожалуйста')
        bot.register_next_step_handler(new_message, email_step)
    else:
        vizidb.set_email(get_username(message), parseaddr(message.text)[1])
        phone_preparation(message)


def phone_preparation(message):
    markup = telebot.types.ReplyKeyboardMarkup(
        row_width=1, one_time_keyboard=True)
    markup.add(telebot.types.KeyboardButton(
        'Отправить свой контакт', request_contact=True))
    new_message = bot.reply_to(
        message, 'Ага, записал. А как насчёт номера телефона?',
        reply_markup=markup)
    bot.register_next_step_handler(new_message, phone_step)


def phone_step(message):
    if message.content_type == 'contact':
        vizidb.set_phone(get_username(message),
                         '+' + message.contact.phone_number)
        links_preparation(message)
    pattern = re.compile('^((8|\+7)[\- ]?)?(\(?\d{3}\)?[\- ]?)?[\d\- ]{7,10}$')
    if pattern.match(message.text):
        vizidb.set_phone(get_username(message), message.text)
        links_preparation(message)
    else:
        new_message = bot.reply_to(
            message,
            ' '.join(['Это точно номер телефона?',
                      'Попробуй ещё раз, пожалуйста.',
                      'Лучше начать с +7 или 8, а продолжить ещё 10 цифрами']))
        bot.register_next_step_handler(new_message, phone_step)


def links_preparation(message):
    markup = telebot.types.ReplyKeyboardMarkup(
        row_width=1)
    markup.add(telebot.types.KeyboardButton(
        'Готово'))
    new_message = bot.reply_to(
        message, 'Хорошо, давай добавим к твоей визитке ссылки. ' +
        'Присылай по одной ссылку и описание через пробел.\n' +
        'Например, вот так: `http://ktwzk.me Мой сайт`\n\n' +
        'Когда закончишь, нажми кнопку внизу или просто напиши «Готово» :)',
        reply_markup=markup)
    bot.register_next_step_handler(new_message, links_loop)


def links_loop(message):
    if message.text.startswith('Готово'):
        final_step(message)
    else:
        markup = telebot.types.ReplyKeyboardMarkup(
            row_width=1, one_time_keyboard=True)
        markup.add(telebot.types.KeyboardButton(
            'Готово'))
        try:
            link = parse_link(message.text)
        except ValueError:
            new_message = bot.reply_to(
                message, 'Что-то пошло не так, попробуй ещё раз',
                reply_markup=markup)
            bot.register_next_step_handler(new_message, links_loop)
        else:
            vizidb.new_link(get_username(message), link[0], link[1])
            new_message = bot.reply_to(
                message, 'Запомнил!',
                reply_markup=markup)
            bot.register_next_step_handler(new_message, links_loop)


def final_step(message):
    bot.reply_to(
        message, 'А вот и твоя визитка!\nhttps://vizij.herokuapp.com/' +
        get_username(message) +
        '\nВсю информацию можно изменить с помощью команды /edit',
        reply_markup=telebot.types.ReplyKeyboardHide())
    bot.send_message(4557094, 'New user! https://vizij.herokuapp.com/' +
                     get_username(message))

# Бот: /edit


def get_edit_markup():
    markup = telebot.types.ReplyKeyboardMarkup(
        row_width=1, one_time_keyboard=True)
    markup.add(telebot.types.KeyboardButton('Имя'),
               telebot.types.KeyboardButton('Информация о себе'),
               telebot.types.KeyboardButton('Дата рождения'),
               telebot.types.KeyboardButton('Фотография'),
               telebot.types.KeyboardButton('E-mail'),
               telebot.types.KeyboardButton('Номер телефона'),
               telebot.types.KeyboardButton('Ссылки'),
               telebot.types.KeyboardButton('Ничего'))
    return markup


def get_links_markup(username):
    markup = telebot.types.ReplyKeyboardMarkup(
        row_width=1, one_time_keyboard=True)
    for description in vizidb.get_links(username):
        markup.add(telebot.types.KeyboardButton('❌ ' + description))
    markup.add(telebot.types.KeyboardButton('Готово'))
    return markup


@bot.message_handler(commands=['edit'], func=check_existing)
def edit(message):
    new_message = bot.reply_to(
        message, 'Что будем менять?', reply_markup=get_edit_markup())
    bot.register_next_step_handler(new_message, edit_choice)


def edit_choice(message):
    if 'Ничего' in message.text:
        bot.reply_to(
            message, 'Ок, пиши в любое время :)',
            reply_markup=telebot.types.ReplyKeyboardHide())
        return
    operations = {'Имя': edit_name,
                  'Информация о себе': edit_bio,
                  'Дата рождения': edit_birthday,
                  'Фотография': edit_image,
                  'E-mail': edit_email,
                  'Номер телефона': edit_phone,
                  'Ссылки': edit_links}
    replys = {'Имя': 'Как тебя называть?',
              'Информация о себе': 'Что напишем?',
              'Дата рождения': 'Это странно, но присылай ДД.ММ.ГГГГ :)',
              'Фотография': 'Новая фотография! Жду загрузки :)',
              'E-mail': 'Какая теперь у тебя почта?',
              'Номер телефона': 'Присылай новый номер :)',
              'Ссылки': 'Если хочешь удалить ссылку — нажми на её описание ' +
                        'ниже. Добавить — просто напиши ссылку и её описание' +
                        ' через пробел'}
    if message.text in operations:
        markup = telebot.types.ReplyKeyboardHide()
        if message.text == 'Ссылки':
            markup = get_links_markup(get_username(message))
        new_message = new_message = bot.reply_to(
            message, replys[message.text],
            reply_markup=markup)
        bot.register_next_step_handler(new_message, operations[message.text])
    else:
        new_message = bot.reply_to(
            message, 'Не совсем понял, ещё раз: что меняем?',
            reply_markup=get_edit_markup())
        bot.register_next_step_handler(new_message, edit_choice)


def edit_name(message):
    vizidb.set_name(get_username(message), message.text)
    final_editing(message)


def edit_bio(message):
    vizidb.set_bio(get_username(message), message.text)
    final_editing(message)


def edit_birthday(message):
    date = message.text
    try:
        date = datetime.strptime(date, '%d.%m.%Y')
    except ValueError:
        new_message = bot.reply_to(message, ' '.join(
            ['Слушай, какая-то странная дата.', 'Давай ещё разок попробуем.',
             'Напомню формат: ДД.ММ.ГГГГ']))
        bot.register_next_step_handler(new_message, edit_birthday)
    else:
        vizidb.set_birthday(get_username(message), date)
        final_editing(message)


def edit_image(message):
    if message.content_type == 'photo':
        vizidb.set_image(get_username(message),
                         get_image_uri(message.photo[-1].file_id))
        final_editing(message)
    else:
        new_message = bot.reply_to(
            message, 'По-моему, это не фотография. Ещё разок?')
        bot.register_next_step_handler(new_message, edit_image)


def edit_email(message):
    if '@' not in parseaddr(message.text)[1]:
        new_message = bot.reply_to(
            message, 'Что-то не похоже на адрес, проверь, пожалуйста')
        bot.register_next_step_handler(new_message, edit_email)
    else:
        vizidb.set_email(get_username(message), parseaddr(message.text)[1])
        final_editing(message)


def edit_phone(message):
    if message.content_type == 'contact':
        vizidb.set_phone(get_username(message),
                         '+' + message.contact.phone_number)
        final_editing(message)
    pattern = re.compile('^((8|\+7)[\- ]?)?(\(?\d{3}\)?[\- ]?)?[\d\- ]{7,10}$')
    if pattern.match(message.text):
        vizidb.set_phone(get_username(message), message.text)
        final_editing(message)
    else:
        new_message = bot.reply_to(
            message,
            ' '.join(['Это точно номер телефона?',
                      'Попробуй ещё раз, пожалуйста.',
                      'Лучше начать с +7 или 8, а продолжить ещё 10 цифрами']))
        bot.register_next_step_handler(new_message, edit_phone)


def edit_links(message):
    if message.text.startswith('Готово'):
        final_editing(message)
    elif message.text.startswith('❌ '):
        try:
            vizidb.del_link(get_username(message), message.text[2:])
        except Exception:
            text = 'Что-то пошло не так, попробуй ещё раз.'
        else:
            text = 'Хорошо, удалил. Если это всё, можно нажать кнопку «Готово»'
        new_message = bot.reply_to(
            message, text,
            reply_markup=get_links_markup(get_username(message)))
        bot.register_next_step_handler(new_message, edit_links)
    else:
        try:
            link = parse_link(message.text)
        except ValueError:
            new_message = bot.reply_to(
                message, 'Что-то пошло не так, попробуй ещё раз',
                reply_markup=get_links_markup(get_username(message)))
            bot.register_next_step_handler(new_message, edit_links)
        else:
            vizidb.new_link(get_username(message), link[0], link[1])
            new_message = bot.reply_to(
                message,
                'Запомнил! Можно в любой момент завершить кнопкой «Готово»',
                reply_markup=get_links_markup(get_username(message)))
            bot.register_next_step_handler(new_message, edit_links)


def final_editing(message):
    new_message = bot.reply_to(message,
                               'Хорошо!\nВизитка по-прежнему тут: ' +
                               'https://vizij.herokuapp.com/' +
                               get_username(message) +
                               '\nХочешь ещё что-то поменять?',
                               reply_markup=get_edit_markup())
    bot.register_next_step_handler(new_message, edit_choice)

# Логика веба


@server.before_request
def _db_connect():
    vizidb.db.connect()


@server.teardown_request
def _db_close(exc):
    if not vizidb.db.is_closed():
        vizidb.db.close()


@server.route('/')
def main_page():
    return send_from_directory(os.path.join(server.root_path, 'static'),
                               'index.html')


@server.route('/favicon.ico')
def favicon():
    return '404', 404


@server.route('/<username>')
def user_page(username):
    try:
        user = vizidb.User.get(username=username)
    except Exception:
        return redirect('/')
    return render_template('page.html', user=user)


@server.route('/bot', methods=['POST'])
def webhook():
    bot.process_new_messages([telebot.types.Update.de_json(
        request.stream.read().decode('utf-8')).message])
    return 'ok', 200


if __name__ == '__main__':
    server.run(host='0.0.0.0', port=config.port)
