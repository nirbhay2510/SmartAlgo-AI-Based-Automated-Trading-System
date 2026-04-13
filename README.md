🚀 SmartAlgo – AI-Based Algorithmic Trading System
SmartAlgo is an intelligent algorithmic trading system that uses Machine Learning to analyze real-time stock market data and automatically generate trading decisions (Buy/Sell/Hold).

📌 Overview
SmartAlgo simulates real-world automated trading by combining:
Real-time data processing
Machine learning predictions
Strategy-based decision making
Automated trade execution
Performance tracking dashboard

✨ Features
📊 Real-time stock data fetching
🤖 ML models (LSTM, Random Forest, SVM)
📈 Buy/Sell/Hold signal generation
⚙️ Strategy-based trade selection
💰 Automated trade execution
🗄️ Trade history storage
📉 Profit/Loss tracking
📺 Dashboard visualization

🧠 Tech Stack
Programming: Python, Flask 
ML: TensorFlow, Scikit-learn
Data: Pandas, NumPy
API: Stock Market API
Database: SQLite 
Frontend: HTML, CSS, JS

⚙️ How It Works
Connects to stock market API
Fetches real-time data
Preprocesses data
Applies ML models
Generates trading signals
Selects best signal
Executes trade
Stores results
Updates dashboard

🏗️Project Structure
SMARTALGO/
│
├── src/
│   ├── app.py                     # Main application (Flask/Dashboard)
│   ├── ai_models.py               # ML models (LSTM, RF, SVM)
│   ├── trading_engine.py          # Trade execution logic
│   ├── strategy_logic.py          # Strategy rules
│
├── database/
│        ├── database.db            # SQLite database
│        └── db_handler.py          # DB operations (rename from raw usage)
│   
│   
│

├── templates/                 # HTML files
│      ├── home.html
│      ├── login.html
│      ├── register.html
│      ├── trade.html
│      ├── strategy.html
│      ├── history.html
│      ├── backtest.html
│      ├── options.html
│      └── options_history.html
│   
├── static/
│     ├── css/
│     ├── js/
│     └── images/
│           ├── logo.png
│           ├── background.jpg
│           └── user.svg


🤝 Contributors
Ayush Singh
Naman Kumar
Kunal Sehrawat
Nirbhay Sisodia
