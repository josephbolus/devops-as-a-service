"""Service configuration loader.

Expansion seed issue #4 (configuration drift, intentional — do not fix
in the scaffold): environment overrides are documented to win over the
built-in defaults, so staging can run with staging settings. In
practice the defaults are applied LAST, so every environment override
is silently discarded and production-shaped defaults leak into every
environment.
"""

DEFAULTS = {
    "host": "prod.internal",
    "port": 8080,
    "debug": False,
    "workers": 4,
}

# Environment variable -> (config key, converter)
ENV_KEYS = {
    "APP_HOST": ("host", str),
    "APP_PORT": ("port", int),
    "APP_DEBUG": ("debug", lambda v: v.lower() in ("1", "true", "yes")),
    "APP_WORKERS": ("workers", int),
}


def env_overrides(env):
    """Translate the known APP_* variables in `env` into config values."""
    out = {}
    for var, (key, conv) in ENV_KEYS.items():
        if var in env:
            out[key] = conv(env[var])
    return out


def load_config(env=None):
    """Effective config: APP_* env overrides must win over DEFAULTS."""
    env = {} if env is None else env
    # BUG: defaults are spread last, so they overwrite every override —
    # the exact opposite of the documented precedence.
    return {**env_overrides(env), **DEFAULTS}
