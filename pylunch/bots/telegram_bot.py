from pylunch.config import AppConfig
import pylunch
import pylunch.utils
from pylunch import lunch

from typing import List

import telegram
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import MessageHandler, CommandHandler, Filters, CallbackContext, \
    InlineQueryHandler, Dispatcher, Updater

from uuid import uuid4
import logging

log = logging.getLogger(__name__)


class CommandHandlers:
    def __init__(self, pylunch_bot: 'PyLunchTelegramBot'):
        self.pylunch_bot = pylunch_bot
        self._commands = {}

    def select_instances(self, selectors, fuzzy=False, tags=False, with_disabled=True) -> List[lunch.LunchEntity]:
        return self.service.instances.select(selectors, fuzzy=fuzzy, tags=tags, with_disabled=with_disabled)

    def _instance_transform(self, instance):
        content = self.service.resolve_text(instance)
        log.debug(f"[Telegram] entity [{instance.name}]: {content}")
        return f"{instance.display_name} ({instance.name}):\n\n{content}\n\n{instance.url}"

    def print_instances(self, update, instances, transform=None):
        transform = transform if transform is not None else self._instance_transform

        def _write(content): self.send_msg(update, content)

        pylunch.utils.write_instances(instances, transform=transform, writer=_write)

    @property
    def service(self) -> lunch.LunchService:
        return self.pylunch_bot.service

    def get_one(self, update: Update, context: CallbackContext):
        result = self.select_instances(context.args)
        log.debug(f"Found for [{context.args}]: {result}")
        self.print_instances(update, result, transform=str)

    def get_menu_one(self, update: Update, context: CallbackContext):
        result = self.select_instances(context.args, tags=False)
        log.debug(f"Found for [{context.args}]: {result}")
        self.print_instances(update, result)

    def get_menu_by_tags(self, update: Update, context: CallbackContext):
        result = self.select_instances(context.args, tags=True)
        log.debug(f"Found for [{context.args}]: {result}")
        self.print_instances(update, result)

    def find_by_tags(self, update: Update, context: CallbackContext):
        result = self.select_instances(context.args, tags=True)
        log.debug(f"Found for [{context.args}]: {result}")
        self.print_instances(update, result, transform=str)

    def list_restaurants(self, update: Update, context: CallbackContext):
        name = " ".join(context.args) if context.args else ""
        result = f"Available ({len(self.service.instances)}):\n"
        for restaurant in self.service.instances.values():
            result += f"{restaurant.name} - {restaurant.url}\n"
        self.send_msg(update, result, markdown=True)

    def get_avaliable_tags(self, update: Update, context: CallbackContext):
        tags = self.service.instances.all_tags()
        result = f"Available ({len(tags)}):\n"
        for tag in tags:
            result += f"- {tag}\n"
        self.send_msg(update, result, markdown=True)

    def start_handler(self, update: Update, context: CallbackContext):
        log.info("[START] Client logged in")
        welcome_message = "Welcome!\n\n"
        welcome_message += self.help_string()
        self.send_msg(update, welcome_message)

    def send_msg(self, update: Update, message, markdown=False):
        log.info(f"[MSG] Message: {message}")
        params = {}
        if markdown:
            params['parse_mode'] = telegram.ParseMode.MARKDOWN
        result = update.message.reply_text(message)
        log.debug(f"[Telegram] Send result: {result}")

    def help_string(self) -> str:
        commands = ""
        for (name, val) in self._commands.items():
            commands += f"- /{name} {val}\n"
        return commands

    def help_handler(self, update: Update, context: CallbackContext):
        log.info("[HELP] Show help")
        result = self.help_string()
        self.send_msg(update, result)

    def inline_query_handler(self, update: Update, context: CallbackContext):
        log.info(f"INLINE initiated")
        query = update.inline_query.query
        log.info(f"[INLINE] Inline query: {query}")
        food_content = InputTextMessageContent(self.service.instances.find_one(query))
        results = [InlineQueryResultArticle(id=uuid4(), title="Get", input_message_content=food_content), ]
        update.inline_query.answer(results)

    def error(self, update, context):
        """Log Errors caused by Updates."""
        log.warning('Error "%s" caused by an update %s', context.error, update)
        update.message.reply_text(context.error)

    @property
    def dispatcher(self) -> Dispatcher:
        return self.pylunch_bot.client.dispatcher

    def add_cmd_handler(self, name, help: str, handler, cls=CommandHandler, **kwargs):
        self.add_help(name, help)
        log.info(f"[CMD] Adding command \"{name}\": {help}")
        pass_args = kwargs.get('pass_args', True)
        cmd = cls(name, handler, pass_args=pass_args, **kwargs)
        self.dispatcher.add_handler(cmd)

    def add_help(self, name, help: str):
        self._commands[name] = help


def message_handler(update: Update, context: CallbackContext):
    text = update.message.text
    log.info(f"Received message: {text}")
    update.message.reply_text(f"Pong: {text}")


def register_handlers(bot):
    dispatcher: Dispatcher = bot.client.dispatcher
    cmd = CommandHandlers(bot)
    # Message handler
    dispatcher.add_handler(MessageHandler(Filters.text | Filters.status_update,
                                          message_handler))

    # Basic commands
    cmd.add_cmd_handler('help', 'Show help', cmd.help_handler)
    cmd.add_cmd_handler('start', 'Begin the conversation', cmd.start_handler)

    # Command handler
    cmd.add_cmd_handler('info', '<restaurant> - Get an info for a restaurant', cmd.get_one)
    cmd.add_cmd_handler('tinfo', '<expr> Find restaurants by tags', cmd.find_by_tags)
    cmd.add_cmd_handler('ls', 'Get list of available restaurants', cmd.list_restaurants)
    cmd.add_cmd_handler('tags', 'Get list of all available tags', cmd.get_avaliable_tags)
    cmd.add_cmd_handler('tmenu', '<expr> Get menu for restaurant based on tags', cmd.get_menu_by_tags)
    cmd.add_cmd_handler('menu', '<restaurant> Get menu by restaurant name', cmd.get_menu_one)

    # Inline handler
    dispatcher.add_handler(InlineQueryHandler(cmd.inline_query_handler))
    dispatcher.add_error_handler(cmd.error)


class PyLunchTelegramBot:
    def __init__(self, service: lunch.LunchService):
        self._service = service
        self._client = None

    def run(self):
        token = self.config.telegram_token
        log.info(f"Using the token: {token}")
        register_handlers(self)
        self.client.start_polling()
        self.client.idle()

    @property
    def service(self) -> lunch.LunchService:
        return self._service

    @property
    def config(self) -> AppConfig:
        return self.service.config

    @property
    def client(self) -> Updater:
        if self._client is None:
            self._client = Updater(token=self.config.telegram_token, use_context=True)
        return self._client
