"""Regenerate the README headline chart and numbers from the shared lecture book.

Writes ``images/surplus_vs_shock.png`` (surplus after a parallel rate shock, unhedged
versus DV01 and convexity matched with two swaps) and prints the Markdown table the README
quotes, so every number in the README comes from the same code as the deck.  No network.
"""

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from alm.examples import lecture_book  # noqa: E402
from alm.utils import get_project_root  # noqa: E402

SHOCKS_BP = list(range(-200, 201, 25))


def money(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def main() -> int:
    book = lecture_book()
    hedge = book.two_swap_hedge()
    base = book.discount_rate
    unhedged = [book.surplus(base + bp / 10_000) for bp in SHOCKS_BP]
    hedged = [book.surplus(base + bp / 10_000, hedge) for bp in SHOCKS_BP]

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.plot(SHOCKS_BP, [v / 1e6 for v in unhedged], color="#dc2626", lw=2.2, label="Unhedged")
    ax.plot(
        SHOCKS_BP,
        [v / 1e6 for v in hedged],
        color="#2563eb",
        lw=2.2,
        label="DV01 and convexity matched (5Y and 10Y swaps)",
    )
    ax.axhline(0, color="#6b7280", lw=0.8)
    ax.axvline(0, color="#6b7280", lw=0.8, ls=":")
    ax.set_xlabel("Parallel shift in Treasury rates (bp)")
    ax.set_ylabel("Surplus ($ millions)")
    ax.set_title("Surplus of a $50M sample insurer after a rate shock")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()

    out = get_project_root() / "images" / "surplus_vs_shock.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    print(f"wrote {out.relative_to(get_project_root()).as_posix()}")

    sheet = book.balance_sheet()
    index = {bp: i for i, bp in enumerate(SHOCKS_BP)}
    rows = [
        ("Assets (at purchase price)", money(sheet["assets"])),
        ("Liabilities (whole life, SPIA, FIA reserves)", money(sheet["liabilities"])),
        ("Surplus", money(sheet["surplus"])),
        ("Surplus after -100 bp, unhedged", money(unhedged[index[-100]])),
        ("Surplus after +100 bp, unhedged", money(unhedged[index[100]])),
        ("Surplus after -100 bp, hedged", money(hedged[index[-100]])),
        ("Surplus after +100 bp, hedged", money(hedged[index[100]])),
        (
            "Hedge: 5Y and 10Y swap notionals",
            f"{money(hedge.notionals[0])} and {money(hedge.notionals[1])} "
            f"(gross {money(hedge.gross_notional)})",
        ),
    ]
    print()
    print("| Measure | Value |")
    print("|---|---|")
    for label, value in rows:
        print(f"| {label} | {value} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
