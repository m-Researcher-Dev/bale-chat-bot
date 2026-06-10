"""
GapGPT - بدون وابستگی به database/__init__.py
"""
import uuid
import logging
import re
import json
from typing import List, Dict, Optional
from datetime import datetime
from openai import OpenAI
from config import DEFAULT_MODEL,GAPGPT_API_KEY
_db = None

def get_gapgpt_db():
    """Lazy DB - بدون Circular Import"""
    global _db
    if _db is None:
        from database.flexible_db import FlexibleDB  # ✅ Direct!
        _db = FlexibleDB("gapgpt_multi.db")
        _initialize_tables(_db)
    return _db

def _initialize_tables(db):
    """ایجاد جداول GapGPT"""
    tables = {
        "users": "user_id TEXT PRIMARY KEY, username TEXT, first_name TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "chat_threads": "id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT, is_active BOOLEAN DEFAULT 1, message_count INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "chat_messages": "id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, tokens INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "user_states" : "user_id TEXT PRIMARY KEY, current_thread TEXT, threads TEXT, state_data TEXT",
        "CREATE TABLE IF NOT EXISTS banned_users":"user_id TEXT PRIMARY KEY,created_at TEXT"

    }
    
    for table, schema in tables.items():
        db.create_table(table, schema)
    
    for table, schema in tables.items():
        db.create_table(table, schema)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GapAI")

