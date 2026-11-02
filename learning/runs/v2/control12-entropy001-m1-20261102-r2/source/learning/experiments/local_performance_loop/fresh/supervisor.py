"""Reuse accepted worker ownership, resource checks and sleep prevention."""
import common
import runpy
runpy.run_path(str(common.CODE.parent/'continuation/supervisor.py'), run_name='__main__')
