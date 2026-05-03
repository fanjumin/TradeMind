"""
TradeMind Strategy Marketplace — 策略市场
对标聚宽策略库/米筐策略研究平台
提供策略比较、基准测试、排名、导出功能
"""
import sys, os, json
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_enhanced import STRATEGY_REGISTRY, run_enhanced_backtest
from data.price import get_price_data


def list_strategies():
    """列出所有策略及元数据。Returns list of dicts."""
    result = []
    for key, info in STRATEGY_REGISTRY.items():
        result.append({
            'key': key,
            'name': info.get('name', key),
            'category': info.get('category', 'unknown'),
            'risk_level': info.get('risk_level', 'unknown'),
            'timeframe': info.get('timeframe', 'unknown'),
            'description': info.get('description', ''),
            'tags': info.get('tags', []),
            'default_params': info.get('default_params', {}),
        })
    return result


def get_strategy(name):
    """获取单个策略详情。"""
    if name not in STRATEGY_REGISTRY:
        return None
    info = STRATEGY_REGISTRY[name]
    return {
        'key': name,
        'name': info.get('name', name),
        'category': info.get('category', 'unknown'),
        'risk_level': info.get('risk_level', 'unknown'),
        'timeframe': info.get('timeframe', 'unknown'),
        'description': info.get('description', ''),
        'tags': info.get('tags', []),
        'default_params': info.get('default_params', {}),
    }


def compare_strategies(symbol, strategies=None, days=252):
    """对一只股票运行所有策略，返回对比排名表。
    
    Args:
        symbol: 股票代码如 '600519'
        strategies: 要比较的策略列表，None=全部
        days: 回测天数
    
    Returns:
        list of dicts, sorted by sharpe_ratio desc
    """
    # Get price data
    df = get_price_data(symbol, datalen=days)
    if df is None or df.empty:
        return {'error': f'无法获取 {symbol} 的价格数据', 'results': []}
    
    if strategies is None:
        strategies = list(STRATEGY_REGISTRY.keys())
    
    results = []
    for sname in strategies:
        if sname not in STRATEGY_REGISTRY:
            continue
        try:
            result = run_enhanced_backtest(df, sname, symbol=symbol)
            if result is not None and result.total_trades > 0:
                info = STRATEGY_REGISTRY[sname]
                results.append({
                    'key': sname,
                    'name': info.get('name', sname),
                    'category': info.get('category', '?'),
                    'risk_level': info.get('risk_level', '?'),
                    'sharpe_ratio': round(getattr(result, 'sharpe_ratio', 0) or 0, 3),
                    'sortino_ratio': round(getattr(result, 'sortino_ratio', 0) or 0, 3),
                    'total_return': round(getattr(result, 'total_return', 0) * 100, 2),
                    'annualized_return': round((getattr(result, 'annualized_return', 0) or 0) * 100, 2),
                    'max_drawdown': round((getattr(result, 'max_drawdown', 0) or 0) * 100, 2),
                    'win_rate': round(getattr(result, 'win_rate', 0) * 100, 1),
                    'total_trades': getattr(result, 'total_trades', 0),
                    'profit_factor': round(getattr(result, 'profit_factor', 0) or 0, 2),
                    'calmar_ratio': round(getattr(result, 'calmar_ratio', 0) or 0, 3),
                })
            else:
                results.append({
                    'key': sname,
                    'name': STRATEGY_REGISTRY[sname].get('name', sname),
                    'category': STRATEGY_REGISTRY[sname].get('category', '?'),
                    'error': '无交易信号或无数据',
                    'total_trades': 0,
                })
        except Exception as e:
            results.append({
                'key': sname,
                'name': STRATEGY_REGISTRY[sname].get('name', sname),
                'error': str(e)[:80],
                'total_trades': 0,
            })
    
    # Sort by sharpe
    results.sort(key=lambda x: x.get('sharpe_ratio', -999), reverse=True)
    
    return {
        'symbol': symbol,
        'days': days,
        'strategy_count': len(results),
        'results': results,
    }


