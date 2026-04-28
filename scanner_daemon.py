#!/usr/bin/env python3
"""
TradeMind Real-Time Scanner — 对标 Trade Ideas Holly AI
定时扫描选股 + 变化检测 + 微信推送 (via Hermes send_message)

用法:
  python scanner_daemon.py                          # 运行一次扫描
  python scanner_daemon.py --preset momentum         # 指定策略
  python scanner_daemon.py --all                     # 运行所有预设
  python scanner_daemon.py --daemon --interval 300   # 持续监控(每5分钟)
"""
import sys, os, json, time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
from screener import run_preset, PRESETS
from collections import defaultdict

SCAN_STATE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'scan_state.json')
REPORT_FILE = os.path.join(os.path.dirname(__file__), 'data', 'scan_history.jsonl')

# ============================================================
# Scan Engine
# ============================================================

def run_scan(preset_name='momentum', limit=20):
    """
    Run a single preset scan and return results.
    """
    try:
        result = run_preset(preset_name, limit=limit)
        stocks = result.get('results', [])
        # Clean internal fields
        for s in stocks:
            s.pop('_quick_score', None)
        return {
            'preset': preset_name,
            'timestamp': datetime.now().isoformat(),
            'total': len(stocks),
            'stocks': [
                {
                    'code': s.get('code', ''),
                    'name': s.get('name', ''),
                    'price': s.get('price', 0),
                    'change_pct': s.get('change_pct', 0),
                    'pe': s.get('pe', 0),
                    'turnover': s.get('turnover', 0),
                }
                for s in stocks
            ]
        }
    except Exception as e:
        return {'preset': preset_name, 'error': str(e), 'timestamp': datetime.now().isoformat()}


def load_previous_state():
    """Load previous scan state for diffing."""
    if os.path.exists(SCAN_STATE_FILE):
        try:
            with open(SCAN_STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}