class GapAIChatMulti:
    """AI Manager کامل - Multi-Thread"""
    
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = OpenAI(
            base_url="https://api.gapgpt.app/v1", 
            api_key=GAPGPT_API_KEY
        )
        self.max_tokens = 8000
        
        logger.info(f"🚀 GapAI Multi-Thread آماده - مدل: {model}")
    
    def _estimate_tokens(self, text: str) -> int:
        """تخمین token"""
        if not text: return 0
        text = re.sub(r'\s+', ' ', text.strip())
        return max(1, len(text) // 3)
    
    def create_thread(self, user_id: str, title: str = "چت جدید") -> Dict:
        """ایجاد Thread جدید"""
        thread_id = str(uuid.uuid4())[:12]
        db = get_gapgpt_db()
        
        result = db.insert("chat_threads", {
            "id": thread_id,
            "user_id": user_id,
            "title": title[:100]
        })
        
        if result.rowcount > 0:
            # به‌روزرسانی state کاربر
            self._update_user_state(user_id, thread_id)
            logger.info(f"✅ Thread ایجاد شد: {thread_id} برای {user_id}")
            return {
                "success": True,
                "thread_id": thread_id,
                "title": title,
                "message": f"Thread جدید: `{thread_id}`"
            }
        return {"success": False, "error": "خطا در ایجاد Thread"}
    
    def get_user_threads(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Thread های کاربر"""
        db = get_gapgpt_db()
        result = db.select(
            "chat_threads",
            "user_id = ? AND is_active = 1",
            (user_id,),
            ["id","title"],
            limit
        )
        
        threads = []
        if result.success:
            for thread in result.data:
                stats = self._get_thread_stats(thread['id'])
                threads.append({**thread, **stats})
        return threads
    
    def _get_thread_stats(self, thread_id: str) -> Dict:
        """آمار Thread"""
        db = get_gapgpt_db()
        msg_count = db.count("chat_messages", "thread_id = ?", (thread_id,))
        
        thread_result = db.select_one("chat_threads", "id = ?", (thread_id,))
        total_tokens = thread_result.data.get('total_tokens', 0) if thread_result.success else 0
        
        return {
            "message_count": msg_count,
            "total_tokens": total_tokens
        }
    
    def chat(self, thread_id: str, message: str, user_id: str = None) -> Dict:
        """چت Multi-Thread"""
        try:
            db = get_gapgpt_db()
            
            # اعتبارسنجی Thread
            thread = db.select_one(
                "chat_threads", 
                "id = ? AND is_active = 1", 
                (thread_id,)
            )
            
            if not thread.success or not thread.data:
                return {"success": False, "response": "❌ Thread پیدا نشد"}
            
            if user_id and thread.data['user_id'] != user_id:
                return {"success": False, "response": "❌ دسترسی ندارید"}
            
            # تاریخچه
            history = self._get_thread_history(thread_id)
            history.append({"role": "user", "content": message})
            
            # AI Response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=history[-25:],
                temperature=0.7,
                max_tokens=2000
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # ذخیره پیام‌ها
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_tokens = self._estimate_tokens(message)
            ai_tokens = self._estimate_tokens(ai_response)
            total_tokens = user_tokens + ai_tokens
            
            db.insert("chat_messages", {
                "thread_id": thread_id,
                "role": "user",
                "content": message,
                "tokens": user_tokens,
                "created_at": now
            })
            
            db.insert("chat_messages", {
                "thread_id": thread_id,
                "role": "assistant", 
                "content": ai_response,
                "tokens": ai_tokens,
                "created_at": now
            })
            
            # آپدیت Thread
            current_thread = db.select_one("chat_threads", "id = ?", (thread_id,))
            if current_thread.success:
                new_tokens = current_thread.data.get('total_tokens', 0) + total_tokens
                new_count = current_thread.data.get('message_count', 0) + 2
                
                db.update(
                    "chat_threads",
                    {
                        "updated_at": now,
                        "total_tokens": new_tokens,
                        "message_count": new_count
                    },
                    "id = ?", (thread_id,)
                )
            
            stats = self._get_thread_stats(thread_id)
            
            return {
                "success": True,
                "response": ai_response,
                "tokens_used": total_tokens,
                "stats": stats,
                "thread_id": thread_id
            }
            
        except Exception as e:
            logger.error(f"❌ Chat Error {thread_id}: {e}")
            return {"success": False, "response": f"❌ خطا: {str(e)[:100]}"}
    
    def _get_thread_history(self, thread_id: str) -> List[Dict]:
        """تاریخچه Thread"""
        db = get_gapgpt_db()
        result = db.select(
            "chat_messages",
            "thread_id = ?",
            (thread_id,),
            ["role","content"],
            50
        )
        print("DSFSDFSDSDFSDFSDFSA",result)
        if result.success:
            return [{"role": msg['role'], "content": msg['content']} for msg in result.data]
        return []
    
    def delete_thread(self, thread_id: str, user_id: str) -> Dict:
        """حذف Thread"""
        db = get_gapgpt_db()
        thread = db.select_one(
            "chat_threads",
            "id = ? AND user_id = ?",
            (thread_id, user_id)
        )
        
        if thread.success and thread.data:
            # حذف پیام‌ها
            db.delete("chat_messages", "thread_id = ?", (thread_id,))
            # غیرفعال Thread
            db.update(
                "chat_threads",
                {"is_active": 0},
                "id = ?", (thread_id,)
            )
            return {"success": True, "message": "Thread حذف شد ✅"}
        
        return {"success": False, "message": "❌ Thread پیدا نشد"}
    
    def _update_user_state(self, user_id: str, current_thread: str = None):
        """به‌روزرسانی state کاربر"""
        db = get_gapgpt_db()
        state_result = db.select_one("user_states", "user_id = ?", (user_id,))
        
        state = {"current_thread": current_thread or "", "threads": []}
        if state_result.success and state_result.data:
            try:
                state["threads"] = json.loads(state_result.data.get('threads', '[]'))
                if current_thread and current_thread not in state["threads"]:
                    state["threads"].append(current_thread)
            except:
                pass
        
        db.insert_or_update("user_states", {
            "user_id": user_id,
            "current_thread": state["current_thread"],
            "threads": json.dumps(state["threads"]),
            "state_data": json.dumps(state)
        }, ["user_id"])

# === GLOBAL MANAGER ===
ai_manager = None

def init_ai_manager():
    """راه‌اندازی AI Manager"""
    global ai_manager
    db = get_gapgpt_db()
    _initialize_tables(db)
    if ai_manager is None:
        ai_manager = GapAIChatMulti()
    return ai_manager

def get_ai_manager():
    """دریافت AI Manager"""
    global ai_manager
    if ai_manager is None:
        init_ai_manager()
    return ai_manager

# === Helper Functions ===
def register_user(user_id: str, username: str = "", first_name: str = "") -> dict:
    """ثبت/به‌روزرسانی کاربر"""
    db = get_gapgpt_db()
    
    existing = db.select_one("users", "user_id = ?", (user_id,))
    
    if not existing.success or not existing.data:
        # کاربر جدید
        db.insert("users", {
            "user_id": user_id,
            "username": username,
            "first_name": first_name
        })
        
        return {"success": True, "new_user": True}
    else:
        # به‌روزرسانی last_seen
        db.update("users", 
                 {"last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                 "user_id = ?", (user_id,))
        return {"success": True, "new_user": False}