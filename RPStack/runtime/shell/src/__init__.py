from .registry import EXT_COMMANDS_FILE, ExternalCommand, registercommand
from . import sh

def run():
    sh.start()
