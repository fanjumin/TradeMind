import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.price import get_price_data, get_latest_price
from data.fund import get_fund_flow
from data.basic import get_basic_info, get_basic_score
from data.sector import get_top_sectors
from data.index import get_all_indices_status
from analysis.technical import get_trend, get_trend_detail
from analysis.scoring import get_score, get_signal, get_signal_cn


class StockAnalysisSkill:
    def analyze_stock(self, symbol):
        """Analyze a single stock, return JSON"""
        try:
            df = get_price_data(symbol)
            trend = get_trend(df)
            indicators = get_trend_detail(df)
            fund_total, fund_detail = get_fund_flow(symbol)
            basic = get_basic_info(symbol)
            basic_score, basic_reasons = get_basic_score(basic)
            score = get_score(trend, fund_total, basic_score, indicators)
            signal = get_signal(score)

            # Add fund flow info to result
            result = {
                "stock": symbol,
                "trend": trend,
                "main_force_net_inflow_5d": round(float(fund_total), 0),
                "main_force_today": round(float(fund_detail.get('main_force_today', 0)), 0),
                "basic_score": basic_score,
                "total_score": score,
                "signal": signal,
                "signal_cn": get_signal_cn(signal),
                "reasons": basic_reasons,
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def market_overview(self):
        """Market overview with all major indices"""
        try:
            indices = get_all_indices_status()
            return json.dumps({"indices": indices}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def sector_ranking(self, top_n=10):
        """Top gaining and losing sectors"""
        try:
            gainers, losers = get_top_sectors(top_n)
            return json.dumps({"gainers": gainers, "losers": losers}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    skill = StockAnalysisSkill()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--market":
            print(skill.market_overview())
        elif cmd == "--sectors":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            print(skill.sector_ranking(n))
        else:
            print(skill.analyze_stock(cmd))
    else:
        print("Usage: python skill.py <symbol>")
        print("       python skill.py --market")
        print("       python skill.py --sectors [N]")