def save_state(state):
    """Save current scan state."""
    os.makedirs(os.path.dirname(SCAN_STATE_FILE), exist_ok=True)
    with open(SCAN_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def diff_scans(previous, current, preset_name):
    """
    Compare two scans and identify new, removed, and changed stocks.
    """
    prev_codes = {s['code']: s for s in previous.get(preset_name, {}).get('stocks', [])}
    curr_codes = {s['code']: s for s in current.get('stocks', [])}
    
    new_stocks = []
    removed_stocks = []
    top_gainers = []
    
    for code, stock in curr_codes.items():
        if code not in prev_codes:
            new_stocks.append(stock)
            # Check if it's a top gainer
            if stock.get('change_pct', 0) > 3:
                top_gainers.append(stock)
    
    for code in prev_codes:
        if code not in curr_codes:
            removed_stocks.append(prev_codes[code])
    
    # Sort current by change_pct for top movers
    sorted_curr = sorted(curr_codes.values(), key=lambda x: x.get('change_pct', 0), reverse=True)
    top_movers = sorted_curr[:3]
    
    return {
        'new_count': len(new_stocks),
        'new_stocks': new_stocks[:10],
        'removed_count': len(removed_stocks),
        'top_gainers': top_gainers[:3],
        'top_movers': top_movers,
    }


def format_wechat_message(scan_result, diff=None, preset_name='momentum'):
    """
    Format a WeChat message with scan results.
    """
    preset_info = PRESETS.get(preset_name, {})
    preset_label = preset_info.get('name', preset_name)
    
    lines = []
    lines.append(f"📊 TradeMind 实时扫描 — {preset_label}")
    lines.append(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    lines.append("")
    
    if 'error' in scan_result:
        lines.append(f"❌ 扫描失败: {scan_result['error']}")
        return '\n'.join(lines)
    
    stocks = scan_result.get('stocks', [])
    lines.append(f"📈 结果: {scan_result['total']} 只股票")
    
    # Top stocks
    if stocks:
        lines.append("")
        lines.append("🏆 Top 5:")
        for i, s in enumerate(stocks[:5], 1):
            change = s.get('change_pct', 0)
            arrow = '🔴' if change > 0 else '🟢' if change < 0 else '⚪'
            lines.append(f"  {i}. {s['name']}({s['code']}) {arrow} {change:+.1f}% ¥{s.get('price',0):.2f}")
    
    # Diff
    if diff:
        if diff['new_count'] > 0:
            lines.append("")
            lines.append(f"🆕 新入选 ({diff['new_count']}):")
            for s in diff['new_stocks'][:5]:
                lines.append(f"  • {s['name']}({s['code']}) {s.get('change_pct',0):+.1f}%")
        
        if diff['top_gainers']:
            lines.append("")
            lines.append("🚀 异动关注:")
            for s in diff['top_gainers'][:3]:
                lines.append(f"  • {s['name']}({s['code']}) {s.get('change_pct',0):+.1f}%")
    
    lines.append("")
    lines.append(f"——— TradeMind Scanner · {datetime.now().strftime('%Y-%m-%d')}")
    
    return '\n'.join(lines)


def push_to_wechat(message):
    """
    Push message to WeChat via Hermes send_message tool.
    In standalone mode, writes to a file for Hermes to pick up.
    """
    # In agent environment, use the Hermes send_message function
    # We write to a delivery file and also try direct push
    delivery_file = os.path.join(os.path.dirname(__file__), 'data', '.pending_delivery.txt')
    
    try:
        # Try Hermes-style delivery
        from hermes_tools import send_message
        send_message(
            target="weixin:o9cq80-MeiCtKpT1896_DD315yb0@im.wechat",
            message=message
        )
        print(f"[Scanner] ✅ Pushed to WeChat")
    except ImportError:
        # Standalone mode — write to delivery file
        with open(delivery_file, 'w') as f:
            f.write(message)
        print(f"[Scanner] 📝 Written to {delivery_file} (Hermes will deliver)")


def save_history(scan_result, diff):
    """Append scan history to JSONL file."""
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    entry = {
        'timestamp': scan_result.get('timestamp'),
        'preset': scan_result.get('preset'),
        'total': scan_result.get('total', 0),
        'new_stocks': diff.get('new_count', 0) if diff else 0,
    }
    with open(REPORT_FILE, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='TradeMind Real-Time Scanner')
    parser.add_argument('--preset', default='momentum', help='Preset name to scan')
    parser.add_argument('--all', action='store_true', help='Scan all presets')
    parser.add_argument('--limit', type=int, default=20, help='Max results per preset')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=300, help='Scan interval in seconds')
    parser.add_argument('--no-push', action='store_true', help='Skip WeChat push')
    parser.add_argument('--list', action='store_true', help='List available presets')
    args = parser.parse_args()
    
    if args.list:
        print("Available presets:")
        for key, info in PRESETS.items():
            print(f"  {key:15s} — {info['name']}")
        return
    
    if args.daemon:
        print(f"[Scanner] Starting daemon mode — interval {args.interval}s")
        print(f"[Scanner] Presets: {'ALL' if args.all else args.preset}")
        
        while True:
            run_and_report(args)
            print(f"[Scanner] Sleeping {args.interval}s...")
            time.sleep(args.interval)
    else:
        run_and_report(args)


def run_and_report(args):
    presets_to_run = list(PRESETS.keys()) if args.all else [args.preset]
    
    all_results = {}
    prev_state = load_previous_state()
    
    for preset in presets_to_run:
        print(f"\n[Scanner] Running {preset}...")
        result = run_scan(preset, limit=args.limit)
        all_results[preset] = result
        
        if 'error' in result:
            print(f"[Scanner] ❌ {preset}: {result['error']}")
            continue
        
        print(f"[Scanner] ✅ {preset}: {result['total']} stocks found")
        
        # Diff with previous
        diff = diff_scans(prev_state, {preset: result}, preset)
        
        if diff['new_count'] > 0 or diff.get('top_gainers'):
            # Build message
            message = format_wechat_message(result, diff, preset)
            
            if not args.no_push:
                push_to_wechat(message)
            
            # Print summary
            for s in result['stocks'][:5]:
                print(f"  {s['name']}({s['code']}) {s.get('change_pct',0):+.1f}%")
            if diff['new_count'] > 0:
                print(f"  🆕 {diff['new_count']} new entries")
        else:
            print(f"  No changes detected")
        
        # Save history
        save_history(result, diff)
    
    # Save current state for next diff
    save_state(all_results)
    print(f"\n[Scanner] Done. State saved.")


if __name__ == '__main__':
    main()
