import polars as pl

from alm.asset import Bond as Bond
from alm.asset import Mortgage as Mortgage
from alm.asset import PrivateCredit as PrivateCredit
from alm.core import SAA as SAA
from alm.core import Block as Block
from alm.core import InterestRateSwap as InterestRateSwap
from alm.core import default_saa as default_saa
from alm.core import dollar_convexity as dollar_convexity
from alm.core import dv01 as dv01
from alm.core import immunize as immunize
from alm.core import irr as irr
from alm.core import spia_saa as spia_saa
from alm.core import term_saa as term_saa
from alm.liability import FIA as FIA
from alm.liability import SPIA as SPIA
from alm.liability import WL as WL
from alm.liability import Term as Term
from alm.read import get_credit_spreads as get_credit_spreads
from alm.read import get_spread as get_spread
from alm.read import get_treasury_rates as get_treasury_rates
from alm.read import read_credit_spread_indices as read_credit_spread_indices
from alm.read import update_credit_spreads as update_credit_spreads

pl.Config.set_tbl_cols(12)
