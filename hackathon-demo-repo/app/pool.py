"""Database connection pool.

Expansion seed issue #6 (database connections, intentional — do not
fix in the scaffold): connections are leaked on the error path. When
the work callable raises, run() never releases its connection, so
each failure permanently shrinks the pool until it exhausts and every
subsequent caller fails — under exactly the failure load where the
service most needs its connections back.
"""


class PoolExhausted(Exception):
    pass


class Connection:
    def __init__(self, ident):
        self.ident = ident
        self.closed = False


class ConnectionPool:
    def __init__(self, max_size=2):
        self.max_size = max_size
        self._idle = []
        self._in_use = 0
        self._next_id = 1

    def acquire(self):
        if self._idle:
            conn = self._idle.pop()
            self._in_use += 1
            return conn
        if self._in_use >= self.max_size:
            raise PoolExhausted("no connections available")
        conn = Connection(self._next_id)
        self._next_id += 1
        self._in_use += 1
        return conn

    def release(self, conn):
        self._in_use -= 1
        self._idle.append(conn)

    @property
    def in_use(self):
        return self._in_use

    def run(self, fn):
        """Run fn(conn) with a pooled connection and return its result.

        The connection must be released whether fn succeeds or raises;
        fn's exception must still propagate to the caller.
        """
        conn = self.acquire()
        result = fn(conn)
        # BUG: on the error path fn() raises before this line, so the
        # connection is never released — it leaks, one per failure.
        self.release(conn)
        return result
