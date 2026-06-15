"""
工具函數模組
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple, Union, Callable
from functools import wraps
import time
import hashlib

from loguru import logger

# 配置日誌格式
logger.remove()  # 移除預設的日誌處理程序
logger.add(
    "logs/app_{time:YYYY-MM-DD}.log",
    rotation="500 MB",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    enqueue=True,
    backtrace=True,
    diagnose=True
)

def setup_logging(log_level: str = "INFO"):
    """配置日誌系統"""
    # 設置日誌級別
    logger.level(log_level.upper())
    
    # 添加控制台輸出
    logger.add(
        lambda msg: print(msg, end=""),
        level=log_level.upper(),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

def timeit(func: Callable) -> Callable:
    """計時裝飾器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logger.debug(f"函數 {func.__name__} 執行時間: {end_time - start_time:.4f} 秒")
        return result
    return wrapper

def ensure_dir(dir_path: Union[str, Path]) -> Path:
    """確保目錄存在，如果不存在則創建"""
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_file_hash(file_path: Union[str, Path], algorithm: str = 'sha256') -> str:
    """計算文件的哈希值"""
    hash_func = getattr(hashlib, algorithm.lower(), hashlib.sha256)
    buffer_size = 65536  # 64KB chunks
    
    with open(file_path, 'rb') as f:
        file_hash = hash_func()
        while chunk := f.read(buffer_size):
            file_hash.update(chunk)
    
    return file_hash.hexdigest()

def save_json(data: Any, file_path: Union[str, Path], indent: int = 2, ensure_ascii: bool = False) -> None:
    """保存數據到 JSON 文件"""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)

def load_json(file_path: Union[str, Path]) -> Any:
    """從 JSON 文件加載數據"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_file_size(file_path: Union[str, Path], unit: str = 'MB') -> float:
    """獲取文件大小，可選單位: B, KB, MB, GB"""
    size_bytes = os.path.getsize(file_path)
    units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3}
    return size_bytes / units.get(unit.upper(), 1)

def chunk_text(text: str, max_length: int = 1800, overlap: int = 100) -> List[str]:
    """
    將文本分割成多個重疊的塊
    
    Args:
        text: 要分割的文本
        max_length: 每個塊的最大長度
        overlap: 重疊的字符數
        
    Returns:
        List[str]: 分割後的文本塊
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + max_length
        
        # 如果剩餘文本不足一個塊，則直接取剩餘文本
        if end >= len(text):
            chunks.append(text[start:])
            break
        
        # 查找最近的句子邊界
        sentence_end = text.rfind('。', start, end)
        if sentence_end > start and (sentence_end - start) > (max_length // 2):
            end = sentence_end + 1  # 包括句號
        
        chunks.append(text[start:end])
        start = end - overlap  # 重疊部分
    
    return chunks

def mask_sensitive_info(text: str, mask_char: str = '*') -> str:
    """
    遮罩敏感信息（用於日誌記錄）
    
    Args:
        text: 要處理的文本
        mask_char: 用於遮罩的字符
        
    Returns:
        str: 遮罩後的文本
    """
    if not text:
        return text
    
    # 遮罩身份證號
    text = re.sub(r'[A-Z][12]\d{8}', lambda m: m.group()[0] + mask_char * (len(m.group()) - 4) + m.group()[-3:], text)
    
    # 遮罩手機號
    text = re.sub(r'\b09\d{2}[ -]?\d{3}[ -]?\d{3}\b', 
                 lambda m: m.group()[:4] + mask_char * (len(m.group()) - 4), text)
    
    # 遮罩電子郵件
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 
                 lambda m: m.group().split('@')[0][0] + mask_char * 3 + '@' + m.group().split('@')[1], text)
    
    return text
