"""Stub minimal FastAPI untuk smoke test tanpa internet. BUKAN untuk produksi."""
class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail); self.status_code = status_code; self.detail = detail
def Query(default=None, *a, **kw): return None if default is ... else default
def Body(default=None, *a, **kw): return None if default is ... else default
def Depends(fn=None): return fn
def Security(fn=None): return None
class Request: pass
class FastAPI:
    def __init__(self, **kw): self.routes = {}; self.handlers = {}; self.meta = kw
    def _reg(self, method, path, kw):
        def deco(fn):
            self.routes[(method, path)] = fn; return fn
        return deco
    def get(self, path, **kw): return self._reg("GET", path, kw)
    def post(self, path, **kw): return self._reg("POST", path, kw)
    def add_middleware(self, cls, **kw): self.middleware = cls
    def exception_handler(self, exc):
        def deco(fn): self.handlers[exc] = fn; return fn
        return deco
