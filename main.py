import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skill import StockAnalysisSkill
from report import generate_report


def main():
    skill = StockAnalysisSkill()
    
    if len(sys.argv) < 2:
        print("TradeMind - A-Stock Analysis Tool")
        print("Usage:")
        print("  python main.py <symbol>          Analyze stock (e.g., 000001, 600519)")
        print("  python main.py --market          Market overview (all major indices)")
        print("  python main.py --sectors [N]     Top N sector ranking (default: 10)")
        print("  python main.py --report <symbol> Full analysis report")
        return
    
    cmd = sys.argv[1]
    
    if cmd == '--market':
        result = skill.market_overview()
        print(result)
    elif cmd == '--sectors':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        result = skill.sector_ranking(n)
        print(result)
    elif cmd == '--report':
        if len(sys.argv) < 3:
            print("Usage: python main.py --report <symbol>")
            return
        report = generate_report(sys.argv[2])
        print(report)
    else:
        result = skill.analyze_stock(cmd)
        print(result)


if __name__ == "__main__":
    main()
