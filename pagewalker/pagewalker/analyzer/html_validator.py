import json
import re
import os
from os import path
from subprocess import Popen, PIPE
from pagewalker.utilities import filesystem_utils, error_utils, text_utils
from pagewalker.config import config


class HtmlValidator(object):
    def __init__(self):
        subdir = "port_%s" % config.chrome_debugging_port
        self.html_dir = path.join(config.validator_html_dir, subdir)
        self.db_conn = None
        self.queue_current_size = 0
        self.queue_max_size = 40
        self.vnu_version = ""

        if not config.validator_enabled:
            return

        self.vnu_version = self._check_vnu()

        stack_size = "-Xss%sk" % config.java_stack_size
        command_parts = [
            config.java_binary, stack_size,
            "-jar", config.validator_vnu_jar,
            "--format", "json",
            "--exit-zero-always"
        ]
        if config.validator_check_css:
            command_parts.append("--also-check-css")
        if not config.validator_show_warnings:
            command_parts.append("--errors-only")
        command_parts.append(self.html_dir)
        self.vnu_command_parts = command_parts

        filesystem_utils.clean_directory(self.html_dir)

    def _check_vnu(self):
        command_parts = [
            config.java_binary,
            "-jar", config.validator_vnu_jar,
            "--version"
        ]
        exec_result = self._exec_command(command_parts)
        if exec_result["code"] == 0:
            return exec_result["out"]
        else:
            error_utils.exit_with_message("v.Nu failed | %s" % exec_result["err"])

    def set_db_connection(self, db_connection):
        self.db_conn = db_connection

    def add_to_queue(self, page_id, html_raw, html_dom):
        if not config.validator_enabled:
            return
        self._save_html_to_file(page_id, "raw", html_raw)
        self._save_html_to_file(page_id, "dom", html_dom)
        self.queue_current_size += 2

    def validate_if_full_queue(self):
        if self.queue_current_size >= self.queue_max_size:
            self.validate()

    def validate(self):
        if not config.validator_enabled:
            return
        logs = self._execute_vnu()
        self._save_result_to_database(logs)

    def _execute_vnu(self):
        if self.queue_current_size == 0:
            return []
        print("[INFO] Running HTML validator on %s files" % self.queue_current_size)
        parsed = json.loads(self._get_vnu_json_result())
        logs = []
        for msg in parsed["messages"]:
            logs.append(self._parse_output_message(msg))
        filesystem_utils.clean_directory(self.html_dir)
        self.queue_current_size = 0
        return logs

    # option "exit-zero-always" was used, but still need to read from "stderr" not "stdout" (this is how v.Nu works)
    def _get_vnu_json_result(self):
        exec_result = self._exec_command(self.vnu_command_parts)
        if exec_result["code"] == 0:
            return exec_result["err"]
        else:
            msg = "v.Nu failed\n%s %s" % (exec_result["out"], exec_result["err"])
            error_utils.exit_with_message(msg)

    def _exec_command(self, command_parts):
        p = Popen(command_parts, stdout=PIPE, stderr=PIPE)
        (out, err) = p.communicate()
        return {
            "code": p.returncode,
            "out": text_utils.bytes_to_string(out),
            "err": text_utils.bytes_to_string(err)
        }

    def _save_result_to_database(self, logs):
        c = self.db_conn.cursor()
        for log in logs:
            message_id = self._get_message_id(log["is_error"], log["description"])
            extract_id = self._get_extract_id(log["extract_json"])
            c.execute(
                "INSERT INTO html_validator (page_id, message_id, extract_id, line, html_type) VALUES (?,?,?,?,?)",
                (log["page_id"], message_id, extract_id, log["line"], log["html_type_id"])
            )
        self.db_conn.commit()

    def _get_message_id(self, is_error, description):
        c = self.db_conn.cursor()
        c.execute(
            "SELECT id FROM html_validator_message WHERE is_error = ? AND description = ?", (is_error, description)
        )
        result = c.fetchone()
        if result:
            message_id = result[0]
        else:
            c.execute(
                "INSERT INTO html_validator_message (is_error, description) VALUES (?, ?)", (is_error, description)
            )
            message_id = c.lastrowid
        return message_id

    def _get_extract_id(self, extract_json):
        c = self.db_conn.cursor()
        c.execute(
            "SELECT id FROM html_validator_extract WHERE extract_json = ?", (extract_json,)
        )
        result = c.fetchone()
        if result:
            extract_id = result[0]
        else:
            c.execute(
                "INSERT INTO html_validator_extract (extract_json) VALUES (?)", (extract_json,)
            )
            extract_id = c.lastrowid
        return extract_id

    def _save_html_to_file(self, page_id, html_type, html):
        file_name = "code_%s_%s.html" % (page_id, html_type)
        file_path = os.path.join(self.html_dir, file_name)
        html = html.encode('utf-8')
        with open(file_path, "wb") as f:
            f.write(html)

    def _parse_output_message(self, msg):
        match = re.findall("code_(\d+)_(raw|dom).html", msg["url"])
        page_id = int(match[0][0])
        html_type_name = match[0][1]
        extract_parts = self._split_extract(msg)
        html_types = {
            "raw": 1,
            "dom": 2
        }
        return {
            "is_error": 1 if msg["type"] == "error" else 0,
            "line": msg["lastLine"] if "lastLine" in msg else 0,
            "extract_json": json.dumps(extract_parts),
            "description": self._replace_unicode_quotes(msg["message"]),
            "page_id": page_id,
            "html_type_id": html_types[html_type_name]
        }

    def _replace_unicode_quotes(self, text):
        open_quote = u'\u201c'
        close_quote = u'\u201d'
        return text.replace(open_quote, '{').replace(close_quote, '}')

    def _split_extract(self, msg):
        extract = msg["extract"] if "extract" in msg else ""
        start = msg["hiliteStart"] if "hiliteStart" in msg else 0
        end = start + msg["hiliteLength"] if "hiliteLength" in msg else 0
        part_before = extract[:start]
        part_hilite = extract[start:end]
        part_after = extract[end:]
        extract_parts = [part_before, part_hilite, part_after]
        return extract_parts

    def get_vnu_version(self):
        return self.vnu_version
