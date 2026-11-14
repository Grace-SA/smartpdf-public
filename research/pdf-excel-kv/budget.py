"""Persistent-cache accounting, NOT a total-process memory limit."""
import threading
MAX_CACHE_BYTES=32*1024*1024
class CacheBudget:
    def __init__(self,limit=MAX_CACHE_BYTES):
        if type(limit)is not int or not 0<=limit<=MAX_CACHE_BYTES:raise ValueError('Unsupported cache budget')
        self.limit=limit;self.used=0;self.peak=0;self._lock=threading.Lock()
    def reserve(self,n):
        if type(n)is not int or not 0<=n<=8*1024*1024:raise ValueError('Unsupported entry size')
        with self._lock:
            if self.used+n>self.limit:return False
            self.used+=n;self.peak=max(self.peak,self.used);return True
    def release(self,n):
        with self._lock:
            if type(n)is not int or not 0<=n<=self.used:raise ValueError('Invalid reservation release')
            self.used-=n
class CacheDeclined(Exception):pass
