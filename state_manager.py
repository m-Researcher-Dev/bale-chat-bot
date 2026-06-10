"""
GapGPT State Manager - کاملاً مستقل
بدون وابستگی به gapgpt_db.py
"""

import json
import uuid
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from gap_ai import get_gapgpt_db, get_ai_manager  # ✅ فقط gap_ai

class GapGPTStateManager:
    """مدیر حالت پیشرفته - Cache + DB"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timeout = 300  # 5 دقیقه
    
    def get(self, user_id: str) -> Dict[str, Any]:
        """دریافت State کاربر (Cache + DB)"""
        # Cache Check
        if user_id in self._cache:
            cached = self._cache[user_id]
            if datetime.now() - cached['timestamp'] < timedelta(seconds=self._cache_timeout):
                return cached['data']
        
        db = get_gapgpt_db()
        state_result = db.select_one("user_states", "user_id = ?", (user_id,))
        
        state = {
            'user_id': user_id,
            'current_thread': '',
            'threads': [],
            'message_quota': {'has_quota': True, 'remaining': 10},
            'thread_count': 0,
            'thread_limit': 5,
            'plan': {'plan_name': 'رایگان'},
            'timestamp': datetime.now()
        }
        
        if state_result.success and state_result.data:
            try:
                state['current_thread'] = state_result.data.get('current_thread', '')
                state['threads'] = json.loads(state_result.data.get('threads', '[]'))
            except:
                pass
        
        # شمارش Threadها
        state['thread_count'] = db.count("chat_threads", "user_id = ? AND is_active = 1", (user_id,))
        state['thread_limit'] = 5  # Freemium
        
        # Cache
        self._cache[user_id] = {'data': state, 'timestamp': datetime.now()}
        return state
    
    def set(self, user_id: str, state: Dict[str, Any]) -> bool:
        """ذخیره State"""
        try:
            state["timestamp"] = state["timestamp"].isoformat()
        except:pass
        db = get_gapgpt_db()
        success = db.insert_or_update("user_states", {
            "user_id": user_id,
            "current_thread": state.get('current_thread', ''),
            "threads": json.dumps(state.get('threads', [])),
            "state_data": json.dumps(state)
        }, ["user_id"])
        
        if success:
            self._cache.pop(user_id, None)  # Cache Invalidate
        return success 
    
    def switch_thread(self, user_id: str, thread_id: str) -> Tuple[bool, str]:
        """تغییر Thread فعال"""
        state = self.get(user_id)
        threads = state['threads']
        
        if thread_id in threads:
            state['current_thread'] = thread_id
            success = self.set(user_id, state)
            return success, f"✅ Thread تغییر یافت: `{thread_id[:8]}`"
        return False, "❌ Thread یافت نشد"
    
    def create_thread(self, user_id: str, title: str = "چت جدید") -> Dict[str, Any]:
        """ایجاد Thread """
        state = self.get(user_id)
        
        if state['thread_count'] >= state['thread_limit']:
            return {"success": False, "error": "حداکثر تعداد Thread"}
        
        ai = get_ai_manager()
        result = ai.create_thread(user_id, title)
        
        if result["success"]:
            thread_id = result["thread_id"]
            state['threads'].append(thread_id)
            state['current_thread'] = thread_id
            self.set(user_id, state)
            return result
        
        return result
    
    def list_threads(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """لیست Threadها"""
        ai = get_ai_manager()
        threads = ai.get_user_threads(user_id, limit)
  
        state = self.get(user_id)
        thread_list = []
        
        for thread in threads:
            stats = ai._get_thread_stats(thread['id'])
            thread_list.append({
                **thread,
                **stats,
                'is_active': thread['id'] == state['current_thread']
            })
        
        return thread_list
    
    def check_quota(self, user_id: str) -> Dict[str, Any]:
        """بررسی سهمیه"""
        state = self.get(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        
        db = get_gapgpt_db()
        used = db.count(
            "chat_messages", 
            "thread_id IN (SELECT id FROM chat_threads WHERE user_id = ?) AND DATE(created_at) = ?",
            (user_id, today)
        )
        
        limit = 10  # Freemium
        remaining = max(0, limit - used)
        
        return {
            'message_quota': {
                'has_quota': remaining > 0,
                'used': used,
                'limit': limit,
                'remaining': remaining
            },
            'thread_quota': {
                'current': state['thread_count'],
                'limit': state['thread_limit'],
                'has_quota': state['thread_count'] < state['thread_limit']
            }
        }
    
    def clear_cache(self, user_id: str = None):
        """پاک Cache"""
        if user_id:
            self._cache.pop(user_id, None)
        else:
            self._cache.clear()

# === GLOBAL ===
state_manager = GapGPTStateManager()

# === Export ===
__all__ = ['state_manager', 'GapGPTStateManager']