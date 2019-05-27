from os import path
import sqlite3
from . import general, javascript, console, page, validator, resource, links
from pagewalker.config import config


class DatabaseReader(object):
    def __init__(self):
        db_file = path.join(config.current_data_dir, "data.db")
        conn = sqlite3.connect(db_file)
        self.conn = conn
        self.general_data = general.DatabaseGeneral(conn)
        self.page_data = page.DatabasePage(conn)
        self.resource_data = resource.DatabaseResource(conn)
        self.javascript_data = javascript.DatabaseJavascript(conn)
        self.console_data = console.DatabaseConsole(conn)
        self.links_data = links.DatabaseLinks(conn)
        self.validator_data = validator.DatabaseValidator(conn)

    def close(self):
        self.conn.close()
