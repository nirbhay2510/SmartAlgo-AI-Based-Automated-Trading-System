import sqlite3
import time
import datetime
import yfinance as yf
from strategy_logic import signal_map

DB_PATH = 'database/db.sqlite3'


def get_db():
    return sqlite3.connect(DB_PATH)


MAX_HOLD_MINUTES = 15
STOP_LOSS_PERCENT = 2   # 2% loss


def run_engine():
    print("Trading Engine Started...")

    while True:
        try:
            conn = get_db()

            # =========================
            # 1. CHECK ACTIVE SESSION
            # =========================
            session = conn.execute("""
                SELECT username, stock, capital 
                FROM trading_session 
                WHERE is_active=1
            """).fetchone()

            if not session:
                print("⏸ Waiting for active session...")
                conn.close()
                time.sleep(10)
                continue

            username, stock, capital = session
            print(f"\nChecking {stock}...")

            # =========================
            # 2. FETCH MARKET DATA
            # =========================
            data = yf.download(
                stock + ".NS",
                period="1d",
                interval="5m",
                progress=False
            )

            if data.empty:
                print("No market data")
                conn.close()
                time.sleep(10)
                continue

            price = float(data['Close'].iloc[-1].item())
            now = datetime.datetime.now()

            # =========================
            # 3. CHECK OPEN TRADES
            # =========================
            open_trades = conn.execute("""
                SELECT id, quantity, buy_price, buy_time, strategy, ai_model
                FROM portfolio
                WHERE username=? AND stock=?
                ORDER BY buy_time ASC
            """, (username, stock)).fetchall()

            # =========================
            # 4. AUTO EXIT + STOP LOSS
            # =========================
            for trade in open_trades:
                trade_id, qty, buy_price, buy_time, strat, ai = trade

                buy_datetime = datetime.datetime.strptime(buy_time, "%Y-%m-%d %H:%M:%S")
                holding_minutes = (now - buy_datetime).total_seconds() / 60

                profit = (price - buy_price) * qty
                profit_percent = ((price - buy_price) / buy_price) * 100

                # ⏱ TIME EXIT
                if holding_minutes >= MAX_HOLD_MINUTES:

                    conn.execute("""
                        INSERT INTO trade_history
                        (username, stock, quantity, buy_price, sell_price, profit, buy_time, sell_time, strategy, ai_model)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        username, stock, qty, buy_price, price, profit,
                        buy_time,
                        now.strftime("%Y-%m-%d %H:%M:%S"),
                        strat, ai
                    ))

                    conn.execute("DELETE FROM portfolio WHERE id=?", (trade_id,))
                    print(f"⏱ AUTO EXIT | Profit: ₹{round(profit,2)}")

                
                elif profit_percent <= -STOP_LOSS_PERCENT:

                    conn.execute("""
                        INSERT INTO trade_history
                        (username, stock, quantity, buy_price, sell_price, profit, buy_time, sell_time, strategy, ai_model)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        username, stock, qty, buy_price, price, profit,
                        buy_time,
                        now.strftime("%Y-%m-%d %H:%M:%S"),
                        strat, ai
                    ))

                    conn.execute("DELETE FROM portfolio WHERE id=?", (trade_id,))
                    print(f"STOP LOSS HIT | Loss: ₹{round(profit,2)}")

            conn.commit()

            # =========================
            # 5. APPLY STRATEGY
            # =========================
            strategy_name = list(signal_map.keys())[0]
            signal = signal_map[strategy_name](data)

            print(f"📊 Signal: {signal}")

            if signal == "HOLD":
                conn.close()
                time.sleep(30)
                continue

            # =========================
            # 6. CHECK IF TRADE ALREADY EXISTS
            # =========================
            has_position = len(open_trades) > 0

            # =========================
            # 7. BUY LOGIC (ONLY IF NO TRADE)
            # =========================
            if signal == "BUY" and not has_position:

                quantity = int(capital / price)

                if quantity <= 0:
                    print("Not enough capital")
                    conn.close()
                    time.sleep(30)
                    continue

                conn.execute(
                    """INSERT INTO portfolio 
                    (username, stock, quantity, buy_price, buy_time, strategy, ai_model) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (username, stock, quantity, price,
                     now.strftime("%Y-%m-%d %H:%M:%S"),
                     strategy_name, "AUTO")
                )

                conn.commit()
                conn.close()

                print(f"BUY EXECUTED | Qty: {quantity} | Price: ₹{price}")
                time.sleep(30)
                continue

            # =========================
            # 8. SELL LOGIC (ONLY IF TRADE EXISTS)
            # =========================
            elif signal == "SELL" and has_position:

                total_profit = 0

                for trade in open_trades:
                    trade_id, qty, buy_price, buy_time, strat, ai = trade

                    profit = (price - buy_price) * qty
                    total_profit += profit

                    conn.execute("""
                        INSERT INTO trade_history
                        (username, stock, quantity, buy_price, sell_price, profit, buy_time, sell_time, strategy, ai_model)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        username, stock, qty, buy_price, price, profit,
                        buy_time,
                        now.strftime("%Y-%m-%d %H:%M:%S"),
                        strat, ai
                    ))

                    conn.execute("DELETE FROM portfolio WHERE id=?", (trade_id,))

                conn.commit()
                conn.close()

                print(f"SELL EXECUTED | Profit: ₹{round(total_profit,2)}")
                time.sleep(30)
                continue

            else:
                print("⚖ No action taken")

            conn.close()

        except Exception as e:
            print("Error:", e)

        time.sleep(30)


if __name__ == "__main__":
    run_engine()