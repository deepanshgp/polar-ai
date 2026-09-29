from datetime import date,timedelta
import numpy as np, pytest
from app.evaluation.splits import TimeSplit,assert_no_leakage,make_time_split
from app.evaluation.metrics import mae,rmse,skill_vs
from app.evaluation.regimes import regime_masks

def test_leakage_test_rejects_deliberately_leaky_split():
    s=TimeSplit((date(2020,1,1),date(2020,1,10)),(date(2020,1,11),date(2020,1,20)),(date(2020,1,21),date(2020,1,30)),0)
    with pytest.raises(AssertionError): assert_no_leakage(s,1)
def test_metrics_and_regimes():
    assert mae([1,2],[2,2])==.5; assert rmse([1,2],[2,2])>.4; assert skill_vs(2,1)==.5
    assert set(regime_masks(np.array([[0,.2,.9]])).keys())=={'open','mizt','pack','consolidated'}