def benchmark_strategies(symbols=None, strategies=None, days=252):
    """多标的基准测试，对每个标的运行所有策略，取平均排名。
    
    Args:
        symbols: 标的列表，默认 ['000001', '600519', '000858', '300750']
    """
    if symbols is None:
        symbols = ['000001', '600519', '000858', '300750']
    
    if strategies is None:
        strategies = list(STRATEGY_REGISTRY.keys())
    
    # Aggregate metrics across symbols
    agg = defaultdict(lambda: {
        'sharpe': [], 'return': [], 'drawdown': [], 'win_rate': [], 
        'trades': [], 'profit_factor': [], 'errors': 0, 'name': '', 'category': ''
    })
    
    for symbol in symbols:
        result = compare_strategies(symbol, strategies=strategies, days=days)
        for r in result.get('results', []):
            key = r['key']
            if r.get('error'):
                agg[key]['errors'] += 1
            else:
                agg[key]['sharpe'].append(r.get('sharpe_ratio', 0))
                agg[key]['return'].append(r.get('total_return', 0))
                agg[key]['drawdown'].append(r.get('max_drawdown', 0))
                agg[key]['win_rate'].append(r.get('win_rate', 0))
                agg[key]['trades'].append(r.get('total_trades', 0))
                agg[key]['profit_factor'].append(r.get('profit_factor', 0))
            agg[key]['name'] = r.get('name', key)
            agg[key]['category'] = r.get('category', '?')
    
    # Compute averages
    benchmark_results = []
    for key, data in agg.items():
        n = max(len(data['sharpe']), 1)
        benchmark_results.append({
            'key': key,
            'name': data['name'],
            'category': data['category'],
            'symbols_tested': len(symbols),
            'errors': data['errors'],
            'avg_sharpe': round(np.mean(data['sharpe']), 3) if data['sharpe'] else 0,
            'avg_return': round(np.mean(data['return']), 2),
            'avg_drawdown': round(np.mean(data['drawdown']), 2),
            'avg_win_rate': round(np.mean(data['win_rate']), 1),
            'avg_trades': round(np.mean(data['trades']), 1),
            'avg_profit_factor': round(np.mean(data['profit_factor']), 2),
        })
    
    benchmark_results.sort(key=lambda x: x['avg_sharpe'], reverse=True)
    
    return {
        'symbols': symbols,
        'strategy_count': len(benchmark_results),
        'results': benchmark_results,
    }


def rank_strategies(metric='sharpe_ratio', symbols=None):
    """全局策略排名（跨基准标的平均）。
    
    Args:
        metric: 排名指标 'sharpe_ratio'|'total_return'|'win_rate'|'profit_factor'
        symbols: 基准标的列表
    """
    bench = benchmark_strategies(symbols=symbols)
    
    metric_map = {
        'sharpe_ratio': 'avg_sharpe',
        'total_return': 'avg_return',
        'win_rate': 'avg_win_rate',
        'profit_factor': 'avg_profit_factor',
    }
    
    sort_key = metric_map.get(metric, 'avg_sharpe')
    bench['results'].sort(key=lambda x: x.get(sort_key, 0), reverse=True)
    
    return {
        'metric': metric,
        'ranking': bench['results'],
    }


def export_strategy(name):
    """导出策略配置为 JSON 格式。"""
    if name not in STRATEGY_REGISTRY:
        return {'error': f'策略 {name} 不存在'}
    
    info = STRATEGY_REGISTRY[name]
    return {
        'key': name,
        'name': info.get('name', name),
        'category': info.get('category', ''),
        'risk_level': info.get('risk_level', ''),
        'timeframe': info.get('timeframe', ''),
        'description': info.get('description', ''),
        'tags': info.get('tags', []),
        'params': info.get('default_params', {}),
        'version': '0.1.0',
    }


def categories_summary():
    """返回各类别策略统计。"""
    cats = defaultdict(list)
    for key, info in STRATEGY_REGISTRY.items():
        cat = info.get('category', 'unknown')
        cats[cat].append(key)
    
    return {
        'categories': [
            {
                'name': cat,
                'count': len(strategies),
                'strategies': strategies,
                'description': _cat_description(cat),
            }
            for cat, strategies in sorted(cats.items())
        ]
    }


