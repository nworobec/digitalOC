# DigitalOC

An intelligent NFL play-calling assistant that leverages machine learning and real play-by-play data to recommend optimal offensive plays for any game situation.

## Overview

DigitalOC is a full-stack web application that combines NFL play-by-play data, team Elo ratings, and Next Gen Stats to power ML models that predict the best offensive strategy. The app features an interactive React frontend where users can input game situations and receive AI-driven play recommendations with visual play diagrams.

## Experimental outcome comparison

A new local baseline separates historical run/pass call probability from expected EPA and yards, evaluates both actions, and reports results on later seasons. See the [baseline setup and measured results](docs/decision-support-baseline.md) and [development roadmap](docs/model-development-plan.md). It now powers the main dashboard while validation continues; the legacy suggestion flow remains available.

## Public Version

You can access the public version of the app here: https://digital-oc-sigma.vercel.app

**⚠️ Note: Since the backend is deployed on the Render Free Tier, response times may take long especially after not using the app for some time.**

## Features

- **Interactive Situation Input**: Modern UI with team selection, down/distance, field position, score, time, and timeout tracking
- **Dynamic Team Branding**: Real-time gradient backgrounds using official NFL team colors
- **ML-Powered Predictions**: 
  - Play type classification (run vs. pass)
  - Run play metrics prediction (EPA, success rate, yards gained)
  - Pass play metrics prediction (completion probability, air yards, YAC)
- **Visual Play Diagrams**: Automated route visualization with receiver positions and routes
- **Real-Time Results**: Side-by-side comparison of situation details and recommended plays

## Tech Stack

### Deployment
- **Frontend**: Vercel
- **Backend**: Render (Free Tier)

### Frontend
- **React 19.2** with React Router for navigation
- **Custom CSS** with gradient animations and team-specific theming
- **Orbitron font** for a modern, futuristic aesthetic
- Dynamic form validation and interactive UI components

### Backend
- **Flask** API with CORS support
- **scikit-learn** for ML models (Random Forest, Logistic Regression, Linear Regression)
- **pandas** for data processing and feature engineering
- **matplotlib** for play visualization generation
- Team Elo rating system for performance-based predictions

### Data Sources
- nflreadpy library for accessing and processing NFL play-by-play data
- NFL play-by-play data (2020-2024 seasons)
- Next Gen Stats (passing, receiving, rushing metrics)
- Snap counts and participation data
- Custom team Elo ratings

### ML Models

The ML models are saved to and read from **GitHub Releases** due to their size. The training scripts are included in located in `backend/model_trainers/` and are loaded by the Flask API server at startup. The models are as follows:

- **Play-by-Play Situation Model**: Random Forest Classifier to predict run vs. pass based on game situation features
- **Run Model**: Random Forest Classifier to predict the optimal run gap, run location, offensive formation, and offensive personnel
- **Pass Model**: Random Forest Classifier to predict the optimal receiver position, pass location, offensive formation, and offensive personnel
- **Expected Metrics Models (Run/Pass)**: Linear Regression models to predict expected points added (EPA), completion probability, and yards gained



## Project Structure

```
digitalOC/
├── frontend/                 # React application
│   ├── src/
│   │   ├── pages/
│   │   │   ├── HomePage/       # Landing page
│   │   │   ├── SituationPage/  # Game situation input
│   │   │   └── ResultPage/     # Play recommendations & visualization
│   │   └── logos/              # NFL team logos (32 teams)
│   │   
└── backend/                 # Flask API and ML models
    ├── app.py                   # Flask API server, loads the trained models from GitHub Releases
    ├── requirements.txt         # Python dependencies
    ├── model_trainers/          # Scripts and helper files to train ML models
    ├── routeDrawer/             # Play visualization module
    ├── data/                    # NFL datasets (PBP, Next Gen Stats)
    ├── getData/                 # Data processing and feature engineering scripts
    └── cleanData/               # Data cleaning scripts
```

## Getting Started

### Prerequisites
- Python 3.8+
- Node.js 14+
- npm or yarn

### Model Training

-  Run the training scripts for each model:
```bash
cd backend
python model_trainers/pbp_situation_model.py
python model_trainers/run_model.py
python model_trainers/pass_model.py
python model_trainers/expected_run_yards_model.py
python model_trainers/expected_pass_yards_model.py
```
-  Trained model artifacts will be saved to `backend/models/`.

### Connected dashboard (default UI)

From the repository root, start the dashboard API:

```bash
python3 -m backend.decision_support.api
```

Then run `npm start` inside `frontend/` and open http://localhost:3000. The dashboard API uses port **5001**, with persistent local sessions in SQLite. If the local model is missing, train it with `python3 -m backend.decision_support.train` first.

See [connected dashboard setup, capabilities, and testing](docs/connected-dashboard.md). `/preview` retains the visual mockup; `/welcome` opens the legacy flow.

### Legacy Backend Setup

1. Clone the repository:
```bash
git clone https://github.com/nworobec/digitalOC.git
cd digitalOC
```

2. Install Python dependencies:
```bash
pip install flask flask-cors pandas scikit-learn matplotlib numpy
```

3. Navigate to backend directory:
```bash
cd backend
```

4. Start the Flask server:
```bash
python app.py
```
The API will run on `http://localhost:5000`

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm start
```
The app will open at `http://localhost:3000`

## 📊 Models & Data Processing

### Play-by-Play Situation Model
- **Input Features**: Down, yards to go, field position, score differential, time remaining, timeouts, team Elo
- **Output**: Play type recommendation (run/pass)
- **Algorithm**: Random Forest Classifier
- **Training Data**: 2024 NFL season play-by-play data

### Run Model
Predicts expected metrics for run plays:
- Expected Points Added (EPA)
- Success rate
- Yards gained

### Pass Model
Predicts expected metrics for pass plays:
- Completion probability
- Air yards
- Yards after catch (YAC)

### Team Elo System
Custom Elo ratings categorized by play situation (e.g., early down, late & long, goal line) to capture team strength in different scenarios.

## Contributors
**Noah Worobec** ([@nworobec](https://github.com/nworobec))\
**Russell C** ([@russellchao](https://github.com/russellchao))\
**Gavin C** ([@gavinc1225](https://github.com/gavinc1225))\
**Nicole S** ([@nstepanenko464](https://github.com/nstepanenko464))\
**Daniel M** ([@DanKMM](https://github.com/DanKMM))\
**Olakiite F** ([@fatuko](https://github.com/fatuko))\
**Rondalph T** ([legffy](https://github.com/legffy)),\
**Rafiki M** ([@RafikiMwethuku](https://github.com/RafikiMwethuku))\
**Ryan D** ([@desour2](https://github.com/desour2))\
**Minh Nghia (Ben) H** ([@NghiaMinhHuynh](https://github.com/NghiaMinhHuynh))


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Related Links

- [NFL Play-by-Play Data](https://github.com/nflverse/nflverse-data)
- [Next Gen Stats](https://nextgenstats.nfl.com/)

## Future Enhancements

- Personnel grouping recommendations
- Historical success rate comparisons
- Real-time game integration
- Advanced route tree customization
- Defensive formation predictions
- Multi-season model training
