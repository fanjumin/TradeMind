import json
from data.index import get_index_price_data, get_index_fund_flow
from analysis.technical import get_trend
from analysis.scoring import get_score, get_signal

class IndexAnalysisSkill:
    def __init__(self):
        pass

    def analyze_index(self, index_code: str) -> str:
        """
        Analyze index and return JSON result
        """
        try:
            df = get_index_price_data(index_code)
            trend = get_trend(df)
            fund_flow = get_index_fund_flow(index_code)
            fund_str = 'positive' if fund_flow > 0 else 'negative'
            # 指数暂不做基本面分析，basic_good 设为 True
            score = get_score(trend, fund_flow, True)
            signal = get_signal(score)
            reasons = []
            if trend == 'uptrend':
                reasons.append("趋势向上")
            if fund_flow > 0:
                reasons.append("资金流入")
            result = {
                "index": index_code,
                "trend": trend,
                "fund_flow": fund_str,
                "score": score,
                "signal": signal,
                "reasons": reasons
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
