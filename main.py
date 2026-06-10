from balethon import Client
import config
from gap_ai import init_ai_manager
from handlers import register_user_handlers
from handlers import admin_handlers, admin_functions

bot = Client(config.BOT_TOKEN)

# ثبت Handlerها
register_user_handlers(bot)
admin_handlers = admin_handlers(bot)

# Global functions
is_banned = admin_functions["is_banned"]

if __name__ == "__main__":
    print("🚀 GapGPT Multi-Chat راه‌اندازی...")
    init_ai_manager()
    print("✅ AI Manager آماده")
    print("🎉 Bot آماده!")
    bot.run()
