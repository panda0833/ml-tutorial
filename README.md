# Hands-On Machine Learning Tutorial (Handwritten Digits)

Learn the basics of machine learning by training a model on a free handwriting dataset: the **scikit-learn digits** dataset. This project is intentionally small and readable, so you can follow each step end-to-end.

## What you'll build

- Load a handwriting dataset (8x8 grayscale digits).
- Split data into train/test sets.
- Train a simple classifier.
- Evaluate accuracy and save the trained model.
- Visualize sample digits and a confusion matrix.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/train.py
python src/visualize.py
python src/predict.py --index 0
```

Artifacts (model + metrics) are saved in `artifacts/`.

## Project layout

```
.
├── artifacts/           # Saved models and metrics
├── src/
│   ├── train.py         # Train and evaluate a classifier
│   ├── visualize.py     # Visualize digits and confusion matrix
│   └── predict.py       # Load a model and predict a single sample
├── tutorial.md          # Step-by-step tutorial
├── requirements.txt
└── .gitignore
```

## Why this dataset?

The digits dataset is free, built into scikit-learn, and requires no downloads. It is a perfect starting point for learning the ML workflow without extra setup.

## Next ideas

- Try a different model (SVM, Random Forest).
- Add preprocessing (PCA, normalization).
- Export the model and build a tiny web UI to draw digits.

