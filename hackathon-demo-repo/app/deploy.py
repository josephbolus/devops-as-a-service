"""Deploy helper used by the CI/CD pipeline.

Expansion seed issue #10 (CI/CD + secrets, intentional — do not fix
in the scaffold): when the deploy token has expired, run_deploy()
crashes with an unhandled RuntimeError whose message embeds the
token itself — and the startup log line prints the token too — so
the secret lands in CI logs exactly on the failure path operators
read first. The clean failure type (DeployAuthError) exists but is
never raised.
"""


class DeployAuthError(Exception):
    """Clean authentication failure: the deploy token is expired/invalid."""


def run_deploy(token, verify, log):
    """Deploy using `token`; `verify(token)` -> bool; `log(msg)` records a line.

    Contract: a valid token deploys and returns "deployed". An
    expired/invalid token raises DeployAuthError with a generic
    message ("authentication failed: token expired or invalid").
    The token value must NEVER appear in any log line or in the
    exception message.
    """
    # BUG: the token itself is written to the log.
    log(f"starting deploy with token {token}")
    if not verify(token):
        # BUG: unhandled crash type, and the token leaks in its message.
        raise RuntimeError(f"deploy failed: token {token} rejected by upstream")
    log("deploy succeeded")
    return "deployed"
