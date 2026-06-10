"""
Admin Panel کامل برای GapGPT Multi-Chat
ویژگی‌ها: آمار، مدیریت کاربران، Threadها، Broadcast، Ban/Unban
"""
from balethon.objects.message import Message
from balethon.conditions import command
from balethon.objects.inline_keyboard import InlineKeyboard, InlineKeyboardButton
from balethon.objects.reply_keyboard import ReplyKeyboard
import config
from gap_ai import ai_manager
from database.flexible_db import FlexibleDB
from typing import Dict, List
import asyncio
import json

# دیتابیس برای admin
admin_db = FlexibleDB("admin_panel.db")

# State مدیریت Admin
admin_states: Dict[str, Dict] = {}

def admin_handlers(bot):
    """همه Handler های Admin"""
    
    @bot.on_message(command("admin"))
    async def admin_panel(message: Message):
        user_id = str(message.chat.id)
        if user_id not in config.ADMINS:
            await message.reply("❌ دسترسی ندارید!")
            return
        
        admin_states[user_id] = {"page": "main"}
        
        keyboard = InlineKeyboard()
        keyboard.row(
            InlineKeyboardButton("📊 آمار کلی", callback_data="stats_all"),
            InlineKeyboardButton("👥 کاربران", callback_data="users")
        )
        keyboard.row(
            InlineKeyboardButton("💬 Threadها", callback_data="threads"),
            InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")
        )
        keyboard.row(
            InlineKeyboardButton("🚫 Ban List", callback_data="bans"),
            InlineKeyboardButton("⚙️ تنظیمات", callback_data="settings")
        )
        keyboard.row(InlineKeyboardButton("🔙 بستن", callback_data="close_admin"))
        
        await message.reply("👑 **پنل ادمین**", reply_markup=keyboard, parse_mode="Markdown")

    @bot.on_callback_query(lambda c: c.data.startswith("admin_") or c.data in [
        "stats_all", "users", "threads", "broadcast", "bans", "settings", "close_admin"
    ])
    async def admin_callback(callback):
        user_id = str(callback.from_user.id)
        if user_id not in config.ADMINS:
            await callback.answer("❌ دسترسی ندارید!", show_alert=True)
            return
        
        data = callback.data
        
        # بستن پنل
        if data == "close_admin":
            await callback.delete()
            if user_id in admin_states:
                del admin_states[user_id]
            return
        
        # آمار کلی
        if data == "stats_all":
            stats = await get_global_stats()
            text (
                "📊 **آمار کلی سیستم**\n\n"
                f"👥 **کاربران:** {stats['users']:,}\n"
                f"💬 **Threadها:** {stats['threads']:,}\n"
                f"📨 **پیام‌ها:** {stats['messages']:,}\n"
                f"💰 **توکن‌ها:** {stats['tokens']:,}\n\n"
                f"📈 **رشد امروز:** +{stats['daily_growth']}\n"
                f"💾 **حجم DB:** {stats['db_size']:.1f} MB"
            )
            
            keyboard = InlineKeyboard()
            keyboard.row(InlineKeyboardButton("🔄 بروزرسانی", callback_data="stats_all"))
            keyboard.row(InlineKeyboardButton("👥 کاربران", callback_data="users"))
            
            await callback.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return
        
        # کاربران
        elif data == "users":
            users = await get_top_users()
            text = "👥 **کاربران فعال** (24h)\n\n"
            for i, user in enumerate(users[:10], 1):
                text += f"{i}. `{user['user_id']}` - {user['threads']} Thread\n"
            
            keyboard = InlineKeyboard()
            keyboard.row(InlineKeyboardButton("🔄 بروزرسانی", callback_data="users"))
            keyboard.row(InlineKeyboardButton("🏆 Top 50", callback_data="top50"))
            
            await callback.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return
        
        # Threadها
        elif data == "threads":
            threads = await get_active_threads()
            text = "💬 **Threadهای فعال** (24h)\n\n"
            for i, thread in enumerate(threads[:15], 1):
                text += f"{i}. `{thread['id'][:8]}` - {thread['title']}\n"
            
            keyboard = InlineKeyboard()
            keyboard.row(InlineKeyboardButton("🔄 بروزرسانی", callback_data="threads"))
            
            await callback.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return
        
        # Broadcast
        elif data == "broadcast":
            admin_states[user_id]["page"] = "broadcast"
            await callback.edit_message_text(
                "📢 **ارسال Broadcast**\n\n"
                "متن پیام را ارسال کنید:\n"
                "`/cancel` برای لغو",
                parse_mode="Markdown"
            )
            return
        
        # Ban List
        elif data == "bans":
            bans = get_ban_list()
            text = "🚫 **لیست بن**:\n\n"
            if bans:
                for ban in bans[:20]:
                    text += f"• `{ban['user_id']}` - {ban['reason']}\n"
            else:
                text += "✅ هیچ کاربری بن نشده"
            
            keyboard = InlineKeyboard()
            keyboard.row(
                InlineKeyboardButton("➕ بن جدید", callback_data="ban_add"),
                InlineKeyboardButton("✅ آنبن", callback_data="ban_remove")
            )
            keyboard.row(InlineKeyboardButton("🔙 بازگشت", callback_data="stats_all"))
            
            await callback.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return

    # Broadcast Handler
    @bot.on_message(command("broadcast"))
    async def broadcast_handler(message: Message):
        user_id = str(message.chat.id)
        if user_id not in config.ADMINS:
            return
        
        # ارسال به همه کاربران
        stats = await send_broadcast(message.text)
        await message.reply(
            f"📢 **Broadcast ارسال شد**\n\n"
            f"✅ موفق: {stats['success']}\n"
            f"❌ خطا: {stats['failed']}\n"
            f"⏱️ زمان: {stats['time']:.1f}s",
            parse_mode="Markdown"
        )

    # Ban/Unban Commands
    @bot.on_message(command("ban"))
    async def ban_user(message: Message):
        user_id = str(message.chat.id)
        if user_id not in config.ADMINS:
            return
        
        try:
            parts = message.text.split(maxsplit=2)
            if len(parts) < 3:
                await message.reply("❌ `/ban user_id دلیل`", parse_mode="Markdown")
                return
            
            target_id, reason = parts[1], parts[2]
            result = ban_user(target_id, reason)
            
            await message.reply(
                f"🚫 **کاربر بن شد:**\n`{target_id}`\n**دلیل:** {reason}",
                parse_mode="Markdown"
            )
        except:
            await message.reply("❌ فرمت اشتباه!")

    @bot.on_message(command("unban"))
    async def unban_user(message: Message):
        user_id = str(message.chat.id)
        if user_id not in config.ADMINS:
            return
        
        try:
            target_id = message.text.split()[1]
            result = unban_user(target_id)
            
            status = "✅ آنبن شد" if result else "❌ پیدا نشد"
            await message.reply(f"**{target_id}** {status}", parse_mode="Markdown")
        except:
            await message.reply("❌ `/unban user_id`")

    return {
        "admin_panel": admin_panel,
        "admin_callback": admin_callback,
        "broadcast_handler": broadcast_handler,
        "ban_user": ban_user,
        "unban_user": unban_user
    }

