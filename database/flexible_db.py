"""
مدیریت پایگاه داده SQLite با قابلیت‌های پیشرفته و امنیتی
نسخه استاندارد‌سازی شده و توسعه‌یافته
"""
# db_center.py
import sqlite3
import logging
from typing import List, Dict, Any, Optional, Union, Tuple, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json


class LogLevel(Enum):
    """سطح‌های مختلف لاگ"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class QueryResult:
    """ساختار نتیجه کوئری"""
    success: bool
    data: Optional[List[Dict]] = None
    rowcount: int = 0
    lastrowid: Optional[int] = None
    message: str = ""
    error: Optional[str] = None


class DBError(Exception):
    """خطای سفارشی پایگاه داده"""
    pass


class DBConnectionError(DBError):
    """خطای اتصال به پایگاه داده"""
    pass


class DBQueryError(DBError):
    """خطای اجرای کوئری"""
    pass


class FlexibleDB:
    """
    یک دیتابیس کاملاً انعطاف‌پذیر با قابلیت‌های پیشرفته و امنیتی
    """
    
    # پیکربندی پیش‌فرض
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_ISOLATION_LEVEL = None  # استفاده از تنظیمات پیش‌فرض SQLite
    
    def __init__(
        self, 
        db_name: str = "my_database.db",
        timeout: float = DEFAULT_TIMEOUT,
        isolation_level: Optional[str] = DEFAULT_ISOLATION_LEVEL,
        enable_foreign_keys: bool = True,
        enable_wal_mode: bool = True,
        log_level: LogLevel = LogLevel.INFO,
        log_file: Optional[str] = "db_center.log"
    ):
        """
        راه‌اندازی دیتابیس با پیکربندی پیشرفته
        
        Parameters:
            db_name (str): نام فایل دیتابیس
            timeout (float): زمان انتظار برای قفل دیتابیس (ثانیه)
            isolation_level (str): سطح ایزوله‌سازی تراکنش‌ها
            enable_foreign_keys (bool): فعال‌سازی محدودیت‌های کلید خارجی
            enable_wal_mode (bool): فعال‌سازی حالت Write-Ahead Logging
            log_level (LogLevel): سطح لاگ‌گیری
            log_file (str): مسیر فایل لاگ
        """
        self.db_name = db_name
        self.timeout = timeout
        self.isolation_level = isolation_level
        self.enable_foreign_keys = enable_foreign_keys
        self.enable_wal_mode = enable_wal_mode
        self.connection = None
        
        # تنظیمات لاگ‌گیری
        self._setup_logging(log_level, log_file)
        
        # اتصال خودکار
        self.connect()
    
    def _setup_logging(self, log_level: LogLevel, log_file: Optional[str]):
        """تنظیم سیستم لاگ‌گیری"""
        self.logger = logging.getLogger(f"FlexibleDB_{self.db_name}")
        self.logger.setLevel(log_level.value)
        
        # فرمت لاگ
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler کنسول
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Handler فایل (در صورت وجود)
        if log_file:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def _quote_identifier(self, identifier: str) -> str:
        """
        حفاظت از شناسه‌ها در برابر تزریق SQL
        فقط برای نام‌های ساده استفاده شود
        """
        # حذف کاراکترهای خطرناک
        safe_chars = ''.join(c for c in identifier if c.isalnum() or c in ('_', '-', ' '))
        # حذف فضاهای اضافه
        safe_chars = safe_chars.strip()
        # قرار دادن در کوتیشن برای اطمینان
        return f'"{safe_chars}"'
    
    def _validate_table_name(self, table_name: str) -> bool:
        """اعتبارسنجی نام جدول"""
        if not table_name or not table_name.strip():
            return False
        # نام جدول باید فقط شامل حروف، اعداد و آندراسکور باشد
        return all(c.isalnum() or c == '_' for c in table_name)
    
    def connect(self) -> bool:
        """
        اتصال به دیتابیس با تنظیمات پیشرفته
        
        Returns:
            bool: True اگر موفق بود
        """
        try:
            self.connection = sqlite3.connect(
                self.db_name,
                timeout=self.timeout,
                isolation_level=self.isolation_level
            )
            
            # تنظیم factory برای بازگرداندن دیکشنری
            self.connection.row_factory = sqlite3.Row
            
            # فعال‌سازی ویژگی‌های پیشرفته
            cursor = self.connection.cursor()
            
            if self.enable_foreign_keys:
                cursor.execute("PRAGMA foreign_keys = ON")
                self.logger.debug("کلیدهای خارجی فعال شدند")
            
            if self.enable_wal_mode:
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
                self.logger.debug("حالت WAL فعال شد")
            
            # بهینه‌سازی‌های دیگر
            cursor.execute("PRAGMA cache_size = -2000")  # 2MB cache
            cursor.execute("PRAGMA temp_store = MEMORY")
            
            self.connection.commit()
            self.logger.info(f"اتصال به دیتابیس '{self.db_name}' برقرار شد")
            return True
            
        except sqlite3.Error as e:
            self.logger.error(f"خطا در اتصال به دیتابیس: {e}")
            raise DBConnectionError(f"خطا در اتصال به دیتابیس: {e}")
        except Exception as e:
            self.logger.error(f"خطای ناشناخته در اتصال: {e}")
            raise DBConnectionError(f"خطای ناشناخته در اتصال: {e}")
    
    @contextmanager
    def transaction(self):
        """
        مدیریت تراکنش با context manager
        Example:
            with db.transaction():
                db.insert("users", {"name": "علی"})
        """
        try:
            yield
            self.connection.commit()
            self.logger.debug("تراکنش با موفقیت انجام شد")
        except Exception as e:
            self.connection.rollback()
            self.logger.error(f"خطا در تراکنش، عملیات Rollback انجام شد: {e}")
            raise
    
    def execute_in_transaction(self, queries: List[Tuple[str, tuple]]) -> bool:
        """
        اجرای چندین کوئری در یک تراکنش
        
        Parameters:
            queries: لیستی از کوئری‌ها و پارامترهای آنها
            
        Returns:
            bool: True اگر همه کوئری‌ها موفق بودند
        """
        try:
            cursor = self.connection.cursor()
            for query, params in queries:
                cursor.execute(query, params)
            self.connection.commit()
            self.logger.info(f"{len(queries)} کوئری در تراکنش اجرا شدند")
            return True
        except Exception as e:
            self.connection.rollback()
            self.logger.error(f"خطا در اجرای تراکنش: {e}")
            return False
    
    def count(
        self, 
        table_name: str, 
        where_clause: str = None, 
        where_params: tuple = None,
        distinct_column: str = None
    ) -> int:
        """
        شمارش تعداد رکوردهای جدول
        
        Parameters:
            table_name (str): نام جدول
            where_clause (str): شرط WHERE
            where_params (tuple): پارامترهای شرط
            distinct_column (str): ستون برای شمارش مقادیر یکتا
            
        Returns:
            int: تعداد رکوردها
        """
        if not self._validate_table_name(table_name):
            self.logger.error(f"نام جدول نامعتبر: {table_name}")
            return 0
        
        try:
            cursor = self.connection.cursor()
            
            if distinct_column:
                query = f"SELECT COUNT(DISTINCT {self._quote_identifier(distinct_column)}) FROM {self._quote_identifier(table_name)}"
            else:
                query = f"SELECT COUNT(*) FROM {self._quote_identifier(table_name)}"
            
            if where_clause:
                query += f" WHERE {where_clause}"
            
            cursor.execute(query, where_params or ())
            result = cursor.fetchone()
            count = result[0] if result else 0
            
            self.logger.debug(f"شمارش جدول '{table_name}': {count} رکورد")
            return count
            
        except sqlite3.Error as e:
            self.logger.error(f"خطا در شمارش جدول {table_name}: {e}")
            return 0
        except Exception as e:
            self.logger.error(f"خطای ناشناخته در شمارش: {e}")
            return 0
    
    def create_table(
        self, 
        table_name: str, 
        columns_definition: str,
        if_not_exists: bool = True,
        additional_options: str = ""
    ) -> QueryResult:
        """
        ایجاد جدول با قابلیت‌های پیشرفته
        
        Parameters:
            table_name (str): نام جدول
            columns_definition (str): تعریف ستون‌ها
            if_not_exists (bool): فقط در صورت عدم وجود ایجاد کند
            additional_options (str): گزینه‌های اضافی (مثل WITHOUT ROWID)
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        if not self._validate_table_name(table_name):
            return QueryResult(
                success=False,
                message=f"نام جدول نامعتبر: {table_name}",
                error="INVALID_TABLE_NAME"
            )
        
        try:
            cursor = self.connection.cursor()
            
            if_exists = "IF NOT EXISTS " if if_not_exists else ""
            query = f"CREATE TABLE {if_exists}{self._quote_identifier(table_name)} ({columns_definition}) {additional_options}"
            
            cursor.execute(query)
            self.connection.commit()
            
            self.logger.info(f"جدول '{table_name}' ایجاد شد")
            return QueryResult(
                success=True,
                message=f"جدول '{table_name}' با موفقیت ایجاد شد",
                rowcount=0
            )
            
        except sqlite3.Error as e:
            error_msg = f"خطا در ایجاد جدول {table_name}: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def create_table_from_dict(
        self,
        table_name: str,
        schema: Dict[str, str],
        primary_key: Optional[List[str]] = None,
        foreign_keys: Optional[List[Dict]] = None,
        indexes: Optional[List[str]] = None
    ) -> QueryResult:
        """
        ایجاد جدول از دیکشنری اسکیما
        
        Parameters:
            table_name: نام جدول
            schema: دیکشنری {نام ستون: نوع داده}
            primary_key: لیست ستون‌های کلید اصلی
            foreign_keys: لیست دیکشنری‌های کلید خارجی
            indexes: لیست ستون‌های برای ایندکس
        """
        try:
            # ساخت تعریف ستون‌ها
            columns_def = []
            for column_name, column_type in schema.items():
                columns_def.append(f"{self._quote_identifier(column_name)} {column_type}")
            
            # اضافه کردن کلید اصلی
            if primary_key:
                pk_columns = ', '.join([self._quote_identifier(pk) for pk in primary_key])
                columns_def.append(f"PRIMARY KEY ({pk_columns})")
            
            # اضافه کردن کلیدهای خارجی
            if foreign_keys:
                for fk in foreign_keys:
                    fk_def = f"FOREIGN KEY ({self._quote_identifier(fk['column'])}) "
                    fk_def += f"REFERENCES {self._quote_identifier(fk['references_table'])}"
                    fk_def += f"({self._quote_identifier(fk['references_column'])})"
                    
                    if 'on_delete' in fk:
                        fk_def += f" ON DELETE {fk['on_delete']}"
                    if 'on_update' in fk:
                        fk_def += f" ON UPDATE {fk['on_update']}"
                    
                    columns_def.append(fk_def)
            
            columns_definition = ', '.join(columns_def)
            
            # ایجاد جدول
            result = self.create_table(table_name, columns_definition)
            
            # ایجاد ایندکس‌ها
            if result.success and indexes:
                for index_col in indexes:
                    index_name = f"idx_{table_name}_{index_col}"
                    self.execute_raw(
                        f"CREATE INDEX IF NOT EXISTS {self._quote_identifier(index_name)} "
                        f"ON {self._quote_identifier(table_name)} ({self._quote_identifier(index_col)})"
                    )
            
            return result
            
        except Exception as e:
            error_msg = f"خطا در ایجاد جدول از دیکشنری: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def insert(
        self, 
        table_name: str, 
        data: dict,
        ignore_on_conflict: bool = False,
        return_id: bool = False
    ) -> QueryResult:
        """
        درج داده با قابلیت‌های پیشرفته
        
        Parameters:
            table_name (str): نام جدول
            data (dict): داده‌ها
            ignore_on_conflict (bool): نادیده گرفتن در صورت تضاد
            return_id (bool): بازگرداندن ID رکورد درج شده
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        if not self._validate_table_name(table_name):
            return QueryResult(
                success=False,
                message=f"نام جدول نامعتبر: {table_name}",
                error="INVALID_TABLE_NAME"
            )
        
        if not data:
            return QueryResult(
                success=False,
                message="داده‌ای برای درج وجود ندارد",
                error="EMPTY_DATA"
            )
        
        try:
            cursor = self.connection.cursor()
            
            # اطمینان از امنیت نام ستون‌ها
            safe_columns = [self._quote_identifier(col) for col in data.keys()]
            columns = ", ".join(safe_columns)
            placeholders = ", ".join(["?" for _ in data])
            values = tuple(data.values())
            
            conflict_action = "OR IGNORE" if ignore_on_conflict else ""
            query = f"INSERT {conflict_action} INTO {self._quote_identifier(table_name)} ({columns}) VALUES ({placeholders})"
            
            cursor.execute(query, values)
            self.connection.commit()
            
            lastrowid = cursor.lastrowid if return_id else None
            rowcount = cursor.rowcount
            
            self.logger.debug(f"درج در جدول '{table_name}': {rowcount} رکورد")
            
            return QueryResult(
                success=True,
                message="درج با موفقیت انجام شد",
                rowcount=rowcount,
                lastrowid=lastrowid
            )
            
        except sqlite3.IntegrityError as e:
            error_msg = f"خطای یکتایی در درج داده: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error="INTEGRITY_ERROR"
            )
        except sqlite3.Error as e:
            error_msg = f"خطا در درج داده: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def batch_insert(
        self,
        table_name: str,
        data_list: List[dict],
        batch_size: int = 100,
        ignore_on_conflict: bool = False
    ) -> QueryResult:
        """
        درج دسته‌ای داده‌ها
        
        Parameters:
            table_name: نام جدول
            data_list: لیستی از دیکشنری‌های داده
            batch_size: اندازه هر دسته
            ignore_on_conflict: نادیده گرفتن در صورت تضاد
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        if not data_list:
            return QueryResult(
                success=False,
                message="لیست داده‌ها خالی است",
                error="EMPTY_DATA_LIST"
            )
        
        try:
            total_inserted = 0
            cursor = self.connection.cursor()
            
            # تقسیم داده‌ها به دسته‌های کوچک‌تر
            for i in range(0, len(data_list), batch_size):
                batch = data_list[i:i + batch_size]
                
                # استفاده از executemany برای کارایی بهتر
                columns = list(batch[0].keys())
                safe_columns = [self._quote_identifier(col) for col in columns]
                columns_str = ", ".join(safe_columns)
                placeholders = ", ".join(["?" for _ in columns])
                
                conflict_action = "OR IGNORE" if ignore_on_conflict else ""
                query = f"INSERT {conflict_action} INTO {self._quote_identifier(table_name)} ({columns_str}) VALUES ({placeholders})"
                
                # آماده کردن مقادیر
                values = [tuple(item[col] for col in columns) for item in batch]
                
                cursor.executemany(query, values)
                total_inserted += cursor.rowcount
            
            self.connection.commit()
            
            self.logger.info(f"درج دسته‌ای در '{table_name}': {total_inserted} از {len(data_list)} رکورد")
            
            return QueryResult(
                success=True,
                message=f"{total_inserted} رکورد با موفقیت درج شدند",
                rowcount=total_inserted
            )
            
        except Exception as e:
            self.connection.rollback()
            error_msg = f"خطا در درج دسته‌ای: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def select(
        self,
        table_name: str,
        where_clause: str = None,
        where_params: tuple = None,
        columns: Union[str, List[str]] = "*",
        limit: int = None,
        offset: int = None,
        order_by: str = None,
        distinct: bool = False,
        group_by: str = None,
        having: str = None,
        join: str = None,
        fetch_as_dict: bool = True
    ) -> QueryResult:
        """
        خواندن داده با قابلیت‌های پیشرفته
        
        Parameters:
            table_name: نام جدول
            where_clause: شرط WHERE
            where_params: پارامترهای شرط
            columns: ستون‌های مورد نیاز
            limit: محدود کردن تعداد نتایج
            offset: شروع از رکورد خاص
            order_by: مرتب‌سازی نتایج
            distinct: بازگرداندن مقادیر یکتا
            group_by: گروه‌بندی نتایج
            having: شرط روی گروه‌ها
            join: دستور JOIN
            fetch_as_dict: بازگرداندن نتایج به صورت دیکشنری
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        if not self._validate_table_name(table_name):
            return QueryResult(
                success=False,
                message=f"نام جدول نامعتبر: {table_name}",
                error="INVALID_TABLE_NAME"
            )
        
        try:
            cursor = self.connection.cursor()
            
            # پردازش ستون‌ها
            if isinstance(columns, list):
                safe_columns = [self._quote_identifier(col) for col in columns]
                columns_str = ", ".join(safe_columns)
            else:
                columns_str = columns
            
            # ساخت کوئری
            distinct_str = "DISTINCT " if distinct else ""
            query = f"SELECT {distinct_str}{columns_str} FROM {self._quote_identifier(table_name)}"
            
            if join:
                query += f" {join}"
            
            if where_clause:
                query += f" WHERE {where_clause}"
            
            if group_by:
                query += f" GROUP BY {group_by}"
            
            if having:
                query += f" HAVING {having}"
            
            if order_by:
                query += f" ORDER BY {order_by}"
            
            if limit is not None:
                query += f" LIMIT {limit}"
                if offset is not None:
                    query += f" OFFSET {offset}"
            
            # اجرای کوئری
            cursor.execute(query, where_params or ())
            
            if fetch_as_dict:
                results = [dict(row) for row in cursor.fetchall()]
            else:
                results = cursor.fetchall()
            
            self.logger.debug(f"انتخاب از جدول '{table_name}': {len(results)} رکورد یافت شد")
            if len(results)>0:
                return QueryResult(
                    success=True,
                    data=results,
                    rowcount=len(results),
                    message=f"{len(results)} رکورد یافت شد"
                )
            else:
                error_msg = f"خطا در خواندن از جدول {table_name}"
                return QueryResult(
                success=False,
                message=error_msg
            )
        except sqlite3.Error as e:
            error_msg = f"خطا در خواندن از جدول {table_name}: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def select_one(
        self,
        table_name: str,
        where_clause: str = None,
        where_params: tuple = None,
        columns: Union[str, List[str]] = "*",
        order_by: str = None
    ) -> QueryResult:
        """
        خواندن یک رکورد
        
        Returns:
            QueryResult: نتیجه عملیات
        """
        result = self.select(
            table_name=table_name,
            where_clause=where_clause,
            where_params=where_params,
            columns=columns,
            limit=1,
            order_by=order_by
        )
        
        if result.success and result.data:
            result.data = result.data[0]
        
        return result
    
    def update(
        self,
        table_name: str,
        set_data: dict,
        where_clause: str,
        where_params: tuple = None,
        limit: int = None
    ) -> QueryResult:
        """
        به‌روزرسانی داده
        
        Parameters:
            table_name: نام جدول
            set_data: داده‌های جدید
            where_clause: شرط WHERE
            where_params: پارامترهای شرط
            limit: محدود کردن تعداد رکوردهای به‌روز شده
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        if not self._validate_table_name(table_name):
            return QueryResult(
                success=False,
                message=f"نام جدول نامعتبر: {table_name}",
                error="INVALID_TABLE_NAME"
            )
        
        if not set_data:
            return QueryResult(
                success=False,
                message="داده‌ای برای به‌روزرسانی وجود ندارد",
                error="EMPTY_DATA"
            )
        
        try:
            cursor = self.connection.cursor()
            
            # ساخت بخش SET با امنیت
            safe_keys = [self._quote_identifier(key) for key in set_data.keys()]
            set_clause = ", ".join([f"{key} = ?" for key in safe_keys])
            values = tuple(set_data.values()) + (where_params or ())
            
            # ساخت کوئری
            limit_str = f" LIMIT {limit}" if limit is not None else ""
            query = f"UPDATE {self._quote_identifier(table_name)} SET {set_clause} WHERE {where_clause}{limit_str}"
            
            cursor.execute(query, values)
            self.connection.commit()
            
            rowcount = cursor.rowcount
            
            self.logger.debug(f"به‌روزرسانی جدول '{table_name}': {rowcount} رکورد به‌روز شد")
            
            return QueryResult(
                success=True,
                rowcount=rowcount,
                message=f"{rowcount} رکورد به‌روزرسانی شد"
            )
            
        except sqlite3.Error as e:
            error_msg = f"خطا در به‌روزرسانی جدول {table_name}: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def delete(
        self,
        table_name: str,
        where_clause: str,
        where_params: tuple = None,
        limit: int = None
    ) -> QueryResult:
        """
        حذف داده
        
        Parameters:
            table_name: نام جدول
            where_clause: شرط WHERE
            where_params: پارامترهای شرط
            limit: محدود کردن تعداد رکوردهای حذف شده
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        if not self._validate_table_name(table_name):
            return QueryResult(
                success=False,
                message=f"نام جدول نامعتبر: {table_name}",
                error="INVALID_TABLE_NAME"
            )
        
        try:
            cursor = self.connection.cursor()
            
            # ساخت کوئری
            limit_str = f" LIMIT {limit}" if limit is not None else ""
            query = f"DELETE FROM {self._quote_identifier(table_name)} WHERE {where_clause}{limit_str}"
            
            cursor.execute(query, where_params or ())
            self.connection.commit()
            
            rowcount = cursor.rowcount
            
            self.logger.debug(f"حذف از جدول '{table_name}': {rowcount} رکورد حذف شد")
            
            return QueryResult(
                success=True,
                rowcount=rowcount,
                message=f"{rowcount} رکورد حذف شد"
            )
            
        except sqlite3.Error as e:
            error_msg = f"خطا در حذف از جدول {table_name}: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def execute_raw(
        self,
        sql_query: str,
        params: tuple = None,
        fetch: bool = True
    ) -> QueryResult:
        """
        اجرای کوئری خام
        
        Parameters:
            sql_query: کوئری SQL
            params: پارامترهای کوئری
            fetch: آیا نتیجه را برگرداند؟
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql_query, params or ())
            
            is_select = sql_query.strip().upper().startswith("SELECT")
            
            if is_select and fetch:
                results = [dict(row) for row in cursor.fetchall()]
                rowcount = len(results)
            else:
                results = None
                rowcount = cursor.rowcount
            
            if not is_select:
                self.connection.commit()
            
            return QueryResult(
                success=True,
                data=results,
                rowcount=rowcount,
                lastrowid=cursor.lastrowid
            )
            
        except sqlite3.Error as e:
            error_msg = f"خطا در اجرای کوئری: {e}"
            self.logger.error(f"{error_msg}\nکوئری: {sql_query}")
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def insert_or_update(
        self,
        table_name: str,
        data: dict,
        conflict_columns: List[str] = None,
        update_columns: List[str] = None
    ) -> QueryResult:
        """
        درج یا به‌روزرسانی با استفاده از UPSERT
        
        Parameters:
            table_name: نام جدول
            data: داده‌ها
            conflict_columns: ستون‌های تشخیص تضاد
            update_columns: ستون‌هایی که باید به‌روزرسانی شوند (همه به جز کلید)
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        if not data:
            return QueryResult(
                success=False,
                message="داده‌ای برای درج/به‌روزرسانی وجود ندارد",
                error="EMPTY_DATA"
            )
        
        # اگر ستون‌های تضد مشخص نشده‌اند، از اولین کلید استفاده کن
        if not conflict_columns:
            if 'id' in data:
                conflict_columns = ['id']
            elif 'chat_id' in data:
                conflict_columns = ['chat_id']
            else:
                # استفاده از اولین ستون
                conflict_columns = [list(data.keys())[0]]
                self.logger.warning(f"ستون‌های تضد به طور خودکار انتخاب شدند: {conflict_columns}")
        
        try:
            cursor = self.connection.cursor()
            
            # آماده‌سازی ستون‌ها و مقادیر
            columns = list(data.keys())
            safe_columns = [self._quote_identifier(col) for col in columns]
            columns_str = ", ".join(safe_columns)
            placeholders = ", ".join(["?" for _ in columns])
            values = tuple(data.values())
            
            # ساخت بخش ON CONFLICT
            safe_conflict_columns = [self._quote_identifier(col) for col in conflict_columns]
            conflict_columns_str = ", ".join(safe_conflict_columns)
            
            # ساخت بخش SET برای به‌روزرسانی
            if update_columns:
                # فقط ستون‌های مشخص شده
                update_cols = [col for col in update_columns if col in data and col not in conflict_columns]
            else:
                # همه ستون‌ها به جز کلید
                update_cols = [col for col in columns if col not in conflict_columns]
            
            if update_cols:
                set_clause = ", ".join([f"{self._quote_identifier(col)} = excluded.{self._quote_identifier(col)}" 
                                       for col in update_cols])
            else:
                # اگر ستونی برای به‌روزرسانی نبود، یک ستون را به‌روز کن
                first_col = [col for col in columns if col not in conflict_columns][0] if len(columns) > len(conflict_columns) else conflict_columns[0]
                set_clause = f"{self._quote_identifier(first_col)} = excluded.{self._quote_identifier(first_col)}"
            
            # ساخت کوئری نهایی
            query = f"""
            INSERT INTO {self._quote_identifier(table_name)} ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT({conflict_columns_str})
            DO UPDATE SET {set_clause}
            """
            
            cursor.execute(query, values)
            self.connection.commit()
            
            return QueryResult(
                success=True,
                rowcount=cursor.rowcount,
                lastrowid=cursor.lastrowid,
                message="عملیات درج/به‌روزرسانی با موفقیت انجام شد"
            )
            
        except sqlite3.IntegrityError as e:
            error_msg = f"خطای یکتایی در درج/به‌روزرسانی: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error="INTEGRITY_ERROR"
            )
        except sqlite3.Error as e:
            error_msg = f"خطا در درج/به‌روزرسانی: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def table_exists(self, table_name: str) -> bool:
        """
        بررسی وجود جدول
        
        Returns:
            bool: True اگر جدول وجود دارد
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            self.logger.error(f"خطا در بررسی وجود جدول: {e}")
            return False
    
    def get_table_info(self, table_name: str) -> QueryResult:
        """
        دریافت اطلاعات ساختار جدول
        
        Returns:
            QueryResult: اطلاعات جدول
        """
        if not self.table_exists(table_name):
            return QueryResult(
                success=False,
                message=f"جدول '{table_name}' وجود ندارد",
                error="TABLE_NOT_FOUND"
            )
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(f"PRAGMA table_info({self._quote_identifier(table_name)})")
            
            columns = [dict(row) for row in cursor.fetchall()]
            
            # دریافت ایندکس‌ها
            cursor.execute(f"PRAGMA index_list({self._quote_identifier(table_name)})")
            indexes = [dict(row) for row in cursor.fetchall()]
            
            # دریافت اطلاعات کلید خارجی
            cursor.execute(f"PRAGMA foreign_key_list({self._quote_identifier(table_name)})")
            foreign_keys = [dict(row) for row in cursor.fetchall()]
            
            return QueryResult(
                success=True,
                data={'columns': columns,'indexes': indexes,'foreign_keys': foreign_keys},
                message=f"اطلاعات جدول '{table_name}' دریافت شد"
            )
            
        except Exception as e:
            error_msg = f"خطا در دریافت اطلاعات جدول: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def get_all_tables(self) -> List[str]:
        """
        دریافت لیست همه جداول
        
        Returns:
            List[str]: لیست نام جداول
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            return tables
        except Exception as e:
            self.logger.error(f"خطا در دریافت لیست جداول: {e}")
            return []
    
    def drop_table(self, table_name: str, if_exists: bool = True) -> QueryResult:
        """
        حذف جدول
        
        Parameters:
            table_name: نام جدول
            if_exists: فقط در صورت وجود حذف کند
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        try:
            cursor = self.connection.cursor()
            
            if_exists_str = "IF EXISTS " if if_exists else ""
            query = f"DROP TABLE {if_exists_str}{self._quote_identifier(table_name)}"
            
            cursor.execute(query)
            self.connection.commit()
            
            self.logger.info(f"جدول '{table_name}' حذف شد")
            
            return QueryResult(
                success=True,
                message=f"جدول '{table_name}' با موفقیت حذف شد"
            )
            
        except Exception as e:
            error_msg = f"خطا در حذف جدول {table_name}: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def vacuum(self) -> QueryResult:
        """
        بهینه‌سازی پایگاه داده
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("VACUUM")
            self.connection.commit()
            
            self.logger.info("بهینه‌سازی پایگاه داده انجام شد")
            
            return QueryResult(
                success=True,
                message="بهینه‌سازی پایگاه داده با موفقیت انجام شد"
            )
            
        except Exception as e:
            error_msg = f"خطا در بهینه‌سازی پایگاه داده: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def backup(self, backup_path: str) -> QueryResult:
        """
        پشتیبان‌گیری از پایگاه داده
        
        Parameters:
            backup_path: مسیر فایل پشتیبان
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        try:
            # اتصال به دیتابیس مقصد
            backup_conn = sqlite3.connect(backup_path)
            self.connection.backup(backup_conn)
            backup_conn.close()
            
            self.logger.info(f"پشتیبان‌گیری در '{backup_path}' انجام شد")
            
            return QueryResult(
                success=True,
                message="پشتیبان‌گیری با موفقیت انجام شد"
            )
            
        except Exception as e:
            error_msg = f"خطا در پشتیبان‌گیری: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def export_to_json(self, table_name: str, file_path: str) -> QueryResult:
        """
        خروجی JSON از جدول
        
        Parameters:
            table_name: نام جدول
            file_path: مسیر فایل خروجی
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        try:
            # دریافت داده‌ها
            result = self.select(table_name)
            if not result.success:
                return result
            
            # ذخیره به JSON
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result.data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"داده‌های جدول '{table_name}' به '{file_path}' صادر شد")
            
            return QueryResult(
                success=True,
                message=f"داده‌های جدول '{table_name}' با موفقیت صادر شد"
            )
            
        except Exception as e:
            error_msg = f"خطا در صادر کردن داده‌ها: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def import_from_json(self, table_name: str, file_path: str, clear_table: bool = False) -> QueryResult:
        """
        وارد کردن داده از JSON
        
        Parameters:
            table_name: نام جدول
            file_path: مسیر فایل ورودی
            clear_table: پاک کردن جدول قبل از وارد کردن
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        try:
            # خواندن داده‌ها
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                return QueryResult(
                    success=False,
                    message="فرمت فایل JSON نامعتبر است (باید لیست باشد)",
                    error="INVALID_JSON_FORMAT"
                )
            
            # پاک کردن جدول (در صورت نیاز)
            if clear_table and self.table_exists(table_name):
                self.execute_raw(f"DELETE FROM {self._quote_identifier(table_name)}")
            
            # درج داده‌ها
            result = self.batch_insert(table_name, data)
            
            if result.success:
                self.logger.info(f"داده‌ها از '{file_path}' به جدول '{table_name}' وارد شدند")
            
            return result
            
        except Exception as e:
            error_msg = f"خطا در وارد کردن داده‌ها: {e}"
            self.logger.error(error_msg)
            return QueryResult(
                success=False,
                message=error_msg,
                error=str(e)
            )
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار پایگاه داده
        
        Returns:
            Dict: آمار پایگاه داده
        """
        try:
            cursor = self.connection.cursor()
            
            stats = {}
            
            # تعداد جداول
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            stats['table_count'] = cursor.fetchone()[0]
            
            # لیست جداول و تعداد رکوردهای هر کدام
            tables = self.get_all_tables()
            table_stats = {}
            total_records = 0
            
            for table in tables:
                count = self.count(table)
                table_stats[table] = count
                total_records += count
            
            stats['tables'] = table_stats
            stats['total_records'] = total_records
            
            # اندازه دیتابیس
            import os
            if os.path.exists(self.db_name):
                stats['database_size'] = os.path.getsize(self.db_name)
            
            # اطلاعات دیگر
            cursor.execute("PRAGMA page_count")
            stats['page_count'] = cursor.fetchone()[0]
            
            cursor.execute("PRAGMA page_size")
            stats['page_size'] = cursor.fetchone()[0]
            
            stats['database_name'] = self.db_name
            stats['connection_time'] = datetime.now().isoformat()
            
            return stats
            
        except Exception as e:
            self.logger.error(f"خطا در دریافت آمار پایگاه داده: {e}")
            return {}
    
    def close(self):
        """بستن اتصال به پایگاه داده"""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.logger.info("اتصال به پایگاه داده بسته شد")
    
    def __enter__(self):
        """برای استفاده با with"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """بستن خودکار با with"""
        self.close()
    
    def __del__(self):
        """تخریب‌کننده"""
        self.close()
    def get_user_campaigns(self, chat_id: str, limit: int = 10) -> QueryResult:
        """
        دریافت کمپین‌های یک کاربر خاص
        
        Parameters:
            chat_id: شناسه چت کاربر
            limit: تعداد رکوردهای بازگشتی
            
        Returns:
            QueryResult: نتیجه عملیات
        """
        return self.select(
            table_name="campaigns",
            where_clause="chat_id = ?",
            where_params=(chat_id,),
            order_by="created_at DESC",
            limit=limit
        )

# تابع کمکی برای استفاده سریع
def create_db_manager(
    db_name: str = "my_database.db",
    **kwargs
) -> FlexibleDB:
    """
    ایجاد سریع یک مدیر پایگاه داده
    
    Parameters:
        db_name: نام فایل دیتابیس
        **kwargs: سایر پارامترهای FlexibleDB
        
    Returns:
        FlexibleDB: نمونه مدیر پایگاه داده
    """
    return FlexibleDB(db_name, **kwargs)

