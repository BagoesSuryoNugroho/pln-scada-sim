def Field(default=None, *a, **kw): return default
class BaseModel:
    def __init__(self, **kw):
        anns = {}
        for c in reversed(type(self).__mro__):
            anns.update(getattr(c, "__annotations__", {}))
        for k in anns:
            default = getattr(type(self), k, None)
            if k not in kw and default is Ellipsis:
                raise ValueError(f"field {k} wajib")
            setattr(self, k, kw.get(k, default))
    def model_dump(self):
        return {k: getattr(self, k) for k in type(self).__annotations__}
