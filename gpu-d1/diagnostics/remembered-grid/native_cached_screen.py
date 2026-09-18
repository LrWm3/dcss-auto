"""Matched short DAgger screen; cached inference, fresh differentiable replay."""
import sys
import native_remedies as runner
from native_cached_exact import make_model,CachedInference

if __name__=='__main__':
    old_make=runner.make_model
    runner.make_model=lambda exact=False: make_model() if exact else old_make(False)
    runner.StaticInference=lambda execution,**kwargs: CachedInference(execution.model)
    sys.argv+=['--arm','exact']
    runner.main()
