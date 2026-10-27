"""Explicit synthetic Torch API; never imports actual Torch or MPS."""
class MPS:
    def __init__(self): self.seed=None
    def manual_seed(self,seed): self.seed=seed
    def get_rng_state(self): return ('mps:'+str(self.seed)).encode()
class Torch:
    def __init__(self): self.cpu=None; self.mps=MPS(); self.log=[]
    def manual_seed(self,seed): self.cpu=seed; self.log.append('cpu_seed')
    def get_rng_state(self): self.log.append('cpu_state'); return ('cpu:'+str(self.cpu)).encode()
def memory_sample(): return (1024,0)
