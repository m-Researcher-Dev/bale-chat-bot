from balethon.objects.callback_query import CallbackQuery
from balethon.objects.message import Message
from balethon import Client
from balethon.conditions import command, regex, text
from balethon.objects import (
    InlineKeyboard,
    InlineKeyboardButton,
    ReplyKeyboard,
    ReplyKeyboardButton,
)
import config
import gap_ai
from gap_ai import get_ai_manager, register_user
from state_manager import state_manager
from handlers.admin_handlers import is_banned

sessions = []


def session(chat_id: str, state: str):
    new_session = {"chat_id": chat_id, "state": state}
    sessions.append(new_session)


def search(chat_id: str):
    for session_ in sessions:
        if session_["chat_id"] == chat_id:
            return session_["state"]
    return False


def register_user_handlers(bot: Client):
    @bot.on_message(command("start"))
    async def start_handler(message: Message):
        user_id = str(message.chat.id)
        

        if is_banned(user_id):
            await message.reply("🚫 حساب شما مسدود است!")
            return

        register_user(user_id, message.author.username, message.author.first_name)

        ai = get_ai_manager()
        result = ai.create_thread(user_id, "چت اصلی")  # ✅ title درست

        if result["success"]:
            state_manager.set(
                user_id,
                {
                    "current_thread": result["thread_id"],
                    "threads": [result["thread_id"]],
                },
            )

            keyboard = ReplyKeyboard(
                [ReplyKeyboardButton("📝 شروع چت")],
                [ReplyKeyboardButton("📋 Threadها")],
                [ReplyKeyboardButton("➕ Thread جدید")],
                [ReplyKeyboardButton("ℹ️ راهنما")],
                resize_keyboard=True,
            )

            await message.reply(
                config.USER_START_MESSAGE.format(thread_id=result["thread_id"]),
                reply_markup=keyboard,
            )

    @bot.on_message(command("end"))
    async def end(message: Message):
        chat_id = str(message.chat.id)
        session(chat_id, state="end chat")
        await message.reply("✅ پایان چت")

    @bot.on_message(regex(r"^(📝 شروع چت|شروع چت)$"))
    async def chat_start(message: Message):
        user_id = str(message.chat.id)
        state = state_manager.get(user_id)

        if not state or not state.get("current_thread"):
            await message.reply("❌ ابتدا /start بزنید!")
            return

        current_thread = state["current_thread"]
        await message.reply(
            f"💬 **Thread فعال:** `{current_thread[:8]}`\n\n" f"پیام خود را بفرستید:",
        )
        session(str(message.chat.id), state="waiting for chat")

    @bot.on_message(regex("📋 Threadها"))
    async def list_threads(message: Message):
        user_id = str(message.chat.id)
        state = state_manager.get(user_id)

        if not state:
            await message.reply("❌ ابتدا /start بزنید!")
            return

        threads = state_manager.list_threads(user_id)
        keyboard = []

        for thread in threads[:8]:
            callback_data = f"switch_{thread['id']}"
            keyboard.append(
                
                    InlineKeyboardButton(
                        f"🔹 {thread.get('title', 'بدون نام')} ({thread.get('message_count', 0)}msg)",
                        callback_data,
                    )
                
            )

        keyboard.append(
            [
                InlineKeyboardButton("➕ Thread جدید", "new_thread"),
                InlineKeyboardButton("🔙 بستن", "close_threads"),
            ]
        )

        await message.reply(
            f"📋 **Threadهای شما:** ({len(threads)})",
            reply_markup=InlineKeyboard(keyboard),
        )

    @bot.on_message(regex("^(ℹ️ راهنما|راهنما)$"))
    async def help_handler(message):
        await message.reply(config.USER_HELP_MESSAGE)

    @bot.on_message(regex("^(➕ Thread جدید|Thread جدید)$"))
    async def new_thread_handler(message: Message):
        user_id = str(message.chat.id)
        quota = state_manager.check_quota(user_id)

        if not quota["thread_quota"]["has_quota"]:
            await message.reply("❌ **حداکثر Thread رسید!**")
            return

        result = state_manager.create_thread(user_id, "چت جدید")  # ✅ title درست
        if result["success"]:
            state_manager.switch_thread(
                user_id, result["thread_id"]
            )  # ✅ switch خودکار
            await message.reply(f"✅ **Thread جدید:** `{result['thread_id'][:8]}`")
        else:
            await message.reply(f"❌ **خطا:** {result.get('error', 'نامشخص')}")

    @bot.on_callback_query()
    async def callback_handler(callback_query: CallbackQuery):
        user_id = str(callback_query.author.id)

        if is_banned(user_id):
            await callback_query.answer("🚫 مسدود!", show_alert=True)
            return

        data = callback_query.data
        state = state_manager.get(user_id)
        ai = get_ai_manager()

        if data.startswith("switch_"):
            thread_id = data.replace("switch_", "")
            success, msg = state_manager.switch_thread(user_id, thread_id)

            await callback_query.answer(msg)
            await callback_query.message.reply(
                f"✅ **Thread تغییر یافت:** `{thread_id[:8]}`\n\n" f"💬 حالا چت کنید:",
            )
            session(str(callback_query.message.chat.id), state="waiting for chat")

        elif data == "new_thread":
            quota = state_manager.check_quota(user_id)
            if not quota["thread_quota"]["has_quota"]:
                await callback_query.answer("❌ حداکثر Thread!", show_alert=True)
                return

            result = state_manager.create_thread(user_id, "چت جدید")
            if result["success"]:
                await callback_query.answer("✅ Thread جدید!")
                await callback_query.message.edit_text(
                    f"✅ **Thread جدید:** `{result['thread_id'][:8]}`\n"
                    f"💬 شروع چت کنید:",
                )
                session(str(callback_query.message.chat.id), state="waiting for chat")

        elif data == "delet_chat":  
            if not state or not state.get("current_thread"):
                await callback_query.answer("❌ Thread پیدا نشد!", show_alert=True)
                return
            
            thread_id = state["current_thread"]
            ai.delete_thread(thread_id, user_id)
            await callback_query.message.delete()
            await callback_query.answer("🗑️ Thread حذف شد!", show_alert=True)

        elif data == "close_threads":
            await callback_query.message.delete()

    @bot.on_message(text)
    async def main_chat(message: Message):
        user_id = str(message.chat.id)
        chat_state = search(str(message.chat.id))
        
        message_count = gap_ai._db.select("chat_threads","user_id = ?",(user_id,),["message_count"])
        all_messages = 0
        for i in message_count.data:
            all_messages += int(i.get("message_count"))
        print(all_messages)
        if chat_state != "waiting for chat":
            return

        if is_banned(user_id) or not message.text:
            return

        # این مشکل دارد و اکنون فقط برای تست است
        if all_messages >= 10:
            await message.reply("❌ **سهمیه پیام تمام شد!**\n\n💎 ارتقا به پریمیوم")
            return

        state = state_manager.get(user_id)

        if not state or not state.get("current_thread"):
            await message.reply("❌ ابتدا `/start` بزنید!")
            return

        current_thread = state["current_thread"]

        typing_msg = await message.reply("🤔 **در حال فکر...**")

        ai = get_ai_manager()
        result = ai.chat(current_thread, message.text, user_id)
        await typing_msg.delete()

        if result["success"]:
            stats = result["stats"]

            response_text = (
                f"🤖 **پاسخ:**\n\n"
                f"{result['response']}\n\n"
                f"📊 **آمار:**\n"
                f"• پیام‌ها: {result['message_count']}\n"
                f"• توکن: {result['tokens_used']:,}"
            )

            # ✅ دکمه حذف
            keyboard = InlineKeyboard([InlineKeyboardButton("🗑️ پاک کردن این Thread", "delet_chat")])

            await message.reply(response_text, reply_markup=keyboard)
        else:
            await message.reply(f"❌ **خطا:** {result['response']}")
