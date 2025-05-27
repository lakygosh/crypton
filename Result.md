***1st order***
crypton    | 2025-05-27 01:22:07.114 | INFO     | __main__:run_paper_trade:368 - Checking for signal on BTC/USDT with DataFrame of shape (100, 10)
crypton    | 2025-05-27 01:22:07.124 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 96 - Time: 96, Close: 109373.0000, BBL: 108973.8332, RSI: 50.86
crypton    | 2025-05-27 01:22:07.124 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: False, RSI < 30: False
crypton    | 2025-05-27 01:22:07.124 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 97 - Time: 97, Close: 109305.6100, BBL: 109056.3899, RSI: 48.75
crypton    | 2025-05-27 01:22:07.125 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: False, RSI < 30: False
crypton    | 2025-05-27 01:22:07.125 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 98 - Time: 98, Close: 109212.5800, BBL: 109064.8866, RSI: 45.92
crypton    | 2025-05-27 01:22:07.125 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: False, RSI < 30: False
crypton    | 2025-05-27 01:22:07.125 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 99 - Time: 99, Close: 108968.3700, BBL: 109049.5729, RSI: 39.45
crypton    | 2025-05-27 01:22:07.125 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: False
crypton    | 2025-05-27 01:22:07.125 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 100 - Time: 100, Close: 108231.3400, BBL: 108725.3862, RSI: 27.06
crypton    | 2025-05-27 01:22:07.126 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: True
crypton    | 2025-05-27 01:22:07.127 | INFO     | crypton.strategy.mean_reversion:generate_signals:176 - Buy signals generated at rows:
crypton    | 2025-05-27 01:22:07.128 | INFO     | crypton.strategy.mean_reversion:generate_signals:178 -   Row 100: Close=108231.3400, BBL=108725.3862, RSI=27.06
crypton    | 2025-05-27 01:22:07.129 | INFO     | crypton.strategy.mean_reversion:generate_signals:198 - Generated signals for BTC/USDT: 1 BUY, 0 SELL
crypton    | 2025-05-27 01:22:07.129 | INFO     | crypton.strategy.mean_reversion:check_for_signal:263 - Found 1 BUY signals in the last 3 candles for BTC/USDT
crypton    | 2025-05-27 01:22:07.130 | INFO     | crypton.strategy.mean_reversion:check_for_signal:271 - Final signal determined for BTC/USDT: BUY at price 108231.34
crypton    | 2025-05-27 01:22:07.130 | INFO     | __main__:run_paper_trade:370 - Signal check result for BTC/USDT: SignalType.BUY
crypton    | 2025-05-27 01:22:07.130 | INFO     | __main__:run_paper_trade:374 - Processing BUY signal for BTC/USDT at price 108231.34
crypton    | 2025-05-27 01:22:07.692 | INFO     | crypton.execution.order_manager:calculate_position_size:255 - Calculated position size for BTC/USDT: 0.37883 units (≈41001.28 USDT)
crypton    | 2025-05-27 01:22:07.692 | INFO     | __main__:run_paper_trade:376 - Calculated position size for BTC/USDT: 0.37883 units (≈41001.2785322 USDT)
crypton    | 2025-05-27 01:22:07.944 | INFO     | crypton.execution.order_manager:place_market_order:299 - Placed BUY market order for 0.37883 BTC/USDT: 7874063
crypton    | 2025-05-27 01:22:08.734 | ERROR    | crypton.execution.order_manager:_place_sl_tp_orders:458 - API error placing SL/TP orders: APIError(code=-1013): Filter failure: LOT_SIZE
crypton    | 2025-05-27 01:22:08.734 | INFO     | __main__:run_paper_trade:384 - Order placement result: {'symbol': 'BTCUSDT', 'orderId': 7874063, 'orderListId': -1, 'clientOrderId': 'IOKPpAuPWLaNwrJYTp8NKh', 'transactTime': 1748308927812, 'price': '0.00000000', 'origQty': '0.37883000', 'executedQty': '0.37883000', 'origQuoteOrderQty': '0.00000000', 'cummulativeQuoteQty': '40971.59567690', 'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'MARKET', 'side': 'BUY', 'workingTime': 1748308927812, 'fills': [{'price': '108146.31000000', 'qty': '0.07199000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3375412}, {'price': '108146.32000000', 'qty': '0.07467000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3375413}, {'price': '108147.71000000', 'qty': '0.05109000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3375414}, {'price': '108147.72000000', 'qty': '0.07495000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3375415}, {'price': '108149.29000000', 'qty': '0.08133000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3375416}, {'price': '108231.34000000', 'qty': '0.02480000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3375417}], 'selfTradePreventionMode': 'EXPIRE_MAKER'}
crypton    | 2025-05-27 01:22:08.734 | INFO     | __main__:run_paper_trade:387 - Executed BUY order for BTC/USDT: 0.37883 @ 108231.34
crypton    | 2025-05-27 01:22:08.735 | INFO     | crypton.utils.notify:notify_trade_execution:31 - Executed BUY order for BTC/USDT: 0.37883 @ 108231.34


***2nd order***
crypton    | 2025-05-27 01:37:10.607 | INFO     | __main__:run_paper_trade:368 - Checking for signal on BTC/USDT with DataFrame of shape (100, 10)
crypton    | 2025-05-27 01:37:10.616 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 96 - Time: 96, Close: 109305.6100, BBL: 109056.3899, RSI: 48.74
crypton    | 2025-05-27 01:37:10.617 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: False, RSI < 30: False
crypton    | 2025-05-27 01:37:10.617 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 97 - Time: 97, Close: 109212.5800, BBL: 109064.8866, RSI: 45.91
crypton    | 2025-05-27 01:37:10.617 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: False, RSI < 30: False
crypton    | 2025-05-27 01:37:10.617 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 98 - Time: 98, Close: 108968.3700, BBL: 109049.5729, RSI: 39.44
crypton    | 2025-05-27 01:37:10.617 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: False
crypton    | 2025-05-27 01:37:10.618 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 99 - Time: 99, Close: 108231.3400, BBL: 108725.3862, RSI: 27.05
crypton    | 2025-05-27 01:37:10.618 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: True
crypton    | 2025-05-27 01:37:10.618 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 100 - Time: 100, Close: 108460.3200, BBL: 108579.7742, RSI: 33.99
crypton    | 2025-05-27 01:37:10.618 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: False
crypton    | 2025-05-27 01:37:10.620 | INFO     | crypton.strategy.mean_reversion:generate_signals:176 - Buy signals generated at rows:
crypton    | 2025-05-27 01:37:10.620 | INFO     | crypton.strategy.mean_reversion:generate_signals:178 -   Row 99: Close=108231.3400, BBL=108725.3862, RSI=27.05
crypton    | 2025-05-27 01:37:10.621 | INFO     | crypton.strategy.mean_reversion:generate_signals:198 - Generated signals for BTC/USDT: 1 BUY, 0 SELL
crypton    | 2025-05-27 01:37:10.621 | INFO     | crypton.strategy.mean_reversion:check_for_signal:263 - Found 1 BUY signals in the last 3 candles for BTC/USDT
crypton    | 2025-05-27 01:37:10.622 | INFO     | crypton.strategy.mean_reversion:check_for_signal:271 - Final signal determined for BTC/USDT: BUY at price 108460.32
crypton    | 2025-05-27 01:37:10.622 | INFO     | __main__:run_paper_trade:370 - Signal check result for BTC/USDT: SignalType.BUY
crypton    | 2025-05-27 01:37:10.622 | INFO     | __main__:run_paper_trade:374 - Processing BUY signal for BTC/USDT at price 108460.32
crypton    | 2025-05-27 01:37:11.201 | INFO     | crypton.execution.order_manager:calculate_position_size:255 - Calculated position size for BTC/USDT: 0.25224 units (≈27358.03 USDT)
crypton    | 2025-05-27 01:37:11.201 | INFO     | __main__:run_paper_trade:376 - Calculated position size for BTC/USDT: 0.25224 units (≈27358.031116800004 USDT)
crypton    | 2025-05-27 01:37:11.441 | INFO     | crypton.execution.order_manager:place_market_order:299 - Placed BUY market order for 0.25224 BTC/USDT: 7878018
crypton    | 2025-05-27 01:37:12.275 | ERROR    | crypton.execution.order_manager:_place_sl_tp_orders:458 - API error placing SL/TP orders: APIError(code=-2010): Account has insufficient balance for requested action.
crypton    | 2025-05-27 01:37:12.276 | INFO     | __main__:run_paper_trade:384 - Order placement result: {'symbol': 'BTCUSDT', 'orderId': 7878018, 'orderListId': -1, 'clientOrderId': 'HluHRXHdrnKAWdPfy1F5jL', 'transactTime': 1748309831321, 'price': '0.00000000', 'origQty': '0.25224000', 'executedQty': '0.25224000', 'origQuoteOrderQty': '0.00000000', 'cummulativeQuoteQty': '27382.14865640', 'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'MARKET', 'side': 'BUY', 'workingTime': 1748309831321, 'fills': [{'price': '108535.57000000', 'qty': '0.00078000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3377406}, {'price': '108535.67000000', 'qty': '0.00100000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3377407}, {'price': '108545.69000000', 'qty': '0.00013000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3377408}, {'price': '108556.00000000', 'qty': '0.06537000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3377409}, {'price': '108556.11000000', 'qty': '0.13731000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3377410}, {'price': '108556.12000000', 'qty': '0.04765000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3377411}], 'selfTradePreventionMode': 'EXPIRE_MAKER'}
crypton    | 2025-05-27 01:37:12.276 | INFO     | __main__:run_paper_trade:387 - Executed BUY order for BTC/USDT: 0.25224 @ 108460.32
crypton    | 2025-05-27 01:37:12.277 | INFO     | crypton.utils.notify:notify_trade_execution:31 - Executed BUY order for BTC/USDT: 0.25224 @ 108460.32


***3rd ORDER***
crypton    | 2025-05-27 01:52:13.942 | INFO     | __main__:run_paper_trade:368 - Checking for signal on BTC/USDT with DataFrame of shape (100, 10)
crypton    | 2025-05-27 01:52:13.949 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 96 - Time: 96, Close: 109212.5800, BBL: 109064.8866, RSI: 45.92
crypton    | 2025-05-27 01:52:13.950 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: False, RSI < 30: False
crypton    | 2025-05-27 01:52:13.950 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 97 - Time: 97, Close: 108968.3700, BBL: 109049.5729, RSI: 39.44
crypton    | 2025-05-27 01:52:13.950 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: False
crypton    | 2025-05-27 01:52:13.950 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 98 - Time: 98, Close: 108231.3400, BBL: 108725.3862, RSI: 27.05
crypton    | 2025-05-27 01:52:13.950 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: True
crypton    | 2025-05-27 01:52:13.950 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 99 - Time: 99, Close: 108460.3200, BBL: 108579.7742, RSI: 33.99
crypton    | 2025-05-27 01:52:13.950 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: False
crypton    | 2025-05-27 01:52:13.951 | INFO     | crypton.strategy.mean_reversion:generate_signals:166 - Candle 100 - Time: 100, Close: 108319.2600, BBL: 108422.2752, RSI: 31.97
crypton    | 2025-05-27 01:52:13.951 | INFO     | crypton.strategy.mean_reversion:generate_signals:167 -   Conditions: Price <= BBL: True, RSI < 30: False
crypton    | 2025-05-27 01:52:13.952 | INFO     | crypton.strategy.mean_reversion:generate_signals:176 - Buy signals generated at rows:
crypton    | 2025-05-27 01:52:13.953 | INFO     | crypton.strategy.mean_reversion:generate_signals:178 -   Row 98: Close=108231.3400, BBL=108725.3862, RSI=27.05
crypton    | 2025-05-27 01:52:13.953 | INFO     | crypton.strategy.mean_reversion:generate_signals:198 - Generated signals for BTC/USDT: 1 BUY, 0 SELL
crypton    | 2025-05-27 01:52:13.954 | INFO     | crypton.strategy.mean_reversion:check_for_signal:263 - Found 1 BUY signals in the last 3 candles for BTC/USDT
crypton    | 2025-05-27 01:52:13.954 | INFO     | crypton.strategy.mean_reversion:check_for_signal:271 - Final signal determined for BTC/USDT: BUY at price 108319.26
crypton    | 2025-05-27 01:52:13.954 | INFO     | __main__:run_paper_trade:370 - Signal check result for BTC/USDT: SignalType.BUY
crypton    | 2025-05-27 01:52:13.955 | INFO     | __main__:run_paper_trade:374 - Processing BUY signal for BTC/USDT at price 108319.26
crypton    | 2025-05-27 01:52:14.968 | INFO     | crypton.execution.order_manager:calculate_position_size:255 - Calculated position size for BTC/USDT: 0.16838 units (≈18238.80 USDT)
crypton    | 2025-05-27 01:52:14.969 | INFO     | __main__:run_paper_trade:376 - Calculated position size for BTC/USDT: 0.16838 units (≈18238.7969988 USDT)
crypton    | 2025-05-27 01:52:15.221 | INFO     | crypton.execution.order_manager:place_market_order:299 - Placed BUY market order for 0.16838 BTC/USDT: 7882107
crypton    | 2025-05-27 01:52:16.262 | ERROR    | crypton.execution.order_manager:_place_sl_tp_orders:458 - API error placing SL/TP orders: APIError(code=-2010): Account has insufficient balance for requested action.
crypton    | 2025-05-27 01:52:16.263 | INFO     | __main__:run_paper_trade:384 - Order placement result: {'symbol': 'BTCUSDT', 'orderId': 7882107, 'orderListId': -1, 'clientOrderId': 'XyegX1HH5MHjOSVrpvXJZn', 'transactTime': 1748310735089, 'price': '0.00000000', 'origQty': '0.16838000', 'executedQty': '0.16838000', 'origQuoteOrderQty': '0.00000000', 'cummulativeQuoteQty': '18249.69558400', 'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'MARKET', 'side': 'BUY', 'workingTime': 1748310735089, 'fills': [{'price': '108383.98000000', 'qty': '0.02506000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3378807}, {'price': '108383.98000000', 'qty': '0.09174000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3378808}, {'price': '108384.00000000', 'qty': '0.05158000', 'commission': '0.00000000', 'commissionAsset': 'BTC', 'tradeId': 3378809}], 'selfTradePreventionMode': 'EXPIRE_MAKER'}
crypton    | 2025-05-27 01:52:16.263 | INFO     | __main__:run_paper_trade:387 - Executed BUY order for BTC/USDT: 0.16838 @ 108319.26
crypton    | 2025-05-27 01:52:16.263 | INFO     | crypton.utils.notify:notify_trade_execution:31 - Executed BUY order for BTC/USDT: 0.16838 @ 108319.26