# ====================== توابع Admin ====================

async def get_global_stats() -> dict:
    """آمار کامل سیستم"""
    stats = {
        "users": ai_manager.db.count("chat_threads", "user_id IS NOT NULL"),
        "threads": ai_manager.db.count("chat_threads", "is_active = 1"),
        "messages": ai_manager.db.count("chat_messages"),
        "tokens": ai_manager.db.execute_raw(
            "SELECT SUM(tokens) as total FROM chat_messages"
        ).data[0]['total'] or 0,
        "daily_growth": ai_manager.db.count(
            "chat_threads", 
            "DATE(updated_at) = DATE('now')"
        ),
        "db_size": ai_manager.db.get_database_stats().get('database_size', 0) / (1024*1024)
    }
    return stats

async def get_top_users(limit: int = 10) -> list:
    """Top کاربران"""
    result = ai_manager.db.execute_raw("""
        SELECT user_id, COUNT(*) as threads 
        FROM chat_threads 
        WHERE DATE(updated_at) = DATE('now')
        GROUP BY user_id 
        ORDER BY threads DESC 
        LIMIT ?
    """, (limit,))
    return result.data or []

async def get_active(limit: int = 15) -> list:
    """Threadهای فعال"""
    result = ai_manager.db.select(
        "chat_threads",
        order_by="updated_at DESC",
        limit=limit
    )
    return result.data or []

async def send_broadcast(message_text: str) -> dict:
    """ارسال Broadcast"""
    start_time = asyncio.get_event_loop().time()
    
    users = ai_manager.db.execute_raw("""
        SELECT DISTINCT user_id FROM chat_threads WHERE is_active = 1
    """).data
    
    success, failed = 0, 0
    
    for user in users[:1000]:  # محدود به 1000
        try:
            # چک بن
            if is_banned(user['user_id']):
                failed += 1
                continue
            
            await bot.send_message(
                user['user_id'],
                f"📢 **پیام ادمین:**\n\n{message_text}",
                parse_mode="Markdown"
            )
            success += 1
            await asyncio.sleep(0.05)  # Rate limit
        except:
            failed += 1
    
    duration = asyncio.get_event_loop().time() - start_time
    return {"success": success, "failed": failed, "time": duration}

def ban_user(user_id: str, reason: str = "نامشخص") -> bool:
    """بن کاربر"""
    # ایجاد جدول ban اگر وجود نداره
    admin_db.create_table(
        "banned_users",
        "user_id TEXT PRIMARY KEY, reason TEXT, banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )
    
    result = admin_db.insert(
        "banned_users",
        {"user_id": user_id, "reason": reason}
    )
    return result.success

def unban_user(user_id: str) -> bool:
    """آنبن کاربر"""
    result = admin_db.delete(
        "banned_users",
        "user_id = ?",
        (user_id,)
    )
    return result.rowcount > 0

def get_ban_list(limit: int = 50) -> list:
    """لیست بن"""
    result = admin_db.select(
        "banned_users",
        limit=limit,
        order_by="banned_at DESC"
    )
    return result.data or []

def is_banned(user_id: str) -> bool:
    # """چک بن"""
    # result = admin_db.select_one(
    #     "banned_users",
    #     "user_id = ?",
    #     (user_id,)
    # )
    # return bool(result.data)
    return False
# ✅ Export برای main.py
admin_functions = {
    "is_banned": is_banned,
    "ban_user": ban_user,
    "unban_user": unban_user
}