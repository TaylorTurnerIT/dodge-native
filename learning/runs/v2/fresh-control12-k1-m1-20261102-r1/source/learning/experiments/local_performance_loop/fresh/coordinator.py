"""Reuse the accepted coordinator with the separately gated fresh profile."""
import common
import runpy
runpy.run_path(str(common.CODE.parent/'continuation/coordinator.py'), run_name='__main__')
