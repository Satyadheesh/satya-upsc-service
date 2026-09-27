"""sqlite-backed stand-in for libsql_client (sync API subset) used by tests."""
import sqlite3
import types

DBS = {}


class Statement:
    def __init__(self, sql, args=()):
        self.sql, self.args = sql, list(args)


class _Client:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, args=()):
        cur = self.conn.execute(sql, list(args))
        rows = cur.fetchall()
        self.conn.commit()
        return types.SimpleNamespace(rows=rows)

    def batch(self, stmts):
        for s in stmts:
            self.conn.execute(s.sql, s.args)
        self.conn.commit()

    def close(self):
        pass


def create_client_sync(url, auth_token=None):
    return _Client(DBS[url])
