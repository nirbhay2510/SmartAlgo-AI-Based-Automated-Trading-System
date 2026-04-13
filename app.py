from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, datetime
import yfinance as yf
import pandas as pd
from urllib.parse import quote
from strategy_logic import strategy_map, signal_map
from ai_models import get_ai_signal, MODEL_BUILDERS

app = Flask(__name__)
app.secret_key = "secret123"

DB_PATH       = 'database/db.sqlite3'
HOLD_MINUTES  = 15
STOP_LOSS_PCT = 2.0
TARGET_PCT    = 3.0
STOCK_LIST    = ["NSEI","RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK"]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def flatten(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy(); df.columns = df.columns.get_level_values(0)
    return df

def fetch_ohlcv(symbol, period="1d", interval="5m"):
    if symbol=="NSEI":
        return flatten(yf.download("^"+symbol, period=period,
                               interval=interval, progress=False))
    else:
        return flatten(yf.download(symbol+".NS", period=period,
                               interval=interval, progress=False))


    

# ─────────────────────────────────────────────────────────────────
# AUTO-SELECT BEST STRATEGY + AI MODEL
# Backtests every combination on recent 5-day 5-min data,
# picks the combo with highest simulated profit.
# ─────────────────────────────────────────────────────────────────
def pick_best_combo(stock):
    """Returns (best_strategy, best_model, score_dict)."""
    try:
        data = fetch_ohlcv(stock, period="5d", interval="5m")
        if data.empty:
            return list(strategy_map.keys())[0], list(MODEL_BUILDERS.keys())[0], {}
    except Exception:
        return list(strategy_map.keys())[0], list(MODEL_BUILDERS.keys())[0], {}

    scores = {}  # (strategy, model) -> combined_score

    for strat_name, strat_fn in strategy_map.items():
        try:
            strat_profit = strat_fn(data)
        except Exception:
            strat_profit = 0

        for model_name in MODEL_BUILDERS:
            try:
                ai_res    = get_ai_signal(data, model_name)
                ai_score  = ai_res.get('accuracy', 50) * ai_res.get('confidence', 50) / 100
                # Combined: weighted strategy profit + AI score
                # Normalise profit to a 0-100 scale relative to stock price
                price     = float(data['Close'].iloc[-1])
                norm_prof = max(0, strat_profit / price * 100)   # % return
                combined  = 0.6 * norm_prof + 0.4 * ai_score
                scores[(strat_name, model_name)] = {
                    "combined":     round(combined, 2),
                    "strat_profit": round(strat_profit, 2),
                    "ai_accuracy":  ai_res.get('accuracy', 0),
                    "ai_confidence":ai_res.get('confidence', 0),
                }
            except Exception:
                scores[(strat_name, model_name)] = {"combined": 0}

    best_key    = max(scores, key=lambda k: scores[k]["combined"])
    best_strat, best_model = best_key
    return best_strat, best_model, scores


# ── AUTH ──────────────────────────────────────────────────────────
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        fn,ln,dob = request.form['first_name'],request.form['last_name'],request.form['dob']
        un,pw,mob = request.form['username'],request.form['password'],request.form['mobile']
        em = request.form.get('email')
        if not mob: return "Mobile is mandatory!"
        try:
            c = get_db()
            c.execute("INSERT INTO users (first_name,last_name,dob,username,password,mobile,email) VALUES(?,?,?,?,?,?,?)",
                      (fn,ln,dob,un,pw,mob,em))
            c.commit(); c.close()
            return "Registered! <a href='/login'>Login</a>"
        except sqlite3.IntegrityError:
            return "Username taken. <a href='/register'>Try again</a>"
    return render_template('register.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        un,pw = request.form['username'],request.form['password']
        c     = get_db()
        user  = c.execute("SELECT * FROM users WHERE username=? AND password=?",(un,pw)).fetchone()
        c.close()
        if user:
            session['username'] = un; return redirect('/')
        return "Invalid credentials. <a href='/login'>Try again</a>"
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('username',None); return redirect('/login')


# ── HOME ──────────────────────────────────────────────────────────
@app.route('/', methods=['GET','POST'])
def index():
    if 'username' not in session: return redirect('/login')
    selected = (request.form if request.method=='POST' else request.args).get('selected_stock', STOCK_LIST[0])
    if selected not in STOCK_LIST: selected = STOCK_LIST[0]

    conn      = get_db()
    portfolio = conn.execute(
        "SELECT stock,quantity,buy_price,buy_time,strategy,ai_model FROM portfolio WHERE username=?",
        (session['username'],)).fetchall()
    conn.close()

    stock_details = None
    try:
        d   = fetch_ohlcv(selected, period="2d", interval="1d")
        if not d.empty:
            c   = d['Close']; p = round(float(c.iloc[-1]),2)
            chg = round(((p-float(c.iloc[-2]))/float(c.iloc[-2]))*100,2) if len(c)>=2 else 0
            stock_details = {
                "price":  f"₹{p:,.2f}",
                "volume": f"{int(d['Volume'].iloc[-1]):,}",
                "change": f"{'+'if chg>=0 else''}{chg}%",
                "up":     chg>=0
            }
    except Exception:
        pass

    return render_template('home.html',
        username=session['username'], stocks=STOCK_LIST,
        selected_stock=selected, stock_details=stock_details,
        portfolio=portfolio, message=request.args.get('message'))


# ── AJAX: stock chart data ─────────────────────────────────────────
@app.route('/api/chart_data')
def api_chart_data():
    """Returns OHLCV JSON for the home-page chart."""
    if 'username' not in session:
        return jsonify({"error": "Not logged in"})
    stock  = request.args.get('stock', STOCK_LIST[0])
    period = request.args.get('period', '1d')     # 1d / 5d / 1mo
    iv_map = {'1d':'5m', '5d':'15m', '1mo':'1d'}
    iv     = iv_map.get(period, '5m')
    try:
        data = fetch_ohlcv(stock, period=period, interval=iv)
        if data.empty:
            return jsonify({"labels":[], "close":[], "open":[], "high":[], "low":[]})
        labels = [str(t) for t in data.index]
        return jsonify({
            "labels": labels,
            "close":  [round(float(x),2) for x in data['Close']],
            "open":   [round(float(x),2) for x in data['Open']],
            "high":   [round(float(x),2) for x in data['High']],
            "low":    [round(float(x),2) for x in data['Low']],
            "volume": [int(x) for x in data['Volume']],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# ── AJAX: auto-select best combo ───────────────────────────────────
@app.route('/api/best_combo')
def api_best_combo():
    """Backtests all strategy+model combinations and returns the winner."""
    if 'username' not in session:
        return jsonify({"error": "Not logged in"})
    stock = request.args.get('stock', STOCK_LIST[0])
    best_strat, best_model, scores = pick_best_combo(stock)

    # Build leaderboard for display
    board = []
    for (s, m), sc in sorted(scores.items(), key=lambda x: -x[1].get("combined",0)):
        board.append({
            "strategy":    s,
            "model":       m,
            "score":       sc.get("combined", 0),
            "strat_profit":sc.get("strat_profit", 0),
            "ai_accuracy": sc.get("ai_accuracy", 0),
            "ai_confidence":sc.get("ai_confidence", 0),
        })
    return jsonify({
        "best_strategy": best_strat,
        "best_model":    best_model,
        "leaderboard":   board[:6],   # top 6 combos
    })


# ── STRATEGY ──────────────────────────────────────────────────────
@app.route('/strategy', methods=['GET','POST'])
def strategy():
    if 'username' not in session: return redirect('/login')
    conn = get_db()
    if request.method == 'POST':
        conn.execute("INSERT INTO strategies (username,name,logic) VALUES(?,?,?)",
                     (session['username'],request.form['name'],request.form['logic']))
        conn.commit(); conn.close(); return redirect('/strategy')
    strats = conn.execute(
        "SELECT id,name,logic FROM strategies WHERE username IS NULL OR username=?",
        (session['username'],)).fetchall()
    conn.close()
    return render_template('strategy.html', strategies=strats)


@app.route('/delete_strategy', methods=['POST'])
def delete_strategy():
    if 'username' not in session: return redirect('/login')
    conn = get_db()
    conn.execute("DELETE FROM strategies WHERE id=? AND username=?",
                 (request.form['id'],session['username']))
    conn.commit(); conn.close(); return redirect('/strategy')


# ── TRADE (auto-only) ─────────────────────────────────────────────
@app.route('/trade')
def trade():
    if 'username' not in session: return redirect('/login')
    conn = get_db()
    sess = conn.execute(
        "SELECT stock,capital,strategy,ai_model,start_time FROM trading_session "
        "WHERE username=? AND is_active=1 ORDER BY id DESC LIMIT 1",
        (session['username'],)).fetchone()
    positions = conn.execute(
        "SELECT id,stock,quantity,buy_price,buy_time,strategy,ai_model "
        "FROM portfolio WHERE username=? ORDER BY buy_time DESC",
        (session['username'],)).fetchall()
    conn.close()
    return render_template('trade.html',
        stocks=STOCK_LIST,
        session_data=sess, positions=positions,
        hold_minutes=HOLD_MINUTES, stop_loss=STOP_LOSS_PCT, target=TARGET_PCT,
        message=request.args.get('message'))


@app.route('/start_trading', methods=['POST'])
def start_trading():
    if 'username' not in session: return redirect('/login')
    stock   = request.form['stock']
    capital = float(request.form['capital'])
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Auto-pick best strategy + model
    best_strat, best_model, _ = pick_best_combo(stock)

    conn = get_db()
    conn.execute("UPDATE trading_session SET is_active=0 WHERE username=?",
                 (session['username'],))
    conn.execute(
        "INSERT INTO trading_session (username,stock,capital,is_active,start_time,strategy,ai_model) "
        "VALUES(?,?,?,1,?,?,?)",
        (session['username'], stock, capital, now_str, best_strat, best_model))
    conn.commit(); conn.close()
    return redirect('/trade')


@app.route('/stop_trading')
def stop_trading():
    if 'username' not in session: return redirect('/login')
    conn = get_db()
    conn.execute("UPDATE trading_session SET is_active=0 WHERE username=?",
                 (session['username'],))
    conn.commit(); conn.close()
    return redirect('/trade?message=Session stopped')


# ── AJAX: live session status ──────────────────────────────────────
@app.route('/api/session_status')
def api_session_status():
    if 'username' not in session: return jsonify({"error":"Not logged in"})
    conn = get_db()
    sess = conn.execute(
        "SELECT id,stock,capital,strategy,ai_model,start_time FROM trading_session "
        "WHERE username=? AND is_active=1 ORDER BY id DESC LIMIT 1",
        (session['username'],)).fetchone()
    if not sess:
        conn.close(); return jsonify({"active":False})

    stock    = sess['stock']
    strategy = sess['strategy']
    ai_model = sess['ai_model']
    start_dt = datetime.datetime.strptime(sess['start_time'],"%Y-%m-%d %H:%M:%S")
    elapsed  = (datetime.datetime.now()-start_dt).total_seconds()
    remaining= max(0, HOLD_MINUTES*60 - elapsed)

    try:
        data  = fetch_ohlcv(stock)
        price = round(float(data['Close'].iloc[-1]),2)
        prev  = round(float(data['Close'].iloc[-2]),2) if len(data)>=2 else price
        chg   = round(((price-prev)/prev)*100,2)
    except Exception:
        conn.close(); return jsonify({"active":True,"error":"Market data unavailable"})

    strat_signal = "HOLD"
    try:
        if strategy in signal_map:
            strat_signal = signal_map[strategy](data)
    except Exception:
        pass

    ai_result   = get_ai_signal(data, ai_model)
    ai_sig      = ai_result.get('signal', 'HOLD')
    ai_conf     = ai_result.get('confidence', 0) or 0

    positions = conn.execute(
        "SELECT id,quantity,buy_price,buy_time FROM portfolio "
        "WHERE username=? AND stock=?",
        (session['username'], stock)).fetchall()
    now      = datetime.datetime.now()
    pos_list = []
    for p in positions:
        try:
            bt  = datetime.datetime.strptime(p['buy_time'], "%Y-%m-%d %H:%M:%S")
            pnl = round((price - p['buy_price']) * p['quantity'], 2)
            pos_list.append({
                "id": p['id'], "qty": p['quantity'], "buy_price": p['buy_price'],
                "buy_time": p['buy_time'],
                "held_min": round((now - bt).total_seconds() / 60, 1),
                "pnl": pnl,
                "pnl_pct": round(((price - p['buy_price']) / p['buy_price']) * 100, 2)
                           if p['buy_price'] else 0.0
            })
        except Exception:
            continue
    conn.close()

    # ── Weighted final signal ──────────────────────────────────────
    # Score: strategy=1pt, AI=2pt (weighted by confidence)
    # BUY if score > 0, SELL if score < 0, else HOLD
    ai_weight  = (ai_conf / 100.0) * 2.0   # 0–2 points
    strat_pts  = {"BUY": 1, "SELL": -1, "HOLD": 0}
    ai_pts     = {"BUY": ai_weight, "SELL": -ai_weight, "HOLD": 0}
    score      = strat_pts.get(strat_signal, 0) + ai_pts.get(ai_sig, 0)

    if score > 0.5:
        final = "BUY"
    elif score < -0.5:
        final = "SELL"
    else:
        final = "HOLD"

    return jsonify({
        "active": True, "stock": stock, "price": price, "change": chg,
        "capital": sess['capital'], "strategy": strategy, "ai_model": ai_model,
        "start_time": sess['start_time'], "remaining_sec": int(remaining),
        "strat_signal": strat_signal,
        "ai_signal":    ai_sig,
        "ai_confidence":ai_conf,
        "ai_accuracy":  ai_result.get('accuracy', 0),
        "ai_features":  ai_result.get('features', {}),
        "final_signal": final, "positions": pos_list,
        "market_status": "open"
    })


# ── AJAX: execute cycle ────────────────────────────────────────────
@app.route('/api/execute_cycle', methods=['POST'])
def api_execute_cycle():
    if 'username' not in session: return jsonify({"error":"Not logged in"})
    conn = get_db()
    sess = conn.execute(
        "SELECT id,stock,capital,strategy,ai_model,start_time FROM trading_session "
        "WHERE username=? AND is_active=1 ORDER BY id DESC LIMIT 1",
        (session['username'],)).fetchone()
    if not sess:
        conn.close(); return jsonify({"action":"NONE","reason":"No active session"})

    stock    = sess['stock']
    strategy = sess['strategy']
    ai_model = sess['ai_model']
    start_dt = datetime.datetime.strptime(sess['start_time'],"%Y-%m-%d %H:%M:%S")
    elapsed  = (datetime.datetime.now()-start_dt).total_seconds()
    remaining= HOLD_MINUTES*60 - elapsed

    try:
        data  = fetch_ohlcv(stock)
        price = round(float(data['Close'].iloc[-1]),4)
    except Exception as e:
        conn.close(); return jsonify({"action":"ERROR","reason":str(e)})

    now = datetime.datetime.now()

    # Load open positions for THIS stock in THIS session
    positions = conn.execute(
        "SELECT id,quantity,buy_price,buy_time,strategy,ai_model FROM portfolio "
        "WHERE username=? AND stock=? ORDER BY buy_time ASC",
        (session['username'],stock)).fetchall()

    # ── FORCED EXIT CHECK ─────────────────────────────────────────
    forced_reason = None
    if remaining <= 0:
        forced_reason = "TIME_EXIT"
    else:
        for p in positions:
            pnl_pct = ((price - p['buy_price']) / p['buy_price']) * 100
            if pnl_pct <= -STOP_LOSS_PCT:
                forced_reason = "STOP_LOSS"; break
            if pnl_pct >= TARGET_PCT:
                forced_reason = "TARGET_HIT"; break

    if forced_reason and positions:
        total = 0.0
        st    = now.strftime("%Y-%m-%d %H:%M:%S")
        for p in positions:
            pnl = round((price - p['buy_price']) * p['quantity'], 4)
            total += pnl
            conn.execute(
                "INSERT INTO trade_history "
                "(username,stock,quantity,buy_price,sell_price,profit,"
                "buy_time,sell_time,strategy,ai_model) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (session['username'],stock,p['quantity'],p['buy_price'],
                 price,pnl,p['buy_time'],st,p['strategy'],p['ai_model']))
            conn.execute("DELETE FROM portfolio WHERE id=?",(p['id'],))
        if forced_reason == "TIME_EXIT":
            conn.execute("UPDATE trading_session SET is_active=0 WHERE username=?",
                         (session['username'],))
        conn.commit(); conn.close()
        return jsonify({"actions":[{
            "action":"SELL","reason":forced_reason,
            "price":price,"pnl":round(total,2)
        }]})

    # ── SIGNAL-BASED TRADING ──────────────────────────────────────
    has_pos   = len(positions) > 0
    strat_sig = "HOLD"
    try:
        if strategy in signal_map:
            strat_sig = signal_map[strategy](data)
    except Exception:
        pass

    ai_res   = get_ai_signal(data, ai_model)
    ai_sig   = ai_res.get('signal', 'HOLD')
    ai_conf  = float(ai_res.get('confidence', 0) or 0)
    actions  = []

    # Weighted score: strategy=1pt, AI weighted by confidence (0-2pt)
    ai_weight = (ai_conf / 100.0) * 2.0
    strat_pts = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}
    ai_pts    = {"BUY": ai_weight, "SELL": -ai_weight, "HOLD": 0.0}
    score     = strat_pts.get(strat_sig, 0) + ai_pts.get(ai_sig, 0)

    # BUY: positive score, no open position, >60s left in window
    if score > 0.5 and not has_pos and remaining > 60:
        qty = int(sess['capital'] / price)
        if qty > 0:
            conn.execute(
                "INSERT INTO portfolio "
                "(username,stock,quantity,buy_price,buy_time,strategy,ai_model) "
                "VALUES(?,?,?,?,?,?,?)",
                (session['username'], stock, qty, price,
                 now.strftime("%Y-%m-%d %H:%M:%S"), strategy, ai_model))
            conn.commit()
            actions.append({
                "action": "BUY", "reason": "SIGNAL", "price": price,
                "qty": qty, "confidence": round(ai_conf, 1)
            })

    # SELL: negative score, ONLY if holding a position (bought first)
    elif score < -0.5 and has_pos:
        total = 0.0
        st    = now.strftime("%Y-%m-%d %H:%M:%S")
        for p in positions:
            pnl = round((price - p['buy_price']) * p['quantity'], 4)
            total += pnl
            conn.execute(
                "INSERT INTO trade_history "
                "(username,stock,quantity,buy_price,sell_price,profit,"
                "buy_time,sell_time,strategy,ai_model) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (session['username'],stock,p['quantity'],p['buy_price'],
                 price,pnl,p['buy_time'],st,p['strategy'],p['ai_model']))
            conn.execute("DELETE FROM portfolio WHERE id=?",(p['id'],))
        conn.commit()
        actions.append({
            "action":"SELL","reason":"SIGNAL",
            "price":price,"pnl":round(total,2)
        })

    conn.close()
    return jsonify({"actions": actions if actions else [{"action":"HOLD","price":price}]})


# ── HISTORY (only completed buy→sell trades) ───────────────────────
@app.route('/history')
def history():
    if 'username' not in session: return redirect('/login')
    conn   = get_db()
    # Only rows that have BOTH buy_price AND sell_price filled
    # sell_time NOT NULL means trade is completed
    trades = conn.execute(
        "SELECT stock,quantity,buy_price,sell_price,profit,"
        "strategy,ai_model,buy_time,sell_time "
        "FROM trade_history "
        "WHERE username=? AND sell_price IS NOT NULL AND sell_time IS NOT NULL "
        "ORDER BY sell_time DESC",
        (session['username'],)).fetchall()

    total  = sum(t['profit'] for t in trades if t['profit'])
    wins   = sum(1 for t in trades if t['profit'] and t['profit'] > 0)
    losses = sum(1 for t in trades if t['profit'] and t['profit'] < 0)
    wr     = round((wins/len(trades))*100, 1) if trades else 0
    conn.close()
    return render_template('history.html', history=trades,
        total_pnl=round(total,2), wins=wins, losses=losses, win_rate=wr)


# ── BACKTEST ──────────────────────────────────────────────────────
@app.route('/backtest', methods=['GET','POST'])
def backtest():
    if 'username' not in session: return redirect('/login')
    conn   = get_db()
    strats = conn.execute(
        "SELECT name FROM strategies WHERE username IS NULL OR username=?",
        (session['username'],)).fetchall()
    conn.close()
    result = request.args.get('result')

    if request.method == 'POST':
        stock    = request.form.get('stock')
        strat    = request.form.get('strategy')
        ai_model = request.form.get('ai_model','Random Forest')
        try:
            data = fetch_ohlcv(stock, period="5d")
            if data.empty:
                result = "No Data Found"
            else:
                sp  = strategy_map[strat](data) if strat in strategy_map else None
                ar  = get_ai_signal(data, ai_model)
                lines = [
                    f"Stock: {stock}  |  Strategy: {strat}  |  AI: {ai_model}",
                    "─" * 48,
                ]
                if sp is not None:
                    lines.append(f"Strategy Simulated Profit:  ₹{sp}")
                lines += [
                    f"AI Signal:      {ar['signal']}",
                    f"Confidence:     {ar.get('confidence',0)}%",
                    f"Model Accuracy: {ar.get('accuracy',0)}%",
                ]
                if 'features' in ar:
                    lines.append("── Last-bar Indicators ──")
                    for k,v in ar['features'].items():
                        lines.append(f"  {k}: {v}")
                result = "\n".join(lines)
        except Exception as e:
            result = f"Error: {e}"
        return redirect(f"/backtest?result={quote(result)}")

    return render_template('backtest.html',
        stocks=STOCK_LIST, strategies=strats,
        ai_models=list(MODEL_BUILDERS.keys()), result=result)


if __name__ == "__main__":
    app.run(debug=True, threaded=True)