def _cat_description(cat):
    descs = {
        'trend': '趋势跟踪类策略，适合趋势明显的市场，如单边上涨或下跌。',
        'momentum': '动量类策略，追涨杀跌，趋势强市中表现优异，震荡市易亏损。',
        'mean_reversion': '均值回归类策略，假设价格会回归均值，震荡市表现好。',
        'volume': '成交量类策略，关注量价关系，A股短线交易中信号质量较高。',
        'combined': '多指标组合策略，通过多重过滤降低假信号。',
    }
    return descs.get(cat, '其他策略类型。')


# CLI entry point
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='TradeMind Strategy Marketplace')
    parser.add_argument('--list', action='store_true', help='list all strategies')
    parser.add_argument('--compare', type=str, help='compare strategies on symbol')
    parser.add_argument('--benchmark', action='store_true', help='benchmark test')
    parser.add_argument('--rank', type=str, default='sharpe_ratio', help='ranking metric')
    parser.add_argument('--export', type=str, help='export strategy config')
    parser.add_argument('--days', type=int, default=252, help='backtest days')
    
    args = parser.parse_args()
    
    if args.list:
        strategies = list_strategies()
        sep = "=" * 80
        print()
        print(sep)
        print(f"  策略市场 — {len(strategies)} 个策略")
        print(sep)
        for s in strategies:
            print()
            print(f"  [{s['key']}] {s['name']}")
            print(f"  类别: {s['category']} | 风险: {s['risk_level']} | 周期: {s['timeframe']}")
            print(f"  描述: {s['description']}")
            print(f"  标签: {', '.join(s['tags'])}")
            if s['default_params']:
                print(f"  参数: {s['default_params']}")
    
    elif args.compare:
        result = compare_strategies(args.compare, days=args.days)
        if 'error' in result:
            print(f"Error: {result['error']}")
        else:
            sep = "=" * 80
            dash = "-" * 80
            print()
            print(sep)
            print(f"  策略比较 — {args.compare} (回测 {args.days} 天)")
            print(sep)
            header = f"  {'策略':<18s} {'类别':<14s} {'Sharpe':>7s} {'收益%':>8s} {'回撤%':>7s} {'胜率%':>6s} {'交易':>5s}"
            print(header)
            print("  " + dash)
            for r in result['results']:
                if r.get('error'):
                    print(f"  {r['key']:<16s} {'ERR: '+r['error']}")
                else:
                    line = f"  {r['key']:<16s} {r['category']:<14s} {r.get('sharpe_ratio',0):>7.2f} {r.get('total_return',0):>8.2f} {r.get('max_drawdown',0):>7.2f} {r.get('win_rate',0):>6.1f} {r.get('total_trades',0):>5d}"
                    print(line)
    
    elif args.benchmark:
        result = benchmark_strategies(days=args.days)
        sep = "=" * 80
        dash = "-" * 80
        print()
        print(sep)
        print(f"  策略基准测试 — 标的总数: {len(result['symbols'])}")
        print(f"  标的: {', '.join(result['symbols'])}")
        print(sep)
        header = f"  {'策略':<18s} {'类别':<14s} {'Avg Sharpe':>10s} {'Avg 收益%':>10s} {'Avg 回撤%':>10s} {'胜率%':>7s}"
        print(header)
        print("  " + dash)
        for r in result['results']:
            line = f"  {r['key']:<16s} {r['category']:<14s} {r['avg_sharpe']:>10.2f} {r['avg_return']:>10.2f} {r['avg_drawdown']:>10.2f} {r['avg_win_rate']:>7.1f}"
            print(line)
    
    elif args.export:
        config = export_strategy(args.export)
        if 'error' in config:
            print(f"Error: {config['error']}")
        else:
            print(json.dumps(config, ensure_ascii=False, indent=2))
    
    elif args.rank:
        result = rank_strategies(metric=args.rank)
        print(f"\n策略排名 (按 {args.rank}):")
        for i, r in enumerate(result['ranking'], 1):
            metric_val = r.get('avg_sharpe', 0)
            print(f"  {i}. {r['name']} — {metric_val:.3f}")
    
    else:
        parser.print_help()
