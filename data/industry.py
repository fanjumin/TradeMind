"""
Industry comparison module.
Compares a stock's PE/PB/ROE against its industry peers.
"""
import baostock as bs
import requests
import os
import sys


def _bs_symbol(symbol):
    clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
    if clean.startswith('6'):
        return 'sh.' + clean
    elif clean.startswith(('0', '3')):
        return 'sz.' + clean
    elif clean.startswith(('8', '4')):
        return 'bj.' + clean
    else:
        return 'sz.' + clean


def get_industry_comparison(symbol):
    """
    Get industry comparison data.
    Returns dict with:
      - industry: industry name
      - pe: stock PE
      - pe_percentile: PE percentile in industry (0-100)
      - pe_median: industry median PE
      - pb: stock PB
      - pb_percentile: PB percentile in industry
      - pb_median: industry median PB
      - roe: stock ROE
      - roe_percentile: ROE percentile in industry
      - peer_count: number of peers
      - top_peers: list of top 5 peers by PE ranking
    """
    result = {
        'industry': '',
        'pe': 0, 'pe_percentile': 0, 'pe_median': 0,
        'pb': 0, 'pb_percentile': 0, 'pb_median': 0,
        'roe': 0, 'roe_percentile': 0,
        'peer_count': 0,
        'top_peers': [],
    }

    devnull = open(os.devnull, 'w')
    from contextlib import redirect_stdout

    try:
        with redirect_stdout(devnull):
            lg = bs.login()
            if lg.error_code != '0':
                return result

            # Get target stock's industry
            bs_sym = _bs_symbol(symbol)
            rs = bs.query_stock_industry(code=bs_sym)
            target_industry = None
            while rs.error_code == '0' and rs.next():
                row = rs.get_row_data()
                target_industry = row[3]  # industry column
                break

            if not target_industry:
                return result

            result['industry'] = target_industry

            # Get all stocks in this industry
            rs2 = bs.query_stock_industry()
            industry_stocks = []
            while rs2.error_code == '0' and rs2.next():
                row = rs2.get_row_data()
                if row[3] == target_industry:
                    code_val = row[1]
                    name = row[2]
                    # Convert to tencent format
                    clean = code_val.replace('sh.', '').replace('sz.', '')
                    if code_val.startswith('sh'):
                        tencent_code = 'sh' + clean
                    else:
                        tencent_code = 'sz' + clean
                    industry_stocks.append({
                        'bs_code': code_val,
                        'name': name,
                        'tencent_code': tencent_code,
                    })

            result['peer_count'] = len(industry_stocks)

            # Batch query Tencent for PE/PB
            # Tencent limits ~60 per request, split into chunks
            all_pe_data = []
            for i in range(0, len(industry_stocks), 50):
                chunk = industry_stocks[i:i+50]
                codes = [s['tencent_code'] for s in chunk]
                url = "http://qt.gtimg.cn/q=" + ",".join(codes)
                r = requests.get(url, timeout=10)
                text = r.text.strip().strip(';')

                for line in text.split(';'):
                    if '~' not in line:
                        continue
                    parts = line.split('~')
                    if len(parts) > 47:
                        name = parts[1]
                        price = float(parts[3]) if parts[3] else 0
                        pe = float(parts[39]) if len(parts) > 39 and parts[39] else 0
                        net_asset = float(parts[47]) if len(parts) > 47 and parts[47] else 0
                        pb = price / net_asset if net_asset > 0 else 0
                        all_pe_data.append({'name': name, 'pe': pe, 'pb': pb, 'price': price})

            if not all_pe_data:
                return result

            # Filter valid data
            valid_pe = [d for d in all_pe_data if d['pe'] > 0]
            valid_pb = [d for d in all_pe_data if d['pb'] > 0]

            if valid_pe:
                pe_list = sorted([d['pe'] for d in valid_pe])
                result['pe_median'] = pe_list[len(pe_list) // 2]

            if valid_pb:
                pb_list = sorted([d['pb'] for d in valid_pb])
                result['pb_median'] = pb_list[len(pb_list) // 2]

            # Find target stock
            target_name = None
            for s in industry_stocks:
                if s['bs_code'] == bs_sym:
                    target_name = s['name']
                    break

            if target_name:
                target_data = [d for d in all_pe_data if target_name in d['name']]
                if target_data:
                    td = target_data[0]
                    result['pe'] = td['pe']
                    result['pb'] = td['pb']

                    if valid_pe:
                        pe_rank = sum(1 for d in valid_pe if d['pe'] < td['pe'])
                        result['pe_percentile'] = round(pe_rank / len(valid_pe) * 100, 1)

                    if valid_pb:
                        pb_rank = sum(1 for d in valid_pb if d['pb'] < td['pb'])
                        result['pb_percentile'] = round(pb_rank / len(valid_pb) * 100, 1)

            # Top peers (cheapest by PE)
            top_peers = sorted(valid_pe, key=lambda x: x['pe'])[:5]
            result['top_peers'] = [
                {'name': p['name'], 'pe': round(p['pe'], 1), 'pb': round(p['pb'], 2)}
                for p in top_peers
            ]

            bs.logout()
    except Exception:
        pass
    finally:
        try:
            bs.logout()
        except:
            pass
        devnull.close()

    return result
