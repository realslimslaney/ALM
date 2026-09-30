"""Refresh assumptions/credit_spreads.csv from the latest FRED credit-spread data.

This is the only code path that writes the credit-spread table. Reports and the demo script
read the committed snapshot, so a render never touches FRED. Run with ``just refresh-spreads``
(needs ``FRED_API_KEY`` in ``.env``) and commit the CSV change on its own.
"""

import logging
import sys

import coloredlogs

from alm.read import update_credit_spreads


def main() -> int:
    coloredlogs.install(level="INFO", fmt="%(asctime)s %(levelname)s %(message)s")
    table = update_credit_spreads()
    logging.getLogger(__name__).info("credit spread table (bps):\n%s", table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
