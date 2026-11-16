"""The local app acting as one user, without signing in: for screenshots and checks of signed-in pages on the
developer's machine, with the real data and market data. Only by running this module
(`python -m shadowfolio.wiring.screenshot`): the configuration alone never turns it on, and it only listens on this
machine. It acts as SHADOWFOLIO_ACT_AS, or else the owner of the wallets made before sign-in."""

import os

import uvicorn

from shadowfolio.main import PORT_ENV, load_config, local_config
from shadowfolio.wiring.local import build_local_app

ACT_AS_ENV = "SHADOWFOLIO_ACT_AS"
LOOPBACK = "127.0.0.1"


def main() -> None:
    config = local_config(load_config())
    user = os.environ.get(ACT_AS_ENV) or config.existing_wallets_owner
    if not user:
        raise SystemExit(f"set {ACT_AS_ENV} (or SHADOWFOLIO_EXISTING_WALLETS_OWNER) to the user id to act as")
    port = int(os.environ.get(PORT_ENV) or 0)
    if not port:
        raise SystemExit(f"set {PORT_ENV}")
    uvicorn.run(build_local_app(config, acting_as=user), host=LOOPBACK, port=port)


if __name__ == "__main__":
    main()
